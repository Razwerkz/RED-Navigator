"""Per-plugin namespaced key-value config store.

Keys are namespaced per plugin (``"<plugin>:<key>"``) so two plugins
using the same key never see each other's values. Use :func:`scoped` to
bind the ambient plugin name, or pass ``plugin=`` explicitly.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_current_plugin: ContextVar[str] = ContextVar("red_config_plugin", default="")

_lock = threading.RLock()
_store: dict[str, str] = {}


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


def delete(key: str, *, plugin: str | None = None) -> None:
    """Remove ``key`` if present."""
    with _lock:
        _store.pop(_namespaced(key, plugin), None)


def clear() -> None:
    """Remove all stored keys (used by tests)."""
    with _lock:
        _store.clear()
