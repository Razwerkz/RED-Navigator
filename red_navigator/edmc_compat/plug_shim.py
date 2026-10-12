"""
Shim module for EDMC's plug module.
Provides plug.show_error() function.
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger("EDMarketConnector.plug")

def show_error(title: str, message: str) -> None:
    """Show an error message (logs instead of UI popup)."""
    logger.error(f"{title}: {message}")

def show_info(title: str, message: str) -> None:
    """Show an info message."""
    logger.info(f"{title}: {message}")

def show_warning(title: str, message: str) -> None:
    logger.warning(f"{title}: {message}")

__all__ = ['show_error', 'show_info', 'show_warning']