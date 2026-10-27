"""Cloud Sync login must survive closing/reopening the app (no GUI, fake sync server only).

Logout is only ever: explicit user action, or the server rejecting the refresh token (401).
Closing the window and transient network/server errors must never log out or wipe data.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.sync_client import AuthError, NetworkError
from app.core.sync_manager import SyncPhase
from tests.fake_sync_server import FakeSyncServer
from tests.test_sync import Device, mk_profile


@pytest.fixture
def server():
    return FakeSyncServer()


def restart(tmp_path, server, name="dev"):
    """Simulate quitting and reopening the app: brand-new objects, same data dir."""
    return Device(tmp_path, server, name=name)


def test_session_persists_across_restart(tmp_path, server):
    d1 = Device(tmp_path, server)
    d1.login()
    d1.pm.save_profile(mk_profile("keep-me"))
    d1.sm.sync_now()
    token = d1.state.refresh_token

    d2 = restart(tmp_path, server)
    assert d2.state.logged_in and d2.state.username == "alice"
    assert d2.state.refresh_token == token
    assert d2.sm.status.phase == SyncPhase.IDLE          # not LOGGED_OUT
    d2.sm.sync_now()                                      # fresh process: refreshes silently
    assert d2.state.logged_in
    assert {p.name for p in d2.pm.load_all_profiles()} == {"keep-me"}


def test_network_error_on_refresh_does_not_logout_or_wipe(tmp_path, server):
    d1 = Device(tmp_path, server)
    d1.login()
    d1.pm.save_profile(mk_profile("precious"))
    d1.sm.sync_now()

    d2 = restart(tmp_path, server)
    server.down = True                                    # first call after restart needs /auth/refresh
    with pytest.raises(NetworkError):
        d2.sm.sync_now()
    assert d2.state.logged_in and d2.state.refresh_token
    assert d2.sm.status.phase == SyncPhase.OFFLINE
    assert {p.name for p in d2.pm.load_all_profiles()} == {"precious"}

    # and the stored session still works once the network is back, even after another restart
    server.down = False
    d3 = restart(tmp_path, server)
    d3.sm.sync_now()
    assert d3.state.logged_in


def test_refresh_401_ends_session_but_keeps_local_data(tmp_path, server):
    """Design: a rejected refresh token = 'Session expired'. Session is dropped (login again),
    but local data and the account are KEPT (no wipe); only explicit Logout wipes."""
    d1 = Device(tmp_path, server)
    d1.login()
    d1.pm.save_profile(mk_profile("still-here"))
    d1.sm.sync_now()

    server.revoke_refresh_tokens()
    d2 = restart(tmp_path, server)
    with pytest.raises(AuthError):
        d2.sm.sync_now()
    assert not d2.state.logged_in
    assert d2.state.last_account == "alice"
    assert {p.name for p in d2.pm.load_all_profiles()} == {"still-here"}


def test_close_handler_does_not_logout(tmp_path, server):
    from app.ui.app_window import AppWindow

    d = Device(tmp_path, server)
    d.login()
    d.pm.save_profile(mk_profile("p"))
    calls = []

    class Root:
        def destroy(self):
            calls.append("destroy")

    class Sync:
        def stop(self, timeout=0):
            calls.append("stop")

        def logout(self):
            calls.append("LOGOUT")

        def logout_and_wipe(self):
            calls.append("WIPE")

    stub = type("W", (), {})()
    stub._closing, stub._root, stub._sync = False, Root(), Sync()
    AppWindow._on_close(stub)
    assert calls == ["stop", "destroy"]
    assert d.state.logged_in and d.pm.load_all_profiles()
    assert restart(tmp_path, server).state.logged_in


def test_close_handler_source_has_no_logout():
    import inspect
    from app.ui.app_window import AppWindow
    src = inspect.getsource(AppWindow._on_close)
    assert "logout" not in src and "end_session" not in src and "wipe" not in src


# ---- where data lives (root cause of "logout on close" in PyInstaller builds) ----

def _reload_config(monkeypatch, *, frozen, platform="darwin", override=None):
    monkeypatch.delenv("KANGPAKET_DATA_DIR", raising=False)
    if override:
        monkeypatch.setenv("KANGPAKET_DATA_DIR", override)
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(sys, "platform", platform)
    import app.config as cfg
    return importlib.reload(cfg)


@pytest.fixture
def restore_config():
    yield
    import app.config as cfg
    importlib.reload(cfg)


def test_frozen_build_uses_persistent_user_dir_not_bundle(monkeypatch, tmp_path, restore_config):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = _reload_config(monkeypatch, frozen=True, platform="darwin")
    assert cfg.DATA_DIR == os.path.join(os.path.expanduser("~"), "Library", "Application Support", "KangPaket")
    assert cfg.SYNC_STATE_FILE.startswith(cfg.DATA_DIR) and cfg.PROFILES_DIR.startswith(cfg.DATA_DIR)
    assert not cfg.DATA_DIR.startswith(cfg.BASE_DIR)


def test_source_run_keeps_repo_data_dir(monkeypatch, restore_config):
    cfg = _reload_config(monkeypatch, frozen=False)
    assert cfg.DATA_DIR == os.path.join(cfg.BASE_DIR, "data")


def test_data_dir_env_override(monkeypatch, tmp_path, restore_config):
    cfg = _reload_config(monkeypatch, frozen=True, override=str(tmp_path / "x"))
    assert cfg.DATA_DIR == str(tmp_path / "x")
