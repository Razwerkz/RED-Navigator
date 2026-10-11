"""Generic per-plugin settings forms (Textual-side, no tkinter).

Each EDMC plugin describes its preferences through ``plugin_prefs``
tkinter widgets, which cannot run headless. Plugins therefore expose a
plain-data ``prefs_spec`` (``{"fields": [...]}``) that this module
renders into a list of field dicts the Textual settings layer can draw,
and applies back through the namespaced :mod:`config_store`.

Supported field ``type`` values: ``bool``, ``text``, ``number``,
``file``, ``dropdown``. Anything else (e.g. raw tkinter widget names)
falls back to a readable ``text`` field with ``fallback: True`` —
rendering never crashes.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from red_navigator.edmc_compat import config_store

_log = logging.getLogger("red_navigator.settings_ui.forms")

#: Field types the Textual settings layer knows how to draw.
KNOWN_TYPES = ("bool", "text", "number", "file", "dropdown")

#: Aliases (including tkinter widget names) mapped onto known types.
_TYPE_ALIASES = {
    "boolean": "bool",
    "checkbutton": "bool",
    "check": "bool",
    "toggle": "bool",
    "str": "text",
    "string": "text",
    "entry": "text",
    "label": "text",
    "int": "number",
    "integer": "number",
    "float": "number",
    "spinbox": "number",
    "scale": "number",
    "path": "file",
    "filename": "file",
    "filepath": "file",
    "choice": "dropdown",
    "option": "dropdown",
    "optionmenu": "dropdown",
    "select": "dropdown",
    "enum": "dropdown",
    "combobox": "dropdown",
}

_TRUE_STRINGS = {"1", "true", "yes", "on"}


def _normalize_type(raw: Any) -> tuple[str, bool]:
    """Map ``raw`` onto a known type; return ``(type, fell_back)``."""
    if isinstance(raw, str):
        lowered = raw.strip().lower().split(".")[-1]
        if lowered in KNOWN_TYPES:
            return lowered, False
        if lowered in _TYPE_ALIASES:
            return _TYPE_ALIASES[lowered], False
    return "text", True


def _stored_value(key: str, plugin: str | None) -> str | None:
    try:
        return config_store.get_str(key, plugin=plugin)
    except Exception:
        _log.debug("config_store read failed for %r", key, exc_info=True)
        return None


def _coerce(field_type: str, stored: str | None, default: Any, options: list) -> Any:
    """Convert a stored string into the field's native value."""
    if stored is None:
        if field_type == "dropdown" and options:
            return default if default in options else options[0]
        return default
    try:
        if field_type == "bool":
            return stored.strip().lower() in _TRUE_STRINGS
        if field_type == "number":
            number: Any = float(stored)
            if isinstance(default, bool):
                return default
            if isinstance(default, int):
                return int(number)
            return number
        if field_type == "dropdown":
            return stored if stored in options else (
                default if default in options else (options[0] if options else default)
            )
        return stored
    except (ValueError, TypeError, AttributeError):
        return default


def render(prefs_spec: dict | list | None, *, plugin: str | None = None) -> list[dict]:
    """Render ``prefs_spec`` into a list of field dicts.

    ``prefs_spec`` is ``{"fields": [{key, type, default, label?,
    options?, ...}]}`` (a bare list of fields is also accepted).
    Each returned dict has ``key``, ``type``, ``label``, ``value`` and
    ``default``; dropdowns add ``options``; unknown widget types fall
    back to ``text`` with ``fallback: True`` and a readable ``hint``.
    Current values come from ``config_store`` (namespaced to ``plugin``
    or the ambient :func:`scoped` plugin), defaulting to each field's
    ``default``. Never raises on bad input.
    """
    try:
        if prefs_spec is None:
            return []
        fields: Any = prefs_spec.get("fields", []) if isinstance(prefs_spec, dict) else prefs_spec
        if not isinstance(fields, list):
            return []
        rendered: list[dict] = []
        for field in fields:
            try:
                if not isinstance(field, Mapping):
                    continue
                key = field.get("key")
                if not isinstance(key, str) or not key:
                    continue
                field_type, fell_back = _normalize_type(field.get("type", "text"))
                default = field.get("default", "" if field_type in ("text", "file") else None)
                if default is None:
                    default = False if field_type == "bool" else (
                        0 if field_type == "number" else "")
                label = field.get("label", key)
                if not isinstance(label, str) or not label:
                    label = key
                options = [str(o) for o in field.get("options", [])] if field_type == "dropdown" else []
                value = _coerce(field_type, _stored_value(key, plugin), default, options)
                entry: dict[str, Any] = {
                    "key": key,
                    "type": field_type,
                    "label": label,
                    "value": value,
                    "default": default,
                }
                if field_type == "dropdown":
                    entry["options"] = options
                if fell_back:
                    entry["fallback"] = True
                    entry["hint"] = f"Unsupported widget {field.get('type')!r}; editing as text."
                rendered.append(entry)
            except Exception:
                _log.debug("Skipping unreadable prefs field %r", field, exc_info=True)
                continue
        return rendered
    except Exception:
        _log.debug("render failed for spec %r", prefs_spec, exc_info=True)
        return []


def apply(values: Mapping[str, Any] | None, *, plugin: str | None = None) -> None:
    """Persist ``values`` through the namespaced ``config_store``.

    Only the keys present in ``values`` are touched — existing keys
    (including brand-new keys from a newer plugin version) are never
    wiped. ``None`` values delete the key (clearing a field). Never
    raises for per-key coercion problems.
    """
    if not isinstance(values, Mapping):
        return
    for key, value in values.items():
        try:
            if not isinstance(key, str) or not key:
                continue
            if value is None:
                config_store.delete(key, plugin=plugin)
            else:
                config_store.set(key, value, plugin=plugin)
        except Exception:
            _log.debug("config_store write failed for %r", key, exc_info=True)
            continue
