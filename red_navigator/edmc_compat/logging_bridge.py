"""Bridge EDMC-style plugin logging to stdlib :mod:`logging`.

Plugins get a child logger named
``red_navigator.plugins.<plugin_name>`` so host log configuration,
levels, and handlers apply uniformly.
"""

from __future__ import annotations

import logging
import sys

_ROOT_NAME = "red_navigator.plugins"


def get_plugin_logger(plugin_name: str) -> logging.Logger:
    """Return the stdlib logger for ``plugin_name``."""
    safe = "".join(c if (c.isalnum() or c in "_-.") else "_" for c in plugin_name)
    return logging.getLogger(f"{_ROOT_NAME}.{safe or 'unknown'}")


def install(level: int = logging.INFO) -> logging.Logger:
    """Ensure the RED Navigator root logger has a stderr handler.

    Returns the ``red_navigator`` root logger. Safe to call multiple
    times; never removes existing handlers.
    """
    root = logging.getLogger("red_navigator")
    root.setLevel(level)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s"))
        root.addHandler(handler)
    return root
