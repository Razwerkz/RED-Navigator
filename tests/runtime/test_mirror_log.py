def test_published_payload_reaches_event_sink():
    from red_navigator.runtime import fanout
    seen = []
    fanout.set_event_sink(seen.append)
    try:
        fanout.journal_entry({"event": "FSDJump", "StarSystem": "Sol"}, {"system": "Sol"})
    finally:
        fanout.set_event_sink(None)
    assert any("Sol" in line for line in seen)


def test_sink_never_raises_to_monitor_thread():
    from red_navigator.runtime import fanout

    def bad(line):
        raise RuntimeError("sink boom")

    fanout.set_event_sink(bad)
    try:
        fanout.journal_entry({"event": "Docked"}, {})
    finally:
        fanout.set_event_sink(None)


def test_dashboard_status_poll_delivers_nothing_to_sink():
    from red_navigator.runtime import fanout
    seen = []
    fanout.set_event_sink(seen.append)
    try:
        fanout.dashboard_entry({"Flags": 0, "Pips": [4, 4, 4]})
    finally:
        fanout.set_event_sink(None)
    assert seen == []
