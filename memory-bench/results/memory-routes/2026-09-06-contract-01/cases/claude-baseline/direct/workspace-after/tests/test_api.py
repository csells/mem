import unittest
from cache_engine import ResponseCache


class CacheApiTest(unittest.TestCase):
    def test_parameterized_engine(self):
        now = [0]
        policy = {"ttl_seconds": 2, "max_entries": 2, "eviction_policy": "fifo",
                  "namespace": "example", "cache_misses": False}
        cache = ResponseCache(policy, lambda: now[0])
        self.assertEqual(cache.get("a", lambda: "first"), "first")
        self.assertEqual(cache.get("a", lambda: "later"), "first")
        self.assertEqual(cache.keys(), ["example:a"])
        now[0] = 2
        self.assertEqual(cache.get("a", lambda: "later"), "later")
