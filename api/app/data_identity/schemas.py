from pydantic import BaseModel, EmailStr, Field, ConfigDict
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from api.app.core.enums import UserRole, ActivityCategory, Unit

# ==========================================
# AUTHENTICATION & USER SCHEMAS
# ==========================================

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
    full_name: str
    org_name: str = Field(..., description="Name of the organization they are creating")

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole
    org_id: UUID
    is_active: bool
    
    # This tells Pydantic to read data even if it's a SQLAlchemy model object
    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ACTIVITY RECORD SCHEMAS
# ==========================================

class ActivityCreate(BaseModel):
    category: ActivityCategory
    amount: Decimal = Field(..., ge=0, description="Amount must be greater than or equal to 0")
    unit: Unit
    period_start: date
    period_end: date
    facility_id: Optional[UUID] = None
    department_id: Optional[UUID] = None
    note: Optional[str] = None
    evidence_ref: Optional[str] = None

class ActivityResponse(ActivityCreate):
    id: UUID
    org_id: UUID
    created_by: Optional[UUID] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)