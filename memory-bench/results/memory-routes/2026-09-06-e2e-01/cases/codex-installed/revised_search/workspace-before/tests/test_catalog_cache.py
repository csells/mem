import unittest
from unittest.mock import Mock

import catalog_cache


class CatalogCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.clock = lambda: self.now
        self.cache = catalog_cache.create_cache(self.clock)

    def test_approved_metadata(self):
        self.assertEqual(catalog_cache.POLICY, {
            "project": "catalog-api",
            "cache": {
                "ttl_seconds": 600,
                "max_entries": 3,
                "eviction_policy": "fifo",
                "namespace": "catalog-response",
                "cache_misses": True,
            },
        })
        self.assertIs(type(catalog_cache.POLICY["cache"]["ttl_seconds"]), int)
        self.assertIs(type(catalog_cache.POLICY["cache"]["max_entries"]), int)
        self.assertIs(catalog_cache.POLICY["cache"]["cache_misses"], True)
        self.assertEqual(catalog_cache.SOURCE,
                         "Architecture approval CACHE-17 (2026-09-06), version v1")
        self.assertEqual(catalog_cache.RATIONALE,
                         "Share response-cache behavior across catalog readers; "
                         "cache absent lookups to avoid repeated backend reads.")

    def test_hit_and_expiry_at_ttl_without_refresh_on_read(self):
        loader = Mock(side_effect=["first", "fresh"])
        self.assertEqual(self.cache.get("a", loader), "first")
        self.now = 599
        self.assertEqual(self.cache.get("a", loader), "first")
        loader.assert_called_once_with()
        self.now = 600
        self.assertEqual(self.cache.get("a", loader), "fresh")
        self.assertEqual(loader.call_count, 2)

    def test_fifo_capacity_and_namespaced_keys(self):
        for key in ("a", "b", "c"):
            self.cache.get(key, lambda: key)
        unused_loader = Mock()
        self.assertEqual(self.cache.get("a", unused_loader), "a")
        unused_loader.assert_not_called()
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_absent_lookups_are_cached_until_expiry(self):
        loader = Mock(return_value=None)
        self.assertIsNone(self.cache.get("missing", loader))
        self.now = 599
        self.assertIsNone(self.cache.get("missing", loader))
        loader.assert_called_once_with()
        self.assertEqual(self.cache.keys(), ["catalog-response:missing"])
        self.now = 600
        self.assertIsNone(self.cache.get("missing", loader))
        self.assertEqual(loader.call_count, 2)

    def test_expired_entries_release_capacity_and_disappear_from_keys(self):
        self.cache.get("a", lambda: "a")
        self.now = 100
        for key in ("b", "c"):
            self.cache.get(key, lambda: key)
        self.now = 600
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])
        self.now = 700
        self.assertEqual(self.cache.keys(), ["catalog-response:d"])
        self.now = 1200
        self.assertEqual(self.cache.keys(), [])

    def test_instances_own_their_entries(self):
        other = catalog_cache.create_cache(self.clock)
        self.cache.get("a", lambda: "first")
        self.assertEqual(other.keys(), [])
        self.assertEqual(other.get("a", lambda: "second"), "second")
        self.assertEqual(self.cache.get("a", lambda: "unexpected"), "first")
