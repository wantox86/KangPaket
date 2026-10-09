"""
KangPaket — Cloud Sync local state (data/sync_state.json).

Holds the session (server URL, username, refresh token — never the password),
the pull cursor, per-item "last synced timestamp" and local delete tombstones.
"""
from __future__ import annotations

import json
import os
import threading
import time

from app.config import SYNC_STATE_FILE

KINDS = ("profile", "environment")


def now_ms() -> int:
    return int(time.time() * 1000)


class SyncState:
    def __init__(self, path: str = SYNC_STATE_FILE) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._reset()
        self.load()

    def _reset(self) -> None:
        self.server_url: str = ""
        self.username: str = ""
        self.refresh_token: str = ""
        self.cursor: int = 0
        self.tombstones: list[dict] = []          # {"kind", "id", "deleted_at"}
        self.known: dict[str, dict[str, int]] = {k: {} for k in KINDS}
        self.last_sync_at: int | None = None
        self.last_status: str = ""
        self.last_error: str = ""

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        with self._lock:
            self._reset()
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._from_dict(data)
            except FileNotFoundError:
                return
            except (json.JSONDecodeError, OSError, AttributeError, TypeError, ValueError, KeyError) as e:
                print(f"[SyncState] Failed to load sync state: {type(e).__name__}. Starting empty.")
                self._reset()

    def _from_dict(self, data: dict) -> None:
        if not isinstance(data, dict):
            raise TypeError("state is not an object")
        self.server_url = str(data.get("server_url") or "")
        self.username = str(data.get("username") or "")
        self.refresh_token = str(data.get("refresh_token") or "")
        self.cursor = max(0, int(data.get("cursor") or 0))
        last = data.get("last_sync_at")
        self.last_sync_at = int(last) if last else None
        self.last_status = str(data.get("last_status") or "")
        self.last_error = str(data.get("last_error") or "")
        self.tombstones = [
            {"kind": str(t["kind"]), "id": str(t["id"]), "deleted_at": int(t["deleted_at"])}
            for t in data.get("tombstones", [])
            if isinstance(t, dict) and t.get("kind") in KINDS
        ]
        known = data.get("known") or {}
        self.known = {
            k: {str(i): int(ts) for i, ts in (known.get(k) or {}).items()} for k in KINDS
        }

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "server_url": self.server_url,
            "username": self.username,
            "refresh_token": self.refresh_token,
            "cursor": self.cursor,
            "tombstones": self.tombstones,
            "known": self.known,
            "last_sync_at": self.last_sync_at,
            "last_status": self.last_status,
            "last_error": self.last_error,
        }

    def save(self) -> None:
        with self._lock:
            tmp = f"{self._path}.tmp"
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.to_dict(), f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self._path)
                try:
                    os.chmod(self._path, 0o600)
                except OSError:
                    pass
            except OSError as e:
                print(f"[SyncState] Failed to save sync state: {e}")

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    @property
    def logged_in(self) -> bool:
        return bool(self.refresh_token)

    def begin_session(self, server_url: str, username: str, refresh_token: str) -> None:
        """Store a fresh login. Sync progress is reset when the account or server differs."""
        with self._lock:
            if username != self.username or server_url != self.server_url:
                self.cursor = 0
                self.tombstones = []
                self.known = {k: {} for k in KINDS}
                self.last_sync_at = None
            self.server_url, self.username, self.refresh_token = server_url, username, refresh_token
            self.last_status, self.last_error = "", ""
            self.save()

    def set_refresh_token(self, token: str) -> None:
        with self._lock:
            self.refresh_token = token
            self.save()

    def end_session(self) -> None:
        """Forget the account and all sync progress; keep only the server URL."""
        with self._lock:
            url = self.server_url
            self._reset()
            self.server_url = url
            self.save()

    # ------------------------------------------------------------------
    # Tombstones
    # ------------------------------------------------------------------

    def record_delete(self, kind: str, item_id: str, deleted_at: int | None = None) -> None:
        with self._lock:
            self.tombstones = [t for t in self.tombstones if not (t["kind"] == kind and t["id"] == item_id)]
            self.tombstones.append({"kind": kind, "id": item_id, "deleted_at": deleted_at or now_ms()})
            self.known[kind].pop(item_id, None)
            self.save()

    def tombstone(self, kind: str, item_id: str) -> dict | None:
        with self._lock:
            return next((t for t in self.tombstones if t["kind"] == kind and t["id"] == item_id), None)

    def drop_tombstone(self, kind: str, item_id: str) -> None:
        with self._lock:
            self.tombstones = [t for t in self.tombstones if not (t["kind"] == kind and t["id"] == item_id)]
