import io

def test_csv_import_valid(client):
    # Register
    client.post("/auth/register", json={"email": "csv@test.com", "password": "password123", "full_name": "CSV User", "org_name": "CSV Org"})
    login = client.post("/auth/login", data={"username": "csv@test.com", "password": "password123"})
    token = login.json()["access_token"]

    # Create a valid CSV in memory
    csv_content = b"category,amount,unit,period_start,period_end,note\nelectricity,1500,kWh,2026-02-01,2026-02-28,Feb bill\n"
    file = {"file": ("test.csv", io.BytesIO(csv_content), "text/csv")}

    response = client.post("/activities/import", headers={"Authorization": f"Bearer {token}"}, files=file)
    assert response.status_code == 201
    assert response.json()["rows_saved"] == 1

def test_csv_import_invalid_rolls_back(client):
    # Register
    client.post("/auth/register", json={"email": "csvfail@test.com", "password": "password123", "full_name": "CSV Fail", "org_name": "CSV Fail Org"})
    login = client.post("/auth/login", data={"username": "csvfail@test.com", "password": "password123"})
    token = login.json()["access_token"]

    # CSV with a negative amount (should fail)
    csv_content = b"category,amount,unit,period_start,period_end,note\nelectricity,-50,kWh,2026-02-01,2026-02-28,Bad bill\n"
    file = {"file": ("bad.csv", io.BytesIO(csv_content), "text/csv")}

    response = client.post("/activities/import", headers={"Authorization": f"Bearer {token}"}, files=file)
    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "CSV import failed"