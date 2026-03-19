# KangPaket

**Internal HTTP API Client Desktop App** — alternatif Postman yang ringan, offline, dan portable.

## Fitur

- Semua HTTP method: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS
- Tab request: Params, Headers, Body (raw/form-data/urlencoded), Auth (Bearer/Basic/API Key), Settings
- Response viewer: syntax highlight JSON, tab Headers, Cookies, Info
- Simpan & kelola profil request per collection
- Collection Runner: eksekusi sekuensial/paralel + assertions
- Import dari Postman Collection v2.0 & v2.1
- Export/import profil antar mesin
- Theme dark/light, font size configurable, proxy support

## Requirements

- Python 3.11+
- tkinter (bawaan Python, atau `brew install python-tk` di macOS)

## Instalasi & Menjalankan

```bash
# Clone / copy project
cd KangPaket

# Buat virtual environment
python3 -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate        # Windows

# Install dependencies
pip install -r requirements.txt

# Jalankan
python main.py
```

## Build Executable

```bash
# macOS
./build.sh macos       # → dist/KangPaket.app

# Linux
./build.sh linux       # → dist/KangPaket

# Windows (jalankan di mesin Windows)
build.sh windows       # → dist/KangPaket.exe
```

## Keyboard Shortcuts

| Shortcut | Aksi |
|---|---|
| `Ctrl+Enter` | Send request |
| `Ctrl+N` | New request |
| `Ctrl+S` | Save profile |
| `Ctrl+,` | Buka Settings |
| `Ctrl+E` | Export profiles |
| `Ctrl+L` | Clear response |

## Struktur Data

Profil disimpan di `data/profiles/<uuid>.json`.
Settings global di `data/settings.json`.
Hasil runner di `data/runner_results/`.

## Lisensi

Internal use only.
