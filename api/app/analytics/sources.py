"""api/app/analytics/sources.py - FR-3.04 & NFR-3.05: Top sources and activity records.

Endpoints:
1. GET /analytics/top-sources?limit=5&start=&end=
   Returns: [{"category": "...", "facility": "...", "t_co2e": ...}, ...]
2. GET /analytics/records?scope=&category=&facility_id=&start=&end=&limit=&offset=
   Returns: [{"id": "...", "category": "...", "kg_co2e": ..., "error": ..., "summary": ...}, ...]
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api.app.analytics.cache import cached_analytics
from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.enums import ActivityCategory, Scope, Scope2Method
from api.app.core.models import (
    ActivityRecord,
    Department,
    EmissionResult,
    Facility,
    User,
)

router = APIRouter(tags=["S3 Analytics"])


@cached_analytics("top-sources")
def calculate_top_sources(
    db: Session,
    org_id: UUID,
    limit: int = 5,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> List[dict]:
    """Computes top emission sources grouped by category + facility, sorted descending in SQL.

    Enforces all non-negotiable rules:
    - Tenant isolation: ActivityRecord.org_id == org_id
    - S3 only READS emission_results
    - Totals computed in SQL (func.sum + group_by + order_by desc + limit)
    - Base filter: is_current is True AND kg_co2e is not NULL AND (method == location_based OR method IS NULL)
    - kg -> tonnes by dividing by 1000
    - Missing facility = "Unassigned"
    """
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

    fac_name = func.coalesce(Facility.name, "Unassigned").label("facility_name")
    stmt = (
        select(
            ActivityRecord.category,
            fac_name,
            func.sum(EmissionResult.kg_co2e).label("total_kg"),
        )
        .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
        .outerjoin(Facility, ActivityRecord.facility_id == Facility.id)
        .where(*base_where)
        .group_by(ActivityRecord.category, fac_name)
        .order_by(func.sum(EmissionResult.kg_co2e).desc())
        .limit(max(1, limit))
    )

    rows = db.execute(stmt).all()
    return [
        {
            "category": r[0].value if hasattr(r[0], "value") else str(r[0]),
            "facility": r[1] or "Unassigned",
            "facility_name": r[1] or "Unassigned",
            "t_co2e": round(float(r[2] / Decimal("1000")), 4),
        }
        for r in rows
        if r[2] is not None
    ]


def get_activity_records(
    db: Session,
    org_id: UUID,
    scope: Optional[str] = None,
    category: Optional[str] = None,
    facility_id: Optional[UUID] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[dict]:
    """Returns underlying activity records joined with their current emission result and trace details."""
    base_where = [
        ActivityRecord.org_id == org_id,
        EmissionResult.is_current.is_(True),
        or_(
            EmissionResult.method == Scope2Method.location_based,
            EmissionResult.method.is_(None),
        ),
    ]

    if scope is not None:
        # Match enum or string
        try:
            scope_enum = Scope(scope)
            base_where.append(EmissionResult.scope == scope_enum)
        except ValueError:
            base_where.append(EmissionResult.scope == scope)

    if category is not None:
        try:
            cat_enum = ActivityCategory(category)
            base_where.append(ActivityRecord.category == cat_enum)
        except ValueError:
            base_where.append(ActivityRecord.category == category)

    if facility_id is not None:
        base_where.append(ActivityRecord.facility_id == facility_id)

    if start is not None:
        base_where.append(ActivityRecord.period_start >= start)
    if end is not None:
        base_where.append(ActivityRecord.period_start <= end)

    stmt = (
        select(ActivityRecord, EmissionResult, Facility.name, Department.name)
        .join(EmissionResult, EmissionResult.activity_id == ActivityRecord.id)
        .outerjoin(Facility, ActivityRecord.facility_id == Facility.id)
        .outerjoin(Department, ActivityRecord.department_id == Department.id)
        .where(*base_where)
        .order_by(ActivityRecord.period_start.desc(), ActivityRecord.id)
    )

    if offset > 0:
        stmt = stmt.offset(offset)
    if limit is not None and limit > 0:
        stmt = stmt.limit(limit)

    rows = db.execute(stmt).all()
    output = []
    for act, res, fac_name, dept_name in rows:
        trace = res.trace or {}
        kg = res.kg_co2e
        t_val = round(float(kg / Decimal("1000")), 4) if kg is not None else None
        kg_float = round(float(kg), 4) if kg is not None else None
        cost_float = round(float(res.cost_eur), 2) if res.cost_eur is not None else None

        summary_text = (
            trace.get("formula")
            or trace.get("summary")
            or (f"{act.amount} {act.unit.value} -> {kg_float} kg CO2e" if kg_float is not None else None)
        )
        error_text = trace.get("error")

        output.append({
            "id": str(act.id),
            "period_start": act.period_start.isoformat() if act.period_start else None,
            "period_end": act.period_end.isoformat() if act.period_end else None,
            "category": act.category.value if hasattr(act.category, "value") else str(act.category),
            "amount": float(act.amount) if act.amount is not None else 0.0,
            "unit": act.unit.value if hasattr(act.unit, "value") else str(act.unit),
            "scope": res.scope.value if res.scope and hasattr(res.scope, "value") else (str(res.scope) if res.scope else None),
            "facility_id": str(act.facility_id) if act.facility_id else None,
            "facility_name": fac_name or "Unassigned",
            "department_id": str(act.department_id) if act.department_id else None,
            "department_name": dept_name or "Unassigned",
            "kg_co2e": kg_float,
            "t_co2e": t_val,
            "cost_eur": cost_float,
            "error": error_text,
            "summary": summary_text,
            "evidence_ref": act.evidence_ref,
            "note": act.note,
        })
    return output


@router.get("/top-sources")
def get_top_sources(
    limit: int = Query(5, ge=1, le=50, description="Number of top sources to return"),
    start: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return calculate_top_sources(db, current_user.org_id, limit=limit, start=start, end=end)


@router.get("/records")
def get_records(
    scope: Optional[str] = Query(None, description="Filter by Scope (scope_1, scope_2, scope_3)"),
    category: Optional[str] = Query(None, description="Filter by ActivityCategory"),
    facility_id: Optional[UUID] = Query(None, description="Filter by facility UUID"),
    start: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: Optional[int] = Query(None, ge=1, le=5000, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_activity_records(
        db,
        current_user.org_id,
        scope=scope,
        category=category,
        facility_id=facility_id,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )
