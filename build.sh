#!/usr/bin/env bash
# =============================================================================
# KangPaket — Build script (PyInstaller)
# Usage:
#   ./build.sh           → detect platform and build
#   ./build.sh macos     → macOS single .app bundle
#   ./build.sh linux     → Linux single binary
#   ./build.sh windows   → Windows single .exe (run on Windows instead)
#
# Output is always a single self-contained file — no separate dependency folder.
#   macOS  → dist/KangPaket.app  (single .app bundle)
#   Linux  → dist/KangPaket      (single binary)
#   Windows→ dist/KangPaket.exe  (single .exe)
# Python is NOT required on the target machine to run the output.
# =============================================================================

set -euo pipefail

APP_NAME="KangPaket"
ENTRY="main.py"
ICON_SRC="assets/KangPaket-ico.png"   # Source icon (PNG)
ICON_WIN="assets/KangPaket-ico.ico"
ICON_MAC="assets/KangPaket-ico.icns"  # Generated from PNG
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

echo "▶  Building KangPaket for: $PLATFORM  (single-file output)"
echo "   Entry: $ENTRY"

# Resolve Python (only needed to BUILD — not needed to run the output binary)
if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "❌ Python not found. Python is required to BUILD (not to run the output)."
    exit 1
fi
echo "   Python: $PYTHON"

# Ensure PyInstaller is available
if ! $PYTHON -m PyInstaller --version &>/dev/null 2>&1; then
    echo "❌ PyInstaller not found. Install with: pip install pyinstaller"
    exit 1
fi

# Clean previous build
rm -rf build/ dist/ *.spec

# Common PyInstaller flags shared by all platforms
# --onefile: pack Python runtime + all libs into a single output binary/bundle
COMMON=(
    --noconfirm
    --clean
    --onefile
    --name "$APP_NAME"
    --add-data "data:data"
    --add-data "assets:assets"
    --collect-all "customtkinter"
    --collect-all "darkdetect"
    --hidden-import "customtkinter"
    --hidden-import "darkdetect"
    --hidden-import "tkinter"
    --hidden-import "_tkinter"
    --hidden-import "PIL"
    --hidden-import "PIL.Image"
    --hidden-import "httpx"
    --hidden-import "jsonpath_ng"
)

case "$PLATFORM" in
    macos)
        echo "   Building macOS single .app bundle…"

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
        echo "✅ Build complete: dist/$APP_NAME.app  (single self-contained .app)"
        ;;

    linux)
        echo "   Building Linux single binary…"
        $PYTHON -m PyInstaller \
            "${COMMON[@]}" \
            --windowed \
            --icon "$ICON_LIN" \
            "$ENTRY"
        echo "✅ Build complete: dist/$APP_NAME  (single self-contained binary)"
        ;;

    windows)
        echo "   Windows build: run build.bat on a Windows machine instead."
        echo "   (Cross-compilation is not supported by PyInstaller)"
        exit 0
        ;;

    *)
        echo "❌ Unknown platform: $PLATFORM"
        echo "   Usage: ./build.sh [macos|linux|windows]"
        exit 1
        ;;
esac

echo ""
echo "📦 Output: dist/$APP_NAME"
echo "   The binary is fully self-contained — Python is NOT required on the target machine."
