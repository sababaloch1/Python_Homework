from fastapi.testclient import TestClient
from api.app.main import app
from api.app.core.security import create_access_token
from api.app.core.models import User, Organization
from api.app.core.enums import UserRole
import uuid

def test_analytics_ping(client: TestClient):
    res = client.get("/analytics/ping")
    assert res.status_code == 200
    assert res.json() == {"ok": True, "service": "S3 Analytics & Reporting"}


def test_analytics_me(client: TestClient):
    from tests.conftest import TestingSessionLocal
    db = TestingSessionLocal()
    org = Organization(name="Acme Corp", employee_count=120)
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(
        org_id=org.id,
        email="sameer@acme.com",
        password_hash="fakehash",
        full_name="Sameer Ghaffar",
        role=UserRole.admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=user.id, org_id=org.id, role=user.role.value)
    db.close()

    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/analytics/me", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "sameer@acme.com"
    assert data["full_name"] == "Sameer Ghaffar"
    assert data["role"] == "admin"
    assert data["org_name"] == "Acme Corp"
    assert data["employee_count"] == 120
