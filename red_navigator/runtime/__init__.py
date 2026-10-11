"""RED runtime bridge: plugin lifecycle plus journal/dashboard fan-out.

Owns the RED session (plugin discovery/loading, settings panels,
overlay host) and the fan-out path the ``ed_monitor`` hooks tap into.
Additive towards ``ed_monitor/``: with no session started the hooks
are no-ops and upstream behavior is unchanged.
"""

from __future__ import annotations

from . import fanout, session

__all__ = ["fanout", "session"]
