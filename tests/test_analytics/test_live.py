"""tests/test_analytics/test_live.py - Unit and integration tests for GET /analytics/live (FR-3.09)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from starlette.testclient import TestClient

from api.app.analytics.live import calculate_live_emissions
from api.app.core.enums import ActivityCategory, AssetKind, ReadingSource, Scope, Scope2Method, Unit, UserRole
from api.app.core.models import (
    Asset,
    EmissionResult,
    Facility,
    MeterReading,
    Organization,
    User,
)
from api.app.core.security import create_access_token
from api.app.main import app
from seed.seed_activity import seed_activities_and_readings


def test_calculate_live_emissions_base(db):
    """Test pure calculation logic with today readings, excluding past dates and other orgs."""
    org1 = Organization(name="Org Live 1", country_code="DE")
    org2 = Organization(name="Org Live 2", country_code="DE")
    db.add_all([org1, org2])
    db.commit()

    fac1 = Facility(org_id=org1.id, name="Solar Factory", country_code="DE")
    fac2 = Facility(org_id=org1.id, name="Central Office", country_code="DE")
    fac_other = Facility(org_id=org2.id, name="Other Org Facility", country_code="DE")
    db.add_all([fac1, fac2, fac_other])
    db.commit()

    asset1 = Asset(org_id=org1.id, facility_id=fac1.id, kind=AssetKind.meter, name="Solar Inverter Meter", code="SOL-01")
    asset2 = Asset(org_id=org1.id, facility_id=fac2.id, kind=AssetKind.meter, name="Office Elec Meter", code="OFF-01")
    asset_unassigned = Asset(org_id=org1.id, facility_id=None, kind=AssetKind.meter, name="Mobile Meter", code="MOB-01")
    asset_other = Asset(org_id=org2.id, facility_id=fac_other.id, kind=AssetKind.meter, name="Other Meter", code="OTH-01")
    db.add_all([asset1, asset2, asset_unassigned, asset_other])
    db.commit()

    today = date.today()
    yesterday = today - timedelta(days=1)
    t_today = datetime(today.year, today.month, today.day, 10, 0, 0)
    t_yesterday = datetime(yesterday.year, yesterday.month, yesterday.day, 10, 0, 0)

    # Readings
    r1 = MeterReading(org_id=org1.id, asset_id=asset1.id, category=ActivityCategory.electricity, value=Decimal("1000"), unit=Unit.kWh, recorded_at=t_today, source=ReadingSource.device)
    r2 = MeterReading(org_id=org1.id, asset_id=asset2.id, category=ActivityCategory.electricity, value=Decimal("500"), unit=Unit.kWh, recorded_at=t_today, source=ReadingSource.device)
    r_unassigned = MeterReading(org_id=org1.id, asset_id=asset_unassigned.id, category=ActivityCategory.electricity, value=Decimal("200"), unit=Unit.kWh, recorded_at=t_today, source=ReadingSource.device)
    r_yesterday = MeterReading(org_id=org1.id, asset_id=asset1.id, category=ActivityCategory.electricity, value=Decimal("9999"), unit=Unit.kWh, recorded_at=t_yesterday, source=ReadingSource.device)
    r_other = MeterReading(org_id=org2.id, asset_id=asset_other.id, category=ActivityCategory.electricity, value=Decimal("5000"), unit=Unit.kWh, recorded_at=t_today, source=ReadingSource.device)

    db.add_all([r1, r2, r_unassigned, r_yesterday, r_other])
    db.commit()

    # Emission Results
    er1 = EmissionResult(reading_id=r1.id, kg_co2e=Decimal("363.0"), scope=Scope.scope_2, method=Scope2Method.location_based, is_current=True)
    er2 = EmissionResult(reading_id=r2.id, kg_co2e=Decimal("181.5"), scope=Scope.scope_2, method=Scope2Method.location_based, is_current=True)
    er_unassigned = EmissionResult(reading_id=r_unassigned.id, kg_co2e=Decimal("72.6"), scope=Scope.scope_2, method=Scope2Method.location_based, is_current=True)
    er_yesterday = EmissionResult(reading_id=r_yesterday.id, kg_co2e=Decimal("3630.0"), scope=Scope.scope_2, method=Scope2Method.location_based, is_current=True)
    er_other = EmissionResult(reading_id=r_other.id, kg_co2e=Decimal("1815.0"), scope=Scope.scope_2, method=Scope2Method.location_based, is_current=True)

    db.add_all([er1, er2, er_unassigned, er_yesterday, er_other])
    db.commit()

    live_res = calculate_live_emissions(db, org1.id, target_date=today)
    assert "as_of" in live_res
    facs = {f["name"]: f["t_co2e"] for f in live_res["facilities"]}

    assert facs["Solar Factory"] == 0.363
    assert facs["Central Office"] == 0.1815
    assert facs["Unassigned"] == 0.0726
    # Other org not present
    assert "Other Org Facility" not in facs
    # Total excludes yesterday (3.6300)
    assert sum(facs.values()) == pytest.approx(0.363 + 0.1815 + 0.0726, rel=1e-3)


def test_get_live_endpoint_seeded(db):
    from api.app.core.database import get_db

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    try:
        seed_activities_and_readings(db)
        user = db.query(User).filter(User.email == "user2acc@carbonlens.local").first()
        org_id = user.org_id
        token = create_access_token(subject=str(user.id), org_id=str(org_id), role=user.role.value)
        headers = {"Authorization": f"Bearer {token}"}

        res = client.get("/analytics/live", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "as_of" in data
        assert isinstance(data["facilities"], list)
        assert len(data["facilities"]) == 3
        # Essen Plant, Dortmund HQ, Köln Warehouse
        names = {f["name"] for f in data["facilities"]}
        assert names == {"Dortmund HQ", "Essen Plant", "Köln Warehouse"}
        for f in data["facilities"]:
            assert f["t_co2e"] > 0
    finally:
        app.dependency_overrides.pop(get_db, None)

