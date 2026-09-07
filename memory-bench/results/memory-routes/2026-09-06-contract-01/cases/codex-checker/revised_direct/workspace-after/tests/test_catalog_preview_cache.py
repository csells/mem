import unittest
from unittest.mock import Mock

import catalog_preview_cache


class CatalogPreviewCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.cache = catalog_preview_cache.create_cache(lambda: self.now)

    def test_approved_v2_agreement(self):
        # Complete agreement recalled from Beads catalog-api.response-cache.
        self.assertEqual(catalog_preview_cache.POLICY, {
            "project": "catalog-api",
            "cache": {
                "ttl_seconds": 300,
                "max_entries": 3,
                "eviction_policy": "fifo",
                "namespace": "catalog-response",
                "cache_misses": True,
            },
        })
        self.assertEqual(catalog_preview_cache.SOURCE,
                         "Operations approval CACHE-18 (2026-09-06), version v2")
        self.assertEqual(catalog_preview_cache.RATIONALE,
                         "Reduce stale catalog responses while retaining the other "
                         "approved cache settings.")

    def test_hits_and_expiry_including_cached_none(self):
        for value in ({"id": "a"}, [], None):
            for expiry_age in (300, 301):
                with self.subTest(value=value, expiry_age=expiry_age):
                    self.now = 0
                    cache = catalog_preview_cache.create_cache(lambda: self.now)
                    loader = Mock(return_value=value)
                    self.assertEqual(cache.get("a", loader), value)
                    self.now = 299.999
                    self.assertEqual(cache.get("a", loader), value)
                    loader.assert_called_once_with()
                    self.assertEqual(cache.keys(), ["catalog-response:a"])
                    self.now = expiry_age
                    self.assertEqual(cache.get("a", loader), value)
                    self.assertEqual(loader.call_count, 2)
                    self.now += 300
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
        self.now = 300
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_cached_none_uses_fifo_capacity(self):
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

    def test_instances_have_independent_entries(self):
        self.cache.get("a", lambda: "preview")
        other = catalog_preview_cache.create_cache(lambda: self.now)
        self.assertEqual(other.keys(), [])
        self.assertEqual(other.get("a", lambda: "other"), "other")
        loader = Mock()
        self.assertEqual(self.cache.get("a", loader), "preview")
        loader.assert_not_called()
