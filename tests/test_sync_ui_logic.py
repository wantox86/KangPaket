"""Cloud Sync UI logic tests (presenter, controller, hooks) — no display needed."""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.sync_client import (
    AuthError, NetworkError, RateLimited, RequestRejected, ServerError, SyncClient,
)
from app.core.sync_controller import SyncUiController
from app.core.sync_manager import SyncManager, SyncPhase, SyncResult, SyncStatus
from app.core.sync_presenter import (
    ACTION_CLOSE, ACTION_NONE, ACTION_RELOAD, ACTION_WARN_CHANGED, ACTION_WARN_DELETED,
    decide_open_profile_action, friendly_login_error, friendly_sync_error, normalize_server_url,
    relative_time, status_view, summary_lines,
)
from app.models.environment_model import Environment, Variable
from app.models.request_model import RequestProfile
from tests.test_sync import Device, PW, dev, mk_profile, server  # noqa: F401  (fixtures)

NOW = 1_700_000_000_000


# ---------------------------------------------------------------- presenter

def test_relative_time():
    assert relative_time(None, NOW) == "belum pernah"
    assert relative_time(NOW - 3_000, NOW) == "baru saja"
    assert relative_time(NOW - 30_000, NOW) == "30 detik lalu"
    assert relative_time(NOW - 5 * 60_000, NOW) == "5 menit lalu"
    assert relative_time(NOW - 2 * 3_600_000, NOW) == "2 jam lalu"
    assert relative_time(NOW - 3 * 86_400_000, NOW) == "3 hari lalu"
    assert relative_time(NOW + 5000, NOW) == "baru saja"   # clock skew


def test_status_view_all_phases():
    S = SyncStatus
    assert status_view(S(SyncPhase.LOGGED_OUT), NOW).text == "Belum login"
    assert status_view(S(SyncPhase.SYNCING), NOW).text == "Menyinkronkan..."
    assert status_view(S(SyncPhase.AUTH_REQUIRED), NOW).text == "Perlu login ulang"
    v = status_view(S(SyncPhase.IDLE, last_sync_at=NOW - 120_000, username="alice"), NOW)
    assert v.text == "Tersinkron sebagai alice · 2 menit lalu" and v.level == "ok"
    assert "menunggu" in status_view(S(SyncPhase.IDLE, username="alice"), NOW).text
    assert status_view(S(SyncPhase.OFFLINE, retry_in=12.4), NOW).text == "Offline (coba lagi dalam 12s)"
    assert status_view(S(SyncPhase.OFFLINE, retry_in=12.4), NOW, elapsed=20).text == "Offline (mencoba lagi…)"
    assert status_view(S(SyncPhase.OFFLINE), NOW).text == "Offline"
    e = status_view(S(SyncPhase.ERROR, message="Server sync sedang bermasalah.", retry_in=30), NOW)
    assert e.text == "Error: Server sync sedang bermasalah. (coba lagi dalam 30s)" and e.level == "error"
    long = status_view(S(SyncPhase.ERROR, message="x" * 500), NOW)
    assert len(long.text) < 100


def test_friendly_errors():
    assert friendly_login_error(AuthError("x")) == "Username atau password salah."
    assert "30 detik" in friendly_login_error(RateLimited("x", retry_after=30))
    assert "Tunggu" in friendly_login_error(RateLimited("x"))
    assert "tidak terjangkau" in friendly_login_error(NetworkError("x"))
    assert "bermasalah" in friendly_login_error(ServerError("x"))
    assert friendly_login_error(RequestRejected("ditolak")) == "ditolak"
    assert friendly_login_error(ValueError("secret detail")) == "Terjadi kesalahan tak terduga saat login."
    assert "login ulang" in friendly_sync_error(AuthError("x"))
    assert "offline" in friendly_sync_error(NetworkError("x"))
    assert "tak terduga" in friendly_sync_error(KeyError("x"))


def test_summary_lines():
    assert "Belum ada" in summary_lines(None)[0]
    r = SyncResult(pulled=3, pushed=2, conflicts=1, skipped_large=["Big"], skipped_invalid=1,
                   warnings=["w1"])
    text = "\n".join(summary_lines(r))
    for frag in ("Diterima dari server: 3", "Dikirim ke server: 2", "Konflik (versi server dipakai): 1",
                 "terlalu besar (>256 KiB): 1 — Big", "ID tidak valid: 1", "Peringatan: w1"):
        assert frag in text
    many = SyncResult(warnings=[f"w{i}" for i in range(9)])
    assert "4 peringatan lain" in "\n".join(summary_lines(many))


def test_normalize_server_url():
    assert normalize_server_url(" https://a.b/ ") == "https://a.b"
    assert normalize_server_url("http://192.168.1.2:8090") == "http://192.168.1.2:8090"
    for bad in ("", "   ", "ftp://x", "a.b", "https://"):
        with pytest.raises(ValueError):
            normalize_server_url(bad)


def test_decide_open_profile_action():
    d = decide_open_profile_action
    assert d(None, "x", True, True) == ACTION_NONE            # nothing saved is open
    assert d("t1", "t1", True, False) == ACTION_NONE
    assert d("t1", "t1", True, True) == ACTION_NONE
    assert d("t1", "t2", True, False) == ACTION_RELOAD
    assert d("t1", "t2", True, True) == ACTION_WARN_CHANGED
    assert d("t1", None, False, False) == ACTION_CLOSE
    assert d("t1", None, False, True) == ACTION_WARN_DELETED


