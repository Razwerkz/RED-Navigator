"""EDMC-style plugin state dict built from read-only journal events.

Key semantics callers must honour:

* ``NavRouteClear`` retains the prior ``state["NavRoute"]`` — plugins
  expecting a retained route must keep seeing it, never ``None``.
* ``Body`` set from journal events carries the binary-staleness caveat
  flag ``BodyStale=True``: close-orbiting binary bodies emit no new
  ``ApproachBody``, so journal ``Body`` may be stale. Only an explicit
  ``ApproachBody`` clears the flag. Callers must cross-check with the
  dashboard body name (see :func:`needs_dashboard_crosscheck`) and never
  use journal ``Body`` blindly while the flag is set.
"""

from __future__ import annotations

import copy
from typing import Any


def build_state() -> dict[str, Any]:
    """Return a fresh EDMC-style state dict with default values."""
    return {
        "Commander": "",
        "SystemName": "",
        "SystemAddress": None,
        "StationName": "",
        "StationType": "",
        "Body": "",
        "BodyID": None,
        "BodyType": "",
        # Caveat flag: journal-derived Body may be stale for
        # close-orbiting binaries; cross-check with the dashboard.
        "BodyStale": False,
        "NavRoute": None,
        "Cargo": {},
        "Credits": None,
        "GameMode": "",
        "InCQC": False,
    }


def _set_body(state: dict[str, Any], name: Any, body_id: Any, kind: Any) -> None:
    if isinstance(name, str) and name:
        state["Body"] = name
        state["BodyID"] = body_id if isinstance(body_id, int) else None
        state["BodyType"] = kind if isinstance(kind, str) else ""
        # Journal-sourced body: needs dashboard cross-check.
        state["BodyStale"] = True


def apply_entry(state: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    """Fold one journal ``entry`` into ``state``; returns ``state``."""
    event = entry.get("event", "")

    if event in ("Location", "FSDJump", "CarrierJump"):
        system = entry.get("StarSystem") or entry.get("System") or ""
        if isinstance(system, str) and system:
            state["SystemName"] = system
        address = entry.get("SystemAddress")
        if isinstance(address, int):
            state["SystemAddress"] = address
        station = entry.get("StationName") or ""
        if isinstance(station, str):
            state["StationName"] = station
        station_type = entry.get("StationType") or ""
        if isinstance(station_type, str):
            state["StationType"] = station_type
        if event == "Location":
            _set_body(state, entry.get("Body"), entry.get("BodyID"), entry.get("BodyType"))

    elif event == "ApproachBody":
        # Direct proximity confirmation: clears the staleness caveat.
        name = entry.get("Body") or entry.get("BodyName") or ""
        if isinstance(name, str) and name:
            state["Body"] = name
            body_id = entry.get("BodyID")
            state["BodyID"] = body_id if isinstance(body_id, int) else None
            kind = entry.get("BodyType") or ""
            state["BodyType"] = kind if isinstance(kind, str) else ""
            state["BodyStale"] = False

    elif event in ("Scan", "SAAScanComplete", "FSSBodySignals", "SAASignalsFound"):
        _set_body(
            state,
            entry.get("BodyName") or entry.get("Body"),
            entry.get("BodyID"),
            entry.get("BodyType"),
        )

    elif event == "Docked":
        station = entry.get("StationName") or ""
        if isinstance(station, str) and station:
            state["StationName"] = station
        station_type = entry.get("StationType") or ""
        if isinstance(station_type, str) and station_type:
            state["StationType"] = station_type

    elif event == "Undocked":
        state["StationName"] = ""
        state["StationType"] = ""

    elif event == "NavRoute":
        route = entry.get("Route")
        state["NavRoute"] = {"Route": copy.deepcopy(route) if isinstance(route, list) else []}

    elif event == "NavRouteClear":
        # Retain the prior route: plugins expect state['NavRoute'] to
        # stay readable after the clear event, never reset to None.
        pass

    elif event == "LoadGame":
        commander = entry.get("Commander") or ""
        if isinstance(commander, str) and commander:
            state["Commander"] = commander
        mode = entry.get("GameMode") or ""
        if isinstance(mode, str) and mode:
            state["GameMode"] = mode

    elif event == "StartUp":
        mode = entry.get("GameMode") or state.get("GameMode") or ""
        state["InCQC"] = isinstance(mode, str) and mode.upper() == "CQC"

    elif event in ("Shutdown", "ShutDown"):
        state["InCQC"] = False

    return state


def needs_dashboard_crosscheck(
    state: dict[str, Any], dashboard: dict[str, Any] | None
) -> bool:
    """Return True when journal ``Body`` must be cross-checked with the dashboard.

    True when the binary-staleness caveat flag is set, or when the
    state's ``Body`` disagrees with the dashboard body name. Never use
    journal ``Body`` blindly while this returns True.
    """
    if state.get("BodyStale"):
        return True
    state_body = state.get("Body") or ""
    dash = dashboard or {}
    dash_body = dash.get("Body", dash.get("BodyName", "")) or ""
    if not isinstance(state_body, str):
        state_body = ""
    if not isinstance(dash_body, str):
        dash_body = ""
    return state_body != dash_body
