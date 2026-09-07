import json
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

    def test_complete_v1_agreement_and_approval_fields(self):
        # Reproduce the historical catalog-api.response-cache.v1 agreement.
        approved_policy = {
            "project": "catalog-api",
            "cache": {
                "ttl_seconds": 600,
                "max_entries": 3,
                "eviction_policy": "fifo",
                "namespace": "catalog-response",
                "cache_misses": True,
            },
        }
        self.assertEqual(
            json.dumps(catalog_listing_cache.POLICY, sort_keys=True),
            json.dumps(approved_policy, sort_keys=True),
        )
        self.assertEqual(
            catalog_listing_cache.SOURCE,
            "Architecture approval CACHE-17 (2026-09-06), version v1",
        )
        self.assertEqual(
            catalog_listing_cache.RATIONALE,
            "Share response-cache behavior across catalog readers; cache absent "
            "lookups to avoid repeated backend reads.",
        )

    def test_hits_expire_at_exact_ttl_without_refresh(self):
        loader = Mock(side_effect=["original", "fresh"])
        self.assertEqual(self.cache.get("a", loader), "original")
        self.now = 599.999
        self.assertEqual(self.cache.get("a", loader), "original")
        loader.assert_called_once_with()
        self.now = 600
        self.assertEqual(self.cache.get("a", loader), "fresh")
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
        self.now = 599.999
        self.assertIsNone(self.cache.get("missing", loader))
        loader.assert_called_once_with()
        self.assertEqual(self.cache.keys(), ["catalog-response:missing"])
        self.now = 600
        self.assertEqual(self.cache.keys(), [])
        self.assertIsNone(self.cache.get("missing", loader))
        self.assertEqual(loader.call_count, 2)

    def test_expired_entries_release_capacity_and_keys_are_live(self):
        for key in ("a", "b"):
            self.cache.get(key, lambda: key)
        self.now = 100
        self.cache.get("c", lambda: "c")
        self.now = 600
        for key in ("d", "e"):
            self.cache.get(key, lambda: key)
        self.assertEqual(self.cache.keys(), [
            "catalog-response:c", "catalog-response:d", "catalog-response:e",
        ])
        self.now = 700
        self.assertEqual(self.cache.keys(), ["catalog-response:d", "catalog-response:e"])
        self.now = 1200
        self.assertEqual(self.cache.keys(), [])

    def test_instances_and_siblings_have_independent_entries(self):
        self.cache.get("a", lambda: "listing")
        for component in (catalog_listing_cache, catalog_cache, catalog_detail_cache):
            with self.subTest(component=component.__name__):
                other = component.create_cache(self.clock)
                self.assertEqual(other.keys(), [])
                self.assertEqual(other.get("a", lambda: "other"), "other")
                self.assertEqual(self.cache.get("a", lambda: "unexpected"), "listing")
