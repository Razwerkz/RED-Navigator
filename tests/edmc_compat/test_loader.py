def test_loader_calls_journal_entry_with_state(tmp_path):
    from red_navigator.edmc_compat import loader
    seen = {}
    class FakePlugin:
        def journal_entry(self, cmdr, is_beta, system, station, entry, state):
            seen.update(entry=entry, state_keys=set(state.keys()))
    loader.call_journal(FakePlugin(), "CMDR", False, "Sol", "", {"event": "FSDJump", "StarSystem": "Sol"}, {"SystemName": "Sol"})
    assert seen["entry"]["event"] == "FSDJump"
    assert "SystemName" in seen["state_keys"]


def test_cqc_routes_to_cqc_hook():
    from red_navigator.edmc_compat import loader
    seen = {}
    class FakePlugin:
        def journal_entry(self, *a, **k):
            seen["where"] = "main"
        def journal_entry_cqc(self, *a, **k):
            seen["where"] = "cqc"
    loader.dispatch_entry(FakePlugin(), {"event": "Location"}, in_cqc=True)
    assert seen["where"] == "cqc"
