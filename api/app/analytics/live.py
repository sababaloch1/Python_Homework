"""api/app/analytics/live.py - FR-3.09: Live monitor of today's meter readings.

GET /analytics/live
Returns:
{
    "as_of": "2026-10-30T12:00:00Z",
    "facilities": [
        {"name": "Essen Plant", "t_co2e": 0.4356},
        {"name": "Dortmund HQ", "t_co2e": 0.1634},
        {"name": "Köln Warehouse", "t_co2e": 0.1379}
    ]
}

Enforces all non-negotiable rules:
- Tenant isolation: MeterReading.org_id == org_id
- Only READS emission_results
- Totals computed in SQL (func.sum, group_by)
- Base filter: is_current is True AND kg_co2e is not NULL AND (method == location_based OR method IS NULL)
- kg -> tonnes by dividing by 1000
- Meter readings recorded today (date(recorded_at) == today)
"""

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.enums import Scope2Method
from api.app.core.models import Asset, EmissionResult, Facility, MeterReading, User

router = APIRouter(tags=["S3 Analytics"])


def calculate_live_emissions(
    db: Session,
    org_id: UUID,
    target_date: Optional[date] = None,
) -> dict:
    """Computes today's emissions per facility based on meter readings.

    Uses MeterReading -> Asset -> Facility joins with EmissionResult.
    Applies the base results filter and computes sums in SQL.
    """
    if target_date is None:
        target_date = date.today()

    start_of_day = datetime.combine(target_date, time.min)
    end_of_day = datetime.combine(target_date, time.max)

    # Base query joining EmissionResult -> MeterReading -> Asset -> Facility
    stmt = (
        select(
            func.coalesce(Facility.name, "Unassigned").label("facility_name"),
            func.sum(EmissionResult.kg_co2e).label("total_kg"),
        )
        .select_from(EmissionResult)
        .join(MeterReading, EmissionResult.reading_id == MeterReading.id)
        .join(Asset, MeterReading.asset_id == Asset.id)
        .outerjoin(Facility, Asset.facility_id == Facility.id)
        .where(
            MeterReading.org_id == org_id,
            MeterReading.recorded_at >= start_of_day,
            MeterReading.recorded_at <= end_of_day,
            EmissionResult.is_current.is_(True),
            EmissionResult.kg_co2e.is_not(None),
            or_(
                EmissionResult.method == Scope2Method.location_based,
                EmissionResult.method.is_(None),
            ),
        )
        .group_by(func.coalesce(Facility.name, "Unassigned"))
        .order_by(func.sum(EmissionResult.kg_co2e).desc())
    )

    rows = db.execute(stmt).all()

    facilities_list = []
    for fac_name, total_kg in rows:
        t_val = round(float((total_kg or Decimal(0)) / Decimal(1000)), 4)
        facilities_list.append({
            "name": fac_name,
            "t_co2e": t_val,
        })

    # As of ISO timestamp (now in UTC)
    as_of = datetime.now(timezone.utc).isoformat()

    return {
        "as_of": as_of,
        "facilities": facilities_list,
    }


@router.get("/live")
def get_live_emissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """GET /analytics/live - FR-3.09: Live emissions today per facility."""
    return calculate_live_emissions(db, current_user.org_id)
