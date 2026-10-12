def test_resume_republishes_announces_and_copies():
    from red_navigator.routes import resume
    route = {"Route": [{"StarSystem": "Sol"}, {"StarSystem": "Alpha"}]}
    published, copied, said = [], [], []
    result = resume.resume_route(lambda: route, lambda p: published.append(p) or True, lambda t: copied.append(t) or True, said.append)
    assert result == {"ok": True, "waypoint": "Sol", "published": 2, "copied": True}
    assert copied == ["Sol"] and any("Sol" in s for s in said)


def test_resume_without_route_announces_gracefully():
    from red_navigator.routes import resume
    said = []
    result = resume.resume_route(lambda: None, lambda p: True, lambda t: True, said.append)
    assert result["ok"] is False and result["waypoint"] is None
    assert len(said) == 1
