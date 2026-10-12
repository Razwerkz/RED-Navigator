"""
Shim module for EDMC's companion module.
Provides CAPI data interfaces.
"""
from __future__ import annotations
from typing import Any, Dict, Optional, List
from dataclasses import dataclass

# Server constants
SERVER_LIVE = "live"
SERVER_LEGACY = "legacy"
SERVER_BETA = "beta"

@dataclass
class CAPIData:
    """CAPI data container."""
    commander: Optional[Dict[str, Any]] = None
    market: Optional[Dict[str, Any]] = None
    shipyard: Optional[Dict[str, Any]] = None
    fleetcarrier: Optional[Dict[str, Any]] = None
    source_host: str = SERVER_LIVE
    raw: Dict[str, Any] = None

    def __post_init__(self):
        if self.raw is None:
            self.raw = {}

__all__ = ['CAPIData', 'SERVER_LIVE', 'SERVER_LEGACY', 'SERVER_BETA']