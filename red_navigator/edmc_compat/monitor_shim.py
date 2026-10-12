"""
Shim module for EDMC's monitor module.
Provides game state detection functions.
"""
from __future__ import annotations
from typing import Any, Optional

# Module-level state
_game_running = True
_is_live_galaxy = True

def game_running() -> bool:
    """Return True if the game appears to be running."""
    return _game_running

def is_live_galaxy() -> bool:
    """Return True if playing in the live galaxy."""
    return _is_live_galaxy

def set_game_running(value: bool) -> None:
    """Set the game running state (for testing)."""
    global _game_running
    _game_running = value

def set_live_galaxy(value: bool) -> None:
    """Set the live galaxy state (for testing)."""
    global _is_live_galaxy
    _is_live_galaxy = value

__all__ = ['game_running', 'is_live_galaxy', 'set_game_running', 'set_live_galaxy']