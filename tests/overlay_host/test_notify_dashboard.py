"""Fix B: overlay dashboard forwarding (host.notify_dashboard + fanout)."""

import pytest


@pytest.fixture
def _host_stopped():
    from red_navigator.overlay_host import host

    host.stop()
    yield
    host.stop()


@pytest.fixture
def _fanout_clean():
    from red_navigator.runtime import fanout

    fanout.set_event_sink(None)
    fanout.clear_test_plugins()
    fanout.clear_session_plugins()
    yield
    fanout.set_event_sink(None)
    fanout.clear_test_plugins()
    fanout.clear_session_plugins()


def _write_plugin(directory, body):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "load.py").write_text(body, encoding="utf-8")
    return str(directory)


DASHBOARD_PLUGIN = (
    "received = []\n"
    "def plugin_start3(plugin_dir):\n"
    "    return 'Dash'\n"
    "def dashboard_entry(cmdr, is_beta, data):\n"
    "    received.append((cmdr, dict(data)))\n"
)

RAISING_PLUGIN = (
    "def plugin_start3(plugin_dir):\n"
    "    return 'Raising'\n"
    "def dashboard_entry(cmdr, is_beta, data):\n"
    "    raise RuntimeError('boom')\n"
)

TRANSPORT_PLUGIN = (
    "received = []\n"
    "class _B:\n"
    "    port = 45711\n"
    "    def publish(self, payload):\n"
    "        received.append(payload)\n"
    "broadcaster = _B()\n"
    "def plugin_start3(plugin_dir):\n"
    "    return 'Fake'\n"
    "def journal_entry(cmdr, is_beta, system, station, entry, state):\n"
    "    received.append(('journal', entry.get('event')))\n"
)


def test_notify_dashboard_delivers_cmdr_and_data(tmp_path, _host_stopped):
    from red_navigator.overlay_host import host

    plugin_dir = _write_plugin(tmp_path / "dash", DASHBOARD_PLUGIN)
    host.start(plugin_dir)
    data = {"Flags": 123, "Pips": [4, 4, 4]}
    assert host.notify_dashboard(dict(data), "CMDR1") is True
    received = host._plugin.received
    assert received == [("CMDR1", data)]


def test_notify_dashboard_raising_contained_false(tmp_path, _host_stopped):
    from red_navigator.overlay_host import host

    plugin_dir = _write_plugin(tmp_path / "raising", RAISING_PLUGIN)
    host.start(plugin_dir)
    assert host.notify_dashboard({"Flags": 1}, "CMDR1") is False


def test_notify_dashboard_false_without_plugin(_host_stopped):
    from red_navigator.overlay_host import host

    assert host.is_running() is False
    assert host.notify_dashboard({"Flags": 1}, "CMDR1") is False


def test_fanout_dashboard_reaches_overlay(tmp_path, _host_stopped, _fanout_clean):
    from red_navigator.overlay_host import host
    from red_navigator.runtime import fanout

    plugin_dir = _write_plugin(tmp_path / "dash", DASHBOARD_PLUGIN)
    host.start(plugin_dir)
    fanout.journal_entry({"event": "LoadGame", "Commander": "CMDR2"}, {"cmdr": "CMDR2"})
    host._plugin.received.clear()
    fanout.dashboard_entry({"Flags": 7})
    assert host._plugin.received == [("CMDR2", {"Flags": 7})]


def test_publish_journal_behavior_unchanged(tmp_path, _host_stopped):
    from red_navigator.overlay_host import host, mirror

    plugin_dir = _write_plugin(tmp_path / "transport", TRANSPORT_PLUGIN)
    assert host.start(plugin_dir) == 45711
    payload = {"event": "FSDJump", "system": "Sol"}
    assert host.publish(payload) is True
    assert "Sol" in mirror.to_textual(payload)
