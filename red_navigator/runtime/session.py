"""RED session lifecycle: discover/load/mount plugins, host overlay, fan out.

:func:`start` discovers and loads plugins via the edmc_compat loader,
mounts each through ``host_panel.mount_loaded`` (which calls
``plugin_start3`` exactly once per plugin and registers its settings
panel), starts the overlay host unless ``overlay=False`` (failure
degrades to terminal-only with a log, never raises), and flips the
fan-out enabled flag. :func:`stop` calls ``plugin_stop`` per plugin,
stops the host, unmounts panels, and disables fan-out.

First-run EDMC import intentionally lives in the Task 4 launcher, not
here: it needs an ``edmc_source`` plus explicit user consent (fresh vs
retry) and must never proceed silently. This module only wires
``config_store`` persistence (``set_store_path`` + ``load``) so per-plugin
settings survive restarts.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger("red_navigator.runtime.session")

#: Config filename used when ``red_store`` is a directory.
_CONFIG_FILENAME = "config.json"


class Session:
    """A running RED Navigator plugin session."""

    def __init__(self, plugin_dir: str, red_store: str, overlay: bool = True) -> None:
        self.plugin_dir = plugin_dir
        self.red_store = red_store
        self.overlay = bool(overlay)
        # (module, plugin path, display name) per loaded plugin.
        self._plugins: list[tuple[Any, str, str]] = []
        self._running = False

    def is_running(self) -> bool:
        """Return True between successful start() and stop()."""
        return self._running

    @property
    def plugin_names(self) -> list[str]:
        """Display names of the loaded plugins."""
        return [name for _, _, name in self._plugins]


def _wire_store(red_store: str) -> None:
    """Point config_store at ``red_store`` and load persisted values.

    ``red_store`` is a directory by convention (see importer/app); the
    JSON backing file is ``<red_store>/config.json``. An explicit
    ``*.json`` path is used verbatim. Best effort: never raises.
    """
    try:
        from red_navigator.edmc_compat import config_store

        candidate = Path(red_store)
        if candidate.suffix == ".json":
            cfg_file = candidate
            try:
                cfg_file.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                _log.warning("Could not create store parent %s", cfg_file.parent)
        else:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
            except OSError:
                _log.warning("Could not create red store dir %s", candidate)
            cfg_file = candidate / _CONFIG_FILENAME
        try:
            config_store.set_store_path(str(cfg_file))
        except Exception:
            _log.warning("Could not set config store path %s", cfg_file, exc_info=True)
            return
        try:
            config_store.load()
        except Exception:
            _log.warning("Could not load config store %s", cfg_file, exc_info=True)
    except Exception:
        _log.warning("Store wiring failed for %s", red_store, exc_info=True)


def start(plugin_dir: str, red_store: str, *, overlay: bool = True) -> Session:
    """Start a RED session from ``plugin_dir`` with store at ``red_store``.

    Never raises for plugin/overlay problems (bad plugins are skipped
    with a log; overlay failure degrades to terminal-only).
    """
    from red_navigator.edmc_compat import loader
    from red_navigator.runtime import fanout
    from red_navigator.settings_ui import host_panel

    sess = Session(plugin_dir, red_store, overlay=overlay)

    _wire_store(red_store)

    try:
        found = loader.discover_plugins(plugin_dir)
    except Exception:
        _log.warning("Plugin discovery failed for %s", plugin_dir, exc_info=True)
        found = []

    for path in found:
        try:
            plugin = loader.load_plugin(path)
        except Exception:
            _log.warning("Skipping unloadable plugin %s", path, exc_info=True)
            continue
        try:
            # mount_loaded calls plugin_start3 exactly once (falling back
            # to the directory name) and mounts the settings panel, so no
            # separate plugin_start3 call here: EDMC starts each plugin once.
            name = host_panel.mount_loaded(plugin, path)
        except Exception:
            _log.warning("Skipping unmountable plugin %s", path, exc_info=True)
            continue
        fanout.register_plugin(plugin)
        sess._plugins.append((plugin, path, name))

    if overlay:
        try:
            from red_navigator.overlay_host import host

            host.start(plugin_dir)
        except Exception as exc:
            _log.warning(
                "Overlay host unavailable (%s); continuing terminal-only", exc
            )
    else:
        _log.info("Overlay disabled; terminal-only mode")

    fanout.set_enabled(True)
    sess._running = True
    _log.info(
        "RED session started: %d plugin(s) from %s (overlay=%s)",
        len(sess._plugins), plugin_dir, overlay,
    )
    return sess


def stop(s: Session | None) -> None:
    """Stop session ``s``: plugin_stop per plugin, host stopped, fan-out off.

    Idempotent; ``None`` or an already-stopped session is a no-op. Never
    raises.
    """
    if s is None or not isinstance(s, Session):
        return
    if not s._running and not s._plugins:
        return

    from red_navigator.edmc_compat import loader
    from red_navigator.runtime import fanout

    try:
        for plugin, path, name in list(s._plugins):
            try:
                loader.call_plugin_stop(plugin)
            except Exception:
                _log.warning("plugin_stop failed for %s", path, exc_info=True)
            try:
                fanout.unregister_plugin(plugin)
            except Exception:
                _log.debug("fanout unregister failed for %s", path, exc_info=True)
            try:
                from red_navigator.settings_ui import host_panel

                host_panel.unmount(name)
            except Exception:
                _log.debug("panel unmount failed for %r", name, exc_info=True)
        s._plugins.clear()
    finally:
        try:
            from red_navigator.overlay_host import host

            host.stop()
        except Exception:
            _log.warning("Overlay host stop failed", exc_info=True)
        try:
            fanout.set_enabled(False)
        except Exception:
            _log.debug("fanout disable failed", exc_info=True)
        s._running = False
        _log.info("RED session stopped")
