import json
import unittest
from unittest.mock import Mock

import catalog_cache
import catalog_detail_cache
import catalog_listing_cache
import catalog_preview_cache
import catalog_refresh_cache


class CatalogPreviewCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.clock = lambda: self.now
        self.cache = catalog_preview_cache.create_cache(self.clock)

    def test_exact_approved_policy_and_fields(self):
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
        self.assertEqual(json.dumps(catalog_preview_cache.POLICY, sort_keys=True),
                         json.dumps(expected, sort_keys=True))
        self.assertEqual(catalog_preview_cache.SOURCE,
                         "Operations approval CACHE-18 (2026-09-06), version v2")
        self.assertEqual(catalog_preview_cache.RATIONALE,
                         "Reduce stale catalog responses while retaining the other approved cache settings.")

    def test_values_and_none_expire_at_ttl(self):
        for value in (["preview"], None):
            with self.subTest(value=value):
                self.now = 0
                cache = catalog_preview_cache.create_cache(self.clock)
                loader = Mock(return_value=value)
                self.assertEqual(cache.get("preview", loader), value)
                self.now = 299.999
                self.assertEqual(cache.get("preview", loader), value)
                loader.assert_called_once_with()
                self.assertEqual(cache.keys(), ["catalog-response:preview"])
                self.now = 300
                replacement = Mock(return_value=["updated"])
                self.assertEqual(cache.get("preview", replacement), ["updated"])
                replacement.assert_called_once_with()
                self.now = 601
                self.assertEqual(cache.keys(), [])

    def test_fifo_capacity_includes_none_and_reads_do_not_reorder(self):
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
        self.now = 400
        self.assertEqual(self.cache.keys(), ["catalog-response:d"])

    def test_instances_own_entries(self):
        self.cache.get("preview", lambda: ["first"])
        for component in (catalog_preview_cache, catalog_refresh_cache,
                          catalog_listing_cache, catalog_detail_cache, catalog_cache):
            with self.subTest(component=component.__name__):
                other = component.create_cache(self.clock)
                self.assertEqual(other.keys(), [])
                self.assertEqual(other.get("preview", lambda: ["second"]), ["second"])
                self.assertEqual(self.cache.get("preview", lambda: ["unused"]), ["first"])
