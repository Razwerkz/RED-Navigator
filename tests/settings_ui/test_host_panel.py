import pytest


@pytest.fixture(autouse=True)
def _clean_state():
    from red_navigator.edmc_compat import config_store
    from red_navigator.settings_ui import host_panel
    config_store.clear()
    host_panel.clear()
    yield
    host_panel.clear()
    config_store.clear()


def test_mount_registers_panel_listed_by_plugin_start3_name(tmp_path):
    from red_navigator.edmc_compat import loader
    from red_navigator.settings_ui import host_panel
    plugin_dir = tmp_path / "myplugin"
    plugin_dir.mkdir()
    (plugin_dir / "load.py").write_text(
        "def plugin_start3(plugin_dir):\n"
        "    return 'My Plugin'\n"
        "def plugin_prefs(parent, cmdr, is_beta):\n"
        "    return parent\n"
        "def prefs_changed(cmdr, is_beta):\n"
        "    pass\n",
        encoding="utf-8",
    )
    plugin = loader.load_plugin(str(plugin_dir))
    name = host_panel.mount_loaded(plugin, str(plugin_dir))
    assert name == "My Plugin"
    names = [p["name"] for p in host_panel.list_panels()]
    assert names == ["My Plugin"]
    panel = host_panel.get_panel("My Plugin")
    assert panel["has_prefs"] is True
    assert panel["has_prefs_changed"] is True


def test_mount_for_plugin_without_hooks_still_lists_panel():
    from red_navigator.settings_ui import host_panel
    host_panel.mount_for_plugin("Hookless")
    panel = host_panel.get_panel("Hookless")
    assert panel is not None
    assert panel["name"] == "Hookless"
    assert panel["has_prefs"] is False
    assert panel["has_prefs_changed"] is False


def test_mount_is_idempotent():
    from red_navigator.settings_ui import host_panel
    host_panel.mount_for_plugin("Dup")
    host_panel.mount_for_plugin("Dup")
    assert [p["name"] for p in host_panel.list_panels()] == ["Dup"]


def test_save_panel_values_persists_and_notifies_plugin():
    from red_navigator.settings_ui import host_panel
    seen = {}

    class FakePlugin:
        prefs_spec = {"fields": [{"key": "level", "type": "number",
                                  "default": 1}]}

        def prefs_changed(self, cmdr, is_beta):
            seen["notified"] = (cmdr, is_beta)

    host_panel.register_plugin("Fake", FakePlugin())
    host_panel.mount_for_plugin("Fake")
    host_panel.save_panel_values("Fake", {"level": 5, "extra": "kept"})
    from red_navigator.edmc_compat import config_store
    assert config_store.get_str("level", plugin="Fake") == "5"
    assert config_store.get_str("extra", plugin="Fake") == "kept"
    assert seen["notified"] == ("", False)


def test_failing_prefs_changed_never_breaks_save():
    from red_navigator.settings_ui import host_panel

    class BadPlugin:
        def prefs_changed(self, cmdr, is_beta):
            raise RuntimeError("boom")

    host_panel.register_plugin("Bad", BadPlugin())
    host_panel.mount_for_plugin("Bad")
    host_panel.save_panel_values("Bad", {"k": "v"})  # must not raise
    from red_navigator.edmc_compat import config_store
    assert config_store.get_str("k", plugin="Bad") == "v"


def test_settings_sections_exposes_hook_path_and_panels():
    from red_navigator.settings_ui import host_panel
    host_panel.mount_for_plugin("Alpha")
    sections = host_panel.settings_sections()
    assert sections["hook"] == host_panel.NOVA_SETTINGS_HOOK
    assert sections["hook"] == "ed_monitor.ui.app:NovaApp.on_key[s]->SettingsScreen"
    assert "SettingsScreen" in sections["hook"]
    assert [p["name"] for p in sections["panels"]] == ["Alpha"]


def test_spec_less_plugin_with_prefs_renders_placeholder():
    from red_navigator.settings_ui import host_panel

    class RawTkPlugin:
        def plugin_prefs(self, parent, cmdr, is_beta):
            return parent

    host_panel.register_plugin("RawTk", RawTkPlugin())
    host_panel.mount_for_plugin("RawTk")
    panel = host_panel.get_panel("RawTk")
    assert panel["has_prefs"] is True
    assert len(panel["fields"]) == 1
    field = panel["fields"][0]
    assert field.get("placeholder") is True
    assert "RawTk" in field["hint"]
    assert "prefs_spec" in field["hint"]
    assert "RawTk" in field["value"]


def test_placeholder_is_never_persisted_and_wipes_nothing():
    from red_navigator.edmc_compat import config_store
    from red_navigator.settings_ui import host_panel

    class RawTkPlugin:
        def plugin_prefs(self, parent, cmdr, is_beta):
            return parent

    host_panel.register_plugin("RawTk", RawTkPlugin())
    host_panel.mount_for_plugin("RawTk")
    config_store.set("real_key", "keep", plugin="RawTk")
    placeholder_key = host_panel.get_panel("RawTk")["fields"][0]["key"]
    host_panel.save_panel_values("RawTk", {placeholder_key: "junk", "other": "v"})
    assert config_store.get_str(placeholder_key, plugin="RawTk") is None
    assert config_store.get_str("other", plugin="RawTk") == "v"
    assert config_store.get_str("real_key", plugin="RawTk") == "keep"
    # Placeholder survives the post-save refresh (still no hollow panel).
    assert host_panel.get_panel("RawTk")["fields"][0].get("placeholder") is True


def test_plugin_without_prefs_and_without_spec_has_no_fields():
    from red_navigator.settings_ui import host_panel
    host_panel.mount_for_plugin("Bare")
    panel = host_panel.get_panel("Bare")
    assert panel["has_prefs"] is False
    assert panel["fields"] == []
