"""FR-2.07: market-based Scope 2 from a facility's green-tariff factor."""
import uuid
from decimal import Decimal

from sqlalchemy import select

from api.app.core.enums import Scope2Method
from api.app.core.models import EmissionResult
from api.app.engine import repository, service

from .helpers import make_activity, make_facility, make_factor, make_org, make_tariff
from .test_routes import _login


def _current(db, activity_id):
    return {r.method: r for r in db.execute(select(EmissionResult).where(
        EmissionResult.activity_id == activity_id, EmissionResult.is_current.is_(True))).scalars()}


def _green(db, fac, year=2024, kg="0.020", source="Supplier certificate"):
    row, _ = repository.upsert_green_tariff(db, fac.id, {"year": year, "kg_co2e_per_kwh": kg,
                                                         "supplier": "GreenPower", "source": source})
    db.commit()
    return row


def test_fr_2_07_without_green_tariff_only_location_based(db):
    org = make_org(db); fac = make_facility(db, org); make_factor(db)
    act = make_activity(db, org, fac)
    service.calculate_activity(db, act.id)
    cur = _current(db, act.id)
    assert list(cur) == [Scope2Method.location_based]
    assert Decimal(str(cur[Scope2Method.location_based].kg_co2e)) == Decimal("4356")


def test_fr_2_07_green_tariff_adds_market_based_result(db):
    org = make_org(db); fac = make_facility(db, org); make_factor(db); make_tariff(db, eur="0.30")
    _green(db, fac)
    act = make_activity(db, org, fac)                       # 12,000 kWh
    main = service.calculate_activity(db, act.id)
    cur = _current(db, act.id)
    assert set(cur) == {Scope2Method.location_based, Scope2Method.market_based}
    assert Decimal(str(cur[Scope2Method.location_based].kg_co2e)) == Decimal("4356")
    mk = cur[Scope2Method.market_based]
    assert Decimal(str(mk.kg_co2e)) == Decimal("240")       # 12,000 x 0.020
    assert mk.cost_eur is None and mk.factor_id is None     # cost never counted twice
    assert mk.trace["method"] == "market_based" and mk.trace["factor_source"] == "Supplier certificate"
    assert main.method == Scope2Method.location_based       # the main result stays location-based


def test_fr_2_07_other_facility_is_not_affected(db):
    org = make_org(db); a = make_facility(db, org); b = make_facility(db, org); make_factor(db)
    _green(db, a)
    act = make_activity(db, org, b)
    service.calculate_activity(db, act.id)
    assert list(_current(db, act.id)) == [Scope2Method.location_based]


def test_fr_2_07_non_electricity_has_no_market_based(db):
    org = make_org(db); fac = make_facility(db, org)
    make_factor(db, type_="natural_gas", unit="m3", value="2.02633", scope="scope_1")
    _green(db, fac)
    act = make_activity(db, org, fac, category="natural_gas", amount="100", unit="m3")
    service.calculate_activity(db, act.id)
    assert list(_current(db, act.id)) == [None]


def test_fr_2_08_green_tariff_change_recalculates_and_keeps_history(db):
    org = make_org(db); fac = make_facility(db, org); make_factor(db)
    act = make_activity(db, org, fac)
    service.calculate_activity(db, act.id)
    _green(db, fac, kg="0.020")
    service.recalculate_facility(db, fac.id)
    _green(db, fac, kg="0.050", source="New certificate")           # version 2
    service.recalculate_facility(db, fac.id)
    cur = _current(db, act.id)
    assert Decimal(str(cur[Scope2Method.market_based].kg_co2e)) == Decimal("600")
    rows = repository.list_green_tariffs(db, fac.id, include_inactive=True)
    assert [(r.version, r.is_active) for r in rows] == [(2, True), (1, False)]
    old = db.execute(select(EmissionResult).where(EmissionResult.activity_id == act.id,
                                                  EmissionResult.is_current.is_(False))).scalars().all()
    assert len(old) >= 3                                            # earlier results kept (FR-2.08)


