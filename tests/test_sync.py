"""Cloud Sync client core tests (fake in-memory server, never touches the live one)."""
import json
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import sync_mapping as m
from app.core.environment_manager import EnvironmentManager
from app.core.profile_manager import ProfileManager
from app.core.sync_client import (
    AuthError, NetworkError, PayloadTooLarge, RateLimited, ServerError, SyncClient, resolve_server_url,
)
from app.core.sync_manager import SyncManager, SyncPhase
from app.core.sync_state import SyncState
from app.models.environment_model import Environment, Variable
from app.models.request_model import RequestProfile
from tests.fake_sync_server import FakeSyncServer

PW = "correct-horse-1"


class Device:
    def __init__(self, tmp_path, server: FakeSyncServer, name="dev", **mgr_kw) -> None:
        self.dir = tmp_path / name
        self.dir.mkdir(exist_ok=True)
        self.pm = ProfileManager(str(self.dir / "profiles"))
        self.em = EnvironmentManager(str(self.dir / "environments.json"))
        self.state = SyncState(str(self.dir / "sync_state.json"))
        self.client = SyncClient(self.state, "https://sync.test", transport=server.transport)
        self.statuses = []
        self.sm = SyncManager(self.pm, self.em, self.state, self.client, on_status=self.statuses.append,
                              debounce=0.05, interval=60, backoff_base=0.05, backoff_max=0.2, **mgr_kw)
        self.sm.attach()

    def login(self):
        self.client.login("alice", PW)

    def profile_ids(self):
        return {p.id for p in self.pm.load_all_profiles()}


@pytest.fixture
def server():
    return FakeSyncServer()


@pytest.fixture
def dev(tmp_path, server):
    return Device(tmp_path, server)


def mk_profile(name="P", collection="C", **kw) -> RequestProfile:
    return RequestProfile(name=name, url="https://x.test", collection=collection, **kw)


# ---------------------------------------------------------------- client

def test_login_refresh_on_401_and_logout(server, dev):
    dev.login()
    assert dev.state.refresh_token and dev.state.username == "alice"
    assert "correct-horse" not in open(dev.state._path).read()
    server.expire_access_tokens()
    old_refresh = dev.state.refresh_token
    dev.client.pull(0)
    assert dev.state.refresh_token != old_refresh        # rotated
    assert server.requests.count(("POST", "/auth/refresh")) == 1
    dev.client.logout()
    assert not dev.state.logged_in and dev.state.username == ""
    assert server.refresh == {}


def test_login_wrong_password(dev):
    with pytest.raises(AuthError):
        dev.client.login("alice", "nope-nope-nope")
    assert not dev.state.logged_in


def test_logout_clears_local_even_when_offline(server, dev):
    dev.login()
    server.down = True
    dev.client.logout()
    assert not dev.state.logged_in


def test_refresh_failure_raises_auth_error(server, dev):
    dev.login()
    server.expire_access_tokens()
    server.revoke_refresh_tokens()
    with pytest.raises(AuthError):
        dev.client.pull(0)
    assert not dev.state.logged_in


def test_typed_errors(server, dev):
    dev.login()
    server.down = True
    with pytest.raises(NetworkError):
        dev.client.pull(0)
    server.down = False
    server.fail_status = 503
    with pytest.raises(ServerError):
        dev.client.pull(0)
    server.fail_status = 413
    with pytest.raises(PayloadTooLarge):
        dev.client.push([], [])
    server.fail_status = 429
    with pytest.raises(RateLimited):
        dev.client.pull(0)


def test_resolve_server_url():
    class S:
        def __init__(self, v): self.v = v
        def get(self, k, d=None): return self.v if k == "sync_server_url" else d
    assert resolve_server_url(S("http://h:1/")) == "http://h:1"
    assert resolve_server_url(S(None)) == "https://kangpaket-api.quezacolt.my.id"


# ---------------------------------------------------------------- mapping

def test_profile_roundtrip_lossless():
    p = mk_profile(headers={"a": "b"}, auth_type="bearer", auth_data={"token": "s3cr3t"})
    p.extra = {"future_field": {"x": [1, 2]}}
    item = m.profile_to_wire(p)
    item["label"] = item["collection"]
    back = m.profile_from_wire({**item, "kind": "profile"})
    assert back.to_dict() == {**p.to_dict(), "updated_at": m.ms_to_iso(item["client_updated_at"])}
    assert back.auth_data == {"token": "s3cr3t"} and back.extra["future_field"] == {"x": [1, 2]}


