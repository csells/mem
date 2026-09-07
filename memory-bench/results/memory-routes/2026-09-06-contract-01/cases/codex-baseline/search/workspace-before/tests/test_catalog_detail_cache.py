import unittest
from unittest.mock import Mock

import catalog_cache
import catalog_detail_cache


class CatalogDetailCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.clock = lambda: self.now
        self.cache = catalog_detail_cache.create_cache(self.clock)

    def test_approved_metadata(self):
        self.assertEqual(catalog_detail_cache.POLICY, {
            "project": "catalog-api",
            "cache": {
                "ttl_seconds": 600,
                "max_entries": 3,
                "eviction_policy": "fifo",
                "namespace": "catalog-response",
                "cache_misses": True,
            },
        })
        policy = catalog_detail_cache.POLICY["cache"]
        self.assertIs(type(policy["ttl_seconds"]), int)
        self.assertIs(type(policy["max_entries"]), int)
        self.assertIs(policy["cache_misses"], True)
        self.assertEqual(catalog_detail_cache.SOURCE,
                         "Architecture approval CACHE-17 (2026-09-06), version v1")
        self.assertEqual(catalog_detail_cache.RATIONALE,
                         "Share response-cache behavior across catalog readers; "
                         "cache absent lookups to avoid repeated backend reads.")

    def test_values_and_absent_lookups_expire_at_ttl(self):
        for value in ("response", None):
            with self.subTest(value=value):
                self.now = 0
                cache = catalog_detail_cache.create_cache(self.clock)
                loader = Mock(return_value=value)
                self.assertEqual(cache.get("item", loader), value)
                self.now = 599.999
                self.assertEqual(cache.get("item", loader), value)
                loader.assert_called_once_with()
                self.assertEqual(cache.keys(), ["catalog-response:item"])
                self.now = 600
                replacement = Mock(return_value="updated")
                self.assertEqual(cache.get("item", replacement), "updated")
                replacement.assert_called_once_with()
                self.now = 1200
                self.assertEqual(cache.keys(), [])

    def test_capacity_and_fifo_reads_include_absent_lookups(self):
        self.cache.get("a", lambda: None)
        for key in ("b", "c"):
            self.cache.get(key, lambda: "stored")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:a", "catalog-response:b", "catalog-response:c",
        ])
        loader = Mock(return_value="found")
        self.assertIsNone(self.cache.get("a", loader))
        loader.assert_not_called()
        self.cache.get("d", lambda: "new")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])
        self.assertEqual(self.cache.get("a", loader), "found")
        loader.assert_called_once_with()
        self.assertEqual(self.cache.keys(), [
            "catalog-response:c", "catalog-response:d", "catalog-response:a",
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
        self.cache.get("item", lambda: "first")
        for component in (catalog_detail_cache, catalog_cache):
            with self.subTest(component=component.__name__):
                other = component.create_cache(self.clock)
                self.assertEqual(other.keys(), [])
                self.assertEqual(other.get("item", lambda: "second"), "second")
                self.assertEqual(self.cache.get("item", lambda: "unused"), "first")
