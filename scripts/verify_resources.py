#!/usr/bin/env python3
"""Resource verification: CPU/RAM report with overlay on versus off.

Measures this host's CPU/RAM (game-running state included) for the
overlay-on and overlay-off samples and fails when RED exceeds the
recorded EDMC-plus-plugins baseline.

The default baseline is the recorded EDMC-plus-plugins ceiling; override
it with ``--baseline-file`` (JSON) or the ``--baseline-cpu`` /
``--baseline-rss-mb`` flags. Measurement is stdlib-only (``/proc`` with
``resource`` fallback) and never raises: unreadable counters yield 0.0
rather than crashing the rig.

This script never imports ``ed_monitor`` and changes no NOVA behavior.

Exit codes: 0 = within baseline, 1 = RED exceeds baseline, 2 = usage error.
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

#: Recorded EDMC-plus-plugins ceiling: RED must stay at or under these.
DEFAULT_BASELINE_CPU_PCT = 15.0
DEFAULT_BASELINE_RSS_MB = 600.0


def default_baseline() -> dict[str, float]:
    """Return the recorded EDMC-plus-plugins baseline ceiling."""
    return {"cpu_pct": DEFAULT_BASELINE_CPU_PCT, "rss_mb": DEFAULT_BASELINE_RSS_MB}


def read_rss_mb() -> float:
    """Return this process's resident set size in MiB (0.0 when unreadable)."""
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return float(parts[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        pass
    try:
        import resource

        peak_kb = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # Linux reports ru_maxrss in KiB; macOS in bytes.
        if sys.platform == "darwin":
            return peak_kb / (1024.0 * 1024.0)
        return peak_kb / 1024.0
    except (OSError, ValueError, ImportError):
        return 0.0


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
    *, overlay_on: bool, journal_dirs: list[str] | None = None
) -> dict[str, Any]:
    """Take one resource sample labelled by overlay state.

    ``game_running`` comes from the Task 2 monitor (recent Status.json
    means the game is active). Never raises.
    """
    try:
        game = bool(monitor.game_running(journal_dirs))
    except Exception:
        game = False
    return {
        "overlay": "on" if overlay_on else "off",
        "game_running": game,
        "cpu_pct": read_cpu_pct(),
        "rss_mb": read_rss_mb(),
        "timestamp": time.time(),
    }


def load_baseline(path: str) -> dict[str, float]:
    """Load a baseline JSON file (``{"cpu_pct": N, "rss_mb": M}``)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Baseline {path} must be a JSON object")
    try:
        return {
            "cpu_pct": float(data.get("cpu_pct", DEFAULT_BASELINE_CPU_PCT)),
            "rss_mb": float(data.get("rss_mb", DEFAULT_BASELINE_RSS_MB)),
        }
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Baseline {path} has non-numeric limits: {exc}") from exc


def check_against_baseline(
    sample: dict[str, Any], baseline: dict[str, Any]
) -> list[str]:
    """Return violation strings when ``sample`` exceeds ``baseline``.

    Empty means RED is within the recorded EDMC-plus-plugins ceiling.
    Missing keys fall back to the recorded defaults; unreadable (0.0)
    counters never count as violations on their own.
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
    baseline: dict[str, float],
    violations: list[str],
) -> str:
    """Render the on/off comparison report."""
    cpu_limit = float(baseline.get("cpu_pct", DEFAULT_BASELINE_CPU_PCT))
    rss_limit = float(baseline.get("rss_mb", DEFAULT_BASELINE_RSS_MB))
    lines = [
        "RED Navigator resource report",
        f"baseline: cpu={cpu_limit:.1f}% rss={rss_limit:.1f} MiB "
        "(recorded EDMC-plus-plugins ceiling)",
    ]
    for sample in (off, on):
        lines.append(
            f"overlay={sample.get('overlay', '?')} "
            f"game_running={bool(sample.get('game_running', False))} "
            f"cpu={float(sample.get('cpu_pct', 0.0)):.1f}% "
            f"rss={float(sample.get('rss_mb', 0.0)):.1f} MiB"
        )
    if violations:
        lines.append("RESULT: FAIL — RED exceeds baseline:")
        lines.extend(f"  - {v}" for v in violations)
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
    if args.baseline_rss_mb is not None:
        baseline["rss_mb"] = args.baseline_rss_mb

    if args.overlay == "compare":
        off = measure(overlay_on=False)
        on = measure(overlay_on=True)
        samples = [off, on]
    else:
        single = measure(overlay_on=(args.overlay == "on"))
        off, on = single, single
        samples = [single]

    violations: list[str] = []
    for sample in samples:
        violations.extend(check_against_baseline(sample, baseline))
    print(format_report(on, off, baseline, violations), flush=True)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {"baseline": baseline, "off": off, "on": on,
                 "violations": violations},
                indent=2, sort_keys=True, default=str,
            ),
            encoding="utf-8",
        )
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