def test_environment_roundtrip_lossless_secrets_untouched():
    v = Variable("k", "topsecret", secret=True, enabled=False, extra={"note": "n"})
    e = Environment("prod", [v], updated_at=1234, extra={"color": "red"})
    item = m.environment_to_wire(e)
    back = m.environment_from_wire({**item, "kind": "environment", "label": "prod"})
    assert back.to_dict() == e.to_dict()
    assert back.vars[0].secret and back.vars[0].value == "topsecret"


# ---------------------------------------------------------------- state

def test_state_corrupt_file_falls_back(tmp_path):
    path = tmp_path / "sync_state.json"
    path.write_text("{not json")
    s = SyncState(str(path))
    assert not s.logged_in and s.cursor == 0
    path.write_text(json.dumps({"cursor": "abc"}))
    assert SyncState(str(path)).cursor == 0


def test_state_atomic_write_and_permissions(tmp_path):
    s = SyncState(str(tmp_path / "sync_state.json"))
    s.begin_session("https://sync.test", "alice", "rt")
    s.record_delete("profile", "id1")
    again = SyncState(str(tmp_path / "sync_state.json"))
    assert again.refresh_token == "rt" and again.tombstone("profile", "id1")
    assert not os.path.exists(str(tmp_path / "sync_state.json.tmp"))
    if os.name == "posix":
        assert os.stat(s._path).st_mode & 0o777 == 0o600


# ---------------------------------------------------------------- sync

def test_first_login_two_way_merge_loses_nothing(tmp_path, server, dev):
    sp = mk_profile("server-only")
    server.seed("alice", "profile", sp.id, sp.collection, m.profile_payload(sp), m.profile_ts(sp) - 10)
    senv = Environment("srv-env", [Variable("a", "1")], updated_at=5000)
    server.seed("alice", "environment", senv.id, senv.name, m.environment_payload(senv), 5000)
    lp = mk_profile("local-only")
    dev.pm.save_profile(lp)
    dev.em.add(Environment("loc-env", [Variable("b", "2")]))
    dev.login()
    r = dev.sm.sync_now()
    assert dev.profile_ids() == {sp.id, lp.id}
    assert {e.name for e in dev.em.envs} == {"srv-env", "loc-env"}
    assert set(server.live("alice", "profile")) == {sp.id, lp.id}
    assert len(server.live("alice", "environment")) == 2
    assert r.pushed == 2 and dev.state.cursor > 0


def test_second_device_receives_and_secret_vars_intact(tmp_path, server, dev):
    p = mk_profile("shared", auth_type="basic", auth_data={"u": "a", "p": "b"})
    dev.pm.save_profile(p)
    dev.em.add(Environment("prod", [Variable("tok", "zzz", secret=True)]))
    dev.em.globals = [Variable("g", "1")]
    dev.em.changed()
    dev.login(); dev.sm.sync_now()
    b = Device(tmp_path, server, "devb"); b.login(); b.sm.sync_now()
    got = b.pm.get_profile(p.id)
    assert got.auth_data == {"u": "a", "p": "b"} and got.updated_at == dev.pm.get_profile(p.id).updated_at[:19] + got.updated_at[19:]
    assert [(v.key, v.value, v.secret) for v in b.em.envs[0].vars] == [("tok", "zzz", True)]
    assert [v.key for v in b.em.globals] == ["g"]
    assert b.em.active_id is None   # active selection is local


def test_local_delete_sends_tombstone_and_server_tombstone_deletes_local(tmp_path, server, dev):
    p1, p2 = mk_profile("a"), mk_profile("b")
    dev.pm.save_profile(p1); dev.pm.save_profile(p2)
    env = dev.em.add(Environment("e"))
    dev.login(); dev.sm.sync_now()
    b = Device(tmp_path, server, "devb"); b.login(); b.sm.sync_now()
    assert b.profile_ids() == {p1.id, p2.id}
    time.sleep(0.01)
    b.pm.delete_profile(p1.id)
    b.em.envs.remove(b.em.get(env.id)); b.em.changed()
    assert len(b.state.tombstones) == 2
    b.sm.sync_now()
    assert b.state.tombstones == []
    assert p1.id in server.tombstones("alice", "profile") and env.id in server.tombstones("alice", "environment")
    dev.sm.sync_now()
    assert dev.profile_ids() == {p2.id} and dev.em.envs == []


