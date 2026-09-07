import unittest
from catalog_summary_cache import POLICY, SOURCE, RATIONALE, create_cache


class CatalogSummaryCachePolicyTest(unittest.TestCase):
    def test_policy_values(self):
        self.assertEqual(POLICY["ttl_seconds"], 300)
        self.assertEqual(POLICY["max_entries"], 3)
        self.assertEqual(POLICY["eviction_policy"], "fifo")
        self.assertEqual(POLICY["namespace"], "catalog-response")
        self.assertTrue(POLICY["cache_misses"])

    def test_source_and_rationale_present(self):
        self.assertIn("CACHE-18", SOURCE)
        self.assertTrue(len(RATIONALE) > 0)


class CatalogSummaryCacheBehaviorTest(unittest.TestCase):
    def setUp(self):
        self.now = [0]
        self.cache = create_cache(lambda: self.now[0])

    def test_hit_returns_cached_value(self):
        self.cache.get("summary-1", lambda: "v1")
        result = self.cache.get("summary-1", lambda: "v2")
        self.assertEqual(result, "v1")

    def test_miss_caches_none(self):
        self.cache.get("absent", lambda: None)
        calls = [0]
        def loader():
            calls[0] += 1
            return None
        self.cache.get("absent", loader)
        self.assertEqual(calls[0], 0)

    def test_expiry_at_ttl(self):
        self.cache.get("summary-1", lambda: "first")
        self.now[0] = 300
        result = self.cache.get("summary-1", lambda: "refreshed")
        self.assertEqual(result, "refreshed")

    def test_fifo_eviction_at_max_entries(self):
        self.cache.get("a", lambda: 1)
        self.cache.get("b", lambda: 2)
        self.cache.get("c", lambda: 3)
        self.cache.get("d", lambda: 4)
        keys = self.cache.keys()
        self.assertNotIn("catalog-response:a", keys)
        self.assertIn("catalog-response:d", keys)

    def test_keys_namespaced(self):
        self.cache.get("x", lambda: "val")
        self.assertIn("catalog-response:x", self.cache.keys())
