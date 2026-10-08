# KangPaket

**Internal HTTP API Client Desktop App** — a lightweight, offline, and portable alternative to Postman.

## Features

- All HTTP methods: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS
- Request tabs: Params, Headers, Body (raw / form-data / urlencoded), Auth (Bearer / Basic / API Key), Assertions, Settings
- Response viewer: JSON syntax highlighting, Headers, Cookies, and Info tabs
- Save and manage request profiles organized by collection
- Collection Runner: sequential / parallel execution with per-request assertions and CSV variable support
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

**macOS / Linux** — run in a terminal:
```bash
./build.sh macos       # → dist/KangPaket.app
./build.sh linux       # → dist/KangPaket
```

**Windows** — run in Command Prompt or PowerShell:
```bat
build.bat              # → dist\KangPaket.exe
```

> **Icon conversion is automatic:**
> - macOS: PNG → `.icns` via built-in `sips` + `iconutil`
> - Windows: PNG → `.ico` via Pillow (included in `requirements.txt`)
> - Generated icon files are excluded from version control via `.gitignore`

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Send request |
| `Ctrl+N` | New request |
| `Ctrl+S` | Save profile |
| `Ctrl+,` | Open Settings |
| `Ctrl+E` | Export profiles |
| `Ctrl+L` | Clear response |

## Cloud Sync

KangPaket can sync your profiles and environments across devices through a KangPaket sync server (optional; the app works fully offline without it).

- **Login**: click the account button (top bar, shows "Belum login") or `Tools > Akun Cloud Sync…`, enter username and password. Registration is done by the server admin. After the first login your local and server data are merged (nothing is lost). The password is never stored; only a refresh token is kept in `data/sync_state.json` (owner-only permissions).
- **What is synced**: request profiles (including collection/folder), environments and global variables. Edits sync automatically a few seconds after you save; switching the active environment does not trigger a sync. Profiles above 256 KiB are skipped (and reported in the account dialog).
- **Auth fields are synced as-is**: bearer tokens, basic-auth passwords, API keys and secret variables are stored **in plaintext on the sync server** (not encrypted). Only use a server you trust, and avoid syncing real production secrets.
- **Offline behaviour**: if the server is unreachable the app keeps working locally; the status shows "Offline (coba lagi dalam Ns)" and retries with backoff. "Perlu login ulang" means the session expired - click the account button and log in again (your local data and sync position are kept).
- **Logout** stops syncing but never deletes local data. Open profiles with unsaved edits are never overwritten by a server update; a warning is shown in the status bar instead.
- **Server URL**: defaults to `https://kangpaket-api.quezacolt.my.id`. Override it in the login dialog under "Lanjutan", or by setting `"sync_server_url"` in `data/settings.json`.

## Data Storage

Profiles are saved to `data/profiles/<uuid>.json`.
Global settings are stored in `data/settings.json`.
Runner results are saved to `data/runner_results/`.
Cloud Sync session state is saved to `data/sync_state.json`.

## License

GNU General Public License v3.0
