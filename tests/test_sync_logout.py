"""Logout clears local data; account-switch protection (no GUI, fake sync server only)."""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.sync_controller import SyncUiController
from app.core.sync_manager import AccountSwitchRequired, SyncPhase
from app.core.sync_presenter import (
    LogoutBlockers, account_switch_text, logout_blockers_text, logout_intro_text,
)
from app.core.sync_state import SyncState
from app.models.environment_model import Environment, Variable
from tests.fake_sync_server import FakeSyncServer
from tests.test_sync import Device, PW, mk_profile

PW_B = "battery-staple-2"
URL = "https://sync.test"


@pytest.fixture
def server():
    return FakeSyncServer({"alice": PW, "bob": PW_B})


@pytest.fixture
def dev(tmp_path, server):
    return Device(tmp_path, server)


def inline(fn):
    fn()


def do_logout(ctl, **kw):
    got, done = [], threading.Event()
    assert ctl.logout_async(lambda o: (got.append(o), done.set()), **kw)
    assert done.wait(5)
    return got[0]


def do_login(ctl, user, pw):
    got = {}
    done = threading.Event()
    ctl.login_async(user, pw, URL, lambda ok, msg: (got.update(done=(ok, msg)), done.set()),
                    on_switch_required=lambda old, new: (got.update(switch=(old, new)), done.set()))
    assert done.wait(5)
    return got


def finish(ctl, fn):
    done, got = threading.Event(), []
    fn(lambda ok, msg: (got.append((ok, msg)), done.set()))
    assert done.wait(5)
    return got[0]


def populate(dev):
    dev.pm.save_profile(mk_profile("P1"))
    dev.pm.save_profile(mk_profile("P2", collection="Other"))
    dev.em.add(Environment("E1", [Variable("a", "1")]))
    dev.em.globals = [Variable("g", "1")]
    dev.em.set_active(dev.em.envs[0].id)
    dev.em.changed()


def local_names(dev):
    return sorted(p.name for p in dev.pm.load_all_profiles()), sorted(e.name for e in dev.em.envs)


# ------------------------------------------------------------ logout

def test_logout_syncs_then_wipes_everything_without_tombstones(server, dev):
    ctl = SyncUiController(dev.sm, inline)
    wiped = []
    dev.sm.on_wiped = lambda: wiped.append(1)
    populate(dev)
    dev.login()
    out = do_logout(ctl)
    assert out.done and not out.blockers.needs_confirm
    # final sync pushed everything first
    assert len(server.live("alice", "environment")) == 2        # E1 + Globals
    assert len(server.live("alice", "profile")) == 2
    # local is empty, including Globals and the active env
    assert local_names(dev) == ([], [])
    assert dev.em.globals == [] and dev.em.active_id is None and dev.em.globals_updated_at == 0
    # state reset, no tombstones, nothing pushed back, server data intact
    assert not dev.state.logged_in and dev.state.username == "" and dev.state.last_account == ""
    assert dev.state.cursor == 0 and dev.state.tombstones == [] and dev.state.known == {"profile": {}, "environment": {}}
    assert dev.sm.status.phase == SyncPhase.LOGGED_OUT
    assert len(server.live("alice", "profile")) == 2 and not server.tombstones("alice", "profile")
    assert wiped == [1]
    # persisted on disk too
    assert Device(dev.dir.parent, server, "dev").profile_ids() == set()
    # login again downloads it back
    dev.login(); dev.sm.sync_now()
    assert local_names(dev)[0] == ["P1", "P2"] and [e.name for e in dev.em.envs] == ["E1"]
    assert [v.key for v in dev.em.globals] == ["g"]


def test_logout_failed_final_sync_needs_confirm_and_cancel_keeps_data(server, dev):
    ctl = SyncUiController(dev.sm, inline)
    populate(dev)
    dev.login()
    server.down = True
    before = local_names(dev)
    out = do_logout(ctl)
    assert not out.done and out.blockers.needs_confirm and out.blockers.sync_error
    assert out.blockers.unsynced >= 3
    assert local_names(dev) == before and dev.state.logged_in and dev.em.globals       # untouched
    assert logout_blockers_text(out.blockers).startswith(
        "Ada perubahan yang belum tersinkron dan akan hilang. Tetap logout dan hapus data lokal?")


