"""Single-owner ``port.json`` claim with stale-file cleanup.

The Modern Overlay broadcaster advertises its port via
``<plugin_dir>/port.json``. Both EDMC and RED Navigator write that
file, so only one owner may hold it at a time. :func:`claim` takes
ownership when the file is missing or stale (previous owner dead or
port no longer listening) and refuses to clobber a live owner — the
stale-file case that happens when EDMC is also installed but not
currently running.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger("red_navigator.overlay_host.port_owner")

OWNER = "red_navigator"


def _is_pid_alive(pid: Any) -> bool:
    try:
        numeric = int(pid)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if numeric <= 0:
        return False
    try:
        os.kill(numeric, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _is_port_open(port: Any) -> bool:
    try:
        numeric = int(port)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if numeric <= 0 or numeric > 65535:
        return False
    try:
        with socket.create_connection(("127.0.0.1", numeric), timeout=0.5):
            return True
    except OSError:
        return False
    return True


def _write_atomically(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _fresh_claim(port: int, existing: dict | None = None) -> dict:
    data: dict[str, Any] = {
        "port": int(port),
        "owner": OWNER,
        "owner_pid": os.getpid(),
        "claimed_at": time.time(),
    }
    # Preserve overlay metadata (version/log_level/flatpak flags) so the
    # overlay client, which reads port.json for discovery, keeps working.
    if isinstance(existing, dict):
        for key in ("version", "log_level", "flatpak", "flatpak_app"):
            if key in existing and key not in data:
                data[key] = existing[key]
    return data


def claim(plugin_dir: str, port: int) -> bool:
    """Claim ``port.json`` in ``plugin_dir`` for ``port``.

    Returns True when this process now owns the file, False when a
    live owner already holds it. A missing, corrupt, or stale file
    (owner PID dead, or advertised port not listening) is replaced.
    """
    try:
        wanted = int(port)
    except (TypeError, ValueError):
        return False
    if wanted <= 0 or wanted > 65535:
        return False
    path = Path(plugin_dir) / "port.json"
    if not path.exists():
        try:
            _write_atomically(path, _fresh_claim(wanted))
        except OSError:
            _log.warning("Could not write %s", path, exc_info=True)
            return False
        return True
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        existing = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Corrupt file can never be a live owner; replace it.
        try:
            _write_atomically(path, _fresh_claim(wanted))
        except OSError:
            return False
        return True
    if not isinstance(existing, dict):
        try:
            _write_atomically(path, _fresh_claim(wanted))
        except OSError:
            return False
        return True
    # Already ours (same process, same port): nothing to do.
    if (
        existing.get("owner") == OWNER
        and existing.get("owner_pid") == os.getpid()
        and existing.get("port") == wanted
    ):
        return True
    # Same process re-claiming a new port (e.g. host restart with a fresh
    # ephemeral broadcaster port): update the file, still ours.
    if existing.get("owner") == OWNER and existing.get("owner_pid") == os.getpid():
        try:
            _write_atomically(path, _fresh_claim(wanted, existing))
        except OSError:
            return False
        return True
    owner_pid = existing.get("owner_pid", existing.get("pid"))
    if owner_pid is not None:
        if _is_pid_alive(owner_pid):
            # Live owner process (EDMC or another RED instance): do not steal.
            return False
        # Dead owner PID: stale file, take ownership.
        try:
            _write_atomically(path, _fresh_claim(wanted, existing))
        except OSError:
            return False
        return True
    # Legacy file without owner metadata (as written by the overlay
    # itself: {"port": N, "version": ...}): probe the advertised port.
    advertised = existing.get("port")
    if advertised is not None:
        try:
            advertised_port = int(advertised)
        except (TypeError, ValueError):
            advertised_port = None
        if advertised_port is not None and _is_port_open(advertised_port):
            # A live broadcaster (likely EDMC's) still owns this file.
            return False
    try:
        _write_atomically(path, _fresh_claim(wanted, existing))
    except OSError:
        return False
    return True


def release(plugin_dir: str) -> bool:
    """Release ``port.json`` if this process owns it. Returns True when removed."""
    path = Path(plugin_dir) / "port.json"
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(existing, dict):
        return False
    if existing.get("owner") != OWNER or existing.get("owner_pid") != os.getpid():
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True
