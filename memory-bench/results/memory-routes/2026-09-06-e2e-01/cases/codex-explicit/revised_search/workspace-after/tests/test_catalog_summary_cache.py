import unittest
from unittest.mock import Mock

import catalog_refresh_cache
import catalog_summary_cache


class CatalogSummaryCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.clock = lambda: self.now
        self.cache = catalog_summary_cache.create_cache(self.clock)

    def test_complete_approved_agreement_and_types(self):
        expected = {
            "project": "catalog-api",
            "cache": {
                "ttl_seconds": 300,
                "max_entries": 3,
                "eviction_policy": "fifo",
                "namespace": "catalog-response",
                "cache_misses": True,
            },
        }
        self.assertEqual(catalog_summary_cache.POLICY, expected)
        self.assertIs(type(catalog_summary_cache.POLICY), dict)
        for key, value in expected.items():
            self.assertIs(type(catalog_summary_cache.POLICY[key]), type(value))
        for key, value in expected["cache"].items():
            self.assertIs(type(catalog_summary_cache.POLICY["cache"][key]), type(value))
        self.assertEqual(catalog_summary_cache.SOURCE,
                         "Operations approval CACHE-18 (2026-09-06), version v2")
        self.assertEqual(catalog_summary_cache.RATIONALE,
                         "Reduce stale catalog responses while retaining the other approved cache settings.")

    def test_hits_and_misses_expire_without_reads_extending_ttl(self):
        for value in ("response", None):
            with self.subTest(value=value):
                self.now = 0
                cache = catalog_summary_cache.create_cache(self.clock)
                loader = Mock(return_value=value)
                self.assertEqual(cache.get("item", loader), value)
                self.now = 299
                self.assertEqual(cache.get("item", loader), value)
                loader.assert_called_once_with()
                self.assertEqual(cache.keys(), ["catalog-response:item"])
                self.now = 300
                loader.return_value = "refreshed"
                self.assertEqual(cache.get("item", loader), "refreshed")
                self.assertEqual(loader.call_count, 2)
                self.now = 600
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
        self.now = 300
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_instances_own_their_entries(self):
        for component in (catalog_summary_cache, catalog_refresh_cache):
            with self.subTest(component=component.__name__):
                cache = catalog_summary_cache.create_cache(self.clock)
                other = component.create_cache(self.clock)
                cache.get("item", lambda: "first")
                self.assertEqual(other.keys(), [])
                self.assertEqual(other.get("item", lambda: "second"), "second")
                self.assertEqual(cache.get("item", lambda: "unexpected"), "first")
