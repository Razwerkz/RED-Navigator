"""Per-plugin settings panels mounted into the NOVA settings hook.

:data:`NOVA_SETTINGS_HOOK` (pinned by Task 1) is the ``s``-key branch in
``ed_monitor/ui/app.py::NovaApp.on_key()`` pushing
``ed_monitor/ui/settings_screen.py::SettingsScreen``. This module is
intentionally read-only towards ``ed_monitor/``: it keeps one panel per
loaded plugin exposing ``plugin_prefs``/``prefs_changed`` — listed by the
name returned from ``plugin_start3`` — and exposes them via
:func:`settings_sections` for the settings overlay to draw.

Adaptor contract (for the loader/adaptor task): a plugin's tkinter
``plugin_prefs(parent, cmdr, is_beta)`` callable cannot be introspected
headless, so a plugin (or its adaptor) supplies a plain-data prefs spec
consumed by :mod:`red_navigator.settings_ui.forms` — either a
``prefs_spec`` attribute (``{"fields": [{key, type, default, label?,
options?, ...}]}``) or a ``get_prefs_spec()`` callable returning one.
When a plugin exposes ``plugin_prefs`` but supplies no such spec, the
panel renders a single explanatory placeholder field (see
:func:`mount_for_plugin`) instead of a silently empty panel, so the UI
never lists hollow panels.
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

#: Field key for the explanatory placeholder rendered when a plugin
#: exposes ``plugin_prefs`` but supplies no RED-side prefs spec. The key
#: is namespaced like any other setting but is stripped from saves (see
#: :func:`save_panel_values`), so it is never persisted and never wipes
#: real settings.
_PLACEHOLDER_KEY = "_prefs_no_spec"


def _placeholder_field(name: str) -> dict[str, Any]:
    """Build the explanatory placeholder field for spec-less ``name``."""
    text = (
        f"Settings for '{name}' are defined by its tkinter plugin_prefs "
        "panel, which has no RED prefs_spec adaptor yet "
        "(provide a prefs_spec attribute or get_prefs_spec() callable); "
        "plugin defaults apply."
    )
    return {
        "key": _PLACEHOLDER_KEY,
        "type": "text",
        "label": f"{name} settings",
        "value": text,
        "default": "",
        "placeholder": True,
        "hint": (
            f"No RED-side prefs spec for '{name}': adaptor contract is a "
            "'prefs_spec' attribute or 'get_prefs_spec()' callable "
            "returning {'fields': [...]}."
        ),
    }


def _build_fields(name: str, plugin: Any, has_prefs: bool) -> list[dict[str, Any]]:
    """Render ``plugin``'s fields, or a placeholder when spec-less.

    Returns ``forms.render`` output when a RED-side spec exists (even if
    it renders to an empty list), a single explanatory placeholder field
    when the plugin exposes ``plugin_prefs`` but supplies no spec, and an
    empty list otherwise. Never raises.
    """
    try:
        with config_store.scoped(name):
            spec = _prefs_spec_of(plugin)
            if spec is None:
                if has_prefs:
                    return [_placeholder_field(name)]
                return []
            return forms.render(spec, plugin=name)
    except Exception:
        _log.debug("Panel render failed for %r", name, exc_info=True)
        return []


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
    overlay still lists them. Plugins exposing ``plugin_prefs`` without
    a RED-side prefs spec (see the module adaptor contract) mount with a
    single explanatory placeholder field instead of a hollow panel.
    """
    if not isinstance(name, str) or not name:
        return
    with _lock:
        plugin = _registry.get(name)
        has_prefs = callable(getattr(plugin, "plugin_prefs", None))
        has_changed = callable(getattr(plugin, "prefs_changed", None))
        fields = _build_fields(name, plugin, bool(has_prefs))
        _panels[name] = {
            "name": name,
            "has_prefs": bool(has_prefs),
            "has_prefs_changed": bool(has_changed),
            "fields": fields,
        }


def list_registered() -> list[str]:
    """Return sorted display names of all registered plugins.

    Includes names registered via :func:`register_plugin` whose panels
    have not been mounted yet (contrast :func:`list_panels`).
    """
    with _lock:
        return sorted(_registry)


def ensure_mounted(name: str) -> bool:
    """Mount the panel for registered ``name`` when missing.

    Calls :func:`mount_for_plugin` when ``name`` is registered but has
    no panel yet. Returns whether a panel exists for ``name``
    afterwards. Never raises (returns ``False`` on error or for
    invalid/unknown names).
    """
    if not isinstance(name, str) or not name:
        return False
    try:
        with _lock:
            if name in _panels or name not in _registry:
                return name in _panels
        mount_for_plugin(name)
        with _lock:
            return name in _panels
    except Exception:
        _log.debug("ensure_mounted failed for %r", name, exc_info=True)
        return False


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
    a failing hook is logged and never breaks the save. The explanatory
    placeholder key (see :data:`_PLACEHOLDER_KEY`) is stripped before
    writing, so saving a spec-less panel persists nothing and wipes
    nothing.
    """
    if not isinstance(name, str) or not name:
        return
    with _lock:
        plugin = _registry.get(name)
    try:
        cleaned = (
            {k: v for k, v in values.items() if k != _PLACEHOLDER_KEY}
            if isinstance(values, dict)
            else values
        )
        with config_store.scoped(name):
            forms.apply(cleaned, plugin=name)
    except Exception:
        _log.debug("Panel save failed for %r", name, exc_info=True)
    try:
        has_prefs = callable(getattr(plugin, "plugin_prefs", None))
        fields = _build_fields(name, plugin, bool(has_prefs))
        with _lock:
            if name in _panels:
                _panels[name] = {
                    "name": name,
                    "has_prefs": bool(has_prefs),
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
