"""api/app/analytics/breakdown.py - FR-3.03: Emissions breakdown by dimension.

GET /analytics/breakdown?by=scope|category|department|facility&start=&end=
Returns:
[
    {"label": "Essen Plant", "t_co2e": 558.1166},
    {"label": "Köln Warehouse", "t_co2e": 281.2504},
    {"label": "Dortmund HQ", "t_co2e": 239.5599}
]
Sorted descending; missing department/facility = "Unassigned"; other values of by -> HTTP 422.
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api.app.analytics.cache import cached_analytics
from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.enums import Scope2Method
from api.app.core.models import (
    ActivityRecord,
    Department,
    EmissionResult,
    Facility,
    User,
)

router = APIRouter(tags=["S3 Analytics"])

VALID_DIMENSIONS = {"scope", "category", "department", "facility"}


class BreakdownDimension(str, Enum):
    scope = "scope"
    category = "category"
    department = "department"
    facility = "facility"


@cached_analytics("breakdown")
def calculate_breakdown(
    db: Session,
    org_id: UUID,
    by: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> List[dict]:
    """Computes emissions breakdown by dimension in SQL, sorted descending.

    Enforces all non-negotiable rules:
    - Tenant isolation: ActivityRecord.org_id == org_id
    - S3 only READS emission_results
    - Totals computed in SQL (func.sum + group_by), never Python loops
    - Base filter: is_current is True AND kg_co2e is not NULL AND (method == location_based OR method IS NULL)
    - kg -> tonnes by dividing by 1000
    - Missing department / facility = "Unassigned"
    - Sorted descending
    - Other values of by -> HTTP 422
    """
    if by not in VALID_DIMENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid breakdown dimension '{by}'. Allowed: scope, category, department, facility",
        )

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

    if by == "scope":
        stmt = (
            select(
                EmissionResult.scope.label("label"),
                func.sum(EmissionResult.kg_co2e).label("total_kg"),
            )
            .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
            .where(*base_where)
            .group_by(EmissionResult.scope)
            .order_by(func.sum(EmissionResult.kg_co2e).desc())
        )
        rows = db.execute(stmt).all()
        return [
            {
                "label": r[0].value if hasattr(r[0], "value") else (str(r[0]) if r[0] else "Unassigned"),
                "t_co2e": round(float(r[1] / Decimal("1000")), 4),
            }
            for r in rows
            if r[1] is not None
        ]

    elif by == "category":
        stmt = (
            select(
                ActivityRecord.category.label("label"),
                func.sum(EmissionResult.kg_co2e).label("total_kg"),
            )
            .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
            .where(*base_where)
            .group_by(ActivityRecord.category)
            .order_by(func.sum(EmissionResult.kg_co2e).desc())
        )
        rows = db.execute(stmt).all()
        return [
            {
                "label": r[0].value if hasattr(r[0], "value") else (str(r[0]) if r[0] else "Unassigned"),
                "t_co2e": round(float(r[1] / Decimal("1000")), 4),
            }
            for r in rows
            if r[1] is not None
        ]

    elif by == "department":
        dept_label = func.coalesce(Department.name, "Unassigned").label("label")
        stmt = (
            select(
                dept_label,
                func.sum(EmissionResult.kg_co2e).label("total_kg"),
            )
            .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
            .outerjoin(Department, ActivityRecord.department_id == Department.id)
            .where(*base_where)
            .group_by(dept_label)
            .order_by(func.sum(EmissionResult.kg_co2e).desc())
        )
        rows = db.execute(stmt).all()
        return [
            {
                "label": r[0] if r[0] else "Unassigned",
                "t_co2e": round(float(r[1] / Decimal("1000")), 4),
            }
            for r in rows
            if r[1] is not None
        ]

    elif by == "facility":
        fac_label = func.coalesce(Facility.name, "Unassigned").label("label")
        stmt = (
            select(
                fac_label,
                func.sum(EmissionResult.kg_co2e).label("total_kg"),
            )
            .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
            .outerjoin(Facility, ActivityRecord.facility_id == Facility.id)
            .where(*base_where)
            .group_by(fac_label)
            .order_by(func.sum(EmissionResult.kg_co2e).desc())
        )
        rows = db.execute(stmt).all()
        return [
            {
                "label": r[0] if r[0] else "Unassigned",
                "t_co2e": round(float(r[1] / Decimal("1000")), 4),
            }
            for r in rows
            if r[1] is not None
        ]

    # Should not be reached due to validation check above
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid dimension")


@router.get("/breakdown")
def get_breakdown(
    by: str = Query(..., description="Grouping dimension: scope, category, department, facility"),
    start: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return calculate_breakdown(db, current_user.org_id, by=by, start=start, end=end)
