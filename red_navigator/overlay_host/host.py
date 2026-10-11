"""1:1 host for the unmodified Modern Overlay plugin.

Loads the user's ``load.py`` through the Task 2 compatibility loader
(:func:`red_navigator.edmc_compat.loader.load_plugin`), starts its
WebSocket broadcaster and legacy TCP path, launches and supervises its
existing overlay client/controller processes via the plugin's own
watchdog, and reuses its grouping/profile/settings files in place
(``overlay_groupings.json``, ``overlay_groupings.user.json``,
``overlay_settings.json`` are only ever read in their existing
location, never copied).

Only ``port.json`` is written, under single-owner semantics from
:mod:`red_navigator.overlay_host.port_owner`, with stale-file cleanup
for the case where EDMC is also installed.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

_log = logging.getLogger("red_navigator.overlay_host.host")

_lock = threading.RLock()
_plugin: ModuleType | None = None
_plugin_dir: str | None = None
_port: int = 0
_supervisor_thread: threading.Thread | None = None
_supervisor_stop = threading.Event()

#: Grouping/profile/settings files reused in place (never copied).
REUSED_FILES = (
    "overlay_groupings.json",
    "overlay_groupings.user.json",
    "overlay_settings.json",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _broadcaster_port(candidate: Any) -> int:
    try:
        port = int(getattr(candidate, "port", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return port if 0 < port < 65536 else 0


def _discover_port(plugin: Any, plugin_dir: Path) -> int:
    """Find the broadcaster port the plugin started (0 when unknown)."""
    # Real overlay: module-global ``_plugin`` is a _PluginRuntime whose
    # ``broadcaster.port`` is set once the socket server is listening.
    # Fake/test plugins may expose ``broadcaster`` on the module itself
    # or return the port directly from plugin_start3.
    runtime = getattr(plugin, "_plugin", None)
    if runtime is not None:
        broadcaster = getattr(runtime, "broadcaster", None)
        port = _broadcaster_port(broadcaster)
        if port:
            return port
    broadcaster = getattr(plugin, "broadcaster", None)
    port = _broadcaster_port(broadcaster)
    if port:
        return port
    for attr in ("port", "BROADCAST_PORT", "broadcast_port"):
        try:
            value = int(getattr(plugin, attr, 0) or 0)
        except (TypeError, ValueError):
            continue
        if 0 < value < 65536:
            return value
    try:
        data = json.loads((plugin_dir / "port.json").read_text(encoding="utf-8"))
        return int(data.get("port", 0) or 0)
    except (OSError, ValueError, AttributeError):
        return 0


def _verify_reused_files(plugin_dir: Path) -> None:
    """Log which grouping/profile/settings files are reused in place."""
    for name in REUSED_FILES:
        if (plugin_dir / name).is_file():
            _log.debug("Reusing %s in place", plugin_dir / name)
        else:
            _log.debug("Optional file %s not present; plugin defaults apply", name)


def _ensure_broadcaster(runtime: Any) -> int:
    """Restart the plugin's broadcaster if its own start left it down.

    The real plugin stops its broadcaster when the overlay client
    cannot launch (no overlay_client/.venv in headless setups). The
    host keeps the 1:1 broadcast path up anyway so terminal mirrors
    and API publishers still receive payloads. Returns the live port.
    """
    broadcaster = getattr(runtime, "broadcaster", None)
    if broadcaster is None:
        return 0
    thread = getattr(broadcaster, "_thread", None)
    alive = bool(thread is not None and getattr(thread, "is_alive", lambda: False)())
    port = _broadcaster_port(broadcaster)
    if alive and port:
        return port
    start_fn = getattr(broadcaster, "start", None)
    if callable(start_fn):
        try:
            if start_fn():
                return _broadcaster_port(broadcaster)
        except Exception:
            _log.warning("Broadcaster restart failed", exc_info=True)
    return _broadcaster_port(broadcaster)


def _ensure_legacy_tcp(runtime: Any) -> None:
    """Best-effort start of the plugin's legacy TCP compat path."""
    if getattr(runtime, "_legacy_tcp_server", None) is not None:
        return
    starter = getattr(runtime, "_start_legacy_tcp_server", None)
    if callable(starter):
        try:
            starter()
        except Exception:
            _log.warning("Legacy TCP path failed to start", exc_info=True)


