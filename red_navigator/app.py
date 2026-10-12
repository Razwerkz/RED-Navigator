"""RED Navigator launcher: first-run import, session lifecycle, NOVA shell.

Wires the Task 1 session (plugin discovery/loading, overlay host,
fan-out flag), the Task 2 mirror sink (overlay payloads rendered into
the NOVA event log), and the Task 3 settings bridge (already bound in
``SettingsScreen``) around NOVA's own entry point
(:func:`ed_monitor.__main__.main`, called as-is — no thread wiring is
duplicated here).

Startup order: parse args → point ``config_store`` at the RED store
and load persisted values → first-run EDMC import (fresh-or-retry on
failure, never silent) → ``session.start`` → attach the mirror sink →
run NOVA. Shutdown order (always, even on error): detach the sink,
restore ``NOVAApp``, ``session.stop`` (``plugin_stop`` per plugin, host
stopped, owned ``port.json`` released).
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from pathlib import Path
from typing import Any, Callable

from ed_monitor.state import EventCategory, LogEvent

from red_navigator.edmc_compat import config_store, importer
from red_navigator.runtime import fanout, session

_log = logging.getLogger("red_navigator.app")

#: Config filename used when the RED store is a directory (same
#: convention as :mod:`red_navigator.runtime.session`).
_CONFIG_FILENAME = "config.json"

# Proton prefix roots that may hold the Windows EDMC install
# (appid 359320). Mirrors the journal/screenshot discovery roots.
def _steam_roots() -> tuple[Path, ...]:
    home = Path.home()
    return (
        home / ".steam/steam/steamapps",
        home / ".local/share/Steam/steamapps",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps",
        Path("/media/hdd2/SteamLibrary/steamapps"),
        Path("/media/hdd2/.steam/steam/steamapps"),
    )

#: Plugin dir inside a Proton prefix (per the plan baseline:
#: ``.../compatdata/359320/pfx/drive_c/.../EDMarketConnector/plugins/``).
_PROTON_PLUGIN_REL = Path(
    "compatdata/359320/pfx/drive_c/users/steamuser"
    "/AppData/Local/EDMarketConnector/plugins"
)

# Native Linux EDMC data dir (fallback import source).
def _native_edmc_data() -> Path:
    return Path.home() / ".config/EDMarketConnector"


def default_plugin_dir() -> str:
    """Return the Proton EDMC plugin dir (first existing, else canonical)."""
    roots = _steam_roots()
    for root in roots:
        candidate = root / _PROTON_PLUGIN_REL
        try:
            if candidate.is_dir():
                return str(candidate)
        except OSError:
            continue
    return str(roots[0] / _PROTON_PLUGIN_REL)


def default_store_dir() -> str:
    """Return the RED data dir (``<nova data_dir>/red``, portable-aware)."""
    try:
        from ed_monitor.config import data_dir

        return str(data_dir() / "red")
    except Exception:
        _log.debug("Falling back to home-based RED store", exc_info=True)
        return str(Path.home() / ".local/share/REDNavigator")


def default_edmc_source(plugin_dir: str) -> str:
    """Return the EDMC data dir to import from for ``plugin_dir``.

    The Proton EDMC data dir is the plugin dir's parent
    (``.../EDMarketConnector/``); the native Linux one is the fallback.
    """
    try:
        parent = Path(plugin_dir).parent
        if parent.is_dir():
            return str(parent)
    except OSError:
        pass
    native = _native_edmc_data()
    try:
        if native.is_dir():
            return str(native)
    except OSError:
        pass
    return str(native)


def _store_file(red_store: str) -> str:
    """Backing file for ``red_store`` (mirrors ``session`` convention)."""
    candidate = Path(red_store)
    if candidate.suffix == ".json":
        return str(candidate)
    return str(candidate / _CONFIG_FILENAME)


def reexec_argv() -> list[str]:
    """Return the argv to re-exec the RED launcher in place.

    Under ``python -m red_navigator.app`` ``sys.argv[0]`` is a
    non-executable ``app.py``, so NOVA's settings-triggered restart
    (``os.execv(sys.argv[0], sys.argv)``) fails. Re-exec via the
    interpreter plus ``-m`` instead, preserving caller args.
    """
    return [sys.executable, "-m", "red_navigator.app", *sys.argv[1:]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse launcher flags (``opts.overlay`` is False with --no-overlay)."""
    parser = argparse.ArgumentParser(
        prog="red-navigator",
        description="RED Navigator: NOVA TUI with EDMC plugins and overlay.",
    )
    parser.add_argument(
        "--no-overlay",
        dest="overlay",
        action="store_false",
        default=True,
        help="Run terminal-only without the game-window overlay host.",
    )
    parser.add_argument(
        "--plugin-dir",
        default=None,
        help="EDMC plugin directory (default: Proton EDMC plugins path).",
    )
    parser.add_argument(
        "--store-dir",
        default=None,
        help="RED data directory (default: the RED data dir).",
    )
    return parser.parse_args(argv)


