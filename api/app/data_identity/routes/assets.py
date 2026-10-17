from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid

from api.app.core.database import get_db
from api.app.core.models import User, Asset, MeterReading
from api.app.core.deps import get_current_user
from api.app.data_identity.schemas import (
    AssetCreate, AssetResponse, MeterReadingCreate, MeterReadingResponse
)

router = APIRouter(tags=["Assets & Meter Readings"])

@router.post("/assets", response_model=AssetResponse, status_code=201)
def create_asset(
    asset_in: AssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Generate a unique QR code payload
    qr_code = f"AST-{str(uuid.uuid4())[:6].upper()}"
    
    new_asset = Asset(
        org_id=current_user.org_id,
        name=asset_in.name,
        kind=asset_in.kind,
        facility_id=asset_in.facility_id,
        code=qr_code
    )
    db.add(new_asset)
    db.commit()
    db.refresh(new_asset)
    return new_asset

@router.get("/assets", response_model=List[AssetResponse])
def get_assets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Asset).filter(Asset.org_id == current_user.org_id).all()

@router.post("/readings", response_model=MeterReadingResponse, status_code=201)
def create_reading(
    reading_in: MeterReadingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify the asset belongs to the user's organization (NFR-1.02)
    asset = db.query(Asset).filter(Asset.id == reading_in.asset_id, Asset.org_id == current_user.org_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found in your organization")
        
    new_reading = MeterReading(
           org_id=current_user.org_id,
           recorded_at=datetime.now(timezone.utc),  # <--- Add this line
           **reading_in.model_dump()
       )
    
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)

   
    
    # ⭐ THE HANDOFF TO S2 FOR REAL-TIME DATA
    print(f"⭐⭐ [S1 -> S2 HANDOFF] Triggering engine.calculate for reading_id: {new_reading.id} ⭐⭐")
    
    return new_reading