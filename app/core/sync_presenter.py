"""
KangPaket — Cloud Sync presentation helpers (pure logic, no widgets).

Turns SyncStatus / SyncResult / exceptions into user-facing Indonesian text, and holds the
small decision logic the UI uses, so all of it can be unit-tested without a display.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.sync_client import (
    AuthError, NetworkError, RateLimited, ServerError, SyncError,
)
from app.core.sync_manager import SyncPhase, SyncResult, SyncStatus

# Colour levels used by the UI for the status label.
LEVEL_MUTED = "muted"
LEVEL_OK = "ok"
LEVEL_BUSY = "busy"
LEVEL_WARN = "warn"
LEVEL_ERROR = "error"

LEVEL_COLORS: dict[str, str] = {
    LEVEL_MUTED: "#94a3b8",
    LEVEL_OK:    "#49cc90",
    LEVEL_BUSY:  "#61affe",
    LEVEL_WARN:  "#fca130",
    LEVEL_ERROR: "#f93e3e",
}

MAX_STATUS_MESSAGE = 70


@dataclass(frozen=True)
class StatusView:
    text: str
    level: str


def relative_time(ts_ms: int | None, now_ms: int) -> str:
    """'baru saja' / '5 menit lalu' / '2 jam lalu' / '3 hari lalu'."""
    if not ts_ms:
        return "belum pernah"
    seconds = max(0, (now_ms - ts_ms) // 1000)
    if seconds < 10:
        return "baru saja"
    if seconds < 60:
        return f"{seconds} detik lalu"
    if seconds < 3600:
        return f"{seconds // 60} menit lalu"
    if seconds < 86400:
        return f"{seconds // 3600} jam lalu"
    return f"{seconds // 86400} hari lalu"


def _shorten(text: str, limit: int = MAX_STATUS_MESSAGE) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _retry_text(retry_in: float | None, elapsed: float) -> str:
    if retry_in is None:
        return ""
    remaining = int(round(retry_in - elapsed))
    return f" (coba lagi dalam {remaining}s)" if remaining > 0 else " (mencoba lagi…)"


def status_view(status: SyncStatus, now_ms: int, elapsed: float = 0.0) -> StatusView:
    """Compact one-line status. `elapsed` = seconds since `status` was received (retry countdown)."""
    phase = status.phase
    if phase == SyncPhase.LOGGED_OUT:
        return StatusView("Belum login", LEVEL_MUTED)
    if phase == SyncPhase.SYNCING:
        return StatusView("Menyinkronkan...", LEVEL_BUSY)
    if phase == SyncPhase.AUTH_REQUIRED:
        return StatusView("Perlu login ulang", LEVEL_WARN)
    if phase == SyncPhase.OFFLINE:
        text = "Offline" + _retry_text(status.retry_in, elapsed)
        return StatusView(text, LEVEL_WARN)
    if phase == SyncPhase.ERROR:
        msg = _shorten(status.message) or "sinkronisasi gagal"
        return StatusView(f"Error: {msg}" + _retry_text(status.retry_in, elapsed), LEVEL_ERROR)
    # IDLE
    if status.last_sync_at:
        return StatusView(
            f"Tersinkron sebagai {status.username} · {relative_time(status.last_sync_at, now_ms)}",
            LEVEL_OK,
        )
    return StatusView(f"Masuk sebagai {status.username} · menunggu sinkronisasi", LEVEL_MUTED)


def friendly_login_error(exc: BaseException) -> str:
    """Message for the login dialog."""
    if isinstance(exc, AuthError):
        return "Username atau password salah."
    if isinstance(exc, RateLimited):
        wait = int(exc.retry_after) if exc.retry_after else 0
        suffix = f" Coba lagi dalam {wait} detik." if wait > 0 else " Tunggu sebentar lalu coba lagi."
        return "Terlalu banyak percobaan login." + suffix
    if isinstance(exc, NetworkError):
        return ("Server tidak terjangkau. Periksa koneksi internet, "
                "atau Server URL di bagian Lanjutan.")
    if isinstance(exc, ServerError):
        return "Server sync sedang bermasalah. Coba lagi nanti."
    if isinstance(exc, SyncError):
        return str(exc) or "Login gagal."
    return "Terjadi kesalahan tak terduga saat login."


def friendly_sync_error(exc: BaseException) -> str:
    """Message for a manual 'Sync Now' failure."""
    if isinstance(exc, AuthError):
        return "Sesi berakhir, silakan login ulang."
    if isinstance(exc, NetworkError):
        return "Tidak bisa terhubung ke server sync (offline). Akan dicoba lagi otomatis."
    if isinstance(exc, RateLimited):
        return "Terlalu banyak permintaan, coba lagi sebentar."
    if isinstance(exc, SyncError):
        return str(exc) or "Sinkronisasi gagal."
    return "Terjadi kesalahan tak terduga saat sinkronisasi."


def summary_lines(result: SyncResult | None) -> list[str]:
    """Human-readable summary of the last sync cycle (one item per line)."""
    if result is None:
        return ["Belum ada ringkasan sinkronisasi pada sesi ini."]
    lines = [
        f"Diterima dari server: {result.pulled}",
        f"Dikirim ke server: {result.pushed}",
        f"Konflik (versi server dipakai): {result.conflicts}",
    ]
    if result.skipped_large:
        names = ", ".join(result.skipped_large[:5])
        more = f" (+{len(result.skipped_large) - 5} lainnya)" if len(result.skipped_large) > 5 else ""
        lines.append(f"Dilewati karena terlalu besar (>256 KiB): {len(result.skipped_large)} — {names}{more}")
    else:
        lines.append("Dilewati karena terlalu besar: 0")
    if result.skipped_invalid:
        lines.append(f"Dilewati karena ID tidak valid: {result.skipped_invalid}")
    for w in result.warnings[:5]:
        lines.append(f"Peringatan: {w}")
    if len(result.warnings) > 5:
        lines.append(f"…dan {len(result.warnings) - 5} peringatan lain")
    return lines


def normalize_server_url(url: str) -> str:
    """Validate/normalise a user-entered server URL. Raises ValueError with a friendly message."""
    url = (url or "").strip().rstrip("/")
    if not url:
        raise ValueError("Server URL tidak boleh kosong.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Server URL harus diawali http:// atau https:// dan berisi host.")
    return url


# ---------------------------------------------------------------------------
# What to do with the request currently open when sync changes data on disk
# ---------------------------------------------------------------------------

ACTION_NONE = "none"
ACTION_RELOAD = "reload"                 # open profile changed remotely, no local edits: reload it
ACTION_CLOSE = "close"                   # open profile deleted remotely, no local edits: clear panel
ACTION_WARN_CHANGED = "warn_changed"     # changed remotely but user has unsaved edits: keep edits
ACTION_WARN_DELETED = "warn_deleted"     # deleted remotely but user has unsaved edits: keep edits


def decide_open_profile_action(
    loaded_updated_at: str | None,
    disk_updated_at: str | None,
    exists_on_disk: bool,
    dirty: bool,
) -> str:
    """
    loaded_updated_at: updated_at of the profile when it was loaded/saved in the panel
    (None = panel holds no saved profile -> nothing to reconcile).
    """
    if loaded_updated_at is None:
        return ACTION_NONE
    if not exists_on_disk:
        return ACTION_WARN_DELETED if dirty else ACTION_CLOSE
    if disk_updated_at == loaded_updated_at:
        return ACTION_NONE
    return ACTION_WARN_CHANGED if dirty else ACTION_RELOAD
