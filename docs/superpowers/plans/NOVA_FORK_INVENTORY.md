# NOVA Fork Inventory (RED Navigator v1 — Task 1)

Fork of NOVA (Navigation, Operations, and Vessel Assistance for Elite Dangerous)
upstream: https://github.com/KernicDE/nova-ed-monitor (MIT License, (c) 2025 Nicolas Kerscher).
LICENSE preserved verbatim at repo-root `LICENSE`. No behavior changes to NOVA
in this task. V1 is Linux-only; Elite Dangerous journals are read-only, never
altered; no EDMC GPL-2.0 code is copied.

## Upstream pin

upstream_commit=8917390f55552b11e24a71fd9cea440136ff0005

Fork method: `git archive` of upstream HEAD extracted into the repo root,
excluding upstream `.git/` (history not merged). Pre-existing
`docs/superpowers/specs/` kept intact; `docs/` and `tests/` merged with
upstream contents (no filename collisions). Upstream version: 2.20.5
(`pyproject.toml`).

## Integration hooks for Tasks 2-5

NOVA_JOURNAL_TAIL_ENTRY=ed_monitor.journal._follow
NOVA_STATUS_FEED_ENTRY=ed_monitor.status._apply_status
NOVA_SETTINGS_HOOK=ed_monitor.ui.app:NovaApp.on_key[s]->SettingsScreen

Details:

- `NOVA_JOURNAL_TAIL_ENTRY`: `ed_monitor/journal.py::_follow()` is the live
  tail loop. It reads each appended journal line into a parsed journal dict
  (`ev = json.loads(line)`) and dispatches via `ed_monitor.events.handle()`.
  Launched by `ed_monitor/journal.py::monitor()` (spawned as the
  `nova-journal` guarded thread from `ed_monitor/__main__.py`). Backlog
  replay helpers in the same module: `_process_backlog()`, `_init_scan()`.
- `NOVA_STATUS_FEED_ENTRY`: `ed_monitor/status.py::_apply_status()` parses
  `Status.json` into its `data` dict (`data = json.loads(text)`) and applies
  flags/fuel/position to `AppState`. Driven by the `ed_monitor/status.py::monitor()`
  feed loop (spawned as the `nova-status` guarded thread from
  `ed_monitor/__main__.py`), which also applies `Cargo.json`/`Materials.json`
  via `_apply_cargo()`/`_apply_materials()`.
- `NOVA_SETTINGS_HOOK`: the `s`-key extension point is
  `ed_monitor/ui/app.py::NovaApp.on_key()`, branch `elif key == "s":`
  which opens the settings overlay via
  `self.push_screen(SettingsScreen(self._cfg))`. Overlay implementation:
  `ed_monitor/ui/settings_screen.py::SettingsScreen` (a Textual `Screen`
  subclass with its own `BINDINGS`). RED settings sections hook in here.

## Baseline verification

- `tests/test_fork_baseline.py::test_fork_inventory_pins_nova_hooks`: PASS
  (asserts the four `*_=` pins above are present in this file).
- NOVA's own suite (`pytest tests/ -q`, 26 files incl. the baseline test):
  421 passed, 1 failed (the baseline RED test) BEFORE this inventory file was
  written; 422 passed AFTER. No NOVA behavior was changed, so the NOVA
  subset result is the upstream-pinned baseline.
- Test env: `uv sync` from upstream `pyproject.toml` (Python >= 3.11;
  used 3.14.7), dev extra `pytest`.
