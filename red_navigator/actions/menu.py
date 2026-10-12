"""Read-only binding-menu helpers over the action registry.

Pure helpers for the settings Hotkeys section: listing current bindings,
applying a rebinding, and capturing a key press (Escape cancels).
"""

from __future__ import annotations

from typing import Any

from red_navigator.actions import registry


def binding_sections() -> list[dict]:
    """Return ``{id, label, key}`` per registered action.

    Read-only over :func:`registry.list_actions`; never raises — ``[]``
    when empty or on unexpected failure.
    """
    try:
        return [
            {"id": a["id"], "label": a["label"], "key": a["key"]}
            for a in registry.list_actions()
        ]
    except Exception:
        return []


def apply_binding(id: str, key: str | None) -> dict:
    """Delegate to :func:`registry.set_binding`; never raises.

    Returns the ``set_binding`` result dict verbatim on success, or
    ``{ok: False, conflict: None, error}`` on unexpected failure.
    """
    try:
        return registry.set_binding(id, key)
    except Exception as exc:
        return {"ok": False, "conflict": None, "error": str(exc)}


def capture_key(id: str, key: str) -> dict[str, Any]:
    """Capture ``key`` as the binding for ``id``.

    Escape short-circuits to ``{ok: False, cancelled: True}`` without
    touching bindings; any other key delegates to :func:`apply_binding`.
    """
    if isinstance(key, str) and key.strip().lower() == "escape":
        return {"ok": False, "cancelled": True}
    return apply_binding(id, key)