def test_fr_2_07_removing_green_tariff_removes_market_based(db):
    org = make_org(db); fac = make_facility(db, org); make_factor(db)
    _green(db, fac)
    act = make_activity(db, org, fac)
    service.calculate_activity(db, act.id)
    assert Scope2Method.market_based in _current(db, act.id)
    repository.deactivate_green_tariffs(db, fac.id); db.commit()
    service.recalculate_facility(db, fac.id)
    assert list(_current(db, act.id)) == [Scope2Method.location_based]


def test_fr_2_07_nearest_year_is_used_for_green_tariff(db):
    org = make_org(db); fac = make_facility(db, org); make_factor(db)
    _green(db, fac, year=2022, kg="0.030")
    act = make_activity(db, org, fac)                                # period 2024
    service.calculate_activity(db, act.id)
    assert Decimal(str(_current(db, act.id)[Scope2Method.market_based].kg_co2e)) == Decimal("360")


def test_fr_2_03_miles_activity_end_to_end(db):
    org = make_org(db); fac = make_facility(db, org)
    make_factor(db, type_="fleet_km", unit="km", value="0.16591", scope="scope_1")
    act = make_activity(db, org, fac, category="fleet_km", amount="100", unit="miles")
    r = service.calculate_activity(db, act.id)
    assert Decimal(str(r.kg_co2e)) == Decimal("26.7006")             # 160.9344 km x 0.16591, stored as NUMERIC(16,4)


# ------------------------------------------------------------------ API
def _setup_facility(client, h):
    return client.post("/facilities", json={"name": "Plant", "city": "Berlin", "country_code": "DE"}, headers=h).json()["id"]


BODY = {"year": 2024, "kg_co2e_per_kwh": "0.020", "supplier": "GreenPower", "source": "Supplier certificate"}


def test_fr_2_07_api_admin_sets_and_removes_green_tariff(client):
    h = _login(client, f"{uuid.uuid4().hex[:8]}@t.com")
    fid = _setup_facility(client, h)
    r = client.put(f"/engine/facilities/{fid}/green-tariff", json=BODY, headers=h)
    assert r.status_code == 200 and r.json()["version"] == 1
    r2 = client.put(f"/engine/facilities/{fid}/green-tariff", json={**BODY, "kg_co2e_per_kwh": "0.03"}, headers=h)
    assert r2.json()["version"] == 2
    assert len(client.get(f"/engine/facilities/{fid}/green-tariff", headers=h).json()) == 1
    assert client.delete(f"/engine/facilities/{fid}/green-tariff", headers=h).status_code == 204
    assert client.get(f"/engine/facilities/{fid}/green-tariff", headers=h).json() == []


def test_fr_2_07_api_source_is_required(client):
    h = _login(client, f"{uuid.uuid4().hex[:8]}@t.com")
    fid = _setup_facility(client, h)
    bad = {k: v for k, v in BODY.items() if k != "source"}
    assert client.put(f"/engine/facilities/{fid}/green-tariff", json=bad, headers=h).status_code == 422


def test_nfr_1_02_green_tariff_other_org_gets_404_and_contributor_403(client):
    admin = _login(client, f"{uuid.uuid4().hex[:8]}@t.com")
    fid = _setup_facility(client, admin)
    other = _login(client, f"{uuid.uuid4().hex[:8]}@t.com")
    assert client.put(f"/engine/facilities/{fid}/green-tariff", json=BODY, headers=other).status_code == 404
    assert client.get(f"/engine/facilities/{fid}/green-tariff", headers=other).status_code == 404
    email = f"{uuid.uuid4().hex[:8]}@t.com"
    client.post("/users/invite", headers=admin, json={"email": email, "password": "password123",
                                                       "full_name": "C", "role": "contributor"})
    c = _login(client, email, register=False)
    assert client.put(f"/engine/facilities/{fid}/green-tariff", json=BODY, headers=c).status_code == 403
