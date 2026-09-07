import json
import unittest
from unittest.mock import Mock

import catalog_preview_cache


class CatalogPreviewCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.clock = lambda: self.now
        self.cache = catalog_preview_cache.create_cache(self.clock)

    def test_complete_v2_agreement_and_approval_fields(self):
        approved_policy = {
            "project": "catalog-api",
            "cache": {
                "ttl_seconds": 300,
                "max_entries": 3,
                "eviction_policy": "fifo",
                "namespace": "catalog-response",
                "cache_misses": True,
            },
        }
        self.assertEqual(
            json.dumps(catalog_preview_cache.POLICY, sort_keys=True),
            json.dumps(approved_policy, sort_keys=True),
        )
        self.assertEqual(
            catalog_preview_cache.SOURCE,
            "Operations approval CACHE-18 (2026-09-06), version v2",
        )
        self.assertEqual(
            catalog_preview_cache.RATIONALE,
            "Reduce stale catalog responses while retaining the other approved cache settings.",
        )

    def test_hits_and_expiry_without_read_refresh(self):
        for expiry_age in (300, 301):
            with self.subTest(expiry_age=expiry_age):
                self.now = 0
                cache = catalog_preview_cache.create_cache(self.clock)
                loader = Mock(side_effect=["original", "fresh"])
                self.assertEqual(cache.get("a", loader), "original")
                self.now = 299.999
                self.assertEqual(cache.get("a", loader), "original")
                loader.assert_called_once_with()
                self.now = expiry_age
                self.assertEqual(cache.get("a", loader), "fresh")
                self.assertEqual(loader.call_count, 2)

    def test_fifo_capacity_and_namespace_without_read_reordering(self):
        for key in ("a", "b", "c"):
            self.cache.get(key, lambda: key)
        expected = ["catalog-response:" + key for key in ("a", "b", "c")]
        self.assertEqual(self.cache.keys(), expected)
        loader = Mock()
        self.assertEqual(self.cache.get("a", loader), "a")
        loader.assert_not_called()
        self.assertEqual(self.cache.keys(), expected)
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_none_results_are_cached_until_expiry(self):
        loader = Mock(return_value=None)
        self.assertIsNone(self.cache.get("missing", loader))
        self.now = 299.999
        self.assertIsNone(self.cache.get("missing", loader))
        loader.assert_called_once_with()
        self.assertEqual(self.cache.keys(), ["catalog-response:missing"])
        self.now = 300
        self.assertEqual(self.cache.keys(), [])
        self.assertIsNone(self.cache.get("missing", loader))
        self.assertEqual(loader.call_count, 2)

    def test_expired_entries_release_capacity_and_keys_are_live(self):
        for key in ("a", "b"):
            self.cache.get(key, lambda: key)
        self.now = 100
        self.cache.get("c", lambda: "c")
        self.now = 300
        for key in ("d", "e"):
            self.cache.get(key, lambda: key)
        self.assertEqual(self.cache.keys(), [
            "catalog-response:c", "catalog-response:d", "catalog-response:e",
        ])
        self.now = 400
        self.assertEqual(self.cache.keys(), ["catalog-response:d", "catalog-response:e"])
        self.now = 600
        self.assertEqual(self.cache.keys(), [])

    def test_instances_are_independent(self):
        self.cache.get("a", lambda: "preview")
        other = catalog_preview_cache.create_cache(self.clock)
        self.assertEqual(other.keys(), [])
        self.assertEqual(other.get("a", lambda: "other"), "other")
        for key in ("b", "c", "d"):
            other.get(key, lambda: key)
        loader = Mock()
        self.assertEqual(self.cache.get("a", loader), "preview")
        loader.assert_not_called()
        self.assertEqual(self.cache.keys(), ["catalog-response:a"])
        self.assertEqual(other.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])
