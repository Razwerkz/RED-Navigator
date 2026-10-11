"""Per-plugin settings panels mounted into the NOVA settings hook.

:data:`NOVA_SETTINGS_HOOK` (pinned by Task 1) is the ``s``-key branch in
``ed_monitor/ui/app.py::NovaApp.on_key()`` pushing
``ed_monitor/ui/settings_screen.py::SettingsScreen``. This module is
intentionally read-only towards ``ed_monitor/``: it keeps one panel per
loaded plugin exposing ``plugin_prefs``/``prefs_changed`` — listed by the
name returned from ``plugin_start3`` — and exposes them via
:func:`settings_sections` for the settings overlay to draw.
"""

from __future__ import annotations

import copy
import logging
import threading
from typing import Any

from red_navigator.edmc_compat import config_store

from . import forms

_log = logging.getLogger("red_navigator.settings_ui.host_panel")

#: Extension point pinned by Task 1 (``docs/superpowers/plans/NOVA_FORK_INVENTORY.md``).
NOVA_SETTINGS_HOOK = "ed_monitor.ui.app:NovaApp.on_key[s]->SettingsScreen"

_lock = threading.RLock()

#: Panels keyed by plugin display name: {"name", "has_prefs",
#: "has_prefs_changed", "fields"}.
_panels: dict[str, dict[str, Any]] = {}

#: Loaded plugin objects keyed by display name (for prefs_changed calls).
_registry: dict[str, Any] = {}


def _prefs_spec_of(plugin: Any) -> dict | list | None:
    """Best-effort prefs spec for ``plugin`` (``None`` when unknown)."""
    if plugin is None:
        return None
    try:
        spec = getattr(plugin, "prefs_spec", None)
        if isinstance(spec, (dict, list)):
            return spec
        getter = getattr(plugin, "get_prefs_spec", None)
        if callable(getter):
            spec = getter()
            if isinstance(spec, (dict, list)):
                return spec
    except Exception:
        _log.debug("prefs spec lookup failed for %r", plugin, exc_info=True)
    return None


def register_plugin(name: str, plugin: Any) -> None:
    """Remember the loaded ``plugin`` object under display ``name``."""
    if not isinstance(name, str) or not name:
        return
    with _lock:
        _registry[name] = plugin


def mount_for_plugin(name: str) -> None:
    """Mount (or refresh) the settings panel for plugin ``name``.

    Idempotent: mounting twice keeps a single panel. Never raises —
    unknown plugins mount as panels with no fields so the settings
    overlay still lists them.
    """
    if not isinstance(name, str) or not name:
        return
    with _lock:
        plugin = _registry.get(name)
        has_prefs = callable(getattr(plugin, "plugin_prefs", None))
        has_changed = callable(getattr(plugin, "prefs_changed", None))
        try:
            with config_store.scoped(name):
                fields = forms.render(_prefs_spec_of(plugin), plugin=name)
        except Exception:
            _log.debug("Panel render failed for %r", name, exc_info=True)
            fields = []
        _panels[name] = {
            "name": name,
            "has_prefs": bool(has_prefs),
            "has_prefs_changed": bool(has_changed),
            "fields": fields,
        }


def mount_loaded(plugin: Any, plugin_dir: str) -> str:
    """Register ``plugin`` under its ``plugin_start3`` name and mount it.

    Returns the display name (falls back to the directory name, matching
    :func:`red_navigator.edmc_compat.loader.call_plugin_start3`).
    """
    from red_navigator.edmc_compat import loader

    try:
        name = loader.call_plugin_start3(plugin, plugin_dir)
    except Exception:
        from pathlib import Path

        name = Path(plugin_dir).name
    if not isinstance(name, str) or not name:
        from pathlib import Path

        name = Path(plugin_dir).name
    register_plugin(name, plugin)
    mount_for_plugin(name)
    return name


def unmount(name: str) -> None:
    """Remove the panel (and registry entry) for ``name``."""
    with _lock:
        _panels.pop(name, None)
        _registry.pop(name, None)


def clear() -> None:
    """Remove all panels (used by tests)."""
    with _lock:
        _panels.clear()
        _registry.clear()


def get_panel(name: str) -> dict[str, Any] | None:
    """Return a copy of the panel dict for ``name``, or ``None``."""
    with _lock:
        panel = _panels.get(name)
        return copy.deepcopy(panel) if panel is not None else None


def list_panels() -> list[dict[str, Any]]:
    """Return copies of all mounted panels, sorted by display name."""
    with _lock:
        return [copy.deepcopy(_panels[name]) for name in sorted(_panels)]


def save_panel_values(
    name: str, values: dict, *, cmdr: str = "", is_beta: bool = False
) -> None:
    """Apply ``values`` to plugin ``name``'s namespace and notify it.

    Writes go through :func:`forms.apply` (existing keys are preserved),
    then the plugin's ``prefs_changed`` hook is called best-effort —
    a failing hook is logged and never breaks the save.
    """
    if not isinstance(name, str) or not name:
        return
    with _lock:
        plugin = _registry.get(name)
    try:
        with config_store.scoped(name):
            forms.apply(values, plugin=name)
    except Exception:
        _log.debug("Panel save failed for %r", name, exc_info=True)
    try:
        with config_store.scoped(name):
            fields = forms.render(_prefs_spec_of(plugin), plugin=name)
        with _lock:
            if name in _panels:
                _panels[name] = {
                    "name": name,
                    "has_prefs": bool(callable(getattr(plugin, "plugin_prefs", None))),
                    "has_prefs_changed": bool(callable(getattr(plugin, "prefs_changed", None))),
                    "fields": fields,
                }
    except Exception:
        _log.debug("Panel refresh after save failed for %r", name, exc_info=True)
    fn = getattr(plugin, "prefs_changed", None)
    if callable(fn):
        try:
            fn(cmdr, is_beta)
        except Exception:
            _log.debug("prefs_changed failed for %r", name, exc_info=True)


def settings_sections() -> dict[str, Any]:
    """Describe the RED sections for the NOVA settings overlay.

    Returns ``{"hook": NOVA_SETTINGS_HOOK, "panels": [...]}`` so the
    ``s``-key ``SettingsScreen`` can draw one section per mounted
    plugin. Read-only towards ``ed_monitor/``.
    """
    return {"hook": NOVA_SETTINGS_HOOK, "panels": list_panels()}
