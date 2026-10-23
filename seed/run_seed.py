"""Idempotent demo seed: one company, 3 facilities, 4 departments, 1 admin.

Run:  python -m seed.run_seed
Extend later with emission factors/tariffs (S2) and 24 months of activity data.
"""
from pathlib import Path

from api.app.core.database import SessionLocal
from api.app.core.enums import UserRole
from api.app.core.models import Department, Facility, Organization, User
from api.app.core.security import get_password_hash
from api.app.engine.importer import load_seed_files

DEMO_EMAIL = "user2acc@carbonlens.local"
DEMO_PASSWORD = "user2account"  


def seed_demo_company(db) -> None:
    if db.query(User).filter(User.email == DEMO_EMAIL).first():
        print("[seed] demo company already present, skipping")
        return
    org = Organization(name="Demo GmbH", country_code="DE", industry="Manufacturing",
                       employee_count=250, reporting_year_start_month=1)
    db.add(org)
    db.flush()
    for name in ("Operations", "Logistics", "Office", "Sales"):
        db.add(Department(org_id=org.id, name=name))
    for name, city in (("Dortmund HQ", "Dortmund"), ("Essen Plant", "Essen"), ("Köln Warehouse", "Köln")):
        db.add(Facility(org_id=org.id, name=name, city=city, country_code="DE", floor_area_m2=2500))
    db.add(User(org_id=org.id, email=DEMO_EMAIL, password_hash=get_password_hash(DEMO_PASSWORD),
                full_name="Demo Admin", role=UserRole.admin))
    db.commit()
    print(f"[seed] created demo company; login {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    with SessionLocal() as session:
        load_seed_files(session, Path(__file__).parent)   # S2: factors.csv + tariffs.csv
        seed_demo_company(session)
