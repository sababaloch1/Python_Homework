
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from api.app.core.database import get_db
from api.app.core.models import User, ActivityRecord, Facility, Department
from api.app.core.deps import get_current_user
from api.app.core.enums import ActivityCategory, AuditAction, BatchStatus
from api.app.data_identity.schemas import ActivityCreate, ActivityResponse
from api.app.data_identity.services import audit_service, csv_import
from api.app.engine import service as engine_service

router = APIRouter(prefix="/activities", tags=["Activity Records"])


def trigger_engine_calculation(db: Session, activity_id: UUID):
    # S1 -> S2 handoff (FR-2.05): calculation problems must not break saving.
    engine_service.safe_calculate_activity(db, activity_id)


def validate_activity_references(
    db: Session,
    org_id: UUID,
    activity_data: dict,
):
    """
    Ensure any selected facility and department belong to the user's
    organisation before an activity is created or updated.
    """

    facility_id = activity_data.get("facility_id")
    if facility_id is not None:
        facility = (
            db.query(Facility)
            .filter(
                Facility.id == facility_id,
                Facility.org_id == org_id,
            )
            .first()
        )

        if facility is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Facility not found in your organisation",
            )

    department_id = activity_data.get("department_id")
    if department_id is not None:
        department = (
            db.query(Department)
            .filter(
                Department.id == department_id,
                Department.org_id == org_id,
            )
            .first()
        )

        if department is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found in your organisation",
            )


# FR-1.06: Downloadable CSV Template
@router.get("/template")
def download_csv_template():
    csv_content = (
        "category,amount,unit,period_start,period_end,note\n"
        "electricity,1500,kWh,2026-01-01,2026-01-31,January bill\n"
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=activity_template.csv"
        },
    )


@router.post("/", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
def create_activity(
    activity_in: ActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    activity_data = activity_in.model_dump()

    # NFR-1.02: Validate organisation ownership before inserting.
    validate_activity_references(
        db=db,
        org_id=current_user.org_id,
        activity_data=activity_data,
    )

    new_activity = ActivityRecord(
        org_id=current_user.org_id,
        created_by=current_user.id,
        **activity_data,
    )

    db.add(new_activity)
    db.commit()
    db.refresh(new_activity)

    audit_service.log_action(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        entity="ActivityRecord",
        entity_id=new_activity.id,
        action=AuditAction.create,
    )

    trigger_engine_calculation(db, new_activity.id)
    return new_activity


@router.get("/", response_model=List[ActivityResponse])
def get_activities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    category: Optional[ActivityCategory] = None,
):
    query = db.query(ActivityRecord).filter(
        ActivityRecord.org_id == current_user.org_id
    )

    if category:
        query = query.filter(ActivityRecord.category == category)

    return query.all()


# FR-1.05: Edit Activity
@router.put("/{activity_id}", response_model=ActivityResponse)
def update_activity(
    activity_id: UUID,
    activity_in: ActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # NFR-1.02: Tenant isolation for the activity itself.
    activity = (
        db.query(ActivityRecord)
        .filter(
            ActivityRecord.id == activity_id,
            ActivityRecord.org_id == current_user.org_id,
        )
        .first()
    )

    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    activity_data = activity_in.model_dump()

    # Prevent changing an activity to another organisation's facility
    # or department.
    validate_activity_references(
        db=db,
        org_id=current_user.org_id,
        activity_data=activity_data,
    )

    for key, value in activity_data.items():
        setattr(activity, key, value)

    db.commit()
    db.refresh(activity)

    # FR-1.10: Audit Log for Update
    audit_service.log_action(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        entity="ActivityRecord",
        entity_id=activity.id,
        action=AuditAction.update,
    )

    # Recalculate emissions.
    trigger_engine_calculation(db, activity.id)
    return activity


# FR-1.05: Delete Activity
@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(
    activity_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # NFR-1.02: Tenant isolation.
    activity = (
        db.query(ActivityRecord)
        .filter(
            ActivityRecord.id == activity_id,
            ActivityRecord.org_id == current_user.org_id,
        )
        .first()
    )

    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    # S2: Keep old results as history but stop S3 from counting them.
    engine_service.retire_activity_results(db, activity_id)
    db.delete(activity)
    db.commit()

    # FR-1.10: Audit Log for Delete
    audit_service.log_action(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        entity="ActivityRecord",
        entity_id=activity_id,
        action=AuditAction.delete,
    )

    return None


@router.post("/import", status_code=status.HTTP_201_CREATED)
def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    batch = csv_import.process_csv(file, db, current_user)

    if batch.status == BatchStatus.failed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "CSV import failed",
                "errors": batch.errors,
            },
        )

    engine_service.safe_calculate_batch(db, batch.id)

    return {
        "message": "CSV imported successfully",
        "rows_saved": batch.row_count,
    }
