"""Task 5: launcher wiring, registry migration, default seed (RED actions/routes).

Verbatim acceptance tests first (TDD): the double-Shift gesture detector
and the import-time seed of migrated NOVA bindings.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reseed_default_bindings():
    """Re-apply the default seed before each test (order-independent).

    Other suites (tests/actions/) clear the global registry; re-seeding
    here keeps these tests green regardless of execution order.
    Re-registration never clobbers a live user binding (registry
    semantics), so this is safe to run unconditionally.
    """
    from red_navigator import app as _red_app

    _red_app.ensure_default_bindings()
    yield


def test_resume_bound_to_double_shift_gesture():
    from red_navigator.actions import gestures
    assert gestures.note_key("shift", 0.0) is None
    assert gestures.note_key("shift", 0.2) == "route.resume"
    assert gestures.note_key("shift", 10.0) is None
    assert gestures.note_key("shift", 11.0) is None  # outside window

def test_migrated_binding_still_resolves():
    from red_navigator.actions import registry
    import red_navigator.app  # noqa: F401
    assert registry.resolve("s") is not None


def test_gesture_ignores_left_shift_but_accepts_right():
    from red_navigator.actions import gestures

    # Right-Shift-only preference: left taps never arm or fire the gesture.
    assert gestures.note_key("left_shift", 100.0) is None
    assert gestures.note_key("left_shift", 100.2) is None
    # Known-right location fires like the location-unknown "shift" name.
    assert gestures.note_key("right_shift", 200.0) is None
    assert gestures.note_key("right_shift", 200.2) == "route.resume"


def test_migrated_defaults_cover_global_single_keys():
    from red_navigator.actions import registry

    for key in ("q", "question_mark", "escape", "g", "t", "y", "p",
                "a", "m", "n", "enter", "plus", "minus", "tab",
                "0", "1", "2", "3", "4", "5", "6"):
        assert registry.resolve(key) is not None, key


def test_resume_has_no_single_key_default():
    from red_navigator.actions import registry

    assert registry.get("route.resume") is not None
    assert registry.get("route.resume")["key"] is None


def _wire_with_fakes(route_entries):
    """Wire real handlers over stub collaborators; caller must clean up."""
    import threading
    from types import SimpleNamespace

    from red_navigator import app as _red_app

    state = SimpleNamespace(route_list=list(route_entries))
    lock = threading.RLock()
    spoken = []

    class _FakeTtsQ:
        def put_nowait(self, item):
            spoken.append(item)

    _red_app.wire_actions(SimpleNamespace(_cfg=None), state, lock, _FakeTtsQ())
    return state, spoken


def test_resume_handler_republishes_route_from_state(monkeypatch):
    import red_navigator.clipboard as _clipboard
    import red_navigator.overlay_host.host as _host
    from red_navigator.actions import registry

    published, copied = [], []
    monkeypatch.setattr(_host, "publish", lambda p: published.append(p) or True)
    monkeypatch.setattr(_clipboard, "copy_text", lambda t: copied.append(t) or True)
    _, spoken = _wire_with_fakes([
        {"StarSystem": "Sol", "StarPos": [0, 0, 0]},
        {"StarSystem": "Alpha", "StarPos": [1, 0, 0]},
    ])
    try:
        registry.get("route.resume")["handler"]()
        # Departure (route[0]) skipped exactly like the route panel.
        assert [p.get("system") for p in published] == ["Alpha"]
        assert copied == ["Alpha"]
        assert any("Alpha" in m.text for m in spoken)
    finally:
        registry.clear()
        from red_navigator import app as _red_app

        _red_app.ensure_default_bindings()


def test_single_key_binding_replaces_gesture():
    from red_navigator.actions import gestures, registry

    _wire_with_fakes([{"StarSystem": "Sol"}])
    try:
        assert registry.set_binding("route.resume", "r")["ok"] is True
        assert gestures.note_key("shift", 300.0) is None
        # Gesture completed but the action is now key-bound: dispatch must
        # treat it as superseded (key is not None).
        assert gestures.note_key("shift", 300.2) == "route.resume"
        assert registry.get("route.resume")["key"] == "r"
        assert registry.resolve("r")["id"] == "route.resume"
        # Unbinding re-arms the gesture.
        assert registry.set_binding("route.resume", None)["ok"] is True
        assert registry.get("route.resume")["key"] is None
    finally:
        registry.clear()
        from red_navigator import app as _red_app

        _red_app.ensure_default_bindings()
