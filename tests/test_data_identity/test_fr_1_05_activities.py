def test_create_activity(client):
    # Register (password must be at least 6 characters!)
    client.post("/auth/register", json={"email": "act@test.com", "password": "password123", "full_name": "Act User", "org_name": "Act Org"})
    login = client.post("/auth/login", data={"username": "act@test.com", "password": "password123"})
    token = login.json()["access_token"]

    # Create Activity
    response = client.post("/activities/", headers={"Authorization": f"Bearer {token}"}, json={
        "category": "electricity",
        "amount": 100,
        "unit": "kWh",
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
        "note": "Test"
    })
    assert response.status_code == 201
    assert response.json()["category"] == "electricity"

def test_get_activities(client):
    # Register
    client.post("/auth/register", json={"email": "getact@test.com", "password": "password123", "full_name": "Get User", "org_name": "Get Org"})
    login = client.post("/auth/login", data={"username": "getact@test.com", "password": "password123"})
    token = login.json()["access_token"]

    # Get Activities (empty at first)
    response = client.get("/activities/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert type(response.json()) == list