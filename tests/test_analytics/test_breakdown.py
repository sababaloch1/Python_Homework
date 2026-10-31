from datetime import date
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app.analytics.breakdown import calculate_breakdown
from api.app.analytics.summary import calculate_summary
from api.app.core.enums import ActivityCategory, Scope, Scope2Method, Unit, UserRole
from api.app.core.models import (
    ActivityRecord,
    Department,
    EmissionResult,
    Facility,
    Organization,
    User,
)
from api.app.core.security import create_access_token


def test_breakdown_sums_equal_summary_total(db: Session):
    """Core test requirement: each grouping's sum equals the /summary total."""
    org = Organization(name="Breakdown Test Org", country_code="DE")
    db.add(org)
    db.commit()

    f1 = Facility(org_id=org.id, name="Plant North", country_code="DE")
    f2 = Facility(org_id=org.id, name="Warehouse South", country_code="DE")
    d1 = Department(org_id=org.id, name="Manufacturing")
    d2 = Department(org_id=org.id, name="Logistics")
    db.add_all([f1, f2, d1, d2])
    db.commit()

    # Record 1: Scope 2 (electricity) at Plant North / Manufacturing
    act1 = ActivityRecord(
        org_id=org.id,
        facility_id=f1.id,
        department_id=d1.id,
        category=ActivityCategory.electricity,
        amount=Decimal("10000"),
        unit=Unit.kWh,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    # Record 2: Scope 1 (natural_gas) at Plant North / Manufacturing
    act2 = ActivityRecord(
        org_id=org.id,
        facility_id=f1.id,
        department_id=d1.id,
        category=ActivityCategory.natural_gas,
        amount=Decimal("2000"),
        unit=Unit.m3,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    # Record 3: Scope 1 (diesel) at Warehouse South / Logistics
    act3 = ActivityRecord(
        org_id=org.id,
        facility_id=f2.id,
        department_id=d2.id,
        category=ActivityCategory.diesel,
        amount=Decimal("1500"),
        unit=Unit.litre,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    db.add_all([act1, act2, act3])
    db.commit()

    r1 = EmissionResult(
        activity_id=act1.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("3630.0"),  # 3.63 t
        is_current=True,
    )
    r2 = EmissionResult(
        activity_id=act2.id,
        scope=Scope.scope_1,
        method=None,
        kg_co2e=Decimal("4052.66"),  # 4.0527 t
        is_current=True,
    )
    r3 = EmissionResult(
        activity_id=act3.id,
        scope=Scope.scope_1,
        method=None,
        kg_co2e=Decimal("3875.31"),  # 3.8753 t
        is_current=True,
    )
    db.add_all([r1, r2, r3])
    db.commit()

    summary = calculate_summary(db, org.id)
    summary_total = summary["total_t_co2e"]

    # Test all 4 breakdown dimensions
    for dim in ("scope", "category", "department", "facility"):
        items = calculate_breakdown(db, org.id, by=dim)
        assert len(items) > 0
        dim_sum = round(sum(item["t_co2e"] for item in items), 4)
        assert dim_sum == pytest.approx(summary_total, abs=0.001)

        # Verify sorted descending
        values = [item["t_co2e"] for item in items]
        assert values == sorted(values, reverse=True)


def test_breakdown_unassigned_department_and_facility(db: Session):
    org = Organization(name="Unassigned Org", country_code="DE")
    db.add(org)
    db.commit()

    # Activity with NO facility and NO department
    act = ActivityRecord(
        org_id=org.id,
        facility_id=None,
        department_id=None,
        category=ActivityCategory.hotel_night,
        amount=Decimal("10"),
        unit=Unit.night,
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
    )
    db.add(act)
    db.commit()

    res = EmissionResult(
        activity_id=act.id,
        scope=Scope.scope_3,
        method=None,
        kg_co2e=Decimal("132.0"),  # 0.132 t
        is_current=True,
    )
    db.add(res)
    db.commit()

    by_dept = calculate_breakdown(db, org.id, by="department")
    assert len(by_dept) == 1
    assert by_dept[0]["label"] == "Unassigned"
    assert by_dept[0]["t_co2e"] == 0.132

    by_fac = calculate_breakdown(db, org.id, by="facility")
    assert len(by_fac) == 1
    assert by_fac[0]["label"] == "Unassigned"
    assert by_fac[0]["t_co2e"] == 0.132


def test_breakdown_invalid_dimension(db: Session):
    from fastapi import HTTPException

    org = Organization(name="Invalid Dim Org", country_code="DE")
    db.add(org)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        calculate_breakdown(db, org.id, by="invalid_dimension")
    assert exc.value.status_code == 422


def test_breakdown_empty_org(db: Session):
    org = Organization(name="Empty Breakdown Org", country_code="DE")
    db.add(org)
    db.commit()

    for dim in ("scope", "category", "department", "facility"):
        res = calculate_breakdown(db, org.id, by=dim)
        assert res == []


def test_breakdown_endpoint(client: TestClient):
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    org = Organization(name="Breakdown Endpoint Org", country_code="DE")
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(
        org_id=org.id,
        email="breakdown_user@test.com",
        password_hash="fake",
        full_name="Breakdown Tester",
        role=UserRole.admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    fac = Facility(org_id=org.id, name="HQ Facility", country_code="DE")
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
        is_current=True,
    )
    db.add(res)
    db.commit()

    token = create_access_token(subject=user.id, org_id=org.id, role=user.role.value)
    db.close()

    # 1. Unauthorized
    resp_unauth = client.get("/analytics/breakdown?by=scope")
    assert resp_unauth.status_code == 401

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Invalid dimension -> 422
    resp_invalid = client.get("/analytics/breakdown?by=wrong", headers=headers)
    assert resp_invalid.status_code == 422

    # 3. Missing 'by' parameter -> 422
    resp_missing = client.get("/analytics/breakdown", headers=headers)
    assert resp_missing.status_code == 422

    # 4. Valid facility breakdown
    resp_valid = client.get("/analytics/breakdown?by=facility", headers=headers)
    assert resp_valid.status_code == 200
    data = resp_valid.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["label"] == "HQ Facility"
    assert data[0]["t_co2e"] == 4.356

