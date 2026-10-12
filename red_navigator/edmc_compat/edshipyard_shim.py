"""
Shim module for EDMC's edshipyard module.
Provides shipyard helper functions.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

# Ship data (minimal)
SHIPS: Dict[str, Dict[str, Any]] = {}

MODULES: Dict[str, Dict[str, Any]] = {}

def get_ship(name: str) -> Optional[Dict[str, Any]]:
    return SHIPS.get(name)

def get_module(name: str) -> Optional[Dict[str, Any]]:
    return MODULES.get(name)

def get_all_ships() -> Dict[str, Dict[str, Any]]:
    return SHIPS

def get_all_modules() -> Dict[str, Dict[str, Any]]:
    return MODULES

__all__ = ['SHIPS', 'MODULES', 'get_ship', 'get_module', 'get_all_ships', 'get_all_modules']