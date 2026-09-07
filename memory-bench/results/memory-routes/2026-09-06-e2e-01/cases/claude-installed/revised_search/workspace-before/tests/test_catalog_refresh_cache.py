import unittest
from catalog_refresh_cache import POLICY, SOURCE, RATIONALE, create_cache


class CatalogRefreshCachePolicyTest(unittest.TestCase):
    def test_policy_values(self):
        self.assertEqual(POLICY["ttl_seconds"], 300)
        self.assertEqual(POLICY["max_entries"], 3)
        self.assertEqual(POLICY["eviction_policy"], "fifo")
        self.assertEqual(POLICY["namespace"], "catalog-response")
        self.assertTrue(POLICY["cache_misses"])

    def test_source_and_rationale_present(self):
        self.assertIn("CACHE-18", SOURCE)
        self.assertTrue(len(RATIONALE) > 0)

    def test_create_cache_returns_working_cache(self):
        now = [0]
        cache = create_cache(lambda: now[0])
        self.assertEqual(cache.get("x", lambda: "val"), "val")
        self.assertEqual(cache.get("x", lambda: "other"), "val")  # cached

    def test_cache_misses_cached(self):
        now = [0]
        cache = create_cache(lambda: now[0])
        calls = [0]
        def loader():
            calls[0] += 1
            return None
        self.assertIsNone(cache.get("missing", loader))
        self.assertIsNone(cache.get("missing", loader))
        self.assertEqual(calls[0], 1)  # second call served from cache

    def test_fifo_eviction_at_max_entries(self):
        now = [0]
        cache = create_cache(lambda: now[0])
        cache.get("a", lambda: 1)
        cache.get("b", lambda: 2)
        cache.get("c", lambda: 3)
        cache.get("d", lambda: 4)
        keys = cache.keys()
        self.assertNotIn("catalog-response:a", keys)
        self.assertIn("catalog-response:d", keys)

    def test_expiry_at_ttl(self):
        now = [0]
        cache = create_cache(lambda: now[0])
        cache.get("k", lambda: "v")
        now[0] = 300  # age == TTL → expired
        self.assertEqual(cache.get("k", lambda: "new"), "new")

    def test_namespace_in_keys(self):
        now = [0]
        cache = create_cache(lambda: now[0])
        cache.get("item", lambda: "v")
        self.assertIn("catalog-response:item", cache.keys())
