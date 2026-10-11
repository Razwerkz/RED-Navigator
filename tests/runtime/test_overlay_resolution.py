"""Regression tests for session overlay-dir resolution (review fix)."""

import pytest

from red_navigator.runtime import fanout, session


@pytest.fixture
def red_env():
    """Reset RED global state around each test."""
    yield
    from red_navigator.edmc_compat import config_store
    from red_navigator.settings_ui import host_panel
    fanout.set_enabled(False)
    fanout.clear_session_plugins()
    fanout.clear_test_plugins()
    host_panel.clear()
    config_store.set_store_path(None)
    config_store.clear()


def _write_plugin(path, name="Demo"):
    path.mkdir(parents=True, exist_ok=True)
    (path / "load.py").write_text(
        f"def plugin_start3(plugin_dir):\n    return {name!r}\n"
    )
    return str(path)


def test_resolve_accepts_plugin_dir_with_load_py(tmp_path):
    mine = _write_plugin(tmp_path / "overlay")
    assert session.resolve_overlay_dir(mine) == mine


def test_resolve_finds_nested_overlay_child(tmp_path):
    parent = tmp_path / "plugins"
    parent.mkdir()
    child = parent / "EDMCModernOverlay"
    _write_plugin(child, name="Overlay")
    _write_plugin(parent / "other", name="Other")
    assert session.resolve_overlay_dir(str(parent)) == str(child)


def test_resolve_returns_none_when_absent(tmp_path):
    parent = tmp_path / "plugins"
    _write_plugin(parent / "other", name="Other")
    assert session.resolve_overlay_dir(str(parent)) is None
    assert session.resolve_overlay_dir(str(tmp_path / "missing")) is None


def test_resolve_prefers_explicit_override(tmp_path):
    parent = tmp_path / "plugins"
    child = parent / "EDMCModernOverlay"
    _write_plugin(child, name="Overlay")
    custom = _write_plugin(tmp_path / "custom", name="Custom")
    assert session.resolve_overlay_dir(str(parent), override=custom) == custom


def test_start_hosts_resolved_child_and_excludes_it(tmp_path, monkeypatch, red_env):
    from red_navigator.overlay_host import host

    parent = tmp_path / "plugins"
    overlay_child = _write_plugin(parent / "EDMCModernOverlay", name="Overlay")
    _write_plugin(parent / "demo", name="Demo")
    started = []
    monkeypatch.setattr(host, "start", lambda d: started.append(d) or 12345)
    monkeypatch.setattr(host, "stop", lambda: None)

    sess = session.start(str(parent), str(tmp_path / "store"), overlay=True)
    try:
        assert started == [overlay_child]
        assert sess.overlay_dir == overlay_child
        assert sess.is_running() is True
        # Host-owned overlay is excluded from the session mount loop:
        # single plugin_start3 via host.start, no double dispatch.
        assert sess.plugin_names == ["Demo"]
    finally:
        session.stop(sess)


def test_start_prefers_explicit_overlay_dir(tmp_path, monkeypatch, red_env):
    from red_navigator.overlay_host import host

    parent = tmp_path / "plugins"
    _write_plugin(parent / "EDMCModernOverlay", name="Overlay")
    custom = _write_plugin(tmp_path / "custom", name="Custom")
    started = []
    monkeypatch.setattr(host, "start", lambda d: started.append(d) or 12345)
    monkeypatch.setattr(host, "stop", lambda: None)

    sess = session.start(
        str(parent), str(tmp_path / "store"), overlay=True, overlay_dir=custom
    )
    try:
        assert started == [custom]
        assert sess.overlay_dir == custom
    finally:
        session.stop(sess)


def test_start_without_overlay_dir_degrades_terminal_only(tmp_path, red_env):
    parent = tmp_path / "plugins"
    _write_plugin(parent / "demo", name="Demo")

    sess = session.start(str(parent), str(tmp_path / "store"), overlay=True)
    try:
        assert sess.is_running() is True
        assert sess.overlay_dir is None
        assert sess.plugin_names == ["Demo"]
    finally:
        session.stop(sess)