def test_conflict_server_wins(tmp_path, server, dev):
    p = mk_profile("orig")
    dev.pm.save_profile(p)
    dev.login(); dev.sm.sync_now()
    b = Device(tmp_path, server, "devb"); b.login(); b.sm.sync_now()
    mine = b.pm.get_profile(p.id); mine.name = "edited-b"; b.pm.save_profile(mine)
    time.sleep(0.01)
    theirs = dev.pm.get_profile(p.id); theirs.name = "edited-a-newer"; dev.pm.save_profile(theirs)
    dev.sm.sync_now()
    r = b.sm.sync_now()          # b is older: pull applies a's newer version first
    assert b.pm.get_profile(p.id).name == "edited-a-newer"
    # force a real push conflict: server gets a newer copy between b's pull and push
    mine = b.pm.get_profile(p.id); mine.name = "b-again"; b.pm.save_profile(mine)
    server.seed("alice", "profile", p.id, p.collection, {**m.profile_payload(mine), "name": "srv"}, m.profile_ts(mine) + 1000)
    orig_pull = b.client.pull
    b.client.pull = lambda since, limit=500: {"items": [], "cursor": since, "has_more": False}
    r = b.sm.sync_now()
    b.client.pull = orig_pull
    assert r.conflicts == 1 and b.pm.get_profile(p.id).name == "srv"


def test_push_idempotent(server, dev):
    dev.pm.save_profile(mk_profile())
    dev.login(); dev.sm.sync_now()
    n = len(server.push_calls)
    for _ in range(3):
        r = dev.sm.sync_now()
        assert r.pushed == 0 and r.applied_local == 0
    assert len(server.push_calls) == n
    version = server.version["alice"]
    # re-pushing identical content is skipped by the server (no version bump)
    dev.state.known["profile"].clear()
    r = dev.sm.sync_now()
    assert r.pushed == 1 and server.version["alice"] == version


def test_batching_over_500_items(server, dev):
    for i in range(1203):
        dev.pm.save_profile(mk_profile(f"p{i}"))
    dev.login(); dev.sm.sync_now()
    sizes = [len(c["profiles"]) + len(c["environments"]) for c in server.push_calls]
    assert max(sizes) <= 500 and sum(sizes) == 1203
    assert len(server.live("alice", "profile")) == 1203


def test_pull_pagination(server, dev):
    for i in range(7):
        pid = f"00000000-0000-4000-8000-00000000010{i}"
        server.seed("alice", "profile", pid, "c", {"id": pid, "name": f"n{i}", "url": "u", "collection": "c"}, 1000 + i)
    server.pull_page_cap = 3
    dev.login(); dev.sm.sync_now()
    assert len(dev.profile_ids()) == 7 and dev.state.cursor == 7
    assert len(server.pull_calls) == 3


def test_large_item_skipped_others_still_sync(server, dev):
    big = mk_profile("big", body_content="x" * (300 * 1024))
    ok = mk_profile("ok")
    dev.pm.save_profile(big); dev.pm.save_profile(ok)
    dev.login()
    r = dev.sm.sync_now()
    assert r.skipped_large == ["big"] and r.warnings
    assert set(server.live("alice", "profile")) == {ok.id}


def test_server_413_on_batch_is_split(server, dev):
    for i in range(4):
        dev.pm.save_profile(mk_profile(f"p{i}"))
    dev.login()
    real = dev.client.push
    def flaky(profiles, envs):
        if len(profiles) > 1:
            raise PayloadTooLarge("too big")
        return real(profiles, envs)
    dev.client.push = flaky
    r = dev.sm.sync_now()
    assert r.pushed == 4


def test_applying_pull_does_not_loop(tmp_path, server, dev):
    p = mk_profile("x"); dev.pm.save_profile(p)
    dev.em.add(Environment("e"))
    dev.login(); dev.sm.sync_now()
    b = Device(tmp_path, server, "devb"); b.login()
    requested = []
    b.sm.request_sync = lambda *a, **k: requested.append(1)
    b.sm.sync_now()
    assert requested == []
    assert b.state.tombstones == []
    pushes = len(server.push_calls)
    b.sm.sync_now(); b.sm.sync_now()
    assert len(server.push_calls) == pushes
    assert b.pm.get_profile(p.id).updated_at == m.ms_to_iso(server.live("alice", "profile")[p.id]["client_updated_at"])


def test_local_edit_bumps_and_propagates_env_edit_not_active_switch(tmp_path, server, dev):
    env = dev.em.add(Environment("e", [Variable("k", "1")]))
    dev.login(); dev.sm.sync_now()
    ts = dev.em.get(env.id).updated_at
    dev.em.set_active(env.id)
    assert dev.em.get(env.id).updated_at == ts
    time.sleep(0.01)
    dev.em.get(env.id).vars[0].value = "2"; dev.em.changed()
    assert dev.em.get(env.id).updated_at > ts
    dev.sm.sync_now()
    b = Device(tmp_path, server, "devb"); b.login(); b.sm.sync_now()
    assert b.em.envs[0].vars[0].value == "2"


