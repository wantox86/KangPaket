"""
KangPaket — Cloud Sync UI controller: runs login / manual sync / logout off the UI thread.

Widget-free so it can be unit-tested. `dispatch(fn)` must run `fn` on the UI thread
(e.g. `lambda fn: root.after(0, fn)`); results are delivered through it.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable

from app.core.sync_manager import AccountSwitchRequired, SyncManager, SyncResult
from app.core.sync_presenter import LogoutBlockers, friendly_login_error, friendly_sync_error


@dataclass(frozen=True)
class LogoutOutcome:
    """done=True: logged out and local data cleared. Otherwise nothing was touched:
    either blockers.needs_confirm (ask the user, then retry with force=True) or error is set."""
    done: bool
    blockers: LogoutBlockers = field(default_factory=LogoutBlockers)
    error: str = ""


class SyncUiController:
    def __init__(self, manager: SyncManager, dispatch: Callable[[Callable[[], None]], None]) -> None:
        self.manager = manager
        self._dispatch = dispatch
        self._busy_lock = threading.Lock()
        self._login_busy = False
        self._sync_busy = False
        self._logout_busy = False
        self._switch_previous_url = ""

    def _spawn(self, name: str, target: Callable[[], None]) -> None:
        threading.Thread(target=target, name=name, daemon=True).start()

    # ------------------------------------------------------------------
    def login_async(
        self, username: str, password: str, server_url: str,
        on_done: Callable[[bool, str], None],
        on_switch_required: Callable[[str, str], None] | None = None,
    ) -> bool:
        """Returns False (and does nothing) if a login is already running.
        on_done(ok, error_message). The password is only passed through, never stored.

        If the device still holds another account's data, nothing is stored or synced and
        on_switch_required(old_account, new_account) is called instead of on_done; the UI must
        then confirm and call confirm_switch_async() or cancel_switch_async()."""
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
            except AccountSwitchRequired as e:
                with self._busy_lock:
                    self._login_busy = False
                if on_switch_required is None:
                    self.manager.cancel_account_switch()
                    client.base_url = previous_url
                    self._dispatch(lambda: on_done(False, "Login dibatalkan."))
                else:
                    self._switch_previous_url = previous_url
                    old, new = e.old_account, e.new_account
                    self._dispatch(lambda: on_switch_required(old, new))
                return
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

    def confirm_switch_async(self, on_done: Callable[[bool, str], None]) -> None:
        """User confirmed the account switch: clear the old data, sign in, pull the new account."""
        def work() -> None:
            ok, message = False, ""
            try:
                self.manager.confirm_account_switch()
                ok = True
            except Exception as e:
                self.manager.client.base_url = self._switch_previous_url or self.manager.client.base_url
                message = friendly_login_error(e)
            self._dispatch(lambda: on_done(ok, message))

        self._spawn("kangpaket-switch-confirm", work)

    def cancel_switch_async(self, on_done: Callable[[bool, str], None]) -> None:
        """User declined the account switch: no token is kept, local data is untouched."""
        def work() -> None:
            try:
                self.manager.cancel_account_switch()
            except Exception as e:
                print(f"[SyncUiController] cancel switch failed: {e}")
            self.manager.client.base_url = self._switch_previous_url or self.manager.client.base_url
            self._dispatch(lambda: on_done(False, "Login dibatalkan. Data lokal tidak diubah."))

        self._spawn("kangpaket-switch-cancel", work)

    def logout_async(
        self, on_done: Callable[[LogoutOutcome], None], *, unsaved_edit: bool = False, force: bool = False,
    ) -> bool:
        """Logout = final sync, then clear local profiles/environments.

        Without force: if the final sync fails, items remain unsynced, or the editor has unsaved
        edits, nothing is touched and on_done gets done=False with the blockers to confirm.
        With force=True (after the user confirmed) the final sync is skipped and data is cleared.
        Returns False if a logout is already running."""
        with self._busy_lock:
            if self._logout_busy:
                return False
            self._logout_busy = True

        def work() -> None:
            try:
                outcome = self._logout(unsaved_edit, force)
            finally:
                with self._busy_lock:
                    self._logout_busy = False
            self._dispatch(lambda: on_done(outcome))

        self._spawn("kangpaket-logout", work)
        return True

    def _logout(self, unsaved_edit: bool, force: bool) -> LogoutOutcome:
        if not force:
            error = ""
            try:
                self.manager.sync_now()
            except Exception as e:
                error = friendly_sync_error(e)
            unsynced, large = self.manager.unsynced_summary()
            blockers = LogoutBlockers(error, unsynced, tuple(large), unsaved_edit)
            if blockers.needs_confirm:
                return LogoutOutcome(False, blockers)
        try:
            self.manager.logout_and_wipe()
        except Exception as e:
            print(f"[SyncUiController] logout failed: {e}")
            return LogoutOutcome(False, error="Logout gagal. Data lokal tidak diubah sepenuhnya; coba lagi.")
        return LogoutOutcome(True)
