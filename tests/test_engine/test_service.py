import time
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from api.app.core.enums import ActivityCategory, AssetKind, ReadingSource, Scope, Unit
from api.app.core.models import Asset, EmissionFactor, EmissionResult, MeterReading
from api.app.engine import repository, service

from .helpers import make_activity, make_facility, make_factor, make_org, make_tariff


def test_fr_2_05_saving_an_activity_creates_result_with_cost(db):
    org = make_org(db)
    fac = make_facility(db, org)
    factor = make_factor(db)
    make_tariff(db, eur="0.30")
    act = make_activity(db, org, fac)

    r = service.calculate_activity(db, act.id)

    assert Decimal(str(r.kg_co2e)) == Decimal("4356")          # NFR-2.06 reference example
    assert r.scope == Scope.scope_2 and r.is_current is True
    assert r.factor_id == factor.id
    assert Decimal(str(r.cost_eur)) == Decimal("3600.00")      # 12,000 kWh x 0.30 EUR


def test_fr_2_09_trace_is_stored_with_factor_conversion_and_formula(db):
    org = make_org(db)
    make_factor(db)
    act = make_activity(db, org, make_facility(db, org), amount="12", unit="MWh")
    r = service.calculate_activity(db, act.id)
    t = r.trace
    assert t["factor_source"] == "UBA" and t["factor_year"] == 2024 and t["factor_version"] == 1
    assert t["amount_unit"] == "MWh" and t["factor_unit"] == "kWh" and t["unit_ratio"] == "1000"
    assert "formula" in t and t["cost"]["note"].startswith("no tariff")
    assert Decimal(str(r.kg_co2e)) == Decimal("4356")


def test_fr_2_06_country_falls_back_to_organisation_when_facility_has_none(db):
    org = make_org(db, "DE")
    make_factor(db)
    act = make_activity(db, org, facility=None)
    assert service.calculate_activity(db, act.id).kg_co2e is not None


def test_fr_2_06_uses_nearest_year_and_global_fallback(db):
    org = make_org(db, "FR")
    make_factor(db, region="GLOBAL", year=2020, value="0.5")
    act = make_activity(db, org, make_facility(db, org, "FR"), amount="10")
    r = service.calculate_activity(db, act.id)
    assert Decimal(str(r.kg_co2e)) == Decimal("5")
    assert r.trace["factor_region"] == "GLOBAL"


def test_nfr_2_10_missing_factor_is_reported_never_zero(db):
    org = make_org(db)
    act = make_activity(db, org, make_facility(db, org), category="diesel", unit="litre")
    r = service.calculate_activity(db, act.id)
    assert r.kg_co2e is None and r.factor_id is None
    assert r.trace["error_type"] == "MissingFactorError" and "diesel" in r.trace["error"]


def test_nfr_2_10_unit_that_cannot_be_converted_is_reported(db):
    org = make_org(db)
    make_factor(db, type_="natural_gas", unit="kWh", scope="scope_1")
    act = make_activity(db, org, make_facility(db, org), category="natural_gas", amount="200", unit="m3")
    r = service.calculate_activity(db, act.id)
    assert r.kg_co2e is None and r.trace["error_type"] == "UnknownUnitError"


def test_nfr_2_10_record_without_any_country_is_reported(db):
    org = make_org(db, country=None)
    make_factor(db)
    act = make_activity(db, org)
    assert "country" in service.calculate_activity(db, act.id).trace["error"]


def test_fr_2_08_factor_change_recalculates_and_keeps_history(db):
    org = make_org(db)
    make_factor(db, value="0.363")
    act = make_activity(db, org, make_facility(db, org))
    service.calculate_activity(db, act.id)

    row, status = repository.upsert_factor(db, dict(
        activity_type="electricity", region="DE", year=2024, unit="kWh",
        kg_co2e_per_unit="0.400", scope="scope_2", ghg_category="Test", source="UBA revised"))
    db.commit()
    assert status == "versioned" and row.version == 2
    counts = service.recalculate_category(db, "electricity")
    assert counts == {"activities": 1, "readings": 0}

    current = service.get_results(db, act.id)
    history = service.get_results(db, act.id, include_history=True)
    assert len(current) == 1 and Decimal(str(current[0].kg_co2e)) == Decimal("4800")
    assert len(history) == 2 and sum(1 for h in history if not h.is_current) == 1


