"""RED runtime fan-out: journal + dashboard dispatch to RED plugins.

Module-level plugin registry plus no-op-when-empty :func:`journal_entry`
/ :func:`dashboard_entry` that fan out through
:mod:`red_navigator.edmc_compat.loader` (``dispatch_entry`` /
``call_dashboard``) and :mod:`red_navigator.overlay_host.host`
(``publish``). Every plugin exception is logged, never raised, so a
broken plugin can never stall the NOVA monitor threads.

Delivery is copy-on-dispatch: each plugin receives its own shallow
copy of the entry/data/state dicts, so a mutating (or hostile) plugin
can neither corrupt the caller's dict (e.g. NOVA's live journal event)
nor affect what later plugins see.

The enabled flag is flipped by :mod:`red_navigator.runtime.session`:
the ``ed_monitor`` hooks check :func:`is_enabled` before calling in, so
upstream behavior is byte-identical when no RED session runs. Direct
calls to :func:`journal_entry` / :func:`dashboard_entry` always fan out
regardless of the flag (that is how the tests below drive them).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

_log = logging.getLogger("red_navigator.runtime.fanout")

_lock = threading.RLock()

#: True once session.start() has run and before session.stop().
_enabled: bool = False

#: Plugins loaded by the current session (see session.start).
_session_plugins: list[Any] = []

#: Test-only plugins (see register_test_plugin/clear_test_plugins).
_test_plugins: list[Any] = []

#: Last commander seen via journal ctx (dashboard_entry has no ctx arg).
_last_cmdr: str = ""
_last_is_beta: bool = False


def is_enabled() -> bool:
    """Return True when a RED session is running (hooks should fan out)."""
    with _lock:
        return _enabled


def set_enabled(value: bool) -> None:
    """Flip the fan-out enabled flag (session lifecycle use)."""
    global _enabled
    with _lock:
        _enabled = bool(value)


def register_plugin(plugin: Any) -> None:
    """Add a session ``plugin`` to the registry (deduped by identity)."""
    if plugin is None:
        return
    with _lock:
        if not any(p is plugin for p in _session_plugins):
            _session_plugins.append(plugin)


def unregister_plugin(plugin: Any) -> None:
    """Remove a session ``plugin`` from the registry (identity match)."""
    with _lock:
        _session_plugins[:] = [p for p in _session_plugins if p is not plugin]


def clear_session_plugins() -> None:
    """Remove all session plugins (used by session.stop)."""
    with _lock:
        _session_plugins.clear()


def register_test_plugin(plugin: Any) -> None:
    """Add a test-only ``plugin`` (deduped by identity)."""
    if plugin is None:
        return
    with _lock:
        if not any(p is plugin for p in _test_plugins):
            _test_plugins.append(plugin)


def clear_test_plugins() -> None:
    """Remove all test-only plugins."""
    with _lock:
        _test_plugins.clear()


def _targets() -> list[Any]:
    with _lock:
        return list(_session_plugins) + list(_test_plugins)


def journal_entry(entry: dict, ctx: dict) -> None:
    """Fan out one journal ``entry`` to every registered plugin + overlay.

    ``ctx`` carries ``cmdr``/``is_beta``/``system``/``station``/``state``
    (all optional; missing keys fall back to EDMC-neutral defaults) and
    an optional ``in_cqc`` flag routing to ``journal_entry_cqc``. Each
    plugin gets its own copy of ``entry``/``state``; the caller's dicts
    are never altered. Never raises.
    """
    try:
        if not isinstance(entry, dict):
            _log.debug("journal_entry: ignoring non-dict entry %r", type(entry))
            return
        if not isinstance(ctx, dict):
            ctx = {}
        try:
            cmdr = str(ctx.get("cmdr", "") or "")
        except Exception:
            cmdr = ""
        try:
            is_beta = bool(ctx.get("is_beta", False))
        except Exception:
            is_beta = False
        try:
            system = str(ctx.get("system", "") or "")
        except Exception:
            system = ""
        try:
            station = str(ctx.get("station", "") or "")
        except Exception:
            station = ""
        state = ctx.get("state", {})
        if not isinstance(state, dict):
            state = {}
        try:
            in_cqc = bool(ctx.get("in_cqc", False))
        except Exception:
            in_cqc = False

        global _last_cmdr, _last_is_beta
        with _lock:
            if cmdr:
                _last_cmdr = cmdr
                _last_is_beta = is_beta

        from red_navigator.edmc_compat import loader

        for plugin in _targets():
            try:
                loader.dispatch_entry(
                    plugin, dict(entry),
                    in_cqc=in_cqc, cmdr=cmdr, is_beta=is_beta,
                    system=system, station=station, state=dict(state),
                )
            except Exception:
                _log.exception("journal_entry fan-out failed for %r", plugin)

        try:
            from red_navigator.overlay_host import host

            host.publish(dict(entry))
        except Exception:
            _log.debug("journal_entry overlay publish failed", exc_info=True)
    except Exception:
        _log.exception("fanout.journal_entry failed")


def dashboard_entry(data: dict) -> None:
    """Fan out one parsed Status.json ``data`` dict + overlay publish.

    Commander context comes from the last journal call (dashboard feed
    carries no cmdr). Each plugin gets its own copy of ``data``; the
    caller's dict is never altered. Never raises.
    """
    try:
        if not isinstance(data, dict):
            _log.debug("dashboard_entry: ignoring non-dict data %r", type(data))
            return
        with _lock:
            cmdr = _last_cmdr
            is_beta = _last_is_beta

        from red_navigator.edmc_compat import loader

        for plugin in _targets():
            try:
                loader.call_dashboard(plugin, cmdr, is_beta, dict(data))
            except Exception:
                _log.exception("dashboard_entry fan-out failed for %r", plugin)

        try:
            from red_navigator.overlay_host import host

            host.publish(dict(data))
        except Exception:
            _log.debug("dashboard_entry overlay publish failed", exc_info=True)
    except Exception:
        _log.exception("fanout.dashboard_entry failed")