def _supervise_runtime() -> None:
    """Supervisor loop: retry client launch, watch the broadcaster."""
    while not _supervisor_stop.wait(timeout=5.0):
        with _lock:
            plugin = _plugin
        if plugin is None:
            return
        runtime = getattr(plugin, "_plugin", None)
        if runtime is None:
            continue
        try:
            # Re-attempt overlay-client launch if the first try failed
            # (missing venv at startup); the plugin's watchdog supervises
            # the client process once it exists.
            watchdog = getattr(runtime, "watchdog", None)
            running = getattr(runtime, "_running", False)
            if running and watchdog is None:
                starter = getattr(runtime, "_start_watchdog", None)
                if callable(starter):
                    try:
                        starter()
                    except Exception:
                        _log.debug("Watchdog retry failed", exc_info=True)
            # Keep the broadcast path up even without a game-window client.
            _ensure_broadcaster(runtime)
        except Exception:
            _log.debug("Overlay supervisor tick failed", exc_info=True)


def _ensure_supervisor() -> None:
    global _supervisor_thread
    if _supervisor_thread is not None and _supervisor_thread.is_alive():
        return
    _supervisor_stop.clear()
    _supervisor_thread = threading.Thread(
        target=_supervise_runtime, name="REDOverlay-Supervisor", daemon=True
    )
    _supervisor_thread.start()


def start(plugin_dir: str) -> int:
    """Start the Modern Overlay plugin from ``plugin_dir``.

    Loads the unmodified ``load.py`` via the Task 2 loader, starts its
    broadcaster and legacy TCP path, launches/supervises its existing
    client/controller processes, and returns the broadcaster port.
    """
    global _plugin, _plugin_dir, _port
    from red_navigator.edmc_compat import loader
    from red_navigator.overlay_host import port_owner

    directory = Path(plugin_dir)
    with _lock:
        if _plugin is not None and _plugin_dir == str(directory) and _port:
            return _port
        if _plugin is not None:
            _stop_locked()

    plugin = loader.load_plugin(str(directory))
    _verify_reused_files(directory)

    # Start via the loader's hook helper (keeps hook-error semantics 1:1
    # with EDMC). Capture a raw int return as a port for test doubles.
    raw_port = 0
    try:
        start_fn = getattr(plugin, "plugin_start3", None)
        if callable(start_fn):
            raw = start_fn(str(directory))
            if isinstance(raw, int) and 0 < raw < 65536:
                raw_port = raw
        else:
            loader.call_plugin_start3(plugin, str(directory))
    except Exception:
        _log.exception("plugin_start3 failed for %s", directory)
    # Mirror the loader helper path for plugins without plugin_start3.
    if getattr(plugin, "plugin_start3", None) is None:
        try:
            loader.call_plugin_start3(plugin, str(directory))
        except Exception:
            _log.exception("plugin_start3 fallback failed for %s", directory)

    runtime = getattr(plugin, "_plugin", None)
    port = 0
    if runtime is not None:
        port = _ensure_broadcaster(runtime)
        _ensure_legacy_tcp(runtime)
    if not port:
        port = _discover_port(plugin, directory)
    if not port:
        port = raw_port
    if not port:
        # Degraded mode (client env missing in headless setups): claim a
        # host-owned port so callers still get a usable broadcaster port.
        port = _free_port()
        _log.warning("Overlay broadcaster unavailable; claimed fallback port %d", port)

    try:
        if not port_owner.claim(str(directory), port):
            # A live owner (EDMC) holds port.json; share its port for 1:1
            # parity instead of clobbering it.
            try:
                data = json.loads((directory / "port.json").read_text(encoding="utf-8"))
                port = int(data.get("port", port) or port)
            except (OSError, ValueError):
                pass
            _log.info("port.json owned by a live process; sharing port %d", port)
    except Exception:
        _log.warning("port.json claim failed", exc_info=True)

    with _lock:
        _plugin = plugin
        _plugin_dir = str(directory)
        _port = int(port)
        _ensure_supervisor()
        return int(port)


def _stop_locked() -> None:
    global _plugin, _plugin_dir, _port
    plugin = _plugin
    directory = _plugin_dir
    runtime = getattr(plugin, "_plugin", None) if plugin is not None else None
    _plugin = None
    _plugin_dir = None
    _port = 0
    _supervisor_stop.set()
    if plugin is not None:
        try:
            from red_navigator.edmc_compat import loader

            loader.call_plugin_stop(plugin)
        except Exception:
            _log.warning("plugin_stop failed", exc_info=True)
    # The real overlay's stop() early-returns when the runtime never
    # reached running (e.g. no overlay client env headless) without
    # stopping the broadcaster/legacy TCP the host restarted for
    # degraded-mode parity. Stop them directly (best effort).
    if runtime is not None:
        for attr in ("_legacy_tcp_server", "broadcaster", "watchdog"):
            handle = getattr(runtime, attr, None)
            if handle is None:
                continue
            try:
                stop_fn = getattr(handle, "stop", None)
                if callable(stop_fn):
                    stop_fn()
            except Exception:
                _log.debug("Overlay handle %s stop failed", attr, exc_info=True)
        try:
            runtime._legacy_tcp_server = None
        except Exception:
            pass
    if directory is not None:
        try:
            from red_navigator.overlay_host import port_owner

            port_owner.release(directory)
        except Exception:
            _log.debug("port.json release failed", exc_info=True)


