"""Shared specs for miner catalogs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ParamSpec:
    name: str
    ptype: str  # "float", "int", "bool", "enum", "str"
    bounds: Optional[Tuple[float, float]] = None
    choices: Optional[List[str]] = None
    default: Any = None
    prom_field: Optional[str] = None
    optimize: bool = True


@dataclass(frozen=True)
class VariantSpec:
    key: str
    label: str
    prom_ref: Optional[str] = None
    parameters: Optional[List[str]] = None  # names of active params for this variant


@dataclass(frozen=True)
class MinerSpec:
    key: str
    family: str
    prom_package: str
    parameters: Dict[str, ParamSpec]
    variants: List[VariantSpec]
    notes: Optional[str] = None
