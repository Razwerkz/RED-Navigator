import pytest


@pytest.fixture(autouse=True)
def _clean_config_store():
    from red_navigator.edmc_compat import config_store
    config_store.clear()
    yield
    config_store.clear()


def test_new_plugin_keys_survive_update():
    from red_navigator.settings_ui import forms
    spec = {"fields": [{"key": "opt_a", "type": "bool", "default": False}]}
    rendered = forms.render(spec)
    assert any(f["key"] == "opt_a" for f in rendered)
    forms.apply({"opt_a": True, "opt_new": "x"})


def test_apply_preserves_unmentioned_keys():
    from red_navigator.edmc_compat import config_store
    from red_navigator.settings_ui import forms
    config_store.set("opt_keep", "keepme")
    forms.apply({"opt_a": True, "opt_new": "x"})
    assert config_store.get_str("opt_keep") == "keepme"
    assert config_store.get_str("opt_new") == "x"
    assert config_store.get_str("opt_a") == "True"


def test_render_all_supported_types():
    from red_navigator.settings_ui import forms
    spec = {"fields": [
        {"key": "b", "type": "bool", "default": False},
        {"key": "t", "type": "text", "default": "hi"},
        {"key": "n", "type": "number", "default": 3},
        {"key": "f", "type": "file", "default": "/tmp/x"},
        {"key": "d", "type": "dropdown", "default": "a",
         "options": ["a", "b"]},
    ]}
    rendered = forms.render(spec)
    assert [f["key"] for f in rendered] == ["b", "t", "n", "f", "d"]
    assert rendered[0]["value"] is False
    assert rendered[3]["type"] == "file"
    assert rendered[4]["options"] == ["a", "b"]


def test_unknown_widget_falls_back_to_text_without_crashing():
    from red_navigator.settings_ui import forms
    spec = {"fields": [
        {"key": "weird", "type": "tkinter.Canvas", "default": "on"},
        {"key": "custom", "type": "MyFancySlider", "default": 3},
        "not-a-dict",
        None,
    ]}
    rendered = forms.render(spec)
    by_key = {f["key"]: f for f in rendered}
    assert by_key["weird"]["type"] == "text"
    assert by_key["weird"].get("fallback") is True
    assert isinstance(by_key["weird"]["value"], str)
    assert by_key["custom"]["type"] == "text"
    assert by_key["custom"].get("fallback") is True
    # Known tkinter widget names keep their semantics, not fallback.
    check = forms.render({"fields": [
        {"key": "flag", "type": "tkinter.Checkbutton", "default": False}]})
    assert check[0]["type"] == "bool"
    assert "fallback" not in check[0]
    # Fields without a usable key are skipped, never crash.
    assert "not-a-dict" not in by_key


def test_render_prefers_stored_values_over_defaults():
    from red_navigator.edmc_compat import config_store
    from red_navigator.settings_ui import forms
    config_store.set("opt_a", "True")
    config_store.set("count", "7")
    config_store.set("mode", "b")
    spec = {"fields": [
        {"key": "opt_a", "type": "bool", "default": False},
        {"key": "count", "type": "number", "default": 0},
        {"key": "mode", "type": "dropdown", "default": "a",
         "options": ["a", "b"]},
    ]}
    rendered = {f["key"]: f for f in forms.render(spec)}
    assert rendered["opt_a"]["value"] is True
    assert rendered["count"]["value"] == 7
    assert rendered["mode"]["value"] == "b"


def test_namespaced_writes_do_not_leak_across_plugins():
    from red_navigator.edmc_compat import config_store
    from red_navigator.settings_ui import forms
    with config_store.scoped("plugin-a"):
        forms.apply({"shared": "aaa"})
    with config_store.scoped("plugin-b"):
        forms.apply({"shared": "bbb"})
    assert config_store.get_str("shared", plugin="plugin-a") == "aaa"
    assert config_store.get_str("shared", plugin="plugin-b") == "bbb"