def resolve_store(
    red_store: str, edmc_source: str, answer: str | None = None
) -> str:
    """Run the first-run import and resolve its outcome.

    Returns ``"fresh"`` (proceed — imported, already present, or the
    user accepted a fresh setup) or ``"retry"`` (the user asked to
    retry the import). A ``"failed"`` import never proceeds silently:
    with ``answer=None`` the user is asked via
    :func:`importer.fresh_setup_prompt`; a non-interactive stdin falls
    back to ``"fresh"`` with a logged warning.
    """
    try:
        outcome = importer.import_if_empty(red_store, edmc_source)
    except Exception:
        _log.warning(
            "EDMC import raised (source=%s dest=%s)",
            edmc_source, red_store, exc_info=True,
        )
        outcome = "failed"
    if outcome == "imported":
        print(f"Imported EDMC data from {edmc_source} into {red_store}.")
        return "fresh"
    if outcome != "failed":
        return "fresh"
    _log.warning("EDMC import failed (source=%s dest=%s)", edmc_source, red_store)
    if answer is None:
        try:
            answer = input(importer.fresh_setup_prompt())
        except (EOFError, OSError):
            print("No interactive input; starting with fresh (empty) RED data.")
            _log.warning("Import prompt unreadable; proceeding with fresh defaults")
            return "fresh"
    choice = (answer or "").strip().lower()
    if choice == "r" or choice.startswith("retry"):
        return "retry"
    return "fresh"


def make_event_sink(
    state: Any, lock: Any
) -> Callable[[str], None]:
    """Build the mirror-line sink pushing to the NOVA event log.

    Each rendered mirror string is split on newlines (Task 2 left
    single-vs-split open; splitting keeps one message per log row) and
    every non-blank line is pushed as
    ``LogEvent.new(EventCategory.System, line)`` under the app ``lock``.
    Never raises.
    """
    def _sink(line: str) -> None:
        try:
            text = line if isinstance(line, str) else str(line)
        except Exception:
            return
        try:
            lines = text.splitlines()
        except Exception:
            return
        if not lines:
            return
        try:
            with lock:
                for entry in lines:
                    if not entry.strip():
                        continue
                    try:
                        state.push_event(LogEvent.new(EventCategory.System, entry))
                    except Exception:
                        _log.debug("RED event push failed", exc_info=True)
        except Exception:
            _log.debug("RED event sink failed", exc_info=True)

    return _sink


#: Default seed for the RED action registry: ``(action id, label, default
#: key)`` per action. ``route.resume`` has **no** single-key default —
#: its default trigger is the bare double-Shift gesture (see
#: :mod:`red_navigator.actions.gestures`); the settings menu renders the
#: ``None`` key as ``unbound``. Every other entry preserves the exact
#: current NOVA ``on_key`` key (``ed_monitor/ui/app.py``), including the
#: canonical ``plus``/``minus`` names Textual delivers ("=" stays a
#: legacy alias — see the ``on_key`` volume branches).
_DEFAULT_ACTIONS: tuple[tuple[str, str, str | None], ...] = (
    ("route.resume", "Resume route (Shift ×2)", None),
    ("nova.help", "Help", "question_mark"),
    ("nova.quit", "Quit", "q"),
    ("nova.escape", "Clear focus / quit", "escape"),
    ("nova.focus.1", "Focus System panel", "1"),
    ("nova.focus.2", "Focus Ship panel", "2"),
    ("nova.focus.3", "Focus Route panel", "3"),
    ("nova.focus.4", "Focus Bodies panel", "4"),
    ("nova.focus.5", "Focus Events panel", "5"),
    ("nova.focus.6", "Focus Chat panel", "6"),
    ("nova.focus.clear", "Clear panel focus", "0"),
    ("nova.focus.next", "Cycle focus forward", "tab"),
    ("chat.game.tts", "Toggle in-game chat TTS", "g"),
    ("chat.twitch.tts", "Toggle Twitch chat TTS", "t"),
    ("chat.youtube.tts", "Toggle YouTube chat TTS", "y"),
    ("chat.all.tts", "Toggle all chat TTS", "p"),
    ("nova.settings", "Open settings", "s"),
    ("sit.auto.lock", "Toggle auto panel switching", "a"),
    ("audio.mute", "Mute / unmute", "m"),
    ("audio.vol.up", "Volume up", "plus"),
    ("audio.vol.down", "Volume down", "minus"),
    ("sit.engineers.enter", "Engineers: open detail / back", "enter"),
    ("neutron.input", "Neutron destination input", "n"),
)


