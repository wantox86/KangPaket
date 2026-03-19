# KangPaket

**Internal HTTP API Client Desktop App** — a lightweight, offline, and portable alternative to Postman.

## Features

- All HTTP methods: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS
- Request tabs: Params, Headers, Body (raw / form-data / urlencoded), Auth (Bearer / Basic / API Key), Settings
- Response viewer: JSON syntax highlighting, Headers, Cookies, and Info tabs
- Save and manage request profiles organized by collection
- Collection Runner: sequential / parallel execution with assertions and CSV variable support
- Import from Postman Collection v2.0 & v2.1
- Export / import profiles across machines
- Dark / light theme, configurable font size, proxy support

## Requirements

- Python 3.11+
- tkinter (bundled with Python, or `brew install python-tk` on macOS)

## Installation & Running

```bash
# Clone / copy the project
cd KangPaket

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

## Build Executable

```bash
# macOS
./build.sh macos       # → dist/KangPaket.app

# Linux
./build.sh linux       # → dist/KangPaket

# Windows (run on a Windows machine)
build.sh windows       # → dist/KangPaket.exe
```

> The build script automatically converts the PNG icon to `.icns` on macOS using the built-in `sips` and `iconutil` tools.

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Send request |
| `Ctrl+N` | New request |
| `Ctrl+S` | Save profile |
| `Ctrl+,` | Open Settings |
| `Ctrl+E` | Export profiles |
| `Ctrl+L` | Clear response |

## Data Storage

Profiles are saved to `data/profiles/<uuid>.json`.
Global settings are stored in `data/settings.json`.
Runner results are saved to `data/runner_results/`.

## License

GNU General Public License v3.0
