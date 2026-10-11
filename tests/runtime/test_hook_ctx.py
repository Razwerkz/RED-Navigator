"""Regression tests for post-handle journal fan-out ctx (review fix)."""

import json
import queue
import threading
import time

import pytest

import ed_monitor.journal as J
from ed_monitor.db import Database
from ed_monitor.state import AppState
from red_navigator.runtime import fanout


@pytest.fixture
def red_env():
    yield
    fanout.set_enabled(False)
    fanout.clear_session_plugins()
    fanout.clear_test_plugins()


def _run_follow(tmp_path, lines):
    """Tail ``lines`` through a real _follow thread; return plugin sightings."""
    J._latest_cache_time = 0.0
    J._latest_cache_path = None
    jdir = tmp_path / "j"
    jdir.mkdir(exist_ok=True)
    jf = jdir / "Journal.2026-10-11T000000.01.log"
    jf.write_text("")
    db = Database(str(tmp_path / "nova.db"))
    state = AppState()
    lock = threading.RLock()

    seen = []

    class Probe:
        def journal_entry(self, cmdr, is_beta, system, station, entry, state):
            seen.append({
                "cmdr": cmdr, "system": system, "station": station,
                "event": entry.get("event"),
            })

    fanout.register_test_plugin(Probe())
    fanout.set_enabled(True)
    try:
        t = threading.Thread(
            target=J._follow,
            args=(jf, state, lock, queue.Queue(), db, jdir, None),
            kwargs={"start_offset": 0},
            daemon=True,
        )
        t.start()
        time.sleep(0.3)
        with open(jf, "a") as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")
        time.sleep(1.0)
        (jdir / "Journal.2026-10-11T000001.02.log").write_text("")
        t.join(timeout=15)
        assert not t.is_alive(), "follow thread should exit on newer journal file"
    finally:
        fanout.set_enabled(False)
        fanout.clear_test_plugins()
    return seen


def test_posthandle_ctx_carries_updated_commander(tmp_path, red_env):
    seen = _run_follow(tmp_path, [{
        "timestamp": "2026-10-11T00:00:01Z", "event": "LoadGame",
        "Commander": "NEWCMDR", "Ship": "CobraMkIII",
    }])
    assert [s["event"] for s in seen] == ["LoadGame"]
    assert seen[0]["cmdr"] == "NEWCMDR"


def test_posthandle_ctx_carries_postjump_system(tmp_path, red_env):
    seen = _run_follow(tmp_path, [{
        "timestamp": "2026-10-11T00:00:01Z", "event": "FSDJump",
        "StarSystem": "Sol", "JumpDist": 5.0,
    }])
    assert [s["event"] for s in seen] == ["FSDJump"]
    assert seen[0]["system"] == "Sol"


def test_fanout_survives_handler_exception(tmp_path, red_env, monkeypatch):
    def boom(effective, state, tts_q):
        raise RuntimeError("handler boom")
    monkeypatch.setattr(J, "handle", boom)
    seen = _run_follow(tmp_path, [{
        "timestamp": "2026-10-11T00:00:01Z", "event": "Docked",
        "StationName": "Daedalus",
    }])
    assert [s["event"] for s in seen] == ["Docked"]
