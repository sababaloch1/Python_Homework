from decimal import Decimal

import pytest

from api.app.engine.core import (
    Activity, Factor, MissingFactorError, Tariff, UnitConverter, UnknownUnitError,
    calculate, calculate_cost, round_for_display, select_factor,
)
from api.app.engine.core.calculator import to_decimal


def factor(id="f1", type_="electricity", region="DE", year=2024, unit="kWh",
           value="0.363", scope="scope_2", active=True, version=1):
    return Factor(id=id, activity_type=type_, region=region, year=year, unit=unit,
                  kg_co2e_per_unit=Decimal(value), scope=scope, ghg_category="Purchased electricity",
                  source="UBA", version=version, is_active=active)


def act(category="electricity", amount="12000", unit="kWh", region="DE", year=2024):
    return Activity(category=category, amount=Decimal(amount), unit=unit, region=region, year=year)


# ---- NFR-2.06 / FR-2.05: the project's reference example --------------------
def test_nfr_2_06_reference_example():
    result = calculate(act(), factor())
    assert result.kg_co2e == Decimal("4356")          # 12,000 kWh x 0.363
    assert result.scope == "scope_2"
    assert result.method == "location_based"
    assert result.factor_id == "f1"


@pytest.mark.parametrize("amount,unit,value,expected", [
    ("100", "kWh", "0.363", "36.3"),
    ("2", "MWh", "0.363", "726"),            # 2000 kWh
    ("1500", "litre", "2.54", "3810"),
    ("0.5", "tonne", "21", "10.5"),
])
def test_nfr_2_06_hand_calculated_cases_within_0_1_percent(amount, unit, value, expected):
    f = factor(unit=unit if unit != "MWh" else "kWh", value=value, type_="x", scope="scope_1")
    r = calculate(act(category="x", amount=amount, unit=unit), f)
    assert abs(r.kg_co2e - Decimal(expected)) / Decimal(expected) < Decimal("0.001")


def test_nfr_2_06_kg_activity_with_per_tonne_factor():
    f = factor(type_="waste_landfill", unit="tonne", value="21", scope="scope_3")
    r = calculate(act(category="waste_landfill", amount="500", unit="kg"), f)
    assert r.kg_co2e == Decimal("10.5")                    # 500 kg = 0.5 t x 21


# ---- FR-2.03: unit conversion -------------------------------------------------
def test_fr_2_03_mwh_to_kwh_and_back():
    c = UnitConverter()
    assert c.convert(Decimal("2"), "MWh", "kWh")[0] == Decimal("2000")
    assert c.convert(Decimal("500"), "kWh", "MWh")[0] == Decimal("0.5")


def test_fr_2_03_litre_m3_and_kg_tonne():
    c = UnitConverter()
    assert c.convert(Decimal("2"), "m3", "litre")[0] == Decimal("2000")
    assert c.convert(Decimal("3000"), "kg", "tonne")[0] == Decimal("3")


def test_fr_2_03_same_unit_ratio_is_one():
    assert UnitConverter().ratio("kWh", "kWh") == Decimal("1")


def test_nfr_2_10_unknown_unit_raises():
    with pytest.raises(UnknownUnitError):
        UnitConverter().convert(Decimal("1"), "furlong", "kWh")


def test_nfr_2_10_cross_dimension_conversion_is_rejected_not_guessed():
    with pytest.raises(UnknownUnitError):
        UnitConverter().convert(Decimal("1"), "m3", "kWh")


def test_is_known():
    c = UnitConverter()
    assert c.is_known("kWh") and not c.is_known("parsec")


# ---- FR-2.06: factor selection -----------------------------------------------
def test_fr_2_06_exact_match_wins():
    fs = [factor("a", year=2023), factor("b", year=2024), factor("g", region="GLOBAL", year=2024)]
    assert select_factor(fs, "electricity", "DE", 2024).id == "b"


def test_fr_2_06_factor_fallback_to_nearest_year():
    fs = [factor("a", year=2021), factor("b", year=2023)]
    assert select_factor(fs, "electricity", "DE", 2024).id == "b"


def test_fr_2_06_country_beats_global_even_with_worse_year():
    fs = [factor("de", year=2020), factor("g", region="GLOBAL", year=2024)]
    assert select_factor(fs, "electricity", "DE", 2024).id == "de"


