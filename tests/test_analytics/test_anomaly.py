from datetime import date
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app.analytics.anomaly import calculate_anomalies, flag_months
from api.app.core.enums import ActivityCategory, Scope, Scope2Method, Unit, UserRole
from api.app.core.models import (
    ActivityRecord,
    EmissionResult,
    Organization,
    User,
)
from api.app.core.security import create_access_token
from seed.seed_activity import seed_activities_and_readings


def test_flag_months_exact_20_percent_boundary():
    """Rule: A month is flagged when > 20% above the average of the previous 3 months.
    Exact 20.0% boundary must NOT be flagged; 20.1% MUST be flagged."""
    # Previous 3 months average = (100 + 100 + 100) / 3 = 100.0
    # Month 4 value = 120.0 (+20.0% exactly -> NOT flagged)
    months_exact_boundary = [
        {"month": "2026-01", "value": 100.0},
        {"month": "2026-02", "value": 100.0},
        {"month": "2026-03", "value": 100.0},
        {"month": "2026-04", "value": 120.0},
    ]
    res_exact = flag_months(months_exact_boundary)
    assert res_exact == []

    # Month 4 value = 120.5 (+20.5% -> flagged!)
    months_above_boundary = [
        {"month": "2026-01", "value": 100.0},
        {"month": "2026-02", "value": 100.0},
        {"month": "2026-03", "value": 100.0},
        {"month": "2026-04", "value": 120.5},
    ]
    res_above = flag_months(months_above_boundary)
    assert len(res_above) == 1
    assert res_above[0]["month"] == "2026-04"
    assert res_above[0]["value"] == 120.5
    assert res_above[0]["average_3m"] == 100.0
    assert res_above[0]["pct_above"] == 20.5


def test_flag_months_fewer_than_4_months():
    """Rule: First 3 months are never flagged. If fewer than 4 months, return []."""
    assert flag_months([]) == []
    assert flag_months([{"month": "2026-01", "value": 100.0}]) == []
    assert flag_months([{"month": "2026-01", "value": 100.0}, {"month": "2026-02", "value": 500.0}]) == []
    assert flag_months([
        {"month": "2026-01", "value": 10.0},
        {"month": "2026-02", "value": 20.0},
        {"month": "2026-03", "value": 300.0},
    ]) == []


def test_flag_months_zero_average():
    """Rule: If previous 3-month average is 0, never flagged (prevents division by zero)."""
    months_zero_avg = [
        {"month": "2026-01", "value": 0.0},
        {"month": "2026-02", "value": 0.0},
        {"month": "2026-03", "value": 0.0},
        {"month": "2026-04", "value": 50.0},
    ]
    res = flag_months(months_zero_avg)
    assert res == []


def test_anomaly_detection_on_seeded_spike(db: Session):
    """Test: Detects the +35% seeded spike month (March 2026) for Demo GmbH."""
    seed_activities_and_readings(db)

    org = db.query(Organization).filter(Organization.name == "Demo GmbH").first()
    assert org is not None

    anomalies = calculate_anomalies(db, org.id)
    assert len(anomalies) == 1
    spike = anomalies[0]
    assert spike["month"] == "2026-03"
    assert spike["pct_above"] >= 30.0  # ~35% spike
    assert spike["value"] > spike["average_3m"]


def test_anomalies_endpoint(client: TestClient):
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    org = Organization(name="Anomaly API Org", country_code="DE")
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(
        org_id=org.id,
        email="anomaly_user@test.com",
        password_hash="fake",
        full_name="Anomaly Tester",
        role=UserRole.admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 4 months of data with a spike in month 4 (April)
    # Months 1-3: 10 t each -> avg = 10 t. Month 4: 15 t (+50% spike)
    for m in range(1, 5):
        val = 15000 if m == 4 else 10000
        act = ActivityRecord(
            org_id=org.id,
            category=ActivityCategory.electricity,
            amount=Decimal("1"),
            unit=Unit.kWh,
            period_start=date(2026, m, 1),
            period_end=date(2026, m, 28),
        )
        db.add(act)
        db.commit()
        db.refresh(act)

        res = EmissionResult(
            activity_id=act.id,
            scope=Scope.scope_2,
            method=Scope2Method.location_based,
            kg_co2e=Decimal(str(val)),
            is_current=True,
        )
        db.add(res)
        db.commit()

    token = create_access_token(subject=user.id, org_id=org.id, role=user.role.value)
    db.close()

    # 1. Unauthorized
    assert client.get("/analytics/anomalies").status_code == 401

    # 2. Authorized
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/analytics/anomalies", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["month"] == "2026-04"
    assert data[0]["value"] == 15.0
    assert data[0]["average_3m"] == 10.0
    assert data[0]["pct_above"] == 50.0

