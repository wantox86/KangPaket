# Copilot Instructions — KangPaket

## Project Overview

**KangPaket** is a lightweight, offline, portable desktop HTTP API client built with Python and CustomTkinter. It is an alternative to Postman, intended for internal API testing without requiring cloud accounts or internet access.

- **Version**: 1.0.1
- **Language**: Python 3.11+
- **UI Framework**: [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) (`customtkinter>=5.2.0`)
- **HTTP Client**: `httpx>=0.27.0`
- **Image processing**: `Pillow>=10.0.0`
- **JSONPath assertions**: `jsonpath-ng>=1.6.0`
- **Packaging**: PyInstaller (`KangPaket.spec`)
- **License**: GPL v3.0

---

## Project Structure

```
KangPaket/
├── main.py                     # Entry point — initializes SettingsManager and AppWindow
├── pyproject.toml
├── requirements.txt
├── KangPaket.spec              # PyInstaller build spec
├── build.sh                    # Build script for macOS / Linux
├── build.bat                   # Build script for Windows
├── assets/                     # App icon and static assets
├── data/                       # Runtime data (gitignored)
│   ├── profiles/               # Saved request profiles (<uuid>.json)
│   ├── runner_results/         # Collection runner results
│   └── settings.json           # Global app settings
├── tests/
│   ├── sample_postman_v21.json # Postman Collection v2.1 sample
│   └── sample_variables.csv   # CSV variable sample for runner
└── app/
    ├── config.py               # App-wide constants (HTTP methods, colors, paths)
    ├── core/
    │   ├── http_client.py      # HTTP request execution (via httpx)
    │   ├── postman_importer.py # Postman Collection v2.0 & v2.1 import
    │   ├── profile_manager.py  # Save/load/export/import request profiles
    │   ├── runner_engine.py    # Collection runner (sequential & parallel, CSV vars)
    │   └── settings_manager.py # Persist and load app settings
    ├── models/
    │   ├── request_model.py    # RequestModel dataclass
    │   ├── response_model.py   # ResponseModel dataclass
    │   └── runner_model.py     # RunnerResult / assertion models
    └── ui/
        ├── app_window.py           # Main application window
        ├── postman_import_dialog.py
        ├── profile_dialog.py
        ├── request_panel.py        # Request builder (method, URL, tabs)
        ├── response_panel.py       # Response viewer (JSON, headers, cookies, info)
        ├── runner_window.py        # Collection runner window
        ├── settings_dialog.py
        ├── sidebar.py              # Collections & profiles sidebar
        └── widgets/
            ├── json_viewer.py      # Syntax-highlighted JSON viewer
            ├── key_value_editor.py # Reusable key-value table editor
            ├── runner_result_row.py
            └── status_bar.py
```

---

## Architecture & Conventions

### Separation of concerns
- **`app/core/`** — pure business logic; no UI imports allowed here
- **`app/models/`** — plain dataclasses; no logic, no UI, no I/O
- **`app/ui/`** — all CustomTkinter widgets and windows
- **`app/config.py`** — single source of truth for constants, colors, and paths

### Coding style
- Python type hints on all function signatures
- Docstrings on modules and public methods (triple-quoted, concise)
- No global mutable state outside `SettingsManager` and `ProfileManager`
- UI components receive dependencies via constructor injection (no direct imports of managers inside widgets)
- All file I/O goes through `data/` — never write to `app/` or `assets/`

### Data flow
```
UI events → core methods → models → JSON persistence in data/
```

### HTTP requests
- All requests go through `app/core/http_client.py` using `httpx`
- Proxy settings come from `SettingsManager`
- Timeouts and SSL verification are configurable per-request via Settings tab

### Profiles
- Stored as individual JSON files in `data/profiles/<uuid>.json`
- Each profile maps to a `RequestModel`
- Collections are logical groupings stored in profile metadata, not separate files

### Runner
- `runner_engine.py` supports sequential and parallel modes
- Variables are resolved from CSV (`data/` path) before each request
- Assertions use JSONPath expressions via `jsonpath-ng`

---

## Key Constants (`app/config.py`)

| Constant | Description |
|---|---|
| `APP_VERSION` | Current version string (`"1.0.1"`) |
| `HTTP_METHODS` | Ordered list of supported HTTP verbs |
| `METHOD_COLORS` | Display colors per HTTP method |
| `BODY_TYPES` | `none`, `raw`, `form-data`, `x-www-form-urlencoded` |
| `AUTH_TYPES` | `none`, `bearer`, `basic`, `api-key` |
| `RAW_CONTENT_TYPES` | Supported Content-Type options for raw body |
| `DATA_DIR` | Absolute path to `data/` folder |
| `PROFILES_DIR` | Absolute path to `data/profiles/` |
| `RESULTS_DIR` | Absolute path to `data/runner_results/` |
| `SETTINGS_FILE` | Absolute path to `data/settings.json` |

---

## Build

```bash
# macOS
./build.sh macos    # → dist/KangPaket.app

# Linux
./build.sh linux    # → dist/KangPaket

# Windows
build.bat           # → dist\KangPaket.exe
```

Icons are auto-converted from PNG in `assets/` using `sips`/`iconutil` (macOS) or Pillow (Windows). Generated `.icns`/`.ico` files are gitignored.

---

## What to Avoid

- Do **not** import UI modules from `app/core/` or `app/models/`
- Do **not** hardcode paths — always use constants from `app/config.py`
- Do **not** add runtime data files to version control (`data/` is gitignored)
- Do **not** use `requests` library — the project uses `httpx`
- Do **not** use `tkinter` directly — always use `customtkinter` equivalents
