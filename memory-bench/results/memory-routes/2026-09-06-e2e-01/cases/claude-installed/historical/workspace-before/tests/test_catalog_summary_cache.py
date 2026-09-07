import unittest
from catalog_summary_cache import POLICY, SOURCE, RATIONALE, create_cache


class CatalogSummaryCachePolicyTest(unittest.TestCase):
    def test_policy_values(self):
        cache_cfg = POLICY["cache"]
        self.assertEqual(cache_cfg["ttl_seconds"], 300)
        self.assertEqual(cache_cfg["max_entries"], 3)
        self.assertEqual(cache_cfg["eviction_policy"], "fifo")
        self.assertEqual(cache_cfg["namespace"], "catalog-response")
        self.assertTrue(cache_cfg["cache_misses"])

    def test_policy_project(self):
        self.assertEqual(POLICY["project"], "catalog-api")

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

    def test_instance_isolation(self):
        now = [0]
        c1 = create_cache(lambda: now[0])
        c2 = create_cache(lambda: now[0])
        c1.get("k", lambda: "c1val")
        self.assertIsNone(c2.get("k", lambda: None))
