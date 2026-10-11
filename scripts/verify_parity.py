#!/usr/bin/env python3
"""Parity verification rig: journal replay plus overlay payload diff (EDMC-vs-RED).

Replays read-only sample journals through the Task 2 compatibility shim
for all 8 Proton-baseline plugins, captures the overlay payloads the
game-window broadcaster would receive, and diffs them against
EDMC-captured baselines.

Each captured payload embeds per-plugin observable output (which hook
ran, its return value, any error), so a changed, removed, or broken
plugin always changes the payload and breaks parity — the rig cannot
report false parity when plugins diverge.

Safety contract (never violated):

* Journals and real plugin directories are reference-only: they are
  opened read-only and never created, truncated, or otherwise altered.
* No live hits by default: without ``--allow-live`` the rig replays the
  embedded fixtures only. Real plugin/journal paths are still only read.
* Frontier calls happen only after interactive user auth: ``--allow-live``
  additionally requires the operator to type ``yes`` at an interactive
  prompt (see :func:`require_frontier_auth`). There is no autonomous
  auth path, and non-interactive stdin never authenticates.
* This script never imports ``ed_monitor`` and changes no NOVA behavior.

Baseline honesty: the default offline run diffs against a synthetic
baseline regenerated from the same fixtures (``mode=fixtures-smoke``,
``baseline=synthetic``) — it proves the replay path works but claims
nothing about EDMC. A real parity claim (``PARITY OK``) requires an
EDMC-captured baseline via ``--baseline``.

Exit codes: 0 = parity holds (no diffs), 1 = diffs found or live run
refused/failed safely, 2 = usage error.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from red_navigator.edmc_compat import loader  # noqa: E402
from red_navigator.feeds import journal_tail, state_builder  # noqa: E402
from red_navigator.overlay_host import mirror  # noqa: E402

#: The 8 plugin folders of the Proton Windows EDMC baseline
#: (``.../drive_c/users/steamuser/AppData/Local/EDMarketConnector/plugins/``).
EIGHT_PLUGINS: tuple[str, ...] = (
    "ArtemisScannerTracker-0.3.4b",
    "cargo-manifest",
    "docking_denied_reason",
    "EDMC-Canonn-7.8.0",
    "EDMCModernOverlay",
    "EDR",
    "EDSM-RSE",
    "HITS",
)

#: Read-only sample journal used when no live run is authorised.
DEFAULT_FIXTURE_EVENTS: list[dict[str, Any]] = [
    {"timestamp": "2026-01-01T12:00:00Z", "event": "Fileheader",
     "part": 1, "gameversion": "4.0.0", "build": "r1"},
    {"timestamp": "2026-01-01T12:01:00Z", "event": "LoadGame",
     "Commander": "ParityCMDR", "GameMode": "Open"},
    {"timestamp": "2026-01-01T12:02:00Z", "event": "Location",
     "StarSystem": "Sol", "SystemAddress": 10477373803,
     "StationName": "Daedalus", "StationType": "Coriolis",
     "Body": "Earth", "BodyID": 1, "BodyType": "Planet"},
    {"timestamp": "2026-01-01T12:03:00Z", "event": "FSDJump",
     "StarSystem": "Alpha Centauri", "SystemAddress": 1234567},
    {"timestamp": "2026-01-01T12:04:00Z", "event": "Scan",
     "BodyName": "Alpha Centauri A", "BodyID": 2},
    {"timestamp": "2026-01-01T12:05:00Z", "event": "NavRoute",
     "Route": [{"StarSystem": "Sol"}, {"StarSystem": "Alpha Centauri"}]},
    {"timestamp": "2026-01-01T12:06:00Z", "event": "NavRouteClear"},
    {"timestamp": "2026-01-01T12:07:00Z", "event": "Docked",
     "StationName": "Hutton Orbital", "StationType": "Outpost"},
    {"timestamp": "2026-01-01T12:08:00Z", "event": "Undocked",
     "StationName": "Hutton Orbital"},
    {"timestamp": "2026-01-01T12:09:00Z", "event": "Shutdown"},
]

AUTH_PROMPT = (
    "Live verification will contact Frontier services and load the real "
    "plugin/journal paths (read-only). Type 'yes' to authorise: "
)


def fixture_events() -> list[dict[str, Any]]:
    """Return a deep copy of the embedded read-only sample journal."""
    return copy.deepcopy(DEFAULT_FIXTURE_EVENTS)


def require_frontier_auth(*, allow_live: bool) -> bool:
    """Return True only when live Frontier use is interactively authorised.

    ``allow_live`` must be True (the ``--allow-live`` flag) *and* the
    operator must type ``yes`` at the interactive prompt. Any other
    answer, EOF (non-interactive stdin), or a false flag returns False.
    This function performs no authentication itself; it only records the
    operator's explicit consent. There is intentionally no way to grant
    consent non-interactively.
    """
    if not allow_live:
        return False
    if not sys.stdin.isatty():
        return False
    try:
        answer = input(AUTH_PROMPT)
    except (EOFError, OSError):
        return False
    return answer.strip().lower() == "yes"


class _RecordingPlugin:
    """In-memory stand-in for one of the 8 baseline plugins (fixture mode)."""

    def __init__(self, name: str, log: list[tuple[str, dict[str, Any]]]) -> None:
        self._name = name
        self._log = log

    def journal_entry(self, cmdr, is_beta, system, station, entry, state):
        self._log.append((self._name, dict(entry)))
        return f"{self._name}:saw:{entry.get('event', '?')}"

    def journal_entry_cqc(self, cmdr, is_beta, system, station, entry, state):
        self._log.append((self._name, dict(entry)))
        return f"{self._name}:saw-cqc:{entry.get('event', '?')}"


def fixture_plugins() -> dict[str, _RecordingPlugin]:
    """Return one recording stand-in per baseline plugin name."""
    log: list[tuple[str, dict[str, Any]]] = []
    return {name: _RecordingPlugin(name, log) for name in EIGHT_PLUGINS}


def load_plugin_report(
    plugin_dir: str, wanted: tuple[str, ...] = EIGHT_PLUGINS
) -> dict[str, Any]:
    """Load real plugins from ``plugin_dir`` (read-only; never writes).

    Returns ``{"modules": {name: module | None}, "errors": {name: str},
    "missing": [names]}`` for the wanted baseline names. A name is
    missing when its folder is absent *or* its ``load.py`` raised during
    import — the error text is recorded, never swallowed, so the exact
    V1 incompatibility surfaces in the result. Loading only executes
    each plugin's ``load.py`` in the Task 2 sandbox; nothing is written
    back.
    """
    found = loader.discover_plugins(plugin_dir)
    by_name = {Path(p).name: p for p in found}
    modules: dict[str, Any | None] = {}
    errors: dict[str, str] = {}
    missing: list[str] = []
    for name in wanted:
        path = by_name.get(name)
        if path is None:
            modules[name] = None
            missing.append(name)
            continue
        try:
            modules[name] = loader.load_plugin(path)
        except Exception as exc:
            modules[name] = None
            errors[name] = f"{type(exc).__name__}: {exc}"
            missing.append(name)
    return {"modules": modules, "errors": errors, "missing": missing}


def load_plugin_modules(
    plugin_dir: str, wanted: tuple[str, ...] = EIGHT_PLUGINS
) -> dict[str, Any | None]:
    """Back-compat wrapper returning only the modules mapping.

    Prefer :func:`load_plugin_report`, which also records per-plugin
    load errors instead of silently mapping failures to ``None``.
    """
    return load_plugin_report(plugin_dir, wanted)["modules"]  # type: ignore[return-value]


def _json_safe(value: Any) -> Any:
    """Return ``value`` if JSON-round-trippable, else its ``repr``."""
    try:
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return repr(value)
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _invoke_hook(
    plugin: Any,
    *,
    in_cqc: bool,
    cmdr: str,
    is_beta: bool,
    system: str,
    station: str,
    entry: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Invoke one plugin hook and capture its observable output.

    Routing mirrors :func:`loader.dispatch_entry` exactly (``in_cqc``
    entries go to ``journal_entry_cqc`` and never to ``journal_entry``;
    all others go to ``journal_entry``), but unlike the loader — which
    discards hook returns and logs away exceptions — the record
    ``{"hook", "called", "result", "error"}`` is returned so plugin
    behaviour participates in the parity diff.
    """
    hook = "journal_entry_cqc" if in_cqc else "journal_entry"
    fn = getattr(plugin, hook, None)
    if not callable(fn):
        return {"hook": hook, "called": False, "result": None, "error": None}
    try:
        result = fn(cmdr, is_beta, system, station, entry, state)
    except Exception as exc:
        return {
            "hook": hook,
            "called": True,
            "result": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {"hook": hook, "called": True, "result": _json_safe(result),
            "error": None}


def _overlay_payload(
    entry: dict[str, Any], state: dict[str, Any], cmdr: str
) -> dict[str, Any]:
    """Build the overlay payload base for one journal event.

    This is the identical dict shape the game-window broadcaster
    receives (see ``overlay_host.host.publish``); ``mirror`` renders the
    same dict for the terminal pane, so capturing it here covers both.
    Per-plugin records are attached by :func:`replay_entries`.
    """
    payload = {
        "event": str(entry.get("event", "")),
        "system": str(state.get("SystemName", "") or ""),
        "station": str(state.get("StationName", "") or ""),
        "cmdr": cmdr,
    }
    payload["mirror"] = mirror.to_textual(payload)
    return payload


def replay_entries(
    entries: list[dict[str, Any]],
    plugins: dict[str, Any],
    *,
    cmdr: str = "",
    is_beta: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Replay ``entries`` through ``plugins`` via the Task 2 shim.

    Entries are folded into an EDMC-style state dict (Task 2
    ``state_builder``), routed per entry by the live CQC flag with the
    same rule as Task 2 ``dispatch_entry``, and captured as overlay
    payloads. Every payload embeds each plugin's observable output, so
    changing, removing, or breaking any plugin changes the payloads.
    Returns ``(payloads, summary)``.
    """
    state = state_builder.build_state()
    payloads: list[dict[str, Any]] = []
    delivered_total = 0
    hook_errors: dict[str, list[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        state = state_builder.apply_entry(state, entry)
        system = str(state.get("SystemName", "") or "")
        station = str(state.get("StationName", "") or "")
        in_cqc = bool(state.get("InCQC", False))
        per_plugin: dict[str, Any] = {}
        delivered = 0
        for name, plugin in plugins.items():
            key = str(name)
            if plugin is None:
                per_plugin[key] = {
                    "hook": "journal_entry_cqc" if in_cqc else "journal_entry",
                    "called": False,
                    "result": None,
                    "error": "plugin not loaded",
                }
                hook_errors.setdefault(key, []).append("plugin not loaded")
                continue
            record = _invoke_hook(
                plugin, in_cqc=in_cqc, cmdr=cmdr, is_beta=is_beta,
                system=system, station=station, entry=entry, state=state,
            )
            per_plugin[key] = record
            if record["called"]:
                delivered += 1
                delivered_total += 1
            if record["error"] is not None:
                hook_errors.setdefault(key, []).append(str(record["error"]))
        payload = _overlay_payload(entry, state, cmdr)
        payload["deliveries"] = delivered
        payload["plugins"] = per_plugin
        payloads.append(payload)
    summary = {
        "events": len(payloads),
        "plugins": sorted(str(n) for n in plugins),
        "deliveries": delivered_total,
        "errors": hook_errors,
    }
    return payloads, summary


def replay_journal_dir(
    journal_dir: str, plugins: list[Any] | dict[str, Any], **kwargs: Any
) -> list[dict[str, Any]]:
    """Replay a real journal directory (strictly read-only) through ``plugins``.

    Files are read via :func:`journal_tail.iter_entries`, which opens
    journals with mode ``"r"`` and never writes. ``plugins`` may be a
    list of plugin objects or a name->plugin mapping.
    """
    mapping = (
        plugins if isinstance(plugins, dict)
        else {f"plugin-{i}": p for i, p in enumerate(plugins)}
    )
    entries = list(journal_tail.iter_entries(journal_dir))
    payloads, _ = replay_entries(entries, mapping, **kwargs)
    return payloads


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def diff_payloads(
    red: list[dict[str, Any]], baseline: list[dict[str, Any]]
) -> list[str]:
    """Diff RED-captured payloads against EDMC-captured baselines.

    Comparison covers the full canonical payload including per-plugin
    hook records. Returns human-readable diff lines; empty means 1:1
    parity.
    """
    diffs: list[str] = []
    if len(red) != len(baseline):
        diffs.append(
            f"payload count differs: RED={len(red)} EDMC-baseline={len(baseline)}"
        )
    for index, (got, want) in enumerate(zip(red, baseline)):
        if _canonical(got) == _canonical(want):
            continue
        diffs.append(f"--- payload[{index}] EDMC-baseline")
        diffs.append(f"+++ payload[{index}] RED")
        diffs.extend(
            difflib.unified_diff(
                json.dumps(want, indent=2, sort_keys=True, default=str).splitlines(),
                json.dumps(got, indent=2, sort_keys=True, default=str).splitlines(),
                lineterm="",
            )
        )
    return diffs


def load_baseline(path: str) -> list[dict[str, Any]]:
    """Load an EDMC-captured baseline payload file (JSON list)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Baseline {path} must be a JSON list of payloads")
    return [entry for entry in data if isinstance(entry, dict)]


def _synthetic_baseline() -> list[dict[str, Any]]:
    """Regenerate the fixture expectation (labels the run as smoke, not parity)."""
    expected, _ = replay_entries(fixture_events(), fixture_plugins())
    return expected


def run(
    *,
    journal_dir: str | None = None,
    plugin_dir: str | None = None,
    baseline: list[dict[str, Any]] | None = None,
    baseline_path: str | None = None,
    allow_live: bool = False,
    allow_partial: bool = False,
    fixtures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run one verification pass; never raises for missing live inputs.

    Fixture smoke (default): replay embedded fixtures through per-plugin
    recording stand-ins and diff against a synthetic baseline
    (``mode=fixtures-smoke``, ``baseline=synthetic``). This exercises the
    full replay path but claims nothing about EDMC.

    Fixture comparison: same replay with an EDMC-captured ``baseline``
    (``mode=fixtures``, ``baseline=supplied``).

    Live mode: only when ``allow_live`` *and* interactive auth succeeds
    *and* both real paths exist; replays the real journal dir through
    the real 8 plugins (read-only). A live run fails unless all 8
    plugins load, or ``allow_partial`` records the skip reason per
    missing plugin. Otherwise falls back to fixtures-smoke and records
    the refusal in the result.
    """
    baseline_kind = "supplied" if (baseline is not None or baseline_path) else None
    if baseline_path is not None:
        baseline = load_baseline(baseline_path)

    live_ok = (
        allow_live
        and require_frontier_auth(allow_live=True)
        and bool(journal_dir)
        and bool(plugin_dir)
        and Path(str(journal_dir)).is_dir()
        and Path(str(plugin_dir)).is_dir()
    )
    if live_ok:
        assert journal_dir is not None and plugin_dir is not None
        report = load_plugin_report(plugin_dir)
        modules = report["modules"]
        present = {k: v for k, v in modules.items() if v is not None}
        missing: list[str] = report["missing"]
        load_errors: dict[str, str] = report["errors"]
        if missing and not allow_partial:
            diffs = [f"missing plugin: {name}" for name in missing]
            diffs += [f"load error {name}: {err}"
                      for name, err in load_errors.items()]
            return {
                "mode": "live",
                "baseline": baseline_kind or "none",
                "events": 0,
                "plugins": sorted(present),
                "missing": missing,
                "load_errors": load_errors,
                "skipped": [],
                "payloads": [],
                "diffs": diffs,
                "ok": False,
            }
        skipped = (
            [{"plugin": name,
              "reason": ("not present under plugin dir; recorded skip via "
                         "--allow-partial" if name not in load_errors
                         else f"load failed ({load_errors[name]}); recorded "
                              "skip via --allow-partial")}
             for name in missing]
            if allow_partial else []
        )
        payloads = replay_journal_dir(journal_dir, present)
        mode = "live"
        names = sorted(present)
        extra: dict[str, Any] = {
            "missing": missing, "load_errors": load_errors, "skipped": skipped,
        }
    else:
        events = copy.deepcopy(fixtures) if fixtures is not None else fixture_events()
        plugins = fixture_plugins()
        payloads, summary = replay_entries(events, plugins)
        names = summary["plugins"]
        extra = {"hook_errors": summary["errors"]}
        if not allow_live:
            reason = "fixture mode (no --allow-live: no live hits)"
        elif journal_dir is None or plugin_dir is None:
            reason = "fixture mode (live paths not supplied)"
        else:
            reason = "fixture mode (live not authorised or paths missing)"
        extra["reason"] = reason
        if baseline is None:
            mode = "fixtures-smoke"
            baseline_kind = "synthetic"
        else:
            mode = "fixtures"

    if baseline is None:
        if mode == "live":
            baseline = []
            baseline_kind = "none"
        else:
            # Synthetic default: proves the path works; NOT an EDMC claim.
            baseline = _synthetic_baseline()
            baseline_kind = "synthetic"

    diffs = diff_payloads(payloads, baseline)
    if baseline_kind == "none":
        diffs.insert(
            0, "no EDMC baseline supplied (--baseline is required for a parity claim)"
        )
    result: dict[str, Any] = {
        "mode": mode,
        "baseline": baseline_kind,
        "events": len(payloads),
        "plugins": names,
        "payloads": payloads,
        "diffs": diffs,
        "ok": not diffs,
    }
    result.update(extra)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay journals through the RED shim and diff overlay "
                    "payloads against EDMC-captured baselines."
    )
    parser.add_argument("--journal-dir", default=None,
                        help="Real journal directory (read-only; live mode only).")
    parser.add_argument("--plugin-dir", default=None,
                        help="Real EDMC plugin directory (read-only; live mode only).")
    parser.add_argument("--baseline", default=None,
                        help="EDMC-captured baseline payload JSON file.")
    parser.add_argument("--allow-live", action="store_true",
                        help="Permit a live (read-only) replay; still requires "
                             "interactive 'yes' auth at the prompt.")
    parser.add_argument("--allow-partial", action="store_true",
                        help="Live mode: proceed when some of the 8 plugins are "
                             "missing/unloadable, recording a skip reason per "
                             "plugin. Without it the run fails.")
    parser.add_argument("--json-out", default=None,
                        help="Write the full result JSON to this path "
                             "(never inside a journal/plugin dir).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.allow_live and os.environ.get("RED_NAVIGATOR_ALLOW_LIVE") == "":
        print("Live run disabled for this session; using fixtures.", flush=True)
        args.allow_live = False
    try:
        result = run(
            journal_dir=args.journal_dir,
            plugin_dir=args.plugin_dir,
            baseline_path=args.baseline,
            allow_live=args.allow_live,
            allow_partial=args.allow_partial,
        )
    except (OSError, ValueError) as exc:
        print(f"parity run failed safely: {exc}", flush=True)
        return 1
    summary = (
        f"mode={result['mode']} baseline={result.get('baseline', '?')} "
        f"events={result['events']} plugins={len(result['plugins'])} "
        f"diffs={len(result['diffs'])}"
    )
    if result["ok"] and result.get("baseline") == "synthetic":
        print(f"SMOKE OK ({summary})", flush=True)
        print("WARNING: synthetic baseline — replay path works, but this "
              "claims nothing about EDMC parity. Supply --baseline with an "
              "EDMC-captured payload file for a real parity claim.", flush=True)
    elif result["ok"]:
        print(f"PARITY OK ({summary})", flush=True)
    else:
        print(f"PARITY MISMATCH ({summary})", flush=True)
        for line in result["diffs"][:50]:
            print(line, flush=True)
    if args.json_out:
        out = Path(args.json_out)
        journal_root = Path(args.journal_dir).resolve() if args.journal_dir else None
        plugin_root = Path(args.plugin_dir).resolve() if args.plugin_dir else None
        resolved = out.resolve()
        for root in (journal_root, plugin_root):
            if root is not None and resolved.is_relative_to(root):
                print(f"Refusing to write inside reference-only dir: {out}",
                      flush=True)
                return 2
        out.write_text(json.dumps(result, indent=2, sort_keys=True, default=str),
                       encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
