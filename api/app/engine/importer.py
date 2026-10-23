"""CSV import for emission factors and tariffs (FR-2.02). Atomic: all rows are saved or none."""
import csv
import io
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Dict, List

from sqlalchemy.orm import Session

from api.app.core.enums import ActivityCategory, Scope, Unit
from api.app.engine import repository, service

log = logging.getLogger(__name__)

FACTOR_COLUMNS = ["activity_type", "region", "year", "unit", "kg_co2e_per_unit", "scope", "ghg_category", "source"]
TARIFF_COLUMNS = ["activity_type", "region", "year", "unit", "eur_per_unit", "source"]


def _enum(cls, value: str, field: str):
    try:
        return cls((value or "").strip())
    except ValueError:
        raise ValueError(f"{field}: '{value}' is not valid (allowed: {', '.join(e.value for e in cls)})")


def _decimal(value: str, field: str) -> Decimal:
    try:
        d = Decimal((value or "").strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"{field}: '{value}' is not a number")
    if not d.is_finite() or d < 0:
        raise ValueError(f"{field}: must be a number >= 0")
    return d


def _common(row: dict) -> dict:
    region = (row.get("region") or "").strip().upper()
    if not 2 <= len(region) <= 8:
        raise ValueError("region: use an ISO country code (e.g. DE) or GLOBAL")
    try:
        year = int((row.get("year") or "").strip())
    except ValueError:
        raise ValueError("year: required, e.g. 2024")          # NFR-2.05
    if not 1990 <= year <= 2100:
        raise ValueError("year: must be between 1990 and 2100")
    source = (row.get("source") or "").strip()
    if not source:
        raise ValueError("source: required")                    # NFR-2.05
    return {"activity_type": _enum(ActivityCategory, row.get("activity_type"), "activity_type"),
            "region": region, "year": year, "unit": _enum(Unit, row.get("unit"), "unit"), "source": source}


def _parse_factor(row: dict) -> dict:
    data = _common(row)
    data["kg_co2e_per_unit"] = _decimal(row.get("kg_co2e_per_unit"), "kg_co2e_per_unit")
    data["scope"] = _enum(Scope, row.get("scope"), "scope")
    data["ghg_category"] = (row.get("ghg_category") or "").strip() or None
    return data


def _parse_tariff(row: dict) -> dict:
    data = _common(row)
    data["eur_per_unit"] = _decimal(row.get("eur_per_unit"), "eur_per_unit")
    return data


def _read(text: str, required: List[str]):
    text = text.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    reader.fieldnames = [(f or "").strip() for f in (reader.fieldnames or [])]
    missing = [c for c in required if c not in reader.fieldnames]
    return reader, missing


def _import(db: Session, text: str, required: List[str], parse: Callable, upsert: Callable) -> Dict:
    reader, missing = _read(text, required)
    if missing:
        return {"status": "failed", "errors": [{"row": 1, "error": f"Missing columns: {', '.join(missing)}"}]}
    parsed, errors = [], []
    for i, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        try:
            parsed.append(parse(row))
        except ValueError as exc:
            errors.append({"row": i, "error": str(exc)})
    if errors:
        return {"status": "failed", "errors": errors}          # nothing saved
    counts = {"created": 0, "versioned": 0, "updated": 0, "unchanged": 0}
    changed = set()
    try:
        for data in parsed:
            _, st = upsert(db, data)
            counts[st] += 1
            if st != "unchanged":
                changed.add(data["activity_type"].value)
        db.commit()
    except Exception:
        db.rollback()
        raise
    recalculated = {c: service.recalculate_category(db, c) for c in sorted(changed)}
    return {"status": "completed", "rows": len(parsed), **counts, "recalculated": recalculated, "errors": []}


def import_factors_text(db: Session, text: str) -> Dict:
    return _import(db, text, FACTOR_COLUMNS, _parse_factor, repository.upsert_factor)


def import_tariffs_text(db: Session, text: str) -> Dict:
    return _import(db, text, TARIFF_COLUMNS, _parse_tariff, repository.upsert_tariff)


def load_seed_files(db: Session, directory: Path) -> None:
    """Idempotent: used by seed/run_seed.py on every container start."""
    for name, fn in (("factors.csv", import_factors_text), ("tariffs.csv", import_tariffs_text)):
        path = Path(directory) / name
        if not path.exists():
            continue
        result = fn(db, path.read_text(encoding="utf-8-sig"))
        if result["status"] == "failed":
            log.warning("[seed] %s rejected: %s", name, result["errors"])
            print(f"[seed] WARNING {name} rejected: {result['errors']}")
        else:
            print(f"[seed] {name}: {result['created']} created, {result['versioned']} versioned, "
                  f"{result.get('updated', 0)} updated, {result['unchanged']} unchanged")
