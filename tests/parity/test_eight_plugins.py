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

import importlib.util
import json
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
    assert result["mode"] == "fixtures"
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
    assert "fixtures" in out


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


def test_verify_resources_main_modes(monkeypatch, capsys):
    resources = _load_script("verify_resources.py")
    fixed_on = {"cpu_pct": 2.0, "rss_mb": 120.0, "overlay": "on",
                "game_running": True}
    fixed_off = {"cpu_pct": 1.0, "rss_mb": 100.0, "overlay": "off",
                 "game_running": True}
    calls = []

    def _fake_measure(*, overlay_on, journal_dirs=None):
        calls.append(overlay_on)
        return dict(fixed_on if overlay_on else fixed_off)

    monkeypatch.setattr(resources, "measure", _fake_measure)
    assert resources.main([]) == 0
    assert calls == [False, True]
    out = capsys.readouterr().out
    assert "overlay=off" in out and "overlay=on" in out
    # RED over baseline must fail.
    assert resources.main(["--baseline-rss-mb", "10", "--baseline-cpu", "0.5"]) == 1


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
