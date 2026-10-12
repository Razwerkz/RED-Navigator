def test_menu_lists_and_applies_with_conflict():
    from red_navigator.actions import registry, menu
    registry.clear()
    registry.register("demo.a", "Demo A", "z", lambda: None)
    registry.register("demo.b", "Demo B", None, lambda: None)
    sections = menu.binding_sections()
    assert any(s["id"] == "demo.a" and s["key"] == "z" for s in sections)
    assert menu.apply_binding("demo.b", "z")["conflict"] == "demo.a"
    assert menu.apply_binding("demo.b", "x")["ok"] is True
    registry.clear()

def test_escape_cancels_capture():
    from red_navigator.actions import menu
    assert menu.capture_key("demo.a", "escape") == {"ok": False, "cancelled": True}
