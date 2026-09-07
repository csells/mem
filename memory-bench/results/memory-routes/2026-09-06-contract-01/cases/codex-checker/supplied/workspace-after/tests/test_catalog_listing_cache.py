import unittest
from unittest.mock import Mock

import catalog_cache
import catalog_detail_cache
import catalog_listing_cache


class CatalogListingCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.cache = catalog_listing_cache.create_cache(lambda: self.now)

    def test_original_v1_agreement(self):
        self.assertEqual(catalog_listing_cache.POLICY, {
            "project": "catalog-api",
            "cache": {
                "ttl_seconds": 600,
                "max_entries": 3,
                "eviction_policy": "fifo",
                "namespace": "catalog-response",
                "cache_misses": True,
            },
        })
        self.assertEqual(catalog_listing_cache.SOURCE,
                         "Architecture approval CACHE-17 (2026-09-06), version v1")
        self.assertEqual(catalog_listing_cache.RATIONALE,
                         "Share response-cache behavior across catalog readers; "
                         "cache absent lookups to avoid repeated backend reads.")

    def test_values_and_absent_lookups_expire_at_ttl(self):
        for value in ([{"id": "a"}], [], None):
            with self.subTest(value=value):
                self.now = 0
                cache = catalog_listing_cache.create_cache(lambda: self.now)
                loader = Mock(return_value=value)
                self.assertEqual(cache.get("a", loader), value)
                self.now = 599.999
                self.assertEqual(cache.get("a", loader), value)
                loader.assert_called_once_with()
                self.assertEqual(cache.keys(), ["catalog-response:a"])
                self.now = 600
                self.assertEqual(cache.get("a", loader), value)
                self.assertEqual(loader.call_count, 2)
                self.now = 1200
                self.assertEqual(cache.keys(), [])

    def test_fifo_capacity_and_reads_preserve_order(self):
        for key in ("a", "b", "c"):
            self.cache.get(key, lambda: key)
        loader = Mock()
        self.assertEqual(self.cache.get("a", loader), "a")
        loader.assert_not_called()
        self.assertEqual(self.cache.keys(), [
            "catalog-response:a", "catalog-response:b", "catalog-response:c",
        ])
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_expired_entries_free_capacity(self):
        self.cache.get("a", lambda: "a")
        self.now = 100
        self.cache.get("b", lambda: "b")
        self.cache.get("c", lambda: "c")
        self.now = 600
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_absent_lookups_use_fifo_capacity(self):
        loader = Mock(return_value=None)
        self.assertIsNone(self.cache.get("missing", loader))
        for key in ("a", "b"):
            self.cache.get(key, lambda: key)
        self.assertIsNone(self.cache.get("missing", loader))
        loader.assert_called_once_with()
        self.cache.get("c", lambda: "c")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:a", "catalog-response:b", "catalog-response:c",
        ])
        self.assertIsNone(self.cache.get("missing", loader))
        self.assertEqual(loader.call_count, 2)

    def test_instances_and_sibling_components_have_independent_entries(self):
        self.cache.get("a", lambda: "listing")
        for component in (catalog_listing_cache, catalog_detail_cache, catalog_cache):
            with self.subTest(component=component.__name__):
                other = component.create_cache(lambda: self.now)
                self.assertEqual(other.keys(), [])
                self.assertEqual(other.get("a", lambda: "other"), "other")
                self.assertEqual(self.cache.get("a", lambda: "unexpected"), "listing")
