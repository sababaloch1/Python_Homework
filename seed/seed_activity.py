"""Idempotent seed script for 24 months of activity data and today's meter readings.

Run: python -m seed.seed_activity
"""

import calendar
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api.app.core.database import SessionLocal
from api.app.core.enums import (
    ActivityCategory,
    AssetKind,
    ReadingSource,
    Unit,
    UserRole,
)
from api.app.core.models import (
    ActivityRecord,
    Asset,
    Department,
    EmissionResult,
    Facility,
    FacilityGreenTariff,
    MeterReading,
    Organization,
    Target,
    User,
)
from api.app.engine import repository
from api.app.engine import service as engine_service
from api.app.engine.importer import load_seed_files
from seed.run_seed import DEMO_EMAIL, seed_demo_company

SEED_DIR = Path(__file__).parent

# Seasonality multipliers (1..12)
GAS_SEASONALITY = {
    1: 1.30, 2: 1.25, 3: 1.15, 4: 0.95, 5: 0.80, 6: 0.70,
    7: 0.70, 8: 0.70, 9: 0.80, 10: 1.00, 11: 1.15, 12: 1.30,
}
ELEC_SEASONALITY = {
    1: 1.08, 2: 1.05, 3: 1.00, 4: 0.95, 5: 0.95, 6: 1.00,
    7: 1.02, 8: 1.00, 9: 0.95, 10: 0.98, 11: 1.02, 12: 1.08,
}
TRANS_SEASONALITY = {
    1: 0.95, 2: 0.98, 3: 1.02, 4: 1.02, 5: 1.05, 6: 1.05,
    7: 1.00, 8: 0.92, 9: 1.05, 10: 1.05, 11: 1.00, 12: 0.92,
}
HOTEL_SEASONALITY = {
    1: 0.85, 2: 0.95, 3: 1.10, 4: 1.10, 5: 1.15, 6: 1.10,
    7: 0.90, 8: 0.80, 9: 1.15, 10: 1.15, 11: 1.05, 12: 0.75,
}

SPIKE_YEAR = 2026
SPIKE_MONTH = 3
SPIKE_MULTIPLIER = 1.424  # Delivers ~+35% spike compared to the preceding 3-month average


def clean_demo_activities_and_readings(db: Session, org_id) -> None:
    """Removes previous demo activity records, readings, results and green tariffs for idempotency."""
    act_ids = [r[0] for r in db.query(ActivityRecord.id).filter(ActivityRecord.org_id == org_id).all()]
    reading_ids = [r[0] for r in db.query(MeterReading.id).filter(MeterReading.org_id == org_id).all()]

    if act_ids:
        db.query(EmissionResult).filter(EmissionResult.activity_id.in_(act_ids)).delete(synchronize_session=False)
        db.query(ActivityRecord).filter(ActivityRecord.id.in_(act_ids)).delete(synchronize_session=False)

    if reading_ids:
        db.query(EmissionResult).filter(EmissionResult.reading_id.in_(reading_ids)).delete(synchronize_session=False)
        db.query(MeterReading).filter(MeterReading.id.in_(reading_ids)).delete(synchronize_session=False)

    # Clean targets, assets and green tariffs for Demo GmbH
    db.query(Target).filter(Target.org_id == org_id).delete(synchronize_session=False)
    fac_ids = [f.id for f in db.query(Facility).filter(Facility.org_id == org_id).all()]
    if fac_ids:
        db.query(Asset).filter(Asset.facility_id.in_(fac_ids)).delete(synchronize_session=False)
        db.query(FacilityGreenTariff).filter(FacilityGreenTariff.facility_id.in_(fac_ids)).delete(synchronize_session=False)

    db.commit()


def setup_green_tariff(db: Session, facility_id, start_year: int, end_year: int) -> None:
    """Sets green tariff on the facility across the given year range."""
    for yr in range(start_year, end_year + 1):
        repository.upsert_green_tariff(
            db,
            facility_id,
            {
                "year": yr,
                "kg_co2e_per_kwh": Decimal("0.020"),
                "supplier": "GreenPower Dortmund",
                "source": f"TÜV Rheinland Green Energy Certificate {yr}",
            },
        )
    db.commit()


