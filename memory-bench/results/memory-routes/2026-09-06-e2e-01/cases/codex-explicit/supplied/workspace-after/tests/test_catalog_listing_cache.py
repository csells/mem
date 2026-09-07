import unittest
from unittest.mock import Mock

import catalog_cache
import catalog_detail_cache
import catalog_listing_cache


class CatalogListingCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.clock = lambda: self.now
        self.cache = catalog_listing_cache.create_cache(self.clock)

    def test_complete_approved_agreement_and_types(self):
        expected = {
            "project": "catalog-api",
            "cache": {
                "ttl_seconds": 600,
                "max_entries": 3,
                "eviction_policy": "fifo",
                "namespace": "catalog-response",
                "cache_misses": True,
            },
        }
        self.assertEqual(catalog_listing_cache.POLICY, expected)
        self.assertIs(type(catalog_listing_cache.POLICY), dict)
        for key, value in expected.items():
            self.assertIs(type(catalog_listing_cache.POLICY[key]), type(value))
        for key, value in expected["cache"].items():
            self.assertIs(type(catalog_listing_cache.POLICY["cache"][key]), type(value))
        self.assertEqual(catalog_listing_cache.SOURCE,
                         "Architecture approval CACHE-17 (2026-09-06), version v1")
        self.assertEqual(catalog_listing_cache.RATIONALE,
                         "Share response-cache behavior across catalog readers; "
                         "cache absent lookups to avoid repeated backend reads.")

    def test_hits_and_misses_expire_without_reads_extending_ttl(self):
        for value in ("response", None):
            with self.subTest(value=value):
                self.now = 0
                cache = catalog_listing_cache.create_cache(self.clock)
                loader = Mock(return_value=value)
                self.assertEqual(cache.get("item", loader), value)
                self.now = 599
                self.assertEqual(cache.get("item", loader), value)
                loader.assert_called_once_with()
                self.assertEqual(cache.keys(), ["catalog-response:item"])
                self.now = 600
                loader.return_value = "refreshed"
                self.assertEqual(cache.get("item", loader), "refreshed")
                self.assertEqual(loader.call_count, 2)
                self.now = 1200
                self.assertEqual(cache.keys(), [])

    def test_fifo_capacity_and_reads_do_not_reorder(self):
        for key in ("a", "b", "c"):
            self.cache.get(key, lambda: key)
        loader = Mock(return_value="unexpected")
        self.assertEqual(self.cache.get("a", loader), "a")
        loader.assert_not_called()
        self.assertEqual(self.cache.keys(), [
            "catalog-response:a", "catalog-response:b", "catalog-response:c",
        ])
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])
        self.assertEqual(self.cache.get("a", loader), "unexpected")
        loader.assert_called_once_with()

    def test_expired_entries_free_capacity_before_eviction(self):
        self.cache.get("a", lambda: "a")
        self.now = 100
        self.cache.get("b", lambda: "b")
        self.cache.get("c", lambda: "c")
        self.now = 600
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_instances_own_their_entries(self):
        for component in (catalog_listing_cache, catalog_detail_cache, catalog_cache):
            with self.subTest(component=component.__name__):
                cache = catalog_listing_cache.create_cache(self.clock)
                other = component.create_cache(self.clock)
                cache.get("item", lambda: "first")
                self.assertEqual(other.keys(), [])
                self.assertEqual(other.get("item", lambda: "second"), "second")
                self.assertEqual(cache.get("item", lambda: "unexpected"), "first")