def _unwired_handler(action_id: str) -> Callable[[], None]:
    """Placeholder handler used before live collaborators exist.

    Import-time seeding (:func:`ensure_default_bindings`) has no app
    instance, so actions start on safe no-ops; :func:`wire_actions`
    replaces them with live closures once ``(app, state, lock, tts_q)``
    exist. Never raises.
    """

    def _handler() -> None:
        _log.debug("Action %r invoked before RED wiring; ignoring", action_id)

    return _handler


def ensure_default_bindings() -> None:
    """Seed registry defaults for any action not yet registered.

    Idempotent and non-clobbering: already-registered ids (live user
    bindings, or handlers installed by :func:`wire_actions`) are left
    untouched — only gaps are filled with defaults + placeholder
    handlers. Safe to call at import, at startup, and in tests.
    """
    from red_navigator.actions import registry

    try:
        known = {a.get("id") for a in registry.list_actions()}
    except Exception:
        _log.debug("Action seed skipped (registry unreadable)", exc_info=True)
        return
    for action_id, label, default in _DEFAULT_ACTIONS:
        if action_id in known:
            continue
        try:
            registry.register(action_id, label, default, _unwired_handler(action_id))
        except Exception:
            _log.debug("Seeding action %r failed", action_id, exc_info=True)


