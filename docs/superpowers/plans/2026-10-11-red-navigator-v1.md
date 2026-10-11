# RED Navigator v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fork NOVA and host all 8 existing EDMC plugins with 1:1 Modern Overlay behavior plus per-plugin terminal settings on Linux.

**Architecture:** Keep NOVA's Textual journal-driven TUI as the host shell; add a clean-room `red_navigator` adapter layer that emulates the EDMC plugin contract, reuses Modern Overlay plugin code as-is, and mirrors overlay payloads into Textual panels.

**Tech Stack:** Python 3.11+, Textual, pytest, stdlib sqlite3 for persistence.

**Spec:** `docs/superpowers/specs/2026-10-11-red-navigator-design.md`

## Global Constraints

- V1 is Linux-only; Windows/macOS support only after v1 serves the user.
- Existing game journals may be read for replay and verification but never altered under any circumstances.
- Frontier auth is always user-directed, never autonomous.
- Baseline EDMC install is the Proton Windows build at `.../compatdata/359320/pfx/drive_c/Program Files (x86)/EDMarketConnector/` with plugins at `.../drive_c/users/steamuser/AppData/Local/EDMarketConnector/plugins/`.
- V1 target: all currently installed plugins should be compatible, preferably (8 folders: ArtemisScannerTracker-0.3.4b, cargo-manifest, docking_denied_reason, EDMC-Canonn-7.8.0, EDMCModernOverlay, EDR, EDSM-RSE, HITS).
- On first run with no data present, offer to import data from EDMC; if import fails, ask permission to set up fresh or retry.
- Do not copy EDMC GPL-2.0 core source; shim is clean-room from PLUGINS.md. Honor Modern Overlay LICENSE on reuse.
- NOVA base is MIT; preserve attribution on fork.

## Review Focus

- Journal `NavRouteClear` arrives but prior route still readable by plugins expecting retained `state['NavRoute']` — expect retained route, not None.
- Close-orbiting binary bodies emit no new `ApproachBody`; `state['Body']` may be stale versus `dashboard_entry` body name — expect cross-check, never blind use.
- Player in CQC Arena sends `StartUp`/`ShutDown` and journal lines that must route to `journal_entry_cqc`, never `journal_entry`.
- Plugin long work or network I/O on the UI thread freezes Textual — expect worker thread plus main-thread message, never direct widget mutation from workers.
- Both EDMC and RED Navigator installed could fight over overlay `port.json` and broadcaster port — expect single-owner rule with stale-file cleanup, never two writers.

---

### Task 1: Fork NOVA and pin integration points

**Files:**
- Create: `docs/superpowers/plans/NOVA_FORK_INVENTORY.md`
- Create: `tests/test_fork_baseline.py`
- Modify: repo root with NOVA fork contents (preserve LICENSE, record upstream commit in inventory)

**Interfaces:**
- Consumes: NOVA upstream `https://github.com/KernicDE/nova-ed-monitor`
- Produces: `NOVA_JOURNAL_TAIL_ENTRY` (path of function yielding journal dicts), `NOVA_STATUS_FEED_ENTRY` (path of function yielding Status.json dicts), `NOVA_SETTINGS_HOOK` (path of `s`-key settings overlay extension point), all recorded in inventory doc for Tasks 2-5.

- [ ] **Step 1: Write the failing test**

```python
def test_fork_inventory_pins_nova_hooks():
    import pathlib
    inv = pathlib.Path("docs/superpowers/plans/NOVA_FORK_INVENTORY.md").read_text()
    assert "upstream_commit=" in inv
    assert "NOVA_JOURNAL_TAIL_ENTRY=" in inv
    assert "NOVA_STATUS_FEED_ENTRY=" in inv
    assert "NOVA_SETTINGS_HOOK=" in inv
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_fork_baseline.py::test_fork_inventory_pins_nova_hooks -v`
Expected: FAIL with inventory file not found.

- [ ] **Step 3: Implement fork plus inventory in `docs/superpowers/plans/NOVA_FORK_INVENTORY.md`**

