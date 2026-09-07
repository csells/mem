"""Historical catalog response-cache replay of approval CACHE-17 v1.

Agreement: catalog-api.response-cache.CACHE-17-v1. This audit component
reproduces the original approval; the standing agreement remains v2.
"""

from cache_engine import ResponseCache


POLICY = {
    "project": "catalog-api",
    "cache": {
        "ttl_seconds": 600,
        "max_entries": 3,
        "eviction_policy": "fifo",
        "namespace": "catalog-response",
        "cache_misses": True,
    },
}

SOURCE = "Architecture approval CACHE-17 (2026-09-06), version v1"
RATIONALE = (
    "Share response-cache behavior across catalog readers; cache absent lookups "
    "to avoid repeated backend reads."
)


def create_cache(clock):
    """Return an independent cache using the supplied clock in seconds."""
    return ResponseCache(POLICY["cache"], clock)
