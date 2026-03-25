# CLAUDE.md — KangPaket

> Internal HTTP API Client Desktop App
> Postman-equivalent, built with Python, lightweight, production-ready.
> **Versi saat ini: 1.0.1**

---

## 1. Project Overview

**KangPaket** adalah aplikasi desktop HTTP API client untuk kebutuhan internal kantor. Aplikasi ini merupakan alternatif Postman yang ringan, berjalan secara offline, mendukung semua HTTP method, dan menyimpan konfigurasi/profil secara lokal dalam format JSON.

### Stack
| Layer | Pilihan | Alasan |
|---|---|---|
| Language | Python 3.11+ | Standar tim, maintainable |
| GUI Framework | **CustomTkinter** | Ringan, modern UI, built on tkinter |
| HTTP Client | `httpx` | Async-ready, mendukung HTTP/1.1 & HTTP/2 |
| Data Persistence | JSON files (lokal) | Portabel, tanpa database eksternal |
| Packaging | `PyInstaller` | Build ke `.exe` / `.app` / binary Linux |

---

## 2. Struktur Direktori

```
kangpaket/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── pyproject.toml
├── main.py                        # Entry point
├── build.sh                       # Script build PyInstaller (Linux/macOS)
├── build.bat                      # Script build PyInstaller (Windows)
│
├── app/
│   ├── __init__.py
│   ├── config.py                  # App-wide config & constants
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── http_client.py         # HTTP request engine (httpx)
│   │   ├── profile_manager.py     # Save/load/export/import profil
│   │   ├── settings_manager.py    # Manage app settings (timeout, dll)
│   │   ├── runner_engine.py       # Collection runner: eksekusi sekuensial/paralel
│   │   └── postman_importer.py    # Parser Postman Collection v2.0 & v2.1 → RequestProfile
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── app_window.py          # Main window & layout root
│   │   ├── sidebar.py             # Panel kiri: daftar profil/request
│   │   ├── request_panel.py       # Panel tengah: form request
│   │   ├── response_panel.py      # Panel kanan/bawah: tampilan response
│   │   ├── settings_dialog.py     # Dialog pengaturan global
│   │   ├── profile_dialog.py      # Dialog save/rename/delete profil
│   │   ├── runner_window.py       # Window runner (top-level window terpisah)
│   │   ├── postman_import_dialog.py  # Dialog preview & konfirmasi import Postman
│   │   └── widgets/
│   │       ├── __init__.py
│   │       ├── key_value_editor.py  # Reusable tabel key-value (headers, params, dll)
│   │       ├── json_viewer.py       # Syntax-highlighted JSON viewer
│   │       ├── status_bar.py        # Status bar bawah
│   │       └── runner_result_row.py # Widget satu baris hasil runner
│   │
│   └── models/
│       ├── __init__.py
│       ├── request_model.py       # Dataclass: RequestProfile
│       ├── response_model.py      # Dataclass: ResponseResult
│       └── runner_model.py        # Dataclass: RunnerConfig, RunnerResult, RunItemResult
│
├── data/
│   ├── profiles/                  # Direktori penyimpanan profil JSON
│   │   └── .gitkeep
│   ├── runner_results/            # Direktori simpan hasil runner (JSON)
│   │   └── .gitkeep
│   └── settings.json              # File pengaturan global app
│
└── assets/
    ├── KangPaket-ico.png          # Icon fallback (macOS/Linux)
    └── KangPaket-ico.ico          # Icon Windows (titlebar & taskbar)
```

---

## 3. Models (Dataclass)

### `app/models/request_model.py`

```python
@dataclass
class RequestProfile:
    id: str                        # UUID
    name: str                      # Nama profil, contoh: "Login API"
    collection: str                # Nama koleksi/grup, default: "Default"
    method: str                    # GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS
    url: str
    headers: dict[str, str]        # Header kustom
    params: dict[str, str]         # Query params
    body_type: str                 # none | raw | form-data | x-www-form-urlencoded
    body_content: str              # Raw body (JSON/XML/text)
    body_form: dict[str, str]      # Form fields jika body_type = form-data
    auth_type: str                 # none | basic | bearer | api-key
    auth_data: dict[str, str]      # Kredensial auth sesuai auth_type
    timeout: float | None          # Override timeout (None = pakai default global)
    follow_redirects: bool
    verify_ssl: bool
    created_at: str                # ISO 8601
    updated_at: str                # ISO 8601
```

### `app/models/response_model.py`

```python
@dataclass
class ResponseResult:
    status_code: int
    status_text: str
    headers: dict[str, str]
    body: str                      # Raw response body
    elapsed_ms: float              # Waktu response dalam milidetik
    size_bytes: int                # Ukuran response body
    timestamp: str                 # Waktu request dikirim
    error: str | None              # Pesan error jika request gagal
```

### `app/models/runner_model.py`

```python
@dataclass
class RunnerConfig:
    id: str                          # UUID run session
    name: str                        # Label run, contoh: "Smoke Test Login Flow"
    profile_ids: list[str]           # Daftar ID profil yang dijalankan, urut
    iteration_count: int             # Jumlah iterasi per profil (default: 1)
    delay_between_ms: int            # Jeda antar request dalam milidetik (default: 0)
    stop_on_failure: bool            # Hentikan run jika ada request yang gagal
    run_mode: str                    # "sequential" | "parallel" (paralel hanya antar profil berbeda)
    created_at: str                  # ISO 8601

@dataclass
class RunItemResult:
    profile_id: str
    profile_name: str
    iteration: int                   # Iterasi ke-N (1-based)
    status: str                      # "success" | "failed" | "error" | "skipped"
    status_code: int | None
    elapsed_ms: float | None
    size_bytes: int | None
    error: str | None                # Pesan error jika status = "error"
    assertion_results: list[dict]    # Hasil assertions: [{name, passed, expected, actual}]
    timestamp: str

@dataclass
class RunnerResult:
    config: RunnerConfig
    items: list[RunItemResult]
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    total_elapsed_ms: float
    finished_at: str
```

