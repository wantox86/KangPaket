"""
KangPaket — Cloud Sync presentation helpers (pure logic, no widgets).

Turns SyncStatus / SyncResult / exceptions into user-facing English text, and holds the
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
    """'just now' / '5 minutes ago' / '2 hours ago' / '3 days ago'."""
    if not ts_ms:
        return "never"
    seconds = max(0, (now_ms - ts_ms) // 1000)
    if seconds < 10:
        return "just now"
    if seconds < 60:
        return f"{seconds} seconds ago"
    if seconds < 3600:
        return f"{seconds // 60} minutes ago"
    if seconds < 86400:
        return f"{seconds // 3600} hours ago"
    return f"{seconds // 86400} days ago"


def _shorten(text: str, limit: int = MAX_STATUS_MESSAGE) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _retry_text(retry_in: float | None, elapsed: float) -> str:
    if retry_in is None:
        return ""
    remaining = int(round(retry_in - elapsed))
    return f" (retry in {remaining}s)" if remaining > 0 else " (retrying…)"


def status_view(status: SyncStatus, now_ms: int, elapsed: float = 0.0) -> StatusView:
    """Compact one-line status. `elapsed` = seconds since `status` was received (retry countdown)."""
    phase = status.phase
    if phase == SyncPhase.LOGGED_OUT:
        return StatusView("Not logged in", LEVEL_MUTED)
    if phase == SyncPhase.SYNCING:
        return StatusView("Syncing...", LEVEL_BUSY)
    if phase == SyncPhase.AUTH_REQUIRED:
        return StatusView("Please log in again", LEVEL_WARN)
    if phase == SyncPhase.OFFLINE:
        text = "Offline" + _retry_text(status.retry_in, elapsed)
        return StatusView(text, LEVEL_WARN)
    if phase == SyncPhase.ERROR:
        msg = _shorten(status.message) or "sync failed"
        return StatusView(f"Error: {msg}" + _retry_text(status.retry_in, elapsed), LEVEL_ERROR)
    # IDLE
    if status.last_sync_at:
        return StatusView(
            f"Synced as {status.username} · {relative_time(status.last_sync_at, now_ms)}",
            LEVEL_OK,
        )
    return StatusView(f"Logged in as {status.username} · waiting to sync", LEVEL_MUTED)


def friendly_login_error(exc: BaseException) -> str:
    """Message for the login dialog."""
    if isinstance(exc, AuthError):
        return "Incorrect username or password."
    if isinstance(exc, RateLimited):
        wait = int(exc.retry_after) if exc.retry_after else 0
        suffix = f" Try again in {wait} seconds." if wait > 0 else " Wait a moment and try again."
        return "Too many login attempts." + suffix
    if isinstance(exc, NetworkError):
        return ("Server unreachable. Check your internet connection, "
                "or the Server URL under Advanced.")
    if isinstance(exc, ServerError):
        return "The sync server is having problems. Try again later."
    if isinstance(exc, SyncError):
        return str(exc) or "Login failed."
    return "An unexpected error occurred during login."


def friendly_sync_error(exc: BaseException) -> str:
    """Message for a manual 'Sync Now' failure."""
    if isinstance(exc, AuthError):
        return "Session expired. Please log in again."
    if isinstance(exc, NetworkError):
        return "Cannot connect to the sync server (offline). Will retry automatically."
    if isinstance(exc, RateLimited):
        return "Too many requests. Try again in a moment."
    if isinstance(exc, SyncError):
        return str(exc) or "Sync failed."
    return "An unexpected error occurred during sync."


def summary_lines(result: SyncResult | None) -> list[str]:
    """Human-readable summary of the last sync cycle (one item per line)."""
    if result is None:
        return ["No sync summary yet in this session."]
    lines = [
        f"Received from server: {result.pulled}",
        f"Sent to server: {result.pushed}",
        f"Conflicts (server version used): {result.conflicts}",
    ]
    if result.skipped_large:
        names = ", ".join(result.skipped_large[:5])
        more = f" (+{len(result.skipped_large) - 5} more)" if len(result.skipped_large) > 5 else ""
        lines.append(f"Skipped because too large (>256 KiB): {len(result.skipped_large)} — {names}{more}")
    else:
        lines.append("Skipped because too large: 0")
    if result.skipped_invalid:
        lines.append(f"Skipped because of invalid ID: {result.skipped_invalid}")
    for w in result.warnings[:5]:
        lines.append(f"Warning: {w}")
    if len(result.warnings) > 5:
        lines.append(f"…and {len(result.warnings) - 5} more warnings")
    return lines


def normalize_server_url(url: str) -> str:
    """Validate/normalise a user-entered server URL. Raises ValueError with a friendly message."""
    url = (url or "").strip().rstrip("/")
    if not url:
        raise ValueError("Server URL cannot be empty.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Server URL must start with http:// or https:// and include a host.")
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


# ---------------------------------------------------------------------------
# Logout / account switch: what the user must confirm before local data is wiped
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LogoutBlockers:
    """Why a logout (which clears local data) must not proceed silently."""
    sync_error: str = ""                 # message of the failed final sync ("" = it succeeded)
    unsynced: int = 0                    # local items the server does not have
    skipped_large: tuple[str, ...] = ()  # names of items too large to sync
    unsaved_edit: bool = False           # the editor holds edits that were never saved

    @property
    def needs_confirm(self) -> bool:
        return bool(self.sync_error or self.unsynced or self.skipped_large or self.unsaved_edit)


LOGOUT_TITLE = "Logout Cloud Sync"
LOGOUT_CONFIRM_QUESTION = "There are changes that have not been synced and will be lost. Log out anyway and delete local data?"
LOGOUT_CONFIRM_YES = "Log out anyway"
SWITCH_CONFIRM_YES = "Continue"
CONFIRM_CANCEL = "Cancel"


def logout_intro_text(username: str) -> str:
    """First dialog: explains what logout does (it clears local data, like Postman)."""
    return (
        f"Log out of account '{username or 'this account'}'?\n\n"
        "• Your latest changes are synced to the server first.\n"
        "• Profiles and environments are removed from this device. Your data stays safe on the server; "
        "logging in again downloads it back.\n"
        "• Automatic sync stops and the session on this device is removed.\n"
        "• App settings (theme, Server URL, etc.) are not removed."
    )


def logout_blockers_text(b: LogoutBlockers) -> str:
    """Second dialog, shown only when something would be lost."""
    lines = [LOGOUT_CONFIRM_QUESTION, ""]
    if b.sync_error:
        lines.append(f"• The last sync failed: {_shorten(b.sync_error, 120)}")
    if b.unsynced:
        lines.append(f"• {b.unsynced} item(s) have not been sent to the server.")
    if b.skipped_large:
        names = ", ".join(b.skipped_large[:5])
        more = f" (+{len(b.skipped_large) - 5} more)" if len(b.skipped_large) > 5 else ""
        lines.append(f"• Too large to sync (>256 KiB): {names}{more}")
    if b.unsaved_edit:
        lines.append("• A request being edited has unsaved changes.")
    return "\n".join(lines)


def account_switch_text(old_account: str, new_account: str, unsaved_edit: bool = False) -> str:
    text = (
        f"Local data belongs to account {old_account}. Logging in as {new_account} will delete "
        "that local data (anything not yet synced may be lost). Continue?"
    )
    if unsaved_edit:
        text += "\n\nThe request being edited, with its unsaved changes, will also be lost."
    return text
