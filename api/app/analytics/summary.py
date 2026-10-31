"""api/app/analytics/summary.py - FR-3.01: Emissions and cost summary.

GET /analytics/summary?start=&end=
Returns:
{
    "period": {"start": "...", "end": "..."},
    "total_t_co2e": 4.356,
    "by_scope": {"scope_1": 0.0, "scope_2": 4.356, "scope_3": 0.0},
    "failed_records": 0,
    "total_cost_eur": 2004.00,
    "cost_complete": true
}
"""

from datetime import date
from decimal import Decimal
from typing import Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api.app.analytics.cache import cached_analytics
from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.enums import Scope, Scope2Method
from api.app.core.models import ActivityRecord, EmissionResult, User

router = APIRouter(tags=["S3 Analytics"])


@cached_analytics("summary")
def calculate_summary(
    db: Session,
    org_id: UUID,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict:
    """Computes emissions and cost summary for an organisation in SQL.

    Enforces all non-negotiable rules:
    - Tenant isolation: ActivityRecord.org_id == org_id
    - Only READS emission_results
    - Totals computed in SQL (func.sum, group_by)
    - Base filter: is_current is True AND kg_co2e is not NULL AND (method == location_based OR method IS NULL)
    - kg -> tonnes by dividing by 1000
    - failed_records: current results with NULL kg_co2e in the period
    - cost_complete: False if any current result in the period has NULL cost_eur
    """
    # 1. Total location-based / standard CO2e and total cost in SQL
    base_where = [
        ActivityRecord.org_id == org_id,
        EmissionResult.is_current.is_(True),
        EmissionResult.kg_co2e.is_not(None),
        or_(
            EmissionResult.method == Scope2Method.location_based,
            EmissionResult.method.is_(None),
        ),
    ]
    if start is not None:
        base_where.append(ActivityRecord.period_start >= start)
    if end is not None:
        base_where.append(ActivityRecord.period_start <= end)

    totals_stmt = (
        select(
            func.sum(EmissionResult.kg_co2e).label("total_kg"),
            func.sum(EmissionResult.cost_eur).label("total_cost"),
        )
        .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
        .where(*base_where)
    )
    total_kg, total_cost = db.execute(totals_stmt).one()

    total_t_co2e = round(float(total_kg / Decimal("1000")), 4) if total_kg else 0.0
    total_cost_eur = round(float(total_cost), 2) if total_cost is not None else 0.0

    # 2. Emissions by Scope in SQL
    scope_stmt = (
        select(
            EmissionResult.scope,
            func.sum(EmissionResult.kg_co2e).label("scope_kg"),
        )
        .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
        .where(*base_where)
        .group_by(EmissionResult.scope)
    )
    scope_rows = db.execute(scope_stmt).all()

    by_scope: Dict[str, float] = {
        Scope.scope_1.value: 0.0,
        Scope.scope_2.value: 0.0,
        Scope.scope_3.value: 0.0,
    }
    for scope_val, scope_kg in scope_rows:
        key = scope_val.value if hasattr(scope_val, "value") else str(scope_val)
        if key in by_scope:
            by_scope[key] = round(float((scope_kg or Decimal("0")) / Decimal("1000")), 4)

    # 3. Failed records count: current results with NULL kg_co2e in the period
    failed_where = [
        ActivityRecord.org_id == org_id,
        EmissionResult.is_current.is_(True),
        EmissionResult.kg_co2e.is_(None),
    ]
    if start is not None:
        failed_where.append(ActivityRecord.period_start >= start)
    if end is not None:
        failed_where.append(ActivityRecord.period_start <= end)

    failed_stmt = (
        select(func.count(EmissionResult.id))
        .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
        .where(*failed_where)
    )
    failed_records = db.execute(failed_stmt).scalar() or 0

    # 4. Cost completeness check: false if ANY current result in the period has NULL cost_eur
    # Check all current results for activities in the period (excluding market_based secondary rows)
    null_cost_where = [
        ActivityRecord.org_id == org_id,
        EmissionResult.is_current.is_(True),
        or_(
            EmissionResult.method == Scope2Method.location_based,
            EmissionResult.method.is_(None),
        ),
        EmissionResult.cost_eur.is_(None),
    ]
    if start is not None:
        null_cost_where.append(ActivityRecord.period_start >= start)
    if end is not None:
        null_cost_where.append(ActivityRecord.period_start <= end)

    null_cost_stmt = (
        select(func.count(EmissionResult.id))
        .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
        .where(*null_cost_where)
    )
    null_cost_count = db.execute(null_cost_stmt).scalar() or 0
    cost_complete = (null_cost_count == 0)

    return {
        "period": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
        "total_t_co2e": total_t_co2e,
        "by_scope": by_scope,
        "failed_records": failed_records,
        "total_cost_eur": total_cost_eur,
        "cost_complete": cost_complete,
    }


@router.get("/summary")
def get_summary(
    start: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return calculate_summary(db, current_user.org_id, start=start, end=end)
