from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class Activity:
    category: str          # e.g. "electricity" (ActivityCategory value)
    amount: Decimal
    unit: str              # e.g. "kWh" (Unit value)
    region: str            # ISO country code of the facility, e.g. "DE"
    year: int


@dataclass(frozen=True)
class Factor:
    id: str
    activity_type: str
    region: str            # ISO code or "GLOBAL"
    year: int
    unit: str
    kg_co2e_per_unit: Decimal
    scope: str             # "scope_1" | "scope_2" | "scope_3"
    ghg_category: Optional[str]
    source: str
    version: int = 1
    is_active: bool = True


@dataclass(frozen=True)
class Tariff:
    id: str
    region: str
    activity_type: str
    unit: str
    eur_per_unit: Decimal
    year: int
    source: str


@dataclass(frozen=True)
class CalculationResult:
    kg_co2e: Decimal
    scope: str
    method: Optional[str]  # "location_based" for scope 2, otherwise None
    factor_id: str
    trace: dict
