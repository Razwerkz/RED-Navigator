#!/usr/bin/env python3
"""Resource verification: CPU/RAM report with overlay on versus off.

Samples CPU/RAM for the overlay-on and overlay-off states (own process
by default, or another PID via ``--sample-pid`` for measuring a running
RED Navigator instance) and fails when RED exceeds the EDMC-plus-plugins
baseline.

BASELINE STATUS: the default ceiling below is an UNCALIBRATED placeholder
(not yet measured from a real game-running EDMC-plus-plugins stack). The
report always prints the baseline's provenance (``source``), and
``format_report`` carries an explicit UNCALIBRATED warning until the
defaults are replaced by values from a real measurement pass (see
``--baseline-file``). A PASS verdict additionally requires game-running
context; without it the verdict is INCONCLUSIVE, never PASS.

Measurement is stdlib-only (``/proc`` with ``resource`` fallback) and
never raises: unreadable counters yield 0.0 rather than crashing the rig.

This script never imports ``ed_monitor`` and changes no NOVA behavior.

Exit codes: 0 = within baseline, 1 = RED exceeds baseline (or
--require-game with no game context), 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from red_navigator.edmc_compat import monitor  # noqa: E402

#: Placeholder EDMC-plus-plugins ceiling: RED must stay at or under these.
#: UNCALIBRATED — replace with values from a real game-running measurement
#: pass (see --baseline-file). Provenance is tracked via the "source" key.
DEFAULT_BASELINE_CPU_PCT = 15.0
DEFAULT_BASELINE_RSS_MB = 600.0
PLACEHOLDER_SOURCE = "placeholder-uncalibrated"


def default_baseline() -> dict[str, Any]:
    """Return the placeholder baseline ceiling with its provenance."""
    return {"cpu_pct": DEFAULT_BASELINE_CPU_PCT, "rss_mb": DEFAULT_BASELINE_RSS_MB,
            "source": PLACEHOLDER_SOURCE}


def read_pid_rss_mb(pid: int) -> float:
    """Return PID ``pid``'s resident set size in MiB (0.0 when unreadable)."""
    try:
        with open(f"/proc/{int(pid)}/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return float(parts[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        pass
    if int(pid) == os.getpid():
        try:
            import resource

            peak_kb = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            # Linux reports ru_maxrss in KiB; macOS in bytes.
            if sys.platform == "darwin":
                return peak_kb / (1024.0 * 1024.0)
            return peak_kb / 1024.0
        except (OSError, ValueError, ImportError):
            return 0.0
    return 0.0


def _pid_cpu_ticks(pid: int) -> float | None:
    """Return PID ``pid``'s total user+system CPU ticks, or None when unreadable."""
    try:
        with open(f"/proc/{int(pid)}/stat", "r", encoding="utf-8") as handle:
            fields = handle.read().rsplit(")", 1)[-1].split()
        # utime is field 14, stime field 15 (after the comm field).
        return float(fields[11]) + float(fields[12])
    except (OSError, ValueError, IndexError):
        return None


def _clock_ticks_per_second() -> float:
    try:
        return float(os.sysconf("SC_CLK_TCK"))
    except (OSError, ValueError, AttributeError):
        return 100.0


def read_pid_cpu_pct(pid: int, interval: float = 0.2) -> float:
    """Return PID ``pid``'s CPU use over ``interval`` seconds (percent).

    0.0 when unreadable. Sampling another PID lets the rig measure a
    running RED Navigator instance instead of only itself.
    """
    before = _pid_cpu_ticks(pid)
    if before is None:
        return 0.0
    wall = time.monotonic()
    time.sleep(max(0.0, interval))
    after = _pid_cpu_ticks(pid)
    elapsed_wall = time.monotonic() - wall
    if after is None or elapsed_wall <= 0:
        return 0.0
    return max(0.0, (after - before) / _clock_ticks_per_second()
               / elapsed_wall * 100.0)


def read_rss_mb() -> float:
    """Return this process's resident set size in MiB (0.0 when unreadable)."""
    return read_pid_rss_mb(os.getpid())


def read_cpu_pct(interval: float = 0.2) -> float:
    """Return this process's CPU use over ``interval`` seconds (percent).

    Uses ``os.times()`` deltas over wall time; 0.0 when unreadable.
    """
    try:
        before = os.times()
        wall = time.monotonic()
        time.sleep(max(0.0, interval))
        after = os.times()
        elapsed_wall = time.monotonic() - wall
        if elapsed_wall <= 0:
            return 0.0
        used = (
            (after.user - before.user)
            + (after.system - before.system)
            + (after.children_user - before.children_user)
            + (after.children_system - before.children_system)
        )
        return max(0.0, used / elapsed_wall * 100.0)
    except (OSError, ValueError):
        return 0.0


def measure(
    *, overlay_on: bool, journal_dirs: list[str] | None = None,
    pid: int | None = None,
) -> dict[str, Any]:
    """Take one resource sample labelled by overlay state.

    ``game_running`` comes from the Task 2 monitor (recent Status.json
    means the game is active). ``pid`` selects the sampled process
    (``None`` = this process); pass a RED Navigator PID via
    ``--sample-pid`` to measure RED under game load instead of the rig
    itself. Never raises.
    """
    try:
        game = bool(monitor.game_running(journal_dirs))
    except Exception:
        game = False
    try:
        target = os.getpid() if pid is None else int(pid)
    except (TypeError, ValueError):
        target = os.getpid()
        pid = None
    if pid is None:
        cpu, rss = read_cpu_pct(), read_rss_mb()
    else:
        cpu, rss = read_pid_cpu_pct(target), read_pid_rss_mb(target)
    return {
        "overlay": "on" if overlay_on else "off",
        "game_running": game,
        "cpu_pct": cpu,
        "rss_mb": rss,
        "pid": target,
        "timestamp": time.time(),
    }


def load_baseline(path: str) -> dict[str, Any]:
    """Load a baseline JSON file (``{"cpu_pct": N, "rss_mb": M}``).

    The returned mapping carries ``"source": "file"`` provenance; a
    ``"source"`` key already present in the file (e.g. from a real
    measurement pass) is preserved.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Baseline {path} must be a JSON object")
    try:
        loaded = {
            "cpu_pct": float(data.get("cpu_pct", DEFAULT_BASELINE_CPU_PCT)),
            "rss_mb": float(data.get("rss_mb", DEFAULT_BASELINE_RSS_MB)),
        }
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Baseline {path} has non-numeric limits: {exc}") from exc
    loaded["source"] = data.get("source", "file")
    return loaded


def check_against_baseline(
    sample: dict[str, Any], baseline: dict[str, Any]
) -> list[str]:
    """Return violation strings when ``sample`` exceeds ``baseline``.

    Empty means RED is within the ceiling. Missing keys fall back to the
    placeholder defaults; unreadable (0.0) counters never count as
    violations on their own. Baseline provenance (``source``) is reported,
    never enforced, here.
    """
    try:
        cpu_limit = float(baseline.get("cpu_pct", DEFAULT_BASELINE_CPU_PCT))
        rss_limit = float(baseline.get("rss_mb", DEFAULT_BASELINE_RSS_MB))
    except (TypeError, ValueError):
        return ["baseline limits are non-numeric"]
    try:
        cpu = float(sample.get("cpu_pct", 0.0))
        rss = float(sample.get("rss_mb", 0.0))
    except (TypeError, ValueError):
        return ["sample counters are non-numeric"]
    violations: list[str] = []
    label = str(sample.get("overlay", "?"))
    if cpu > cpu_limit:
        violations.append(
            f"overlay={label} cpu {cpu:.1f}% exceeds baseline {cpu_limit:.1f}%"
        )
    if rss > rss_limit:
        violations.append(
            f"overlay={label} rss {rss:.1f} MiB exceeds baseline {rss_limit:.1f} MiB"
        )
    return violations


def format_report(
    on: dict[str, Any],
    off: dict[str, Any],
    baseline: dict[str, Any],
    violations: list[str],
) -> str:
    """Render the on/off comparison report.

    The baseline provenance (``source``) is always printed; a
    placeholder source adds an explicit UNCALIBRATED warning. PASS is
    only reported with game-running context, otherwise INCONCLUSIVE.
    """
    cpu_limit = float(baseline.get("cpu_pct", DEFAULT_BASELINE_CPU_PCT))
    rss_limit = float(baseline.get("rss_mb", DEFAULT_BASELINE_RSS_MB))
    source = str(baseline.get("source", PLACEHOLDER_SOURCE))
    lines = [
        "RED Navigator resource report",
        f"baseline: cpu={cpu_limit:.1f}% rss={rss_limit:.1f} MiB "
        f"(EDMC-plus-plugins ceiling; source: {source})",
    ]
    if str(source).startswith(PLACEHOLDER_SOURCE):
        lines.append(
            "WARNING: baseline is an UNCALIBRATED placeholder, not a measured "
            "game-running EDMC stack — calibrate via --baseline-file from a "
            "real measurement pass before treating any verdict as binding."
        )
    for sample in (off, on):
        lines.append(
            f"overlay={sample.get('overlay', '?')} "
            f"game_running={bool(sample.get('game_running', False))} "
            f"cpu={float(sample.get('cpu_pct', 0.0)):.1f}% "
            f"rss={float(sample.get('rss_mb', 0.0)):.1f} MiB"
        )
    game_context = bool(on.get("game_running", False)) or bool(
        off.get("game_running", False)
    )
    if violations:
        lines.append("RESULT: FAIL — RED exceeds baseline:")
        lines.extend(f"  - {v}" for v in violations)
    elif not game_context:
        lines.append("RESULT: INCONCLUSIVE — game not running; rerun with the "
                     "game running for a binding PASS verdict.")
    else:
        lines.append("RESULT: PASS — RED within baseline.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report CPU/RAM with overlay on versus off and fail "
                    "when RED exceeds the recorded EDMC-plus-plugins baseline."
    )
    parser.add_argument("--baseline-file", default=None,
                        help="Baseline JSON file {'cpu_pct': N, 'rss_mb': M}.")
    parser.add_argument("--baseline-cpu", type=float, default=None,
                        help="Override baseline CPU ceiling (percent).")
    parser.add_argument("--baseline-rss-mb", type=float, default=None,
                        help="Override baseline RSS ceiling (MiB).")
    parser.add_argument("--overlay", choices=("on", "off", "compare"),
                        default="compare",
                        help="Which sample(s) to take (default: compare).")
    parser.add_argument("--sample-pid", type=int, default=None,
                        help="Sample this PID's CPU/RAM instead of the rig's own "
                             "process (e.g. a running RED Navigator instance).")
    parser.add_argument("--journal-dirs", default=None,
                        help="Journal directories for game-running detection, "
                             f"separated by os.pathsep (default: auto-detect).")
    parser.add_argument("--require-game", action="store_true",
                        help="Exit 1 when the game is not running (no "
                             "game-running context for the verdict).")
    parser.add_argument("--json-out", default=None,
                        help="Write the full report JSON to this path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        baseline = (
            load_baseline(args.baseline_file) if args.baseline_file else default_baseline()
        )
    except (OSError, ValueError) as exc:
        print(f"Cannot load baseline: {exc}", flush=True)
        return 2
    if args.baseline_cpu is not None:
        baseline["cpu_pct"] = args.baseline_cpu
        baseline["source"] = str(baseline.get("source", PLACEHOLDER_SOURCE)) + "+flags"
    if args.baseline_rss_mb is not None:
        baseline["rss_mb"] = args.baseline_rss_mb
        baseline["source"] = str(baseline.get("source", PLACEHOLDER_SOURCE)) + "+flags"

    journal_dirs: list[str] | None = None
    if args.journal_dirs:
        journal_dirs = [p for p in args.journal_dirs.split(os.pathsep) if p.strip()]

    if args.overlay == "compare":
        off = measure(overlay_on=False, journal_dirs=journal_dirs, pid=args.sample_pid)
        on = measure(overlay_on=True, journal_dirs=journal_dirs, pid=args.sample_pid)
        samples = [off, on]
    else:
        single = measure(overlay_on=(args.overlay == "on"),
                         journal_dirs=journal_dirs, pid=args.sample_pid)
        off, on = single, single
        samples = [single]

    violations: list[str] = []
    for sample in samples:
        violations.extend(check_against_baseline(sample, baseline))
    game_context = any(bool(s.get("game_running", False)) for s in samples)
    if args.require_game and not game_context:
        violations.append(
            "no game-running context (game_running=False); rerun with the "
            "game running for a binding verdict"
        )
    print(format_report(on, off, baseline, violations), flush=True)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {"baseline": baseline, "off": off, "on": on,
                 "game_context": game_context, "violations": violations},
                indent=2, sort_keys=True, default=str,
            ),
            encoding="utf-8",
        )
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
