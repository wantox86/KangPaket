"""
KangPaket — Cloud Sync UI controller: runs login / manual sync / logout off the UI thread.

Widget-free so it can be unit-tested. `dispatch(fn)` must run `fn` on the UI thread
(e.g. `lambda fn: root.after(0, fn)`); results are delivered through it.
"""
from __future__ import annotations

import threading
from typing import Callable

from app.core.sync_manager import SyncManager, SyncResult
from app.core.sync_presenter import friendly_login_error, friendly_sync_error


class SyncUiController:
    def __init__(self, manager: SyncManager, dispatch: Callable[[Callable[[], None]], None]) -> None:
        self.manager = manager
        self._dispatch = dispatch
        self._busy_lock = threading.Lock()
        self._login_busy = False
        self._sync_busy = False

    def _spawn(self, name: str, target: Callable[[], None]) -> None:
        threading.Thread(target=target, name=name, daemon=True).start()

    # ------------------------------------------------------------------
    def login_async(
        self, username: str, password: str, server_url: str,
        on_done: Callable[[bool, str], None],
    ) -> bool:
        """Returns False (and does nothing) if a login is already running.
        on_done(ok, error_message). The password is only passed through, never stored."""
        with self._busy_lock:
            if self._login_busy:
                return False
            self._login_busy = True
        client = self.manager.client

        def work() -> None:
            previous_url = client.base_url
            ok, message = False, ""
            try:
                client.base_url = server_url.rstrip("/")
                self.manager.login(username.strip(), password)
                ok = True
            except Exception as e:   # SyncError subclasses or anything unexpected
                client.base_url = previous_url
                message = friendly_login_error(e)
            finally:
                with self._busy_lock:
                    self._login_busy = False
            self._dispatch(lambda: on_done(ok, message))

        self._spawn("kangpaket-login", work)
        return True

    def sync_now_async(self, on_done: Callable[[SyncResult | None, str], None]) -> bool:
        """on_done(result, error_message); exactly one of them is meaningful."""
        with self._busy_lock:
            if self._sync_busy:
                return False
            self._sync_busy = True

        def work() -> None:
            result: SyncResult | None = None
            message = ""
            try:
                result = self.manager.sync_now()
            except Exception as e:
                message = friendly_sync_error(e)
            finally:
                with self._busy_lock:
                    self._sync_busy = False
            self._dispatch(lambda: on_done(result, message))

        self._spawn("kangpaket-sync-now", work)
        return True

    def logout_async(self, on_done: Callable[[], None]) -> None:
        def work() -> None:
            try:
                self.manager.logout()
            except Exception as e:
                print(f"[SyncUiController] logout failed: {e}")
            self._dispatch(on_done)

        self._spawn("kangpaket-logout", work)
