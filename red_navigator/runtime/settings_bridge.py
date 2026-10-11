"""RED Plugins settings bridge for the NOVA settings overlay.

Builds render-ready RED sections from :mod:`red_navigator.settings_ui.host_panel`
panels and persists per-plugin values with per-plugin save isolation (one
plugin's failure never blocks the rest).
"""

from __future__ import annotations

import logging
from typing import Any

from red_navigator.settings_ui import host_panel

_log = logging.getLogger("red_navigator.runtime.settings_bridge")


def _ensure_mounted(names: list[str] | None = None) -> None:
    """Mount registered-but-unmounted plugins so panels exist.

    Best-effort; never raises. When ``names`` is given only those names
    are ensured, otherwise every registered name is ensured. Uses the
    public :func:`host_panel.list_registered` /
    :func:`host_panel.ensure_mounted` helpers.
    """
    try:
        if names is None:
            try:
                names = host_panel.list_registered()
            except Exception:
                _log.debug("list_registered failed", exc_info=True)
                return
        for name in names:
            try:
                if not isinstance(name, str) or not name:
                    continue
                host_panel.ensure_mounted(name)
            except Exception:
                _log.debug("Panel mount failed for %r", name, exc_info=True)
                continue
    except Exception:
        _log.debug("Panel mount pass failed", exc_info=True)


def red_sections() -> list[dict[str, Any]]:
    """Build render-ready RED plugin sections from mounted panels.

    Returns one dict per mounted plugin (sorted by name)::

        {"plugin": name, "name": name, "title": "RED Plugins: {name}",
         "fields": [...], "has_prefs": bool, "has_prefs_changed": bool}

    Never raises; returns ``[]`` when no plugins are mounted.
    """
    try:
        _ensure_mounted()
        panels = host_panel.list_panels()
    except Exception:
        _log.debug("red_sections failed", exc_info=True)
        return []
    sections: list[dict[str, Any]] = []
    try:
        for panel in panels:
            try:
                if not isinstance(panel, dict):
                    continue
                name = panel.get("name")
                if not isinstance(name, str) or not name:
                    continue
                fields = panel.get("fields", [])
                if not isinstance(fields, list):
                    fields = []
                sections.append(
                    {
                        "plugin": name,
                        "name": name,
                        "title": f"RED Plugins: {name}",
                        "fields": fields,
                        "has_prefs": bool(panel.get("has_prefs", False)),
                        "has_prefs_changed": bool(panel.get("has_prefs_changed", False)),
                    }
                )
            except Exception:
                _log.debug("Skipping unreadable panel %r", panel, exc_info=True)
                continue
    except Exception:
        _log.debug("red_sections build failed", exc_info=True)
        return []
    return sections


def save_red_section(values_by_plugin: dict) -> dict[str, dict[str, Any]]:
    """Persist per-plugin values with per-plugin isolation.

    Each plugin's values go through :func:`host_panel.save_panel_values`,
    which contains failures internally (it logs and swallows them), so a
    failing ``prefs_changed`` hook never breaks the save; a raised
    exception for one plugin is recorded and the rest still save.

    Returns ``{plugin_name: {"ok": bool, "error": str | None}}``. ``ok``
    reflects successful dispatch to ``save_panel_values``, not verified
    persistence, since that helper never raises on per-plugin failures.
    Never raises; returns ``{}`` for non-dict input.
    """
    if not isinstance(values_by_plugin, dict):
        return {}
    try:
        _ensure_mounted(
            [n for n in values_by_plugin.keys() if isinstance(n, str) and n]
        )
    except Exception:
        _log.debug("save_red_section mount pass failed", exc_info=True)
    results: dict[str, dict[str, Any]] = {}
    for name, values in values_by_plugin.items():
        try:
            if not isinstance(name, str) or not name:
                results[name] = {"ok": False, "error": "invalid plugin name"}
                continue
            if not isinstance(values, dict):
                results[name] = {"ok": False, "error": "invalid values"}
                continue
            try:
                if host_panel.get_panel(name) is None:
                    host_panel.ensure_mounted(name)
            except Exception:
                _log.debug(
                    "Panel ensure-mount failed for %r", name, exc_info=True
                )
            host_panel.save_panel_values(name, values)
            results[name] = {"ok": True, "error": None}
        except Exception as exc:
            _log.debug("Panel save failed for %r", name, exc_info=True)
            try:
                results[name] = {"ok": False, "error": str(exc)}
            except Exception:
                pass
    return results
