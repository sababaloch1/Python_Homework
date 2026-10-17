from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from api.app.core.database import get_db
from api.app.core.models import User, Organization, Department, Facility
from api.app.core.deps import get_current_user
from api.app.data_identity.schemas import (
    OrganizationResponse, DepartmentCreate, DepartmentResponse, 
    FacilityCreate, FacilityResponse
)

router = APIRouter(tags=["Core Data (Org, Dept, Facilities)"])

@router.get("/organization", response_model=OrganizationResponse)
def get_my_organization(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org

@router.post("/departments", response_model=DepartmentResponse, status_code=201)
def create_department(
    dept_in: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    new_dept = Department(org_id=current_user.org_id, name=dept_in.name)
    db.add(new_dept)
    db.commit()
    db.refresh(new_dept)
    return new_dept

@router.get("/departments", response_model=List[DepartmentResponse])
def get_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Department).filter(Department.org_id == current_user.org_id).all()

@router.post("/facilities", response_model=FacilityResponse, status_code=201)
def create_facility(
    fac_in: FacilityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    new_fac = Facility(
        org_id=current_user.org_id,
        name=fac_in.name,
        city=fac_in.city,
        country_code=fac_in.country_code,
        floor_area_m2=fac_in.floor_area_m2
    )
    db.add(new_fac)
    db.commit()
    db.refresh(new_fac)
    return new_fac

@router.get("/facilities", response_model=List[FacilityResponse])
def get_facilities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Facility).filter(Facility.org_id == current_user.org_id).all()