"""Game/client status helpers (read-only).

``game_running`` mirrors the NOVA status-feed notion of "recent
Status.json means the game is active" without touching ``ed_monitor``
behaviour; ``is_live_galaxy`` reports whether the commander is in the
live galaxy as opposed to beta or the CQC arena.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

# Status.json older than this means the game is not actively writing.
GAME_ACTIVE_MAX_AGE_S = 300.0


def _status_candidates(journal_dirs: Iterable[str | Path] | None) -> list[Path]:
    if journal_dirs is not None:
        return [Path(d) / "Status.json" for d in journal_dirs]
    # Lazy import: feeds never imports edmc_compat, so no cycle.
    from red_navigator.feeds.journal_tail import journal_dirs as _dirs

    return [d / "Status.json" for d in _dirs()]


def game_running(journal_dirs: Iterable[str | Path] | None = None) -> bool:
    """Return True if any known Status.json was written recently."""
    now = time.time()
    for status_path in _status_candidates(journal_dirs):
        try:
            age = now - status_path.stat().st_mtime
        except OSError:
            continue
        if 0 <= age < GAME_ACTIVE_MAX_AGE_S:
            return True
    return False


def is_live_galaxy(is_beta: bool = False, in_cqc: bool = False) -> bool:
    """Return False when in beta or in the CQC arena, else True."""
    return not (is_beta or in_cqc)
