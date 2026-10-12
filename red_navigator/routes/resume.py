"""Resume a stored NavRoute: republish waypoints, copy next, announce.

Headless core: all collaborators are injected callables, so this module
never imports overlay host, clipboard, or TTS internals directly.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

_log = logging.getLogger("red_navigator.routes.resume")


def _waypoint_names(route: Any) -> list[str]:
    """Extract waypoint system names from a stored route dict."""
    if not isinstance(route, dict):
        return []
    entries = route.get("Route")
    if not isinstance(entries, list):
        return []
    names: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("StarSystem") or entry.get("System") or ""
        name = str(name).strip()
        if name:
            names.append(name)
    return names


def resume_route(
    get_route: Callable[[], dict | None],
    publish: Callable[[dict], bool],
    copy: Callable[[str], bool],
    speak: Callable[[str], None],
) -> dict:
    """Republish each waypoint, copy the next one, speak one announce line.

    Returns ``{ok, waypoint, published, copied}`` where ``waypoint`` is
    the next (first) waypoint system name or ``None``. An empty or
    missing route returns a graceful failure after exactly one speak
    line. Never raises — collaborator failures are contained.
    """
    try:
        route = get_route()
    except Exception:
        _log.debug("get_route raised; treating as no route", exc_info=True)
        route = None
    names = _waypoint_names(route)
    if not names:
        try:
            speak("No route plotted.")
        except Exception:
            _log.debug("speak raised on empty route", exc_info=True)
        return {"ok": False, "waypoint": None, "published": 0, "copied": False}

    waypoint = names[0]
    total = len(names)
    published = 0
    for index, name in enumerate(names):
        payload = {
            "event": "RouteResume",
            "system": name,
            "StarSystem": name,
            "waypoint": name,
            "index": index,
            "total": total,
        }
        try:
            if publish(payload):
                published += 1
        except Exception:
            _log.debug("publish raised for waypoint %r", name, exc_info=True)
    try:
        copied = bool(copy(waypoint))
    except Exception:
        _log.debug("copy raised for waypoint %r", waypoint, exc_info=True)
        copied = False
    remaining = total - 1
    try:
        speak(f"Route resumed. Next waypoint {waypoint}, {remaining} remaining.")
    except Exception:
        _log.debug("speak raised on resume announce", exc_info=True)
    return {"ok": True, "waypoint": waypoint, "published": published, "copied": copied}
