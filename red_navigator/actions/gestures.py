"""Bare-Shift double-tap gesture detector for the ``route.resume`` action.

The default trigger for route resume is a bare double-tap of Shift (a
VoiceAttack-macro replacement that needs no single-key binding). The
detector is deliberately headless — :func:`note_key` takes the Textual
key name and a timestamp — so it is unit-testable without a running app.
:mod:`ed_monitor.ui.app` feeds it every Shift-family key press before
consulting the action registry.
"""

from __future__ import annotations

#: Action id fired when the double-tap gesture completes.
RESUME_ACTION_ID = "route.resume"

#: Maximum interval between the two taps of a double-tap, in seconds.
WINDOW_S = 0.4

#: Key names that count as a Shift tap.
#:
#: Textual 8.x exposes Kitty-protocol modifier locations as distinct key
#: names (``textual/_keyboard_protocol.py`` maps codepoint ``57441u`` to
#: ``"left_shift"`` and ``57447u`` to ``"right_shift"``; ``Key`` carries no
#: separate location attribute, so the name is the only signal). Per the
#: right-Shift-only preference, a location-known *left* tap is ignored —
#: it neither arms nor completes the gesture. The location-unknown
#: ``"shift"`` name (other drivers/protocols) is accepted as a tap so the
#: gesture still works where the terminal does not report key location.
_TAP_KEYS = frozenset({"shift", "right_shift"})

#: Timestamp of the last unmatched tap, or None when no tap is pending.
_last_tap: float | None = None


def note_key(key: str, now: float) -> str | None:
    """Record a Shift-family key press at time ``now`` (seconds).

    Returns :data:`RESUME_ACTION_ID` when this press completes a
    double-tap (a previous tap within :data:`WINDOW_S`), else ``None``.
    A completed (or expired) tap resets the pending state, so each pair
    of taps fires at most once. Non-tap keys (including ``"left_shift"``)
    leave the pending state untouched and return ``None``. Never raises.
    """
    global _last_tap
    try:
        name = key.strip().lower()
    except Exception:
        return None
    if name not in _TAP_KEYS:
        return None
    try:
        previous = _last_tap
        if previous is not None:
            elapsed = now - previous
            if 0 <= elapsed <= WINDOW_S:
                _last_tap = None
                return RESUME_ACTION_ID
        _last_tap = now
    except Exception:
        return None
    return None
