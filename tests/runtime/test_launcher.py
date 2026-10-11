def test_no_overlay_flag_parses():
    from red_navigator import app
    opts = app.parse_args(["--no-overlay"])
    assert opts.overlay is False


def test_import_failure_asks_fresh_or_retry(capsys):
    from red_navigator import app
    choice = app.resolve_store("/tmp/red-empty-x", "/tmp/red-missing-src-y", answer="fresh")
    assert choice in ("fresh", "retry")


def test_overlay_defaults_on():
    from red_navigator import app
    opts = app.parse_args([])
    assert opts.overlay is True


def test_plugin_and_store_dir_overrides_parse():
    from red_navigator import app
    opts = app.parse_args(["--plugin-dir", "/tmp/p", "--store-dir", "/tmp/s"])
    assert opts.plugin_dir == "/tmp/p"
    assert opts.store_dir == "/tmp/s"
    assert opts.overlay is True


def test_resolve_store_retry_answer():
    from red_navigator import app
    assert app.resolve_store("/tmp/red-empty-x", "/tmp/red-missing-src-y", answer="retry") == "retry"


def test_resolve_store_success_proceeds(tmp_path):
    from red_navigator import app
    from red_navigator.edmc_compat import config_store
    config_store.clear()
    try:
        src = tmp_path / "edmc"
        src.mkdir()
        (src / "settings.ini").write_text("opt=1\n")
        dest = tmp_path / "red"
        assert app.resolve_store(str(dest), str(src)) == "fresh"
        assert (dest / "settings.ini").read_text() == "opt=1\n"
    finally:
        config_store.clear()


def test_event_sink_splits_multiline_into_system_events():
    from red_navigator import app
    from ed_monitor.state import EventCategory
    import threading

    seen = []

    class FakeState:
        def push_event(self, ev):
            seen.append(ev)

    sink = app.make_event_sink(FakeState(), threading.RLock())
    sink("line one\nline two\n")
    assert [ev.message for ev in seen] == ["line one", "line two"]
    assert all(ev.category is EventCategory.System for ev in seen)


def test_main_starts_nova_and_stops_session(monkeypatch, tmp_path):
    import sys
    import types
    from red_navigator import app
    from red_navigator.runtime import session

    calls = {}

    def fake_start(plugin_dir, red_store, *, overlay=True):
        calls["start"] = (plugin_dir, red_store, overlay)
        return session.Session(plugin_dir, red_store, overlay=overlay)

    def fake_stop(s):
        calls["stop"] = s

    stub = types.ModuleType("ed_monitor.__main__")

    class StubApp:
        def __init__(self, state, lock, *args, **kwargs):
            calls["nova_state"] = state

    def fake_nova_main():
        calls["nova_ran"] = True
        stub.NOVAApp("state", "lock")

    stub.NOVAApp = StubApp
    stub.main = fake_nova_main

    monkeypatch.setitem(sys.modules, "ed_monitor.__main__", stub)
    monkeypatch.setattr(session, "start", fake_start)
    monkeypatch.setattr(session, "stop", fake_stop)
    monkeypatch.setattr(app, "resolve_store", lambda *a, **k: "fresh")

    plugin_dir = str(tmp_path / "plugins")
    red_store = str(tmp_path / "red")
    code = app.main(["--no-overlay", "--plugin-dir", plugin_dir, "--store-dir", red_store])

    assert code == 0
    assert calls["start"] == (plugin_dir, red_store, False)
    assert calls["nova_ran"] is True
    assert calls["stop"] is not None
    assert calls["stop"].plugin_dir == plugin_dir


def test_mirror_sink_wires_into_app_state_under_lock():
    import threading
    from ed_monitor.state import AppState, EventCategory
    from red_navigator import app
    from red_navigator.runtime import fanout

    state = AppState()
    lock = threading.RLock()
    before = state.events_version
    fanout.set_event_sink(app.make_event_sink(state, lock))
    try:
        fanout.journal_entry({"event": "FSDJump", "StarSystem": "Sol"}, {"system": "Sol"})
    finally:
        fanout.set_event_sink(None)
    assert state.events_version > before
    assert any(
        ev.category is EventCategory.System and "Sol" in ev.message
        for ev in state.events
    )
