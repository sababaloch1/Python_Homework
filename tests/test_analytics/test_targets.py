from datetime import date
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app.analytics.targets import calculate_targets_status, evaluate_target_status
from api.app.core.enums import ActivityCategory, Scope, Scope2Method, Unit, UserRole
from api.app.core.models import (
    ActivityRecord,
    EmissionResult,
    Organization,
    Target,
    User,
)
from api.app.core.security import create_access_token


def test_evaluate_target_status_pure_math_on_track():
    """Tests straight line interpolation and on_track condition."""
    # Baseline 2024: 100.0 t, Target 2030: 70.0 t (30% reduction over 6 years = 5 t/year reduction)
    # At 2026 (2 years in): expected_now = 100.0 - 5.0 * 2 = 90.0 t
    # Actual 2026: 88.0 t <= 90.0 t -> on_track
    res = evaluate_target_status(
        baseline_year=2024,
        target_year=2030,
        reduction_pct=30.0,
        baseline_t=100.0,
        actual_t=88.0,
        current_year=2026,
    )
    assert res["baseline_t"] == 100.0
    assert res["target_t"] == 70.0
    assert res["expected_now"] == 90.0
    assert res["actual_t"] == 88.0
    assert res["status"] == "on_track"
    assert res["saved_t"] == 12.0  # 100 - 88 = 12 t saved


def test_evaluate_target_status_pure_math_off_track():
    """Tests off_track condition when actual emissions exceed expected trajectory."""
    # At 2026: expected_now = 90.0 t. Actual 2026: 95.0 t > 90.0 t -> off_track
    res = evaluate_target_status(
        baseline_year=2024,
        target_year=2030,
        reduction_pct=30.0,
        baseline_t=100.0,
        actual_t=95.0,
        current_year=2026,
    )
    assert res["expected_now"] == 90.0
    assert res["actual_t"] == 95.0
    assert res["status"] == "off_track"
    assert res["saved_t"] == 5.0  # 100 - 95 = 5 t saved


def test_targets_status_database_aggregation(db: Session):
    org = Organization(name="Target Test Org", country_code="DE")
    db.add(org)
    db.commit()

    # 1. Target with scope_2 filter: baseline 2024, target 2030, 20% reduction
    t_scope2 = Target(
        org_id=org.id,
        scope=Scope.scope_2,
        baseline_year=2024,
        target_year=2030,
        reduction_pct=Decimal("20.00"),
    )
    # 2. Overall target (all scopes): baseline 2024, target 2030, 50% reduction
    t_all = Target(
        org_id=org.id,
        scope=None,
        baseline_year=2024,
        target_year=2030,
        reduction_pct=Decimal("50.00"),
    )
    db.add_all([t_scope2, t_all])
    db.commit()

    # Activities in baseline year (2024):
    # - Electricity (Scope 2): 10,000 kg = 10.0 t
    # - Natural Gas (Scope 1): 20,000 kg = 20.0 t
    # Total 2024 = 30.0 t
    act_2024_elec = ActivityRecord(org_id=org.id, category=ActivityCategory.electricity, amount=Decimal("1"), unit=Unit.kWh,
                                   period_start=date(2024, 6, 1), period_end=date(2024, 6, 30))
    act_2024_gas = ActivityRecord(org_id=org.id, category=ActivityCategory.natural_gas, amount=Decimal("1"), unit=Unit.m3,
                                  period_start=date(2024, 6, 1), period_end=date(2024, 6, 30))

    # Activities in current year (2026):
    # - Electricity (Scope 2): 9,000 kg = 9.0 t
    # - Natural Gas (Scope 1): 18,000 kg = 18.0 t
    # Total 2026 = 27.0 t
    act_2026_elec = ActivityRecord(org_id=org.id, category=ActivityCategory.electricity, amount=Decimal("1"), unit=Unit.kWh,
                                   period_start=date(2026, 6, 1), period_end=date(2026, 6, 30))
    act_2026_gas = ActivityRecord(org_id=org.id, category=ActivityCategory.natural_gas, amount=Decimal("1"), unit=Unit.m3,
                                  period_start=date(2026, 6, 1), period_end=date(2026, 6, 30))
    db.add_all([act_2024_elec, act_2024_gas, act_2026_elec, act_2026_gas])
    db.commit()

    r1 = EmissionResult(activity_id=act_2024_elec.id, scope=Scope.scope_2, method=Scope2Method.location_based,
                        kg_co2e=Decimal("10000.0"), is_current=True)
    r2 = EmissionResult(activity_id=act_2024_gas.id, scope=Scope.scope_1, method=None,
                        kg_co2e=Decimal("20000.0"), is_current=True)
    r3 = EmissionResult(activity_id=act_2026_elec.id, scope=Scope.scope_2, method=Scope2Method.location_based,
                        kg_co2e=Decimal("9000.0"), is_current=True)
    r4 = EmissionResult(activity_id=act_2026_gas.id, scope=Scope.scope_1, method=None,
                        kg_co2e=Decimal("18000.0"), is_current=True)
    db.add_all([r1, r2, r3, r4])
    db.commit()

    status_list = calculate_targets_status(db, org.id, as_of_year=2026)
    assert len(status_list) == 2

    # Verify t_scope2:
    # baseline_t (Scope 2 only in 2024) = 10.0 t
    # target_t = 10.0 * (1 - 0.20) = 8.0 t
    # slope = (8.0 - 10.0) / 6 = -0.3333 t/year. expected_now at 2026 = 10.0 - 0.6667 = 9.3333 t
    # actual_t (Scope 2 only in 2026) = 9.0 t <= 9.3333 t -> on_track
    s2_status = next(s for s in status_list if s["scope"] == "scope_2")
    assert s2_status["baseline_t"] == 10.0
    assert s2_status["target_t"] == 8.0
    assert s2_status["actual_t"] == 9.0
    assert s2_status["status"] == "on_track"
    assert s2_status["saved_t"] == 1.0

    # Verify t_all:
    # baseline_t (all scopes in 2024) = 30.0 t
    # target_t = 30.0 * (1 - 0.50) = 15.0 t
    # slope = (15.0 - 30.0) / 6 = -2.5 t/year. expected_now at 2026 = 30.0 - 5.0 = 25.0 t
    # actual_t (all scopes in 2026) = 27.0 t > 25.0 t -> off_track
    all_status = next(s for s in status_list if s["scope"] is None)
    assert all_status["baseline_t"] == 30.0
    assert all_status["target_t"] == 15.0
    assert all_status["expected_now"] == 25.0
    assert all_status["actual_t"] == 27.0
    assert all_status["status"] == "off_track"
    assert all_status["saved_t"] == 3.0