Clone NOVA main into this repo root without deleting `docs/superpowers/specs/`, keep its LICENSE, record upstream commit hash, and fill the three hook paths by reading `ed_monitor/` plus docs. No behavior changes to NOVA in this task.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_fork_baseline.py -v`
Expected: PASS. Also run NOVA's own smoke (`python -m pytest tests/ -q` if present) and record result in inventory.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/NOVA_FORK_INVENTORY.md tests/test_fork_baseline.py
git commit -m "chore: fork NOVA and pin integration points"
```

### Task 2: EDMC core shim with read-only journal and dashboard feeds

**Files:**
- Create: `red_navigator/edmc_compat/__init__.py`
- Create: `red_navigator/edmc_compat/loader.py`
- Create: `red_navigator/edmc_compat/config_store.py`
- Create: `red_navigator/edmc_compat/monitor.py`
- Create: `red_navigator/edmc_compat/logging_bridge.py`
- Create: `red_navigator/feeds/journal_tail.py`
- Create: `red_navigator/feeds/dashboard_feed.py`
- Create: `red_navigator/feeds/state_builder.py`
- Test: `tests/edmc_compat/test_loader.py`, `tests/edmc_compat/test_feeds_readonly.py`

**Interfaces:**
- Consumes: `NOVA_JOURNAL_TAIL_ENTRY`, `NOVA_STATUS_FEED_ENTRY` from Task 1 inventory.
- Produces: `loader.discover_plugins(plugin_dir: str) -> list[str]`, `loader.load_plugin(path: str) -> module`, `loader.call_journal(plugin, cmdr: str, is_beta: bool, system: str, station: str, entry: dict, state: dict) -> None`, `loader.dispatch_entry(plugin, entry: dict, in_cqc: bool) -> None`, `config_store.get_str(key: str) -> str | None`, `config_store.set(key: str, value: str) -> None`, `monitor.game_running() -> bool`, `monitor.is_live_galaxy() -> bool`, `state_builder.build_state() -> dict`, `state_builder.apply_entry(state: dict, entry: dict) -> dict`, `state_builder.needs_dashboard_crosscheck(state: dict, dashboard: dict) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
def test_loader_calls_journal_entry_with_state(tmp_path):
    from red_navigator.edmc_compat import loader
    seen = {}
    class FakePlugin:
        def journal_entry(self, cmdr, is_beta, system, station, entry, state):
            seen.update(entry=entry, state_keys=set(state.keys()))
    loader.call_journal(FakePlugin(), "CMDR", False, "Sol", "", {"event": "FSDJump", "StarSystem": "Sol"}, {"SystemName": "Sol"})
    assert seen["entry"]["event"] == "FSDJump"
    assert "SystemName" in seen["state_keys"]

def test_journal_files_never_written(tmp_path):
    from red_navigator.feeds import journal_tail
    p = tmp_path / "Journal.1.log"
    p.write_text('{"event":"Fileheader"}\n')
    before = p.read_bytes()
    list(journal_tail.iter_entries(str(tmp_path)))
    assert p.read_bytes() == before

def test_navroute_clear_retains_prior_route():
    from red_navigator.feeds import state_builder
    state = state_builder.build_state()
    state["NavRoute"] = {"Route": [{"StarSystem": "Sol"}]}
    updated = state_builder.apply_entry(state, {"event": "NavRouteClear"})
    assert updated["NavRoute"] == {"Route": [{"StarSystem": "Sol"}]}

def test_cqc_routes_to_cqc_hook():
    from red_navigator.edmc_compat import loader
    seen = {}
    class FakePlugin:
        def journal_entry(self, *a, **k):
            seen["where"] = "main"
        def journal_entry_cqc(self, *a, **k):
            seen["where"] = "cqc"
    loader.dispatch_entry(FakePlugin(), {"event": "Location"}, in_cqc=True)
    assert seen["where"] == "cqc"

def test_body_state_requires_dashboard_crosscheck():
    from red_navigator.feeds import state_builder
    state = state_builder.build_state()
    state["Body"] = "BodyA"
    assert state_builder.needs_dashboard_crosscheck(state, {"Body": "BodyB"}) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/edmc_compat/test_loader.py tests/edmc_compat/test_feeds_readonly.py -v`
