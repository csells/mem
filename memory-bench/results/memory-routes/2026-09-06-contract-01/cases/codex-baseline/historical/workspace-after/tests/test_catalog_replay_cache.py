import unittest
from unittest.mock import Mock

import catalog_replay_cache


class CatalogReplayCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.clock = lambda: self.now
        self.cache = catalog_replay_cache.create_cache(self.clock)

    def test_historical_approval_metadata(self):
        self.assertEqual(catalog_replay_cache.POLICY, {
            "project": "catalog-api",
            "cache": {
                "ttl_seconds": 600,
                "max_entries": 3,
                "eviction_policy": "fifo",
                "namespace": "catalog-response",
                "cache_misses": True,
            },
        })
        self.assertIs(catalog_replay_cache.POLICY["cache"]["cache_misses"], True)
        self.assertEqual(catalog_replay_cache.SOURCE,
                         "Architecture approval CACHE-17 (2026-09-06), version v1")
        self.assertEqual(catalog_replay_cache.RATIONALE,
                         "Share response-cache behavior across catalog readers; "
                         "cache absent lookups to avoid repeated backend reads.")

    def test_values_and_misses_expire_at_historical_ttl(self):
        for value in ("response", None):
            with self.subTest(value=value):
                self.now = 0
                cache = catalog_replay_cache.create_cache(self.clock)
                loader = Mock(return_value=value)
                self.assertEqual(cache.get("item", loader), value)
                for age in (300, 599):
                    self.now = age
                    self.assertEqual(cache.get("item", loader), value)
                    loader.assert_called_once_with()
                    self.assertEqual(cache.keys(), ["catalog-response:item"])
                self.now = 600
                self.assertEqual(cache.keys(), [])
                self.assertEqual(cache.get("item", loader), value)
                self.assertEqual(loader.call_count, 2)

    def test_capacity_and_fifo_reads(self):
        for key in ("a", "b", "c"):
            self.cache.get(key, lambda: "stored")
        loader = Mock(return_value="unexpected")
        self.assertEqual(self.cache.get("a", loader), "stored")
        loader.assert_not_called()
        self.cache.get("d", lambda: "new")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_expired_entries_do_not_consume_capacity(self):
        self.cache.get("a", lambda: "old")
        self.now = 100
        for key in ("b", "c"):
            self.cache.get(key, lambda: "live")
        self.now = 600
        self.cache.get("d", lambda: "new")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_instances_own_entries(self):
        other = catalog_replay_cache.create_cache(self.clock)
        self.cache.get("item", lambda: "first")
        self.assertEqual(other.keys(), [])
        self.assertEqual(other.get("item", lambda: "second"), "second")
        self.assertEqual(self.cache.get("item", lambda: "unused"), "first")
