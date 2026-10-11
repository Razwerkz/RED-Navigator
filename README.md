# RED Navigator

A terminal-first companion for **Elite Dangerous** on PC. RED Navigator
consolidates a resource-heavy companion stack — standalone EDMC plus its
plugins plus the in-game overlay — into one light process, so you can
close most of the other windows while you fly.

It does this by hosting your existing EDMC plugins and the Modern
Overlay inside a live terminal dashboard, with the same plugin behaviour
and the same game-window overlay you had under EDMC.

> **Fork attribution:** RED Navigator is a fork of
> **NOVA** (Navigation, Operations, and Vessel Assistance) by
> **Nicolas Kerscher**, MIT-licensed —
> https://github.com/KernicDE/nova-ed-monitor —
> pinned at upstream commit
> `8917390f55552b11e24a71fd9cea440136ff0005`
> (v2.20.5). The NOVA base (live journal tail, Status.json dashboard,
> Textual TUI, TTS, routing) is preserved underneath; the RED layer on
> top is described below. See `LICENSE` and
> `docs/superpowers/plans/NOVA_FORK_INVENTORY.md`.

---

## Quick Start

Requirements: **Python 3.11+**, Linux (v1 is Linux-only; the game is
expected via Proton/Steam).

```bash
# from the repo root
.venv/bin/python -m red_navigator.app
```

Useful flags:

```bash
.venv/bin/python -m red_navigator.app --no-overlay   # terminal-only, no game-window overlay
.venv/bin/python -m red_navigator.app --plugin-dir <path>  # override EDMC plugin dir
.venv/bin/python -m red_navigator.app --store-dir <path>   # override RED data dir
```

What happens on launch:

1. The plugin dir defaults to the Proton EDMC install
   (`compatdata/359320/.../AppData/Local/EDMarketConnector/plugins/`,
   probed across Steam library roots, with the native
   `~/.config/EDMarketConnector` as fallback).
2. On first run with no RED data present, settings are imported from
   your EDMC data dir. If the import fails you are asked whether to
   retry or start fresh — it never proceeds silently.
3. The session loads each plugin's `load.py` unchanged, starts the
   overlay host (unless `--no-overlay`), and drops you into the NOVA
   terminal UI with the RED feeds fanning journal/Status events into
   the plugins.

Journal files are **read-only, never altered**. The journal search
covers Proton compatdata locations plus native fallbacks, overridable
via `RED_NAVIGATOR_JOURNAL_DIR`.

---

## What RED Navigator adds (v1)

- **EDMC plugin shim** (`red_navigator/edmc_compat/`): clean-room
  implementation of the documented plugin contract — `plugin_start3`,
  `plugin_stop`, `journal_entry`, `journal_entry_cqc`,
  `dashboard_entry`, the `cmdr_data` family, per-plugin namespaced
  `config` persistence, `monitor.game_running()` /
  `monitor.is_live_galaxy()`, and EDMC-style logging bridging. Each
  plugin's `load.py` loads unchanged in a per-plugin sandbox so
  same-named sibling modules never collide. Target set: the 8
  currently installed plugins (ArtemisScannerTracker-0.3.4b,
  cargo-manifest, docking_denied_reason, EDMC-Canonn-7.8.0,
  EDMCModernOverlay, EDR, EDSM-RSE, HITS).
- **1:1 Modern Overlay host** (`red_navigator/overlay_host/`): runs
  the unmodified Modern Overlay plugin code — same WebSocket
  broadcaster, `port.json` handshake, legacy TCP path, grouping and
  profile stores reused in place. `port.json` uses single-owner
  semantics with stale-file cleanup, so a live EDMC owner is shared,
  never clobbered.
- **Terminal mirror**: every payload sent to the game-window overlay
  is also rendered as text into the terminal event log, so the
  terminal is useful on its own and the external overlay can be
  toggled off for lighter nights.
- **Per-plugin settings UI** (`red_navigator/settings_ui/`): each
  loaded plugin exposing `plugin_prefs` / `prefs_changed` gets a
  settings panel rendered from a generic form layer, hosted in NOVA's
  `s`-key settings overlay. Values persist across restarts and survive
  plugin updates that add new keys.
- **Runtime bridge** (`red_navigator/runtime/` + `feeds/`): journal and
  Status.json feeds are fanned out to all loaded plugins with
  copy-on-dispatch (a misbehaving plugin can never corrupt the live
  event or stall the monitor threads). Broken plugins are skipped with
  a log; overlay failure degrades to terminal-only, never a crash.

## NOVA base (unchanged)

The underlying dashboard is still NOVA: live journal tail with TTS
voicelines, cockpit-style Textual panels (situational, route,
exploration, bio/neutron), config hot-reload, and Proton journal
auto-detection. NOVA-specific guides live in `docs/`:

| Guide | Contents |
|-------|----------|
| [Installation & Update](docs/Installation.md) | NOVA launcher scripts, pip install, data paths, troubleshooting. |
| [Settings](docs/Settings.md) | NOVA `config.toml` keys, voicelines, themes. |
| [Usage Guide](docs/Usage.md) | NOVA keyboard shortcuts and panels. |

Note: those docs describe the NOVA base (including its own
`nova.sh`/`nova.ps1` launchers and Windows/macOS paths). The RED
layer itself is v1 Linux-only and launched via
`python -m red_navigator.app` as above.

---

## Status

v1 (NOVA fork + EDMC shim + 1:1 overlay host + terminal mirror +
per-plugin settings + launcher) is implemented in `red_navigator/`
with headless replay/parity tests under `tests/` (see
`tests/parity/` and `scripts/verify_parity.py`). Full suite:
`.venv/bin/python -m pytest tests/ -q`.

## Roadmap

- **Phase 2 — EDNA behaviour.** Explicitly not in v1 beyond leaving
  room for another integration module.
- **Phase 3 — Discord Rich Presence** (VeeLume /
  Elite-Dangerous-Rich-Presence style). After EDNA.
- No browser dependency and no always-on heavyweight renderer are
  standing constraints: loading plugins must cost less than the stack
  they replace.

---

## License

MIT — see `LICENSE`.

Original NOVA copyright (Nicolas Kerscher, 2025) is retained there
alongside the RED Navigator copyright (Razwerkz, 2026), per the
upstream MIT terms.
