from abc import ABC, abstractmethod

# 1. Abstract Base Class (ABCs)
class StreamProcessor(ABC):
    """Blueprint for all our stream processors."""
    
    @abstractmethod
    def process(self, item):
        """Every processor must implement this method."""
        pass

    # 3. Operator Overloading (__or__)
    def __or__(self, other):
        """Allows chaining processors together using the | operator."""
        return Pipeline(self, other)

# 2. Inheritance & Polymorphism
class FilterByScope(StreamProcessor):
    """Filters out records that don't match the target scope."""
    def __init__(self, target_scope: int):
        self.target_scope = target_scope

    def process(self, item):
        if item.get("scope") == self.target_scope:
            return item
        return None  # Dropped

class TransformToEmissions(StreamProcessor):
    """Converts raw activity amounts into kg CO2e."""
    def __init__(self, emission_factor: float):
        self.emission_factor = emission_factor

    def process(self, item):
        if item is not None:
            # Ensure amount exists and is a number
            amount = item.get("amount", 0)
            item["co2e_kg"] = amount * self.emission_factor
            return item
        return None

class Pipeline(StreamProcessor):
    """Combines multiple processors into a pipeline."""
    def __init__(self, left, right):
        self.left = left
        self.right = right

    def process(self, item):
        result = self.left.process(item)
        return self.right.process(result)

# 4. Iterators (__iter__ & __next__)
class TelemetryStream:
    """Simulates a live stream of data coming from IoT/operational systems."""
    def __init__(self, data: list, pipeline: StreamProcessor):
        self._data = data
        self._pipeline = pipeline
        self._index = 0

    def __iter__(self):
        return self

    def __next__(self):
        while self._index < len(self._data):
            raw_item = self._data[self._index]
            self._index += 1
            
            # Run the raw data through the pipeline
            processed_item = self._pipeline.process(raw_item)
            
            # If the pipeline didn't drop it, yield it
            if processed_item is not None:
                return processed_item
                
        raise StopIteration

# ==========================================
# Demonstration 
# ==========================================
if __name__ == "__main__":
    # Mock live telemetry data (e.g., from data center logs or flight APIs)
    live_events = [
        {"id": 1, "type": "flight", "scope": 3, "amount": 1000},
        {"id": 2, "type": "electricity", "scope": 2, "amount": 5000},
        {"id": 3, "type": "flight", "scope": 3, "amount": 2500},
        {"id": 4, "type": "diesel", "scope": 1, "amount": 300},
    ]

    # We only want Scope 3 records, and we transform them using an emission factor of 0.15
    pipeline = FilterByScope(3) | TransformToEmissions(0.15)

    # Start the stream (Iterator)
    stream = TelemetryStream(live_events, pipeline)

    print("--- Processing Live Stream ---")
    for event in stream:
        print(f"Processed Event {event['id']}: {event['amount']} units -> {event['co2e_kg']} kg CO2e")
