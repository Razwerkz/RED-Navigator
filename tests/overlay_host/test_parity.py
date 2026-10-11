import pytest


def test_overlay_publishes_and_mirrors():
    from red_navigator.overlay_host import mirror
    text = mirror.to_textual({"event": "FSDJump", "system": "Sol"})
    assert "Sol" in text

def test_port_single_owner(tmp_path):
    from red_navigator.overlay_host import port_owner
    assert port_owner.claim(str(tmp_path), 50123) is True


@pytest.fixture(autouse=True)
def _host_stopped():
    from red_navigator.overlay_host import host
    host.stop()
    yield
    host.stop()


def _write_plugin(directory, body):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "load.py").write_text(body, encoding="utf-8")
    return str(directory)


TRANSPORTLESS_PLUGIN = (
    "def plugin_start3(plugin_dir):\n"
    "    return 'NoTransport'\n"
    "def journal_entry(cmdr, is_beta, system, station, entry, state):\n"
    "    pass\n"
)


def test_discover_port_survives_corrupt_port_json(tmp_path):
    from red_navigator.overlay_host import host
    # Truthy non-numeric values: int() raises TypeError, which must be
    # contained (the old code only caught OSError/ValueError/AttributeError
    # and crashed start() before port_owner.claim could clean the file).
    (tmp_path / "port.json").write_text('{"port": ["a"]}', encoding="utf-8")
    assert host._discover_port(object(), tmp_path) == 0
    (tmp_path / "port.json").write_text('{"port": {"x": 1}}', encoding="utf-8")
    assert host._discover_port(object(), tmp_path) == 0
    (tmp_path / "port.json").write_text('[1, 2]', encoding="utf-8")
    assert host._discover_port(object(), tmp_path) == 0
    (tmp_path / "port.json").write_text('not json', encoding="utf-8")
    assert host._discover_port(object(), tmp_path) == 0


def test_start_returns_zero_without_advertising_unbound_port(tmp_path):
    from pathlib import Path
    from red_navigator.overlay_host import host
    plugin_dir = _write_plugin(tmp_path / "notransport", TRANSPORTLESS_PLUGIN)
    assert host.start(plugin_dir) == 0
    assert not (Path(plugin_dir) / "port.json").exists()


def test_publish_false_without_transport(tmp_path):
    from red_navigator.overlay_host import host, mirror
    plugin_dir = _write_plugin(tmp_path / "notransport", TRANSPORTLESS_PLUGIN)
    assert host.start(plugin_dir) == 0
    payload = {"event": "FSDJump", "system": "Sol"}
    assert host.publish(payload) is False
    assert "Sol" in mirror.to_textual(payload)


def test_publish_true_with_broadcaster(tmp_path):
    from red_navigator.overlay_host import host
    body = (
        "received = []\n"
        "class _B:\n"
        "    port = 45681\n"
        "    def publish(self, payload):\n"
        "        received.append(payload)\n"
        "broadcaster = _B()\n"
        "def plugin_start3(plugin_dir):\n"
        "    return 'Fake'\n"
    )
    plugin_dir = _write_plugin(tmp_path / "withtransport", body)
    assert host.start(plugin_dir) == 45681
    assert host.publish({"event": "FSDJump", "system": "Sol"}) is True


def test_start_routes_through_loader_once(tmp_path, monkeypatch):
    from red_navigator.edmc_compat import loader
    from red_navigator.overlay_host import host
    calls = []
    real_start3 = loader.call_plugin_start3

    def counting(plugin, plugin_dir):
        calls.append(plugin_dir)
        return real_start3(plugin, plugin_dir)

    monkeypatch.setattr(loader, "call_plugin_start3", counting)
    hooked = _write_plugin(
        tmp_path / "hooked",
        "def plugin_start3(plugin_dir):\n    return 'Hooked'\n",
    )
    assert host.start(hooked) == 0
    host.stop()
    hookless = _write_plugin(tmp_path / "hookless", "x = 1\n")
    assert host.start(hookless) == 0
    assert calls == [hooked, hookless]
