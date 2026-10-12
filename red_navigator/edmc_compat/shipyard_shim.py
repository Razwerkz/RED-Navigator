"""
Shim module for EDMC's shipyard module.
Provides shipyard data structures.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

@dataclass
class ShipyardItem:
    name: str
    price: int = 0
    ship_class: str = ""
    size: int = 0
    rating: str = ""
    mount: str = ""
    power: float = 0.0

@dataclass
class Shipyard:
    name: str
    market_id: int = 0
    ships: List[Dict[str, Any]] = field(default_factory=list)
    modules: List[Dict[str, Any]] = field(default_factory=list)
    allow_cobra_mk4: bool = False
    allow_cobra_mk3: bool = True

SHIPYARDS: Dict[str, Shipyard] = {}

def get_shipyard(market_id: int) -> Optional[Shipyard]:
    return SHIPYARDS.get(str(market_id))

__all__ = ['Shipyard', 'ShipyardItem', 'SHIPYARDS', 'get_shipyard']