from datetime import date
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app.analytics.score import (
    calculate_sustainability_score,
    score_carbon_intensity,
    score_data_completeness,
    score_target_progress,
    score_yoy_trend,
)
from api.app.core.enums import ActivityCategory, Scope, Scope2Method, Unit, UserRole
from api.app.core.models import (
    ActivityRecord,
    EmissionResult,
    Organization,
    SustainabilityScore,
    Target,
    User,
)
from api.app.core.security import create_access_token


def test_component_1_yoy_trend():
    """Unit test for Component 1 pure scoring function."""
    assert score_yoy_trend(-12.5)["points"] == 25.0
    assert score_yoy_trend(-8.0)["points"] == 20.0
    assert score_yoy_trend(-2.0)["points"] == 15.0
    assert score_yoy_trend(3.5)["points"] == 10.0
    assert score_yoy_trend(10.0)["points"] == 5.0
    assert score_yoy_trend(20.0)["points"] == 0.0
    assert score_yoy_trend(None)["points"] == 12.5


def test_component_2_target_progress():
    """Unit test for Component 2 pure scoring function."""
    # No targets
    assert score_target_progress([])["points"] == 0.0

    # 2 targets, both on track
    targets_all_good = [{"status": "on_track"}, {"status": "on_track"}]
    assert score_target_progress(targets_all_good)["points"] == 25.0

    # 2 targets, 1 on track, 1 off track
    targets_half = [{"status": "on_track"}, {"status": "off_track"}]
    assert score_target_progress(targets_half)["points"] == 12.5

    # 2 targets, both off track
    targets_none = [{"status": "off_track"}, {"status": "off_track"}]
    assert score_target_progress(targets_none)["points"] == 0.0


def test_component_3_data_completeness():
    """Unit test for Component 3 pure scoring function."""
    # 12 months with data, 0 errors -> 15 + 10 = 25.0
    assert score_data_completeness(12, 100, 0)["points"] == 25.0

    # 6 months with data, 0 errors -> 7.5 + 10 = 17.5
    assert score_data_completeness(6, 50, 0)["points"] == 17.5

    # 12 months with data, 20% errors -> 15 + 8.0 = 23.0
    assert score_data_completeness(12, 100, 20)["points"] == 23.0

    # 0 months with data -> 0.0
    assert score_data_completeness(0, 0, 0)["points"] == 0.0


def test_component_4_carbon_intensity():
    """Unit test for Component 4 pure scoring function."""
    # < 2.0 t/employee -> 25.0
    assert score_carbon_intensity(150.0, 100)["points"] == 25.0

    # 2.0 - 4.0 t/employee -> 20.0
    assert score_carbon_intensity(300.0, 100)["points"] == 20.0

    # 4.0 - 7.0 t/employee -> 15.0
    assert score_carbon_intensity(500.0, 100)["points"] == 15.0

    # 7.0 - 12.0 t/employee -> 10.0
    assert score_carbon_intensity(1000.0, 100)["points"] == 10.0

    # 12.0 - 20.0 t/employee -> 5.0
    assert score_carbon_intensity(1500.0, 100)["points"] == 5.0

    # >= 20.0 t/employee -> 0.0
    assert score_carbon_intensity(2500.0, 100)["points"] == 0.0

    # Missing employee count -> baseline 12.5
    assert score_carbon_intensity(500.0, None)["points"] == 12.5
    assert score_carbon_intensity(500.0, 0)["points"] == 12.5


def test_score_empty_organization_returns_null(db: Session):
    """An organisation with no data returns score null with a clear message."""
    org = Organization(name="Empty Score Org", country_code="DE")
    db.add(org)
    db.commit()

    res = calculate_sustainability_score(db, org.id)
    assert res["score"] is None
    assert "No activity data recorded yet" in res["message"]
    assert res["components"] is None


def test_score_calculation_and_persistence(db: Session):
    org = Organization(name="Scored Org", country_code="DE", employee_count=100)
    db.add(org)
    db.commit()

    # Add a target
    target = Target(
        org_id=org.id,
        baseline_year=2024,
        target_year=2030,
        reduction_pct=Decimal("30.0"),
    )
    db.add(target)
    db.commit()

    # Add activities
    act_prev = ActivityRecord(
        org_id=org.id, category=ActivityCategory.electricity, amount=Decimal("10000"), unit=Unit.kWh,
        period_start=date(2025, 1, 1), period_end=date(2025, 1, 31)
    )
    act_curr = ActivityRecord(
        org_id=org.id, category=ActivityCategory.electricity, amount=Decimal("8000"), unit=Unit.kWh,
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 31)
    )
    db.add_all([act_prev, act_curr])
    db.commit()

    r_prev = EmissionResult(
        activity_id=act_prev.id, scope=Scope.scope_2, method=Scope2Method.location_based,
        kg_co2e=Decimal("3630.0"), is_current=True
    )
    r_curr = EmissionResult(
        activity_id=act_curr.id, scope=Scope.scope_2, method=Scope2Method.location_based,
        kg_co2e=Decimal("2904.0"), is_current=True
    )
    db.add_all([r_prev, r_curr])
    db.commit()

    res = calculate_sustainability_score(db, org.id)
    assert res["score"] is not None
    assert 0 <= res["score"] <= 100
    assert "components" in res
    assert "yoy_trend" in res["components"]
    assert "target_progress" in res["components"]
    assert "data_completeness" in res["components"]
    assert "carbon_intensity" in res["components"]

    # Verify score row was saved in sustainability_scores table
    saved = db.query(SustainabilityScore).filter(SustainabilityScore.org_id == org.id).first()
    assert saved is not None
    assert saved.score == res["score"]
    assert saved.components["yoy_trend"]["points"] == res["components"]["yoy_trend"]["points"]


def test_score_endpoint(client: TestClient):
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    org = Organization(name="Score API Org", country_code="DE", employee_count=50)
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(
        org_id=org.id,
        email="score_user@test.com",
        password_hash="fake",
        full_name="Score Tester",
        role=UserRole.admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    act = ActivityRecord(
        org_id=org.id, category=ActivityCategory.electricity, amount=Decimal("5000"), unit=Unit.kWh,
        period_start=date(2026, 3, 1), period_end=date(2026, 3, 31)
    )
    db.add(act)
    db.commit()
    db.refresh(act)

    res = EmissionResult(
        activity_id=act.id, scope=Scope.scope_2, method=Scope2Method.location_based,
        kg_co2e=Decimal("1815.0"), is_current=True
    )
    db.add(res)
    db.commit()

    token = create_access_token(subject=user.id, org_id=org.id, role=user.role.value)
    db.close()

    # 1. Unauthorized
    assert client.get("/analytics/score").status_code == 401

    # 2. Authorized
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/analytics/score", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert data["score"] is not None
    assert "components" in data

