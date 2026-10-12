def test_register_resolve_and_conflict():
    from red_navigator.actions import registry
    registry.clear()
    registry.register("demo.a", "Demo A", "z", lambda: None)
    registry.register("demo.b", "Demo B", None, lambda: None)
    assert registry.resolve("z")["id"] == "demo.a"
    result = registry.set_binding("demo.b", "z")
    assert result["ok"] is False and result["conflict"] == "demo.a"
    assert registry.resolve("z")["id"] == "demo.a"
    registry.clear()


def test_bindings_persist_and_reload():
    from red_navigator.actions import registry
    registry.clear()
    registry.register("demo.a", "Demo A", "z", lambda: None)
    registry.set_binding("demo.a", "x")
    registry.clear(keep_store=True)
    registry.register("demo.a", "Demo A", "z", lambda: None)
    registry.load_bindings()
    assert registry.resolve("x")["id"] == "demo.a"
    registry.clear()
