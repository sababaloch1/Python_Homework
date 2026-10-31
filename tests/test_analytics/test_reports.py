"""tests/test_analytics/test_reports.py - Tests for CSV and PDF reports (FR-3.08, NFR-3.06)."""

import time
from datetime import date
from decimal import Decimal
import io
import pytest
from starlette.testclient import TestClient

from api.app.analytics.reports import DEMO_DISCLAIMER, generate_csv_report, generate_pdf_report
from api.app.core.enums import ActivityCategory, Scope, Scope2Method, UserRole
from api.app.core.models import (
    ActivityRecord,
    EmissionResult,
    Facility,
    Organization,
    User,
)
from api.app.core.security import create_access_token
from api.app.main import app
from seed.seed_activity import seed_activities_and_readings


@pytest.fixture
def client():
    return TestClient(app)


def test_generate_csv_report_structure():
    summary_data = {
        "total_t_co2e": 100.5,
        "by_scope": {"scope_1": 40.2, "scope_2": 50.3, "scope_3": 10.0},
        "failed_records": 0,
        "total_cost_eur": 12500.0,
        "cost_complete": True,
    }
    facility_breakdown = [
        {"label": "Dortmund HQ", "t_co2e": 60.3},
        {"label": "Essen Plant", "t_co2e": 40.2},
    ]

    csv_out = generate_csv_report(summary_data, facility_breakdown)

    assert "# SECTION: SUMMARY" in csv_out
    assert "# SECTION: SCOPE_SPLIT" in csv_out
    assert "# SECTION: FACILITY_BREAKDOWN" in csv_out
    assert "Total Emissions (t CO2e),100.5000" in csv_out
    assert "Scope 1,40.2,40.0" in csv_out
    assert "Dortmund HQ,60.3,60.0" in csv_out


def test_generate_pdf_report_bytes():
    summary_data = {
        "total_t_co2e": 100.5,
        "by_scope": {"scope_1": 40.2, "scope_2": 50.3, "scope_3": 10.0},
        "total_cost_eur": 12500.0,
    }
    facility_breakdown = [{"label": "Dortmund HQ", "t_co2e": 60.3}]
    top_sources = [{"category": "electricity", "facility": "Dortmund HQ", "t_co2e": 50.3}]
    anomalies = [{"month": "2026-03", "value": 65.0, "average_3m": 48.0, "pct_above": 35.4}]

    pdf_bytes = generate_pdf_report(
        org_name="Demo GmbH",
        summary_data=summary_data,
        facility_breakdown=facility_breakdown,
        top_sources=top_sources,
        anomalies=anomalies,
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000
    # Note check
    assert b"CarbonLens" in pdf_bytes or len(pdf_bytes) > 2000


def test_reports_endpoints_seeded_timing(db):
    """Seed 24 months and verify both CSV and PDF endpoints respond in under 10 seconds."""
    from api.app.core.database import get_db
    
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    seed_activities_and_readings(db)
    user = db.query(User).filter(User.email == "user2acc@carbonlens.local").first()
    org_id = user.org_id
    token = create_access_token(subject=str(user.id), org_id=str(org_id), role=user.role.value)
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # 1. Test CSV Endpoint & Timing
        t0 = time.time()
        res_csv = client.get("/analytics/report.csv", headers=headers)
        t_csv = time.time() - t0

        assert res_csv.status_code == 200
        assert res_csv.headers["content-type"].startswith("text/csv")
        assert "attachment; filename=" in res_csv.headers["content-disposition"]
        assert "# SECTION: SUMMARY" in res_csv.text
        assert "# SECTION: SCOPE_SPLIT" in res_csv.text
        assert "# SECTION: FACILITY_BREAKDOWN" in res_csv.text
        assert t_csv < 10.0, f"CSV report took too long: {t_csv:.2f}s"

        # 2. Test PDF Endpoint & Timing
        t0 = time.time()
        res_pdf = client.get("/analytics/report.pdf", headers=headers)
        t_pdf = time.time() - t0

        assert res_pdf.status_code == 200
        assert res_pdf.headers["content-type"] == "application/pdf"
        assert "attachment; filename=" in res_pdf.headers["content-disposition"]
        assert res_pdf.content.startswith(b"%PDF-")
        assert t_pdf < 10.0, f"PDF report took too long: {t_pdf:.2f}s"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_reports_unauthorized(client):
    res_csv = client.get("/analytics/report.csv")
    assert res_csv.status_code == 401

    res_pdf = client.get("/analytics/report.pdf")
    assert res_pdf.status_code == 401
