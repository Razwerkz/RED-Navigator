# RED Navigator — Design (v1: NOVA fork + EDMC + 1:1 Overlay)

Date: 2026-10-11
Status: draft for review, not approved for build

## Intent and why

RED Navigator (Razwerkz Elite Dangerous Navigator) is a terminal-first companion app for Elite Dangerous on PC, aimed at consolidating a resource-heavy companion stack into one light process.

Today the user flies with EDCoPilot, ED Market Connector plus plugins, EDNA, the elite-dangerous-route-widget, sometimes EDOMH and ODEliteTracker, plus a web browser on top. On their Linux setup (Elite via Proton, Steam compatdata on `/media/hdd2`) that sprawl costs enough CPU and RAM to matter while the game itself runs.

Why now: someone shared a NOVA build (KernicDE/nova-ed-monitor) that already does live terminal dashboard plus TTS plus routing in one Python Textual app. That proved the shape. RED Navigator takes that shape as the starting point and adds the compatibility layers the user actually depends on, so they can close most of the other windows.

V1 wins if the user can shut down standalone EDMC and still get the same plugin behavior and the same in-game overlay, from inside one terminal app.

## Goals (v1)

1. Fork NOVA as the base. Keep its live journal tail, Status.json dashboard feed, Textual TUI structure, situational plus route plus exploration panels, config hot-reload pattern, and Proton journal auto-detection. Apply RED Navigator naming and theming after the integration works (coat of paint last).
2. Load the user's existing EDMC plugins unchanged from their current install path (`.../AppData/Local/EDMarketConnector/plugins/`). V1 target: all currently installed plugins should be compatible, preferably. Confirmed set (8 folders observed): ArtemisScannerTracker-0.3.4b, cargo-manifest, docking_denied_reason, EDMC-Canonn-7.8.0, EDMCModernOverlay, EDR, EDSM-RSE, HITS. All expose `load.py`. [User decision 2026-10-11.]
3. Implement an EDMC core shim sufficient for those plugins: `plugin_start3(plugin_dir) -> name`, `plugin_stop`, `journal_entry(cmdr, is_beta, system, station, entry, state)`, `journal_entry_cqc`, `dashboard_entry(cmdr, is_beta, entry)`, `cmdr_data` family where feasible, plus `config` key-value persistence namespaced per plugin, `monitor.game_running()` and `monitor.is_live_galaxy()`, and EDMC-style `logging` bridging. Long-running plugin work must run off the UI thread; tkinter `event_generate` patterns must be adapted to Textual-safe messaging. [My call: clean-room shim guided by PLUGINS.md, no copying of EDMC GPL-2.0 core code.]
4. Host EDMC Modern Overlay 1:1. The same Modern Overlay plugin code runs inside RED Navigator, with the same WebSocket broadcaster, `port.json` handshake, legacy TCP path, grouping and profile stores (`overlay_groupings.json`, `overlay_groupings.user.json`, `overlay_settings.json`), controller launch sequence (`!ovr` style prefix), and external overlay client plus controller processes drawing over the game window. Plugins that publish via `send_overlay_message` / `register_publisher` (e.g. EDR, Canonn) see no difference from running under EDMC.
5. Mirror overlay messages inside the terminal. The same payloads that go to the game-window overlay are also rendered as Textual panels, so the terminal is useful on its own and the external overlay can be toggled off for lighter nights.
6. Functional per-plugin settings UI in the terminal. Each loaded plugin that exposes `plugin_prefs` / `prefs_changed` gets its own settings panel rendered from a generic form layer (checkboxes, text/numbers, file picks, dropdowns where mappable), with values persisted across restarts and surviving plugin updates that add new keys. On first run with no data present, offer to import data from EDMC; if import fails, ask permission to set up fresh or retry. [User decision 2026-10-11.] NOVA's `s`-key settings overlay pattern is the host. [My call: generic renderer plus safe fallback text when a tkinter widget has no terminal equivalent.]
7. Low overhead and Proton-aware paths. Journal, Cargo, NavRoute, ModulesInfo, Backpack/ShipLocker, and Status files resolved from Proton compatdata plus normal Linux EDMC data dirs. No browser dependency. No always-on heavyweight renderer when the external overlay is off.

## Non-goals (v1 — explicitly later)

- EDNA replication. Agreed phase 2, after EDMC plus overlay v1 works. Do not design the EDNA behavior in v1 beyond leaving room for another integration module.
- Discord Rich Presence mirroring VeeLume/Elite-Dangerous-Rich-Presence. Agreed phase 3, after EDNA.
- Full parity with EDCoPilot, EDOMH, ODEliteTracker, or the route widget. Those motivated the consolidation idea and remain future integrations over time, not v1 acceptance.
- Rewriting Modern Overlay's client/controller renderers. V1 reuses them as-is for 1:1 behavior.

