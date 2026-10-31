"""tests/test_analytics/test_cache.py - Tests for in-memory cache and speed requirements (NFR-3.10, NFR-3.01)."""

import time
from unittest.mock import MagicMock
import pytest
from starlette.testclient import TestClient

from api.app.analytics.breakdown import calculate_breakdown
from api.app.analytics.cache import analytics_cache
from api.app.analytics.sources import calculate_top_sources
from api.app.analytics.summary import calculate_summary
from api.app.analytics.trend import calculate_trend
from api.app.core.models import User
from api.app.core.security import create_access_token
from api.app.main import app
from seed.seed_activity import seed_activities_and_readings


@pytest.fixture(autouse=True)
def clear_cache():
    analytics_cache.clear()
    yield
    analytics_cache.clear()


def test_cache_avoids_db_on_second_call(db):
    """Test that a second invocation returns cached data without touching the DB."""
    seed_activities_and_readings(db)
    user = db.query(User).filter(User.email == "user2acc@carbonlens.local").first()
    org_id = user.org_id

    # 1. First call - should query db and cache
    res1 = calculate_summary(db, org_id)
    assert analytics_cache.hits == 0
    assert analytics_cache.misses == 1

    # 2. Second call with a mock DB that would raise if touched
    mock_db = MagicMock()
    mock_db.execute.side_effect = RuntimeError("DB should not be accessed on cache hit!")
    res2 = calculate_summary(mock_db, org_id)

    assert analytics_cache.hits == 1
    assert res1 == res2


def test_cache_works_for_all_four_functions(db):
    seed_activities_and_readings(db)
    user = db.query(User).filter(User.email == "user2acc@carbonlens.local").first()
    org_id = user.org_id

    mock_db = MagicMock()
    mock_db.execute.side_effect = RuntimeError("DB hit error!")

    # Summary
    calculate_summary(db, org_id)
    s2 = calculate_summary(mock_db, org_id)
    assert "total_t_co2e" in s2

    # Trend
    calculate_trend(db, org_id)
    t2 = calculate_trend(mock_db, org_id)
    assert "months" in t2

    # Breakdown
    calculate_breakdown(db, org_id, by="facility")
    b2 = calculate_breakdown(mock_db, org_id, by="facility")
    assert isinstance(b2, list)

    # Top sources
    calculate_top_sources(db, org_id, limit=5)
    ts2 = calculate_top_sources(mock_db, org_id, limit=5)
    assert isinstance(ts2, list)

    assert analytics_cache.hits == 4


def test_dashboard_endpoints_speed_under_3_seconds(db):
    """NFR-3.01: Test that all four dashboard endpoints together respond under 3 seconds on seed data."""
    from api.app.core.database import get_db

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    try:
        seed_activities_and_readings(db)
        user = db.query(User).filter(User.email == "user2acc@carbonlens.local").first()
        org_id = user.org_id
        token = create_access_token(subject=str(user.id), org_id=str(org_id), role=user.role.value)
        headers = {"Authorization": f"Bearer {token}"}

        t0 = time.time()
        r_sum = client.get("/analytics/summary", headers=headers)
        r_trend = client.get("/analytics/trend", headers=headers)
        r_break = client.get("/analytics/breakdown?by=facility", headers=headers)
        r_sources = client.get("/analytics/top-sources?limit=5", headers=headers)
        elapsed = time.time() - t0

        assert r_sum.status_code == 200
        assert r_trend.status_code == 200
        assert r_break.status_code == 200
        assert r_sources.status_code == 200
        assert elapsed < 3.0, f"Four dashboard endpoints took {elapsed:.3f}s (must be < 3.0s)"
    finally:
        from tests.conftest import override_get_db
        app.dependency_overrides[get_db] = override_get_db
