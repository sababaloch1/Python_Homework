from datetime import date
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app.analytics.summary import calculate_summary
from api.app.core.enums import ActivityCategory, Scope, Scope2Method, Unit, UserRole
from api.app.core.models import (
    ActivityRecord,
    EmissionFactor,
    EmissionResult,
    Facility,
    Organization,
    RegionTariff,
    User,
)
from api.app.core.security import create_access_token
from api.app.engine import service as engine_service


def test_summary_12000_kwh_worked_example(db: Session):
    """Test with 12,000 kWh x 0.363 = 4,356 kg CO2e (= 4.356 t CO2e), matching FR-3.01."""
    org = Organization(name="Test Org Worked Example", country_code="DE")
    db.add(org)
    db.commit()

    fac = Facility(org_id=org.id, name="Test Plant", country_code="DE")
    db.add(fac)
    db.commit()

    factor = EmissionFactor(
        activity_type=ActivityCategory.electricity,
        region="DE",
        year=2026,
        unit=Unit.kWh,
        kg_co2e_per_unit=Decimal("0.363"),
        scope=Scope.scope_2,
        ghg_category="Purchased electricity",
        source="UBA 2026",
        version=1,
        is_active=True,
    )
    tariff = RegionTariff(
        region="DE",
        activity_type=ActivityCategory.electricity,
        unit=Unit.kWh,
        eur_per_unit=Decimal("0.1670"),
        year=2026,
        source="BDEW 2026",
    )
    db.add_all([factor, tariff])
    db.commit()

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

    engine_service.calculate_activity(db, act.id)

    summary = calculate_summary(db, org.id)
    assert summary["total_t_co2e"] == 4.356
    assert summary["by_scope"]["scope_1"] == 0.0
    assert summary["by_scope"]["scope_2"] == 4.356
    assert summary["by_scope"]["scope_3"] == 0.0
    assert summary["failed_records"] == 0
    assert summary["total_cost_eur"] == 2004.0
    assert summary["cost_complete"] is True


