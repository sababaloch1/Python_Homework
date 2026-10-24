from typing import Iterable, Optional

from .errors import MissingFactorError
from .types import Factor, Tariff

GLOBAL_REGION = "GLOBAL"


def _best_in_region(factors, region: str, year: int) -> Optional[Factor]:
    candidates = [f for f in factors if f.region == region]
    if not candidates:
        return None
    # exact year first, otherwise nearest year; ties -> earlier year, then higher version
    return min(candidates, key=lambda f: (abs(f.year - year), f.year, -f.version))


def select_factor(factors: Iterable[Factor], activity_type: str, region: str, year: int) -> Factor:
    """FR-2.06: country+year, else nearest year in that country, else GLOBAL (same rule)."""
    active = [f for f in factors if f.is_active and f.activity_type == activity_type]
    for r in (region, GLOBAL_REGION):
        best = _best_in_region(active, r, year)
        if best is not None:
            return best
    raise MissingFactorError(
        f"No active emission factor for '{activity_type}' in '{region}' or GLOBAL (year {year})"
    )


def select_tariff(tariffs: Iterable[Tariff], activity_type: str, region: str, year: int) -> Optional[Tariff]:
    """Same fallback as factors (country, nearest year, GLOBAL). None when no tariff exists:
    a missing tariff only means 'no cost estimate', it is not an error."""
    matching = [t for t in tariffs if t.activity_type == activity_type]
    for r in (region, GLOBAL_REGION):
        candidates = [t for t in matching if t.region == r]
        if candidates:
            return min(candidates, key=lambda t: (abs(t.year - year), t.year))
    return None
