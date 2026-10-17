from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import date

from api.app.core.database import get_db
from api.app.core.models import User, ActivityRecord
from api.app.core.deps import get_current_user
from api.app.core.enums import ActivityCategory, AuditAction, BatchStatus
from api.app.data_identity.schemas import ActivityCreate, ActivityResponse
from api.app.data_identity.services import audit_service, csv_import

router = APIRouter(prefix="/activities", tags=["Activity Records"])

def trigger_engine_calculation(activity_id: UUID):
    print(f"⭐⭐ [S1 -> S2 HANDOFF] Triggering engine.calculate for activity_id: {activity_id} ⭐⭐")

# FR-1.06: Downloadable CSV Template
@router.get("/template")
def download_csv_template():
    csv_content = "category,amount,unit,period_start,period_end,note\nelectricity,1500,kWh,2026-01-01,2026-01-31,January bill\n"
    return Response(content=csv_content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=activity_template.csv"})

@router.post("/", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
def create_activity(
    activity_in: ActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    new_activity = ActivityRecord(
        org_id=current_user.org_id,
        created_by=current_user.id,
        **activity_in.model_dump()
    )
    db.add(new_activity)
    db.commit()
    db.refresh(new_activity)

    audit_service.log_action(db=db, org_id=current_user.org_id, user_id=current_user.id, entity="ActivityRecord", entity_id=new_activity.id, action=AuditAction.create)
    trigger_engine_calculation(new_activity.id)
    return new_activity

@router.get("/", response_model=List[ActivityResponse])
def get_activities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    category: Optional[ActivityCategory] = None,
):
    query = db.query(ActivityRecord).filter(ActivityRecord.org_id == current_user.org_id)
    if category:
        query = query.filter(ActivityRecord.category == category)
    return query.all()

# FR-1.05: Edit Activity
@router.put("/{activity_id}", response_model=ActivityResponse)
def update_activity(
    activity_id: UUID,
    activity_in: ActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # NFR-1.02: Tenant Isolation
    activity = db.query(ActivityRecord).filter(ActivityRecord.id == activity_id, ActivityRecord.org_id == current_user.org_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Update fields
    for key, value in activity_in.model_dump().items():
        setattr(activity, key, value)
    
    db.commit()
    db.refresh(activity)

    # FR-1.10: Audit Log for Update
    audit_service.log_action(db=db, org_id=current_user.org_id, user_id=current_user.id, entity="ActivityRecord", entity_id=activity.id, action=AuditAction.update)
    
    # Recalculate emissions!
    trigger_engine_calculation(activity.id)
    return activity

# FR-1.05: Delete Activity
@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(
    activity_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # NFR-1.02: Tenant Isolation
    activity = db.query(ActivityRecord).filter(ActivityRecord.id == activity_id, ActivityRecord.org_id == current_user.org_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    db.delete(activity)
    db.commit()

    # FR-1.10: Audit Log for Delete
    audit_service.log_action(db=db, org_id=current_user.org_id, user_id=current_user.id, entity="ActivityRecord", entity_id=activity_id, action=AuditAction.delete)
    
    return None

@router.post("/import", status_code=status.HTTP_201_CREATED)
def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    batch = csv_import.process_csv(file, db, current_user)
    if batch.status == BatchStatus.failed:
        raise HTTPException(status_code=400, detail={"message": "CSV import failed", "errors": batch.errors})
    return {"message": "CSV imported successfully", "rows_saved": batch.row_count}