def wire_actions(app: Any, state: Any, lock: Any, tts_q: Any) -> None:
    """(Re-)register every action with live collaborators, then load.

    Handlers close over ``app`` (migrated NOVA keys, via the ``_key_*``
    helpers in :mod:`ed_monitor.ui.app` — the same bodies the legacy
    ``on_key`` chain calls) and over ``(state, lock, tts_q)`` for
    ``route.resume`` (``host.publish`` / ``clipboard.copy_text`` / TTS
    speak, following the :func:`make_event_sink` app-lock pattern:
    state is read under ``lock``, nothing here ever raises).
    Re-registering preserves live user bindings (registry semantics);
    :func:`load_bindings` then applies stored overrides. ``tts_q=None``
    degrades speak to a logged no-op. Only builds closures — no eager
    state access — so running before ``App.__init__`` is safe.
    """
    from red_navigator.actions import registry
    from red_navigator.routes import resume

    try:
        from ed_monitor.ui.app import (
            SituationalPanel,
            _key_escape,
            _key_focus,
            _key_focus_next,
            _key_help,
            _key_mute,
            _key_neutron_input,
            _key_quit,
            _key_settings,
            _key_engineers_enter,
            _key_toggle_all_chat_tts,
            _key_toggle_auto_lock,
            _key_toggle_chat_tts,
            _key_toggle_twitch_tts,
            _key_toggle_youtube_tts,
            _key_volume_down,
            _key_volume_up,
        )
    except Exception:
        _log.debug("RED action wiring skipped (ui helpers unavailable)", exc_info=True)
        return

    def _when_has_cfg() -> bool:
        try:
            return app._cfg is not None
        except Exception:
            return False

    def _when_neutron() -> bool:
        try:
            sit = app.query_one(SituationalPanel)
            return sit._active == "neutron" or sit._mode == "neutron"
        except Exception:
            return False

    def _when_engineers() -> bool:
        try:
            return app.query_one(SituationalPanel)._active == "engineers"
        except Exception:
            return False

    # ── route.resume collaborators ────────────────────────────────────
    def _get_route() -> dict | None:
        try:
            with lock:
                entries = list(state.route_list)
        except Exception:
            _log.debug("route read failed", exc_info=True)
            return None
        # Mirror the route panel (situational/route.py): route[0] is the
        # departure system, display (and resume) starts at route[1:].
        remaining = [dict(e) for e in entries[1:] if isinstance(e, dict)]
        if not remaining:
            return None
        return {"Route": remaining}

    def _publish(payload: dict) -> bool:
        try:
            from red_navigator.overlay_host import host

            return bool(host.publish(payload))
        except Exception:
            _log.debug("route republish failed", exc_info=True)
            return False

    def _copy(text: str) -> bool:
        try:
            from red_navigator import clipboard

            return bool(clipboard.copy_text(text))
        except Exception:
            _log.debug("route clipboard copy failed", exc_info=True)
            return False

    def _speak(text: str) -> None:
        try:
            if tts_q is None:
                _log.debug("tts_q unavailable; dropping speak line: %s", text[:60])
                return
            from ed_monitor.tts import TtsMsg

            tts_q.put_nowait(TtsMsg(text=text, priority=False))
        except Exception:
            _log.debug("route speak failed", exc_info=True)

    def _on_resume() -> None:
        try:
            resume.resume_route(_get_route, _publish, _copy, _speak)
        except Exception:
            _log.debug("route.resume failed", exc_info=True)

    specs: tuple[tuple[str, str, str | None, Callable[[], None], Any], ...] = (
        ("route.resume", "Resume route (Shift ×2)", None, _on_resume, None),
        ("nova.help", "Help", "question_mark", lambda: _key_help(app), None),
        ("nova.quit", "Quit", "q", lambda: _key_quit(app), None),
        ("nova.escape", "Clear focus / quit", "escape", lambda: _key_escape(app), None),
        ("nova.focus.1", "Focus System panel", "1", lambda: _key_focus(app, 1), None),
        ("nova.focus.2", "Focus Ship panel", "2", lambda: _key_focus(app, 2), None),
        ("nova.focus.3", "Focus Route panel", "3", lambda: _key_focus(app, 3), None),
        ("nova.focus.4", "Focus Bodies panel", "4", lambda: _key_focus(app, 4), None),
        ("nova.focus.5", "Focus Events panel", "5", lambda: _key_focus(app, 5), None),
        ("nova.focus.6", "Focus Chat panel", "6", lambda: _key_focus(app, 6), None),
        ("nova.focus.clear", "Clear panel focus", "0", lambda: _key_focus(app, 0), None),
        ("nova.focus.next", "Cycle focus forward", "tab", lambda: _key_focus_next(app), None),
        ("chat.game.tts", "Toggle in-game chat TTS", "g", lambda: _key_toggle_chat_tts(app), None),
        ("chat.twitch.tts", "Toggle Twitch chat TTS", "t", lambda: _key_toggle_twitch_tts(app), None),
        ("chat.youtube.tts", "Toggle YouTube chat TTS", "y", lambda: _key_toggle_youtube_tts(app), None),
        ("chat.all.tts", "Toggle all chat TTS", "p", lambda: _key_toggle_all_chat_tts(app), None),
        ("nova.settings", "Open settings", "s", lambda: _key_settings(app), _when_has_cfg),
        ("sit.auto.lock", "Toggle auto panel switching", "a", lambda: _key_toggle_auto_lock(app), None),
        ("audio.mute", "Mute / unmute", "m", lambda: _key_mute(app), None),
        ("audio.vol.up", "Volume up", "plus", lambda: _key_volume_up(app), None),
        ("audio.vol.down", "Volume down", "minus", lambda: _key_volume_down(app), None),
        ("sit.engineers.enter", "Engineers: open detail / back", "enter", lambda: _key_engineers_enter(app), _when_engineers),
        ("neutron.input", "Neutron destination input", "n", lambda: _key_neutron_input(app), _when_neutron),
    )
    for action_id, label, default, handler, when in specs:
        try:
            registry.register(action_id, label, default, handler, when)
        except Exception:
            _log.debug("Wiring action %r failed", action_id, exc_info=True)
    try:
        registry.load_bindings()
    except Exception:
        _log.debug("Loading stored bindings failed", exc_info=True)


