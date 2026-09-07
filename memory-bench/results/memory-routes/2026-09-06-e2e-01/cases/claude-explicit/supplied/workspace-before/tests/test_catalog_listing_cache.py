import unittest
from catalog_listing_cache import POLICY, SOURCE, RATIONALE, create_cache


class CatalogListingCachePolicyTest(unittest.TestCase):
    def test_policy_values(self):
        self.assertEqual(POLICY["ttl_seconds"], 600)
        self.assertEqual(POLICY["max_entries"], 3)
        self.assertEqual(POLICY["eviction_policy"], "fifo")
        self.assertEqual(POLICY["namespace"], "catalog-response")
        self.assertTrue(POLICY["cache_misses"])

    def test_source_and_rationale_present(self):
        self.assertIn("CACHE-17", SOURCE)
        self.assertTrue(len(RATIONALE) > 0)


class CatalogListingCacheBehaviorTest(unittest.TestCase):
    def setUp(self):
        self.now = [0]
        self.cache = create_cache(lambda: self.now[0])

    def test_hit_returns_cached_value(self):
        self.cache.get("page-1", lambda: ["a", "b"])
        result = self.cache.get("page-1", lambda: ["x", "y"])
        self.assertEqual(result, ["a", "b"])

    def test_miss_caches_none(self):
        self.cache.get("empty-page", lambda: None)
        calls = [0]
        def loader():
            calls[0] += 1
            return None
        self.cache.get("empty-page", loader)
        self.assertEqual(calls[0], 0)

    def test_expiry_at_ttl(self):
        self.cache.get("page-1", lambda: ["a"])
        self.now[0] = 600
        result = self.cache.get("page-1", lambda: ["b"])
        self.assertEqual(result, ["b"])

    def test_fifo_eviction_at_max_entries(self):
        self.cache.get("p1", lambda: 1)
        self.cache.get("p2", lambda: 2)
        self.cache.get("p3", lambda: 3)
        self.cache.get("p4", lambda: 4)  # evicts "p1"
        keys = self.cache.keys()
        self.assertNotIn("catalog-response:p1", keys)
        self.assertIn("catalog-response:p4", keys)

    def test_keys_namespaced(self):
        self.cache.get("page-1", lambda: ["a"])
        self.assertIn("catalog-response:page-1", self.cache.keys())
