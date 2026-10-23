"""Database access for S2. Converts ORM rows to the pure core objects and back."""
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.app.core.enums import ActivityCategory, Scope, Unit
from api.app.core.models import EmissionFactor, RegionTariff
from api.app.engine.core import Factor, Tariff

KG_SCALE = Decimal("0.000001")   # emission_factors.kg_co2e_per_unit is NUMERIC(14,6)
EUR_SCALE = Decimal("0.0001")    # region_tariffs.eur_per_unit is NUMERIC(10,4)


def enum_value(x):
    return x.value if isinstance(x, Enum) else x


def to_core_factor(row: EmissionFactor) -> Factor:
    return Factor(
        id=str(row.id),
        activity_type=enum_value(row.activity_type),
        region=row.region,
        year=row.year,
        unit=enum_value(row.unit),
        kg_co2e_per_unit=Decimal(str(row.kg_co2e_per_unit)),
        scope=enum_value(row.scope),
        ghg_category=row.ghg_category,
        source=row.source or "",
        version=row.version or 1,
        is_active=bool(row.is_active),
    )


def to_core_tariff(row: RegionTariff) -> Tariff:
    return Tariff(
        id=str(row.id),
        region=row.region,
        activity_type=enum_value(row.activity_type),
        unit=enum_value(row.unit),
        eur_per_unit=Decimal(str(row.eur_per_unit)),
        year=row.year,
        source=row.source or "",
    )


def load_active_factors(db: Session, activity_type: str) -> List[Factor]:
    rows = db.execute(
        select(EmissionFactor).where(
            EmissionFactor.activity_type == ActivityCategory(activity_type),
            EmissionFactor.is_active.is_(True),
        )
    ).scalars().all()
    return [to_core_factor(r) for r in rows]


def load_tariffs(db: Session, activity_type: str) -> List[Tariff]:
    rows = db.execute(
        select(RegionTariff).where(RegionTariff.activity_type == ActivityCategory(activity_type))
    ).scalars().all()
    return [to_core_tariff(r) for r in rows]


def upsert_factor(db: Session, data: dict) -> Tuple[EmissionFactor, str]:
    """Create a factor, or a NEW VERSION if one already exists for (type, region, year).

    Old versions are deactivated, never edited or deleted (NFR-2.08).
    Returns (row, status) with status in {"created", "versioned", "unchanged"}.
    The caller commits, so an import is atomic.
    """
    activity_type = ActivityCategory(data["activity_type"])
    region = data["region"].strip().upper()
    year = int(data["year"])
    unit = Unit(data["unit"])
    scope = Scope(data["scope"])
    kg = Decimal(str(data["kg_co2e_per_unit"])).quantize(KG_SCALE)

    key = (
        EmissionFactor.activity_type == activity_type,
        EmissionFactor.region == region,
        EmissionFactor.year == year,
    )
    active = db.execute(
        select(EmissionFactor).where(*key, EmissionFactor.is_active.is_(True))
        .order_by(EmissionFactor.version.desc())
    ).scalars().first()
    max_version = db.execute(select(func.max(EmissionFactor.version)).where(*key)).scalar()

    if active is not None:
        same = (
            enum_value(active.unit) == unit.value
            and enum_value(active.scope) == scope.value
            and Decimal(str(active.kg_co2e_per_unit)).quantize(KG_SCALE) == kg
            and (active.ghg_category or None) == (data.get("ghg_category") or None)
            and (active.source or "") == data["source"]
        )
        if same:
            return active, "unchanged"
        active.is_active = False

    row = EmissionFactor(
        activity_type=activity_type, region=region, year=year, unit=unit,
        kg_co2e_per_unit=kg, scope=scope, ghg_category=data.get("ghg_category") or None,
        source=data["source"], version=(max_version or 0) + 1, is_active=True,
    )
    db.add(row)
    db.flush()
    return row, ("created" if max_version is None else "versioned")


def deactivate_factor(db: Session, factor_id) -> Optional[EmissionFactor]:
    """Soft delete: factors are never hard-deleted (NFR-2.08)."""
    row = db.get(EmissionFactor, factor_id)
    if row is not None:
        row.is_active = False
        db.flush()
    return row


def upsert_tariff(db: Session, data: dict) -> Tuple[RegionTariff, str]:
    activity_type = ActivityCategory(data["activity_type"])
    region = data["region"].strip().upper()
    year = int(data["year"])
    unit = Unit(data["unit"])
    eur = Decimal(str(data["eur_per_unit"])).quantize(EUR_SCALE)

    row = db.execute(
        select(RegionTariff).where(
            RegionTariff.activity_type == activity_type,
            RegionTariff.region == region,
            RegionTariff.year == year,
        )
    ).scalars().first()
    if row is None:
        row = RegionTariff(activity_type=activity_type, region=region, year=year, unit=unit,
                           eur_per_unit=eur, source=data["source"])
        db.add(row)
        db.flush()
        return row, "created"
    if (enum_value(row.unit) == unit.value
            and Decimal(str(row.eur_per_unit)).quantize(EUR_SCALE) == eur
            and (row.source or "") == data["source"]):
        return row, "unchanged"
    row.unit, row.eur_per_unit, row.source = unit, eur, data["source"]
    db.flush()
    return row, "updated"
