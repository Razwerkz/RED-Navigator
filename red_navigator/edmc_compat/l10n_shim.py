"""
Shim module for EDMC's l10n module.
Provides translations and number formatting.
"""
from __future__ import annotations
from typing import Any, Dict, Optional
import locale

# Translation dictionary - minimal for plugin compatibility
translations: Dict[str, Dict[str, str]] = {}

class _Translations:
    def __init__(self) -> None:
        self._translations: Dict[str, str] = {}
        self._current_locale = locale.getdefaultlocale()[0] or 'en_US'

    def tl(self, text: str) -> str:
        """Translate text to current locale."""
        return translations.get(self._current_locale, {}).get(text, text)

    def set_locale(self, locale_str: str) -> None:
        self._current_locale = locale_str

translations_obj = _Translations()

# Alias for compatibility
tl = translations_obj.tl

def tl(text: str) -> str:
    return translations_obj.tl(text)

def number_from_string(text: str, default: float = 0.0) -> float:
    """Parse a number from a string in a locale-independent way."""
    try:
        return float(text.replace(',', '').replace(' ', ''))
    except (ValueError, TypeError):
        return 0.0

def string_from_number(value: float, decimals: int = 2) -> str:
    """Format a number in a locale-independent way."""
    try:
        if value == int(value):
            return str(int(value))
        return f"{value:.{decimals}f}".rstrip('0').rstrip('.')
    except (ValueError, TypeError):
        return "0"

def get_locale() -> str:
    """Get current locale string."""
    return locale.getdefaultlocale()[0] or 'en_US'

def get_supported_locales() -> list:
    return ['en_US']

__all__ = ['tl', 'number_from_string', 'string_from_number', 'get_locale', 'get_supported_locales']