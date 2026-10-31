"""api/app/analytics/trend.py - FR-3.02: 12-month emissions trend and YoY comparison.

GET /analytics/trend?anchor=
Returns:
{
    "months": [
        {"month": "2025-11", "t_co2e": 46.3006},
        ...
        {"month": "2026-10", "t_co2e": 44.2775}
    ],
    "prev_year_total": 529.7001,
    "current_total": 549.2268,
    "pct_change": 3.69
}
"""

import calendar
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import extract, func, or_, select
from sqlalchemy.orm import Session

from api.app.analytics.cache import cached_analytics
from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.enums import Scope2Method
from api.app.core.models import ActivityRecord, EmissionResult, User

router = APIRouter(tags=["S3 Analytics"])


def _get_12_month_tuples(anchor: date) -> List[Tuple[int, int]]:
    """Returns 12 chronological (year, month) tuples ending at anchor's month."""
    months = []
    y, m = anchor.year, anchor.month
    for _ in range(12):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()
    return months


@cached_analytics("trend")
def calculate_trend(
    db: Session,
    org_id: UUID,
    anchor_date: Optional[date] = None,
) -> dict:
    """Computes the 12-month trend and year-over-year percentage change.

    Enforces all non-negotiable rules:
    - Tenant isolation: ActivityRecord.org_id == org_id
    - S3 only READS emission_results
    - Totals computed in SQL (func.sum + group_by extract year/month), never Python loops
    - Base filter: is_current is True AND kg_co2e is not NULL AND (method == location_based OR method IS NULL)
    - kg -> tonnes by dividing by 1000
    - Empty months = 0.0
    - pct_change is null when prev_year_total is 0
    """
    if anchor_date is None:
        today = date.today()
        latest = (
            db.query(func.max(ActivityRecord.period_start))
            .filter(ActivityRecord.org_id == org_id)
            .scalar()
        )
        if latest is not None:
            anchor_date = max(today, latest)
        else:
            anchor_date = today if today.year >= 2026 else date(2026, 10, 31)

    # 1. Determine current 12-month window and previous 12-month window
    curr_months = _get_12_month_tuples(anchor_date)

    # 12 months immediately preceding curr_months
    first_curr_y, first_curr_m = curr_months[0]
    prev_end_m = first_curr_m - 1
    prev_end_y = first_curr_y
    if prev_end_m == 0:
        prev_end_m = 12
        prev_end_y -= 1
    prev_months = _get_12_month_tuples(date(prev_end_y, prev_end_m, 1))

    start_prev = date(prev_months[0][0], prev_months[0][1], 1)
    start_curr = date(curr_months[0][0], curr_months[0][1], 1)
    end_curr_last_day = calendar.monthrange(curr_months[-1][0], curr_months[-1][1])[1]
    end_curr = date(curr_months[-1][0], curr_months[-1][1], end_curr_last_day)

    base_where = [
        ActivityRecord.org_id == org_id,
        EmissionResult.is_current.is_(True),
        EmissionResult.kg_co2e.is_not(None),
        or_(
            EmissionResult.method == Scope2Method.location_based,
            EmissionResult.method.is_(None),
        ),
    ]

    # 2. Monthly aggregates for the current 12 months using SQL extract(year/month) + group_by
    monthly_stmt = (
        select(
            extract("year", ActivityRecord.period_start).label("yr"),
            extract("month", ActivityRecord.period_start).label("mo"),
            func.sum(EmissionResult.kg_co2e).label("monthly_kg"),
        )
        .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
        .where(
            *base_where,
            ActivityRecord.period_start >= start_curr,
            ActivityRecord.period_start <= end_curr,
        )
        .group_by(
            extract("year", ActivityRecord.period_start),
            extract("month", ActivityRecord.period_start),
        )
    )
    month_rows = db.execute(monthly_stmt).all()
    month_data = {
        f"{int(r[0])}-{int(r[1]):02d}": round(float(r[2] / Decimal("1000")), 4)
        for r in month_rows
        if r[2] is not None
    }

    result_months = [
        {"month": f"{yr}-{mo:02d}", "t_co2e": month_data.get(f"{yr}-{mo:02d}", 0.0)}
        for yr, mo in curr_months
    ]

    # 3. Compute current 12-month total in SQL
    curr_total_stmt = (
        select(func.sum(EmissionResult.kg_co2e))
        .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
        .where(
            *base_where,
            ActivityRecord.period_start >= start_curr,
            ActivityRecord.period_start <= end_curr,
        )
    )
    curr_kg = db.execute(curr_total_stmt).scalar()
    current_total = round(float(curr_kg / Decimal("1000")), 4) if curr_kg else 0.0

    # 4. Compute previous 12-month total in SQL
    prev_total_stmt = (
        select(func.sum(EmissionResult.kg_co2e))
        .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
        .where(
            *base_where,
            ActivityRecord.period_start >= start_prev,
            ActivityRecord.period_start < start_curr,
        )
    )
    prev_kg = db.execute(prev_total_stmt).scalar()
    prev_year_total = round(float(prev_kg / Decimal("1000")), 4) if prev_kg else 0.0

    # 5. YoY % change (null when prev_year_total is 0)
    pct_change: Optional[float] = None
    if prev_year_total > 0:
        pct_change = round(((current_total - prev_year_total) / prev_year_total) * 100, 2)

    return {
        "months": result_months,
        "prev_year_total": prev_year_total,
        "current_total": current_total,
        "pct_change": pct_change,
    }


@router.get("/trend")
def get_trend(
    anchor: Optional[date] = Query(None, description="Anchor date for 12-month window (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return calculate_trend(db, current_user.org_id, anchor_date=anchor)