def test_logout_confirmed_wipes_even_offline_without_tombstones(server, dev):
    ctl = SyncUiController(dev.sm, inline)
    populate(dev)
    dev.login()
    server.down = True
    out = do_logout(ctl, force=True)
    assert out.done
    assert local_names(dev) == ([], []) and not dev.state.logged_in
    assert dev.state.tombstones == [] and dev.state.last_account == ""
    server.down = False
    assert server.live("alice", "profile") == {}      # never pushed, never deleted remotely


def test_logout_skipped_large_item_needs_confirm(server, dev):
    ctl = SyncUiController(dev.sm, inline)
    dev.pm.save_profile(mk_profile("Huge", body_content="x" * 300_000))
    dev.pm.save_profile(mk_profile("Small"))
    dev.login()
    out = do_logout(ctl)
    assert not out.done and out.blockers.skipped_large == ("Huge",)
    assert "Huge" in logout_blockers_text(out.blockers)
    assert sorted(p.name for p in dev.pm.load_all_profiles()) == ["Huge", "Small"]


def test_logout_unsaved_edit_needs_confirm_even_when_synced(server, dev):
    ctl = SyncUiController(dev.sm, inline)
    populate(dev)
    dev.login()
    out = do_logout(ctl, unsaved_edit=True)
    assert not out.done and out.blockers.unsaved_edit and not out.blockers.sync_error
    assert "belum disimpan" in logout_blockers_text(out.blockers)
    assert dev.state.logged_in and len(dev.pm.load_all_profiles()) == 2
    assert do_logout(ctl, unsaved_edit=True, force=True).done
    assert local_names(dev) == ([], [])


def test_logout_text_mentions_wipe_not_keep():
    text = logout_intro_text("alice")
    assert "dihapus dari perangkat ini" in text and "aman di server" in text and "mengunduhnya kembali" in text
    assert "TIDAK dihapus" not in text and "digabung" not in text


def test_logout_preserves_non_data_settings_files(server, dev, tmp_path):
    settings = dev.dir / "settings.json"
    settings.write_text('{"theme": "dark", "sync_server_url": "https://x"}')
    ctl = SyncUiController(dev.sm, inline)
    populate(dev); dev.login()
    assert do_logout(ctl).done
    assert settings.read_text() == '{"theme": "dark", "sync_server_url": "https://x"}'
    assert dev.state.server_url == URL     # server URL kept for the next login


# ------------------------------------------------------------ AUTH_REQUIRED / account switch

def expire_session(server, dev):
    server.revoke_refresh_tokens(); server.expire_access_tokens()
    with pytest.raises(Exception):
        dev.sm.sync_now()
    assert dev.sm.status.phase == SyncPhase.AUTH_REQUIRED


def test_auth_required_keeps_local_data_and_same_account_relogin_merges(server, dev):
    ctl = SyncUiController(dev.sm, inline)
    populate(dev); dev.login(); dev.sm.sync_now()
    expire_session(server, dev)
    assert len(dev.pm.load_all_profiles()) == 2 and dev.state.last_account == "alice"
    dev.pm.save_profile(mk_profile("Offline edit"))
    assert do_login(ctl, "alice", PW)["done"] == (True, "")
    dev.sm.sync_now()
    assert len(dev.pm.load_all_profiles()) == 3
    assert len(server.live("alice", "profile")) == 3


def test_different_account_after_auth_required_needs_confirm_cancel_leaks_nothing(server, dev):
    ctl = SyncUiController(dev.sm, inline)
    populate(dev); dev.login(); dev.sm.sync_now()
    expire_session(server, dev)
    before_state = open(dev.state._path).read()
    server.requests.clear()
    res = do_login(ctl, "bob", PW_B)
    assert res["switch"] == ("alice", "bob") and "done" not in res
    # validated on the server but nothing stored and nothing synced yet
    assert not dev.state.logged_in and dev.state.username == "alice"
    assert ("POST", "/sync/push") not in server.requests and ("GET", "/sync/pull") not in server.requests
    ok, msg = finish(ctl, ctl.cancel_switch_async)
    assert ok is False and "dibatalkan" in msg
    assert open(dev.state._path).read() == before_state          # token of bob never stored
    assert len(dev.pm.load_all_profiles()) == 2 and dev.em.globals     # alice data intact
    assert server.live("bob", "profile") == {}
    assert "bob" not in server.refresh.values()                   # bob's unused token revoked
    assert ("POST", "/sync/push") not in server.requests


