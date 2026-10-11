"""Parity rig for all 8 Proton-baseline plugins.

Replays read-only sample journals through the Task 2 shim for the 8
plugins installed in the Proton EDMC baseline
(ArtemisScannerTracker-0.3.4b, cargo-manifest, docking_denied_reason,
EDMC-Canonn-7.8.0, EDMCModernOverlay, EDR, EDSM-RSE, HITS), captures
overlay payloads, and diffs them against EDMC-captured baselines.

Constraints honoured here: journals and real plugin dirs are
reference-only (read, never written); Frontier calls happen only after
interactive user auth (never autonomous); no live hits by default —
fixture replay only.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path

import pytest

SCRIPTS_DIR = Path("scripts")


def _load_script(name: str):
    path = SCRIPTS_DIR / name
    spec = importlib.util.spec_from_file_location(
        f"parity_scripts_{name.replace('.py', '')}", path
    )
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parity_script_exists():
    import pathlib
    assert pathlib.Path("scripts/verify_parity.py").exists()
    assert pathlib.Path("scripts/verify_resources.py").exists()


def test_eight_plugin_names_match_proton_baseline():
    parity = _load_script("verify_parity.py")
    assert tuple(parity.EIGHT_PLUGINS) == (
        "ArtemisScannerTracker-0.3.4b",
        "cargo-manifest",
        "docking_denied_reason",
        "EDMC-Canonn-7.8.0",
        "EDMCModernOverlay",
        "EDR",
        "EDSM-RSE",
        "HITS",
    )


def test_fixture_replay_makes_no_live_hits(monkeypatch):
    """Fixture replay must never touch the network (no live hits by default)."""
    import socket

    parity = _load_script("verify_parity.py")

    def _no_network(*args, **kwargs):
        raise AssertionError("live network hit during fixture replay")

    monkeypatch.setattr(socket, "socket", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)
    result = parity.run(allow_live=False)
    assert result["mode"] == "fixtures-smoke"
    assert result["baseline"] == "synthetic"
    assert result["events"] > 0
    assert len(result["payloads"]) == result["events"]
    assert result["ok"] is True


def test_replay_leaves_journals_and_plugins_untouched(tmp_path):
    """Journals and plugin dirs are reference-only: replay never alters them."""
    parity = _load_script("verify_parity.py")

    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()
    journal_file = journal_dir / "Journal.260101120000.01.log"
    lines = [
        {"timestamp": "2026-01-01T12:00:00Z", "event": "Fileheader"},
        {"timestamp": "2026-01-01T12:01:00Z", "event": "LoadGame",
         "Commander": "ParityCMDR", "GameMode": "Open"},
        {"timestamp": "2026-01-01T12:02:00Z", "event": "FSDJump",
         "StarSystem": "Sol", "SystemAddress": 10477373803},
        {"timestamp": "2026-01-01T12:03:00Z", "event": "NavRouteClear"},
    ]
    journal_file.write_text(
        "\n".join(json.dumps(entry) for entry in lines) + "\n", encoding="utf-8"
    )
    plugin_dir = tmp_path / "EDMCModernOverlay"
    plugin_dir.mkdir()
    load_py = plugin_dir / "load.py"
    load_py.write_text(
        "seen = []\n"
        "def plugin_start3(plugin_dir):\n"
        "    return 'FixtureOverlay'\n"
        "def journal_entry(cmdr, is_beta, system, station, entry, state):\n"
        "    seen.append(entry.get('event'))\n",
        encoding="utf-8",
    )
    before_journal = journal_file.read_bytes()
    before_plugin = load_py.read_bytes()

    modules = parity.load_plugin_modules(str(tmp_path))
    assert modules.get("EDMCModernOverlay") is not None
    seen_plugins = [m for m in modules.values() if m is not None]
    payloads = parity.replay_journal_dir(str(journal_dir), seen_plugins)
    assert len(payloads) == len(lines)

    assert journal_file.read_bytes() == before_journal
    assert load_py.read_bytes() == before_plugin


def test_overlay_payload_diff_detects_mismatch():
    parity = _load_script("verify_parity.py")
    payloads = [
        {"event": "FSDJump", "system": "Sol", "station": "", "cmdr": "", "mirror": "x"}
    ]
    assert parity.diff_payloads(payloads, [dict(p) for p in payloads]) == []
    altered = [dict(payloads[0], system="Alpha Centauri")]
    diffs = parity.diff_payloads(payloads, altered)
    assert diffs, "payload mismatch must produce a diff"
    count_diffs = parity.diff_payloads(payloads, payloads + altered)
    assert count_diffs, "payload count mismatch must produce a diff"


class _HealthyPlugin:
    def journal_entry(self, *args):
        return "pong"

    def journal_entry_cqc(self, *args):
        return "pong-cqc"


class _BrokenPlugin:
    def journal_entry(self, *args):
        raise RuntimeError("boom")

    def journal_entry_cqc(self, *args):
        raise RuntimeError("boom")


class _HooklessPlugin:
    pass


def test_plugin_behavior_captured_in_payloads():
    """Payloads must change when plugin behaviour changes (no false parity)."""
    parity = _load_script("verify_parity.py")
    entries = [{"event": "FSDJump", "StarSystem": "Sol"}]

    first, _ = parity.replay_entries(entries, {"P": _HealthyPlugin()})
    second, _ = parity.replay_entries(entries, {"P": _HealthyPlugin()})
    assert parity.diff_payloads(first, second) == []
    assert first[0]["plugins"]["P"]["called"] is True
    assert first[0]["plugins"]["P"]["result"] == "pong"
    assert first[0]["plugins"]["P"]["error"] is None

    # Removing the plugin changes the payload.
    removed, _ = parity.replay_entries(entries, {})
    assert parity.diff_payloads(first, removed), "removed plugin must break parity"

    # A hookless plugin is recorded as not called — and differs.
    hookless, _ = parity.replay_entries(entries, {"P": _HooklessPlugin()})
    assert hookless[0]["plugins"]["P"]["called"] is False
    assert parity.diff_payloads(first, hookless), "hookless plugin must break parity"


def test_broken_plugin_error_recorded_and_differs():
    """A raising plugin records its error in the payload (never swallowed)."""
    parity = _load_script("verify_parity.py")
    entries = [{"event": "FSDJump", "StarSystem": "Sol"}]

    healthy, _ = parity.replay_entries(entries, {"P": _HealthyPlugin()})
    broken, summary = parity.replay_entries(entries, {"P": _BrokenPlugin()})
    record = broken[0]["plugins"]["P"]
    assert record["called"] is True
    assert record["result"] is None
    assert "RuntimeError" in str(record["error"]) and "boom" in str(record["error"])
    assert summary["errors"] == {"P": [record["error"]]}
    assert parity.diff_payloads(healthy, broken), "broken plugin must break parity"


def test_load_plugin_report_records_errors_and_missing(tmp_path):
    """Load failures surface per-plugin errors instead of silent None."""
    parity = _load_script("verify_parity.py")
    good = tmp_path / "EDMCModernOverlay"
    good.mkdir()
    (good / "load.py").write_text(
        "def plugin_start3(plugin_dir):\n    return 'OK'\n", encoding="utf-8"
    )
    bad = tmp_path / "EDR"
    bad.mkdir()
    (bad / "load.py").write_text("raise ValueError('incompatible API')\n",
                                 encoding="utf-8")

    report = parity.load_plugin_report(str(tmp_path))
    assert report["modules"]["EDMCModernOverlay"] is not None
    assert report["modules"]["EDR"] is None
    assert "EDR" in report["errors"]
    assert "ValueError" in report["errors"]["EDR"]
    assert "incompatible API" in report["errors"]["EDR"]
    # One present, seven missing (six absent plus the unloadable one).
    assert len(report["missing"]) == 7
    assert "EDR" in report["missing"] and "HITS" in report["missing"]
    # Back-compat wrapper keeps its mapping shape.
    assert parity.load_plugin_modules(str(tmp_path))["EDMCModernOverlay"] is not None


def _write_live_dirs(tmp_path):
    plugin_dir = tmp_path / "plugins"
    overlay = plugin_dir / "EDMCModernOverlay"
    overlay.mkdir(parents=True)
    (overlay / "load.py").write_text(
        "def plugin_start3(plugin_dir):\n"
        "    return 'LiveOverlay'\n"
        "def journal_entry(cmdr, is_beta, system, station, entry, state):\n"
        "    return 'live-pong'\n",
        encoding="utf-8",
    )
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()
    (journal_dir / "Journal.260101120000.01.log").write_text(
        json.dumps({"timestamp": "2026-01-01T12:00:00Z", "event": "FSDJump",
                    "StarSystem": "Sol"}) + "\n",
        encoding="utf-8",
    )
    return str(journal_dir), str(plugin_dir)


def test_live_partial_plugin_set_strict_vs_allowed(tmp_path, monkeypatch):
    """Live runs fail on a partial 8-plugin set unless --allow-partial records skips."""
    import socket

    parity = _load_script("verify_parity.py")
    journal_dir, plugin_dir = _write_live_dirs(tmp_path)
    monkeypatch.setattr(parity, "require_frontier_auth",
                        lambda *, allow_live: True)

    def _no_network(*args, **kwargs):
        raise AssertionError("live replay must stay offline for fixture journals")

    monkeypatch.setattr(socket, "socket", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)

    strict = parity.run(journal_dir=journal_dir, plugin_dir=plugin_dir,
                        allow_live=True)
    assert strict["mode"] == "live"
    assert strict["ok"] is False
    assert len(strict["missing"]) == 7
    assert any("missing plugin: EDR" in d for d in strict["diffs"])

    allowed = parity.run(journal_dir=journal_dir, plugin_dir=plugin_dir,
                         allow_live=True, allow_partial=True)
    assert allowed["mode"] == "live"
    assert allowed["plugins"] == ["EDMCModernOverlay"]
    assert len(allowed["skipped"]) == 7
    assert all(s["reason"] for s in allowed["skipped"])
    assert allowed["events"] == 1
    assert allowed["payloads"][0]["plugins"]["EDMCModernOverlay"]["result"] == \
        "live-pong"


def test_fixture_smoke_labelled_synthetic_not_edmc_parity():
    """Default run is smoke (synthetic); --baseline upgrades it to a parity claim."""
    parity = _load_script("verify_parity.py")
    smoke = parity.run()
    assert smoke["mode"] == "fixtures-smoke"
    assert smoke["baseline"] == "synthetic"
    assert smoke["ok"] is True

    claimed = parity.run(baseline=copy.deepcopy(smoke["payloads"]))
    assert claimed["mode"] == "fixtures"
    assert claimed["baseline"] == "supplied"
    assert claimed["ok"] is True


def test_frontier_calls_require_interactive_auth(monkeypatch):
    """Frontier auth is user-directed: never granted without live flag + yes."""
    parity = _load_script("verify_parity.py")

    class _Tty:
        def isatty(self):
            return True

    # Interactive terminal for the consent cases below.
    monkeypatch.setattr("sys.stdin", _Tty())
    # Flag off: even an eager "yes" must not authenticate (no autonomous auth).
    monkeypatch.setattr("builtins.input", lambda *a, **k: "yes")
    assert parity.require_frontier_auth(allow_live=False) is False
    # Flag on but user declines.
    monkeypatch.setattr("builtins.input", lambda *a, **k: "no")
    assert parity.require_frontier_auth(allow_live=True) is False
    # Flag on and user explicitly confirms.
    monkeypatch.setattr("builtins.input", lambda *a, **k: "yes")
    assert parity.require_frontier_auth(allow_live=True) is True
    # Non-interactive stdin (EOF) never authenticates.
    def _eof(*a, **k):
        raise EOFError
    monkeypatch.setattr("builtins.input", _eof)
    assert parity.require_frontier_auth(allow_live=True) is False


def test_verify_parity_fixture_mode_passes(capsys):
    parity = _load_script("verify_parity.py")
    assert parity.main([]) == 0
    out = capsys.readouterr().out
    assert "SMOKE OK" in out
    assert "synthetic" in out


def test_verify_parity_supplied_baseline_claims_parity(tmp_path, capsys):
    """With an EDMC-captured --baseline file, a matching run prints PARITY OK."""
    parity = _load_script("verify_parity.py")
    smoke = parity.run()
    baseline_file = tmp_path / "edmc_baseline.json"
    baseline_file.write_text(json.dumps(smoke["payloads"]), encoding="utf-8")
    assert parity.main(["--baseline", str(baseline_file)]) == 0
    out = capsys.readouterr().out
    assert "PARITY OK" in out
    assert "SMOKE" not in out


def test_resources_pass_within_baseline():
    resources = _load_script("verify_resources.py")
    sample = {"cpu_pct": 2.0, "rss_mb": 120.0, "overlay": "on", "game_running": True}
    baseline = {"cpu_pct": 15.0, "rss_mb": 600.0}
    assert resources.check_against_baseline(sample, baseline) == []


def test_resources_fail_when_red_exceeds_baseline():
    resources = _load_script("verify_resources.py")
    baseline = {"cpu_pct": 15.0, "rss_mb": 600.0}
    over_cpu = {"cpu_pct": 99.9, "rss_mb": 120.0, "overlay": "on",
                "game_running": True}
    over_ram = {"cpu_pct": 2.0, "rss_mb": 99999.0, "overlay": "on",
                "game_running": True}
    assert resources.check_against_baseline(over_cpu, baseline)
    assert resources.check_against_baseline(over_ram, baseline)


def _mock_measure(monkeypatch, resources, *, game_running):
    fixed_on = {"cpu_pct": 2.0, "rss_mb": 120.0, "overlay": "on",
                "game_running": game_running, "pid": 1, "timestamp": 0.0}
    fixed_off = {"cpu_pct": 1.0, "rss_mb": 100.0, "overlay": "off",
                 "game_running": game_running, "pid": 1, "timestamp": 0.0}
    calls = []

    def _fake_measure(*, overlay_on, journal_dirs=None, pid=None):
        calls.append((overlay_on, journal_dirs, pid))
        return dict(fixed_on if overlay_on else fixed_off)

    monkeypatch.setattr(resources, "measure", _fake_measure)
    return calls


def test_verify_resources_main_modes(monkeypatch, capsys):
    resources = _load_script("verify_resources.py")
    calls = _mock_measure(monkeypatch, resources, game_running=True)
    assert resources.main([]) == 0
    assert [c[0] for c in calls] == [False, True]
    out = capsys.readouterr().out
    assert "overlay=off" in out and "overlay=on" in out
    assert "UNCALIBRATED" in out
    # RED over baseline must fail.
    assert resources.main(["--baseline-rss-mb", "10", "--baseline-cpu", "0.5"]) == 1


def test_placeholder_baseline_flagged_without_game(monkeypatch, capsys):
    """Placeholder provenance is printed; no game context means INCONCLUSIVE, not PASS."""
    resources = _load_script("verify_resources.py")
    _mock_measure(monkeypatch, resources, game_running=False)
    assert resources.main([]) == 0
    out = capsys.readouterr().out
    assert "placeholder-uncalibrated" in out
    assert "UNCALIBRATED" in out
    assert "INCONCLUSIVE" in out
    assert "RESULT: PASS" not in out


def test_require_game_fails_without_game_context(monkeypatch, capsys):
    resources = _load_script("verify_resources.py")
    _mock_measure(monkeypatch, resources, game_running=False)
    assert resources.main(["--require-game"]) == 1
    out = capsys.readouterr().out
    assert "no game-running context" in out

    _mock_measure(monkeypatch, resources, game_running=True)
    assert resources.main(["--require-game"]) == 0
    out = capsys.readouterr().out
    assert "RESULT: PASS" in out


def test_sample_pid_measures_given_process():
    """--sample-pid plumbing reads the target PID's counters (self here)."""
    resources = _load_script("verify_resources.py")
    if not Path("/proc/self/status").is_file():
        pytest.skip("no /proc — pid sampling unavailable")
    self_pid = os.getpid()
    assert resources.read_pid_rss_mb(self_pid) > 0.0
    assert resources.read_pid_cpu_pct(self_pid, interval=0.01) >= 0.0
    sample = resources.measure(overlay_on=True, pid=self_pid)
    assert sample["pid"] == self_pid
    assert sample["rss_mb"] > 0.0


def test_scripts_never_touch_ed_monitor():
    """Task 6 is scripts-only: no ed_monitor imports, no behavior change."""
    import re

    pattern = re.compile(r"^\s*(import|from)\s+ed_monitor", re.MULTILINE)
    for name in ("verify_parity.py", "verify_resources.py"):
        source = (SCRIPTS_DIR / name).read_text(encoding="utf-8")
        assert pattern.search(source) is None, (
            f"{name} must not import ed_monitor"
        )


@pytest.fixture(autouse=True)
def _no_live_by_default(monkeypatch):
    # Belt-and-braces: no test in this module may perform a live hit.
    monkeypatch.setenv("RED_NAVIGATOR_ALLOW_LIVE", "")
