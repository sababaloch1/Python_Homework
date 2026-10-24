from enum import Enum

class UserRole(str, Enum):
    admin = "admin"
    manager = "manager"
    contributor = "contributor"

class ActivityCategory(str, Enum):
    electricity = "electricity"
    natural_gas = "natural_gas"
    diesel = "diesel"
    petrol = "petrol"
    fleet_km = "fleet_km"
    refrigerant = "refrigerant"
    flight_short_haul = "flight_short_haul"
    flight_long_haul = "flight_long_haul"
    rail = "rail"
    hotel_night = "hotel_night"
    employee_commute = "employee_commute"
    waste_landfill = "waste_landfill"
    waste_recycled = "waste_recycled"
    water = "water"

class Unit(str, Enum):
    kWh = "kWh"
    MWh = "MWh"
    m3 = "m3"
    litre = "litre"
    km = "km"
    miles = "miles"
    passenger_km = "passenger_km"
    night = "night"
    kg = "kg"
    tonne = "tonne"

class Scope(str, Enum):
    scope_1 = "scope_1"
    scope_2 = "scope_2"
    scope_3 = "scope_3"

class Scope2Method(str, Enum):
    location_based = "location_based"
    market_based = "market_based"

class BatchStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"

class AuditAction(str, Enum):
    create = "create"
    update = "update"
    delete = "delete"

class Level(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"

class RecStatus(str, Enum):
    proposed = "proposed"
    accepted = "accepted"
    dismissed = "dismissed"
    completed = "completed"

class RecSource(str, Enum):
    ai = "ai"
    rules = "rules"

class MsgRole(str, Enum):
    user = "user"
    assistant = "assistant"

class AssetKind(str, Enum):
    facility = "facility"
    vehicle = "vehicle"
    meter = "meter"

class ReadingSource(str, Enum):
    device = "device"
    simulator = "simulator"
    manual = "manual"

class ScoreLevel(str, Enum):
    organization = "organization"
    facility = "facility"
    department = "department"

class ContentStatus(str, Enum):
    draft = "draft"
    approved = "approved"