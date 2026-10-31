from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.app.core.enums import ActivityCategory, Scope2Method, Unit
from api.app.core.models import (
    ActivityRecord,
    EmissionResult,
    Facility,
    MeterReading,
    Organization,
)
from seed.seed_activity import seed_activities_and_readings


def test_seed_activity_execution_and_idempotency(db: Session):
    """Verifies that seed_activities_and_readings creates 24 months of data,
    green tariff results, meter readings, and is completely idempotent."""
    # First execution
    act_count, res_count, err_count = seed_activities_and_readings(db)
    assert act_count == 240
    assert res_count == 268
    assert err_count == 0

    org = db.query(Organization).filter(Organization.name == "Demo GmbH").first()
    assert org is not None

    # Verify facilities and departments covered
    facs = db.query(Facility).filter(Facility.org_id == org.id).all()
    assert len(facs) == 3
    fac_names = {f.name for f in facs}
    assert fac_names == {"Dortmund HQ", "Essen Plant", "Köln Warehouse"}

    # Verify categories covered
    categories = {
        r[0]
        for r in db.query(ActivityRecord.category)
        .filter(ActivityRecord.org_id == org.id)
        .distinct()
        .all()
    }
    assert categories == {
        ActivityCategory.electricity,
        ActivityCategory.natural_gas,
        ActivityCategory.diesel,
        ActivityCategory.fleet_km,
        ActivityCategory.hotel_night,
    }

    # Verify Dortmund HQ has both location-based and market-based emission results
    hq = next(f for f in facs if f.name == "Dortmund HQ")
    hq_elec_acts = (
        db.query(ActivityRecord)
        .filter(
            ActivityRecord.org_id == org.id,
            ActivityRecord.facility_id == hq.id,
            ActivityRecord.category == ActivityCategory.electricity,
        )
        .all()
    )
    assert len(hq_elec_acts) == 24

    first_hq_elec = hq_elec_acts[0]
    methods = {
        r.method
        for r in db.query(EmissionResult)
        .filter(
            EmissionResult.activity_id == first_hq_elec.id,
            EmissionResult.is_current.is_(True),
        )
        .all()
    }
    assert methods == {Scope2Method.location_based, Scope2Method.market_based}

    # Verify other facilities (e.g. Essen) have only location-based for electricity
    essen = next(f for f in facs if f.name == "Essen Plant")
    essen_elec = (
        db.query(ActivityRecord)
        .filter(
            ActivityRecord.org_id == org.id,
            ActivityRecord.facility_id == essen.id,
            ActivityRecord.category == ActivityCategory.electricity,
        )
        .first()
    )
    essen_methods = {
        r.method
        for r in db.query(EmissionResult)
        .filter(
            EmissionResult.activity_id == essen_elec.id,
            EmissionResult.is_current.is_(True),
        )
        .all()
    }
    assert essen_methods == {Scope2Method.location_based}

    # Verify today's meter readings
    readings = db.query(MeterReading).filter(MeterReading.org_id == org.id).all()
    assert len(readings) == 3
    for r in readings:
        assert r.recorded_at.date() == date.today()
        # Ensure emission results exist for the reading
        r_results = (
            db.query(EmissionResult)
            .filter(
                EmissionResult.reading_id == r.id,
                EmissionResult.is_current.is_(True),
            )
            .all()
        )
        assert len(r_results) >= 1

    # Verify idempotency by running a second time
    act_count2, res_count2, err_count2 = seed_activities_and_readings(db)
    assert act_count2 == 240
    assert res_count2 == 268
    assert err_count2 == 0

