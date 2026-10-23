from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.app.core.database import get_db
from api.app.core.deps import get_current_user, require_admin
from api.app.core.enums import ActivityCategory, AuditAction
from api.app.core.models import ActivityRecord, EmissionFactor, RegionTariff, User
from api.app.data_identity.services import audit_service
from api.app.engine import importer, repository, service
from api.app.engine.schemas import (
    FactorIn, FactorOut, ResultOut, SimulateChangeIn, SimulateChangeOut, SimulateIn,
    SimulateOut, TariffIn, TariffOut,
)

router = APIRouter(prefix="/engine", tags=["Emission Engine"])


def _dump(model) -> dict:
    return model.model_dump(mode="json")


# ------------------------------------------------------------------ factors (FR-2.01, FR-2.02)
@router.get("/factors", response_model=List[FactorOut])
def list_factors(
    activity_type: Optional[ActivityCategory] = None,
    region: Optional[str] = None,
    year: Optional[int] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(EmissionFactor)
    if activity_type:
        q = q.where(EmissionFactor.activity_type == activity_type)
    if region:
        q = q.where(EmissionFactor.region == region.strip().upper())
    if year:
        q = q.where(EmissionFactor.year == year)
    if not include_inactive:
        q = q.where(EmissionFactor.is_active.is_(True))
    q = q.order_by(EmissionFactor.activity_type, EmissionFactor.region, EmissionFactor.year, EmissionFactor.version.desc())
    return db.execute(q).scalars().all()


@router.post("/factors", response_model=FactorOut, status_code=status.HTTP_201_CREATED)
def save_factor(body: FactorIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Creates a factor, or a new version if one exists for the same type/region/year."""
    row, st = repository.upsert_factor(db, body.model_dump())
    db.commit()
    db.refresh(row)
    if st != "unchanged":
        audit_service.log_action(db, admin.org_id, admin.id, "EmissionFactor", row.id, AuditAction.create,
                                 {"status": st, "version": row.version, "kg_co2e_per_unit": str(row.kg_co2e_per_unit)})
        service.recalculate_category(db, body.activity_type.value)
    return row


@router.delete("/factors/{factor_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_factor(factor_id: UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Soft delete only (NFR-2.08)."""
    row = repository.deactivate_factor(db, factor_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Factor not found")
    db.commit()
    audit_service.log_action(db, admin.org_id, admin.id, "EmissionFactor", row.id, AuditAction.delete, {"soft": True})
    service.recalculate_category(db, row.activity_type.value)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/factors/import")
def import_factors(file: UploadFile = File(...), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    result = importer.import_factors_text(db, file.file.read().decode("utf-8-sig"))
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail={"message": "Factor import failed", "errors": result["errors"]})
    return result


# ------------------------------------------------------------------ tariffs (FR-2.02)
@router.get("/tariffs", response_model=List[TariffOut])
def list_tariffs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.execute(select(RegionTariff).order_by(RegionTariff.activity_type, RegionTariff.region, RegionTariff.year)).scalars().all()


@router.post("/tariffs", response_model=TariffOut, status_code=status.HTTP_201_CREATED)
def save_tariff(body: TariffIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    row, st = repository.upsert_tariff(db, body.model_dump())
    db.commit()
    db.refresh(row)
    if st != "unchanged":
        service.recalculate_category(db, body.activity_type.value)
    return row


@router.post("/tariffs/import")
def import_tariffs(file: UploadFile = File(...), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    result = importer.import_tariffs_text(db, file.file.read().decode("utf-8-sig"))
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail={"message": "Tariff import failed", "errors": result["errors"]})
    return result


# ------------------------------------------------------------------ results (FR-2.05, FR-2.09)
def _own_activity(db: Session, activity_id: UUID, user: User) -> ActivityRecord:
    activity = db.execute(select(ActivityRecord).where(
        ActivityRecord.id == activity_id, ActivityRecord.org_id == user.org_id)).scalars().first()
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")     # NFR tenant isolation
    return activity


@router.post("/calculate/{activity_id}", response_model=ResultOut)
def calculate(activity_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _own_activity(db, activity_id, user)
    return service.calculate_activity(db, activity_id)


@router.get("/results/{activity_id}", response_model=List[ResultOut])
def results(activity_id: UUID, include_history: bool = False, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    _own_activity(db, activity_id, user)
    return service.get_results(db, activity_id, include_history)


# ------------------------------------------------------------------ simulate (FR-2.10)
@router.post("/simulate", response_model=SimulateOut)
def simulate(body: SimulateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.simulate(db, [i.model_dump() for i in body.items])


@router.post("/simulate/compare", response_model=SimulateChangeOut)
def simulate_compare(body: SimulateChangeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.simulate_change(db, [i.model_dump() for i in body.before], [i.model_dump() for i in body.after])
