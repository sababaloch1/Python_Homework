"""S2 service layer: connects the pure calculation core to the database.

Public interface used by the other subsystems:
  S1 -> S2   calculate_activity(db, activity_id), calculate_reading(db, reading_id)
  S4 -> S2   simulate(db, items), simulate_change(db, before, after)   (never saves)
S3 only reads EmissionResult rows with is_current = True.
"""
import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.app.core.enums import ActivityCategory, Scope, Scope2Method
from api.app.core.models import (
    ActivityRecord, Asset, EmissionResult, Facility, MeterReading, Organization,
)
from api.app.engine import repository
from api.app.engine.core import (
    Activity, EmissionError, Factor, Tariff, calculate, calculate_cost,
    round_for_display, select_factor, select_tariff,
)
from api.app.engine.core.calculator import to_decimal

log = logging.getLogger(__name__)
_CHUNK = 500


# --------------------------------------------------------------------------- helpers
@dataclass
class Computed:
    """Result of one calculation, independent of the ORM (so simulate never touches the DB)."""
    ok: bool
    kg_co2e: Optional[Decimal]
    cost_eur: Optional[Decimal]
    scope: Optional[str]
    method: Optional[str]
    factor_id: Optional[str]
    trace: dict = field(default_factory=dict)


@dataclass
class _Context:
    factors: List[Factor]
    tariffs: List[Tariff]


def _context(db: Session, category: str) -> _Context:
    return _Context(repository.load_active_factors(db, category), repository.load_tariffs(db, category))


def _region(facility_country: Optional[str], org_country: Optional[str]) -> str:
    return (facility_country or org_country or "").strip().upper()


def _compute(ctx: _Context, category: Optional[str], amount, unit: str, region: str, year: int) -> Computed:
    base = {"category": category, "amount": str(amount), "unit": unit, "region": region, "year": year}
    try:
        if not category:
            raise EmissionError("Record has no category")
        if not region:
            raise EmissionError("No country for this record: set the facility country (or the organisation country)")
        activity = Activity(category=category, amount=to_decimal(amount), unit=unit, region=region, year=year)
        factor = select_factor(ctx.factors, category, region, year)
        result = calculate(activity, factor)
    except EmissionError as exc:  # NFR-2.10: reported on the record, never stored as zero
        return Computed(False, None, None, None, None, None,
                        {**base, "error": str(exc), "error_type": type(exc).__name__})

    trace = dict(result.trace)
    cost: Optional[Decimal] = None
    tariff = select_tariff(ctx.tariffs, category, region, year)
    if tariff is None:
        trace["cost"] = {"note": "no tariff found; cost not calculated"}
    else:
        try:
            cost_full = calculate_cost(activity, tariff)
            cost = round_for_display(cost_full, 2)     # cost_eur column is NUMERIC(12,2)
            trace["cost"] = {
                "tariff_id": tariff.id, "tariff_region": tariff.region, "tariff_year": tariff.year,
                "eur_per_unit": str(tariff.eur_per_unit), "tariff_unit": tariff.unit,
                "cost_eur_full_precision": str(cost_full), "cost_eur": str(cost),
            }
        except EmissionError as exc:
            trace["cost"] = {"note": f"cost not calculated: {exc}"}
    return Computed(True, result.kg_co2e, cost, result.scope, result.method, result.factor_id, trace)


def _compute_market(green: List[Factor], category: Optional[str], amount, unit: str, year: int) -> Optional[Computed]:
    """FR-2.07: market-based Scope 2 from the facility's green-tariff factor.
    Returns None when the facility has no green tariff (or the record is not electricity).
    Cost stays on the location-based result so money is never counted twice."""
    if category != "electricity" or not green:
        return None
    base = {"category": category, "amount": str(amount), "unit": unit, "year": year, "method": "market_based"}
    try:
        activity = Activity(category=category, amount=to_decimal(amount), unit=unit,
                            region=repository.GREEN_REGION, year=year)
        factor = select_factor(green, category, repository.GREEN_REGION, year)
        result = calculate(activity, factor, method="market_based")
    except EmissionError as exc:
        return Computed(False, None, None, "scope_2", "market_based", None,
                        {**base, "error": str(exc), "error_type": type(exc).__name__})
    trace = dict(result.trace)
    trace.update({"method": "market_based", "green_tariff_id": factor.id,
                  "cost": {"note": "cost is stored on the location-based result"}})
    # factor_id stays empty: the green tariff is not a row of emission_factors (foreign key)
    return Computed(True, result.kg_co2e, None, "scope_2", "market_based", None, trace)


def _to_row(c: Computed, activity_id=None, reading_id=None) -> EmissionResult:
    return EmissionResult(
        activity_id=activity_id,
        reading_id=reading_id,
        factor_id=uuid.UUID(c.factor_id) if c.factor_id else None,
        scope=Scope(c.scope) if c.scope else None,
        method=Scope2Method(c.method) if c.method else None,
        kg_co2e=c.kg_co2e,
        cost_eur=c.cost_eur,
        trace=c.trace,
        is_current=True,
    )


