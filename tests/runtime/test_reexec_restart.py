"""Fix A: launcher-aware restart (reexec_argv, selection, stop_active)."""

import sys


def test_reexec_argv_shape(monkeypatch):
    from red_navigator import app

    monkeypatch.setattr(
        sys, "argv", ["app.py", "--no-overlay", "--plugin-dir", "/tmp/p"]
    )
    argv = app.reexec_argv()
    assert argv[0] == sys.executable
    assert argv[1:3] == ["-m", "red_navigator.app"]
    assert argv[3:] == ["--no-overlay", "--plugin-dir", "/tmp/p"]
    assert isinstance(argv, list)


def test_restart_selection_prefers_red(monkeypatch):
    import ed_monitor.__main__ as nova_main

    monkeypatch.setattr(sys, "argv", ["/path/to/app.py", "--no-overlay"])
    argv = nova_main._restart_exec_argv()
    assert argv[0] == sys.executable
    assert argv[1:3] == ["-m", "red_navigator.app"]
    assert argv[3:] == ["--no-overlay"]


def test_restart_selection_legacy_when_red_absent(monkeypatch):
    import red_navigator

    import ed_monitor.__main__ as nova_main

    monkeypatch.setitem(sys.modules, "red_navigator.app", None)
    monkeypatch.delattr(red_navigator, "app", raising=False)
    # __main__.py launch keeps the legacy -m ed_monitor form.
    monkeypatch.setattr(sys, "argv", ["/x/ed_monitor/__main__.py"])
    assert nova_main._restart_exec_argv() == [sys.executable, "-m", "ed_monitor"]
    # Entry-point launch keeps the legacy direct-exec form.
    monkeypatch.setattr(sys, "argv", ["/usr/bin/nova", "--foo"])
    assert nova_main._restart_exec_argv() == ["/usr/bin/nova", "--foo"]


def test_stop_active_empty_false():
    from red_navigator.runtime import session

    assert session.stop_active() is False


def test_stop_active_stops_started_session(tmp_path):
    from red_navigator.edmc_compat import config_store
    from red_navigator.runtime import fanout, session

    old_path = config_store._store_path if hasattr(config_store, "_store_path") else None
    sess = session.start(str(tmp_path / "plugins"), str(tmp_path / "red"), overlay=False)
    try:
        assert sess.is_running() is True
        assert session.stop_active() is True
        assert sess.is_running() is False
        assert session.stop_active() is False
    finally:
        try:
            session.stop(sess)
        except Exception:
            pass
        fanout.set_enabled(False)
        try:
            config_store.set_store_path(old_path)
        except Exception:
            pass
        config_store.clear()
