# Action Registry, Binding Menu, Route Resume, Live Spansh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bindable hotkeys for every RED function with a settings menu, a resume-route keybind replacing the VoiceAttack macro, and live Spansh plotting with offline fallback.

**Architecture:** New `red_navigator/actions/` registry owns all global keybindings (NOVA's `on_key` chain consults it first, context-sensitive keys stay in the legacy chain); a binding menu in SettingsScreen captures and persists bindings; route resume republishes the stored NavRoute plus clipboard and TTS; Spansh neutron plotting goes live with the offline dump as fallback.

**Tech Stack:** Python 3.11+, Textual, pytest, stdlib subprocess for clipboard (`wl-copy`/`xclip`/`xsel` fallback chain), existing `ed_monitor/_http.py` patterns for Spansh calls.

**Spec:** `docs/superpowers/specs/2026-10-11-red-navigator-design.md` plus the EDCoPilot reference captured in this plan (39 `HotKey-*` entries in `EDCoPilot.ini`; radio/music controls out of scope; no VA equivalent of route-resume exists, so resume is fresh design)

## Global Constraints

- V1 is Linux-only; Windows/macOS support only after v1 serves the user.
- Existing game journals may be read for replay and verification but never altered under any circumstances.
- Frontier auth is always user-directed, never autonomous.
- NOVA base is MIT; preserve attribution on fork.
- EDCoPilot is proprietary: clean-room reimplementation of functionality only, no copied assets, voices, or text.
- Bindings persist across restarts and survive updates adding new actions.
- Registry dispatch preserves existing focus behavior (bindings do not fire while typing in an Input); implementer verifies against current `on_key`.
- Spansh network calls never run on the UI thread and always have timeouts.

## Review Focus

- Pressing Escape during key capture must cancel binding, not bind Escape — expect capture mode to treat Escape as cancel.
- Rebinding onto an occupied key must warn and require confirm, never silently steal — expect a conflict result the UI surfaces.
- Clipboard tools missing on minimal systems must never raise — expect silent no-op with a logged debug.
- Spansh API down or slow must fall back to the offline dump within a bounded time — expect a visible fallback notice, never a hung UI.
- Route resume with no stored route must announce gracefully — expect a "no route plotted" TTS/line, never an exception.

---

### Task 1: Action registry with persistence

**Files:**
- Create: `red_navigator/actions/__init__.py`
- Create: `red_navigator/actions/registry.py`
- Test: `tests/actions/test_registry.py`

**Interfaces:**
- Consumes: `config_store` namespaced persistence (`plugin="red_navigator.bindings"`) from `red_navigator/edmc_compat`.
- Produces: `registry.register(id: str, label: str, default: str | None, handler: Callable[[], None], when: Callable[[], bool] | None = None) -> None`, `registry.resolve(key: str) -> dict | None`, `registry.list_actions() -> list[dict]`, `registry.set_binding(id: str, key: str | None) -> dict` returning `{ok, conflict}` (conflict names the occupying action, binding unchanged), `registry.load_bindings() -> None`, `registry.clear() -> None` (tests).

- [ ] **Step 1: Write the failing test**

```python
def test_register_resolve_and_conflict():
    from red_navigator.actions import registry
    registry.clear()
    registry.register("demo.a", "Demo A", "z", lambda: None)
    registry.register("demo.b", "Demo B", None, lambda: None)
    assert registry.resolve("z")["id"] == "demo.a"
    result = registry.set_binding("demo.b", "z")
    assert result["ok"] is False and result["conflict"] == "demo.a"
    assert registry.resolve("z")["id"] == "demo.a"
    registry.clear()

def test_bindings_persist_and_reload():
    from red_navigator.actions import registry
    registry.clear()
    registry.register("demo.a", "Demo A", "z", lambda: None)
    registry.set_binding("demo.a", "x")
    registry.clear(keep_store=True)
    registry.register("demo.a", "Demo A", "z", lambda: None)
    registry.load_bindings()
    assert registry.resolve("x")["id"] == "demo.a"
    registry.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/actions/test_registry.py -v`
Expected: FAIL with module not found.

- [ ] **Step 3: Implement `registry` in `red_navigator/actions/registry.py`**

Dict-backed registry keyed by action id; key normalization (lowercase, `plus`/`equal` aliases matching Textual key names); `when` predicates evaluated at resolve time; bindings persisted through namespaced `config_store` under a fixed key; `load_bindings` applies stored overrides for registered ids only (unknown stored ids ignored so removals never crash).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/actions/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add red_navigator/actions tests/actions
git commit -m "feat: add bindable action registry"
```

### Task 2: Binding menu in settings

**Files:**
- Create: `red_navigator/actions/menu.py`
- Modify: `ed_monitor/ui/settings_screen.py` (append Hotkeys section + capture mode)
- Test: `tests/actions/test_menu.py`

**Interfaces:**
- Consumes: `registry.list_actions/resolve/set_binding` from Task 1.
- Produces: `menu.binding_sections() -> list[dict]` (`{id, label, key}` per action), `menu.apply_binding(id: str, key: str | None) -> dict` (passthrough of `set_binding` result, never raises), `menu.capture_key(id: str, key: str) -> dict` (Escape returns `{ok: False, cancelled: True}` without touching bindings; any other key delegates to `apply_binding`); settings screen enters capture on row activate.

- [ ] **Step 1: Write the failing test**

```python
def test_menu_lists_and_applies_with_conflict():
    from red_navigator.actions import registry, menu
    registry.clear()
    registry.register("demo.a", "Demo A", "z", lambda: None)
    registry.register("demo.b", "Demo B", None, lambda: None)
    sections = menu.binding_sections()
    assert any(s["id"] == "demo.a" and s["key"] == "z" for s in sections)
    assert menu.apply_binding("demo.b", "z")["conflict"] == "demo.a"
    assert menu.apply_binding("demo.b", "x")["ok"] is True
    registry.clear()

def test_escape_cancels_capture():
    from red_navigator.actions import menu
    assert menu.capture_key("demo.a", "escape") == {"ok": False, "cancelled": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/actions/test_menu.py -v`
Expected: FAIL with module not found.

- [ ] **Step 3: Implement `menu` in `red_navigator/actions/menu.py`**

Read-only section builder over `list_actions` (never raises, `[]` when empty); apply path delegates to `set_binding` inside `try/except` returning `{ok: False, conflict: None, error}` on unexpected failure; `capture_key` short-circuits Escape to `{ok: False, cancelled: True}` before delegating.

- [ ] **Step 4: Wire the Hotkeys section into `ed_monitor/ui/settings_screen.py`**

Append one row per action (`label — current key`) using native row types after existing rows including the RED Plugins section; activating a row enters capture mode showing "press keys… (Esc cancels)"; Escape aborts with no change; any other key calls `apply_binding` and shows the conflict name on conflict. Read the existing row/capture mechanics first; upstream rows and save flow unchanged.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/actions/test_menu.py tests/runtime/test_settings_section.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add red_navigator/actions/menu.py tests/actions/test_menu.py ed_monitor/ui/settings_screen.py
git commit -m "feat: add hotkey binding menu to settings"
```

### Task 3: Route resume core plus clipboard

**Files:**
- Create: `red_navigator/routes/__init__.py`
- Create: `red_navigator/routes/resume.py`
- Create: `red_navigator/clipboard.py`
- Test: `tests/routes/test_resume.py`, `tests/test_clipboard.py`

**Interfaces:**
- Consumes: `host.publish(payload: dict) -> bool` from `red_navigator/overlay_host`, `mirror.to_textual` for the announce line.
- Produces: `resume.resume_route(get_route: Callable[[], dict | None], publish: Callable[[dict], bool], copy: Callable[[str], bool], speak: Callable[[str], None]) -> dict` returning `{ok, waypoint: str | None, published: int, copied: bool}`, `clipboard.copy_text(text: str) -> bool` (tries `wl-copy`, then `xclip`, then `xsel`; False when none work, never raises).

- [ ] **Step 1: Write the failing test**

```python
def test_resume_republishes_announces_and_copies():
    from red_navigator.routes import resume
    route = {"Route": [{"StarSystem": "Sol"}, {"StarSystem": "Alpha"}]}
    published, copied, said = [], [], []
    result = resume.resume_route(lambda: route, lambda p: published.append(p) or True, lambda t: copied.append(t) or True, said.append)
    assert result == {"ok": True, "waypoint": "Sol", "published": 2, "copied": True}
    assert copied == ["Sol"] and any("Sol" in s for s in said)

def test_resume_without_route_announces_gracefully():
    from red_navigator.routes import resume
    said = []
    result = resume.resume_route(lambda: None, lambda p: True, lambda t: True, said.append)
    assert result["ok"] is False and result["waypoint"] is None
    assert len(said) == 1

def test_clipboard_missing_tools_never_raises(monkeypatch):
    import shutil
    from red_navigator import clipboard
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert clipboard.copy_text("Sol") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/routes/test_resume.py tests/test_clipboard.py -v`
Expected: FAIL with module not found.

- [ ] **Step 3: Implement `resume_route` in `red_navigator/routes/resume.py` and `copy_text` in `red_navigator/clipboard.py`**

Resume reads waypoints from the route dict (empty/None route returns graceful failure with a speak line, never raises); republishes each waypoint as an overlay payload via `publish`; copies the next (first) waypoint system name via `copy`; speaks one announce line naming the waypoint and remaining count. No direct imports of host/clipboard/tts internals — all four collaborators are injected callables so tests stay headless.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/routes/ tests/test_clipboard.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add red_navigator/routes red_navigator/clipboard.py tests/routes tests/test_clipboard.py
git commit -m "feat: add route resume core and clipboard"
```

### Task 4: Live Spansh neutron plotting with offline fallback

**Files:**
- Modify: `ed_monitor/spansh.py` and/or `ed_monitor/neutron.py` (additive live path; read both plus `ed_monitor/_http.py` and `ed_monitor/ui/situational/neutron.py` first)
- Test: `tests/test_spansh_live.py`

**Interfaces:**
- Consumes: existing offline neutron dump path and `ed_monitor/_http.py` request patterns.
- Produces: `plot_neutron_live(origin: str, destination: str, *, timeout_s: float = 15.0) -> dict` returning `{ok, route: list | None, source: "live" | "offline", notice: str}` — live Spansh neutron API first, offline dump fallback on any failure or timeout, `notice` carrying the human-readable fallback reason; internal seam `neutron._fetch_live(origin: str, destination: str, timeout_s: float) -> dict` performing the single live request (may raise; tests stub it).

- [ ] **Step 1: Write the failing test**

```python
def test_live_fallback_on_timeout(monkeypatch):
    import ed_monitor.neutron as neutron
    monkeypatch.setattr(neutron, "_fetch_live", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    result = neutron.plot_neutron_live("Sol", "Colonia")
    assert result["source"] == "offline" and "fallback" in result["notice"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_spansh_live.py -v`
Expected: FAIL with function not defined.

- [ ] **Step 3: Implement live path with bounded fallback**

Live Spansh neutron router request with explicit timeout, executed off the UI thread by callers (document that the function blocks); any exception or timeout falls back to the existing offline dump path; `notice` always explains which source served the route. No API keys required (Spansh neutron router is keyless).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_spansh_live.py -v`
Expected: PASS (no live network in tests; stub the fetch layer).

- [ ] **Step 5: Commit**

```bash
git add ed_monitor/spansh.py ed_monitor/neutron.py tests/test_spansh_live.py
git commit -m "feat: live Spansh neutron plotting with offline fallback"
```

### Task 5: Launcher wiring, registry migration, default seed

**Files:**
- Modify: `red_navigator/app.py` (register resume action, wire collaborators, load bindings at startup)
- Modify: `ed_monitor/ui/app.py` (consult registry first in `on_key`, keep legacy context chain as fallback)
- Test: `tests/runtime/test_action_wiring.py`

**Interfaces:**
- Consumes: `registry.register/load_bindings/resolve`, `resume.resume_route`, `clipboard.copy_text`, `host.publish`, `NavRoute` state (read the stored route the same way the route panel does).
- Produces: `route.resume` action registered with default key `r` (verified free of NOVA bindings at plan time); all pre-existing global single-key NOVA bindings migrated to registry entries with identical defaults; startup calls `load_bindings()` after store wiring.

- [ ] **Step 1: Write the failing test**

```python
def test_resume_registered_with_default_r():
    from red_navigator.actions import registry
    import red_navigator.app  # noqa: F401 -- registration side effect
    hit = registry.resolve("r")
    assert hit is not None and hit["id"] == "route.resume"

def test_migrated_binding_still_resolves():
    from red_navigator.actions import registry
    import red_navigator.app  # noqa: F401
    assert registry.resolve("s") is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/runtime/test_action_wiring.py -v`
Expected: FAIL (no registration yet).

- [ ] **Step 3: Implement wiring in `red_navigator/app.py` and registry-first dispatch in `ed_monitor/ui/app.py`**

`app.main` registers `route.resume` (handler closes over publish/clipboard-copy/`tts_q` speak with the app lock pattern from `make_event_sink`) and migrates each global NOVA binding to a registry entry preserving exact current keys; `on_key` normalizes the event key, resolves via registry (honoring `when` predicates and Input focus behavior identical to today), and falls through to the legacy chain on no match. `load_bindings()` runs at startup after store wiring.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/runtime/test_action_wiring.py tests/actions/ tests/runtime/ -v`
Expected: PASS, plus full suite green.

- [ ] **Step 5: Commit**

```bash
git add red_navigator/app.py ed_monitor/ui/app.py tests/runtime/test_action_wiring.py
git commit -m "feat: wire route resume and migrate bindings to registry"
```