def get_24_month_range(end_date: date):
    """Returns 24 chronological (year, month) tuples ending with end_date's month."""
    months = []
    y, m = end_date.year, end_date.month
    for _ in range(24):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()
    return months


def seed_activities_and_readings(db: Session) -> Tuple[int, int, int]:
    """Idempotently creates 24 months of activities and today's readings for Demo GmbH."""
    # Ensure factors, tariffs and demo company exist
    load_seed_files(db, SEED_DIR)
    seed_demo_company(db)

    org = db.query(Organization).filter(Organization.name == "Demo GmbH").first()
    if not org:
        raise RuntimeError("Demo GmbH organization not found after seeding.")

    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if not user:
        raise RuntimeError("Demo Admin user not found.")

    # Clean previous run data to ensure idempotency
    clean_demo_activities_and_readings(db, org.id)

    # Facilities and Departments
    facs = {f.name: f for f in db.query(Facility).filter(Facility.org_id == org.id).all()}
    deps = {d.name: d for d in db.query(Department).filter(Department.org_id == org.id).all()}

    hq = facs["Dortmund HQ"]
    essen = facs["Essen Plant"]
    koln = facs["Köln Warehouse"]

    ops = deps["Operations"]
    logistics = deps["Logistics"]
    office = deps["Office"]
    sales = deps["Sales"]

    today = date.today()
    # Anchor to 2026-10 if today is earlier
    anchor_year = max(today.year, 2026)
    anchor_month = today.month if today.year >= 2026 else 10
    anchor_date = date(anchor_year, anchor_month, 1)

    months = get_24_month_range(anchor_date)
    start_year, end_year = months[0][0], months[-1][0]

    # Configure green tariff on Dortmund HQ
    setup_green_tariff(db, hq.id, start_year, end_year)

    # Generate activities
    for yr, mo in months:
        days_in_month = calendar.monthrange(yr, mo)[1]
        period_start = date(yr, mo, 1)
        period_end = date(yr, mo, days_in_month)

        is_spike = (yr == SPIKE_YEAR and mo == SPIKE_MONTH)
        spike_mult = SPIKE_MULTIPLIER if is_spike else 1.0

        elec_factor = ELEC_SEASONALITY[mo] * spike_mult
        gas_factor = GAS_SEASONALITY[mo] * spike_mult
        trans_factor = TRANS_SEASONALITY[mo] * spike_mult
        hotel_factor = HOTEL_SEASONALITY[mo] * spike_mult

        month_activities = [
            # Dortmund HQ
            (hq.id, office.id, ActivityCategory.electricity, Decimal(str(round(15000 * elec_factor, 1))), Unit.kWh),
            (hq.id, ops.id, ActivityCategory.natural_gas, Decimal(str(round(1500 * gas_factor, 1))), Unit.m3),
            (hq.id, sales.id, ActivityCategory.fleet_km, Decimal(str(round(6000 * trans_factor, 1))), Unit.km),
            (hq.id, sales.id, ActivityCategory.hotel_night, Decimal(str(round(25 * hotel_factor))), Unit.night),

            # Essen Plant
            (essen.id, ops.id, ActivityCategory.electricity, Decimal(str(round(35000 * elec_factor, 1))), Unit.kWh),
            (essen.id, ops.id, ActivityCategory.natural_gas, Decimal(str(round(4000 * gas_factor, 1))), Unit.m3),
            (essen.id, ops.id, ActivityCategory.diesel, Decimal(str(round(800 * trans_factor, 1))), Unit.litre),

            # Köln Warehouse
            (koln.id, logistics.id, ActivityCategory.electricity, Decimal(str(round(12000 * elec_factor, 1))), Unit.kWh),
            (koln.id, logistics.id, ActivityCategory.diesel, Decimal(str(round(2500 * trans_factor, 1))), Unit.litre),
            (koln.id, logistics.id, ActivityCategory.fleet_km, Decimal(str(round(4000 * trans_factor, 1))), Unit.km),
        ]

        for fac_id, dept_id, cat, amount, unit in month_activities:
            act = ActivityRecord(
                org_id=org.id,
                facility_id=fac_id,
                department_id=dept_id,
                category=cat,
                amount=amount,
                unit=unit,
                period_start=period_start,
                period_end=period_end,
                created_by=user.id,
                evidence_ref="SEED_DEMO",
            )
            db.add(act)
            db.commit()
            db.refresh(act)
            engine_service.safe_calculate_activity(db, act.id)

    # Meter Readings for today
    assets = [
        Asset(org_id=org.id, facility_id=hq.id, kind=AssetKind.meter, name="HQ Main Electricity Meter", code="MTR-HQ-ELEC", is_active=True),
        Asset(org_id=org.id, facility_id=essen.id, kind=AssetKind.meter, name="Essen Main Electricity Meter", code="MTR-ESS-ELEC", is_active=True),
        Asset(org_id=org.id, facility_id=koln.id, kind=AssetKind.meter, name="Köln Main Electricity Meter", code="MTR-KOL-ELEC", is_active=True),
    ]
    db.add_all(assets)
    db.commit()
    for a in assets:
        db.refresh(a)

    today = date.today()
    recorded_time = datetime(today.year, today.month, today.day, 12, 0, 0)
    readings = [
        MeterReading(org_id=org.id, asset_id=assets[0].id, category=ActivityCategory.electricity, value=Decimal("450.0"), unit=Unit.kWh, recorded_at=recorded_time, source=ReadingSource.device),
        MeterReading(org_id=org.id, asset_id=assets[1].id, category=ActivityCategory.electricity, value=Decimal("1200.0"), unit=Unit.kWh, recorded_at=recorded_time, source=ReadingSource.device),
        MeterReading(org_id=org.id, asset_id=assets[2].id, category=ActivityCategory.electricity, value=Decimal("380.0"), unit=Unit.kWh, recorded_at=recorded_time, source=ReadingSource.device),
    ]
    for r in readings:
        db.add(r)
        db.commit()
        db.refresh(r)
        engine_service.safe_calculate_reading(db, r.id)

    # Demo target: baseline 2025 (full year), target 2030, 30% reduction across all scopes
    demo_target = Target(
        org_id=org.id,
        scope=None,
        baseline_year=2025,
        target_year=2030,
        reduction_pct=Decimal("30.00"),
        created_by=user.id,
    )
    db.add(demo_target)
    db.commit()

    # Query counts
    act_count = db.query(ActivityRecord).filter(ActivityRecord.org_id == org.id).count()

    # Results for activities and readings
    results_stmt = select(func.count(EmissionResult.id)).where(
        EmissionResult.is_current.is_(True),
        or_(
            EmissionResult.activity_id.in_(
                select(ActivityRecord.id).where(ActivityRecord.org_id == org.id)
            ),
            EmissionResult.reading_id.in_(
                select(MeterReading.id).where(MeterReading.org_id == org.id)
            ),
        ),
    )
    res_count = db.execute(results_stmt).scalar() or 0

    err_stmt = select(func.count(EmissionResult.id)).where(
        EmissionResult.is_current.is_(True),
        EmissionResult.kg_co2e.is_(None),
        or_(
            EmissionResult.activity_id.in_(
                select(ActivityRecord.id).where(ActivityRecord.org_id == org.id)
            ),
            EmissionResult.reading_id.in_(
                select(MeterReading.id).where(MeterReading.org_id == org.id)
            ),
        ),
    )
    err_count = db.execute(err_stmt).scalar() or 0

    return act_count, res_count, err_count


if __name__ == "__main__":
    with SessionLocal() as session:
        act_count, res_count, err_count = seed_activities_and_readings(session)
        print(f"[seed] Activities: {act_count}, Results: {res_count}, Results with errors: {err_count}")
