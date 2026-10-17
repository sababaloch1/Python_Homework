from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
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

# ⭐ THE HANDOFF TO S2
def trigger_engine_calculation(activity_id: UUID):
    print(f"⭐⭐ [S1 -> S2 HANDOFF] Triggering engine.calculate for activity_id: {activity_id} ⭐⭐")

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

    audit_service.log_action(
        db=db, org_id=current_user.org_id, user_id=current_user.id,
        entity="ActivityRecord", entity_id=new_activity.id, action=AuditAction.create
    )

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

# ⭐ NEW ROUTE: CSV Upload (FR-1.06 & FR-1.07)
@router.post("/import", status_code=status.HTTP_201_CREATED)
def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    batch = csv_import.process_csv(file, db, current_user)
    
    if batch.status == BatchStatus.failed:
        raise HTTPException(
            status_code=400, 
            detail={"message": "CSV import failed", "errors": batch.errors}
        )
    
    return {"message": "CSV imported successfully", "rows_saved": batch.row_count}