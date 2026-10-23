from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.app.core.enums import ActivityCategory, Scope, Scope2Method, Unit


class _RegionMixin(BaseModel):
    region: str = Field(..., min_length=2, max_length=8, description="ISO country code or GLOBAL")

    @field_validator("region")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class FactorIn(_RegionMixin):
    activity_type: ActivityCategory
    year: int = Field(..., ge=1990, le=2100)
    unit: Unit
    kg_co2e_per_unit: Decimal = Field(..., ge=0)
    scope: Scope
    ghg_category: Optional[str] = Field(None, max_length=60)
    source: str = Field(..., min_length=1, max_length=255)   # NFR-2.05


class FactorOut(FactorIn):
    id: UUID
    version: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class TariffIn(_RegionMixin):
    activity_type: ActivityCategory
    year: int = Field(..., ge=1990, le=2100)
    unit: Unit
    eur_per_unit: Decimal = Field(..., ge=0)
    source: str = Field(..., min_length=1, max_length=255)


class TariffOut(TariffIn):
    id: UUID
    model_config = ConfigDict(from_attributes=True)


class ResultOut(BaseModel):
    id: UUID
    activity_id: Optional[UUID] = None
    reading_id: Optional[UUID] = None
    factor_id: Optional[UUID] = None
    scope: Optional[Scope] = None
    method: Optional[Scope2Method] = None
    kg_co2e: Optional[Decimal] = None
    cost_eur: Optional[Decimal] = None
    trace: Optional[dict] = None
    is_current: bool
    calculated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class SimItem(_RegionMixin):
    category: ActivityCategory
    amount: Decimal = Field(..., ge=0)
    unit: Unit
    year: int = Field(..., ge=1990, le=2100)
    label: Optional[str] = None


class SimItemOut(BaseModel):
    label: Optional[str] = None
    category: str
    amount: Decimal
    unit: str
    region: str
    year: int
    kg_co2e: Optional[Decimal] = None
    cost_eur: Optional[Decimal] = None
    scope: Optional[str] = None
    error: Optional[str] = None


class SimulateIn(BaseModel):
    items: List[SimItem]


class SimulateOut(BaseModel):
    items: List[SimItemOut]
    total_kg_co2e: Decimal
    total_cost_eur: Decimal
    errors: int


class SimulateChangeIn(BaseModel):
    before: List[SimItem]
    after: List[SimItem]


class SimulateChangeOut(BaseModel):
    before: SimulateOut
    after: SimulateOut
    saving_kg_co2e: Decimal
    saving_pct: Optional[Decimal] = None
    saving_cost_eur: Decimal
