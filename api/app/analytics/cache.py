"""api/app/analytics/cache.py - NFR-3.10, NFR-3.01: In-memory TTL cache and database index recommendations.

In-memory cache with 5-minute TTL keyed by org_id + function + arguments.
Wrapped around:
- summary (calculate_summary)
- trend (calculate_trend)
- breakdown (calculate_breakdown)
- top-sources (calculate_top_sources)

Output is unmodified.

Database Index Recommendations (Do NOT create migrations as S3 only reads):
-----------------------------------------------------------------------------
1. emission_results:
   - CREATE INDEX idx_emission_results_active ON emission_results (is_current, method, kg_co2e);
     Optimizes base_results_query and join filtering.
   - CREATE INDEX idx_emission_results_activity ON emission_results (activity_id, is_current);
     Optimizes joins with activity_records.
   - CREATE INDEX idx_emission_results_reading ON emission_results (reading_id, is_current);
     Optimizes joins with meter_readings in /analytics/live.

2. activity_records:
   - CREATE INDEX idx_activity_records_org_period ON activity_records (org_id, period_start, period_end);
     Optimizes date filtering across summary, trend, breakdown, and sources.
   - CREATE INDEX idx_activity_records_org_facility ON activity_records (org_id, facility_id);
     Optimizes facility breakdown and top-sources queries.
   - CREATE INDEX idx_activity_records_org_dept ON activity_records (org_id, department_id);
     Optimizes department breakdown queries.

3. meter_readings:
   - CREATE INDEX idx_meter_readings_org_recorded ON meter_readings (org_id, recorded_at);
     Optimizes /analytics/live daily queries.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import wraps
import hashlib
import json
import time
from typing import Any, Callable, Dict, Optional, Tuple

CACHE_TTL_SECONDS = 300  # 5 minutes


class InMemoryCache:
    """Thread-safe-compatible in-memory cache with TTL and hit tracking."""

    def __init__(self, default_ttl: int = CACHE_TTL_SECONDS):
        self.default_ttl = default_ttl
        self._store: Dict[str, Tuple[datetime, Any]] = {}
        self.hits: int = 0
        self.misses: int = 0

    def _make_key(self, org_id: Any, func_name: str, *args, **kwargs) -> str:
        """Constructs an deterministic cache key."""
        # Convert args/kwargs to a JSON serializable structure
        serializable_args = []
        for a in args:
            if hasattr(a, "isoformat"):
                serializable_args.append(a.isoformat())
            else:
                serializable_args.append(str(a))

        serializable_kwargs = {}
        for k, v in sorted(kwargs.items()):
            if hasattr(v, "isoformat"):
                serializable_kwargs[k] = v.isoformat()
            else:
                serializable_kwargs[k] = str(v)

        raw = json.dumps({
            "org_id": str(org_id),
            "func": func_name,
            "args": serializable_args,
            "kwargs": serializable_kwargs,
        }, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        if key in self._store:
            expires_at, val = self._store[key]
            if datetime.now(timezone.utc) < expires_at:
                self.hits += 1
                return deepcopy(val)
            else:
                # Expired
                del self._store[key]
        self.misses += 1
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        duration = ttl if ttl is not None else self.default_ttl
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration)
        self._store[key] = (expires_at, deepcopy(value))

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0


# Global analytics cache instance
analytics_cache = InMemoryCache(default_ttl=300)


def cached_analytics(func_name: str, ttl: int = CACHE_TTL_SECONDS):
    """Decorator for analytics calculator functions.
    
    Expects (db, org_id, ...) signature.
    """
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(db, org_id, *args, **kwargs):
            key = analytics_cache._make_key(org_id, func_name, *args, **kwargs)
            cached_val = analytics_cache.get(key)
            if cached_val is not None:
                return cached_val

            result = fn(db, org_id, *args, **kwargs)
            analytics_cache.set(key, result, ttl=ttl)
            return result

        return wrapper
    return decorator

