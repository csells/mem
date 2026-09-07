import unittest
from catalog_replay_cache import POLICY, SOURCE, RATIONALE, create_cache


class CatalogReplayCachePolicyTest(unittest.TestCase):
    def test_policy_values(self):
        self.assertEqual(POLICY["ttl_seconds"], 600)
        self.assertEqual(POLICY["max_entries"], 3)
        self.assertEqual(POLICY["eviction_policy"], "fifo")
        self.assertEqual(POLICY["namespace"], "catalog-response")
        self.assertTrue(POLICY["cache_misses"])

    def test_source_references_cache17_v1(self):
        self.assertIn("CACHE-17", SOURCE)
        self.assertIn("v1", SOURCE)
        self.assertTrue(len(RATIONALE) > 0)


class CatalogReplayCacheBehaviorTest(unittest.TestCase):
    def setUp(self):
        self.now = [0]
        self.cache = create_cache(lambda: self.now[0])

    def test_hit_returns_cached_value(self):
        self.cache.get("item-1", lambda: "v1")
        result = self.cache.get("item-1", lambda: "v2")
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
        self.cache.get("item-1", lambda: "first")
        self.now[0] = 600
        result = self.cache.get("item-1", lambda: "refreshed")
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
