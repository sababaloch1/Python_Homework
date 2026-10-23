from datetime import date
from decimal import Decimal

from api.app.core.enums import ActivityCategory, Scope, Unit
from api.app.core.models import ActivityRecord, EmissionFactor, Facility, Organization, RegionTariff


def make_org(db, country="DE"):
    org = Organization(name="Test GmbH", country_code=country)
    db.add(org)
    db.commit()
    return org


def make_facility(db, org, country="DE"):
    fac = Facility(org_id=org.id, name="Plant", country_code=country)
    db.add(fac)
    db.commit()
    return fac


def make_factor(db, type_="electricity", region="DE", year=2024, unit="kWh", value="0.363",
                scope="scope_2", source="UBA", version=1, active=True):
    f = EmissionFactor(activity_type=ActivityCategory(type_), region=region, year=year, unit=Unit(unit),
                       kg_co2e_per_unit=Decimal(value), scope=Scope(scope), ghg_category="Test",
                       source=source, version=version, is_active=active)
    db.add(f)
    db.commit()
    return f


def make_tariff(db, type_="electricity", region="DE", year=2024, unit="kWh", eur="0.30"):
    t = RegionTariff(activity_type=ActivityCategory(type_), region=region, year=year, unit=Unit(unit),
                     eur_per_unit=Decimal(eur), source="admin")
    db.add(t)
    db.commit()
    return t


def make_activity(db, org, facility=None, category="electricity", amount="12000", unit="kWh",
                  start=date(2024, 3, 1), created=True):
    a = ActivityRecord(org_id=org.id, facility_id=facility.id if facility else None,
                       category=ActivityCategory(category), amount=Decimal(amount), unit=Unit(unit),
                       period_start=start, period_end=start)
    db.add(a)
    db.commit()
    return a
