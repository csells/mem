import unittest
from catalog_public_cache import POLICY, SOURCE, RATIONALE, create_cache


class CatalogPublicCachePolicyTest(unittest.TestCase):
    def test_policy_fields(self):
        cache_cfg = POLICY["cache"]
        self.assertEqual(cache_cfg["ttl_seconds"], 300)
        self.assertEqual(cache_cfg["max_entries"], 3)
        self.assertEqual(cache_cfg["eviction_policy"], "fifo")
        self.assertEqual(cache_cfg["namespace"], "catalog-response")
        self.assertTrue(cache_cfg["cache_misses"])

    def test_source_and_rationale_present(self):
        self.assertIn("CACHE-18", SOURCE)
        self.assertTrue(len(RATIONALE) > 0)


class CatalogPublicCacheBehaviorTest(unittest.TestCase):
    def setUp(self):
        self.now = [0]
        self.cache = create_cache(lambda: self.now[0])

    def test_hit_returns_cached_value(self):
        self.cache.get("x", lambda: "v1")
        result = self.cache.get("x", lambda: "v2")
        self.assertEqual(result, "v1")

    def test_namespaced_keys(self):
        self.cache.get("item", lambda: "data")
        self.assertIn("catalog-response:item", self.cache.keys())

    def test_expiry_at_ttl(self):
        self.cache.get("item", lambda: "data")
        self.now[0] = 300
        result = self.cache.get("item", lambda: "fresh")
        self.assertEqual(result, "fresh")

    def test_cache_misses_caches_none(self):
        result = self.cache.get("missing", lambda: None)
        self.assertIsNone(result)
        self.assertIn("catalog-response:missing", self.cache.keys())

    def test_fifo_eviction_at_capacity(self):
        self.cache.get("a", lambda: 1)
        self.cache.get("b", lambda: 2)
        self.cache.get("c", lambda: 3)
        self.cache.get("d", lambda: 4)
        keys = self.cache.keys()
        self.assertNotIn("catalog-response:a", keys)
        self.assertIn("catalog-response:d", keys)
