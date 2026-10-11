def test_settings_sections_expose_red_panels():
    from red_navigator.settings_ui import host_panel
    from red_navigator.runtime import settings_bridge
    host_panel.clear()
    host_panel.register_plugin("Demo", None)
    sections = settings_bridge.red_sections()
    assert any("Demo" in s["title"] for s in sections)
    host_panel.clear()

def test_settings_save_isolated_per_plugin():
    from red_navigator.runtime import settings_bridge
    from red_navigator.settings_ui import host_panel
    host_panel.clear()
    host_panel.register_plugin(" risky ", None)
    settings_bridge.save_red_section({" risky ": {"k": "v"}})
    assert host_panel.get_panel(" risky ") is not None
    host_panel.clear()
