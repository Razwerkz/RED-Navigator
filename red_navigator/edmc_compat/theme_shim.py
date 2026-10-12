"""
Shim module for EDMC's theme module.
Provides theme support without requiring tkinter UI.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Callable, Dict, Set, List, Tuple
from collections.abc import Callable as AbcCallable

try:
    from config_shim import config
except ImportError:
    class _DummyConfig:
        def get_str(self, key: str, default: str = "") -> str:
            defaults = {
                'dark_text': '#ff8000',
                'dark_highlight': 'white',
            }
            return defaults.get(key, "")
        def get_int(self, key: str, default: int = 0) -> int:
            return default
        def get_bool(self, key: str, default: bool = False) -> bool:
            return False
        def set(self, key: str, value: Any) -> None:
            pass
        def get(self, key: str, default: Any = None) -> Any:
            return None
    config = _DummyConfig()

try:
    from l10n_shim import translations as tr
except ImportError:
    class _DummyTranslations:
        def tl(self, text: str) -> str:
            return text
    tr = _DummyTranslations()

try:
    from EDMCLogging_shim import get_main_logger
except ImportError:
    import logging
    def get_main_logger() -> Any:
        return logging.getLogger("EDMarketConnector")

logger = get_main_logger()

if __debug__:
    from traceback import print_exc

class _Theme:
    THEME_DEFAULT = 0
    THEME_DARK = 1
    THEME_TRANSPARENT = 2

    def __init__(self) -> None:
        self.active: int | None = None
        self.minwidth: int | None = None
        self.widgets: Dict[Any, Set[str]] = {}
        self.widgets_pair: List[Tuple] = []
        self.defaults: Dict[str, Any] = {}
        self.current: Dict[str, Any] = {}
        self.default_ui_scale: float | None = None
        self.startup_ui_scale: int | None = None

    def register(self, widget: Any) -> None:
        if not hasattr(widget, 'winfo_class'):
            return
        if widget not in self.widgets:
            self.widgets[widget] = set()

    def register_alternate(self, pair: Tuple, gridopts: Dict) -> None:
        self.widgets_pair.append((pair, gridopts))

    def button_bind(self, widget: Any, command: Callable, image: Any = None) -> None:
        pass

    def _update_widget(self, widget: Any) -> None:
        pass

    def update(self, widget: Any) -> None:
        self.register(widget)

    def apply(self, root: Any) -> None:
        pass

theme = _Theme()

# Export
THEME_DEFAULT = _Theme.THEME_DEFAULT
THEME_DARK = _Theme.THEME_DARK
THEME_TRANSPARENT = _Theme.THEME_TRANSPARENT

__all__ = ['THEME_DEFAULT', 'THEME_DARK', 'THEME_TRANSPARENT', 'theme']