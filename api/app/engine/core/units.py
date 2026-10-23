from decimal import Decimal
from typing import Tuple

from .errors import UnknownUnitError

# unit -> (dimension, ratio to the dimension's base unit). Ratios are strings -> exact Decimal.
_UNITS = {
    "kWh": ("energy", Decimal("1")),
    "MWh": ("energy", Decimal("1000")),
    "kg": ("mass", Decimal("1")),
    "tonne": ("mass", Decimal("1000")),
    "litre": ("volume", Decimal("1")),
    "m3": ("volume", Decimal("1000")),
    "km": ("distance", Decimal("1")),
    "passenger_km": ("passenger_distance", Decimal("1")),
    "night": ("night", Decimal("1")),
}


class UnitConverter:
    """Converts within one dimension only (energy, mass, volume).

    Cross-dimension conversion (litre -> kWh, m3 -> kWh) needs fuel properties,
    so it is rejected instead of guessed (NFR-2.10).
    """

    def is_known(self, unit: str) -> bool:
        return unit in _UNITS

    def ratio(self, from_unit: str, to_unit: str) -> Decimal:
        for u in (from_unit, to_unit):
            if u not in _UNITS:
                raise UnknownUnitError(f"Unknown unit '{u}'")
        from_dim, from_ratio = _UNITS[from_unit]
        to_dim, to_ratio = _UNITS[to_unit]
        if from_dim != to_dim:
            raise UnknownUnitError(
                f"Cannot convert '{from_unit}' ({from_dim}) to '{to_unit}' ({to_dim})"
            )
        return from_ratio / to_ratio

    def convert(self, amount: Decimal, from_unit: str, to_unit: str) -> Tuple[Decimal, Decimal]:
        """Return (converted_amount, ratio_used)."""
        r = self.ratio(from_unit, to_unit)
        return amount * r, r