---

## 4. Core Modules

### 4.1 `app/core/http_client.py`

**Tugas:** Eksekusi HTTP request berdasarkan `RequestProfile`, kembalikan `ResponseResult`.

**Implementasi wajib:**
- Gunakan `httpx.Client` (synchronous) — bukan async, agar lebih mudah diintegrasikan dengan tkinter.
- Dukung semua method: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`.
- Dukung body type:
  - `none` → tidak ada body
  - `raw` → kirim `body_content` sebagai string, Content-Type dari header
  - `form-data` → `httpx` multipart/form-data
  - `x-www-form-urlencoded` → `data=` dict
- Dukung auth type:
  - `none` → tidak ada auth
  - `bearer` → header `Authorization: Bearer <token>`
  - `basic` → `httpx.BasicAuth(username, password)`
  - `api-key` → header kustom `X-API-Key: <key>` atau sesuai config
- Tangkap semua exception (`httpx.ConnectError`, `httpx.TimeoutException`, dll) dan masukkan ke `ResponseResult.error`.
- Hitung `elapsed_ms` dari `response.elapsed.total_seconds() * 1000`.
- Hitung `size_bytes` dari `len(response.content)`.

### 4.2 `app/core/profile_manager.py`

**Tugas:** CRUD profil request, simpan ke disk, export/import JSON.

**Fungsi wajib:**

```python
def load_all_profiles() -> list[RequestProfile]
def save_profile(profile: RequestProfile) -> None
def delete_profile(profile_id: str) -> None
def delete_collection(collection_name: str) -> list[str]
    # Hapus semua profil dalam satu collection. Return list ID yang dihapus.
def get_profile(profile_id: str) -> RequestProfile | None
def duplicate_profile(profile: RequestProfile) -> RequestProfile
    # UUID baru, nama + " (copy)"
def get_collections() -> list[str]
    # Sorted unique collection names
def get_profiles_by_collection() -> dict[str, list[RequestProfile]]
    # Profil dikelompokkan & di-sort per collection
def export_profiles(profiles: list[RequestProfile], path: str) -> None
def import_profiles(path: str) -> list[RequestProfile]
    # Import: jika ID konflik, generate UUID baru.
    # Jika nama konflik, tambahkan suffix " (imported)".
```

**Format file penyimpanan:**
- Satu file per profil: `data/profiles/<uuid>.json`
- Format export: satu file JSON berisi array of profiles

```json
{
  "version": "1.0",
  "app": "KangPaket",
  "exported_at": "2025-01-01T00:00:00",
  "profiles": [ ... ]
}
```

### 4.3 `app/core/settings_manager.py`

**Tugas:** Baca/tulis file `data/settings.json`.

**Struktur settings default:**

```json
{
  "default_timeout": 30.0,
  "follow_redirects": true,
  "verify_ssl": true,
  "max_response_size_mb": 10,
  "theme": "dark",
  "font_size": 13,
  "default_collection": "Default",
  "proxy_enabled": false,
  "proxy_http": "",
  "proxy_https": ""
}
```

**Fungsi wajib:**

```python
def load_settings() -> dict
def save_settings(settings: dict) -> None
def get(key: str, default=None)
def set(key: str, value) -> None   # auto-save setelah set
def reset_to_defaults() -> None
@property
def all() -> dict                  # copy dari seluruh settings
```

### 4.4 `app/core/runner_engine.py`

**Tugas:** Eksekusi sekumpulan `RequestProfile` secara sekuensial atau paralel, evaluasi assertions, dan emit progress via callback.

**Interface utama:**

```python
class RunnerEngine:
    def __init__(self, http_client: HttpClient, settings: SettingsManager):
        ...

    def run(
        self,
        config: RunnerConfig,
        profiles: list[RequestProfile],
        on_item_done: Callable[[RunItemResult], None],   # callback per item selesai
        on_progress: Callable[[int, int], None],         # callback (done, total)
        on_finished: Callable[[RunnerResult], None],     # callback saat semua selesai
        csv_data: list[dict] | None = None,              # data CSV untuk variable substitution
    ) -> None:
        # Dijalankan di thread terpisah (threading.Thread)
        # Jangan block main thread tkinter
        ...

    def stop(self) -> None:
        # Set flag stop, request yang sedang berjalan dibiarkan selesai
        # Request berikutnya di-skip dengan status "skipped"
        ...
