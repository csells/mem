import unittest
from unittest.mock import Mock

import catalog_cache


class CatalogCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.cache = catalog_cache.create_cache(lambda: self.now)

    def test_approved_agreement(self):
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
        self.assertEqual(catalog_cache.SOURCE,
                         "Architecture approval CACHE-17 (2026-09-06), version v1")
        self.assertEqual(catalog_cache.RATIONALE,
                         "Share response-cache behavior across catalog readers; "
                         "cache absent lookups to avoid repeated backend reads.")

    def test_values_and_absent_lookups_expire_at_ttl(self):
        for value in ("item", None):
            with self.subTest(value=value):
                self.setUp()
                loader = Mock(return_value=value)
                self.assertEqual(self.cache.get("a", loader), value)
                self.now = 599
                self.assertEqual(self.cache.get("a", loader), value)
                loader.assert_called_once_with()
                self.assertEqual(self.cache.keys(), ["catalog-response:a"])
                self.now = 600
                self.assertEqual(self.cache.keys(), [])
                self.assertEqual(self.cache.get("a", loader), value)
                self.assertEqual(loader.call_count, 2)

    def test_fifo_reads_do_not_refresh_order(self):
        for key in ("a", "b", "c"):
            self.cache.get(key, lambda: key)
        loader = Mock(return_value="unexpected")
        self.assertEqual(self.cache.get("a", loader), "a")
        loader.assert_not_called()
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_expired_entries_do_not_consume_capacity(self):
        self.cache.get("a", lambda: "a")
        self.now = 100
        self.cache.get("b", lambda: "b")
        self.cache.get("c", lambda: "c")
        self.now = 600
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_instances_have_independent_entries(self):
        other = catalog_cache.create_cache(lambda: self.now)
        self.cache.get("a", lambda: "first")
        self.assertEqual(other.keys(), [])
        self.assertEqual(other.get("a", lambda: "second"), "second")
        self.assertEqual(self.cache.get("a", lambda: "unexpected"), "first")
