"""Read-only dashboard feed (Status.json and siblings).

Mirrors the consumption point pinned as ``NOVA_STATUS_FEED_ENTRY``
(``ed_monitor.status._apply_status``: Status.json parsed into a data
dict) without importing or altering ``ed_monitor`` behaviour.

All reads are read-only; files are never written.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger("red_navigator.feeds.dashboard_feed")

STATUS_FILENAME = "Status.json"


def load_dashboard(journal_dir: str | Path) -> dict[str, Any] | None:
    """Read and parse ``Status.json`` from ``journal_dir`` (read-only).

    ``journal_dir`` may also be the ``Status.json`` file path itself.
    Returns the parsed dict, or ``None`` when missing/unparseable.
    """
    given = Path(journal_dir)
    path = given if given.is_file() else given / STATUS_FILENAME
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        _log.debug("Cannot read dashboard file %s: %s", path, exc)
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        _log.debug("Dashboard file %s is not valid JSON", path)
        return None
    return data if isinstance(data, dict) else None


def dashboard_body(dashboard: dict[str, Any] | None) -> str:
    """Return the dashboard's current body name (``""`` when unknown)."""
    if not dashboard:
        return ""
    body = dashboard.get("BodyName", "")
    return body if isinstance(body, str) else ""
