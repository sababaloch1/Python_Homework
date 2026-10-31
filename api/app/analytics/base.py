"""api/app/analytics/base.py - Base query builder and shared S3 rules.

NON-NEGOTIABLE RULES:
- S3 only READS emission_results; never insert/update/delete there.
- Totals are computed in SQL (func.sum + group_by), never Python loops.
- Every query is filtered by current_user.org_id.
- Base filter for every total:
    is_current is True AND kg_co2e is not NULL AND
    (method == location_based OR method IS NULL).
  Never add market_based rows to location_based ones, and never drop rows whose method is NULL.
- kg -> tonnes by dividing by 1000. Convert Decimal to float only for JSON/charts.
- Use SQLAlchemy extract() for dates, never database-specific functions.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from api.app.core.enums import Scope2Method
from api.app.core.models import ActivityRecord, EmissionResult

router = APIRouter(tags=["S3 Analytics"])


@router.get("/base/ping")
def base_ping():
    return {"ok": True}


def base_results_query(
    db: Session,
    org_id: UUID,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> Select:
    """Builds the foundational SQLAlchemy Select query joining EmissionResult to ActivityRecord.

    Enforces:
    1. Tenant isolation: ActivityRecord.org_id == org_id
    2. is_current is True
    3. EmissionResult.kg_co2e is not None
    4. Method filter: (EmissionResult.method == Scope2Method.location_based OR EmissionResult.method.is_(None))
    5. Optional period_start date range [start, end]
    """
    stmt = (
        select(EmissionResult, ActivityRecord)
        .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
        .where(
            ActivityRecord.org_id == org_id,
            EmissionResult.is_current.is_(True),
            EmissionResult.kg_co2e.is_not(None),
            or_(
                EmissionResult.method == Scope2Method.location_based,
                EmissionResult.method.is_(None),
            ),
        )
    )

    if start is not None:
        stmt = stmt.where(ActivityRecord.period_start >= start)
    if end is not None:
        stmt = stmt.where(ActivityRecord.period_start <= end)

    return stmt