Expected: FAIL with module not found.

- [ ] **Step 3: Implement `loader`, `config_store`, `monitor`, `logging_bridge` in `red_navigator/edmc_compat/`**

Clean-room hook dispatcher supporting `plugin_start3`, `plugin_stop`, `journal_entry`, `journal_entry_cqc`, `dashboard_entry`, `cmdr_data` passthrough; per-plugin key namespacing and per-plugin module sandboxing so same-named sibling modules never collide; stdlib logging bridge. Long plugin work runs in worker threads with Textual-safe main-thread delivery; workers never mutate widgets directly. No tkinter imports.

- [ ] **Step 4: Implement `iter_entries` in `red_navigator/feeds/journal_tail.py` plus `dashboard_feed` and `state_builder`**

Read-only tail over Proton journal dirs plus native Linux fallbacks; `NavRouteClear` retains prior `state['NavRoute']`; CQC lines route to `journal_entry_cqc`; Body fields carry the binary-staleness caveat flag for callers to cross-check with dashboard body name.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/edmc_compat/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add red_navigator/edmc_compat red_navigator/feeds tests/edmc_compat
git commit -m "feat: add EDMC shim with read-only feeds"
```

### Task 3: First-run EDMC import with fresh-or-retry

**Files:**
- Create: `red_navigator/edmc_compat/importer.py`
- Test: `tests/edmc_compat/test_importer.py`

**Interfaces:**
- Consumes: `config_store.set`, `config_store.get_str` from Task 2.
- Produces: `importer.import_if_empty(red_store: str, edmc_source: str) -> str` returning `"imported" | "already-present" | "failed"`, plus `importer.fresh_setup_prompt() -> str` contract for the TUI to ask fresh-or-retry.

- [ ] **Step 1: Write the failing test**

```python
def test_import_offers_and_handles_failure(tmp_path):
    from red_navigator.edmc_compat import importer
    assert importer.import_if_empty(str(tmp_path / "red"), str(tmp_path / "missing")) == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/edmc_compat/test_importer.py -v`
Expected: FAIL with module not found.

- [ ] **Step 3: Implement `import_if_empty` in `red_navigator/edmc_compat/importer.py`**

Copy-only import from the Proton EDMC config/plugin dirs when red store is empty; never delete or modify source; on failure return `"failed"` and let the TUI ask fresh-or-retry.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/edmc_compat/test_importer.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add red_navigator/edmc_compat/importer.py tests/edmc_compat/test_importer.py
git commit -m "feat: add first-run EDMC import with retry"
```

### Task 4: Modern Overlay 1:1 host plus terminal mirror

**Files:**
- Create: `red_navigator/overlay_host/host.py`
- Create: `red_navigator/overlay_host/port_owner.py`
- Create: `red_navigator/overlay_host/mirror.py`
- Test: `tests/overlay_host/test_parity.py`

**Interfaces:**
- Consumes: `loader.load_plugin`, `loader.call_journal`, `monitor.game_running` from Task 2.
- Produces: `host.start(plugin_dir: str) -> int` (broadcaster port), `host.publish(payload: dict) -> bool`, `port_owner.claim(plugin_dir: str, port: int) -> bool`, `mirror.to_textual(payload: dict) -> str`.

- [ ] **Step 1: Write the failing test**

```python
def test_overlay_publishes_and_mirrors():
    from red_navigator.overlay_host import mirror
    text = mirror.to_textual({"event": "FSDJump", "system": "Sol"})
    assert "Sol" in text

def test_port_single_owner(tmp_path):
    from red_navigator.overlay_host import port_owner
    assert port_owner.claim(str(tmp_path), 50123) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/overlay_host/test_parity.py -v`
