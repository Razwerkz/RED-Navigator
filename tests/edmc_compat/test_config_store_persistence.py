import pytest


@pytest.fixture(autouse=True)
def _clean_config_store():
    from red_navigator.edmc_compat import config_store
    config_store.clear()
    config_store.set_store_path(None)
    yield
    config_store.clear()
    config_store.set_store_path(None)


def test_store_survives_restart_via_backing_file(tmp_path):
    from red_navigator.edmc_compat import config_store
    backing = str(tmp_path / "red_config.json")
    config_store.set_store_path(backing)
    config_store.set("opt_a", "True", plugin="My Plugin")
    config_store.set("count", "7", plugin="My Plugin")
    # Simulate a restart: drop memory, reload from disk.
    config_store.clear()
    assert config_store.get_str("opt_a", plugin="My Plugin") is None
    assert config_store.load(backing) is True
    assert config_store.get_str("opt_a", plugin="My Plugin") == "True"
    assert config_store.get_str("count", plugin="My Plugin") == "7"


def test_load_missing_file_is_not_an_error(tmp_path):
    from red_navigator.edmc_compat import config_store
    assert config_store.load(str(tmp_path / "nope.json")) is False
    config_store.set("k", "v")
    assert config_store.get_str("k") == "v"


def test_no_autosave_without_configured_path(tmp_path):
    from red_navigator.edmc_compat import config_store
    assert config_store.get_store_path() is None
    config_store.set("k", "v")  # must not raise, must not write anywhere
    assert list(tmp_path.iterdir()) == []
