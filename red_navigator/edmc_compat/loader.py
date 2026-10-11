"""Clean-room EDMC plugin hook dispatcher.

Loads each plugin's ``load.py`` in a per-plugin sandboxed module
namespace so same-named sibling modules (e.g. ``widgets.py`` in two
different plugins) never collide, and dispatches journal/dashboard/cmdr
hooks with EDMC-compatible signatures.

Long-running plugin work must run via :func:`run_in_worker`; worker
threads must never mutate Textual widgets directly — results are
delivered back through the caller-supplied ``on_done`` callback so the
host can forward them with a Textual-safe mechanism such as
``App.call_from_thread``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

_log = logging.getLogger("red_navigator.edmc_compat.loader")

#: Hook names the dispatcher knows how to call.
KNOWN_HOOKS = (
    "plugin_start3",
    "plugin_stop",
    "journal_entry",
    "journal_entry_cqc",
    "dashboard_entry",
    "cmdr_data",
    "plugin_app",
    "plugin_prefs",
    "prefs_changed",
)


def discover_plugins(plugin_dir: str) -> list[str]:
    """Return sorted paths of plugins (dirs containing ``load.py``)."""
    root = Path(plugin_dir)
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []
    found = [str(p) for p in entries if p.is_dir() and (p / "load.py").is_file()]
    # A bare load.py directly in the dir counts as a single plugin too.
    if (root / "load.py").is_file():
        found.insert(0, str(root))
    return found


def _sandbox_name(path: Path) -> str:
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
    stem = "".join(c if (c.isalnum() or c == "_") else "_" for c in path.name)
    return f"_red_plugin_{stem}_{digest}"


def load_plugin(path: str) -> ModuleType:
    """Load a plugin's ``load.py`` into a per-plugin sandbox namespace.

    ``path`` may be the plugin directory or the ``load.py`` file itself.
    The module is registered under a unique name derived from its path,
    and any same-named top-level sibling modules it imports from its own
    directory are re-keyed under that namespace so a later plugin
    importing a same-named sibling gets a fresh module, not the cached
    one. Plugins should still prefer relative imports.
    """
    given = Path(path)
    plugin_dir = given if given.is_dir() else given.parent
    load_py = plugin_dir / "load.py"
    if not load_py.is_file():
        raise FileNotFoundError(f"No load.py in plugin dir: {plugin_dir}")

    pkg_name = _sandbox_name(plugin_dir)
    full_name = f"{pkg_name}.load"

    if full_name in sys.modules:
        return sys.modules[full_name]

    # Synthesise a package so relative imports (``from . import x``)
    # resolve inside the plugin directory.
    pkg = ModuleType(pkg_name)
    pkg.__path__ = [str(plugin_dir)]  # type: ignore[attr-defined]
    sys.modules[pkg_name] = pkg

    spec = importlib.util.spec_from_file_location(
        full_name, load_py, submodule_search_locations=[str(plugin_dir)]
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {load_py}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = pkg_name
    sys.modules[full_name] = module

    before = set(sys.modules)
    sys.path.insert(0, str(plugin_dir))
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(plugin_dir))
        except ValueError:
            pass

    # Re-key sibling modules loaded from this plugin dir out of the
    # global top-level namespace so same-named siblings in other plugins
    # never collide on the sys.modules cache. Attribute bindings already
    # taken by this plugin keep working (they reference the object).
    for name in set(sys.modules) - before - {full_name}:
        if "." in name or name.startswith("_red_plugin_"):
            continue
        mod = sys.modules.get(name)
        mod_file = getattr(mod, "__file__", None)
        if not mod_file:
            continue
        try:
            if Path(mod_file).resolve().is_relative_to(plugin_dir.resolve()):
                sys.modules[f"{pkg_name}.{name}"] = mod
                del sys.modules[name]
        except OSError:
            continue
    return module


def call_plugin_start3(plugin: Any, plugin_dir: str) -> str:
    """Call ``plugin_start3``; fall back to the directory name."""
    fn = getattr(plugin, "plugin_start3", None)
    if callable(fn):
        try:
            name = fn(plugin_dir)
            if isinstance(name, str) and name:
                return name
        except Exception:
            _log.exception("plugin_start3 failed for %s", plugin_dir)
    return Path(plugin_dir).name


def call_plugin_stop(plugin: Any) -> None:
    """Call ``plugin_stop`` if present; never raises."""
    fn = getattr(plugin, "plugin_stop", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            _log.exception("plugin_stop failed for %r", plugin)


def call_journal(
    plugin: Any,
    cmdr: str,
    is_beta: bool,
    system: str,
    station: str,
    entry: dict,
    state: dict,
) -> None:
    """Deliver a journal event to ``plugin.journal_entry`` (no-op if absent)."""
    fn = getattr(plugin, "journal_entry", None)
    if not callable(fn):
        return
    try:
        fn(cmdr, is_beta, system, station, entry, state if state is not None else {})
    except Exception:
        _log.exception(
            "journal_entry failed for event %r", entry.get("event", "?")
        )


def call_journal_cqc(
    plugin: Any,
    cmdr: str,
    is_beta: bool,
    system: str,
    station: str,
    entry: dict,
    state: dict,
) -> None:
    """Deliver a journal event to ``plugin.journal_entry_cqc`` (no-op if absent)."""
    fn = getattr(plugin, "journal_entry_cqc", None)
    if not callable(fn):
        return
    try:
        fn(cmdr, is_beta, system, station, entry, state if state is not None else {})
    except Exception:
        _log.exception(
            "journal_entry_cqc failed for event %r", entry.get("event", "?")
        )


def dispatch_entry(
    plugin: Any,
    entry: dict,
    in_cqc: bool = False,
    cmdr: str = "",
    is_beta: bool = False,
    system: str = "",
    station: str = "",
    state: dict | None = None,
) -> None:
    """Route one journal entry to the CQC or main hook.

    Entries flagged ``in_cqc`` go to ``journal_entry_cqc`` and never to
    ``journal_entry``; all others go to ``journal_entry``.
    """
    if state is None:
        state = {}
    if in_cqc:
        call_journal_cqc(plugin, cmdr, is_beta, system, station, entry, state)
    else:
        call_journal(plugin, cmdr, is_beta, system, station, entry, state)


def call_dashboard(plugin: Any, cmdr: str, is_beta: bool, entry: dict) -> None:
    """Deliver a Status.json update to ``plugin.dashboard_entry``."""
    fn = getattr(plugin, "dashboard_entry", None)
    if not callable(fn):
        return
    try:
        fn(cmdr, is_beta, entry)
    except Exception:
        _log.exception("dashboard_entry failed")


def call_cmdr_data(plugin: Any, data: dict, is_beta: bool = False) -> dict:
    """Pass CAPI commander data through ``plugin.cmdr_data``.

    Returns the plugin's return value when it returns a dict, else the
    input ``data`` unchanged.
    """
    fn = getattr(plugin, "cmdr_data", None)
    if not callable(fn):
        return data
    try:
        result = fn(data, is_beta)
    except Exception:
        _log.exception("cmdr_data failed")
        return data
    return result if isinstance(result, dict) else data


def run_in_worker(
    fn: Callable[..., Any],
    *args: Any,
    on_done: Callable[[Any], None] | None = None,
    name: str = "red-plugin-worker",
) -> threading.Thread:
    """Run ``fn`` on a daemon worker thread.

    The worker must never mutate Textual widgets directly. When ``fn``
    completes, ``on_done(result)`` is invoked on the worker thread; the
    host is responsible for forwarding to the UI thread with a
    Textual-safe mechanism (e.g. ``App.call_from_thread``).
    """
    def _target() -> None:
        try:
            result: Any = fn(*args)
            error: BaseException | None = None
        except BaseException as exc:  # noqa: BLE001 - must not kill host
            result = None
            error = exc
            _log.exception("Plugin worker %s failed", name)
        if on_done is not None:
            try:
                on_done(result)
            except Exception:
                _log.exception("Plugin worker on_done failed")
        if error is not None:
            _log.debug("Plugin worker %s raised %r (contained)", name, error)

    thread = threading.Thread(target=_target, daemon=True, name=name)
    thread.start()
    return thread