## Anti-goals

- It would be a failure if RED Navigator technically loads plugins but uses more resources than the stack it replaces, or adds noticeable input or overlay lag versus EDMC today.
- It would be a failure if plugin updates routinely break because settings keys were hardcoded or the hook signatures drifted from PLUGINS.md.
- It would be a failure if the game-window overlay looks or positions differently from EDMC hosting with no way to get exact parity back.
- It would be a failure if Windows-only assumptions (paths, `%LOCALAPPDATA%`, bundled Python) leak into the Linux Proton path handling.

## Constraints

- Base license: NOVA is MIT. EDMC core is GPL-2.0. RED Navigator must not copy EDMC core source into the fork; the shim is a clean-room implementation of the documented plugin contract. Modern Overlay reuse must honor its own LICENSE as shipped in its plugin folder.
- Language and stack: NOVA is Python 3.11+ with Textual. V1 is Linux-only; Windows/macOS support only after v1 serves the user. [User decision 2026-10-11.] EDMC plugins expect a CPython environment with `requests`, stdlib helpers (`shutil`, `sqlite3`, `zipfile`), and EDMC-provided modules (`L10n`, `theme`, `config`, `companion`, `edmc_data`, `plug`, `monitor`, `timeout_session`, `myNotebook`, `ttkHyperlinkLabel`). V1 shim decides the exact subset to guarantee; anything else is best-effort with a clear error in logs. [My call.]
- UI mismatch: EDMC plugin UI is tkinter (`plugin_app`, `plugin_prefs` returning `tk.Frame`/`tk.Label`). NOVA/RED is Textual. V1 must translate, not run an X embed. Unmappable widgets degrade to a readable fallback, never a crash.
- Overlay on Linux Proton: transparent game-window overlay depends on compositor behavior (XWayland force-render, Flatpak context, scale modes like fill, nudge/gutter settings observed in `overlay_settings.json`). V1 keeps the client's existing knobs (`force_xwayland`, `force_render`, opacity, gridlines, font bounds) working rather than inventing new ones.
- Data locations: v1 must handle both the Proton Windows-style plugin dir the user pointed at and the native Linux EDMC data dirs, plus NOVA-style portable config next to the launcher and `~/.config`-style system paths. Reference baseline verified 2026-10-11: EDMC runs inside the Proton prefix as a Windows build at `.../compatdata/359320/pfx/drive_c/Program Files (x86)/EDMarketConnector/` (EDMarketConnector.exe, library.zip, _tkinter.pyd present), with plugins at `.../drive_c/users/steamuser/AppData/Local/EDMarketConnector/plugins/`.
- Journals are reference-only: existing game journals may be read for replay and verification but never altered under any circumstances. [User decision 2026-10-11.]
- Auth and live services: live data may be retrieved from services for verification; Frontier auth is always user-directed, never autonomous. [User decision 2026-10-11.]

## How it gets made (decisions already taken by user)

- Start from a fork of NOVA (https://github.com/KernicDE/nova-ed-monitor), then apply integrations, then re-theme as RED Navigator. More integrations stack later.
- Start integrations with EDMC plugins and overlay functionality, referencing EDMC repo (https://github.com/EDCD/EDMarketConnector) and the 8 installed plugins.
- Overlay behavior must be 1:1 with normal EDMC hosting (user requirement).
- Per-plugin settings UI is required in v1 because plugins update and add config (user requirement).
- Order after v1: EDNA behavior next, Discord Rich Presence after that.

## What's left to the builder (do not guess back to user unless load-bearing)

- Exact shim module layout and import names so `load.py` files load without edits, including how to sandbox per-plugin imports to avoid cross-plugin module collisions (PLUGINS.md warns `import widgets` collides; relative imports required).
- Settings persistence format and migration when a plugin adds keys, and the tkinter-to-Textual widget map with fallback rules.
- `port.json` location and port ownership when both EDMC and RED Navigator could be installed; single-owner rule and stale-file cleanup. [My call: RED Navigator owns its own plugin-dir copy when hosting; document the conflict.]
- Process supervision for the overlay client/controller (launch, restart, logs, Flatpak env forwarding keys observed in `load.py`), and the terminal-mirror subscription point on the same bus.
- Feed completeness: which `state` dict fields from PLUGINS.md are emulated in v1 (credits, cargo, ranks, NavRoute, ModuleInfo, suits, taxi, Body caveats, Powerplay, etc.) versus stubbed as None, and CAPI (`cmdr_data`) scope for v1.
- Verification rig: headless journal replay plus the 8 target plugins loaded, overlay payload capture comparison EDMC-vs-RED for parity, and resource comparison (CPU/RAM with game running, overlay on and off).
