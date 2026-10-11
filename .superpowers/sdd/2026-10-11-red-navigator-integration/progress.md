# SDD ledger — plan: /home/razwerkz/Projects/RED Navigator/docs/superpowers/plans/2026-10-11-red-navigator-integration.md

## Setup
- Normal repo on master, working in place (same as v1 run; user approved continued execution).
- Ruling: work in place, no worktree — single-branch repo, no remote, nothing to isolate from — cost if wrong: none.
- Workspace: /home/razwerkz/Projects/RED Navigator/.superpowers/sdd/2026-10-11-red-navigator-integration
- BASE at start: 09f329c
- Spec read: docs/superpowers/specs/2026-10-11-red-navigator-design.md (authority); v1 final-review follow-up (unwired seam) is the direct parent of this plan.
- Ruling: added `fanout.register_test_plugin/clear_test_plugins` to Task 1 Produces — the brief's own tests use them, so the plan text mandated them without naming them — cost if wrong: none, test-named helpers.

## Preflight scan (pairs sharing files/interfaces)
| Pair | Shared surface | Produces vs consumes | Finding |
|---|---|---|---|
| T1 -> T2 | `fanout.journal_entry`, sink hook | T1 produces fanout+session; T2 adds `set_event_sink` to fanout.py | Clean — sequential edits to the same new file, no signature clash. |
| T1 -> T3 | `host_panel.list_panels` (v1, exists) | T1 mounts plugins; T3 reads panels into settings_bridge | Clean — T3 only reads v1 interfaces. |
| T1 -> T4 | `session.start/stop` | T1 produces; T4 launches | Clean. |
| T2 -> T4 | `fanout.set_event_sink` | T2 produces; T4 wires to push_event | Clean. |
| T3 -> T4 | `settings_bridge` | T3 produces; T4 indirectly via SettingsScreen | Clean — no file overlap (app.py new). |
| T1 <-> T3 | `ed_monitor/` edits | T1 touches journal.py+status.py; T3 touches settings_screen.py | Clean — disjoint files. |

## Per-task self-agreement
| Task | Tests vs code | Files created vs touched | Finding |
|---|---|---|---|
| T1 | fanout dispatch + exception tests vs fanout/session + 2 hook sites | creates runtime/* + test, modifies journal.py+status.py | Clean after Produces fix (test helpers named). |
| T2 | sink delivery + sink-throws tests vs set_event_sink | modifies fanout.py + 1 test | Clean. |
| T3 | sections + save-isolation tests vs settings_bridge + screen wiring | creates settings_bridge + test, modifies settings_screen.py | Clean — register_plugin/clear/get_panel verified present in v1 host_panel.py. |
| T4 | flag + import-resolve tests vs app.main/parse_args/resolve_store | creates app.py + test | Clean. |

## Progress
