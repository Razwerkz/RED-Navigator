"""Per-plugin namespaced key-value config store.

Keys are namespaced per plugin (``"<plugin>:<key>"``) so two plugins
using the same key never see each other's values. Use :func:`scoped` to
bind the ambient plugin name, or pass ``plugin=`` explicitly.

The store is in-memory by default (Task 2 behavior). For settings that
must survive restarts, configure a JSON backing file with
:func:`set_store_path` (or pass an explicit path to :func:`save` /
:func:`load`); :func:`set` then best-effort autosaves without ever
raising for I/O problems.
"""

from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

_log = logging.getLogger("red_navigator.edmc_compat.config_store")

_current_plugin: ContextVar[str] = ContextVar("red_config_plugin", default="")

_lock = threading.RLock()
_store: dict[str, str] = {}
_store_path: str | None = None


@contextmanager
def scoped(plugin_name: str) -> Iterator[None]:
    """Bind ``plugin_name`` as the ambient namespace within the block."""
    token = _current_plugin.set(plugin_name)
    try:
        yield
    finally:
        _current_plugin.reset(token)


def _namespaced(key: str, plugin: str | None) -> str:
    owner = plugin if plugin is not None else _current_plugin.get()
    return f"{owner}:{key}" if owner else key


def get_str(key: str, *, plugin: str | None = None) -> str | None:
    """Return the stored string for ``key``, or ``None`` if unset."""
    with _lock:
        return _store.get(_namespaced(key, plugin))


def set(key: str, value: str, *, plugin: str | None = None) -> None:
    """Store ``value`` (coerced to ``str``) under ``key``."""
    with _lock:
        _store[_namespaced(key, plugin)] = str(value)
        path = _store_path
    if path is not None:
        try:
            save(path)
        except Exception:
            _log.warning("config_store autosave to %s failed", path, exc_info=True)


def delete(key: str, *, plugin: str | None = None) -> None:
    """Remove ``key`` if present."""
    with _lock:
        _store.pop(_namespaced(key, plugin), None)
        path = _store_path
    if path is not None:
        try:
            save(path)
        except Exception:
            _log.warning("config_store autosave to %s failed", path, exc_info=True)


def clear() -> None:
    """Remove all stored keys (used by tests)."""
    with _lock:
        _store.clear()


def set_store_path(path: str | None) -> None:
    """Set (or clear with ``None``) the JSON backing file for autosave.

    When a path is configured, :func:`set`/:func:`delete` best-effort
    persist the whole store after each mutation so settings survive
    restarts. I/O failures are logged, never raised. Default is
    ``None`` (pure in-memory, Task 2 behavior).
    """
    global _store_path
    with _lock:
        _store_path = str(path) if path is not None else None


def get_store_path() -> str | None:
    """Return the configured backing-file path, or ``None``."""
    with _lock:
        return _store_path


def save(path: str | None = None) -> None:
    """Write the whole store as JSON to ``path`` (or the configured one).

    Parent directories are created as needed. Raises ``OSError``/``ValueError``
    on failure when called explicitly; autosave callers contain those.
    """
    target = path if path is not None else get_store_path()
    if target is None:
        raise ValueError("No config_store path configured")
    with _lock:
        snapshot = dict(_store)
    dest = Path(target)
    try:
        if dest.parent and str(dest.parent):
            dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    except (OSError, ValueError, TypeError) as exc:
        raise OSError(f"Cannot save config_store to {dest}: {exc}") from exc


def load(path: str | None = None) -> bool:
    """Merge a JSON file written by :func:`save` into the store.

    Returns ``True`` on success, ``False`` when the file is missing or
    unreadable (missing file is not an error: first run has nothing to
    load). Existing in-memory keys are kept; file keys are added/overwrite
    per key. Never raises.
    """
    target = path if path is not None else get_store_path()
    if target is None:
        return False
    try:
        data = json.loads(Path(target).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    with _lock:
        for key, value in data.items():
            if isinstance(key, str) and isinstance(value, str):
                _store[key] = value
    return True
