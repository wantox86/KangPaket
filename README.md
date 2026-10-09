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

- **Login**: click the account button (top bar, shows "Belum login") or `Tools > Akun Cloud Sync…`, enter username and password. Registration is done by the server admin. After the first login your local and server data are merged (nothing is lost). The password is never stored; only a refresh token is kept in `data/sync_state.json` (owner-only permissions on macOS/Linux; on Windows file permissions are not restricted, so protect your user profile).
- **What is synced**: request profiles (including collection/folder), environments and global variables. Edits sync automatically a few seconds after you save; switching the active environment does not trigger a sync. Profiles above 256 KiB are skipped (and reported in the account dialog).
- **Auth fields are synced as-is**: bearer tokens, basic-auth passwords, API keys and secret variables are stored **in plaintext on the sync server** (not encrypted). Only use a server you trust, and avoid syncing real production secrets.
- **Offline behaviour**: if the server is unreachable the app keeps working locally; the status shows "Offline (coba lagi dalam Ns)" and retries with backoff. "Perlu login ulang" means the session expired - click the account button and log in again (your local data and sync position are kept).
- **Conflicts**: last write wins, compared by each item's edit time on the device's clock. Keep the system clock correct on every device: a device whose clock is far behind will see its edits overwritten by older edits from other devices.
- **Logout** (like Postman) first syncs your last changes, then removes all profiles, environments and Globals from this device and ends the session. Your data stays safe on the server; logging in again downloads it back. App settings (theme, Server URL, window size) are not touched. If the last sync fails (offline, error, items over 256 KiB) or the editor holds unsaved edits, you are asked to confirm: "Ada perubahan yang belum tersinkron dan akan hilang. Tetap logout dan hapus data lokal?" (Batal / Tetap logout). Cancelling leaves everything as it was and you stay logged in.
- **Session expired ("Perlu login ulang")** is not a logout: local data is kept, and logging in again with the same account simply continues (merge).
- **Switching accounts on the same device**: if you log in as a *different* user while this device still holds the previous account's data (for example after the session expired), you are asked "Data lokal milik akun <lama>. Login sebagai <baru> akan menghapus data lokal itu (belum tersinkron bisa hilang). Lanjut?". Lanjut clears the local data and then downloads the new account's data; Batal does not log in and nothing is uploaded or stored. Nothing of the previous account is ever uploaded to the new one. The first login on a device that has local data but was never logged in still merges that data into the account.
- **Server URL**: defaults to `https://kangpaket-api.quezacolt.my.id`. Override it in the login dialog under "Lanjutan", or by setting `"sync_server_url"` in `data/settings.json`.

## Data Storage

Profiles are saved to `data/profiles/<uuid>.json`.
Global settings are stored in `data/settings.json`.
Runner results are saved to `data/runner_results/`.
Cloud Sync session state is saved to `data/sync_state.json`.

## License

GNU General Public License v3.0
