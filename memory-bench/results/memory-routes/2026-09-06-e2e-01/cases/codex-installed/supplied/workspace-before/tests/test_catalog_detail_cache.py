import json
import unittest
from unittest.mock import Mock

import catalog_cache
import catalog_detail_cache


class CatalogDetailCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.clock = lambda: self.now
        self.cache = catalog_detail_cache.create_cache(self.clock)

    def test_complete_approved_policy_and_metadata(self):
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
        # JSON comparison also distinguishes booleans and integer/float values.
        self.assertEqual(
            json.dumps(catalog_detail_cache.POLICY, sort_keys=True),
            json.dumps(approved_policy, sort_keys=True),
        )
        self.assertEqual(
            catalog_detail_cache.SOURCE,
            "Architecture approval CACHE-17 (2026-09-06), version v1",
        )
        self.assertEqual(
            catalog_detail_cache.RATIONALE,
            "Share response-cache behavior across catalog readers; cache absent "
            "lookups to avoid repeated backend reads.",
        )

    def test_hits_and_exact_ttl_expiry_without_read_refresh(self):
        loader = Mock(side_effect=["original", "fresh"])
        self.assertEqual(self.cache.get("a", loader), "original")
        self.now = 599.999
        self.assertEqual(self.cache.get("a", loader), "original")
        loader.assert_called_once_with()
        self.now = 600
        self.assertEqual(self.cache.get("a", loader), "fresh")
        self.assertEqual(loader.call_count, 2)

    def test_fifo_capacity_without_read_reordering(self):
        for key in ("a", "b", "c"):
            self.cache.get(key, lambda: key)
        expected_keys = ["catalog-response:" + key for key in ("a", "b", "c")]
        self.assertEqual(self.cache.keys(), expected_keys)
        loader = Mock()
        self.assertEqual(self.cache.get("a", loader), "a")
        loader.assert_not_called()
        self.assertEqual(self.cache.keys(), expected_keys)
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])
        reload_a = Mock(return_value="reloaded")
        self.assertEqual(self.cache.get("a", reload_a), "reloaded")
        reload_a.assert_called_once_with()
        self.assertEqual(self.cache.keys(), [
            "catalog-response:c", "catalog-response:d", "catalog-response:a",
        ])

    def test_none_results_are_cached_until_exact_expiry(self):
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

    def test_expired_entries_release_capacity_and_keys_show_only_live_entries(self):
        for key in ("a", "b"):
            self.cache.get(key, lambda: key)
        self.now = 100
        self.cache.get("c", lambda: "c")
        self.now = 600
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), ["catalog-response:c", "catalog-response:d"])
        self.cache.get("e", lambda: "e")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:c", "catalog-response:d", "catalog-response:e",
        ])
        self.now = 700
        self.assertEqual(self.cache.keys(), ["catalog-response:d", "catalog-response:e"])
        self.now = 1200
        self.assertEqual(self.cache.keys(), [])

    def test_instances_and_sibling_component_have_independent_entries(self):
        other = catalog_detail_cache.create_cache(self.clock)
        sibling = catalog_cache.create_cache(self.clock)
        self.cache.get("a", lambda: "detail")
        self.assertEqual(other.keys(), [])
        self.assertEqual(sibling.keys(), [])
        self.assertEqual(other.get("a", lambda: "other"), "other")
        self.assertEqual(sibling.get("a", lambda: "catalog"), "catalog")
        self.assertEqual(self.cache.get("a", lambda: "unexpected"), "detail")
