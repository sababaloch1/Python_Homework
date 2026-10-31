"""api/app/analytics/targets.py - FR-3.06 & FR-3.07: Target setting and trajectory tracking.

Endpoints:
1. POST /analytics/targets (admin or manager only)
   Body: {"scope": "scope_1" (optional), "baseline_year": 2024, "target_year": 2030, "reduction_pct": 30.0}
2. GET /analytics/targets
   Returns list of created targets for current organization
3. GET /analytics/targets/status?as_of_year=
   Returns per target: baseline_t, target_t, expected_now, actual_t, status (on_track/off_track), saved_t
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import extract, func, or_, select
from sqlalchemy.orm import Session

from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.enums import Scope, Scope2Method, UserRole
from api.app.core.models import ActivityRecord, EmissionResult, Target, User

router = APIRouter(tags=["S3 Analytics"])


class TargetCreate(BaseModel):
    scope: Optional[Scope] = None
    baseline_year: int = Field(..., ge=1990, le=2100, description="Baseline year (e.g. 2024)")
    target_year: int = Field(..., ge=1990, le=2100, description="Target year (e.g. 2030)")
    reduction_pct: Decimal = Field(..., gt=0, le=100, description="Reduction percentage (0 < pct <= 100)")

    @model_validator(mode="after")
    def validate_target_year_greater(self):
        if self.target_year <= self.baseline_year:
            raise ValueError("target_year must be greater than baseline_year")
        return self


def evaluate_target_status(
    baseline_year: int,
    target_year: int,
    reduction_pct: float,
    baseline_t: float,
    actual_t: float,
    current_year: Optional[int] = None,
) -> dict:
    """Pure mathematical function evaluating trajectory and status for one target.

    Formula:
    - baseline_t: total emissions in baseline_year
    - target_t = baseline_t * (1 - reduction_pct / 100)
    - expected_now: point at current_year on straight line from (baseline_year, baseline_t) to (target_year, target_t)
    - actual_t: emissions in current_year to date
    - status: "on_track" if actual_t <= expected_now else "off_track"
    - saved_t = baseline_t - actual_t
    """
    baseline_t = round(float(baseline_t), 4)
    actual_t = round(float(actual_t), 4)
    target_t = round(float(baseline_t * (1.0 - reduction_pct / 100.0)), 4)

    eval_year = current_year if current_year is not None else date.today().year

    if target_year <= baseline_year:
        expected_now = target_t
    else:
        # Straight line: y = y0 + m * (x - x0)
        slope = (target_t - baseline_t) / (target_year - baseline_year)
        expected_now = round(float(baseline_t + slope * (eval_year - baseline_year)), 4)

    status_val = "on_track" if actual_t <= expected_now else "off_track"
    saved_t = round(float(baseline_t - actual_t), 4)

    return {
        "baseline_t": baseline_t,
        "target_t": target_t,
        "expected_now": expected_now,
        "actual_t": actual_t,
        "status": status_val,
        "saved_t": saved_t,
    }


def calculate_targets_status(
    db: Session,
    org_id: UUID,
    as_of_year: Optional[int] = None,
) -> List[dict]:
    """Evaluates all targets for an organization using SQL aggregations."""
    eval_year = as_of_year if as_of_year is not None else date.today().year

    targets = (
        db.query(Target)
        .filter(Target.org_id == org_id)
        .order_by(Target.baseline_year, Target.target_year)
        .all()
    )
    if not targets:
        return []

    results = []
    for t in targets:
        base_where = [
            ActivityRecord.org_id == org_id,
            EmissionResult.is_current.is_(True),
            EmissionResult.kg_co2e.is_not(None),
            or_(
                EmissionResult.method == Scope2Method.location_based,
                EmissionResult.method.is_(None),
            ),
        ]
        if t.scope is not None:
            base_where.append(EmissionResult.scope == t.scope)

        # Baseline year emissions in SQL
        baseline_stmt = (
            select(func.sum(EmissionResult.kg_co2e))
            .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
            .where(
                *base_where,
                extract("year", ActivityRecord.period_start) == t.baseline_year,
            )
        )
        base_kg = db.execute(baseline_stmt).scalar()
        baseline_t = round(float(base_kg / Decimal("1000")), 4) if base_kg else 0.0

        # Current year to date emissions in SQL
        actual_stmt = (
            select(func.sum(EmissionResult.kg_co2e))
            .join(ActivityRecord, EmissionResult.activity_id == ActivityRecord.id)
            .where(
                *base_where,
                extract("year", ActivityRecord.period_start) == eval_year,
            )
        )
        act_kg = db.execute(actual_stmt).scalar()
        actual_t = round(float(act_kg / Decimal("1000")), 4) if act_kg else 0.0

        eval_data = evaluate_target_status(
            baseline_year=t.baseline_year,
            target_year=t.target_year,
            reduction_pct=float(t.reduction_pct),
            baseline_t=baseline_t,
            actual_t=actual_t,
            current_year=eval_year,
        )

        results.append({
            "id": str(t.id),
            "scope": t.scope.value if t.scope else None,
            "baseline_year": t.baseline_year,
            "target_year": t.target_year,
            "reduction_pct": float(t.reduction_pct),
            **eval_data,
        })

    return results


@router.post("/targets", status_code=status.HTTP_201_CREATED)
def create_target(
    payload: TargetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # FR-3.06: Admin or manager only
    if current_user.role not in (UserRole.admin, UserRole.manager):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not permitted. Admin or manager role required.",
        )

    target = Target(
        org_id=current_user.org_id,
        scope=payload.scope,
        baseline_year=payload.baseline_year,
        target_year=payload.target_year,
        reduction_pct=payload.reduction_pct,
        created_by=current_user.id,
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    return {
        "id": str(target.id),
        "org_id": str(target.org_id),
        "scope": target.scope.value if target.scope else None,
        "baseline_year": target.baseline_year,
        "target_year": target.target_year,
        "reduction_pct": float(target.reduction_pct),
        "created_by": str(target.created_by) if target.created_by else None,
    }


@router.get("/targets")
def get_targets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    targets = (
        db.query(Target)
        .filter(Target.org_id == current_user.org_id)
        .order_by(Target.baseline_year, Target.target_year)
        .all()
    )
    return [
        {
            "id": str(t.id),
            "org_id": str(t.org_id),
            "scope": t.scope.value if t.scope else None,
            "baseline_year": t.baseline_year,
            "target_year": t.target_year,
            "reduction_pct": float(t.reduction_pct),
            "created_by": str(t.created_by) if t.created_by else None,
        }
        for t in targets
    ]


@router.get("/targets/status")
def get_targets_status(
    as_of_year: Optional[int] = Query(None, description="Year to evaluate actual progress against"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return calculate_targets_status(db, current_user.org_id, as_of_year=as_of_year)