def test_fr_2_06_falls_back_to_global():
    fs = [factor("g", region="GLOBAL", year=2023)]
    assert select_factor(fs, "electricity", "FR", 2024).id == "g"


def test_fr_2_06_tie_prefers_earlier_year_deterministically():
    fs = [factor("a", year=2022), factor("b", year=2024)]
    assert select_factor(fs, "electricity", "DE", 2023).id == "a"


def test_nfr_2_08_inactive_factors_are_ignored_and_highest_version_wins():
    fs = [factor("old", active=False, version=1), factor("v2", version=2), factor("v3", version=3)]
    assert select_factor(fs, "electricity", "DE", 2024).id == "v3"


def test_nfr_2_10_missing_factor_is_an_explicit_error():
    with pytest.raises(MissingFactorError):
        select_factor([factor(type_="diesel")], "electricity", "DE", 2024)


# ---- FR-2.09: trace, NFR-2.01: determinism, NFR-2.02: Decimal ----------------
def test_fr_2_09_trace_explains_the_calculation():
    r = calculate(act(amount="2", unit="MWh"), factor())
    t = r.trace
    assert t["factor_id"] == "f1" and t["factor_source"] == "UBA" and t["factor_year"] == 2024
    assert t["amount_unit"] == "MWh" and t["factor_unit"] == "kWh" and t["unit_ratio"] == "1000"
    assert t["converted_amount"] == "2000" and "x 0.363" in t["formula"]
    assert t["kg_co2e"] == "726.000"


def test_nfr_2_01_same_input_same_output():
    assert calculate(act(), factor()) == calculate(act(), factor())


def test_nfr_2_02_results_are_decimal_and_floats_are_rejected():
    assert isinstance(calculate(act(), factor()).kg_co2e, Decimal)
    with pytest.raises(TypeError):
        to_decimal(0.1)
    assert to_decimal("0.1") == Decimal("0.1") and to_decimal(5) == Decimal(5)


def test_nfr_2_02_rounding_only_for_display():
    r = calculate(act(amount="1", unit="kWh"), factor(value="0.3635"))
    assert r.kg_co2e == Decimal("0.3635")                  # full precision kept
    assert round_for_display(r.kg_co2e, 2) == Decimal("0.36")
    assert round_for_display(Decimal("2.345"), 2) == Decimal("2.35")   # half-up


# ---- FR-2.04 / FR-2.07: scope + method ----------------------------------------
def test_fr_2_04_scope_comes_from_the_factor():
    r = calculate(act(category="diesel", unit="litre"), factor(type_="diesel", unit="litre", scope="scope_1", value="2.51"))
    assert r.scope == "scope_1" and r.method is None


def test_fr_2_07_explicit_market_based_method_is_kept():
    r = calculate(act(), factor(value="0"), method="market_based")
    assert r.method == "market_based" and r.kg_co2e == Decimal("0")


# ---- FR-2.05: cost -------------------------------------------------------------
def test_fr_2_05_cost_uses_tariff_with_unit_conversion():
    t = Tariff(id="t1", region="DE", activity_type="electricity", unit="kWh",
               eur_per_unit=Decimal("0.30"), year=2024, source="admin")
    assert calculate_cost(act(amount="2", unit="MWh"), t) == Decimal("600.00")


# ---- tariff selection (cost estimate) -------------------------------------------
def test_fr_2_05_tariff_fallback_and_missing_tariff_is_none():
    from api.app.engine.core import select_tariff
    mk = lambda id, region, year: Tariff(id=id, region=region, activity_type="electricity", unit="kWh",
                                         eur_per_unit=Decimal("0.3"), year=year, source="admin")
    ts = [mk("de22", "DE", 2022), mk("de25", "DE", 2025), mk("g24", "GLOBAL", 2024)]
    assert select_tariff(ts, "electricity", "DE", 2024).id == "de25"      # nearest year
    assert select_tariff(ts, "electricity", "DE", 2023).id == "de22"      # tie 2022/2025? no: 2022 is nearer
    tie = [mk("a", "DE", 2022), mk("b", "DE", 2024)]
    assert select_tariff(tie, "electricity", "DE", 2023).id == "a"        # tie -> earlier year
    assert select_tariff(ts, "electricity", "FR", 2024).id == "g24"       # GLOBAL
    assert select_tariff(ts, "diesel", "DE", 2024) is None
