import unittest
from unittest.mock import Mock

import catalog_public_cache


class CatalogPublicCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.clock = lambda: self.now
        self.cache = catalog_public_cache.create_cache(self.clock)

    def test_complete_approved_policy_and_fields(self):
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
        self.assertEqual(catalog_public_cache.POLICY, expected)
        for key, value in expected["cache"].items():
            self.assertIs(type(catalog_public_cache.POLICY["cache"][key]), type(value))
        self.assertEqual(catalog_public_cache.SOURCE,
                         "Operations approval CACHE-18 (2026-09-06), version v2")
        self.assertEqual(catalog_public_cache.RATIONALE,
                         "Reduce stale catalog responses while retaining the other approved cache settings.")

    def test_values_and_misses_expire_at_ttl(self):
        for value in (["item"], None):
            with self.subTest(value=value):
                self.now = 0
                cache = catalog_public_cache.create_cache(self.clock)
                loader = Mock(return_value=value)
                self.assertEqual(cache.get("public", loader), value)
                self.now = 299.999
                self.assertEqual(cache.get("public", loader), value)
                loader.assert_called_once_with()
                self.assertEqual(cache.keys(), ["catalog-response:public"])
                self.now = 300
                replacement = Mock(return_value=["updated"])
                self.assertEqual(cache.get("public", replacement), ["updated"])
                replacement.assert_called_once_with()
                self.now = 600
                self.assertEqual(cache.keys(), [])

    def test_fifo_capacity_includes_misses_and_reads_do_not_reorder(self):
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

    def test_expired_entries_do_not_consume_capacity(self):
        self.cache.get("a", lambda: "old")
        self.now = 100
        for key in ("b", "c"):
            self.cache.get(key, lambda: "live")
        self.now = 300
        self.cache.get("d", lambda: "new")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_instances_own_entries(self):
        self.cache.get("public", lambda: "first")
        other = catalog_public_cache.create_cache(self.clock)
        self.assertEqual(other.keys(), [])
        self.assertEqual(other.get("public", lambda: "second"), "second")
        self.assertEqual(self.cache.get("public", lambda: "unused"), "first")
