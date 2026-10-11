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

def test_mutating_plugin_cannot_alter_caller_journal_dict():
    from red_navigator.runtime import fanout
    class Mutator:
        def journal_entry(self, cmdr, is_beta, system, station, entry, state):
            entry.pop("event", None)
            entry["injected"] = True
            state["polluted"] = True
    seen = []
    class Observer:
        def journal_entry(self, cmdr, is_beta, system, station, entry, state):
            seen.append((dict(entry), dict(state)))
    entry = {"event": "FSDJump", "StarSystem": "Sol"}
    state = {"k": "v"}
    snapshot = (dict(entry), dict(state))
    fanout.register_test_plugin(Mutator())
    fanout.register_test_plugin(Observer())
    try:
        fanout.journal_entry(entry, {"state": state})
    finally:
        fanout.clear_test_plugins()
    assert (entry, state) == snapshot
    assert seen == [snapshot]

def test_mutating_plugin_cannot_alter_caller_dashboard_dict():
    from red_navigator.runtime import fanout
    class Mutator:
        def dashboard_entry(self, cmdr, is_beta, entry):
            entry.pop("Flags", None)
            entry["injected"] = True
    seen = []
    class Observer:
        def dashboard_entry(self, cmdr, is_beta, entry):
            seen.append(dict(entry))
    data = {"Flags": 0, "Pips": [4, 4, 4]}
    snapshot = dict(data)
    fanout.register_test_plugin(Mutator())
    fanout.register_test_plugin(Observer())
    try:
        fanout.dashboard_entry(data)
    finally:
        fanout.clear_test_plugins()
    assert data == snapshot
    assert seen == [snapshot]
