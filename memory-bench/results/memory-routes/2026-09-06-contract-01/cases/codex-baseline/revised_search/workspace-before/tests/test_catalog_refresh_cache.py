import unittest
from unittest.mock import Mock

import catalog_cache
import catalog_detail_cache
import catalog_listing_cache
import catalog_refresh_cache


class CatalogRefreshCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.clock = lambda: self.now
        self.cache = catalog_refresh_cache.create_cache(self.clock)

    def test_v2_changes_only_ttl_and_approval(self):
        for component in (catalog_cache, catalog_detail_cache, catalog_listing_cache):
            with self.subTest(component=component.__name__):
                expected = dict(component.POLICY, cache=dict(component.POLICY["cache"]))
                self.assertEqual(expected["cache"]["ttl_seconds"], 600)
                expected["cache"]["ttl_seconds"] = 300
                self.assertEqual(catalog_refresh_cache.POLICY, expected)
                for key, value in expected["cache"].items():
                    self.assertIs(type(catalog_refresh_cache.POLICY["cache"][key]), type(value))
        self.assertEqual(catalog_refresh_cache.SOURCE,
                         "Operations approval CACHE-18 (2026-09-06), version v2")
        self.assertEqual(catalog_refresh_cache.RATIONALE,
                         "Reduce stale catalog responses while retaining the other approved cache settings.")

    def test_values_and_absent_lookups_expire_at_300_seconds(self):
        for value in (["item"], None):
            with self.subTest(value=value):
                self.now = 0
                cache = catalog_refresh_cache.create_cache(self.clock)
                loader = Mock(return_value=value)
                self.assertEqual(cache.get("refresh", loader), value)
                self.now = 299.999
                self.assertEqual(cache.get("refresh", loader), value)
                loader.assert_called_once_with()
                self.assertEqual(cache.keys(), ["catalog-response:refresh"])
                self.now = 300
                replacement = Mock(return_value=["updated"])
                self.assertEqual(cache.get("refresh", replacement), ["updated"])
                replacement.assert_called_once_with()
                self.now = 600
                self.assertEqual(cache.keys(), [])

    def test_capacity_and_fifo_reads_include_absent_lookups(self):
        self.cache.get("a", lambda: None)
        for key in ("b", "c"):
            self.cache.get(key, lambda: ["stored"])
        self.assertEqual(self.cache.keys(), [
            "catalog-response:a", "catalog-response:b", "catalog-response:c",
        ])
        loader = Mock(return_value=["found"])
        self.assertIsNone(self.cache.get("a", loader))
        loader.assert_not_called()
        self.cache.get("d", lambda: ["new"])
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])
        self.assertEqual(self.cache.get("a", loader), ["found"])
        loader.assert_called_once_with()

    def test_expired_entries_do_not_consume_capacity(self):
        self.cache.get("a", lambda: ["old"])
        self.now = 100
        for key in ("b", "c"):
            self.cache.get(key, lambda: ["live"])
        self.now = 300
        self.cache.get("d", lambda: ["new"])
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_instances_own_entries(self):
        self.cache.get("refresh", lambda: ["first"])
        for component in (catalog_refresh_cache, catalog_listing_cache,
                          catalog_detail_cache, catalog_cache):
            with self.subTest(component=component.__name__):
                other = component.create_cache(self.clock)
                self.assertEqual(other.keys(), [])
                self.assertEqual(other.get("refresh", lambda: ["second"]), ["second"])
                self.assertEqual(self.cache.get("refresh", lambda: ["unused"]), ["first"])
