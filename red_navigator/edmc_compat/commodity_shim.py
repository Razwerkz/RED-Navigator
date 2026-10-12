"""
Shim module for EDMC's commodity module.
Provides commodity data structures.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

@dataclass
class Commodity:
    name: str
    category: str = ""
    avg_price: int = 0
    buy_price: int = 0
    sell_price: int = 0
    demand: int = 0
    supply: int = 0
    demand_level: str = ""
    supply_level: str = ""
    category: str = ""
    rare: bool = False

    def __post_init__(self):
        pass

# Commodity data (minimal)
COMMODITIES: Dict[str, Commodity] = {}

def get_commodity(name: str) -> Optional[Commodity]:
    return COMMODITIES.get(name)

def get_all_commodities() -> Dict[str, Commodity]:
    return COMMODITIES

__all__ = ['Commodity', 'COMMODITIES', 'get_commodity', 'get_all_commodities']