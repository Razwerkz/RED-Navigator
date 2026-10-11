# RED Navigator Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Launch RED Navigator as one process: NOVA's TUI shell with the EDMC shim, overlay host, and per-plugin settings bound in.

**Architecture:** Additive `red_navigator/runtime/` bridge owns plugin lifecycle and fan-out; tiny guarded hooks in `ed_monitor` tap parsed journal/Status dicts into the bridge (no behavior change when RED is off); the Event Log renders overlay mirror lines; SettingsScreen gains a RED Plugins section; a launcher wires first-run import, store persistence, and startup/shutdown order.

**Tech Stack:** Python 3.11+, Textual, pytest, stdlib only for the bridge.

**Spec:** `docs/superpowers/specs/2026-10-11-red-navigator-design.md` (v1 goals: EDMC hosting, 1:1 overlay, per-plugin settings; this plan implements the unwired seam the v1 final review recorded)

## Global Constraints

- V1 is Linux-only; Windows/macOS support only after v1 serves the user.
- Existing game journals may be read for replay and verification but never altered under any circumstances.
- Frontier auth is always user-directed, never autonomous.
- Baseline EDMC install is the Proton Windows build at `.../compatdata/359320/pfx/drive_c/Program Files (x86)/EDMarketConnector/` with plugins at `.../drive_c/users/steamuser/AppData/Local/EDMarketConnector/plugins/`.
- V1 target: all currently installed plugins should be compatible, preferably (8 folders: ArtemisScannerTracker-0.3.4b, cargo-manifest, docking_denied_reason, EDMC-Canonn-7.8.0, EDMCModernOverlay, EDR, EDSM-RSE, HITS).
- On first run with no data present, offer to import data from EDMC; if import fails, ask permission to set up fresh or retry.
- Do not copy EDMC GPL-2.0 core source; shim is clean-room from PLUGINS.md. Honor Modern Overlay LICENSE on reuse.
- NOVA base is MIT; preserve attribution on fork.
- `ed_monitor/` hooks are additive and guarded: with no RED session started, journal/status threads behave exactly as upstream.

## Review Focus

- A plugin raising inside journal fan-out must never kill the `nova-journal` thread — expect the exception logged and the thread continuing on the next entry.
- Fan-out runs on monitor threads, so it must never touch Textual widgets — expect only `AppState.push_event` under the existing lock, with widget updates left to the render loop.
- Overlay host failing to start (no client env, port fight) must never block TUI launch — expect degraded terminal-only startup with the failure logged.
- One plugin's `prefs_changed` raising during settings save must never lose other panels' saves — expect per-plugin isolation with the error surfaced.
- App exit must stop the overlay host and call `plugin_stop` — expect owned `port.json` released and no leaked server threads on shutdown.

---

### Task 1: RED runtime bridge with journal and dashboard fan-out

**Files:**
- Create: `red_navigator/runtime/__init__.py`
- Create: `red_navigator/runtime/session.py`
- Create: `red_navigator/runtime/fanout.py`
- Modify: `ed_monitor/journal.py` (one guarded hook call where each parsed `ev` dict is ready)
- Modify: `ed_monitor/status.py` (one guarded hook call where each parsed `data` dict is ready)
- Test: `tests/runtime/test_fanout.py`

**Interfaces:**
- Consumes: `loader.discover_plugins/discover+load_plugin/call_plugin_start3/call_journal/dispatch_entry/call_dashboard/call_plugin_stop` and `monitor` from `red_navigator/edmc_compat`, `host.start/publish/stop` from `red_navigator/overlay_host`, `mount_loaded` from `red_navigator/settings_ui/host_panel`, `importer` + `config_store.set_store_path/load` from `red_navigator/edmc_compat`.
- Produces: `session.start(plugin_dir: str, red_store: str, *, overlay: bool = True) -> Session`, `session.stop(s: Session) -> None`, `fanout.journal_entry(entry: dict, ctx: dict) -> None`, `fanout.dashboard_entry(data: dict) -> None`, `fanout.register_test_plugin(p: Any) -> None`, `fanout.clear_test_plugins() -> None`, `Session.is_running() -> bool`.

- [ ] **Step 1: Write the failing test**