def test_summary_failed_records_and_incomplete_cost(db: Session):
    org = Organization(name="Test Org Incomplete", country_code="DE")
    db.add(org)
    db.commit()

    # 1. Successful electricity record with tariff
    act1 = ActivityRecord(
        org_id=org.id,
        category=ActivityCategory.electricity,
        amount=Decimal("1000"),
        unit=Unit.kWh,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    # 2. Scope 1 record without cost (e.g. natural gas with no tariff)
    act2 = ActivityRecord(
        org_id=org.id,
        category=ActivityCategory.natural_gas,
        amount=Decimal("500"),
        unit=Unit.m3,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    # 3. Failed record (calculation failed -> kg_co2e is NULL)
    act3 = ActivityRecord(
        org_id=org.id,
        category=ActivityCategory.diesel,
        amount=Decimal("200"),
        unit=Unit.litre,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    db.add_all([act1, act2, act3])
    db.commit()

    res1 = EmissionResult(
        activity_id=act1.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("363.0"),
        cost_eur=Decimal("167.0"),
        is_current=True,
    )
    res2 = EmissionResult(
        activity_id=act2.id,
        scope=Scope.scope_1,
        method=None,
        kg_co2e=Decimal("1013.165"),
        cost_eur=None,  # Missing cost
        is_current=True,
    )
    res3 = EmissionResult(
        activity_id=act3.id,
        scope=None,
        method=None,
        kg_co2e=None,  # Failed calculation
        cost_eur=None,
        is_current=True,
    )
    db.add_all([res1, res2, res3])
    db.commit()

    summary = calculate_summary(db, org.id)
    assert summary["failed_records"] == 1
    assert summary["cost_complete"] is False
    assert summary["total_t_co2e"] == round(float((Decimal("363.0") + Decimal("1013.165")) / Decimal("1000")), 4)
    assert summary["by_scope"]["scope_1"] == round(float(Decimal("1013.165") / Decimal("1000")), 4)
    assert summary["by_scope"]["scope_2"] == round(float(Decimal("363.0") / Decimal("1000")), 4)
    assert summary["total_cost_eur"] == 167.0


def test_summary_empty_organization(db: Session):
    org = Organization(name="Empty Org", country_code="DE")
    db.add(org)
    db.commit()

    summary = calculate_summary(db, org.id)
    assert summary["total_t_co2e"] == 0.0
    assert summary["by_scope"] == {"scope_1": 0.0, "scope_2": 0.0, "scope_3": 0.0}
    assert summary["failed_records"] == 0
    assert summary["total_cost_eur"] == 0.0
    assert summary["cost_complete"] is True


def test_summary_tenant_isolation_and_filters(db: Session):
    org1 = Organization(name="Tenant 1", country_code="DE")
    org2 = Organization(name="Tenant 2", country_code="DE")
    db.add_all([org1, org2])
    db.commit()

    act1 = ActivityRecord(
        org_id=org1.id,
        category=ActivityCategory.electricity,
        amount=Decimal("1000"),
        unit=Unit.kWh,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    act2 = ActivityRecord(
        org_id=org2.id,
        category=ActivityCategory.electricity,
        amount=Decimal("5000"),
        unit=Unit.kWh,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    db.add_all([act1, act2])
    db.commit()

    # Location based for Org 1
    r1_loc = EmissionResult(
        activity_id=act1.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("363.0"),
        cost_eur=Decimal("167.0"),
        is_current=True,
    )
    # Market based for Org 1 (MUST NOT BE ADDED)
    r1_mkt = EmissionResult(
        activity_id=act1.id,
        scope=Scope.scope_2,
        method=Scope2Method.market_based,
        kg_co2e=Decimal("20.0"),
        cost_eur=None,
        is_current=True,
    )
    # Historic (is_current=False) for Org 1 (MUST NOT BE ADDED)
    r1_old = EmissionResult(
        activity_id=act1.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("350.0"),
        cost_eur=Decimal("150.0"),
        is_current=False,
    )
    # Org 2 result (MUST NOT BE INCLUDED)
    r2 = EmissionResult(
        activity_id=act2.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("1815.0"),
        cost_eur=Decimal("835.0"),
        is_current=True,
    )
    db.add_all([r1_loc, r1_mkt, r1_old, r2])
    db.commit()

    summary = calculate_summary(db, org1.id)
    assert summary["total_t_co2e"] == 0.363
    assert summary["by_scope"]["scope_2"] == 0.363
    assert summary["total_cost_eur"] == 167.0


def test_summary_date_filtering(db: Session):
    org = Organization(name="Date Org", country_code="DE")
    db.add(org)
    db.commit()

    act_jan = ActivityRecord(
        org_id=org.id,
        category=ActivityCategory.electricity,
        amount=Decimal("1000"),
        unit=Unit.kWh,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    act_feb = ActivityRecord(
        org_id=org.id,
        category=ActivityCategory.electricity,
        amount=Decimal("2000"),
        unit=Unit.kWh,
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
    )
    db.add_all([act_jan, act_feb])
    db.commit()

    r_jan = EmissionResult(
        activity_id=act_jan.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("363.0"),
        is_current=True,
    )
    r_feb = EmissionResult(
        activity_id=act_feb.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("726.0"),
        is_current=True,
    )
    db.add_all([r_jan, r_feb])
    db.commit()

    # Jan only
    s_jan = calculate_summary(db, org.id, start=date(2026, 1, 1), end=date(2026, 1, 31))
    assert s_jan["total_t_co2e"] == 0.363

    # Feb only
    s_feb = calculate_summary(db, org.id, start=date(2026, 2, 1), end=date(2026, 2, 28))
    assert s_feb["total_t_co2e"] == 0.726

    # Both
    s_both = calculate_summary(db, org.id, start=date(2026, 1, 1), end=date(2026, 2, 28))
    assert s_both["total_t_co2e"] == round(float(Decimal("1089.0") / Decimal("1000")), 4)


def test_get_summary_endpoint(client: TestClient):
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    org = Organization(name="Endpoint Org", country_code="DE")
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(
        org_id=org.id,
        email="summary_user@test.com",
        password_hash="fake",
        full_name="Summary Tester",
        role=UserRole.admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    act = ActivityRecord(
        org_id=org.id,
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
        cost_eur=Decimal("2004.0"),
        is_current=True,
    )
    db.add(res)
    db.commit()

    token = create_access_token(subject=user.id, org_id=org.id, role=user.role.value)
    db.close()

    # 1. Unauthorized
    unauth = client.get("/analytics/summary")
    assert unauth.status_code == 401

    # 2. Authorized
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/analytics/summary?start=2026-01-01&end=2026-01-31", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_t_co2e"] == 4.356
    assert data["by_scope"]["scope_2"] == 4.356
    assert data["by_scope"]["scope_1"] == 0.0
    assert data["by_scope"]["scope_3"] == 0.0
    assert data["total_cost_eur"] == 2004.0
    assert data["cost_complete"] is True
    assert data["failed_records"] == 0
    assert data["period"] == {"start": "2026-01-01", "end": "2026-01-31"}

