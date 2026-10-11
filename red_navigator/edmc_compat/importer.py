"""First-run EDMC data import (copy-only).

On first run with no RED Navigator data present, the TUI offers to
import data from the Proton EDMC config/plugin dirs. The import is
strictly copy-only: the source tree is only ever read, never deleted
or modified. Journal files are never written (read-only constraint).

On failure :func:`import_if_empty` returns ``"failed"`` so the TUI
can ask the user to set up fresh or retry (see
:func:`fresh_setup_prompt`).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from . import config_store

_log = logging.getLogger("red_navigator.edmc_compat.importer")

#: config_store key recording where the seed data was copied from.
IMPORT_SOURCE_KEY = "import_source"

#: Namespace used for importer keys in config_store.
IMPORT_PLUGIN = "red_navigator.importer"


def _red_store_has_data(red_store: Path) -> bool:
    """Return True when the red store already holds data."""
    if config_store.get_str(IMPORT_SOURCE_KEY, plugin=IMPORT_PLUGIN) is not None:
        return True
    try:
        if red_store.is_file():
            return True
        if red_store.is_dir():
            return any(red_store.iterdir())
    except OSError:
        _log.warning("Could not list red store %s", red_store, exc_info=True)
        return True
    return False


def import_if_empty(red_store: str, edmc_source: str) -> str:
    """Copy EDMC data into ``red_store`` when it is empty.

    Returns ``"imported"`` on success, ``"already-present"`` when the
    red store already holds data (source is left untouched), and
    ``"failed"`` when the source is missing/unreadable or any copy
    step fails. The source tree is never deleted or modified.
    """
    dest = Path(red_store)
    if _red_store_has_data(dest):
        return "already-present"
    try:
        src = Path(edmc_source)
        if not src.is_dir():
            return "failed"
        if src.resolve() == dest.resolve():
            return "failed"
        dest.mkdir(parents=True, exist_ok=True)
        for entry in sorted(src.iterdir(), key=lambda p: p.name):
            target = dest / entry.name
            if entry.is_symlink():
                # Copy what the link points at; never recreate links
                # that could escape the dest tree on later reads.
                pointed = entry.resolve()
                if pointed.is_dir():
                    shutil.copytree(pointed, target, dirs_exist_ok=True)
                elif pointed.is_file():
                    shutil.copy2(pointed, target)
                # Dangling links are skipped, never followed out.
            elif entry.is_dir():
                shutil.copytree(entry, target, dirs_exist_ok=True)
            elif entry.is_file():
                shutil.copy2(entry, target)
            # Sockets, fifos, and other special files are skipped.
        config_store.set(IMPORT_SOURCE_KEY, str(src), plugin=IMPORT_PLUGIN)
    except OSError:
        _log.warning(
            "EDMC import failed (source=%s dest=%s)", edmc_source, red_store,
            exc_info=True,
        )
        return "failed"
    return "imported"


def fresh_setup_prompt() -> str:
    """Return the TUI prompt asking fresh-or-retry after a failed import."""
    return (
        "Could not import EDMC data. "
        "Set up fresh with empty defaults, or retry the import? "
        "[fresh/retry]: "
    )