def test_different_account_confirmed_wipes_then_pulls_only_new_account(server, dev):
    ctl = SyncUiController(dev.sm, inline)
    wiped = []
    dev.sm.on_wiped = lambda: wiped.append(1)
    bp = mk_profile("bob-profile")
    from app.core import sync_mapping as m
    server.seed("bob", "profile", bp.id, bp.collection, m.profile_payload(bp), m.profile_ts(bp))
    populate(dev); dev.login(); dev.sm.sync_now()
    alice_profiles = set(server.live("alice", "profile"))
    expire_session(server, dev)
    dev.pm.save_profile(mk_profile("alice-unsynced"))
    res = do_login(ctl, "bob", PW_B)
    assert "switch" in res
    ok, msg = finish(ctl, ctl.confirm_switch_async)
    assert ok and msg == ""
    assert wiped == [1]
    assert dev.state.username == "bob" and dev.state.last_account == "bob" and dev.state.logged_in
    assert local_names(dev) == ([], [])
    dev.sm.sync_now()
    assert dev.profile_ids() == {bp.id}
    # nothing of alice reached bob; alice's server data untouched
    assert set(server.live("bob", "profile")) == {bp.id} and server.live("bob", "environment") == {}
    assert set(server.live("alice", "profile")) == alice_profiles
    assert not server.tombstones("alice", "profile") and not server.tombstones("bob", "profile")


def test_different_account_without_local_data_logs_in_directly(server, dev):
    ctl = SyncUiController(dev.sm, inline)
    dev.login(); dev.sm.sync_now()
    expire_session(server, dev)
    assert do_login(ctl, "bob", PW_B)["done"] == (True, "")
    assert dev.state.username == "bob"


def test_first_login_with_local_data_and_empty_state_still_merges(server, dev):
    ctl = SyncUiController(dev.sm, inline)
    assert dev.state.last_account == ""
    populate(dev)
    assert do_login(ctl, "bob", PW_B)["done"] == (True, "")
    dev.sm.sync_now()
    assert len(server.live("bob", "profile")) == 2 and len(dev.pm.load_all_profiles()) == 2


def test_switch_without_handler_cancels(server, dev):
    ctl = SyncUiController(dev.sm, inline)
    populate(dev); dev.login(); dev.sm.sync_now()
    expire_session(server, dev)
    got, done = [], threading.Event()
    ctl.login_async("bob", PW_B, URL, lambda ok, msg: (got.append((ok, msg)), done.set()))
    assert done.wait(5) and got[0][0] is False
    assert not dev.state.logged_in and len(dev.pm.load_all_profiles()) == 2


def test_last_account_persisted_and_legacy_state_falls_back_to_username(tmp_path):
    path = str(tmp_path / "s.json")
    st = SyncState(path)
    st.begin_session(URL, "alice", "rt")
    st.set_refresh_token("")
    assert SyncState(path).last_account == "alice"
    import json
    d = json.load(open(path)); d.pop("last_account"); json.dump(d, open(path, "w"))
    assert SyncState(path).last_account == "alice"
    st.end_session()
    assert SyncState(path).last_account == ""


def test_account_switch_text():
    t = account_switch_text("alice", "bob")
    assert t == ("Data lokal milik akun alice. Login sebagai bob akan menghapus data lokal itu "
                 "(belum tersinkron bisa hilang). Lanjut?")
    assert "belum disimpan" in account_switch_text("alice", "bob", unsaved_edit=True)


def test_logout_blockers_flags():
    assert not LogoutBlockers().needs_confirm
    assert LogoutBlockers(unsaved_edit=True).needs_confirm
    assert LogoutBlockers(sync_error="x").needs_confirm
