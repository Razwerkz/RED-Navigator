"""Neutron star route planner — Spansh API only.

Submits an async job to the Spansh neutron router and polls until the result
arrives. Every system in the Spansh response (boosted and non-boosted) is
forwarded to the UI as-is.

Queue messages: ("plot", target_system_name)
State written: neutron_route, neutron_route_to, neutron_route_status
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

from ._http import USER_AGENT, TIMEOUT_SHORT, TIMEOUT_MEDIUM
from .state import AppState

_log = logging.getLogger("nova.neutron")

_SPANSH_ROUTE_URL   = "https://spansh.co.uk/api/route"
_SPANSH_RESULTS_URL = "https://spansh.co.uk/api/results/{}"
_SPANSH_TIMEOUT     = 120   # seconds to wait for result


def spawn(state: AppState, lock: threading.RLock) -> queue.Queue:
    q: queue.Queue = queue.Queue()
    threading.Thread(
        target=_worker,
        args=(q, state, lock),
        daemon=True,
        name="nova-neutron",
    ).start()
    return q


# ── Worker ─────────────────────────────────────────────────────────────────────

def _worker(q: queue.Queue, state: AppState, lock: threading.RLock) -> None:
    while True:
        try:
            msg = q.get(timeout=300.0)
        except queue.Empty:
            continue

        if not isinstance(msg, tuple) or len(msg) < 2 or msg[0] != "plot":
            continue

        target_name: str = msg[1]
        if not target_name:
            continue

        with lock:
            jump_range = state.jump_range_last if state.jump_range_last > 0 else state.jump_range
            cur_system = state.system

        if not cur_system or jump_range <= 0.0:
            with lock:
                state.neutron_route_status = "error"
                state.neutron_route        = []
                state.neutron_route_to     = target_name
            _log.warning("Neutron plotter: no system or jump range available.")
            continue

        with lock:
            state.neutron_route_status = "plotting"
            state.neutron_route        = []
            state.neutron_route_to     = target_name

        _log.info(f"Neutron plotter: {cur_system} → {target_name}  range={jump_range:.1f} ly")

        route = _spansh_route(cur_system, target_name, jump_range)

        with lock:
            state.neutron_route        = route or []
            state.neutron_route_to     = target_name
            state.neutron_route_status = "done" if route else "error"

        _log.info(f"Neutron plotter: {len(route) if route else 0} hops.")


# ── Spansh API ─────────────────────────────────────────────────────────────────

def _hops_to_route(jumps: list) -> list[dict]:
    """Normalise Spansh `system_jumps` entries to {system, neutron, distance, jumps}."""
    route = []
    for j in jumps:
        if not isinstance(j, dict):
            continue
        dist = float(j.get("distance_jumped") or j.get("distance") or 0.0)
        route.append({
            "system":   j.get("system", "?"),
            "neutron":  bool(j.get("neutron_star", False)),
            "distance": dist,
            "jumps":    int(j.get("jumps") or 0),  # regular hops to reach this waypoint
        })
    return route


def _spansh_route(src: str, dst: str, jump_range: float) -> Optional[list[dict]]:
    """Submit neutron route job to Spansh, poll until done.
    Returns list of {system, neutron, distance} or None on failure."""

    params = urllib.parse.urlencode({
        "from":       src,
        "to":         dst,
        "efficiency": 60,
        "range":      f"{jump_range:.2f}",
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            _SPANSH_ROUTE_URL,
            data=params,
            headers={
                "User-Agent":   USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_MEDIUM) as resp:
            data = json.loads(resp.read())
        job_id = data.get("job")
        if not job_id:
            _log.warning(f"Spansh: unexpected submit response: {data}")
            return None
    except Exception as exc:
        _log.warning(f"Spansh submit failed: {exc}")
        return None

    _log.info(f"Spansh job: {job_id}")
    poll_url = _SPANSH_RESULTS_URL.format(job_id)

    for _ in range(_SPANSH_TIMEOUT):
        time.sleep(1.0)
        try:
            req = urllib.request.Request(poll_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT_SHORT) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            _log.debug(f"Spansh poll error: {exc}")
            continue

        status = data.get("status", "")
        if status == "ok":
            jumps = (data.get("result") or {}).get("system_jumps") or []
            _log.info(f"Spansh done: {len(jumps)} hops")
            route = _hops_to_route(jumps)
            return route or None
        elif status == "error":
            _log.warning(f"Spansh error: {data}")
            return None

    _log.warning(f"Spansh timed out after {_SPANSH_TIMEOUT}s")
    return None


# ── Live plotting with offline fallback ──────────────────────────────────────
#
# plot_neutron_live() tries the keyless live Spansh neutron router first with an
# explicit timeout, then falls back to the offline neutron-dump path on any
# failure. NOTE: this function blocks on network I/O — callers must execute it
# off the UI thread (e.g. the nova-neutron worker or a background future).

_DEFAULT_LIVE_RANGE = 30.0   # ly; the Spansh router needs a jump range and this
                             # entry point carries no ship state, so use a sane default.
_POLL_STEP = 2.0             # seconds between live result polls


def _fetch_live(origin: str, destination: str, timeout_s: float) -> dict:
    """Perform the single bounded live request against the Spansh neutron router.

    Submits the route job then polls until done, all within `timeout_s`.
    Returns {"route": [hop, ...]}. May raise (including TimeoutError);
    callers (plot_neutron_live) translate any failure into offline fallback.
    No API key required — the Spansh neutron router is keyless.
    """
    budget = max(0.1, float(timeout_s))
    deadline = time.monotonic() + budget

    params = urllib.parse.urlencode({
        "from":       origin,
        "to":         destination,
        "efficiency": 60,
        "range":      f"{_DEFAULT_LIVE_RANGE:.2f}",
    }).encode("utf-8")

    req = urllib.request.Request(
        _SPANSH_ROUTE_URL,
        data=params,
        headers={
            "User-Agent":   USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=min(budget, TIMEOUT_MEDIUM)) as resp:
        data = json.loads(resp.read())
    job_id = data.get("job") if isinstance(data, dict) else None
    if not job_id:
        raise ValueError(f"unexpected live submit response: {data!r:.120}")

    poll_url = _SPANSH_RESULTS_URL.format(job_id)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"live Spansh neutron route {origin} → {destination} "
                f"timed out after {timeout_s:g}s"
            )
        time.sleep(min(_POLL_STEP, remaining))
        try:
            req = urllib.request.Request(poll_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=min(remaining, TIMEOUT_SHORT)) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            _log.debug(f"Spansh live poll error: {exc}")
            continue

        status = data.get("status", "") if isinstance(data, dict) else ""
        if status == "ok":
            jumps = (data.get("result") or {}).get("system_jumps") or []
            return {"route": _hops_to_route(jumps)}
        elif status == "error":
            raise RuntimeError(f"live Spansh router error: {data!r:.160}")


def _plot_offline(origin: str, destination: str) -> tuple[Optional[list[dict]], str]:
    """Offline neutron-dump fallback path.

    Returns (route | None, reason). No local neutron-star dump cache is wired
    into the plotter yet, so this seam currently reports unavailability; it
    exists so the systems_neutron dump can be plugged in without touching the
    live path or its callers.
    """
    _ = (origin, destination)
    return None, "no cached offline neutron dump available"


def plot_neutron_live(origin: str, destination: str, *, timeout_s: float = 15.0) -> dict:
    """Plot a neutron route, live Spansh first with offline-dump fallback.

    Blocks on network I/O — callers must execute off the UI thread.
    Returns {ok, route: list | None, source: "live" | "offline", notice: str}
    where `notice` always explains which source served the route.
    """
    try:
        payload = _fetch_live(origin, destination, timeout_s)
        route = payload.get("route") if isinstance(payload, dict) else None
        if not route:
            raise ValueError("live Spansh response contained no route")
        return {
            "ok":     True,
            "route":  route,
            "source": "live",
            "notice": (
                f"Live Spansh neutron route {origin} → {destination}: "
                f"{len(route)} waypoint(s)."
            ),
        }
    except Exception as exc:
        route, reason = _plot_offline(origin, destination)
        if route:
            return {
                "ok":     True,
                "route":  route,
                "source": "offline",
                "notice": (
                    f"Live Spansh request failed ({exc}); "
                    f"fallback to offline dump ({reason}): {len(route)} waypoint(s)."
                ),
            }
        return {
            "ok":     False,
            "route":  None,
            "source": "offline",
            "notice": (
                f"Live Spansh request failed ({exc}); "
                f"fallback to offline dump: {reason}."
            ),
        }