def test_target_roles_and_validation(client: TestClient):
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    org = Organization(name="Target Roles Org", country_code="DE")
    db.add(org)
    db.commit()
    db.refresh(org)

    admin = User(org_id=org.id, email="admin@target.test", password_hash="h", role=UserRole.admin)
    manager = User(org_id=org.id, email="manager@target.test", password_hash="h", role=UserRole.manager)
    contributor = User(org_id=org.id, email="contrib@target.test", password_hash="h", role=UserRole.contributor)
    db.add_all([admin, manager, contributor])
    db.commit()
    for u in (admin, manager, contributor):
        db.refresh(u)

    token_admin = create_access_token(subject=admin.id, org_id=org.id, role="admin")
    token_manager = create_access_token(subject=manager.id, org_id=org.id, role="manager")
    token_contrib = create_access_token(subject=contributor.id, org_id=org.id, role="contributor")
    db.close()

    # 1. Contributor forbidden (HTTP 403)
    resp_contrib = client.post(
        "/analytics/targets",
        headers={"Authorization": f"Bearer {token_contrib}"},
        json={"baseline_year": 2024, "target_year": 2030, "reduction_pct": 25.0},
    )
    assert resp_contrib.status_code == 403

    # 2. Validation: target_year <= baseline_year -> 422
    resp_val_year = client.post(
        "/analytics/targets",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"baseline_year": 2026, "target_year": 2024, "reduction_pct": 25.0},
    )
    assert resp_val_year.status_code == 422

    # 3. Validation: reduction_pct <= 0 or > 100 -> 422
    resp_val_pct0 = client.post(
        "/analytics/targets",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"baseline_year": 2024, "target_year": 2030, "reduction_pct": 0.0},
    )
    assert resp_val_pct0.status_code == 422

    resp_val_pct101 = client.post(
        "/analytics/targets",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"baseline_year": 2024, "target_year": 2030, "reduction_pct": 105.0},
    )
    assert resp_val_pct101.status_code == 422

    # 4. Manager can create target (HTTP 201)
    resp_mgr = client.post(
        "/analytics/targets",
        headers={"Authorization": f"Bearer {token_manager}"},
        json={"scope": "scope_1", "baseline_year": 2024, "target_year": 2030, "reduction_pct": 30.0},
    )
    assert resp_mgr.status_code == 201
    mgr_data = resp_mgr.json()
    assert mgr_data["scope"] == "scope_1"
    assert mgr_data["reduction_pct"] == 30.0

    # 5. Admin can create target (HTTP 201)
    resp_adm = client.post(
        "/analytics/targets",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"baseline_year": 2024, "target_year": 2035, "reduction_pct": 40.0},
    )
    assert resp_adm.status_code == 201

    # 6. GET /analytics/targets lists both targets
    list_resp = client.get("/analytics/targets", headers={"Authorization": f"Bearer {token_contrib}"})
    assert list_resp.status_code == 200
    targets_data = list_resp.json()
    assert len(targets_data) == 2

    # 7. GET /analytics/targets/status returns list
    status_resp = client.get("/analytics/targets/status?as_of_year=2026", headers={"Authorization": f"Bearer {token_contrib}"})
    assert status_resp.status_code == 200
    statuses = status_resp.json()
    assert len(statuses) == 2
    assert "status" in statuses[0]
    assert "expected_now" in statuses[0]

