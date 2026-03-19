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
ICON_WIN="assets/icon.ico"
ICON_MAC="assets/icon.png"
ICON_LIN="assets/icon.png"

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

# Ensure PyInstaller is available
if ! python -m PyInstaller --version &>/dev/null 2>&1; then
    echo "❌ PyInstaller tidak ditemukan. Install dengan: pip install pyinstaller"
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
        python -m PyInstaller \
            "${COMMON[@]}" \
            --windowed \
            --icon "$ICON_MAC" \
            --osx-bundle-identifier "com.internal.kangpaket" \
            "$ENTRY"
        echo "✅ Build selesai: dist/$APP_NAME.app"
        ;;

    windows)
        echo "   Building Windows .exe…"
        python -m PyInstaller \
            "${COMMON[@]}" \
            --windowed \
            --icon "$ICON_WIN" \
            "$ENTRY"
        echo "✅ Build selesai: dist/$APP_NAME.exe"
        ;;

    linux)
        echo "   Building Linux binary…"
        python -m PyInstaller \
            "${COMMON[@]}" \
            --windowed \
            --icon "$ICON_LIN" \
            "$ENTRY"
        echo "✅ Build selesai: dist/$APP_NAME"
        ;;

    *)
        echo "❌ Platform tidak dikenali: $PLATFORM"
        echo "   Gunakan: ./build.sh [macos|windows|linux]"
        exit 1
        ;;
esac

echo ""
echo "📦 Output ada di: dist/$APP_NAME"
