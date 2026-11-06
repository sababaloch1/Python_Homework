"""Enterprise carbon footprint stream pipeline.

The emission factors below are demonstration values for this homework. A
production tracker should replace them with documented, jurisdiction-specific
factors and record the source and version of each factor.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, Optional


Event = Dict[str, Any]


class StreamProcessor(ABC):
    """Contract for every step in the event-processing pipeline."""

    @abstractmethod
    def process(self, event: Event) -> Optional[Event]:
        """Transform an event, or return ``None`` to drop it."""

    def __or__(self, other: "StreamProcessor") -> "Pipeline":
        """Compose processors with ``processor_a | processor_b``."""
        return Pipeline(self, other)


class Pipeline(StreamProcessor):
    """A processor made by composing two other processors."""

    def __init__(self, first: StreamProcessor, second: StreamProcessor) -> None:
        self.first = first
        self.second = second

    def process(self, event: Event) -> Optional[Event]:
        result = self.first.process(event)
        return None if result is None else self.second.process(result)


class ScopeFilter(StreamProcessor):
    """Keep only events tagged with the requested GHG Protocol scope."""

    VALID_SCOPES = {"scope_1", "scope_2", "scope_3"}

    def __init__(self, target_scope: str) -> None:
        if target_scope not in self.VALID_SCOPES:
            raise ValueError("target_scope must be 'scope_1', 'scope_2', or 'scope_3'")
        self.target_scope = target_scope

    def process(self, event: Event) -> Optional[Event]:
        return event if event.get("scope") == self.target_scope else None


@dataclass(frozen=True)
class EmissionFactor:
    """Factor expressed as metric tons CO2e per activity unit."""

    activity_type: str
    unit: str
    tonnes_co2e_per_unit: float


class EmissionCalculator(StreamProcessor):
    """Convert activity quantities into metric tons of CO2e."""

    # Demo factors: tonnes CO2e per unit of activity.
    FACTORS = {
        "business_flight": EmissionFactor("business_flight", "passenger_km", 0.00015),
        "freight": EmissionFactor("freight", "tonne_km", 0.00009),
        "purchased_goods": EmissionFactor("purchased_goods", "kg", 0.0008),
        "electricity": EmissionFactor("electricity", "kWh", 0.000363),
        "diesel": EmissionFactor("diesel", "litre", 0.00268),
    }

    def process(self, event: Event) -> Optional[Event]:
        activity_type = event.get("activity_type")
        factor = self.FACTORS.get(activity_type)
        if factor is None:
            # Unknown activities are retained for observability, but not
            # incorrectly reported as zero emissions.
            event["error"] = f"no Scope 3 factor for {activity_type!r}"
            event["emissions_t_co2e"] = None
            return event

        if event.get("unit") != factor.unit or event.get("amount", 0) < 0:
            event["error"] = "invalid activity unit or negative amount"
            event["emissions_t_co2e"] = None
            return event

        event["emissions_t_co2e"] = round(
            float(event["amount"]) * factor.tonnes_co2e_per_unit, 6
        )
        return event


class ValidEventsOnly(StreamProcessor):
    """Drop events that could not be calculated."""

    def process(self, event: Event) -> Optional[Event]:
        return None if event.get("error") else event


class TelemetryStream(Iterator[Event]):
    """Pull events from any iterable and expose processed events as an iterator."""

    def __init__(self, source: Iterable[Event], pipeline: StreamProcessor) -> None:
        self._source = iter(source)
        self._pipeline = pipeline
        self.events_seen = 0

    def __iter__(self) -> "TelemetryStream":
        return self

    def __next__(self) -> Event:
        while True:
            raw_event = next(self._source)
            self.events_seen += 1
            processed = self._pipeline.process(dict(raw_event))
            if processed is not None:
                return processed


def live_telemetry() -> Iterator[Event]:
    """Generator simulating events arriving from operational systems."""
    yield {"id": 1, "source": "fuel_storage", "scope": "scope_1", "activity_type": "diesel",
           "amount": 100, "unit": "litre"}
    yield {"id": 2, "source": "travel", "scope": "scope_3", "activity_type": "business_flight",
           "amount": 1200, "unit": "passenger_km"}
    yield {"id": 3, "source": "data_center", "scope": "scope_2", "activity_type": "electricity",
           "amount": 5000, "unit": "kWh"}
    yield {"id": 4, "source": "logistics", "scope": "scope_3", "activity_type": "freight",
           "amount": 8000, "unit": "tonne_km"}
    yield {"id": 5, "source": "procurement", "scope": "scope_3", "activity_type": "purchased_goods",
           "amount": 250, "unit": "kg"}


if __name__ == "__main__":
    # The same general-purpose filter can be configured for Scope 1, 2, or 3.
    for scope in ("scope_1", "scope_2", "scope_3"):
        pipeline = ScopeFilter(scope) | EmissionCalculator() | ValidEventsOnly()
        stream = TelemetryStream(live_telemetry(), pipeline)
        total = 0.0
        print(f"{scope}:")
        for event in stream:
            total += event["emissions_t_co2e"]
            print(f"  event {event['id']}: {event['emissions_t_co2e']:.6f} t CO2e")
        print(f"  total: {total:.6f} t CO2e ({stream.events_seen} events seen)")
