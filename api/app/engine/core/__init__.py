"""S2 calculation core: plain Python + Decimal. No web or database imports (NFR-2.03)."""
from .calculator import calculate, calculate_cost, round_for_display
from .errors import EmissionError, MissingFactorError, UnknownUnitError
from .selector import select_factor, select_tariff
from .types import Activity, CalculationResult, Factor, Tariff
from .units import UnitConverter

__all__ = [
    "Activity", "CalculationResult", "EmissionError", "Factor", "MissingFactorError",
    "Tariff", "UnitConverter", "UnknownUnitError", "calculate", "calculate_cost",
    "round_for_display", "select_factor", "select_tariff",
]
