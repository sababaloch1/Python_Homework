from datetime import date
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app.analytics.sources import calculate_top_sources, get_activity_records
from api.app.analytics.summary import calculate_summary
from api.app.core.enums import ActivityCategory, Scope, Scope2Method, Unit, UserRole
from api.app.core.models import (
    ActivityRecord,
    EmissionResult,
    Facility,
    Organization,
    User,
)
from api.app.core.security import create_access_token


def test_records_sums_to_same_total_as_summary(db: Session):
    """Core test requirement: /records sums to the same total as /summary for the same filters."""
    org = Organization(name="Sources Test Org", country_code="DE")
    db.add(org)
    db.commit()

    f1 = Facility(org_id=org.id, name="Factory Alpha", country_code="DE")
    f2 = Facility(org_id=org.id, name="Factory Beta", country_code="DE")
    db.add_all([f1, f2])
    db.commit()

    # 1. Scope 2 electricity
    act1 = ActivityRecord(
        org_id=org.id,
        facility_id=f1.id,
        category=ActivityCategory.electricity,
        amount=Decimal("12000"),
        unit=Unit.kWh,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    # 2. Scope 1 natural gas
    act2 = ActivityRecord(
        org_id=org.id,
        facility_id=f1.id,
        category=ActivityCategory.natural_gas,
        amount=Decimal("3000"),
        unit=Unit.m3,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    # 3. Scope 1 diesel in Feb
    act3 = ActivityRecord(
        org_id=org.id,
        facility_id=f2.id,
        category=ActivityCategory.diesel,
        amount=Decimal("1000"),
        unit=Unit.litre,
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
    )
    db.add_all([act1, act2, act3])
    db.commit()

    r1 = EmissionResult(
        activity_id=act1.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("4356.0"),
        trace={"formula": "12000 kWh x 0.363 = 4356 kg CO2e"},
        is_current=True,
    )
    r2 = EmissionResult(
        activity_id=act2.id,
        scope=Scope.scope_1,
        method=None,
        kg_co2e=Decimal("6078.99"),
        trace={"formula": "3000 m3 x 2.02633 = 6078.99 kg CO2e"},
        is_current=True,
    )
    r3 = EmissionResult(
        activity_id=act3.id,
        scope=Scope.scope_1,
        method=None,
        kg_co2e=Decimal("2583.54"),
        trace={"formula": "1000 litre x 2.58354 = 2583.54 kg CO2e"},
        is_current=True,
    )
    db.add_all([r1, r2, r3])
    db.commit()

    # 1. Total comparison without date filter
    summary_all = calculate_summary(db, org.id)
    records_all = get_activity_records(db, org.id)
    sum_kg = sum(Decimal(str(r["kg_co2e"])) for r in records_all if r["kg_co2e"] is not None)
    records_total_t = round(float(sum_kg / Decimal("1000")), 4)
    assert records_total_t == summary_all["total_t_co2e"]

    # 2. Total comparison with date filter (Jan 2026 only)
    start_filter = date(2026, 1, 1)
    end_filter = date(2026, 1, 31)
    summary_jan = calculate_summary(db, org.id, start=start_filter, end=end_filter)
    records_jan = get_activity_records(db, org.id, start=start_filter, end=end_filter)
    sum_jan_kg = sum(Decimal(str(r["kg_co2e"])) for r in records_jan if r["kg_co2e"] is not None)
    records_jan_t = round(float(sum_jan_kg / Decimal("1000")), 4)
    assert records_jan_t == summary_jan["total_t_co2e"]


def test_records_trace_error_and_summary(db: Session):
    org = Organization(name="Trace Org", country_code="DE")
    db.add(org)
    db.commit()

    # Successful record
    act_ok = ActivityRecord(
        org_id=org.id,
        category=ActivityCategory.electricity,
        amount=Decimal("1000"),
        unit=Unit.kWh,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    # Failed record
    act_err = ActivityRecord(
        org_id=org.id,
        category=ActivityCategory.diesel,
        amount=Decimal("50"),
        unit=Unit.litre,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    db.add_all([act_ok, act_err])
    db.commit()

    res_ok = EmissionResult(
        activity_id=act_ok.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("363.0"),
        trace={"formula": "1000 kWh x 0.363 = 363 kg CO2e"},
        is_current=True,
    )
    res_err = EmissionResult(
        activity_id=act_err.id,
        scope=None,
        method=None,
        kg_co2e=None,
        trace={"error": "Missing diesel factor for year 2026"},
        is_current=True,
    )
    db.add_all([res_ok, res_err])
    db.commit()

    records = get_activity_records(db, org.id)
    assert len(records) == 2

    rec_by_id = {r["id"]: r for r in records}
    assert rec_by_id[str(act_ok.id)]["kg_co2e"] == 363.0
    assert rec_by_id[str(act_ok.id)]["error"] is None
    assert "1000 kWh x 0.363 = 363 kg CO2e" in rec_by_id[str(act_ok.id)]["summary"]

    assert rec_by_id[str(act_err.id)]["kg_co2e"] is None
    assert rec_by_id[str(act_err.id)]["error"] == "Missing diesel factor for year 2026"


def test_top_sources_ranking_and_filters(db: Session):
    org = Organization(name="Top Sources Org", country_code="DE")
    db.add(org)
    db.commit()

    f1 = Facility(org_id=org.id, name="HQ", country_code="DE")
    f2 = Facility(org_id=org.id, name="Plant", country_code="DE")
    db.add_all([f1, f2])
    db.commit()

    # Source A: electricity at Plant (high emissions = 50 t)
    act1 = ActivityRecord(org_id=org.id, facility_id=f2.id, category=ActivityCategory.electricity,
                          amount=Decimal("1"), unit=Unit.kWh, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31))
    # Source B: gas at Plant (medium emissions = 20 t)
    act2 = ActivityRecord(org_id=org.id, facility_id=f2.id, category=ActivityCategory.natural_gas,
                          amount=Decimal("1"), unit=Unit.m3, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31))
    # Source C: electricity at HQ (low emissions = 10 t)
    act3 = ActivityRecord(org_id=org.id, facility_id=f1.id, category=ActivityCategory.electricity,
                          amount=Decimal("1"), unit=Unit.kWh, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31))
    # Source D: fleet km with unassigned facility (5 t)
    act4 = ActivityRecord(org_id=org.id, facility_id=None, category=ActivityCategory.fleet_km,
                          amount=Decimal("1"), unit=Unit.km, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31))
    db.add_all([act1, act2, act3, act4])
    db.commit()

    r1 = EmissionResult(activity_id=act1.id, scope=Scope.scope_2, method=Scope2Method.location_based,
                        kg_co2e=Decimal("50000.0"), is_current=True)
    r2 = EmissionResult(activity_id=act2.id, scope=Scope.scope_1, method=None,
                        kg_co2e=Decimal("20000.0"), is_current=True)
    r3 = EmissionResult(activity_id=act3.id, scope=Scope.scope_2, method=Scope2Method.location_based,
                        kg_co2e=Decimal("10000.0"), is_current=True)
    r4 = EmissionResult(activity_id=act4.id, scope=Scope.scope_1, method=None,
                        kg_co2e=Decimal("5000.0"), is_current=True)
    db.add_all([r1, r2, r3, r4])
    db.commit()

    top_sources = calculate_top_sources(db, org.id, limit=3)
    assert len(top_sources) == 3
    # Sorted descending
    assert top_sources[0]["category"] == "electricity"
    assert top_sources[0]["facility"] == "Plant"
    assert top_sources[0]["t_co2e"] == 50.0

    assert top_sources[1]["category"] == "natural_gas"
    assert top_sources[1]["facility"] == "Plant"
    assert top_sources[1]["t_co2e"] == 20.0

    assert top_sources[2]["category"] == "electricity"
    assert top_sources[2]["facility"] == "HQ"
    assert top_sources[2]["t_co2e"] == 10.0

    # Test limit=10 to check Unassigned facility
    all_top = calculate_top_sources(db, org.id, limit=10)
    assert len(all_top) == 4
    assert all_top[3]["category"] == "fleet_km"
    assert all_top[3]["facility"] == "Unassigned"
    assert all_top[3]["t_co2e"] == 5.0