# ---------------------------------------------------------------- controller

def run_sync_dispatch(fn):
    fn()


def wait(event, timeout=5):
    assert event.wait(timeout), "callback not called"


def test_controller_login_success_and_url(server, dev):
    ctl = SyncUiController(dev.sm, run_sync_dispatch)
    done, got = threading.Event(), []
    assert ctl.login_async("alice", PW, "https://sync.test/", lambda ok, msg: (got.append((ok, msg)), done.set()))
    wait(done)
    assert got == [(True, "")]
    assert dev.state.logged_in and dev.state.server_url == "https://sync.test"
    assert PW not in open(dev.state._path).read()


def test_controller_login_failure_restores_url_and_is_friendly(server, dev):
    ctl = SyncUiController(dev.sm, run_sync_dispatch)
    before = dev.client.base_url
    done, got = threading.Event(), []
    ctl.login_async("alice", "wrong-wrong", "https://other.test", lambda ok, msg: (got.append((ok, msg)), done.set()))
    wait(done)
    assert got == [(False, "Username atau password salah.")]
    assert dev.client.base_url == before and not dev.state.logged_in
    # offline
    server.down = True
    done.clear(); got.clear()
    ctl.login_async("alice", PW, "https://sync.test", lambda ok, msg: (got.append((ok, msg)), done.set()))
    wait(done)
    assert got[0][0] is False and "tidak terjangkau" in got[0][1]


def test_controller_rejects_parallel_login(server, dev):
    ctl = SyncUiController(dev.sm, run_sync_dispatch)
    gate, started = threading.Event(), threading.Event()
    orig = dev.sm.login

    def slow(u, p):
        started.set()
        gate.wait(5)
        orig(u, p)
    dev.sm.login = slow
    done = threading.Event()
    assert ctl.login_async("alice", PW, "https://sync.test", lambda ok, msg: done.set())
    wait(started)
    assert ctl.login_async("alice", PW, "https://sync.test", lambda ok, msg: None) is False
    gate.set()
    wait(done)


def test_controller_sync_now_and_errors(server, dev):
    ctl = SyncUiController(dev.sm, run_sync_dispatch)
    dev.login()
    p = mk_profile("Up")
    dev.pm.save_profile(p)
    done, got = threading.Event(), []
    ctl.sync_now_async(lambda r, msg: (got.append((r, msg)), done.set()))
    wait(done)
    r, msg = got[0]
    assert msg == "" and r.pushed >= 1 and dev.sm.last_result is r
    server.down = True
    done.clear(); got.clear()
    ctl.sync_now_async(lambda r, msg: (got.append((r, msg)), done.set()))
    wait(done)
    assert got[0][0] is None and "offline" in got[0][1]
    assert dev.sm.status.phase == SyncPhase.OFFLINE


# ---------------------------------------------------------------- hooks (auto-sync on change)

def test_local_changes_request_sync_but_active_env_switch_does_not(server, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(SyncManager, "request_sync", lambda self, immediate=False: calls.append(1))
    dev = Device(tmp_path, server, "hooks")   # patched before attach() binds the listeners
    dev.login()
    p = mk_profile("A")
    dev.pm.save_profile(p)                                   # save
    assert len(calls) == 1
    dev.pm.save_profile(p)                                   # rename/move = save
    assert len(calls) == 2
    dev.pm.delete_profile(p.id)                              # delete (via record_local_delete)
    assert len(calls) == 3
    env = dev.em.add(Environment("E1", [Variable("k", "v")]))   # add env = data change
    assert len(calls) == 4
    dev.em.changed()                                         # nothing modified
    assert len(calls) == 4
    n = len(calls)
    dev.em.set_active(env.id)                                # switch active env
    dev.em.set_active(None)
    assert len(calls) == n
    env.name = "E1b"
    dev.em.changed()                                         # rename = data change
    assert len(calls) == n + 1


def test_remote_apply_is_silent_and_last_result_set(server, tmp_path):
    a = Device(tmp_path, server, "a")
    b = Device(tmp_path, server, "b")
    a.login(); b.login()
    a.pm.save_profile(mk_profile("FromA"))
    a.sm.sync_now()
    changed = []
    b.sm.on_data_changed = changed.append
    calls = []
    b.sm.request_sync = lambda immediate=False: calls.append(1)
    r = b.sm.sync_now()
    assert r.applied_local == 1 and len(changed) == 1 and not calls   # no echo-sync loop


def test_environment_manager_concurrent_apply_and_save(tmp_path):
    from app.core.environment_manager import EnvironmentManager
    em = EnvironmentManager(str(tmp_path / "e.json"))
    stop = threading.Event()

    def remote():
        i = 0
        while not stop.is_set():
            i += 1
            em.apply_remote_env(Environment(f"R{i % 5}", [Variable("k", str(i))], id=f"{i % 5:032d}"))
    t = threading.Thread(target=remote)
    t.start()
    try:
        for i in range(200):
            em.add(Environment(f"L{i}", [Variable("x", "1")]))
    finally:
        stop.set(); t.join()
    import json
    data = json.load(open(tmp_path / "e.json"))   # always valid JSON
    assert len(data["envs"]) >= 200
