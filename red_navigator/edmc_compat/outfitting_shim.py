"""
Shim module for EDMC's outfitting module.
Provides outfitting data structures.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

@dataclass
class OutfittingItem:
    name: str
    price: int = 0
    item_class: str = ""
    size: int = 0
    rating: str = ""
    mount: str = ""
    power: float = 0.0

@dataclass
class Outfitting:
    name: str
    market_id: int = 0
    modules: List[Dict[str, Any]] = field(default_factory=list)

OUTFITTINGS: Dict[str, Outfitting] = {}

def get_outfitting(market_id: int) -> Optional[Outfitting]:
    return OUTFITTINGS.get(str(market_id))

__all__ = ['Outfitting', 'OutfittingItem', 'OUTFITTINGS', 'get_outfitting']