def test_sources_endpoints(client: TestClient):
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    org = Organization(name="Sources API Org", country_code="DE")
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(
        org_id=org.id,
        email="sources_user@test.com",
        password_hash="fake",
        full_name="Sources Tester",
        role=UserRole.admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    fac = Facility(org_id=org.id, name="Sources Facility", country_code="DE")
    db.add(fac)
    db.commit()
    db.refresh(fac)

    act = ActivityRecord(
        org_id=org.id,
        facility_id=fac.id,
        category=ActivityCategory.electricity,
        amount=Decimal("12000"),
        unit=Unit.kWh,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    db.add(act)
    db.commit()
    db.refresh(act)

    res = EmissionResult(
        activity_id=act.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("4356.0"),
        trace={"formula": "12000 kWh x 0.363 = 4356 kg CO2e"},
        is_current=True,
    )
    db.add(res)
    db.commit()

    token = create_access_token(subject=user.id, org_id=org.id, role=user.role.value)
    db.close()

    # 1. Unauthorized checks
    assert client.get("/analytics/top-sources").status_code == 401
    assert client.get("/analytics/records").status_code == 401

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Authorized /analytics/top-sources
    resp_top = client.get("/analytics/top-sources?limit=5", headers=headers)
    assert resp_top.status_code == 200
    top_data = resp_top.json()
    assert len(top_data) == 1
    assert top_data[0]["category"] == "electricity"
    assert top_data[0]["facility"] == "Sources Facility"
    assert top_data[0]["t_co2e"] == 4.356

    # 3. Authorized /analytics/records
    resp_rec = client.get("/analytics/records", headers=headers)
    assert resp_rec.status_code == 200
    rec_data = resp_rec.json()
    assert len(rec_data) == 1
    assert rec_data[0]["category"] == "electricity"
    assert rec_data[0]["kg_co2e"] == 4356.0
    assert rec_data[0]["summary"] is not None

