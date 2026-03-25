#!/usr/bin/env bash
# =============================================================================
# KangPaket — Build script (PyInstaller)
# Usage:
#   ./build.sh           → detect platform and build
#   ./build.sh windows   → cross-build hint (run on Windows)
#   ./build.sh macos     → macOS .app bundle
#   ./build.sh linux     → Linux binary
# =============================================================================

set -euo pipefail

APP_NAME="KangPaket"
ENTRY="main.py"
ICON_SRC="assets/KangPaket-ico.png"   # Source icon (PNG)
ICON_WIN="assets/KangPaket-ico.ico"
ICON_MAC="assets/KangPaket-ico.icns"  # Will be generated from PNG
ICON_LIN="assets/KangPaket-ico.png"

# Detect platform
PLATFORM="${1:-auto}"
if [ "$PLATFORM" = "auto" ]; then
    case "$(uname -s)" in
        Darwin)  PLATFORM="macos" ;;
        Linux)   PLATFORM="linux" ;;
        MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
        *)       PLATFORM="linux" ;;
    esac
fi

echo "▶  Building KangPaket for: $PLATFORM"
echo "   Entry: $ENTRY"

# Resolve Python: prefer local .venv, then python3, then python
if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "❌ Python not found."
    exit 1
fi

# Ensure PyInstaller is available
if ! $PYTHON -m PyInstaller --version &>/dev/null 2>&1; then
    echo "❌ PyInstaller not found. Install with: pip install pyinstaller"
    exit 1
fi

# Clean previous build
rm -rf build/ dist/ *.spec

# Common PyInstaller flags
COMMON=(
    --noconfirm
    --clean
    --name "$APP_NAME"
    --add-data "data:data"
    --add-data "assets:assets"
    --hidden-import "customtkinter"
    --hidden-import "PIL"
    --hidden-import "PIL.Image"
    --hidden-import "httpx"
    --hidden-import "jsonpath_ng"
    --collect-all "customtkinter"
)

case "$PLATFORM" in
    macos)
        echo "   Building macOS .app bundle…"

        # Convert PNG → .icns using built-in macOS tools
        echo "   Converting icon PNG → ICNS…"
        ICONSET_DIR="assets/KangPaket-ico.iconset"
        mkdir -p "$ICONSET_DIR"
        for size in 16 32 64 128 256 512; do
            sips -z $size $size "$ICON_SRC" \
                --out "$ICONSET_DIR/icon_${size}x${size}.png"      &>/dev/null
            sips -z $((size*2)) $((size*2)) "$ICON_SRC" \
                --out "$ICONSET_DIR/icon_${size}x${size}@2x.png"   &>/dev/null
        done
        iconutil -c icns "$ICONSET_DIR" -o "$ICON_MAC"
        rm -rf "$ICONSET_DIR"
        echo "   ICNS generated: $ICON_MAC"

        $PYTHON -m PyInstaller \
            "${COMMON[@]}" \
            --windowed \
            --icon "$ICON_MAC" \
            --osx-bundle-identifier "com.internal.kangpaket" \
            "$ENTRY"
        echo "✅ Build complete: dist/$APP_NAME.app"
        ;;

    windows)
        echo "   Building Windows .exe…"

        # Convert PNG → .ico using Pillow
        echo "   Converting icon PNG → ICO…"
        $PYTHON -c "
from PIL import Image
img = Image.open('$ICON_SRC')
img.save('$ICON_WIN', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
"
        echo "   ICO generated: $ICON_WIN"

        $PYTHON -m PyInstaller \
            "${COMMON[@]}" \
            --windowed \
            --icon "$ICON_WIN" \
            "$ENTRY"
        echo "✅ Build complete: dist/$APP_NAME.exe"
        ;;

    linux)
        echo "   Building Linux binary…"
        $PYTHON -m PyInstaller \
            "${COMMON[@]}" \
            --windowed \
            --icon "$ICON_LIN" \
            "$ENTRY"
        echo "✅ Build complete: dist/$APP_NAME"
        ;;

    *)
        echo "❌ Unknown platform: $PLATFORM"
        echo "   Usage: ./build.sh [macos|windows|linux]"
        exit 1
        ;;
esac

echo ""
echo "📦 Output: dist/$APP_NAME"
