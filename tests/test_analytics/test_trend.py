from datetime import date
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app.analytics.trend import calculate_trend
from api.app.core.enums import ActivityCategory, Scope, Scope2Method, Unit, UserRole
from api.app.core.models import (
    ActivityRecord,
    EmissionResult,
    Organization,
    User,
)
from api.app.core.security import create_access_token


def test_trend_structure_and_empty_months(db: Session):
    """Verifies that calculate_trend returns 12 months with 0 for missing months."""
    org = Organization(name="Trend Org Empty", country_code="DE")
    db.add(org)
    db.commit()

    # Add data only for 2026-03 and 2026-05
    act1 = ActivityRecord(
        org_id=org.id,
        category=ActivityCategory.electricity,
        amount=Decimal("10000"),
        unit=Unit.kWh,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    act2 = ActivityRecord(
        org_id=org.id,
        category=ActivityCategory.electricity,
        amount=Decimal("20000"),
        unit=Unit.kWh,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    db.add_all([act1, act2])
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
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("7260.0"),  # 7.26 t
        is_current=True,
    )
    db.add_all([r1, r2])
    db.commit()

    res = calculate_trend(db, org.id, anchor_date=date(2026, 10, 31))
    months = res["months"]
    assert len(months) == 12

    # Check order (from 2025-11 to 2026-10)
    assert months[0]["month"] == "2025-11"
    assert months[-1]["month"] == "2026-10"

    month_dict = {m["month"]: m["t_co2e"] for m in months}
    assert month_dict["2026-03"] == 3.63
    assert month_dict["2026-05"] == 7.26
    # Empty months should be 0.0
    assert month_dict["2026-01"] == 0.0
    assert month_dict["2026-02"] == 0.0
    assert month_dict["2026-04"] == 0.0

    assert res["current_total"] == round(3.63 + 7.26, 4)
    assert res["prev_year_total"] == 0.0
    assert res["pct_change"] is None  # prev_year_total is 0 -> None


def test_trend_yoy_pct_change(db: Session):
    org = Organization(name="YoY Trend Org", country_code="DE")
    db.add(org)
    db.commit()

    # Previous year activity (2025-01): 10 t CO2e
    act_prev = ActivityRecord(
        org_id=org.id,
        category=ActivityCategory.natural_gas,
        amount=Decimal("1000"),
        unit=Unit.m3,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
    )
    # Current year activity (2026-01): 12 t CO2e (+20%)
    act_curr = ActivityRecord(
        org_id=org.id,
        category=ActivityCategory.natural_gas,
        amount=Decimal("1200"),
        unit=Unit.m3,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    db.add_all([act_prev, act_curr])
    db.commit()

    r_prev = EmissionResult(
        activity_id=act_prev.id,
        scope=Scope.scope_1,
        method=None,
        kg_co2e=Decimal("10000.0"),  # 10.0 t
        is_current=True,
    )
    r_curr = EmissionResult(
        activity_id=act_curr.id,
        scope=Scope.scope_1,
        method=None,
        kg_co2e=Decimal("12000.0"),  # 12.0 t
        is_current=True,
    )
    db.add_all([r_prev, r_curr])
    db.commit()

    res = calculate_trend(db, org.id, anchor_date=date(2026, 10, 31))
    assert res["prev_year_total"] == 10.0
    assert res["current_total"] == 12.0
    assert res["pct_change"] == 20.0


def test_trend_filters_and_tenant_isolation(db: Session):
    org1 = Organization(name="Trend Tenant 1", country_code="DE")
    org2 = Organization(name="Trend Tenant 2", country_code="DE")
    db.add_all([org1, org2])
    db.commit()

    act1 = ActivityRecord(
        org_id=org1.id,
        category=ActivityCategory.electricity,
        amount=Decimal("1000"),
        unit=Unit.kWh,
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
    )
    act2 = ActivityRecord(
        org_id=org2.id,
        category=ActivityCategory.electricity,
        amount=Decimal("5000"),
        unit=Unit.kWh,
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
    )
    db.add_all([act1, act2])
    db.commit()

    # Org 1: location-based
    r1_loc = EmissionResult(
        activity_id=act1.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("1000.0"),  # 1.0 t
        is_current=True,
    )
    # Org 1: market-based (MUST NOT BE INCLUDED)
    r1_mkt = EmissionResult(
        activity_id=act1.id,
        scope=Scope.scope_2,
        method=Scope2Method.market_based,
        kg_co2e=Decimal("200.0"),
        is_current=True,
    )
    # Org 1: historical is_current=False (MUST NOT BE INCLUDED)
    r1_old = EmissionResult(
        activity_id=act1.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("800.0"),
        is_current=False,
    )
    # Org 2: must not leak
    r2 = EmissionResult(
        activity_id=act2.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("5000.0"),
        is_current=True,
    )
    db.add_all([r1_loc, r1_mkt, r1_old, r2])
    db.commit()

    res = calculate_trend(db, org1.id, anchor_date=date(2026, 10, 31))
    month_dict = {m["month"]: m["t_co2e"] for m in res["months"]}
    assert month_dict["2026-02"] == 1.0
    assert res["current_total"] == 1.0


def test_trend_endpoint(client: TestClient):
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    org = Organization(name="Trend Endpoint Org", country_code="DE")
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(
        org_id=org.id,
        email="trend_user@test.com",
        password_hash="fake",
        full_name="Trend Tester",
        role=UserRole.admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    act = ActivityRecord(
        org_id=org.id,
        category=ActivityCategory.electricity,
        amount=Decimal("10000"),
        unit=Unit.kWh,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    db.add(act)
    db.commit()
    db.refresh(act)

    res = EmissionResult(
        activity_id=act.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("3630.0"),
        is_current=True,
    )
    db.add(res)
    db.commit()

    token = create_access_token(subject=user.id, org_id=org.id, role=user.role.value)
    db.close()

    # 1. Unauthorized check
    resp_unauth = client.get("/analytics/trend")
    assert resp_unauth.status_code == 401

    # 2. Authorized check
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/analytics/trend?anchor=2026-10-31", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "months" in data
    assert len(data["months"]) == 12
    assert "prev_year_total" in data
    assert "current_total" in data
    assert "pct_change" in data
    assert data["current_total"] == 3.63

