"""api/app/analytics/me.py - User profile and organization details for S3 Analytics."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from api.app.core.deps import get_current_user
from api.app.core.models import User

router = APIRouter(tags=["S3 Analytics"])


class UserMeResponse(BaseModel):
    full_name: Optional[str] = None
    email: str
    role: str
    org_name: str
    employee_count: Optional[int] = None


@router.get("/me", response_model=UserMeResponse)
def get_analytics_me(current_user: User = Depends(get_current_user)):
    org = current_user.organization
    return UserMeResponse(
        full_name=current_user.full_name,
        email=current_user.email,
        role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        org_name=org.name if org else "Unknown",
        employee_count=org.employee_count if org else None,
    )
