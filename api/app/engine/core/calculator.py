from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from .types import Activity, CalculationResult, Factor, Tariff
from .units import UnitConverter

_converter = UnitConverter()


def to_decimal(value) -> Decimal:
    """Accept Decimal/int/str only; floats would bring binary rounding in (NFR-2.02)."""
    if isinstance(value, float):
        raise TypeError("Use Decimal or str, not float")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def calculate(activity: Activity, factor: Factor, method: Optional[str] = None) -> CalculationResult:
    """kg CO2e = amount converted to the factor's unit x kg_co2e_per_unit (FR-2.05/2.09)."""
    amount = to_decimal(activity.amount)
    converted, ratio = _converter.convert(amount, activity.unit, factor.unit)
    kg = converted * factor.kg_co2e_per_unit
    if factor.scope == "scope_2" and method is None:
        method = "location_based"
    trace = {
        "factor_id": factor.id,
        "factor_version": factor.version,
        "factor_source": factor.source,
        "factor_year": factor.year,
        "factor_region": factor.region,
        "amount": str(amount),
        "amount_unit": activity.unit,
        "converted_amount": str(converted),
        "factor_unit": factor.unit,
        "unit_ratio": str(ratio),
        "kg_co2e_per_unit": str(factor.kg_co2e_per_unit),
        "formula": f"{converted} {factor.unit} x {factor.kg_co2e_per_unit} kg CO2e/{factor.unit}",
        "kg_co2e": str(kg),
    }
    return CalculationResult(kg_co2e=kg, scope=factor.scope, method=method,
                             factor_id=factor.id, trace=trace)


def calculate_cost(activity: Activity, tariff: Tariff) -> Decimal:
    """Estimated cost in EUR: amount converted to the tariff's unit x eur_per_unit."""
    converted, _ = _converter.convert(to_decimal(activity.amount), activity.unit, tariff.unit)
    return converted * tariff.eur_per_unit


def round_for_display(value: Decimal, places: int = 2) -> Decimal:
    """Rounding happens only here, for display (NFR-2.02)."""
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
