"""catalog-api response-cache component. Policy: CACHE-18 v2."""
from cache_engine import ResponseCache

POLICY = {
    "ttl_seconds": 300,
    "max_entries": 3,
    "eviction_policy": "fifo",
    "namespace": "catalog-response",
    "cache_misses": True,
}

SOURCE = "Operations approval CACHE-18 (2026-09-06), version v2"

RATIONALE = (
    "Reduce stale catalog responses while retaining the other approved "
    "cache settings."
)


def create_cache(clock):
    return ResponseCache(POLICY, clock)
