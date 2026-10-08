"""
KangPaket — Cloud Sync manager: pull/merge/push cycle plus a background runner.

Flow of sync_now(): pull everything after the stored cursor and merge it into local data
(last-write-wins on client_updated_at, same tie-break as the server), then push what is
newer locally (or missing on the server, or deleted), adopting the server copy on conflict.
First login is the same flow with cursor 0, which makes it a two-way merge.
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from app.config import SYNC_DEBOUNCE_SECONDS, SYNC_INTERVAL_SECONDS
from app.core import sync_mapping as m
from app.core.environment_manager import EnvironmentManager
from app.core.profile_manager import ProfileManager
from app.core.sync_client import (
    AuthError, NetworkError, PayloadTooLarge, RateLimited, SyncClient, SyncError,
)
from app.core.sync_state import SyncState, now_ms

MAX_BATCH_ITEMS = 500
MAX_BATCH_BYTES = 4 * 1024 * 1024 + 512 * 1024   # server limit is 5 MiB; keep headroom


class SyncPhase(str, Enum):
    LOGGED_OUT = "logged_out"
    IDLE = "idle"                    # logged in and synced (or waiting for the first sync)
    SYNCING = "syncing"
    OFFLINE = "offline"
    ERROR = "error"
    AUTH_REQUIRED = "auth_required"  # session expired / refresh failed: login again


@dataclass(frozen=True)
class SyncStatus:
    phase: SyncPhase
    message: str = ""
    last_sync_at: int | None = None  # unix ms of the last successful sync
    retry_in: float | None = None    # seconds until the next automatic retry (offline/error)
    username: str = ""


@dataclass
class SyncResult:
    pulled: int = 0                  # items received from the server
    applied_local: int = 0           # upserts applied to local storage
    deleted_local: int = 0           # local items removed because of server tombstones
    pushed: int = 0                  # items accepted by the server (applied or already identical)
    conflicts: int = 0               # pushed items where the server copy won (adopted locally)
    skipped_large: list[str] = field(default_factory=list)   # names of items over 256 KiB
    skipped_invalid: int = 0         # local items without a valid lowercase UUID id
    warnings: list[str] = field(default_factory=list)

    @property
    def local_changed(self) -> bool:
        return bool(self.applied_local or self.deleted_local)


class SyncManager:
    def __init__(
        self,
        profiles: ProfileManager,
        environments: EnvironmentManager,
        state: SyncState,
        client: SyncClient,
        *,
        on_status: Callable[[SyncStatus], None] | None = None,
        on_data_changed: Callable[[SyncResult], None] | None = None,
        interval: float = SYNC_INTERVAL_SECONDS,
        debounce: float = SYNC_DEBOUNCE_SECONDS,
        backoff_base: float = 5.0,
        backoff_max: float = 300.0,
    ) -> None:
        """
        on_status / on_data_changed may be invoked from the runner thread: UI code must
        marshal them to the UI thread (e.g. widget.after(0, ...)).
        on_data_changed fires after a sync that modified local profiles/environments.
        """
        self._pm = profiles
        self._em = environments
        self.state = state
        self.client = client
        self.on_status = on_status
        self.on_data_changed = on_data_changed
        self._interval = interval
        self._debounce = debounce
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max

        self._sync_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._due_at: float | None = None        # debounced sync deadline (monotonic)
        self._next_periodic: float = 0.0
        self._backoff_until: float = 0.0
        self._failures = 0
        self._attached = False
        self._snap: dict[str, dict] = {}
        self.last_result: SyncResult | None = None   # summary of the last successful cycle
        self._status = SyncStatus(SyncPhase.LOGGED_OUT)
        self._status = self._make_status(
            SyncPhase.IDLE if state.logged_in else SyncPhase.LOGGED_OUT,
            state.last_error if state.logged_in and state.last_status == "error" else "",
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def status(self) -> SyncStatus:
        return self._status

    @property
    def logged_in(self) -> bool:
        return self.state.logged_in

    def _make_status(self, phase: SyncPhase, message: str = "", retry_in: float | None = None) -> SyncStatus:
        return SyncStatus(phase, message, self.state.last_sync_at, retry_in, self.state.username)

    def _set_status(self, phase: SyncPhase, message: str = "", retry_in: float | None = None) -> None:
        status = self._make_status(phase, message, retry_in)
        with self._status_lock:
            self._status = status
        if self.on_status:
            try:
                self.on_status(status)
            except Exception as e:
                print(f"[SyncManager] on_status failed: {e}")

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> None:
        """Raises SyncError subclasses (AuthError for wrong credentials). Triggers a sync if running."""
        self.client.login(username, password)
        self._failures = 0
        self._backoff_until = 0.0
        self._set_status(SyncPhase.IDLE)
        self.request_sync(immediate=True)

    def logout(self) -> None:
        self.client.logout()
        self.last_result = None
        self._due_at = None
        self._set_status(SyncPhase.LOGGED_OUT)

    # ------------------------------------------------------------------
    # Local change hooks
    # ------------------------------------------------------------------

    def attach(self) -> None:
        """Hook into the managers: record delete tombstones and request a debounced sync on edits."""
        if self._attached:
            return
        self._attached = True
        self._pm.on_change(self._on_profile_event)
        self._em.on_delete(lambda env_id: self.record_local_delete(m.ENVIRONMENT, env_id))
        self._em.on_data_change(self.request_sync)

    def _on_profile_event(self, event: str, profile_id: str) -> None:
        if event == "delete":
            self.record_local_delete(m.PROFILE, profile_id)
        else:
            self.state.drop_tombstone(m.PROFILE, profile_id)
            self.request_sync()

    def record_local_delete(self, kind: str, item_id: str) -> None:
        """Record that a profile/environment was deleted locally so the delete is pushed."""
        if not self.state.logged_in:
            return
        self.state.record_delete(kind, item_id)
        self.request_sync()

    # ------------------------------------------------------------------
    # Sync cycle
    # ------------------------------------------------------------------

    def sync_now(self) -> SyncResult:
        """Run one full sync (blocks; serialised with other syncs). Raises SyncError."""
        with self._sync_lock:
            if not self.state.logged_in:
                raise AuthError("Belum login.")
            self._set_status(SyncPhase.SYNCING)
            result = SyncResult()
            try:
                self._pull(result)
                self._push(result)
            except SyncError as e:
                self._fail(e)
                raise
            self.state.last_sync_at = now_ms()
            self.state.last_status, self.state.last_error = "ok", ""
            self.state.save()
            self.last_result = result
            self._set_status(SyncPhase.IDLE)
        if result.local_changed and self.on_data_changed:
            try:
                self.on_data_changed(result)
            except Exception as e:
                print(f"[SyncManager] on_data_changed failed: {e}")
        return result

    def _fail(self, e: SyncError) -> None:
        if isinstance(e, AuthError):
            phase = SyncPhase.AUTH_REQUIRED
        elif isinstance(e, NetworkError):
            phase = SyncPhase.OFFLINE
        else:
            phase = SyncPhase.ERROR
        self.state.last_status, self.state.last_error = phase.value, str(e)
        self.state.save()
        self._set_status(phase, str(e))

    # ---- local snapshot ------------------------------------------------

    def _load_snapshot(self) -> None:
        profiles = {p.id: p for p in self._pm.load_all_profiles()}
        envs = {e.id: e for e in list(self._em.envs)}
        envs[m.GLOBALS_ID] = m.globals_as_environment(self._em.globals, self._em.globals_updated_at)
        self._snap = {m.PROFILE: profiles, m.ENVIRONMENT: envs}

    def _local_ts(self, kind: str, item_id: str) -> int | None:
        obj = self._snap[kind].get(item_id)
        if obj is None:
            return None
        return m.profile_ts(obj) if kind == m.PROFILE else obj.updated_at

    def _local_key(self, kind: str, item_id: str) -> bytes:
        obj = self._snap[kind][item_id]
        if kind == m.PROFILE:
            return m.content_key(obj.collection, m.profile_payload(obj))
        return m.content_key(obj.name, m.environment_payload(obj))

    # ---- pull ----------------------------------------------------------

    def _pull(self, result: SyncResult) -> None:
        self._load_snapshot()
        while True:
            page = self.client.pull(self.state.cursor, 500)
            items = page.get("items", [])
            result.pulled += len(items)
            for item in items:
                try:
                    self._merge_server_item(item, result)
                except (KeyError, TypeError, ValueError, RuntimeError) as e:
                    result.warnings.append(f"Item {item.get('id', '?')} dilewati: data server tidak valid ({e})")
            cursor = int(page.get("cursor", self.state.cursor))
            advanced = cursor > self.state.cursor
            self.state.cursor = max(cursor, self.state.cursor)
            self.state.save()
            if not page.get("has_more") or not advanced:
                break

    def _merge_server_item(self, item: dict, result: SyncResult) -> None:
        kind, item_id = item["kind"], item["id"]
        if kind not in (m.PROFILE, m.ENVIRONMENT):
            return
        sts = int(item["client_updated_at"])
        deleted = bool(item.get("deleted"))
        known = self.state.known[kind]
        lts = self._local_ts(kind, item_id)

        tomb = self.state.tombstone(kind, item_id)
        if tomb is not None:
            if deleted or tomb["deleted_at"] >= sts:
                # We deleted it too (or our delete is at least as new): the delete stands.
                if deleted:
                    self.state.drop_tombstone(kind, item_id)
                    known.pop(item_id, None)
                return
            self.state.drop_tombstone(kind, item_id)   # server edit is newer than our delete

        if lts is None:
            if not deleted:
                self._apply_live(kind, item, result)
                known[item_id] = sts
            else:
                known.pop(item_id, None)
            return

        if deleted:
            if sts >= lts:
                self._apply_delete(kind, item_id, result)
                known.pop(item_id, None)
            else:
                known.pop(item_id, None)   # local is newer: push will resurrect it
            return

        if sts > lts:
            winner = "server"
        elif sts < lts:
            winner = "local"
        elif known.get(item_id) == lts:
            return
        else:
            label = item.get("label") or ""
            skey = m.content_key(label, item["payload"])
            lkey = self._local_key(kind, item_id)
            winner = "same" if skey == lkey else ("server" if skey > lkey else "local")

        if winner == "server":
            self._apply_live(kind, item, result)
            known[item_id] = sts
        elif winner == "same":
            known[item_id] = sts
        else:
            known.pop(item_id, None)

    # ---- apply to local storage (silent: no manager listeners fire) -----

    def _apply_live(self, kind: str, item: dict, result: SyncResult) -> None:
        if kind == m.PROFILE:
            profile = m.profile_from_wire(item)
            self._pm.save_profile(profile, touch=False, notify=False)
            self._snap[kind][profile.id] = profile
        elif item["id"] == m.GLOBALS_ID:
            env = m.environment_from_wire(item)
            self._em.apply_remote_globals(env.vars, env.updated_at)
            self._snap[kind][m.GLOBALS_ID] = m.globals_as_environment(env.vars, env.updated_at)
        else:
            env = m.environment_from_wire(item)
            self._em.apply_remote_env(env)
            self._snap[kind][env.id] = env
        result.applied_local += 1

    def _apply_delete(self, kind: str, item_id: str, result: SyncResult) -> None:
        if kind == m.PROFILE:
            self._pm.delete_profile(item_id, notify=False)
        elif item_id == m.GLOBALS_ID:
            return   # Globals is never deleted
        else:
            self._em.apply_remote_delete(item_id)
        self._snap[kind].pop(item_id, None)
        result.deleted_local += 1

    # ---- push ----------------------------------------------------------

    def _collect_local_changes(self, result: SyncResult) -> list[tuple[str, str, dict, int]]:
        """Return [(kind, id, wire_item, client_updated_at)] for everything the server may lack."""
        out: list[tuple[str, str, dict, int]] = []

        def add(kind: str, item_id: str, wire: dict, label: str) -> None:
            size = len(m.dumps(wire["payload"]).encode("utf-8"))
            if size > m.MAX_PAYLOAD_BYTES:
                result.skipped_large.append(label or item_id)
                result.warnings.append(f"'{label or item_id}' dilewati: ukuran {size // 1024} KiB melebihi batas 256 KiB")
                return
            out.append((kind, item_id, wire, wire["client_updated_at"]))

        for pid, p in self._snap[m.PROFILE].items():
            if not m.is_valid_id(pid):
                result.skipped_invalid += 1
            elif m.profile_ts(p) != self.state.known[m.PROFILE].get(pid):
                add(m.PROFILE, pid, m.profile_to_wire(p), p.name)
        for eid, e in self._snap[m.ENVIRONMENT].items():
            if e.updated_at <= 0:
                continue   # never edited (empty Globals)
            if not m.is_valid_id(eid):
                result.skipped_invalid += 1
            elif e.updated_at != self.state.known[m.ENVIRONMENT].get(eid):
                add(m.ENVIRONMENT, eid, m.environment_to_wire(e), e.name)
        for t in list(self.state.tombstones):
            kind, tid = t["kind"], t["id"]
            if self._local_ts(kind, tid) is not None or not m.is_valid_id(tid):
                self.state.drop_tombstone(kind, tid)   # re-created locally, or id can never sync
                continue
            out.append((kind, tid, m.tombstone_to_wire(tid, t["deleted_at"]), t["deleted_at"]))
        return out

    def _push(self, result: SyncResult) -> None:
        changes = self._collect_local_changes(result)
        batch: list[tuple[str, str, dict, int]] = []
        size = 0
        for change in changes:
            n = len(m.dumps(change[2]).encode("utf-8")) + 1
            if batch and (len(batch) >= MAX_BATCH_ITEMS or size + n > MAX_BATCH_BYTES):
                self._push_batch(batch, result)
                batch, size = [], 0
            batch.append(change)
            size += n
        if batch:
            self._push_batch(batch, result)

    def _push_batch(self, batch: list[tuple[str, str, dict, int]], result: SyncResult) -> None:
        profiles = [c[2] for c in batch if c[0] == m.PROFILE]
        envs = [c[2] for c in batch if c[0] == m.ENVIRONMENT]
        try:
            resp = self.client.push(profiles, envs)
        except PayloadTooLarge as e:
            if len(batch) == 1:
                kind, item_id = batch[0][0], batch[0][1]
                result.skipped_large.append(item_id)
                result.warnings.append(f"Item {item_id} ditolak server: {e}")
                return
            mid = len(batch) // 2
            self._push_batch(batch[:mid], result)
            self._push_batch(batch[mid:], result)
            return

        sent = {(c[0], c[1]): c for c in batch}
        for r in resp.get("results", []):
            key = (r.get("kind"), r.get("id"))
            if key not in sent:
                continue
            kind, item_id, wire, ts = sent[key]
            is_tomb = bool(wire.get("deleted"))
            known = self.state.known[kind]
            if r["status"] == "conflict" and r.get("server"):
                result.conflicts += 1
                self._adopt_server(kind, item_id, r["server"], result)
            else:
                result.pushed += 1
                if is_tomb:
                    known.pop(item_id, None)
                else:
                    known[item_id] = ts
            if is_tomb:
                self.state.drop_tombstone(kind, item_id)
        self.state.save()

    def _adopt_server(self, kind: str, item_id: str, server: dict, result: SyncResult) -> None:
        known = self.state.known[kind]
        server = {**server, "kind": kind, "id": item_id}
        if server.get("deleted"):
            if self._local_ts(kind, item_id) is not None:
                self._apply_delete(kind, item_id, result)
            known.pop(item_id, None)
            return
        try:
            self._apply_live(kind, server, result)
            known[item_id] = int(server["client_updated_at"])
        except (KeyError, TypeError, ValueError, RuntimeError) as e:
            result.warnings.append(f"Item {item_id}: data server tidak bisa diterapkan ({e})")

    # ------------------------------------------------------------------
    # Background runner
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._next_periodic = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="kangpaket-sync", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)
            self._thread = None

    def request_sync(self, immediate: bool = False) -> None:
        """Ask for a sync soon; bursts of calls collapse into one (debounced)."""
        if not self._active():
            return
        self._due_at = time.monotonic() + (0.0 if immediate else self._debounce)
        self._wake.set()

    def backoff_delay(self, failures: int) -> float:
        base = min(self._backoff_max, self._backoff_base * (2 ** max(0, failures - 1)))
        return base * random.uniform(0.75, 1.25)

    def _active(self) -> bool:
        return self.state.logged_in and self._status.phase != SyncPhase.AUTH_REQUIRED

    def _run(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            if not self._active():
                self._due_at = None
                self._next_periodic = now + self._interval
                timeout = self._interval
            else:
                due = self._next_periodic
                if self._due_at is not None:
                    due = min(due, self._due_at)
                timeout = max(due, self._backoff_until) - now
                if timeout <= 0:
                    self._run_once()
                    continue
            self._wake.wait(timeout)
            self._wake.clear()

    def _run_once(self) -> None:
        self._due_at = None
        try:
            self.sync_now()
        except AuthError:
            self._failures = 0   # status already auth_required; wait for a new login
            return
        except SyncError as e:
            self._failures += 1
            delay = self.backoff_delay(self._failures)
            if isinstance(e, RateLimited):
                delay = max(delay, e.retry_after)
            self._backoff_until = time.monotonic() + delay
            self._set_status(self._status.phase, str(e), retry_in=delay)
            return
        except Exception as e:   # never let the runner die silently
            print(f"[SyncManager] unexpected sync failure: {e}")
            self._failures += 1
            delay = self.backoff_delay(self._failures)
            self._backoff_until = time.monotonic() + delay
            self._set_status(SyncPhase.ERROR, "Kesalahan tak terduga saat sync.", retry_in=delay)
            return
        self._failures = 0
        self._backoff_until = 0.0
        self._next_periodic = time.monotonic() + self._interval
