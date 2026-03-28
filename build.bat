@echo off
REM =============================================================================
REM  KangPaket — Windows Build Script (PyInstaller)
REM  Usage: build.bat
REM  Output: dist\KangPaket.exe
REM =============================================================================

setlocal EnableDelayedExpansion

set APP_NAME=KangPaket
set ENTRY=main.py
set ICON_SRC=assets\KangPaket-ico.png
set ICON_ICO=assets\KangPaket-ico.ico

echo ^> Building %APP_NAME% for Windows...

REM Resolve Python
set PYTHON=
if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
) else (
    where python >nul 2>&1
    if !errorlevel! == 0 (
        set PYTHON=python
    ) else (
        where python3 >nul 2>&1
        if !errorlevel! == 0 (
            set PYTHON=python3
        ) else (
            echo ERROR: Python not found.
            exit /b 1
        )
    )
)
echo   Python: %PYTHON%

REM Check PyInstaller
%PYTHON% -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not found. Install with: pip install pyinstaller
    exit /b 1
)

REM Convert PNG -> ICO using Pillow
echo   Converting icon PNG ^> ICO...
%PYTHON% -c "from PIL import Image; img = Image.open('%ICON_SRC%'); img.save('%ICON_ICO%', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if errorlevel 1 (
    echo ERROR: Icon conversion failed. Make sure Pillow is installed ^(pip install Pillow^).
    exit /b 1
)
echo   ICO generated: %ICON_ICO%

REM Clean previous build
if exist build\ rmdir /s /q build\
if exist dist\ rmdir /s /q dist\
del /q *.spec 2>nul

REM Run PyInstaller
REM --onefile     : pack Python runtime + all libs into a single .exe (no _internal folder)
REM --collect-all : must be WITHOUT quotes around module name
echo   Running PyInstaller...
%PYTHON% -m PyInstaller --noconfirm --clean --onefile --name %APP_NAME% --windowed --icon %ICON_ICO% --add-data "data;data" --add-data "assets;assets" --collect-all customtkinter --collect-all darkdetect --hidden-import customtkinter --hidden-import darkdetect --hidden-import tkinter --hidden-import _tkinter --hidden-import PIL --hidden-import PIL.Image --hidden-import httpx --hidden-import jsonpath_ng %ENTRY%

if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

echo.
echo Build complete: dist\%APP_NAME%.exe  (single self-contained .exe, no Python required)
echo The .exe runs without Python installed on the target machine.
endlocal