def test_server_tombstone_vs_newer_local_resurrects(tmp_path, server, dev):
    p = mk_profile("keep"); dev.pm.save_profile(p)
    server.seed("alice", "profile", p.id, p.collection, None, m.profile_ts(p) - 500, deleted=True)
    dev.login(); dev.sm.sync_now()
    assert p.id in server.live("alice", "profile") and dev.pm.get_profile(p.id)


def test_globals_synced_as_fixed_id_environment(tmp_path, server, dev):
    dev.em.globals = [Variable("g", "1")]; dev.em.changed()
    dev.login(); dev.sm.sync_now()
    assert m.GLOBALS_ID in server.live("alice", "environment")
    b = Device(tmp_path, server, "devb"); b.login(); b.sm.sync_now()
    assert [v.key for v in b.em.globals] == ["g"] and b.em.envs == []


def test_record_delete_ignored_when_logged_out(dev):
    dev.sm.record_local_delete("profile", "abc")
    assert dev.state.tombstones == []


def test_logout_clears_progress(dev):
    dev.pm.save_profile(mk_profile())
    dev.login(); dev.sm.sync_now()
    dev.sm.logout()
    assert dev.state.cursor == 0 and dev.state.known["profile"] == {} and dev.sm.status.phase == SyncPhase.LOGGED_OUT


# ---------------------------------------------------------------- status / runner

def test_offline_status_and_backoff(server, dev):
    dev.login()
    server.down = True
    with pytest.raises(NetworkError):
        dev.sm.sync_now()
    assert dev.sm.status.phase == SyncPhase.OFFLINE
    d1, d2, d3 = (dev.sm.backoff_delay(n) for n in (1, 3, 10))
    assert d1 < d2 and d3 <= dev.sm._backoff_max * 1.25


def test_auth_required_when_refresh_fails(server, dev):
    dev.pm.save_profile(mk_profile())
    dev.login()
    server.expire_access_tokens(); server.revoke_refresh_tokens()
    with pytest.raises(AuthError):
        dev.sm.sync_now()
    assert dev.sm.status.phase == SyncPhase.AUTH_REQUIRED
    dev.sm.request_sync()          # ignored while auth is required
    assert dev.sm._due_at is None


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_runner_debounces_and_syncs_after_edit(server, dev):
    dev.login()
    dev.sm.start()
    try:
        assert wait_for(lambda: dev.state.last_sync_at)
        pushes = len(server.push_calls)
        for i in range(5):
            dev.pm.save_profile(mk_profile(f"p{i}"))
        assert wait_for(lambda: len(server.live("alice", "profile")) == 5)
        assert len(server.push_calls) - pushes == 1      # burst collapsed into one push
        assert dev.sm.status.phase == SyncPhase.IDLE
    finally:
        dev.sm.stop()


def test_runner_retries_after_offline_then_recovers(server, dev):
    dev.pm.save_profile(mk_profile())
    dev.login()
    server.down = True
    dev.sm.start()
    try:
        assert wait_for(lambda: dev.sm.status.phase == SyncPhase.OFFLINE)
        assert dev.sm.status.retry_in is not None
        server.down = False
        assert wait_for(lambda: len(server.live("alice", "profile")) == 1)
        assert wait_for(lambda: dev.sm.status.phase == SyncPhase.IDLE)
    finally:
        dev.sm.stop()


def test_runner_stops_retrying_on_auth_error(server, dev):
    dev.login()
    server.expire_access_tokens(); server.revoke_refresh_tokens()
    dev.sm.start()
    try:
        assert wait_for(lambda: dev.sm.status.phase == SyncPhase.AUTH_REQUIRED)
        calls = len(server.requests)
        time.sleep(0.5)
        assert len(server.requests) == calls
    finally:
        dev.sm.stop()


def test_only_one_sync_at_a_time(server, dev):
    dev.pm.save_profile(mk_profile())
    dev.login()
    active, peak = [0], [0]
    real = dev.client.pull
    def slow(since, limit=500):
        active[0] += 1; peak[0] = max(peak[0], active[0])
        time.sleep(0.1)
        try:
            return real(since, limit)
        finally:
            active[0] -= 1
    dev.client.pull = slow
    ts = [threading.Thread(target=dev.sm.sync_now) for _ in range(3)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert peak[0] == 1