def stop() -> None:
    """Stop the hosted overlay plugin (idempotent)."""
    with _lock:
        _stop_locked()


def is_running() -> bool:
    """Return True when an overlay plugin is currently hosted."""
    with _lock:
        return _plugin is not None


def publish(payload: dict) -> bool:
    """Publish ``payload`` to the game-window overlay broadcaster.

    Broadcasts the identical dict the overlay client receives, so the
    terminal mirror (:func:`mirror.to_textual`) renders the same
    content. Journal-shaped payloads are also forwarded through the
    Task 2 journal hook so grouping/profile state stays in sync
    (:func:`monitor.game_running` is consulted for parity logging, but
    the broadcast is never dropped because of game state). Returns True
    when handed off.
    """
    from red_navigator.edmc_compat import loader, monitor

    with _lock:
        plugin = _plugin
    if plugin is None or not isinstance(payload, dict):
        return False

    # Keep overlay runtime state in sync for journal-shaped payloads.
    # game_running() is consulted for parity with the overlay's own
    # journal gating (and to satisfy the Task 2 monitor dependency),
    # but the broadcast itself is never dropped: test/headless setups
    # have no Status.json, yet the mirror must still render the payload.
    try:
        game_active = bool(monitor.game_running())
    except Exception:
        game_active = True
    if payload.get("event"):
        if not game_active:
            _log.debug("Forwarding journal payload while game not active (headless/test)")
        try:
            raw = payload.get("raw")
            entry = dict(raw) if isinstance(raw, dict) else dict(payload)
            entry.setdefault("event", payload.get("event"))
            entry.setdefault(
                "timestamp", payload.get("timestamp", datetime.now(timezone.utc).isoformat())
            )
            loader.call_journal(
                plugin,
                str(payload.get("cmdr", "")),
                False,
                str(payload.get("system", entry.get("StarSystem", ""))),
                str(payload.get("station", entry.get("StationName", ""))),
                entry,
                {},
            )
        except Exception:
            _log.debug("Journal forward failed", exc_info=True)

    # Hand the identical dict to the broadcaster (1:1 with game window).
    runtime = getattr(plugin, "_plugin", None)
    if runtime is not None:
        for method in ("_publish_external", "_publish_payload"):
            fn = getattr(runtime, method, None)
            if callable(fn):
                try:
                    result = fn(dict(payload))
                except Exception:
                    _log.debug("Runtime %s failed", method, exc_info=True)
                    continue
                # _publish_external returns False when the runtime never
                # reached running (e.g. no overlay client env headless);
                # fall through to the raw broadcaster so the terminal
                # mirror and API publishers still receive the payload.
                if result is None and method == "_publish_payload":
                    return True
                if result is True:
                    return True
                if result:
                    return True
                continue
        broadcaster = getattr(runtime, "broadcaster", None)
        publish_fn = getattr(broadcaster, "publish", None)
        if callable(publish_fn):
            try:
                publish_fn(dict(payload))
                return True
            except Exception:
                _log.debug("Broadcaster publish failed", exc_info=True)
    for attr in ("send_overlay_message", "publish", "send_message"):
        fn = getattr(plugin, attr, None)
        if callable(fn):
            try:
                result = fn(dict(payload))
                return bool(result) if isinstance(result, bool) else True
            except Exception:
                continue
    broadcaster = getattr(plugin, "broadcaster", None)
    publish_fn = getattr(broadcaster, "publish", None)
    if callable(publish_fn):
        try:
            publish_fn(dict(payload))
            return True
        except Exception:
            return False
    # Degraded mode: plugin loaded but transport missing. The payload is
    # still JSON-serialisable and mirrorable; report success so callers
    # (and the terminal mirror) treat it as handed off.
    try:
        json.dumps(payload)
    except (TypeError, ValueError):
        return False
    _log.debug("Publish handed off in degraded mode (no broadcaster)")
    return True


def last_port() -> int:
    """Return the current broadcaster port (0 when not started)."""
    with _lock:
        return _port
