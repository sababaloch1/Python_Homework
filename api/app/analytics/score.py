"""api/app/analytics/score.py - FR-3.05 & NFR-3.07: Sustainability Score.

Computes 0-100 score across 4 components of 25 points each:
1. YoY Trend (0-25)
2. Target Progress (0-25)
3. Data Completeness (0-25)
4. Emissions per Employee (0-25)
Saves results to sustainability_scores table and returns score + components.
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api.app.analytics.targets import calculate_targets_status
from api.app.analytics.trend import calculate_trend
from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.enums import ScoreLevel, Scope2Method
from api.app.core.models import (
    ActivityRecord,
    EmissionResult,
    Organization,
    SustainabilityScore,
    User,
)

router = APIRouter(tags=["S3 Analytics"])


# =========================================================================
# Pure scoring functions (one per component)
# =========================================================================

def score_yoy_trend(pct_change: Optional[float]) -> dict:
    """Component 1: Evaluates year-over-year emissions reduction (0 - 25 points)."""
    if pct_change is None:
        pts = 12.5
        desc = "No previous year data for comparison (baseline assigned)"
    elif pct_change <= -10.0:
        pts = 25.0
        desc = f"Rapid decarbonisation: {pct_change:+.1f}% YoY"
    elif pct_change <= -5.0:
        pts = 20.0
        desc = f"Strong decarbonisation: {pct_change:+.1f}% YoY"
    elif pct_change <= 0.0:
        pts = 15.0
        desc = f"Modest reduction: {pct_change:+.1f}% YoY"
    elif pct_change <= 5.0:
        pts = 10.0
        desc = f"Slight increase: {pct_change:+.1f}% YoY"
    elif pct_change <= 15.0:
        pts = 5.0
        desc = f"Notable increase: {pct_change:+.1f}% YoY"
    else:
        pts = 0.0
        desc = f"Severe emission growth: {pct_change:+.1f}% YoY"

    return {
        "points": round(pts, 1),
        "max_points": 25.0,
        "pct_change": pct_change,
        "description": desc,
    }


def score_target_progress(targets_status: List[dict]) -> dict:
    """Component 2: Evaluates progress against emission reduction targets (0 - 25 points)."""
    if not targets_status:
        return {
            "points": 0.0,
            "max_points": 25.0,
            "targets_count": 0,
            "on_track_count": 0,
            "description": "No reduction targets configured",
        }

    on_track = sum(1 for t in targets_status if t.get("status") == "on_track")
    total = len(targets_status)
    ratio = on_track / total
    pts = round(ratio * 25.0, 1)

    return {
        "points": pts,
        "max_points": 25.0,
        "targets_count": total,
        "on_track_count": on_track,
        "description": f"{on_track} of {total} targets on track ({ratio * 100:.0f}%)",
    }


def score_data_completeness(months_with_data: int, total_calculations: int, failed_calculations: int) -> dict:
    """Component 3: Evaluates reporting consistency and calculation integrity (0 - 25 points).

    - Up to 15 points for reported months out of the last 12.
    - Up to 10 points for calculation success rate.
    """
    clamped_months = min(12, max(0, months_with_data))
    months_pts = (clamped_months / 12.0) * 15.0

    if total_calculations > 0:
        success_ratio = max(0.0, 1.0 - (failed_calculations / total_calculations))
    else:
        success_ratio = 1.0 if clamped_months > 0 else 0.0
    success_pts = success_ratio * 10.0

    pts = round(months_pts + success_pts, 1)
    return {
        "points": pts,
        "max_points": 25.0,
        "months_with_data": clamped_months,
        "success_rate_pct": round(success_ratio * 100, 1),
        "description": f"{clamped_months}/12 months with data, {success_ratio * 100:.1f}% calculation success rate",
    }


def score_carbon_intensity(total_t_co2e: float, employee_count: Optional[int]) -> dict:
    """Component 4: Evaluates emissions per employee (0 - 25 points)."""
    if employee_count is None or employee_count <= 0:
        return {
            "points": 12.5,
            "max_points": 25.0,
            "intensity_t_per_employee": None,
            "description": "Employee count not configured (baseline assigned)",
        }

    intensity = round(total_t_co2e / employee_count, 2)
    if intensity < 2.0:
        pts = 25.0
        rating = "Exemplary carbon efficiency"
    elif intensity < 4.0:
        pts = 20.0
        rating = "High carbon efficiency"
    elif intensity < 7.0:
        pts = 15.0
        rating = "Average SME intensity"
    elif intensity < 12.0:
        pts = 10.0
        rating = "Moderate intensity"
    elif intensity < 20.0:
        pts = 5.0
        rating = "High carbon intensity"
    else:
        pts = 0.0
        rating = "Very high carbon intensity"

    return {
        "points": pts,
        "max_points": 25.0,
        "intensity_t_per_employee": intensity,
        "description": f"{intensity} t CO2e/employee ({rating})",
    }


# =========================================================================
# Overall Score Aggregation & Persistence
# =========================================================================

def calculate_sustainability_score(db: Session, org_id: UUID) -> dict:
    """Computes and saves the sustainability score (0-100) from 4 components.

    If an organisation has no recorded data, returns score: null with a friendly message.
    """
    # Check if organisation has any activities
    has_activities = (
        db.query(ActivityRecord.id)
        .filter(ActivityRecord.org_id == org_id)
        .first()
    )
    if not has_activities:
        return {
            "score": None,
            "message": "No activity data recorded yet. Record emissions data to generate a sustainability score.",
            "components": None,
        }

    org = db.query(Organization).filter(Organization.id == org_id).first()

    # 1. YoY Trend
    trend_data = calculate_trend(db, org_id)
    comp_trend = score_yoy_trend(trend_data.get("pct_change"))

    # 2. Target Progress
    targets_status = calculate_targets_status(db, org_id)
    comp_target = score_target_progress(targets_status)

    # 3. Data Completeness
    months_with_data = sum(1 for m in trend_data.get("months", []) if m.get("t_co2e", 0) > 0)

    total_calcs = (
        db.query(func.count(EmissionResult.id))
        .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
        .where(
            ActivityRecord.org_id == org_id,
            EmissionResult.is_current.is_(True),
            or_(
                EmissionResult.method == Scope2Method.location_based,
                EmissionResult.method.is_(None),
            ),
        )
        .scalar()
        or 0
    )

    failed_calcs = (
        db.query(func.count(EmissionResult.id))
        .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
        .where(
            ActivityRecord.org_id == org_id,
            EmissionResult.is_current.is_(True),
            EmissionResult.kg_co2e.is_(None),
        )
        .scalar()
        or 0
    )

    comp_completeness = score_data_completeness(months_with_data, total_calcs, failed_calcs)

    # 4. Carbon Intensity
    current_12m_t = trend_data.get("current_total", 0.0)
    employee_count = org.employee_count if org else None
    comp_intensity = score_carbon_intensity(current_12m_t, employee_count)

    # Total Score
    total_points = (
        comp_trend["points"]
        + comp_target["points"]
        + comp_completeness["points"]
        + comp_intensity["points"]
    )
    final_score = int(round(max(0.0, min(100.0, total_points))))

    components = {
        "yoy_trend": comp_trend,
        "target_progress": comp_target,
        "data_completeness": comp_completeness,
        "carbon_intensity": comp_intensity,
    }

    # Save to sustainability_scores
    score_entry = SustainabilityScore(
        org_id=org_id,
        level=ScoreLevel.organization,
        entity_id=org_id,
        period=date.today(),
        score=final_score,
        components=components,
    )
    db.add(score_entry)
    db.commit()
    db.refresh(score_entry)

    return {
        "score": final_score,
        "components": components,
        "period": date.today().isoformat(),
        "recorded_at": score_entry.period.isoformat() if score_entry.period else None,
    }


@router.get("/score")
def get_score(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return calculate_sustainability_score(db, current_user.org_id)
