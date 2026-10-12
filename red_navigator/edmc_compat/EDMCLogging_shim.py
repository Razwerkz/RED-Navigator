"""
Shim module for EDMC's EDMCLogging module.
Provides logging utilities.
"""
from __future__ import annotations
import logging
from typing import Any, Optional

# Module-level logger
_main_logger: Optional[logging.Logger] = None

def get_main_logger() -> logging.Logger:
    """Get the main application logger."""
    global _main_logger
    if _main_logger is None:
        logger = logging.getLogger("EDMarketConnector")
        logger.setLevel(logging.DEBUG)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        _main_logger = logger
    return _main_logger

# For backward compatibility
def log(text: str) -> None:
    """Log a message to the main logger."""
    get_main_logger().info(text)

def log_error(text: str) -> None:
    get_main_logger().error(text)

def log_warning(text: str) -> None:
    get_main_logger().warning(text)

__all__ = ['get_main_logger', 'log', 'log_error', 'log_warning']