Expected: FAIL with module not found.

- [ ] **Step 3: Implement `host.start` in `red_navigator/overlay_host/host.py`**

Load the unmodified Modern Overlay `load.py` from the user's plugin dir through the Task 2 loader, start its WebSocket broadcaster and legacy TCP path, launch and supervise its existing client/controller processes, and reuse its grouping/profile/settings files in place.

- [ ] **Step 4: Implement `port_owner.claim` and `mirror.to_textual`**

Single-owner `port.json` with stale-file cleanup when EDMC also installed; terminal mirror renders the same payload the game-window overlay receives.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/overlay_host/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add red_navigator/overlay_host tests/overlay_host
git commit -m "feat: host Modern Overlay 1:1 with terminal mirror"
```

### Task 5: Per-plugin Textual settings UI

**Files:**
- Create: `red_navigator/settings_ui/forms.py`
- Create: `red_navigator/settings_ui/host_panel.py`
- Test: `tests/settings_ui/test_forms.py`

**Interfaces:**
- Consumes: `config_store` from Task 2, `NOVA_SETTINGS_HOOK` from Task 1.
- Produces: `forms.render(prefs_spec: dict) -> list[dict]`, `forms.apply(values: dict) -> None`, `host_panel.mount_for_plugin(name: str) -> None`.

- [ ] **Step 1: Write the failing test**

```python
def test_new_plugin_keys_survive_update():
    from red_navigator.settings_ui import forms
    spec = {"fields": [{"key": "opt_a", "type": "bool", "default": False}]}
    rendered = forms.render(spec)
    assert any(f["key"] == "opt_a" for f in rendered)
    forms.apply({"opt_a": True, "opt_new": "x"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/settings_ui/test_forms.py -v`
Expected: FAIL with module not found.

- [ ] **Step 3: Implement `forms.render` and `forms.apply` in `red_navigator/settings_ui/forms.py`**

Generic bool/text/number/file/dropdown renderer driven by each plugin's `plugin_prefs` fields; unknown tkinter widgets fall back to readable text, never crash; new keys persist without wiping existing ones; writes go through namespaced `config_store`.

- [ ] **Step 4: Implement `host_panel.mount_for_plugin` mounting into `NOVA_SETTINGS_HOOK`**

One panel per loaded plugin exposing `plugin_prefs`/`prefs_changed`, listed by the name returned from `plugin_start3`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/settings_ui/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add red_navigator/settings_ui tests/settings_ui
git commit -m "feat: add per-plugin terminal settings UI"
```

### Task 6: Parity and resource verification rig

**Files:**
- Create: `tests/parity/test_eight_plugins.py`
- Create: `scripts/verify_parity.py`
- Create: `scripts/verify_resources.py`

**Interfaces:**
- Consumes: all Task 2-5 interfaces.
- Produces: `scripts/verify_parity.py` (journal replay plus overlay payload diff EDMC-vs-RED), `scripts/verify_resources.py` (CPU/RAM report overlay on/off).

- [ ] **Step 1: Write the failing test**

```python
def test_parity_script_exists():
    import pathlib
    assert pathlib.Path("scripts/verify_parity.py").exists()
    assert pathlib.Path("scripts/verify_resources.py").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/parity/test_eight_plugins.py -v`
Expected: FAIL with scripts missing.

- [ ] **Step 3: Implement `scripts/verify_parity.py`**

Replays read-only sample journals through the shim for all 8 plugins, captures overlay payloads, diffs against EDMC-captured baselines; Frontier calls only after interactive user auth.

- [ ] **Step 4: Implement `scripts/verify_resources.py`**

Reports CPU/RAM with game running, overlay on versus off, failing if RED exceeds the recorded EDMC-plus-plugins baseline.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/parity/ -v`
Expected: PASS (with fixtures, no live hits by default).

- [ ] **Step 6: Commit**

```bash
git add tests/parity scripts/verify_parity.py scripts/verify_resources.py
git commit -m "test: add parity and resource verification rig"
```
