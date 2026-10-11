"""Read-only tail over Elite Dangerous journal directories.

Mirrors the consumption point pinned as ``NOVA_JOURNAL_TAIL_ENTRY``
(``ed_monitor.journal._follow``: each appended journal line parsed into
an event dict) without importing or altering ``ed_monitor`` behaviour.

Every file here is opened read-only (mode ``"r"``); journals are reference
data and must never be altered.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterator

_log = logging.getLogger("red_navigator.feeds.journal_tail")

_JOURNAL_PREFIX = "Journal."
_JOURNAL_SUFFIX = ".log"

# Proton/Steam compatdata layout for the Windows ED build (appid 359320).
_PROTON_JOURNAL_REL = Path(
    "drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous"
)

# Likely Steam library roots holding compatdata/359320 on Linux.
_STEAM_ROOT_CANDIDATES = (
    Path.home() / ".steam/steam/steamapps",
    Path.home() / ".local/share/Steam/steamapps",
    Path("/media/hdd2/SteamLibrary/steamapps"),
    Path("/media/hdd2/.steam/steam/steamapps"),
)

# Native Linux fallbacks (EDMC data dirs / manual journal copies).
_NATIVE_FALLBACKS = (
    Path.home() / ".local/share/Frontier Developments/Elite Dangerous",
    Path.home() / ".config/EDMarketConnector",
)

#: Env override: one journal dir, or several separated by os.pathsep.
JOURNAL_DIR_ENV = "RED_NAVIGATOR_JOURNAL_DIR"


def journal_dirs() -> list[Path]:
    """Resolve candidate journal directories (existing ones only).

    Order: ``RED_NAVIGATOR_JOURNAL_DIR`` override first, then Proton
    compatdata locations, then native Linux fallbacks.
    """
    found: list[Path] = []

    override = os.environ.get(JOURNAL_DIR_ENV, "")
    for piece in override.split(os.pathsep):
        if piece.strip():
            candidate = Path(piece.strip()).expanduser()
            if candidate.is_dir() and candidate not in found:
                found.append(candidate)

    for root in _STEAM_ROOT_CANDIDATES:
        candidate = root / "compatdata/359320/pfx" / _PROTON_JOURNAL_REL
        if candidate.is_dir() and candidate not in found:
            found.append(candidate)

    for candidate in _NATIVE_FALLBACKS:
        if candidate.is_dir() and candidate not in found:
            found.append(candidate)

    return found


def _journal_files(journal_dir: str | Path) -> list[Path]:
    root = Path(journal_dir)
    try:
        entries = [
            p
            for p in root.iterdir()
            if p.name.startswith(_JOURNAL_PREFIX)
            and p.name.endswith(_JOURNAL_SUFFIX)
            and p.is_file()
        ]
    except OSError as exc:
        _log.debug("Cannot list journal dir %s: %s", root, exc)
        return []
    entries.sort(key=lambda p: p.stat().st_mtime)
    return entries


def iter_entries(journal_dir: str | Path) -> Iterator[dict]:
    """Yield parsed journal event dicts from ``journal_dir``, oldest first.

    Strictly read-only: files are opened with mode ``"r"`` and never
    written, truncated, or had metadata changed. Blank lines and
    malformed JSON lines are skipped with a debug log.
    """
    for path in _journal_files(journal_dir):
        try:
            handle = open(path, "r", encoding="utf-8", errors="replace")
        except OSError as exc:
            _log.debug("Cannot read journal file %s: %s", path, exc)
            continue
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    _log.debug("Skipping malformed line in %s", path.name)
                    continue
                if isinstance(event, dict):
                    yield event