# Import-time seed (placeholder handlers): importing this module makes
# the migrated defaults resolvable; live wiring happens in main() and
# _RedSinkNOVAApp.__init__ below.
ensure_default_bindings()


def _attach_sink_to_nova_app() -> Callable[[], None]:
    """Patch ``ed_monitor.__main__.NOVAApp`` to install the mirror sink.

    NOVA's ``main()`` builds its own ``(state, lock)`` pair, so the
    sink is installed in a subclass ``__init__`` that captures them and
    calls :func:`fanout.set_event_sink` before delegating. Returns a
    ``restore()`` callable that unpatches and detaches (idempotent).
    """
    nova_main = importlib.import_module("ed_monitor.__main__")
    original = nova_main.NOVAApp

    class _RedSinkNOVAApp(original):  # type: ignore[misc, valid-type]
        def __init__(self, state: Any, lock: Any, *args: Any, **kwargs: Any) -> None:
            fanout.set_event_sink(make_event_sink(state, lock))
            # Full action wiring with live collaborators. NOVAApp.__init__
            # takes (state, lock, volume, vol_lock, tts_q, ...) positionally,
            # so tts_q is args[2] unless passed by keyword. Closure-only —
            # safe before super().__init__; never raises.
            try:
                if "tts_q" in kwargs:
                    tts_q = kwargs["tts_q"]
                elif len(args) >= 3:
                    tts_q = args[2]
                else:
                    tts_q = None
                wire_actions(self, state, lock, tts_q)
            except Exception:
                _log.debug("RED action wiring failed", exc_info=True)
            try:
                super().__init__(state, lock, *args, **kwargs)
            except Exception:
                fanout.set_event_sink(None)
                raise

    nova_main.NOVAApp = _RedSinkNOVAApp

    def _restore() -> None:
        try:
            if nova_main.NOVAApp is _RedSinkNOVAApp:
                nova_main.NOVAApp = original
        finally:
            try:
                fanout.set_event_sink(None)
            except Exception:
                _log.debug("Sink detach failed", exc_info=True)

    return _restore


def main(argv: list[str] | None = None) -> int:
    """Launch RED Navigator; return the process exit code."""
    opts = parse_args(argv)
    plugin_dir = opts.plugin_dir or default_plugin_dir()
    red_store = opts.store_dir or default_store_dir()
    edmc_source = default_edmc_source(plugin_dir)

    try:
        config_store.set_store_path(_store_file(red_store))
    except Exception:
        _log.warning("Could not set config store path for %s", red_store, exc_info=True)
    config_store.load()

    sess: session.Session | None = None
    restore_nova: Callable[[], None] | None = None
    code = 0
    try:
        while True:
            choice = resolve_store(red_store, edmc_source)
            if choice != "retry":
                _log.info("RED store ready at %s", red_store)
                break
            print("Retrying EDMC import…")
            _log.info("User chose retry; re-running EDMC import")
        # Session resolves overlay_dir=None itself (Task 1): an explicit
        # plugin dir holding load.py is used directly, else a well-known
        # overlay child, else terminal-only. Nothing extra passed here.
        sess = session.start(plugin_dir, red_store, overlay=bool(opts.overlay))
        # Seed action defaults and apply stored bindings now that the
        # store is wired (config_store path + session store wiring above).
        # Live collaborator wiring (state/lock/tts_q exist only inside
        # NOVA) follows in _RedSinkNOVAApp.__init__.
        try:
            ensure_default_bindings()
            from red_navigator.actions import registry as _registry

            _registry.load_bindings()
        except Exception:
            _log.debug("Action seed/load failed", exc_info=True)
        restore_nova = _attach_sink_to_nova_app()
        nova_main = importlib.import_module("ed_monitor.__main__")
        nova_main.main()
    except KeyboardInterrupt:
        _log.info("RED Navigator interrupted; shutting down")
        code = 130
    except Exception:
        _log.exception("RED Navigator exited with an error")
        code = 1
    finally:
        if restore_nova is not None:
            try:
                restore_nova()
            except Exception:
                _log.debug("NOVAApp restore failed", exc_info=True)
        try:
            session.stop(sess)
        except Exception:
            _log.debug("Session stop failed", exc_info=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
