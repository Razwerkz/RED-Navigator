"""Bindable global action registry.

Owns all global keybindings behind a small dict-backed registry keyed by
action id. Bindings persist across restarts through the namespaced
:mod:`red_navigator.edmc_compat.config_store` and survive updates that add
or remove actions (unknown stored ids are ignored on load).
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any

from red_navigator.edmc_compat import config_store

_log = logging.getLogger("red_navigator.actions.registry")

#: config_store namespace owning persisted bindings (verbatim per plan).
BINDINGS_PLUGIN = "red_navigator.bindings"

#: Fixed config_store key holding the JSON-encoded ``{action_id: key}`` map.
BINDINGS_KEY = "bindings"

_lock = threading.RLock()
_actions: dict[str, dict[str, Any]] = {}


def _normalize_key(key: str) -> str:
    """Normalize a key name to Textual key-name form.

    Lowercases and maps the ``+``/``=`` glyphs to their Textual key names
    (``plus``/``equal``) so ``resolve("+")`` matches a binding stored as
    ``"plus"`` and vice versa.
    """
    name = key.strip().lower()
    if name == "+":
        return "plus"
    if name == "=":
        return "equal"
    return name


def register(
    id: str,
    label: str,
    default: str | None,
    handler: Callable[[], None],
    when: Callable[[], bool] | None = None,
) -> None:
    """Register (or re-register) an action.

    Re-registering updates label/handler/when/default but keeps a live
    binding already set for the id, so a re-import never clobbers a loaded
    user override. Fresh registrations start on ``default``.
    """
    norm_default = _normalize_key(default) if default is not None else None
    with _lock:
        existing = _actions.get(id)
        _actions[id] = {
            "id": id,
            "label": label,
            "default": norm_default,
            "key": existing["key"] if existing is not None else norm_default,
            "handler": handler,
            "when": when,
        }


def resolve(key: str) -> dict | None:
    """Return the action bound to ``key``, or ``None``.

    ``when`` predicates are evaluated at resolve time; actions whose
    predicate returns False (or raises) are skipped.
    """
    norm = _normalize_key(key)
    with _lock:
        candidates = [a for a in _actions.values() if a["key"] == norm]
    for action in candidates:
        predicate = action["when"]
        if predicate is not None:
            try:
                if not predicate():
                    continue
            except Exception:
                _log.debug("when predicate for %r raised; skipping", action["id"], exc_info=True)
                continue
        return {
            "id": action["id"],
            "label": action["label"],
            "key": action["key"],
            "handler": action["handler"],
        }
    return None


def get(id: str) -> dict | None:
    """Return the registered action ``id``, or ``None``.

    Unlike :func:`resolve` (key lookup), this is a by-id lookup for
    callers that already know the action (e.g. gesture dispatch for
    actions with no single-key binding). The ``when`` predicate is
    evaluated exactly as in :func:`resolve`: an action whose predicate
    returns False (or raises) yields ``None``.
    """
    with _lock:
        action = _actions.get(id)
        snapshot = dict(action) if action is not None else None
    if snapshot is None:
        return None
    predicate = snapshot["when"]
    if predicate is not None:
        try:
            if not predicate():
                return None
        except Exception:
            _log.debug("when predicate for %r raised; skipping", id, exc_info=True)
            return None
    return {
        "id": snapshot["id"],
        "label": snapshot["label"],
        "key": snapshot["key"],
        "default": snapshot["default"],
        "handler": snapshot["handler"],
    }


def list_actions() -> list[dict]:
    """Return ``{id, label, key, default}`` per registered action."""
    with _lock:
        return [
            {"id": a["id"], "label": a["label"], "key": a["key"], "default": a["default"]}
            for a in _actions.values()
        ]


def set_binding(id: str, key: str | None) -> dict:
    """Rebind ``id`` to ``key`` (``None`` unbinds).

    Returns ``{"ok": True, "conflict": None}`` on success, or
    ``{"ok": False, "conflict": <occupying id>}`` when ``key`` is already
    bound elsewhere (binding unchanged). Unknown ids return
    ``{"ok": False, "conflict": None, "error": ...}``.
    """
    norm = _normalize_key(key) if key is not None else None
    with _lock:
        if id not in _actions:
            return {"ok": False, "conflict": None, "error": f"unknown action: {id}"}
        for other_id, other in _actions.items():
            if other_id != id and other["key"] is not None and other["key"] == norm and norm is not None:
                return {"ok": False, "conflict": other_id}
        _actions[id]["key"] = norm
        _persist_locked()
        return {"ok": True, "conflict": None}


def load_bindings() -> None:
    """Apply persisted binding overrides for registered ids only.

    Unknown stored ids (actions removed by an update) are ignored so
    removals never crash. Missing or corrupt store data is a no-op.
    """
    raw = config_store.get_str(BINDINGS_KEY, plugin=BINDINGS_PLUGIN)
    if raw is None:
        return
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        _log.debug("ignoring corrupt bindings store data", exc_info=True)
        return
    if not isinstance(data, dict):
        return
    with _lock:
        for stored_id, stored_key in data.items():
            if stored_id not in _actions:
                continue
            if stored_key is None:
                _actions[stored_id]["key"] = None
            elif isinstance(stored_key, str):
                _actions[stored_id]["key"] = _normalize_key(stored_key)
            # Non-string, non-None values are ignored (never crash).


def clear(keep_store: bool = False) -> None:
    """Drop all registered actions (test helper).

    Unless ``keep_store`` is true, the persisted bindings are removed too.
    """
    with _lock:
        _actions.clear()
        if not keep_store:
            try:
                config_store.delete(BINDINGS_KEY, plugin=BINDINGS_PLUGIN)
            except Exception:
                _log.debug("clearing persisted bindings failed", exc_info=True)


def _persist_locked() -> None:
    """Write the current ``{id: key}`` map to config_store (lock held)."""
    try:
        payload = json.dumps({aid: a["key"] for aid, a in _actions.items()}, sort_keys=True)
    except (ValueError, TypeError):
        _log.debug("bindings not JSON-serializable; skipping persist", exc_info=True)
        return
    try:
        config_store.set(BINDINGS_KEY, payload, plugin=BINDINGS_PLUGIN)
    except Exception:
        _log.debug("persisting bindings failed", exc_info=True)