```python
def test_fanout_reaches_plugin_and_overlay():
    from red_navigator.runtime import fanout
    calls = []
    class FakePlugin:
        def journal_entry(self, cmdr, is_beta, system, station, entry, state):
            calls.append(entry["event"])
    fanout.register_test_plugin(FakePlugin())
    try:
        fanout.journal_entry({"event": "FSDJump", "StarSystem": "Sol"}, {"cmdr": "CMDR", "is_beta": False, "system": "Sol", "station": ""})
    finally:
        fanout.clear_test_plugins()
    assert calls == ["FSDJump"]

def test_plugin_exception_never_escapes_fanout():
    from red_navigator.runtime import fanout
    class Boom:
        def journal_entry(self, *a, **k):
            raise RuntimeError("boom")
    fanout.register_test_plugin(Boom())
    try:
        fanout.journal_entry({"event": "Docked"}, {})
    finally:
        fanout.clear_test_plugins()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/runtime/test_fanout.py -v`
Expected: FAIL with module not found.

- [ ] **Step 3: Implement `fanout` in `red_navigator/runtime/fanout.py`**

Module-level plugin registry plus no-op-when-empty `journal_entry`/`dashboard_entry` that fan out through `loader.call_journal`/`dispatch_entry`/`call_dashboard` and `host.publish`, containing every plugin exception (log, never raise). Include `register_test_plugin`/`clear_test_plugins` helpers for tests.

- [ ] **Step 4: Implement `session.start/stop` in `red_navigator/runtime/session.py`**

`start` discovers and loads plugins via the Task 2 loader, calls `plugin_start3`, mounts each via `host_panel.mount_loaded`, starts the overlay host unless `overlay=False` (failure degrades to terminal-only with a log, never raises), and flips the fan-out enabled flag. `stop` calls `plugin_stop` per plugin, stops the host, and disables fan-out.

- [ ] **Step 5: Add guarded hooks in `ed_monitor/journal.py` and `ed_monitor/status.py`**

At the point each parsed dict is ready, call the fan-out inside `try/except` guarded by an enabled check, importing `red_navigator` lazily so upstream behavior is byte-identical when no session runs. Pin the exact call sites by reading the monitor loops first.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/runtime/ tests/edmc_compat/ -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add red_navigator/runtime tests/runtime ed_monitor/journal.py ed_monitor/status.py
git commit -m "feat: add RED runtime bridge with journal fan-out"
```

### Task 2: Overlay mirror lines in the Event Log

**Files:**
- Modify: `red_navigator/runtime/fanout.py` (mirror push on published payloads)
- Test: `tests/runtime/test_mirror_log.py`

**Interfaces:**
- Consumes: `mirror.to_textual(payload: dict) -> str` from `red_navigator/overlay_host`, `LogEvent.new(category, message)` and `AppState.push_event` from `ed_monitor/state.py` (`EventCategory.System` for RED lines).
- Produces: `fanout.set_event_sink(push: Callable[[str], None] | None) -> None` (sink receives rendered mirror lines; `None` detaches).

- [ ] **Step 1: Write the failing test**

```python
def test_published_payload_reaches_event_sink():
    from red_navigator.runtime import fanout
    seen = []
    fanout.set_event_sink(seen.append)
    try:
        fanout.journal_entry({"event": "FSDJump", "StarSystem": "Sol"}, {"system": "Sol"})
    finally:
        fanout.set_event_sink(None)
    assert any("Sol" in line for line in seen)

