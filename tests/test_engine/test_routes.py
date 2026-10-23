"""API tests (use the shared `client` fixture from tests/conftest.py)."""
import uuid
from decimal import Decimal


def _login(client, email, org="Org", register=True):
    if register:
        client.post("/auth/register", json={"email": email, "password": "password123", "full_name": "T", "org_name": org})
    token = client.post("/auth/login", data={"username": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


FACTOR = {"activity_type": "electricity", "region": "de", "year": 2024, "unit": "kWh",
          "kg_co2e_per_unit": "0.363", "scope": "scope_2", "ghg_category": "Purchased electricity",
          "source": "UBA"}


def test_fr_2_02_admin_manages_factors_and_versions_them(client):
    h = _login(client, f"{uuid.uuid4().hex[:8]}@t.com")
    r1 = client.post("/engine/factors", json=FACTOR, headers=h)
    assert r1.status_code == 201 and r1.json()["version"] >= 1 and r1.json()["region"] == "DE"
    r2 = client.post("/engine/factors", json={**FACTOR, "kg_co2e_per_unit": "0.371"}, headers=h)
    assert r2.json()["version"] == r1.json()["version"] + 1
    listed = client.get("/engine/factors", params={"activity_type": "electricity", "region": "DE", "year": 2024}, headers=h).json()
    assert [f["kg_co2e_per_unit"] for f in listed] == ["0.371000"]
    assert client.delete(f"/engine/factors/{r2.json()['id']}", headers=h).status_code == 204
    all_rows = client.get("/engine/factors", params={"region": "DE", "year": 2024, "include_inactive": True}, headers=h).json()
    assert len(all_rows) >= 2                                   # never hard-deleted


def test_nfr_1_02_contributor_cannot_change_factors(client):
    admin = _login(client, f"{uuid.uuid4().hex[:8]}@t.com")
    email = f"{uuid.uuid4().hex[:8]}@t.com"
    client.post("/users/invite", headers=admin, json={"email": email, "password": "password123",
                                                       "full_name": "C", "role": "contributor"})
    h = _login(client, email, register=False)
    assert client.post("/engine/factors", json=FACTOR, headers=h).status_code == 403
    assert client.get("/engine/factors", headers=h).status_code == 200


def test_fr_2_05_saving_an_activity_triggers_calculation_end_to_end(client):
    h = _login(client, f"{uuid.uuid4().hex[:8]}@t.com")
    client.post("/engine/factors", json={**FACTOR, "region": "XX", "kg_co2e_per_unit": "0.363"}, headers=h)
    fac = client.post("/facilities", headers=h, json={"name": "P", "country_code": "XX"}).json()
    act = client.post("/activities/", headers=h, json={
        "category": "electricity", "amount": "12000", "unit": "kWh", "facility_id": fac["id"],
        "period_start": "2024-03-01", "period_end": "2024-03-31"}).json()
    res = client.get(f"/engine/results/{act['id']}", headers=h).json()
    assert len(res) == 1 and Decimal(res[0]["kg_co2e"]) == Decimal("4356") and res[0]["scope"] == "scope_2"

    client.put(f"/activities/{act['id']}", headers=h, json={
        "category": "electricity", "amount": "1000", "unit": "kWh", "facility_id": fac["id"],
        "period_start": "2024-03-01", "period_end": "2024-03-31"})
    cur = client.get(f"/engine/results/{act['id']}", headers=h).json()
    hist = client.get(f"/engine/results/{act['id']}", params={"include_history": True}, headers=h).json()
    assert Decimal(cur[0]["kg_co2e"]) == Decimal("363") and len(hist) == 2

    assert client.delete(f"/activities/{act['id']}", headers=h).status_code == 204


def test_nfr_2_10_missing_factor_shows_error_on_the_record(client):
    h = _login(client, f"{uuid.uuid4().hex[:8]}@t.com")
    fac = client.post("/facilities", headers=h, json={"name": "P", "country_code": "ZZ"}).json()
    act = client.post("/activities/", headers=h, json={
        "category": "water", "amount": "5", "unit": "m3", "facility_id": fac["id"],
        "period_start": "2024-03-01", "period_end": "2024-03-31"}).json()
    res = client.get(f"/engine/results/{act['id']}", headers=h).json()[0]
    assert res["kg_co2e"] is None and "error" in res["trace"]


def test_tenant_isolation_for_results(client):
    a = _login(client, f"{uuid.uuid4().hex[:8]}@t.com")
    b = _login(client, f"{uuid.uuid4().hex[:8]}@t.com")
    act = client.post("/activities/", headers=a, json={"category": "water", "amount": "1", "unit": "m3",
                                                       "period_start": "2024-01-01", "period_end": "2024-01-31"}).json()
    assert client.get(f"/engine/results/{act['id']}", headers=b).status_code == 404
    assert client.post(f"/engine/calculate/{act['id']}", headers=b).status_code == 404


def test_fr_2_10_simulate_endpoint(client):
    h = _login(client, f"{uuid.uuid4().hex[:8]}@t.com")
    client.post("/engine/factors", json={**FACTOR, "region": "SIM", "kg_co2e_per_unit": "0.5"}, headers=h)
    item = {"category": "electricity", "amount": "100", "unit": "kWh", "region": "sim", "year": 2024}
    out = client.post("/engine/simulate", json={"items": [item]}, headers=h).json()
    assert Decimal(out["total_kg_co2e"]) == Decimal("50") and out["errors"] == 0
    cmp_ = client.post("/engine/simulate/compare", json={"before": [item], "after": [{**item, "amount": "40"}]}, headers=h).json()
    assert Decimal(cmp_["saving_kg_co2e"]) == Decimal("30")


def test_fr_2_02_factor_import_endpoint_reports_row_errors(client):
    h = _login(client, f"{uuid.uuid4().hex[:8]}@t.com")
    bad = b"activity_type,region,year,unit,kg_co2e_per_unit,scope,ghg_category,source\nelectricity,DE,,kWh,0.3,scope_2,x,UBA\n"
    r = client.post("/engine/factors/import", headers=h, files={"file": ("f.csv", bad, "text/csv")})
    assert r.status_code == 400 and r.json()["detail"]["errors"][0]["row"] == 2
    good = b"activity_type,region,year,unit,kg_co2e_per_unit,scope,ghg_category,source\nelectricity,IM,2024,kWh,0.3,scope_2,x,UBA\n"
    ok = client.post("/engine/factors/import", headers=h, files={"file": ("f.csv", good, "text/csv")})
    assert ok.status_code == 200 and ok.json()["created"] == 1
