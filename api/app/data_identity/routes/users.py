from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.app.core.database import get_db
from api.app.core.models import User, ActivityRecord
from api.app.core.deps import get_current_user, require_admin
from api.app.core.security import get_password_hash
from api.app.data_identity.schemas import UserResponse, UserInvite

router = APIRouter(prefix="/users", tags=["Users & GDPR"])

# FR-1.04: Admin invites a user to their organization
@router.post("/invite", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def invite_user(
    user_in: UserInvite,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)  # NFR-1.02: Only admins can do this
):
    # Check if user exists globally
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = User(
        org_id=current_user.org_id,  # Assign to the admin's org
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

# NFR-1.10: User exports their own data
@router.get("/me/export")
def export_my_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Get all activities created by this user
    activities = db.query(ActivityRecord).filter(ActivityRecord.created_by == current_user.id).all()
    
    return {
        "user_profile": {
            "id": str(current_user.id),
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role
        },
        "activities_created": [
            {
                "id": str(a.id),
                "category": a.category,
                "amount": str(a.amount),
                "unit": a.unit
            } for a in activities
        ]
    }

# NFR-1.10: User deletes their own account (Soft delete)
@router.delete("/me", status_code=status.HTTP_200_OK)
def delete_my_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # We don't actually delete the row to keep the audit trail safe, we just deactivate it
    current_user.is_active = False
    db.commit()
    return {"message": "Account successfully deleted (deactivated)"}