```

**Logika eksekusi:**

1. **Sequential mode:**
   - Iterasi profil satu per satu sesuai urutan `config.profile_ids`
   - Setiap profil dieksekusi sebanyak `iteration_count` kali
   - Jika `delay_between_ms > 0`, sleep antar request
   - Jika `stop_on_failure = True` dan item gagal → mark sisa item sebagai "skipped" → selesai

2. **Parallel mode:**
   - Gunakan `concurrent.futures.ThreadPoolExecutor` dengan max workers = min(len(profiles), 5)
   - Setiap profil dieksekusi di thread sendiri
   - Iterasi tetap sekuensial per profil
   - Hasil di-collect secara thread-safe (gunakan `threading.Lock`)
   - `stop_on_failure` berlaku: jika satu thread gagal, thread lain boleh selesai dulu baru stop

3. **Assertions:** Evaluasi setelah setiap response diterima:
   - `status_code_equals(expected: int)`
   - `status_code_in(expected: list[int])`
   - `response_time_less_than(ms: int)`
   - `body_contains(substring: str)`
   - `body_json_path_equals(path: str, expected_value)` — pakai library `jsonpath-ng`
   - `header_exists(header_name: str)`
   - `header_equals(header_name: str, expected_value: str)`
   - Jika assertion gagal → `RunItemResult.status = "failed"`, lanjut atau stop sesuai `stop_on_failure`

4. **Variable substitution via CSV:**
   - `csv_data` adalah list of dict (hasil `csv.DictReader`)
   - Placeholder `{{ColumnName}}` dalam url, headers, params, body_content, body_form, auth_data → diganti nilai dari row CSV per iterasi
   - Jika `csv_data` diberikan, `iteration_count` diabaikan — jumlah iterasi = jumlah baris CSV
   - Placeholder tidak dikenal → dibiarkan as-is

5. **Callback thread-safety:**
   - Semua callback (`on_item_done`, `on_progress`, `on_finished`) harus dipanggil via `root.after(0, callback)` agar aman untuk update UI tkinter dari thread background.

---

## 5. Postman Import

### 5.1 `app/core/postman_importer.py`

**Tugas:** Parse file Postman Collection (`.json`) format v2.0 dan v2.1, konversi setiap item request menjadi `RequestProfile`, kembalikan hasil parse lengkap dengan warning jika ada field yang tidak bisa dikonversi.

#### Format Postman yang Didukung

| Format | `info.schema` | Keterangan |
|---|---|---|
| Collection v2.0 | `...schema/collection/v2.0.0/...` | Legacy, masih banyak dipakai |
| Collection v2.1 | `...schema/collection/v2.1.0/...` | Format terbaru Postman |

File lain (OpenAPI, Swagger, Insomnia) **tidak** didukung di V1 — tolak dengan pesan jelas.

#### Dataclass Hasil Parse

```python
@dataclass
class PostmanImportResult:
    collection_name: str              # Nama collection dari info.name
    total_items: int                  # Total request ditemukan (termasuk di subfolder)
    profiles: list[RequestProfile]    # Hasil konversi siap simpan
    warnings: list[str]               # Peringatan per item yang tidak bisa dikonversi sempurna
    skipped: list[str]                # Nama item yang diskip (tidak bisa dikonversi sama sekali)
```

#### Interface Utama

```python
def parse_postman_file(path: str) -> PostmanImportResult:
    """
    Baca file JSON Postman, validasi format, rekursif parse semua item.
    Raise PostmanImportError jika file bukan Postman Collection yang valid.
    """

class PostmanImportError(Exception):
    """Dilempar jika file bukan Postman Collection atau versi tidak didukung."""
```

#### Logika Mapping Field

**Collection Name → `RequestProfile.collection`**
- Ambil dari `info.name`
- Semua request dalam satu file masuk ke collection dengan nama yang sama

**Folder Nested → Flatten ke Sub-collection**
- Postman mendukung nested folder. KangPaket V1 hanya support 1 level collection.
- Flatten: `FolderA/FolderB/Request` → `collection = "CollectionName / FolderA / FolderB"`
- Kedalaman folder > 3 level → tetap flatten, tambahkan warning

**Request Name → `RequestProfile.name`**
- Ambil dari `item.name`; jika kosong → gunakan URL sebagai nama + warning

**Method → `RequestProfile.method`**
- `item.request.method` (uppercase); jika tidak dikenal → default `GET` + warning

**URL → `RequestProfile.url`**
- v2.1: `item.request.url.raw`
- v2.0: `item.request.url` bisa string atau object
- URL dengan Postman variable `{{variableName}}` → biarkan as-is + warning

**Query Params → `RequestProfile.params`**
- v2.1: `item.request.url.query[]` → `{key, value, disabled}`
- Hanya ambil `disabled != true`
- Jika query embedded di `url.raw` tapi tidak ada `url.query` → parse dari URL string

**Headers → `RequestProfile.headers`**
- `item.request.header[]` → `{key, value, disabled}`
- Hanya ambil `disabled != true`
- Header bernilai `{{variable}}` → ikutkan dengan warning

**Body → `RequestProfile.body_type` + `body_content` / `body_form`**

| Postman `body.mode` | KangPaket `body_type` | Mapping |
|---|---|---|
| `raw` | `raw` | `body.raw` → `body_content`; `body.options.raw.language` → tentukan Content-Type |
| `urlencoded` | `x-www-form-urlencoded` | `body.urlencoded[]` → `body_form` (skip disabled) |
| `formdata` | `form-data` | `body.formdata[]` → `body_form` (skip disabled; skip `type=file` + warning) |
| `none` / tidak ada | `none` | — |
| `graphql` | `raw` | Serialize `{query, variables}` ke JSON string + warning |
| `file` | `none` | Skip + warning "file upload tidak didukung" |

**Auth → `RequestProfile.auth_type` + `auth_data`**

Prioritaskan auth di level request; fallback ke level collection.

| Postman `auth.type` | KangPaket `auth_type` | Mapping |
|---|---|---|
| `noauth` / tidak ada | `none` | — |
| `bearer` | `bearer` | `auth.bearer[key=token].value` → `auth_data.token` |
| `basic` | `basic` | `auth.basic[key=username/password]` → `auth_data` |
| `apikey` | `api-key` | `auth.apikey[key=key/value/in]` → `auth_data` |
| `oauth2`, `oauth1`, `aws`, `digest`, dll | `none` | Skip + warning per request |

**Pre-request Script & Tests → Abaikan**
- `event[]` tidak dikonversi
- Tambahkan satu warning global jika collection mengandung scripts

**Collection Variables → Abaikan**
- `variable[]` di level collection tidak dikonversi
- Tambahkan warning global jika ada

#### Contoh Mapping (v2.1)

```json
// Input Postman item:
{
  "name": "Login",
  "request": {
    "method": "POST",
    "url": { "raw": "https://api.example.com/auth/login", "query": [] },
    "header": [{ "key": "Content-Type", "value": "application/json" }],
    "auth": { "type": "noauth" },
    "body": {
      "mode": "raw",
      "raw": "{\"username\": \"admin\", \"password\": \"secret\"}",
      "options": { "raw": { "language": "json" } }
    }
  }
}