def test_sink_never_raises_to_monitor_thread():
    from red_navigator.runtime import fanout
    def bad(line):
        raise RuntimeError("sink boom")
    fanout.set_event_sink(bad)
    try:
        fanout.journal_entry({"event": "Docked"}, {})
    finally:
        fanout.set_event_sink(None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_mirror_log.py -v`
Expected: FAIL with `set_event_sink` not defined.

- [ ] **Step 3: Implement `set_event_sink` in `red_navigator/runtime/fanout.py`**

On each published payload, render via `mirror.to_textual` and deliver to the sink inside `try/except` (a throwing sink never propagates to monitor threads). Sink wiring to `state.push_event(LogEvent.new(EventCategory.System, line))` under the app lock lives in Task 4's launcher, not here.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/runtime/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add red_navigator/runtime/fanout.py tests/runtime/test_mirror_log.py
git commit -m "feat: mirror overlay payloads to event sink"
```

### Task 3: RED Plugins section in SettingsScreen

**Files:**
- Modify: `ed_monitor/ui/settings_screen.py` (append RED plugin rows + save hook)
- Test: `tests/runtime/test_settings_section.py`

**Interfaces:**
- Consumes: `host_panel.list_panels() -> list[dict]`, `forms.render(spec, plugin=name)`, `forms.apply(values, plugin=name)`, `host_panel.save_panel_values(name, values) -> None` from `red_navigator/settings_ui`.
- Produces: SettingsScreen shows one collapsible "RED Plugins" group listing each mounted panel's fields (bool→ToggleRow, options→SelectRow, else TextRow; spec-less panels show the placeholder hint), and saving the screen persists via `save_panel_values` with per-plugin isolation.

- [ ] **Step 1: Write the failing test**

```python
def test_settings_sections_expose_red_panels():
    from red_navigator.settings_ui import host_panel
    from red_navigator.runtime import settings_bridge
    host_panel.clear()
    host_panel.register_plugin("Demo", None)
    sections = settings_bridge.red_sections()
    assert any("Demo" in s["title"] for s in sections)
    host_panel.clear()

def test_settings_save_isolated_per_plugin():
    from red_navigator.runtime import settings_bridge
    from red_navigator.settings_ui import host_panel
    host_panel.clear()
    host_panel.register_plugin(" risky ", None)
    settings_bridge.save_red_section({" risky ": {"k": "v"}})
    assert host_panel.get_panel(" risky ") is not None
    host_panel.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/runtime/test_settings_section.py -v`
Expected: FAIL with module not found.

- [ ] **Step 3: Implement `settings_bridge` in `red_navigator/runtime/settings_bridge.py`**

`red_sections() -> list[dict]` builds render-ready groups from `list_panels()` (never raises; empty list when no plugins), and `save_red_section(values_by_plugin: dict) -> dict` persists each plugin via `save_panel_values` in isolation, returning per-plugin `{ok, error}` so one failure never blocks the rest.

- [ ] **Step 4: Wire the section into `ed_monitor/ui/settings_screen.py`**

Append the RED groups after the existing rows using the screen's native row types, and call `save_red_section` in the existing save path before emitting `Saved`. Read the save flow first; keep upstream rows and messages unchanged.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/runtime/test_settings_section.py tests/settings_ui/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add red_navigator/runtime/settings_bridge.py tests/runtime/test_settings_section.py ed_monitor/ui/settings_screen.py
git commit -m "feat: add RED Plugins settings section"
```

### Task 4: RED launcher with first-run import and clean shutdown

**Files:**
- Create: `red_navigator/app.py`
- Test: `tests/runtime/test_launcher.py`

**Interfaces:**
- Consumes: `session.start/stop`, `fanout.set_event_sink`, `settings_bridge` from this plan; `importer.import_if_empty/fresh_setup_prompt`, `config_store.set_store_path/load` from `red_navigator/edmc_compat`; NOVA entry in `ed_monitor/__main__.py` (read the `main` function name first and call it; do not duplicate its thread wiring).
- Produces: `app.main(argv: list[str] | None = None) -> int` supporting `--no-overlay` (terminal-only) and `--plugin-dir/--store-dir` overrides; `app.parse_args(argv) -> opts` with `opts.overlay: bool`; `app.resolve_store(red_store, edmc_source, answer: str | None) -> str` returning `"fresh" | "retry"`; `python -m red_navigator.app` launches RED Navigator.

- [ ] **Step 1: Write the failing test**

```python
def test_no_overlay_flag_parses():
    from red_navigator import app
    opts = app.parse_args(["--no-overlay"])
    assert opts.overlay is False

def test_import_failure_asks_fresh_or_retry(capsys):
    from red_navigator import app
    choice = app.resolve_store("/tmp/red-empty-x", "/tmp/red-missing-src-y", answer="fresh")
    assert choice in ("fresh", "retry")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/runtime/test_launcher.py -v`
Expected: FAIL with module not found.

- [ ] **Step 3: Implement `app.main` in `red_navigator/app.py`**

Parse args; wire `config_store.set_store_path` + `load`; run `import_if_empty` when the store is empty and resolve `"failed"` via `fresh_setup_prompt` (fresh or retry, never proceed silently); `session.start` (overlay unless `--no-overlay`); attach the event sink to `state.push_event(LogEvent.new(EventCategory.System, line))` under the app lock; invoke NOVA's main; on exit `session.stop` (host stopped, owned `port.json` released, `plugin_stop` called).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/runtime/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add red_navigator/app.py tests/runtime/test_launcher.py
git commit -m "feat: add RED Navigator launcher"
```
