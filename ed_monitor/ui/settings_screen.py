"""Settings overlay screen for NOVA TUI (issue #97).

Shows a scrollable list of settings rows. Navigate with ↑/↓.
Toggle/select values with ← / →. Text values with Enter to edit.
ESC cancels without saving (or closes the text editor if one is open).
SAVE button writes config.toml and applies changes live.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _parse_voice_catalog(
    voices: list[dict[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    """Parse edge-tts voice list into a nested catalog.

    Returns ``{lang: {locale: [voice_name, ...]}}`` where
    ``lang`` = e.g. ``"en"``, ``locale`` = e.g. ``"GB"``,
    ``voice_name`` = e.g. ``"SoniaNeural"``.
    Voices within each locale are sorted alphabetically.
    """
    catalog: dict[str, dict[str, list[str]]] = {}
    for v in voices:
        short_name = v.get("ShortName", "")
        if "Multilingual" in short_name:
            continue
        parts = short_name.split("-")
        if len(parts) < 3:
            continue
        lang   = parts[0]
        locale = parts[1]
        name   = "-".join(parts[2:])  # handles multi-hyphen names
        catalog.setdefault(lang, {}).setdefault(locale, []).append(name)
    # Sort voice names within each locale
    for lang_dict in catalog.values():
        for locale in lang_dict:
            lang_dict[locale].sort()
    return catalog


@dataclass
class ToggleRow:
    """A boolean setting row (Yes/No), cycled with ← / →."""
    key:   str
    label: str
    value: bool

    def cycle(self, direction: int) -> None:
        self.value = not self.value

    def display_value(self) -> str:
        return "Yes" if self.value else "No"


@dataclass
class SelectRow:
    """A setting row with a fixed list of options, cycled with ← / →."""
    key:     str
    label:   str
    value:   str
    options: list[str]

    def cycle(self, direction: int) -> None:
        if not self.options:
            return
        idx = self.options.index(self.value) if self.value in self.options else 0
        self.value = self.options[(idx + direction) % len(self.options)]

    def display_value(self) -> str:
        return self.value


@dataclass
class TextRow:
    """A setting row with a free-text value, edited via inline Input."""
    key:   str
    label: str
    value: str

    def display_value(self) -> str:
        return self.value


# ── Screen ────────────────────────────────────────────────────────────────────

import asyncio
import logging
import threading

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Input, Label, Static
from textual.containers import Vertical

from .. import config as _config
from ..config import Config
from . import palette as P
from ..ui.palette import _theme_dir

_log = logging.getLogger("ed_monitor.ui.settings_screen")

_SUPPORTED_LANGS = ["en", "de", "fr", "it", "es", "pt", "ru"]
# "auto" = empty string in config (language auto-detected from message content)
_CHAT_LANGS = ["auto"] + _SUPPORTED_LANGS

# Volume options in steps of 5
_VOLUME_OPTIONS = [str(v) for v in range(0, 101, 5)]

# TTS rate options
_RATE_OPTIONS = [
    "-50%", "-40%", "-30%", "-20%", "-10%", "-5%",
    "+0%", "+5%", "+10%", "+15%", "+20%", "+30%", "+40%", "+50%",
]

_HINT_NAV  = "↑↓ navigate   ← → change   Enter edit text   Esc cancel"
_HINT_EDIT = "Enter = confirm   Esc = cancel edit"
_HINT_CAPTURE = "press keys… (Esc cancels)"

# Row-key prefix for Hotkeys section rows (one TextRow per bindable action).
_HOTKEY_PREFIX = "hotkey:"


def _available_themes() -> list[str]:
    """Return sorted list of theme names found in config/themes/*.toml."""
    themes_dir = _theme_dir()
    names: list[str] = []
    try:
        for p in themes_dir.glob("*.toml"):
            if p.is_file():
                names.append(p.stem)
    except OSError:
        pass
    if "default" not in names:
        names.insert(0, "default")
    names.sort()
    return names


def _snap_volume(vol: int) -> str:
    """Snap an arbitrary volume value to the nearest 5-step option."""
    snapped = str(round(max(0, min(100, vol)) / 5) * 5)
    return snapped if snapped in _VOLUME_OPTIONS else "50"


def _snap_rate(rate: str) -> str:
    """Return rate if it's in the options list, else fall back to +0%."""
    return rate if rate in _RATE_OPTIONS else "+0%"


class SettingsScreen(Screen):
    """Overlay for editing NOVA settings (keybind: s)."""

    # BINDINGS on a Screen are processed BEFORE App.on_key, which means they
    # definitively prevent situational-panel switching while settings are open.
    # check_action() disables navigation bindings while a text editor is open
    # so that arrow keys and Enter fall through to the Input widget instead.
    BINDINGS = [
        Binding("escape", "do_escape", "", show=False),
        Binding("up",     "do_up",     "", show=False),
        Binding("down",   "do_down",   "", show=False),
        Binding("left",   "do_left",   "", show=False),
        Binding("right",  "do_right",  "", show=False),
        Binding("enter",  "do_enter",  "", show=False),
    ]

    CSS = P.css("""
    SettingsScreen {
        background: [[OVERLAY_BG]];
        align: center middle;
    }
    #settings-box {
        width: 74;
        height: 90%;
        background: [[OVERLAY_BOX_BG]];
        border: solid [[OVERLAY_BOX_BORDER]];
        padding: 1 2;
        overflow-y: auto;
    }
    #settings-title {
        color: [[OVERLAY_BOX_BORDER]];
        text-style: bold;
        margin-bottom: 1;
    }
    .setting-row {
        height: 1;
        padding: 0 0;
    }
    .setting-row.focused-row {
        background: [[SETTINGS_ROW_FOCUS_BG]];
    }
    #save-row {
        height: 1;
        margin-top: 1;
        background: [[OVERLAY_BOX_BG]];
        color: [[OVERLAY_BOX_BORDER]];
        text-style: bold;
    }
    #save-row.focused-row {
        background: [[OVERLAY_BOX_BORDER]];
        color: [[BG_DARK]];
        text-style: bold;
    }
    #text-edit-input {
        margin-top: 1;
    }
    #settings-hint {
        color: [[LABEL_DIM]];
        margin-top: 1;
    }
    """)

    class Saved(Message):
        def __init__(self, cfg: "Config") -> None:
            super().__init__()
            self.cfg = cfg

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._cfg        = cfg
        self._catalog: dict = {}    # {lang: {locale: [voice_name]}}
        self._editing: bool = False
        self._editing_row: "TextRow | None" = None
        self._cursor: int   = 0

        # Decompose current voice for the active tts_lang
        voice_str  = cfg.tts_voices.get(cfg.tts_lang, "")
        parts      = voice_str.split("-") if voice_str else []
        v_lang     = cfg.tts_lang
        v_locale   = parts[1] if len(parts) >= 3 else ""
        v_name     = "-".join(parts[2:]) if len(parts) >= 3 else ""

        self._voice_lang_row   = SelectRow("_voice_lang",   "Voice Language", v_lang,   _SUPPORTED_LANGS)
        self._voice_locale_row = SelectRow("_voice_locale", "Voice Locale",   v_locale, [])
        self._voice_name_row   = SelectRow("_voice_name",   "Voice Name",     v_name,   [])

        # chat_lang "" → "auto" for display; mapped back on save
        chat_lang_val = cfg.chat_lang if cfg.chat_lang in _SUPPORTED_LANGS else "auto"

        # Build panel-order rows from current config
        _PANEL_MODES = [
            ("overview", "Overview"), ("bio", "Bio"), ("galaxy", "Maps"),
            ("missions", "Missions"), ("engineers", "Engineers"), ("bgs", "BGS"),
            ("colonisation", "Colonisation"), ("route", "Route"), ("neutron", "Neutron"),
            ("assets", "Assets"), ("stats", "Stats"),
        ]
        # current order: mode -> position string (1-based)
        if cfg.situational_panels:
            _current_order = {mode: str(i + 1) for i, mode in enumerate(cfg.situational_panels) if mode}
        else:
            # Default order: all panels visible, numbered 1-N
            _current_order = {mode: str(i + 1) for i, (mode, _) in enumerate(_PANEL_MODES)}

        self._panel_rows = [
            TextRow(f"panel_{mode}", label, _current_order.get(mode, ""))
            for mode, label in _PANEL_MODES
        ]

        self._theme_options = _available_themes()

        self._rows: list = [
            # ── Appearance ────────────────────────────────────────────────────
            SelectRow("theme",       "Theme",                    cfg.theme,                       self._theme_options),
            SelectRow("layout",      "Layout",                   getattr(cfg, "layout", "landscape"), ["landscape", "portrait-half", "portrait-full"]),
            # ── TTS ──────────────────────────────────────────────────────────
            SelectRow("tts_lang",    "TTS Language",             cfg.tts_lang,                    _SUPPORTED_LANGS),
            SelectRow("tts_rate",    "TTS Rate",                 _snap_rate(cfg.tts_rate),        _RATE_OPTIONS),
            SelectRow("volume",      "Volume (0–100)",            _snap_volume(cfg.default_volume), _VOLUME_OPTIONS),
            # ── Voice selection ───────────────────────────────────────────────
            self._voice_lang_row,
            self._voice_locale_row,
            self._voice_name_row,
            # ── Chat & integrations ───────────────────────────────────────────
            TextRow("twitch",        "Twitch Channel",           cfg.twitch_channel),
            TextRow("youtube",       "YouTube Channel",          cfg.youtube_channel),
            SelectRow("chat_lang",   "Chat default language",    chat_lang_val,                   _CHAT_LANGS),
            ToggleRow("tts_chat",    "Chat TTS",                 cfg.tts_chat),
            ToggleRow("tts_twitch",  "Twitch TTS",               cfg.tts_twitch),
            ToggleRow("tts_youtube", "YouTube TTS",              cfg.tts_youtube),
            # ── Bodies & display ─────────────────────────────────────────────
            TextRow("notable",       "Notable Value (Cr)",       str(cfg.notable_value_threshold)),
            TextRow("fuel_warn",     "Fuel Warning % (0=off)",   str(cfg.fuel_warning_percent)),
            TextRow("home_system",   "Home System",              cfg.home_system),
            ToggleRow("carrier",     "Fleet Carrier Lookup",     cfg.carrier_lookup),
            # ── AI Voice ─────────────────────────────────────────────────────
            SelectRow("voice_engine", "Voice Engine",            cfg.voice_engine, ["static", "kimi", "claude"]),
            ToggleRow("ambient",     "Ambient Commentary",       cfg.ambient_commentary_enabled),
            # ── Situational Panels ────────────────────────────────────────────
            *self._panel_rows,
        ]

        # ── RED Plugins (additive; upstream rows above unchanged) ─────────────
        # One native row per mounted RED plugin field (bool→ToggleRow,
        # options→SelectRow, else TextRow; spec-less panels show the
        # placeholder hint). Best-effort: never breaks upstream init.
        self._red_rows: list = []
        self._red_field_of: dict[int, tuple[str, str]] = {}
        self._red_placeholder_ids: set[int] = set()
        self._append_red_rows()

        # ── Hotkeys (additive; upstream rows above unchanged) ─────────────────
        # One TextRow per bindable action (`label — current key`); activating a
        # row enters key-capture mode. Best-effort: never breaks upstream init.
        self._hotkey_rows: list = []
        self._hotkey_id_of: dict[int, str] = {}
        self._capturing: bool = False
        self._capture_row: "TextRow | None" = None
        self._append_hotkey_rows()

    # ── RED Plugins helpers (additive; upstream behavior unchanged) ─────────

    def _append_red_rows(self) -> None:
        """Append one native row per RED plugin field to ``self._rows``."""
        try:
            from red_navigator.runtime import settings_bridge
            sections = settings_bridge.red_sections()
        except Exception:
            return
        if not sections:
            return
        for section in sections:
            try:
                if not isinstance(section, dict):
                    continue
                plugin = section.get("plugin", section.get("name", ""))
                fields = section.get("fields", [])
                if not isinstance(plugin, str) or not plugin:
                    continue
                if not isinstance(fields, list):
                    continue
                for field in fields:
                    try:
                        row = self._red_row_for(plugin, field)
                        if row is None:
                            continue
                        self._red_rows.append(row)
                        fkey = field.get("key", "") if isinstance(field, dict) else ""
                        self._red_field_of[id(row)] = (plugin, fkey)
                        if isinstance(field, dict) and field.get("placeholder"):
                            self._red_placeholder_ids.add(id(row))
                        self._rows.append(row)
                    except Exception:
                        continue
            except Exception:
                continue

    @staticmethod
    def _red_row_for(plugin: str, field: dict):
        """Map a RED field dict to a native ToggleRow/SelectRow/TextRow."""
        if not isinstance(field, dict):
            return None
        key = field.get("key", "")
        if not isinstance(key, str) or not key:
            return None
        label = field.get("label", key)
        if not isinstance(label, str) or not label:
            label = key
        row_label = f"[{plugin}] {label}"
        row_key = f"red:{plugin}:{key}"
        if field.get("placeholder"):
            hint = field.get("hint") or field.get("value") or ""
            return TextRow(row_key, row_label, str(hint))
        ftype = field.get("type", "text")
        options = field.get("options", [])
        if ftype == "bool" and not options:
            val = field.get("value", field.get("default", False))
            if isinstance(val, str):
                bval = val.strip().lower() in ("1", "true", "yes", "on")
            else:
                bval = bool(val)
            return ToggleRow(row_key, row_label, bval)
        if isinstance(options, list) and len(options) > 0:
            opts = [str(o) for o in options]
            raw = field.get("value", field.get("default", opts[0] if opts else ""))
            val = str(raw) if raw is not None else ""
            if val not in opts and opts:
                val = opts[0]
            return SelectRow(row_key, row_label, val, opts)
        raw = field.get("value", field.get("default", ""))
        if raw is None:
            raw = ""
        return TextRow(row_key, row_label, str(raw))

    def _save_red_rows(self) -> None:
        """Persist RED plugin rows via save_red_section (per-plugin isolation).

        Best-effort: one plugin's failure never blocks others and never
        breaks the upstream save path.
        """
        try:
            from red_navigator.runtime import settings_bridge
        except Exception:
            return
        try:
            values_by_plugin: dict[str, dict] = {}
            placeholder_ids = getattr(self, "_red_placeholder_ids", set())
            for row in getattr(self, "_red_rows", []):
                try:
                    if id(row) in placeholder_ids:
                        continue
                    ident = self._red_field_of.get(id(row))
                    if ident is None:
                        continue
                    plugin, field_key = ident
                    if not isinstance(plugin, str) or not plugin:
                        continue
                    if not isinstance(field_key, str) or not field_key:
                        continue
                    if isinstance(row, ToggleRow):
                        values_by_plugin.setdefault(plugin, {})[field_key] = bool(row.value)
                    elif isinstance(row, (SelectRow, TextRow)):
                        values_by_plugin.setdefault(plugin, {})[field_key] = row.value
                except Exception:
                    continue
            if values_by_plugin:
                results = settings_bridge.save_red_section(values_by_plugin)
                try:
                    for plugin, res in results.items():
                        if isinstance(res, dict) and not res.get("ok", False):
                            _log.warning(
                                "RED plugin save failed for %r: %s",
                                plugin, res.get("error"),
                            )
                except Exception:
                    pass
        except Exception:
            pass

    # ── Hotkeys helpers (additive; upstream behavior unchanged) ───────────────

    def _append_hotkey_rows(self) -> None:
        """Append one TextRow per bindable action to ``self._rows``."""
        try:
            from red_navigator.actions import menu as _menu
            sections = _menu.binding_sections()
        except Exception:
            return
        if not sections:
            return
        for section in sections:
            try:
                if not isinstance(section, dict):
                    continue
                action_id = section.get("id", "")
                label = section.get("label", action_id)
                if not isinstance(action_id, str) or not action_id:
                    continue
                if not isinstance(label, str) or not label:
                    label = action_id
                key = section.get("key")
                value = str(key) if isinstance(key, str) and key else "unbound"
                row = TextRow(f"{_HOTKEY_PREFIX}{action_id}", label, value)
                self._hotkey_rows.append(row)
                self._hotkey_id_of[id(row)] = action_id
                self._rows.append(row)
            except Exception:
                continue

    def _hotkey_action_of(self, row) -> "str | None":
        """Return the action id for a Hotkeys row, else None."""
        try:
            hit = getattr(self, "_hotkey_id_of", {}).get(id(row))
            if isinstance(hit, str) and hit:
                return hit
            key = getattr(row, "key", "")
            if isinstance(row, TextRow) and isinstance(key, str) \
                    and key.startswith(_HOTKEY_PREFIX):
                action_id = key[len(_HOTKEY_PREFIX):]
                return action_id or None
        except Exception:
            pass
        return None

    def _enter_hotkey_capture(self, row: TextRow) -> None:
        """Enter key-capture mode for a Hotkeys row."""
        self._capturing = True
        self._capture_row = row
        try:
            self.query_one("#settings-hint", Label).update(_HINT_CAPTURE)
        except Exception:
            pass
        self._render_rows()

    def _abort_hotkey_capture(self) -> None:
        """Leave capture mode with no change."""
        self._capturing = False
        self._capture_row = None
        try:
            self.query_one("#settings-hint", Label).update(_HINT_NAV)
        except Exception:
            pass
        self._render_rows()

    def _refresh_hotkey_row(self, row: TextRow, action_id: str) -> None:
        """Re-read a Hotkeys row value from the registry (None → unbound)."""
        try:
            from red_navigator.actions import menu as _menu
            for section in _menu.binding_sections():
                if isinstance(section, dict) and section.get("id") == action_id:
                    key = section.get("key")
                    row.value = str(key) if isinstance(key, str) and key else "unbound"
                    return
        except Exception:
            pass

    def _finish_hotkey_capture(self, key: str) -> None:
        """Apply a captured key; conflicts stay in capture showing the name."""
        row = getattr(self, "_capture_row", None)
        action_id = self._hotkey_action_of(row) if row is not None else None
        if row is None or action_id is None:
            self._abort_hotkey_capture()
            return
        try:
            from red_navigator.actions import menu as _menu
        except Exception:
            self._abort_hotkey_capture()
            return
        try:
            result = _menu.capture_key(action_id, key)
        except Exception:
            result = {"ok": False, "conflict": None}
        if isinstance(result, dict) and result.get("cancelled"):
            self._abort_hotkey_capture()
            return
        if isinstance(result, dict) and result.get("ok"):
            self._refresh_hotkey_row(row, action_id)
            self._capturing = False
            self._capture_row = None
            try:
                self.query_one("#settings-hint", Label).update(_HINT_NAV)
            except Exception:
                pass
            self._render_rows()
            return
        conflict = result.get("conflict") if isinstance(result, dict) else None
        err = result.get("error") if isinstance(result, dict) else None
        if conflict:
            msg = f"Key already bound to {conflict} — press another key or Esc"
        elif err:
            msg = f"Rebind failed: {err} — press another key or Esc"
        else:
            msg = f"Could not bind {key!r} — press another key or Esc"
        try:
            self.query_one("#settings-hint", Label).update(msg)
        except Exception:
            pass
        self._render_rows()

    # ── Textual lifecycle ────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._fetch_catalog()
        self.call_after_refresh(self._render_rows)

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-box"):
            yield Label("◈ NOVA Settings", id="settings-title")
            for i, row in enumerate(self._rows):
                yield Static(self._row_text(row), id=f"row-{i}", classes="setting-row", markup=False)
            yield Static("[ SAVE ]", id="save-row", markup=False)
            # Note: Input is mounted dynamically in _open_editor — not here,
            # so it cannot steal focus during normal navigation.
            yield Label(_HINT_NAV, id="settings-hint")

    # ── check_action: disable navigation bindings while editing ──────────────

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Disable navigation bindings while a TextRow editor is open.

        When editing, the bindings for cursor movement and Enter are disabled so
        that the key events fall through to the focused Input widget instead.
        ESC is always active so it can close the editor.
        """
        if action in ("do_up", "do_down", "do_left", "do_right", "do_enter"):
            return not (self._editing or getattr(self, "_capturing", False))
        return True

    # ── BINDING action methods ───────────────────────────────────────────────

    def action_do_escape(self) -> None:
        if getattr(self, "_capturing", False):
            self._abort_hotkey_capture()
        elif self._editing:
            self._close_editor()
        else:
            self.app.pop_screen()

    def action_do_up(self) -> None:
        self._cursor = max(0, self._cursor - 1)
        self._render_rows()

    def action_do_down(self) -> None:
        n_rows = len(self._rows)
        self._cursor = min(n_rows, self._cursor + 1)
        self._render_rows()

    def action_do_left(self) -> None:
        self._cycle(-1)

    def action_do_right(self) -> None:
        self._cycle(+1)

    def action_do_enter(self) -> None:
        if getattr(self, "_capturing", False):
            return
        n_rows = len(self._rows)
        if self._cursor == n_rows:
            self._do_save()
        elif self._cursor < n_rows:
            row = self._rows[self._cursor]
            if self._hotkey_action_of(row) is not None:
                if isinstance(row, TextRow):
                    self._enter_hotkey_capture(row)
                return
            if isinstance(row, TextRow):
                # RED spec-less placeholder rows are informational only —
                # never open an editor for them (their hint is discarded on save).
                if id(row) in getattr(self, "_red_placeholder_ids", set()):
                    return
                self._open_editor(row)

    def on_key(self, event) -> None:
        """Route unbound keys to hotkey capture while capturing."""
        if getattr(self, "_capturing", False):
            try:
                event.stop()
            except Exception:
                pass
            self._finish_hotkey_capture(getattr(event, "key", ""))

    def _cycle(self, direction: int) -> None:
        n_rows = len(self._rows)
        if self._cursor < n_rows:
            row = self._rows[self._cursor]
            if hasattr(row, "cycle"):
                row.cycle(direction)
                if row is self._voice_lang_row:
                    self._update_voice_options()
                elif row is self._voice_locale_row:
                    self._update_voice_name_options()
                self._render_rows()

    # ── Voice catalog ────────────────────────────────────────────────────────

    def _fetch_catalog(self) -> None:
        """Fetch edge-tts voice catalog in a background thread."""
        def _worker():
            try:
                import edge_tts
                voices = asyncio.run(edge_tts.list_voices())
                self._catalog = _parse_voice_catalog(voices)
                self.call_from_thread(self._update_voice_options)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _update_voice_options(self) -> None:
        lang    = self._voice_lang_row.value
        locales = sorted(self._catalog.get(lang, {}).keys())
        self._voice_locale_row.options = locales
        if self._voice_locale_row.value not in locales and locales:
            self._voice_locale_row.value = locales[0]
        self._update_voice_name_options()
        self._render_rows()

    def _update_voice_name_options(self) -> None:
        lang   = self._voice_lang_row.value
        locale = self._voice_locale_row.value
        names  = self._catalog.get(lang, {}).get(locale, [])
        self._voice_name_row.options = names
        if self._voice_name_row.value not in names and names:
            self._voice_name_row.value = names[0]

    # ── Rendering ────────────────────────────────────────────────────────────

    def _row_text(self, row) -> str:
        if getattr(self, "_capturing", False) and row is getattr(self, "_capture_row", None):
            label = f"{row.label}:"
            return f"{label:<30} [ {_HINT_CAPTURE} ]"
        if isinstance(row, TextRow) and row.key.startswith("panel_"):
            val = row.display_value().strip() or " "
            return f"[{val:<2}] {row.label}"
        label = f"{row.label}:"
        val   = row.display_value() or "(none)"
        return f"{label:<30} [ {val} ]"

    def _render_rows(self) -> None:
        n_rows = len(self._rows)
        for i, row in enumerate(self._rows):
            try:
                w = self.query_one(f"#row-{i}", Static)
                w.update(self._row_text(row))
                if i == self._cursor:
                    w.add_class("focused-row")
                else:
                    w.remove_class("focused-row")
            except Exception:
                pass
        try:
            save_w = self.query_one("#save-row", Static)
            if self._cursor == n_rows:
                save_w.add_class("focused-row")
            else:
                save_w.remove_class("focused-row")
        except Exception:
            pass
        # Scroll cursor into view
        try:
            target_id = f"#row-{self._cursor}" if self._cursor < n_rows else "#save-row"
            self.query_one(target_id).scroll_visible(animate=False)
        except Exception:
            pass

    # ── Text editing ─────────────────────────────────────────────────────────

    def _open_editor(self, row: TextRow) -> None:
        """Dynamically mount an Input widget for editing the row's text value."""
        self._editing_row = row
        inp = Input(
            value=row.value,
            placeholder=f"Editing: {row.label}",
            id="text-edit-input",
        )
        try:
            self.query_one("#settings-box").mount(
                inp, before=self.query_one("#settings-hint")
            )
            self._editing = True
            self.query_one("#settings-hint", Label).update(_HINT_EDIT)
            self.call_after_refresh(inp.focus)
        except Exception:
            self._editing_row = None
            self._editing = False

    def _close_editor(self) -> None:
        """Remove the Input widget without saving its value."""
        try:
            self.query_one("#text-edit-input", Input).remove()
        except Exception:
            pass
        self._editing = False
        self._editing_row = None
        try:
            self.query_one("#settings-hint", Label).update(_HINT_NAV)
        except Exception:
            pass
        self._render_rows()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "text-edit-input":
            return
        row = self._editing_row
        if isinstance(row, TextRow):
            row.value = event.value  # allow empty string (clears the field)
        try:
            event.input.remove()
        except Exception:
            pass
        self._editing = False
        self._editing_row = None
        try:
            self.query_one("#settings-hint", Label).update(_HINT_NAV)
        except Exception:
            pass
        self._render_rows()

    # ── Save ─────────────────────────────────────────────────────────────────

    def _do_save(self) -> None:
        """Apply all row values to a Config copy, write to disk, notify app."""
        import copy as _copy
        cfg = _copy.copy(self._cfg)
        cfg.tts_voices = dict(self._cfg.tts_voices)

        for row in self._rows:
            if isinstance(row, SelectRow):
                match row.key:
                    case "tts_lang":
                        cfg.tts_lang = row.value
                    case "tts_rate":
                        cfg.tts_rate = row.value
                    case "volume":
                        try:
                            cfg.default_volume = max(0, min(100, int(row.value)))
                        except ValueError:
                            pass
                    case "chat_lang":
                        cfg.chat_lang = "" if row.value == "auto" else row.value
                    case "theme":
                        cfg.theme = row.value
                    case "layout":
                        cfg.layout = row.value
                    case "voice_engine":
                        cfg.voice_engine = row.value
            elif isinstance(row, TextRow):
                match row.key:
                    case "notable":
                        try:
                            cfg.notable_value_threshold = int(row.value)
                        except ValueError:
                            pass
                    case "fuel_warn":
                        try:
                            cfg.fuel_warning_percent = max(0, min(100, int(row.value)))
                        except ValueError:
                            pass
                    case "home_system":
                        cfg.home_system = row.value
                    case "twitch":
                        cfg.twitch_channel = row.value
                    case "youtube":
                        cfg.youtube_channel = row.value
            elif isinstance(row, ToggleRow):
                match row.key:
                    case "carrier":
                        cfg.carrier_lookup = row.value
                    case "tts_chat":
                        cfg.tts_chat = row.value
                    case "tts_twitch":
                        cfg.tts_twitch = row.value
                    case "tts_youtube":
                        cfg.tts_youtube = row.value
                    case "ambient":
                        cfg.ambient_commentary_enabled = row.value

        # Compile situational panel order from panel rows
        _mode_from_key = {f"panel_{mode}": mode for mode, _ in [
            ("overview", "Overview"), ("bio", "Bio"), ("galaxy", "Maps"),
            ("missions", "Missions"), ("engineers", "Engineers"), ("bgs", "BGS"),
            ("colonisation", "Colonisation"), ("route", "Route"), ("neutron", "Neutron"),
            ("assets", "Assets"), ("stats", "Stats"),
        ]}
        panel_orders: list[tuple[int, str]] = []
        for row in self._panel_rows:
            if row.value.strip():
                try:
                    panel_orders.append((int(row.value.strip()), _mode_from_key[row.key]))
                except (ValueError, KeyError):
                    pass
        panel_orders.sort(key=lambda x: x[0])
        cfg.situational_panels = [mode for _, mode in panel_orders]

        # Voice: reconstruct full voice string from lang/locale/name selections
        v_lang   = self._voice_lang_row.value
        v_locale = self._voice_locale_row.value
        v_name   = self._voice_name_row.value
        if v_lang and v_locale and v_name:
            cfg.tts_voices[v_lang] = f"{v_lang}-{v_locale}-{v_name}"

        _config.save(cfg)
        # RED Plugins save (additive; per-plugin isolation, never breaks upstream).
        try:
            self._save_red_rows()
        except Exception:
            pass
        self.post_message(SettingsScreen.Saved(cfg))
        self.app.pop_screen()
