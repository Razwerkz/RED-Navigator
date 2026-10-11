def test_fanout_reaches_plugin_and_overlay():
    from red_navigator.runtime import fanout
    calls = []
    class FakePlugin:
        def journal_entry(self, cmdr, is_beta, system, station, entry, state):
            calls.append(entry["event"])
    fanout.register_test_plugin(FakePlugin())
    try:
        fanout.journal_entry({"event": "FSDJump", "StarSystem": "Sol"}, {"cmdr": "CMDR", "is_beta": False, "system": "Sol", "station": ""})
    finally:
        fanout.clear_test_plugins()
    assert calls == ["FSDJump"]

def test_plugin_exception_never_escapes_fanout():
    from red_navigator.runtime import fanout
    class Boom:
        def journal_entry(self, *a, **k):
            raise RuntimeError("boom")
    fanout.register_test_plugin(Boom())
    try:
        fanout.journal_entry({"event": "Docked"}, {})
    finally:
        fanout.clear_test_plugins()