def test_nfr_2_08_factors_are_versioned_and_never_hard_deleted(db):
    f1, s1 = repository.upsert_factor(db, dict(activity_type="electricity", region="de", year=2024, unit="kWh",
        kg_co2e_per_unit="0.363", scope="scope_2", ghg_category=None, source="UBA"))
    f2, s2 = repository.upsert_factor(db, dict(activity_type="electricity", region="DE", year=2024, unit="kWh",
        kg_co2e_per_unit="0.363", scope="scope_2", ghg_category=None, source="UBA"))
    assert (s1, s2) == ("created", "unchanged") and f1.id == f2.id and f1.region == "DE"
    repository.upsert_factor(db, dict(activity_type="electricity", region="DE", year=2024, unit="kWh",
        kg_co2e_per_unit="0.370", scope="scope_2", ghg_category=None, source="UBA"))
    repository.deactivate_factor(db, f1.id)
    db.commit()
    rows = db.execute(select(EmissionFactor).order_by(EmissionFactor.version)).scalars().all()
    assert [r.version for r in rows] == [1, 2] and not rows[0].is_active


def test_fr_2_10_simulate_returns_projection_and_writes_nothing(db):
    org = make_org(db)
    make_factor(db)
    make_factor(db, type_="diesel", unit="litre", value="2.5", scope="scope_1")
    before = db.execute(select(func.count()).select_from(EmissionResult)).scalar()

    out = service.simulate(db, [
        {"category": "electricity", "amount": "12000", "unit": "kWh", "region": "de", "year": 2024, "label": "grid"},
        {"category": "diesel", "amount": "100", "unit": "litre", "region": "DE", "year": 2024},
        {"category": "petrol", "amount": "1", "unit": "litre", "region": "DE", "year": 2024},   # no factor
    ])
    assert out["total_kg_co2e"] == Decimal("4606.000") and out["errors"] == 1
    assert out["items"][2]["error"] and out["items"][2]["kg_co2e"] is None
    assert db.execute(select(func.count()).select_from(EmissionResult)).scalar() == before
    assert not db.new and not db.dirty


def test_fr_2_10_simulate_change_reports_saving(db):
    make_factor(db, type_="diesel", unit="litre", value="2.5", scope="scope_1")
    make_factor(db, type_="electricity", unit="kWh", value="0.25", scope="scope_2")
    item = lambda c, a, u: {"category": c, "amount": a, "unit": u, "region": "DE", "year": 2024}
    out = service.simulate_change(db, [item("diesel", "1000", "litre")], [item("electricity", "1000", "kWh")])
    assert out["saving_kg_co2e"] == Decimal("2250.000") and out["saving_pct"] == Decimal("90")


def test_fr_2_05_meter_reading_is_calculated(db):
    org = make_org(db)
    fac = make_facility(db, org)
    make_factor(db)
    asset = Asset(org_id=org.id, facility_id=fac.id, kind=AssetKind.meter, name="M1", code="AST-1")
    db.add(asset)
    db.commit()
    reading = MeterReading(org_id=org.id, asset_id=asset.id, category=ActivityCategory.electricity,
                           value=Decimal("100"), unit=Unit.kWh, recorded_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
                           source=ReadingSource.manual)
    db.add(reading)
    db.commit()
    r = service.calculate_reading(db, reading.id)
    assert Decimal(str(r.kg_co2e)) == Decimal("36.3") and r.reading_id == reading.id


def test_retired_results_are_no_longer_current(db):
    org = make_org(db)
    make_factor(db)
    act = make_activity(db, org, make_facility(db, org))
    service.calculate_activity(db, act.id)
    service.retire_activity_results(db, act.id)
    assert service.get_results(db, act.id) == []
    assert len(service.get_results(db, act.id, include_history=True)) == 1


def test_safe_wrapper_swallows_errors(db):
    import uuid
    service.safe_calculate_activity(db, uuid.uuid4())      # unknown id: must not raise


def test_nfr_2_04_recalculating_10000_records_takes_under_30_seconds(db):
    org = make_org(db)
    fac = make_facility(db, org)
    make_factor(db)
    make_tariff(db)
    from api.app.core.models import ActivityRecord
    db.add_all([ActivityRecord(org_id=org.id, facility_id=fac.id, category=ActivityCategory.electricity,
                               amount=Decimal(1000 + i), unit=Unit.kWh, period_start=date(2024, 1, 1),
                               period_end=date(2024, 1, 31)) for i in range(10_000)])
    db.commit()

    start = time.perf_counter()
    counts = service.recalculate_category(db, "electricity")
    first = time.perf_counter() - start
    start = time.perf_counter()
    service.recalculate_category(db, "electricity")          # second run also retires 10,000 old results
    second = time.perf_counter() - start

    assert counts["activities"] == 10_000
    assert first < 30 and second < 30
    current = db.execute(select(func.count()).select_from(EmissionResult)
                         .where(EmissionResult.is_current.is_(True))).scalar()
    assert current == 10_000