def _chunks(items: list, n: int = _CHUNK):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _retire(db: Session, *, activity_ids: Iterable = (), reading_ids: Iterable = ()) -> None:
    """Mark old results as history (FR-2.08). Rows are kept, never deleted."""
    for chunk in _chunks(list(activity_ids)):
        db.execute(update(EmissionResult)
                   .where(EmissionResult.activity_id.in_(chunk), EmissionResult.is_current.is_(True))
                   .values(is_current=False))
    for chunk in _chunks(list(reading_ids)):
        db.execute(update(EmissionResult)
                   .where(EmissionResult.reading_id.in_(chunk), EmissionResult.is_current.is_(True))
                   .values(is_current=False))


# --------------------------------------------------------------------------- queries
def _activity_query():
    return (
        select(ActivityRecord, Facility.country_code.label("fac_cc"), Organization.country_code.label("org_cc"),
               ActivityRecord.facility_id.label("fac_id"))
        .outerjoin(Facility, ActivityRecord.facility_id == Facility.id)
        .outerjoin(Organization, ActivityRecord.org_id == Organization.id)
    )


def _reading_query():
    return (
        select(MeterReading, Facility.country_code.label("fac_cc"), Organization.country_code.label("org_cc"),
               Asset.facility_id.label("fac_id"))
        .join(Asset, MeterReading.asset_id == Asset.id)
        .outerjoin(Facility, Asset.facility_id == Facility.id)
        .outerjoin(Organization, MeterReading.org_id == Organization.id)
    )


def _compute_activity_rows(db: Session, rows) -> int:
    """Calculate many activities with ONE factor/tariff load per category (NFR-2.04)."""
    contexts: Dict[str, _Context] = {}
    green = repository.load_green_factors(db, [r[3] for r in rows])
    new_rows, ids = [], []
    for activity, fac_cc, org_cc, fac_id in rows:
        category = repository.enum_value(activity.category)
        if category not in contexts:
            contexts[category] = _context(db, category)
        unit = repository.enum_value(activity.unit)
        year = activity.period_start.year
        c = _compute(contexts[category], category, activity.amount, unit, _region(fac_cc, org_cc), year)
        new_rows.append(_to_row(c, activity_id=activity.id))
        m = _compute_market(green.get(str(fac_id), []), category, activity.amount, unit, year)
        if m is not None:
            new_rows.append(_to_row(m, activity_id=activity.id))
        ids.append(activity.id)
    _retire(db, activity_ids=ids)
    db.add_all(new_rows)
    db.commit()
    return len(new_rows)


def _compute_reading_rows(db: Session, rows) -> int:
    contexts: Dict[str, _Context] = {}
    green = repository.load_green_factors(db, [r[3] for r in rows])
    new_rows, ids = [], []
    for reading, fac_cc, org_cc, fac_id in rows:
        category = repository.enum_value(reading.category)
        if category and category not in contexts:
            contexts[category] = _context(db, category)
        unit = repository.enum_value(reading.unit)
        year = reading.recorded_at.year
        c = _compute(contexts.get(category, _Context([], [])), category, reading.value, unit,
                     _region(fac_cc, org_cc), year)
        new_rows.append(_to_row(c, reading_id=reading.id))
        m = _compute_market(green.get(str(fac_id), []), category, reading.value, unit, year)
        if m is not None:
            new_rows.append(_to_row(m, reading_id=reading.id))
        ids.append(reading.id)
    _retire(db, reading_ids=ids)
    db.add_all(new_rows)
    db.commit()
    return len(new_rows)


# --------------------------------------------------------------------------- public API
def calculate_activity(db: Session, activity_id) -> EmissionResult:
    """FR-2.05: calculate and save kg CO2e + cost for one activity record."""
    row = db.execute(_activity_query().where(ActivityRecord.id == activity_id)).first()
    if row is None:
        raise LookupError(f"Activity {activity_id} not found")
    _compute_activity_rows(db, [row])
    return get_current_result(db, activity_id=activity_id)


def calculate_reading(db: Session, reading_id) -> EmissionResult:
    row = db.execute(_reading_query().where(MeterReading.id == reading_id)).first()
    if row is None:
        raise LookupError(f"Reading {reading_id} not found")
    _compute_reading_rows(db, [row])
    rows = db.execute(select(EmissionResult).where(
        EmissionResult.reading_id == reading_id, EmissionResult.is_current.is_(True))).scalars().all()
    rows.sort(key=lambda r: r.method == Scope2Method.market_based)
    return rows[0] if rows else None


def calculate_batch(db: Session, import_batch_id) -> int:
    """Calculate every activity created by one CSV import."""
    rows = db.execute(_activity_query().where(ActivityRecord.import_batch_id == import_batch_id)).all()
    return _compute_activity_rows(db, rows)


