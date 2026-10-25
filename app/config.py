"""
KangPaket — App-wide constants and configuration.
"""

APP_NAME = "KangPaket"
APP_VERSION = "1.0.2"
APP_TITLE = "KangPaket"
USER_AGENT = "KangPaket/1.0"

# HTTP Method colors
METHOD_COLORS: dict[str, str] = {
    "GET":     "#61affe",
    "POST":    "#49cc90",
    "PUT":     "#fca130",
    "PATCH":   "#50e3c2",
    "DELETE":  "#f93e3e",
    "HEAD":    "#9012fe",
    "OPTIONS": "#0d5aa7",
}

HTTP_METHODS: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]

# Status code colors
def status_color(code: int) -> str:
    if 200 <= code < 300:
        return "#49cc90"
    elif 300 <= code < 400:
        return "#fca130"
    elif 400 <= code < 600:
        return "#f93e3e"
    return "#aaaaaa"

# Body types
BODY_TYPES: list[str] = ["none", "raw", "form-data", "x-www-form-urlencoded"]

# Auth types
AUTH_TYPES: list[str] = ["none", "bearer", "basic", "api-key"]

# Runner assertion types (evaluated by app/core/runner_engine.py)
ASSERTION_TYPES: list[str] = [
    "status_code_equals",
    "status_code_in",
    "response_time_less_than",
    "body_contains",
    "body_json_path_equals",
    "header_exists",
    "header_equals",
]

ASSERTION_LABELS: dict[str, str] = {
    "status_code_equals":      "Status code equals",
    "status_code_in":          "Status code in",
    "response_time_less_than": "Response time < (ms)",
    "body_contains":           "Body contains",
    "body_json_path_equals":   "Body JSON path equals",
    "header_exists":           "Header exists",
    "header_equals":           "Header equals",
}

# Raw body content types
RAW_CONTENT_TYPES: list[str] = [
    "application/json",
    "application/xml",
    "text/plain",
    "text/html",
    "application/javascript",
]

# Fonts
FONT_MONO = "Courier New"
FONT_UI   = "Segoe UI"

# Sidebar width
SIDEBAR_WIDTH = 220

# Data directories
import os
BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR      = os.path.join(BASE_DIR, "data")
PROFILES_DIR  = os.path.join(DATA_DIR, "profiles")
RESULTS_DIR   = os.path.join(DATA_DIR, "runner_results")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
ENVIRONMENTS_FILE = os.path.join(DATA_DIR, "environments.json")
ASSETS_DIR    = os.path.join(BASE_DIR, "assets")

# Cloud Sync
SYNC_STATE_FILE        = os.path.join(DATA_DIR, "sync_state.json")
SYNC_DEFAULT_URL       = "https://kangpaket-api.quezacolt.my.id"
SYNC_SETTINGS_URL_KEY  = "sync_server_url"   # optional override in settings.json
SYNC_INTERVAL_SECONDS  = 90
SYNC_DEBOUNCE_SECONDS  = 2.5
SYNC_HTTP_TIMEOUT      = 20.0
