def test_journal_files_never_written(tmp_path):
    from red_navigator.feeds import journal_tail
    p = tmp_path / "Journal.1.log"
    p.write_text('{"event":"Fileheader"}\n')
    before = p.read_bytes()
    list(journal_tail.iter_entries(str(tmp_path)))
    assert p.read_bytes() == before


def test_navroute_clear_retains_prior_route():
    from red_navigator.feeds import state_builder
    state = state_builder.build_state()
    state["NavRoute"] = {"Route": [{"StarSystem": "Sol"}]}
    updated = state_builder.apply_entry(state, {"event": "NavRouteClear"})
    assert updated["NavRoute"] == {"Route": [{"StarSystem": "Sol"}]}


def test_body_state_requires_dashboard_crosscheck():
    from red_navigator.feeds import state_builder
    state = state_builder.build_state()
    state["Body"] = "BodyA"
    assert state_builder.needs_dashboard_crosscheck(state, {"Body": "BodyB"}) is True
