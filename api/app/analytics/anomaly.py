"""api/app/analytics/anomaly.py - FR-3.10: Anomaly detection on monthly emission totals.

A month is flagged when its emissions exceed the average of the previous 3 months by more than 20%.
Rules:
- First 3 months are never flagged.
- If previous 3-month average is 0, never flagged.
- Strict boundary: > 20.0% (exact 20% is not flagged).
"""

from decimal import Decimal
from typing import List, Optional, Union
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func, or_, select
from sqlalchemy.orm import Session

from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.enums import Scope2Method
from api.app.core.models import ActivityRecord, EmissionResult, User

router = APIRouter(tags=["S3 Analytics"])


def flag_months(monthly_totals: list) -> List[dict]:
    """Pure function: flag a month when its value is more than 20% above the average of the previous 3 months.

    Accepts:
    - List of dicts: [{"month": "2026-03", "value": 65.2}] or [{"month": "2026-03", "t_co2e": 65.2}]
    - List of tuples: [("2026-03", 65.2)]
    - List of numbers: [10.0, 10.0, 10.0, 15.0]

    Returns list of flagged records:
    [
        {
            "month": "2026-03",
            "value": 65.6073,
            "average_3m": 48.3411,
            "pct_above": 35.72,
        }
    ]
    """
    if len(monthly_totals) < 4:
        return []

    parsed = []
    for idx, item in enumerate(monthly_totals):
        if isinstance(item, dict):
            m = item.get("month", f"M{idx + 1}")
            val = float(item.get("value", item.get("t_co2e", 0.0)))
        elif isinstance(item, (tuple, list)):
            m = str(item[0])
            val = float(item[1])
        else:
            m = f"M{idx + 1}"
            val = float(item)
        parsed.append((m, val))

    flagged = []
    for i in range(3, len(parsed)):
        val = parsed[i][1]
        prev3 = [parsed[j][1] for j in range(i - 3, i)]
        avg3 = sum(prev3) / 3.0

        if avg3 <= 0:
            continue

        pct_above = ((val - avg3) / avg3) * 100.0
        # Strict boundary: must be MORE than 20% above average
        if pct_above > 20.0:
            flagged.append({
                "month": parsed[i][0],
                "value": round(val, 4),
                "average_3m": round(avg3, 4),
                "pct_above": round(pct_above, 2),
            })

    return flagged


def calculate_anomalies(db: Session, org_id: UUID) -> List[dict]:
    """Extracts chronological monthly emission totals for an organization in SQL and applies flag_months."""
    stmt = (
        select(
            extract("year", ActivityRecord.period_start).label("yr"),
            extract("month", ActivityRecord.period_start).label("mo"),
            func.sum(EmissionResult.kg_co2e).label("total_kg"),
        )
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
        .group_by(
            extract("year", ActivityRecord.period_start),
            extract("month", ActivityRecord.period_start),
        )
        .order_by(
            extract("year", ActivityRecord.period_start),
            extract("month", ActivityRecord.period_start),
        )
    )
    rows = db.execute(stmt).all()
    monthly = [
        {
            "month": f"{int(r[0])}-{int(r[1]):02d}",
            "value": round(float(r[2] / Decimal("1000")), 4),
        }
        for r in rows
        if r[2] is not None
    ]
    return flag_months(monthly)


@router.get("/anomalies")
def get_anomalies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return calculate_anomalies(db, current_user.org_id)
