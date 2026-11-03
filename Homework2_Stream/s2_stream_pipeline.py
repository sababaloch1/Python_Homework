"""Homework 2 - Real-time data processing (S2: Emission Engine, Tuba Jabeen).

Meter readings arrive one by one (a stream). Each reading goes through a pipeline:
    ValidateReading | LookupFactor | CalculateEmission | CalculateCost
Shows: abstract base class, inheritance/polymorphism, operator overloading (|),
iterator protocol (__iter__/__next__) and a generator.
Bad readings are NOT turned into zero: they come out with an 'error' field.

Run:  python s2_stream_pipeline.py
"""
import csv
import random
from abc import ABC, abstractmethod
from decimal import Decimal
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parents[1] / "seed"


def load_rows(name):
    with open(SEED_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


FACTORS = {(r["activity_type"], r["region"]): r for r in load_rows("factors.csv")}
TARIFFS = {(r["activity_type"], r["region"]): r for r in load_rows("tariffs.csv")}
RATIO = {"kWh": 1, "MWh": 1000, "litre": 1, "m3": 1000, "kg": 1, "tonne": 1000}


# --------------------------------------------------------------- processors
class Processor(ABC):
    """One step of the pipeline."""

    @abstractmethod
    def process(self, item):
        """Take a reading (dict) and return it (changed) or None to drop it."""

    def __or__(self, other):                  # operator overloading:  a | b | c
        return Pipeline(self, other)


class Pipeline(Processor):
    def __init__(self, first, second):
        self.first, self.second = first, second

    def process(self, item):
        item = self.first.process(item)
        return None if item is None else self.second.process(item)


class ValidateReading(Processor):
    def process(self, item):
        if item.get("value") is None or item["value"] < 0:
            item["error"] = "invalid value (missing or negative)"
        return item


class LookupFactor(Processor):
    def process(self, item):
        if "error" in item:
            return item
        row = FACTORS.get((item["type"], item.get("region", "DE"))) or FACTORS.get((item["type"], "GLOBAL"))
        if row is None:
            item["error"] = f"no emission factor for '{item['type']}'"
        elif item["unit"] not in RATIO or row["unit"] not in RATIO or \
                (item["unit"] in ("kWh", "MWh")) != (row["unit"] in ("kWh", "MWh")):
            item["error"] = f"unit '{item['unit']}' does not fit factor unit '{row['unit']}'"
        else:
            item["_factor"] = row
        return item


class CalculateEmission(Processor):
    def process(self, item):
        if "error" in item:
            item["kg_co2e"] = None            # unknown, never 0
            return item
        row = item["_factor"]
        amount = Decimal(str(item["value"])) * RATIO[item["unit"]] / RATIO[row["unit"]]
        item["kg_co2e"] = (amount * Decimal(row["kg_co2e_per_unit"])).quantize(Decimal("0.0001"))
        return item


class CalculateCost(Processor):
    def process(self, item):
        item.pop("_factor", None)             # internal helper field, not part of the output
        if "error" in item:
            item["cost_eur"] = None
            return item
        t = TARIFFS.get((item["type"], item.get("region", "DE")))
        if t is None:
            item["cost_eur"] = None           # no tariff -> cost unknown (emissions still valid)
        else:
            amount = Decimal(str(item["value"])) * RATIO[item["unit"]] / RATIO[t["unit"]]
            item["cost_eur"] = (amount * Decimal(t["eur_per_unit"])).quantize(Decimal("0.01"))
        return item


class OnlyOk(Processor):
    """Drops readings with an error (use instead of keeping them)."""

    def process(self, item):
        return None if "error" in item else item


# ------------------------------------------------------------------ stream
class MeterStream:
    """Iterator: pulls readings from a source and pushes them through the pipeline."""

    def __init__(self, source, pipeline):
        self._source = iter(source)
        self._pipeline = pipeline
        self.seen = 0

    def __iter__(self):
        return self

    def __next__(self):
        while True:
            raw = next(self._source)          # StopIteration ends the stream
            self.seen += 1
            out = self._pipeline.process(dict(raw))
            if out is not None:
                return out


def simulated_meter(n=8, seed=1):
    """Generator: yields one fake live reading at a time (like a smart meter)."""
    rng = random.Random(seed)
    for i in range(1, n + 1):
        kind = rng.choice(["electricity", "diesel", "electricity", "unobtainium"])
        unit = "litre" if kind == "diesel" else "kWh"
        value = rng.choice([round(rng.uniform(5, 500), 1), round(rng.uniform(5, 500), 1), -3])
        yield {"id": i, "type": kind, "unit": unit, "value": value, "region": "DE"}


if __name__ == "__main__":
    pipeline = ValidateReading() | LookupFactor() | CalculateEmission() | CalculateCost()
    stream = MeterStream(simulated_meter(), pipeline)
    total = Decimal("0")
    print("id  type          value unit    kg CO2e      EUR     note")
    for r in stream:
        if r["kg_co2e"] is not None:
            total += r["kg_co2e"]
        print(f"{r['id']:<3} {r['type']:<13} {r['value']:>6} {r['unit']:<6} "
              f"{str(r['kg_co2e']):>9} {str(r['cost_eur']):>9}   {r.get('error', '')}")
    print(f"\nreadings seen: {stream.seen}   total (valid only): {total} kg CO2e")

    print("\nSame stream, errors dropped:")
    clean = MeterStream(simulated_meter(), pipeline | OnlyOk())
    print([r["id"] for r in clean])