// Output RequestProfile:
RequestProfile(
    name="Login",
    collection="My API Collection",
    method="POST",
    url="https://api.example.com/auth/login",
    headers={"Content-Type": "application/json"},
    params={},
    body_type="raw",
    body_content='{"username": "admin", "password": "secret"}',
    auth_type="none",
    ...
)
```

### 5.2 `app/ui/postman_import_dialog.py` — Dialog Preview Import

Dialog modal (`CTkToplevel`) yang muncul setelah user memilih file Postman `.json`. Menampilkan preview hasil parse sebelum user konfirmasi import.

**Layout:**

```
┌─────────────────────────────────────────────────────────┐
│  Import dari Postman Collection                         │
├─────────────────────────────────────────────────────────┤
│  File   : my-api.postman_collection.json                │
│  Format : Postman Collection v2.1  ✅                   │
│  Collection : "My API Collection"                       │
│  Request ditemukan: 24                                  │
│  Import ke collection: [My API Collection           ▾]  │
│  (bisa diganti atau digabung ke collection existing)    │
├─────────────────────────────────────────────────────────┤
│  PREVIEW REQUEST (scrollable)                           │
│  [✓] POST  Login                                        │
│  [✓] GET   Get User Profile                             │
│  [✓] PUT   Update User                                  │
│  [⚠] GET   Get Orders    ← URL mengandung {{baseUrl}}  │
│  [⚠] POST  Upload File   ← file upload body diabaikan  │
│  [ ] (skip) Raw GraphQL  ← tidak dapat dikonversi      │
│  [Select All] [Deselect All]                            │
├─────────────────────────────────────────────────────────┤
│  ▼ WARNINGS (3)                                         │
│   • 3 request mengandung Postman variables ({{...}})   │
│   • Pre-request scripts diabaikan (2 item)             │
│   • 1 file upload body dikonversi ke body=none         │
├─────────────────────────────────────────────────────────┤
│              [Batal]          [Import 22 Request]       │
└─────────────────────────────────────────────────────────┘
```

**Perilaku:**
- Checkbox per item → user bisa uncheck item tertentu agar tidak diimport
- Item status ❌ (skipped/tidak bisa dikonversi) → tidak bisa di-check, ditampilkan abu-abu
- Dropdown collection target: pilih collection existing atau ketik nama baru
- Tombol "Import N Request" disabled jika 0 item di-check; label update dinamis sesuai jumlah checked
- Warnings section collapsible (klik untuk expand/collapse)
- Setelah import sukses → tutup dialog, sidebar di-refresh, tampilkan toast notification: "✅ 22 request berhasil diimport ke 'My API Collection'"

---

## 6. UI Modules

### 6.1 `app/ui/app_window.py` — Main Window

**Layout:**
- Title bar: `KangPaket`
- Menu bar: `File | Tools | Help`
- Layout utama: 3-panel horizontal
  - **Kiri (220px fixed):** Sidebar profil
  - **Tengah/Atas (flex):** Request panel
  - **Bawah:** Response panel (vertical PanedWindow, resizable)
- Status bar di paling bawah (26px)

**Window Icon:**
- Windows: `assets/KangPaket-ico.ico` via `iconbitmap()` (titlebar & taskbar)
- macOS/Linux: `assets/KangPaket-ico.png` via `PIL + iconphoto()`
- Graceful fallback jika file tidak ditemukan

**Menu `File`:**
- New Request (Ctrl+N) → buat request kosong baru
- Save Profile (Ctrl+S) → simpan request aktif sebagai profil
- Export Profiles (Ctrl+E) → ekspor semua profil ke JSON
- Import Profiles → impor dari file JSON (format KangPaket)
- **Import from Postman** → buka file dialog pilih `.json` → buka `PostmanImportDialog`
- Settings (Ctrl+,) → buka `SettingsDialog`
- Exit

**Menu `Tools`:**
- Collection Runner → buka `runner_window.py`
- Clear Response (Ctrl+L)
- Copy Response Body
- Copy as cURL

**Menu `Help`:**
- About KangPaket

**Keyboard Shortcuts:**
- `Ctrl+N` → New Request
- `Ctrl+S` → Save Profile
- `Ctrl+Enter` → Send Request
- `Ctrl+,` → Settings
- `Ctrl+E` → Export Profiles
- `Ctrl+L` → Clear Response

**Callbacks ke Sidebar:**
- `on_delete(profile_id)` → hapus profil dari request panel jika aktif
- `on_delete_collection(deleted_ids)` → sama, untuk bulk delete collection

### 6.2 `app/ui/sidebar.py` — Panel Kiri

**Fitur:**
- Search bar (filter real-time by nama/URL/method)
- Daftar profil dikelompokkan per collection (expandable/collapsible)
- Klik profil → muat ke request panel
- Tombol `+` di header untuk new request

**Collection header row (per collection):**
- Tombol label collection (klik → toggle collapse/expand)
- Tombol `▶` (hijau) → Run Collection (buka RunnerWindow dengan collection pre-selected)
- Tombol `×` (merah) → Delete Collection (konfirmasi, hapus semua profil)
- Klik kanan pada header → context menu: `Run '<nama>'`, `Delete Collection (N requests)`

**Profile rows:**
- Method badge (warna sesuai METHOD_COLORS, 3 huruf)
- Nama profil (klik untuk load)
- Klik kanan → context menu: `Open`, `Rename…`, `Duplicate`, `Move to Collection…`, `Delete`

**Callbacks:**
- `on_select(profile)` → load ke request panel
- `on_new_request()` → buat request baru
- `on_run_collection(name)` → buka runner
- `on_delete(profile_id)` → notifikasi profile dihapus
- `on_delete_collection(deleted_ids)` → notifikasi collection dihapus (list ID)

### 6.3 `app/ui/request_panel.py` — Panel Request

**Komponen (dari atas ke bawah):**

1. **URL Bar Row:**
   - Dropdown method (GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS) — warna berbeda per method
   - Entry URL (monospace font, lebar penuh)
   - Tombol **SEND** (biru prominent)
   - Tombol **Save** — menampilkan `"Save •"` jika ada perubahan belum disimpan (dirty flag)
   - Tombol **Delete** (merah, disabled saat profil belum tersimpan ke disk; aktif setelah Save)

2. **Tab request:** `Params | Headers | Body | Auth | Settings`

   **Tab Params:**
   - `KeyValueEditor` widget (tabel: enabled checkbox | key | value | delete)
   - Params di-append ke URL sebagai query string

   **Tab Headers:**
   - `KeyValueEditor` widget
   - Quick-add buttons: `Content-Type: JSON`, `Content-Type: XML`, `Accept: JSON`, `Accept: Any`

   **Tab Body:**
   - Radio: `None | Raw | Form Data | x-www-form-urlencoded`
   - Jika Raw: dropdown Content-Type (JSON, XML, Text, HTML, JS) + tombol **Format JSON** + TextArea multi-line
   - Jika Form Data/URL-encoded: `KeyValueEditor`

   **Tab Auth:**
   - Dropdown: `none | bearer | basic | api-key`
   - Form dinamis sesuai pilihan:
     - Bearer: input token
     - Basic: input username + password (password masked)
     - API Key: input key name + value + lokasi radio (`header` / `query param`)

   **Tab Settings (per-request override):**
   - Timeout (override global, kosong = pakai global)
   - Follow Redirects (checkbox)
   - Verify SSL (checkbox)

**Method API:**
- `load_profile(profile, is_saved=False)` → populate semua field; `is_saved=True` mengaktifkan tombol Delete
- `get_current_profile()` → build `RequestProfile` dari state UI saat ini
- `clear_profile()` → reset `_current_profile_id` dan disable tombol Delete
- `apply_settings()` → update font size dari settings

**Callbacks:**
- `on_response(ResponseResult)` → kirim ke response panel
- `on_status(str)` → update status bar
- `on_save(profile)` → buka ProfileDialog
- `on_delete(profile_id)` → hapus profil dari disk, refresh sidebar

### 6.4 `app/ui/response_panel.py` — Panel Response

**Bagian atas (status bar response):**
- Status code + text (warna: hijau 2xx, kuning 3xx, merah 4xx/5xx)
- Waktu (ms)
- Ukuran (bytes/KB/MB)

**Tab response:** `Body | Headers | Cookies | Info`

**Status bar response (atas tab):**
- Status code + text (warna: hijau 2xx, kuning 3xx, merah 4xx/5xx)
- Elapsed time (ms)
- Size (bytes/KB/MB)
- Tombol Copy (body ke clipboard)
- Tombol Save to File (auto-detect extension dari Content-Type)

**Tab Body:**
- Auto-detect Content-Type → format display:
  - `application/json` atau body dimulai dengan `{`/`[` → JSON viewer syntax-highlighted + pretty print
  - `image/*` → label "[Image response — use Save to File]"
  - Lainnya → raw text
- Toggle: Pretty | Raw
- Warning banner jika ukuran body melebihi `max_response_size_mb` (truncated)

**Tab Headers:**
- Tabel read-only: Header Name | Value
- Tombol Copy All Headers

**Tab Cookies:**
- Parse `Set-Cookie` headers → tabel: Name | Value | Domain | Path | Expires
- Label "No cookies" jika kosong

**Tab Info:**
- Timestamp request
- Status code + text
- Elapsed time
- Size
- Error message (jika ada)

### 6.5 `app/ui/widgets/key_value_editor.py`

Widget reusable tabel key-value. Parameter constructor:

```python
KeyValueEditor(parent, columns=["Key", "Value"], allow_toggle=True)
```

- Setiap baris: checkbox enable/disable | key entry | value entry | tombol delete (×)
- Tombol Add Row di bawah
- Method: `get_data() -> dict[str, str]` (hanya baris yang enabled)
- Method: `set_data(data: dict)` → populate tabel

### 6.6 `app/ui/widgets/json_viewer.py`

- Gunakan `tkinter.Text` dengan tag-based syntax highlighting
- Warna: string (hijau), number (oranye), boolean/null (ungu), key (biru/cyan)
- Support scroll panjang untuk response besar
- Truncate otomatis jika > `max_response_size_mb` setting, tampilkan peringatan

### 6.7 `app/ui/settings_dialog.py`

Dialog modal dengan form:
- Default Timeout (detik)
- Max Response Size (MB)
- Follow Redirects (checkbox)
- Verify SSL (checkbox)
- Theme (Dark/Light)
- Font Size
- Proxy Settings (checkbox enable + HTTP/HTTPS proxy URL)
- Default Collection Name
- Tombol Save, Cancel, Reset to Default

### 6.8 `app/ui/runner_window.py` — Runner Window

Window top-level terpisah (`CTkToplevel`) yang bisa dibuka dari menu `Tools → Collection Runner` atau klik kanan collection di sidebar → "Run Collection".

**Layout (3 bagian vertikal):**

```
┌─────────────────────────────────────────────────────┐
│  RUNNER CONFIGURATION                               │
│  ┌──────────────────────────────────────────────┐  │
│  │ Run Name: [________________]                 │  │
│  │ Collection: [Dropdown ▾]                     │  │
│  │ Requests:  [Ordered checklist of profiles]   │  │
│  │            [↑ ↓ untuk reorder]               │  │
│  │ Iterations: [1    ] Delay (ms): [0    ]      │  │
│  │ Mode: (●) Sequential  ( ) Parallel           │  │
│  │ Stop on failure: [✓]                         │  │
│  └──────────────────────────────────────────────┘  │
│  [▶ RUN]  [■ STOP]  [Export Results]               │
├─────────────────────────────────────────────────────┤
│  PROGRESS                                           │
│  Progress bar: ████████░░░░░░ 8/15                  │
│  Summary: ✅ 6 passed  ❌ 2 failed  ⚠ 0 error      │
├─────────────────────────────────────────────────────┤
│  RESULTS (scrollable list)                          │
│  ┌──────────────────────────────────────────────┐  │
│  │ RunnerResultRow × N                          │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**Bagian Configuration:**
- **Run Name:** text input, default otomatis: `"Run - <collection> - <timestamp>"`
- **Collection dropdown:** pilih collection → auto-populate checklist profil di bawahnya + tombol refresh
- **Data File (CSV):** Browse + Clear buttons; jika dipilih, `{{ColumnName}}` di URL/headers/body/auth diganti nilai per baris CSV; jumlah iterasi = jumlah baris CSV (override Iterations)
  - Info label menampilkan: jumlah baris, nama kolom yang terdeteksi
- **Ordered checklist profil:**
  - Setiap item: checkbox (include/exclude) | method badge | nama profil | URL (truncated)
  - Tombol "Select All" / "Deselect All"
- **Iterations:** spinbox integer (min 1, max 100) — diabaikan jika CSV dipakai
- **Delay (ms):** spinbox integer (min 0, max 60000)
- **Mode:** radio button Sequential / Parallel
- **Stop on failure:** checkbox

**Bagian Progress (muncul saat run berjalan):**
- `CTkProgressBar` dengan nilai 0.0 → 1.0
- Label teks: `8 / 15 requests`
- Summary chips: `✅ Passed: 6 | ❌ Failed: 2 | ⚠ Error: 0 | ⏭ Skipped: 0`
- Elapsed time counter (update setiap 1 detik selama run)

**Tombol aksi:**
- `▶ RUN` — mulai runner, disable tombol Run, enable Stop
- `■ STOP` — kirim sinyal stop ke engine, disabled saat idle
- `Export Results` — aktif setelah run selesai, export ke JSON/CSV

**Bagian Results:**
- Scrollable frame berisi `RunnerResultRow` widgets
- Rows ditambahkan secara live saat setiap request selesai (via callback `on_item_done`)
- Warna background row sesuai status: hijau (success), merah (failed), kuning (error), abu (skipped)
- Klik pada row → expand untuk lihat detail response body & assertions

### 6.9 `app/ui/widgets/runner_result_row.py`

Widget satu baris hasil eksekusi runner. Dua state: **collapsed** (default) dan **expanded**.

**Collapsed state:**
```
[✅] #3  POST  Login API              200 OK    142ms   1.2KB
[❌] #4  GET   Get User Profile       404       89ms    0.3KB   [assertion: status_code_equals(200) FAILED]
```
Kolom: status icon | nomor urut | method badge | nama profil | status code | elapsed | size | pesan singkat

**Expanded state (klik untuk toggle):**
- Response body (JSON viewer, max 50 baris, scroll)
- Tabel assertions:
  ```
  Assertion                          Expected    Actual    Result
  status_code_equals                 200         404       ❌ FAILED
  response_time_less_than (ms)       500         89        ✅ PASSED
  body_contains ("token")            -           -         ✅ PASSED
  ```
- Tombol "Open in Main Window" → load profil ini ke request panel utama

---

## 7. `requirements.txt`

```
customtkinter>=5.2.0
httpx>=0.27.0
Pillow>=10.0.0
jsonpath-ng>=1.6.0
pyinstaller>=6.0.0
```

---

## 8. `main.py`

```python
"""
KangPaket — Entry point
"""
import sys
from app.ui.app_window import AppWindow
from app.core.settings_manager import SettingsManager

def main():
    settings = SettingsManager()
    app = AppWindow(settings)
    app.run()

if __name__ == "__main__":
    main()
```

---

## 9. Sprint Plan

> **Status: Semua sprint selesai (v1.0.1)**

### Sprint 1 — Foundation & Core Engine ✅
**Goal:** Aplikasi bisa kirim request dan tampilkan response.

- [x] Setup project structure & `requirements.txt`
- [x] Implement `RequestProfile` dan `ResponseResult` dataclass
- [x] Implement `http_client.py` (semua method, auth, body types, error handling)
- [x] Implement `settings_manager.py` dengan defaults
- [x] Main window layout (3-panel skeleton dengan CustomTkinter)
- [x] URL bar + method dropdown + SEND button
- [x] Response panel: Body (raw text) + status code display

### Sprint 2 — Request Builder Lengkap ✅
**Goal:** Tab Params, Headers, Body, Auth semua fungsional.

- [x] Implement `KeyValueEditor` widget
- [x] Tab Params → auto-append ke URL sebagai query string
- [x] Tab Headers → merge dengan default headers + quick-add preset buttons
- [x] Tab Body → semua mode (none/raw/form/urlencoded) + tombol Format JSON
- [x] Tab Auth → bearer, basic, api-key (header/query param)
- [x] Tab Settings (per-request override timeout/ssl/redirect)

### Sprint 3 — Response Panel & JSON Viewer ✅
**Goal:** Response ditampilkan dengan baik, syntax-highlighted.

- [x] Implement `json_viewer.py` dengan syntax highlighting (7 token types)
- [x] Auto-detect Content-Type response → pilih renderer
- [x] Tab Body: toggle Pretty/Raw, tombol Copy, Save to File
- [x] Tab Headers response (tabel read-only + Copy All)
- [x] Tab Cookies (parse Set-Cookie headers)
- [x] Tab Info (timestamp, status, elapsed, size, error)
- [x] Status bar response (status code berwarna, elapsed, size)
- [x] Truncation warning banner untuk response besar

### Sprint 4 — Profile Manager & Sidebar ✅
**Goal:** Simpan, muat, kelola request profiles.

- [x] Implement `profile_manager.py` (CRUD ke disk, duplicate, delete collection)
- [x] Sidebar: daftar profil grouped by collection (collapsible)
- [x] Search/filter profil real-time (by nama/URL/method)
- [x] Klik profil → load ke request panel
- [x] Context menu profil: Open, Rename, Duplicate, Move to Collection, Delete
- [x] Context menu collection header: Run, Delete Collection
- [x] Tombol × pada collection header → delete collection (bulk)
- [x] Tombol ▶ pada collection header → run collection
- [x] Tombol + new request di header
- [x] Save Profile dialog (`profile_dialog.py`): input nama, pilih collection existing atau baru
- [x] "Unsaved changes" dirty flag di tombol Save (teks "Save •")
- [x] Tombol Delete di URL bar (merah, aktif hanya untuk profil tersimpan)

### Sprint 5 — Export/Import & Settings Dialog ✅
**Goal:** Portabilitas profil dan konfigurasi global.

- [x] Export profil ke JSON dengan metadata (version, exported_at)
- [x] Import profil dari JSON (handle ID conflict, nama conflict)
- [x] `settings_dialog.py` lengkap (semua field + Reset to Defaults)
- [x] Apply settings ke http_client (timeout, ssl, redirect, proxy)
- [x] Theme switching (dark/light/system) via CustomTkinter
- [x] Font size setting diterapkan ke URL entry dan body textarea

### Sprint 6 — Polish, Menu & Utilities ✅
**Goal:** App siap pakai untuk tim internal.

- [x] Menu bar lengkap (File/Tools/Help)
- [x] "Copy as cURL" feature (builder dari RequestProfile)
- [x] Status bar bawah (last request method, status, elapsed, size)
- [x] Keyboard shortcuts: Ctrl+Enter, Ctrl+S, Ctrl+N, Ctrl+,, Ctrl+E, Ctrl+L
- [x] Error dialog dengan contextual tips (timeout, SSL, connection, invalid URL)
- [x] About dialog (versi, Python, platform, libraries)
- [x] Window icon platform-specific (KangPaket-ico.ico / .png)
- [x] `build.sh` + `build.bat` script PyInstaller

### Sprint 7 — Collection Runner ✅
**Goal:** Fitur runner berjalan end-to-end: eksekusi multi-request, live progress, assertions, export hasil.

- [x] Implement `RunnerConfig`, `RunItemResult`, `RunnerResult` dataclass
- [x] Implement `runner_engine.py` (sequential + parallel, 7 assertions, CSV substitution, thread-safe callbacks)
- [x] Implement `runner_result_row.py` widget (collapsed + expanded dengan assertions table)
- [x] Implement `runner_window.py` (config panel, CSV data file, progress, live results, export JSON/CSV)
- [x] Integrasi ke menu Tools → Collection Runner + sidebar ▶ button
- [x] Tombol "Open in Main Window" dari expanded row

### Sprint 8 — Postman Collection Importer ✅
**Goal:** User bisa import file `.postman_collection.json` (v2.0 & v2.1) langsung menjadi profil KangPaket.

- [x] Implement `PostmanImportResult` dataclass di `postman_importer.py`
- [x] Implement `postman_importer.py` (v2.0 & v2.1, nested folder flatten, semua body/auth mode, warnings)
- [x] Implement `postman_import_dialog.py` (checklist, target collection, collapsible warnings, dynamic button label)
- [x] Integrasi ke menu File → Import from Postman (file dialog, error dialog, sidebar refresh)

---

## 10. Coding Standards & Conventions

### Umum
- Python 3.11+ dengan type hints di semua fungsi dan method
- Gunakan `dataclass` untuk models, bukan plain dict
- Tidak boleh ada hardcoded string UI — gunakan konstanta di `app/config.py`
- Semua operasi file harus ada error handling (`try/except`) dengan pesan user-friendly

### UI/UX
- CustomTkinter theme: **dark** sebagai default
- Warna method HTTP:
  - GET → `#61affe` (biru)
  - POST → `#49cc90` (hijau)
  - PUT → `#fca130` (oranye)
  - PATCH → `#50e3c2` (teal)
  - DELETE → `#f93e3e` (merah)
  - HEAD → `#9012fe` (ungu)
  - OPTIONS → `#0d5aa7` (biru tua)
- Warna status code:
  - 2xx → `#49cc90` (hijau)
  - 3xx → `#fca130` (kuning/oranye)
  - 4xx → `#f93e3e` (merah)
  - 5xx → `#f93e3e` (merah tua)
- Gunakan monospace font (`Courier New` atau `JetBrains Mono` jika tersedia) untuk area URL, body, dan response viewer
- Semua dialog harus modal (grab_set)

### HTTP Client
- Default timeout: 30 detik
- Timeout 0 berarti tidak ada timeout
- Selalu include `User-Agent: KangPaket/1.0` di setiap request
- Jangan cache response apapun

### File & Data
- UUID v4 untuk semua profile ID
- ISO 8601 untuk semua timestamp (`datetime.utcnow().isoformat() + "Z"`)
- JSON disimpan dengan `indent=2` untuk readability
- Direktori `data/profiles/` dibuat otomatis jika belum ada

---

## 11. Error Handling Priorities

| Kondisi | Behavior |
|---|---|
| URL kosong saat Send | Tampilkan pesan inline di URL bar, jangan kirim |
| URL invalid format | Warning dialog sebelum send |
| Connection timeout | Tampilkan di response panel tab Info + status "TIMEOUT" |
| Connection refused | Tampilkan error detail di response panel |
| SSL error | Tampilkan error + saran "Nonaktifkan Verify SSL di tab Settings" |
| Response > max size | Truncate + warning banner di response body |
| Profile file corrupt | Skip file tersebut, log warning, lanjutkan load profil lain |
| Import JSON invalid | Dialog error dengan detail parse error |
| Disk full saat save | Dialog error, jangan crash |
| Runner: 0 profil dipilih | Disable tombol RUN, tampilkan hint "Pilih minimal 1 request" |
| Runner: profil dihapus saat runner open | Skip profil tersebut saat run, tampilkan warning di hasil |
| Runner: thread timeout | Tandai item sebagai "error" dengan pesan timeout, lanjut ke berikutnya |
| Runner: stop ditrigger | Request aktif selesai dulu, sisanya jadi "skipped" |
| Runner: export gagal (disk full) | Dialog error, hasil tetap tampil di UI |
| Postman import: file bukan JSON valid | Dialog error: "File tidak dapat dibaca sebagai JSON" |
| Postman import: bukan format Postman Collection | Dialog error: "Format tidak dikenali. Hanya Postman Collection v2.0/v2.1 yang didukung" |
| Postman import: collection kosong (0 request) | Dialog error: "Collection tidak memiliki request yang dapat diimport" |
| Postman import: semua item di-skip | Import berjalan, notifikasi: "0 request diimport — semua item tidak dapat dikonversi" |
| Postman import: file sangat besar (>10MB) | Warning dialog sebelum parse: "File besar, proses mungkin membutuhkan waktu" |

---

## 12. Out of Scope (V1)

Fitur berikut **tidak** diimplementasikan di V1:
- WebSocket / GraphQL / gRPC support
- Global environment variables (substitusi `{{var}}` di luar konteks CSV runner)
- Request chaining dengan data passing antar request (response body request A → body request B)
- Team sync / cloud storage
- History log request otomatis
- Pre-request / post-request scripts
- Mock server
- Runner: scheduling / cron otomatis
- Postman import: OpenAPI / Swagger / Insomnia format
- Postman import: environment variables substitution otomatis
- Postman import: OAuth2 / AWS Signature auth conversion

> **Catatan:** Variable substitution `{{ColumnName}}` **sudah diimplementasikan** di Collection Runner via CSV Data File (per-iterasi, per-baris CSV). Ini berbeda dari "global environment variables" yang belum ada.

---

## 13. Build & Distribution

```bash
# Install dependencies
pip install -r requirements.txt

# Run development
python main.py

# Build executable (Windows) — via script
build.bat
# atau manual:
pyinstaller --onefile --windowed --icon=assets/KangPaket-ico.ico --name=KangPaket main.py

# Build executable (macOS/Linux) — via script
bash build.sh
# atau manual:
pyinstaller --onefile --windowed --icon=assets/KangPaket-ico.png --name=KangPaket main.py
```

Output binary akan ada di `dist/KangPaket` atau `dist/KangPaket.exe`.

---

## Notes untuk Claude Code

1. **Semua sprint sudah selesai** — jangan implementasi ulang fitur yang sudah ada, cukup modifikasi jika ada bug atau request perubahan.
2. **Versi saat ini: 1.0.1** — update `APP_VERSION` di `app/config.py` dan `pyproject.toml` saat ada rilis baru.
3. **Jangan install library tambahan** di luar `requirements.txt` tanpa konfirmasi dulu.
4. **Jika ada ambiguitas**, pilih implementasi yang paling simpel dan konsisten dengan yang sudah ada.
5. **Test setelah setiap perubahan** — jalankan `python main.py` untuk verifikasi UI muncul dan fitur bekerja.
6. **CustomTkinter reference:** https://github.com/TomSchimansky/CustomTkinter
7. **httpx reference:** https://www.python-httpx.org/
8. **Postman Collection v2.1 schema reference:** https://schema.postman.com/collection/json/v2.1.0/draft-07/collection.json