def recalculate_category(db: Session, category: str) -> Dict[str, int]:
    """FR-2.08: after a factor/tariff change, recalculate every affected record.
    Old results stay in the table with is_current = False."""
    cat = ActivityCategory(category)
    a_rows = db.execute(_activity_query().where(ActivityRecord.category == cat)).all()
    r_rows = db.execute(_reading_query().where(MeterReading.category == cat)).all()
    return {"activities": _compute_activity_rows(db, a_rows) if a_rows else 0,
            "readings": _compute_reading_rows(db, r_rows) if r_rows else 0}


def recalculate_facility(db: Session, facility_id) -> Dict[str, int]:
    """FR-2.07: after a green tariff is set or removed, recalculate that facility's electricity."""
    cat = ActivityCategory.electricity
    a_rows = db.execute(_activity_query().where(ActivityRecord.facility_id == facility_id,
                                                ActivityRecord.category == cat)).all()
    r_rows = db.execute(_reading_query().where(Asset.facility_id == facility_id,
                                               MeterReading.category == cat)).all()
    return {"activities": _compute_activity_rows(db, a_rows) if a_rows else 0,
            "readings": _compute_reading_rows(db, r_rows) if r_rows else 0}


def retire_activity_results(db: Session, activity_id) -> None:
    """Call before an activity is deleted so S3 stops counting its emissions."""
    _retire(db, activity_ids=[activity_id])
    db.commit()


def get_current_result(db: Session, *, activity_id) -> Optional[EmissionResult]:
    """The main result (location-based for electricity). The market-based one is a second row."""
    rows = db.execute(select(EmissionResult).where(
        EmissionResult.activity_id == activity_id, EmissionResult.is_current.is_(True))).scalars().all()
    rows.sort(key=lambda r: r.method == Scope2Method.market_based)
    return rows[0] if rows else None


def get_results(db: Session, activity_id, include_history: bool = False) -> List[EmissionResult]:
    q = select(EmissionResult).where(EmissionResult.activity_id == activity_id)
    if not include_history:
        q = q.where(EmissionResult.is_current.is_(True))
    return list(db.execute(q.order_by(EmissionResult.calculated_at.desc())).scalars().all())


# Safe wrappers for S1's save endpoints: a calculation problem must never break saving data.
def safe_calculate_activity(db: Session, activity_id) -> None:
    try:
        calculate_activity(db, activity_id)
    except Exception:
        db.rollback()
        log.exception("S2 calculation failed for activity %s", activity_id)


def safe_calculate_reading(db: Session, reading_id) -> None:
    try:
        calculate_reading(db, reading_id)
    except Exception:
        db.rollback()
        log.exception("S2 calculation failed for reading %s", reading_id)


def safe_calculate_batch(db: Session, import_batch_id) -> None:
    try:
        calculate_batch(db, import_batch_id)
    except Exception:
        db.rollback()
        log.exception("S2 calculation failed for import batch %s", import_batch_id)


# --------------------------------------------------------------------------- simulate (FR-2.10)
def simulate(db: Session, items: List[dict]) -> dict:
    """Projected emissions for hypothetical activities. Reads factors, WRITES NOTHING.

    item = {"category", "amount", "unit", "region", "year", "label" (optional)}
    """
    contexts: Dict[str, _Context] = {}
    out, total_kg, total_cost, errors = [], Decimal("0"), Decimal("0"), 0
    for item in items:
        category = repository.enum_value(item["category"])
        if category not in contexts:
            contexts[category] = _context(db, category)
        region = str(item["region"]).strip().upper()
        c = _compute(contexts[category], category, item["amount"], repository.enum_value(item["unit"]),
                     region, int(item["year"]))
        entry = {"label": item.get("label"), "category": category, "amount": to_decimal(item["amount"]),
                 "unit": repository.enum_value(item["unit"]), "region": region, "year": int(item["year"]),
                 "kg_co2e": c.kg_co2e, "cost_eur": c.cost_eur, "scope": c.scope,
                 "error": c.trace.get("error")}
        if c.ok:
            total_kg += c.kg_co2e
            total_cost += c.cost_eur or Decimal("0")
        else:
            errors += 1
        out.append(entry)
    return {"items": out, "total_kg_co2e": total_kg, "total_cost_eur": total_cost, "errors": errors}


def simulate_change(db: Session, before: List[dict], after: List[dict]) -> dict:
    """What-if: projected saving when `before` is replaced by `after`."""
    b, a = simulate(db, before), simulate(db, after)
    saving = b["total_kg_co2e"] - a["total_kg_co2e"]
    pct = (saving / b["total_kg_co2e"] * Decimal("100")) if b["total_kg_co2e"] else None
    return {"before": b, "after": a, "saving_kg_co2e": saving,
            "saving_pct": pct, "saving_cost_eur": b["total_cost_eur"] - a["total_cost_eur"]}
