import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Numeric, Boolean, DateTime, Date, 
    ForeignKey, Enum, Text, JSON, Uuid
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .database import Base
from .enums import (
    UserRole, ActivityCategory, Unit, Scope, Scope2Method, BatchStatus, 
    AuditAction, Level, RecStatus, RecSource, MsgRole, AssetKind, 
    ReadingSource, ScoreLevel, ContentStatus
)

# Use this trick so it works on PostgreSQL (JSONB) and SQLite (JSON) for tests
JSONType = JSON().with_variant(JSONB, "postgresql")

# ==========================================
# S1 TABLES (Owned by Saba)
# ==========================================

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    country_code = Column(String(2))
    industry = Column(String(80))
    employee_count = Column(Integer)
    reporting_year_start_month = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    departments = relationship("Department", back_populates="organization")
    facilities = relationship("Facility", back_populates="organization")
    users = relationship("User", back_populates="organization")

class Department(Base):
    __tablename__ = "departments"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(80), nullable=False)

    organization = relationship("Organization", back_populates="departments")

class Facility(Base):
    __tablename__ = "facilities"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(120), nullable=False)
    city = Column(String(80))
    country_code = Column(String(2))
    floor_area_m2 = Column(Numeric(12, 2))

    organization = relationship("Organization", back_populates="facilities")
    assets = relationship("Asset", back_populates="facility")

class User(Base):
    __tablename__ = "users"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False)
    email = Column(String(254), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(120))
    role = Column(Enum(UserRole), default=UserRole.contributor)
    department_id = Column(Uuid, ForeignKey("departments.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    organization = relationship("Organization", back_populates="users")

class ActivityRecord(Base):
    __tablename__ = "activity_records"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False)
    facility_id = Column(Uuid, ForeignKey("facilities.id"))
    department_id = Column(Uuid, ForeignKey("departments.id"))
    category = Column(Enum(ActivityCategory), nullable=False)
    amount = Column(Numeric(14, 4), nullable=False)
    unit = Column(Enum(Unit), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    evidence_ref = Column(String(255))
    note = Column(Text)
    import_batch_id = Column(Uuid, ForeignKey("import_batches.id"), nullable=True)
    created_by = Column(Uuid, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    emission_results = relationship("EmissionResult", back_populates="activity")

class ImportBatch(Base):
    __tablename__ = "import_batches"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False)
    file_name = Column(String(255))
    uploaded_by = Column(Uuid, ForeignKey("users.id"))
    row_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    status = Column(Enum(BatchStatus), default=BatchStatus.pending)
    errors = Column(JSONType)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False)
    user_id = Column(Uuid, ForeignKey("users.id"))
    entity = Column(String(40))
    entity_id = Column(Uuid)
    action = Column(Enum(AuditAction))
    changes = Column(JSONType)
    at = Column(DateTime(timezone=True), default=datetime.utcnow)

class Asset(Base):
    __tablename__ = "assets"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False)
    facility_id = Column(Uuid, ForeignKey("facilities.id"))
    kind = Column(Enum(AssetKind), nullable=False)
    name = Column(String(120), nullable=False)
    code = Column(String(12), unique=True)
    is_active = Column(Boolean, default=True)

    facility = relationship("Facility", back_populates="assets")
    readings = relationship("MeterReading", back_populates="asset")

class MeterReading(Base):
    __tablename__ = "meter_readings"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False)
    asset_id = Column(Uuid, ForeignKey("assets.id"), nullable=False)
    category = Column(Enum(ActivityCategory))
    value = Column(Numeric(14, 4), nullable=False)
    unit = Column(Enum(Unit), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False)
    source = Column(Enum(ReadingSource))

    asset = relationship("Asset", back_populates="readings")

# ==========================================
# S2 TABLES (Owned by Tuba)
# ==========================================

class EmissionFactor(Base):
    __tablename__ = "emission_factors"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    activity_type = Column(Enum(ActivityCategory))
    region = Column(String(8))
    year = Column(Integer)
    unit = Column(Enum(Unit))
    kg_co2e_per_unit = Column(Numeric(14, 6), nullable=False)
    scope = Column(Enum(Scope))
    ghg_category = Column(String(60))
    source = Column(String(255))
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)

class EmissionResult(Base):
    __tablename__ = "emission_results"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    activity_id = Column(Uuid, ForeignKey("activity_records.id"), nullable=True)
    reading_id = Column(Uuid, ForeignKey("meter_readings.id"), nullable=True)
    factor_id = Column(Uuid, ForeignKey("emission_factors.id"))
    scope = Column(Enum(Scope))
    method = Column(Enum(Scope2Method))
    kg_co2e = Column(Numeric(16, 4))
    cost_eur = Column(Numeric(12, 2))
    trace = Column(JSONType)
    is_current = Column(Boolean, default=True)
    calculated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    activity = relationship("ActivityRecord", back_populates="emission_results")

class RegionTariff(Base):
    __tablename__ = "region_tariffs"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    region = Column(String(8))
    activity_type = Column(Enum(ActivityCategory))
    unit = Column(Enum(Unit))
    eur_per_unit = Column(Numeric(10, 4))
    year = Column(Integer)
    source = Column(String(255))

# ==========================================
# S3 TABLES (Owned by Sameer)
# ==========================================

class Target(Base):
    __tablename__ = "targets"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False)
    scope = Column(Enum(Scope), nullable=True)
    baseline_year = Column(Integer)
    target_year = Column(Integer)
    reduction_pct = Column(Numeric(5, 2))
    created_by = Column(Uuid, ForeignKey("users.id"))

class SustainabilityScore(Base):
    __tablename__ = "sustainability_scores"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False)
    level = Column(Enum(ScoreLevel))
    entity_id = Column(Uuid)
    period = Column(Date)
    score = Column(Integer)
    components = Column(JSONType)

# ==========================================
# S4 TABLES (Owned by Mustafa)
# ==========================================

class Recommendation(Base):
    __tablename__ = "recommendations"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id = Column(Uuid, ForeignKey("organizations.id"), nullable=False)
    department_id = Column(Uuid, ForeignKey("departments.id"), nullable=True)
    title = Column(String(160))
    description = Column(Text)
    est_saving_t_co2e = Column(Numeric(10, 2))
    cost_level = Column(Enum(Level))
    effort = Column(Enum(Level))
    scope = Column(Enum(Scope))
    status = Column(Enum(RecStatus), default=RecStatus.proposed)
    source = Column(Enum(RecSource))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    title = Column(String(120))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    messages = relationship("ChatMessage", back_populates="session")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id = Column(Uuid, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(Enum(MsgRole))
    content = Column(Text)
    tokens_in = Column(Integer)
    tokens_out = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")

class LearningContent(Base):
    __tablename__ = "learning_contents"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    topic = Column(String(160))
    audience = Column(Enum(UserRole))
    body = Column(Text)
    status = Column(Enum(ContentStatus), default=ContentStatus.draft)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)