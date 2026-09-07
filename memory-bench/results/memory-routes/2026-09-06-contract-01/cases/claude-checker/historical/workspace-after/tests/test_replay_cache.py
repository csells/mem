import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import catalog_replay_cache as mod


class ReplayCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = [0]
        self.cache = mod.create_cache(lambda: self.now[0])

    def test_policy_ttl(self):
        self.assertEqual(mod.POLICY["cache"]["ttl_seconds"], 600)

    def test_policy_fields(self):
        c = mod.POLICY["cache"]
        self.assertEqual(c["max_entries"], 3)
        self.assertEqual(c["eviction_policy"], "fifo")
        self.assertEqual(c["namespace"], "catalog-response")
        self.assertTrue(c["cache_misses"])

    def test_source_references_cache17_v1(self):
        self.assertIn("CACHE-17", mod.SOURCE)
        self.assertIn("v1", mod.SOURCE)
        self.assertIsInstance(mod.RATIONALE, str)

    def test_cache_stores_and_returns_value(self):
        result = self.cache.get("r1", lambda: "replay-data")
        self.assertEqual(result, "replay-data")
        self.assertEqual(self.cache.get("r1", lambda: "other"), "replay-data")

    def test_cache_misses_are_cached(self):
        calls = [0]
        def loader():
            calls[0] += 1
            return None
        self.cache.get("missing", loader)
        self.cache.get("missing", loader)
        self.assertEqual(calls[0], 1)

    def test_expiry_at_ttl(self):
        self.cache.get("k", lambda: "v")
        self.now[0] = 600
        result = self.cache.get("k", lambda: "fresh")
        self.assertEqual(result, "fresh")

    def test_fifo_eviction(self):
        self.cache.get("a", lambda: 1)
        self.cache.get("b", lambda: 2)
        self.cache.get("c", lambda: 3)
        self.cache.get("d", lambda: 4)
        keys = self.cache.keys()
        self.assertNotIn("catalog-response:a", keys)
        self.assertIn("catalog-response:d", keys)


if __name__ == "__main__":
    unittest.main()
