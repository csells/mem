import unittest
from unittest.mock import Mock

import catalog_refresh_cache
import catalog_replay_cache


class CatalogReplayCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.cache = catalog_replay_cache.create_cache(lambda: self.now)

    def test_original_approval_fields(self):
        self.assertEqual(catalog_replay_cache.POLICY, {
            "project": "catalog-api",
            "cache": {
                "ttl_seconds": 600,
                "max_entries": 3,
                "eviction_policy": "fifo",
                "namespace": "catalog-response",
                "cache_misses": True,
            },
        })
        self.assertEqual(catalog_replay_cache.SOURCE,
                         "Architecture approval CACHE-17 (2026-09-06), version v1")
        self.assertEqual(catalog_replay_cache.RATIONALE,
                         "Share response-cache behavior across catalog readers; "
                         "cache absent lookups to avoid repeated backend reads.")

    def test_values_and_absent_lookups_expire_at_600_seconds(self):
        for value in ({"id": "a"}, [], None):
            with self.subTest(value=value):
                self.now = 0
                cache = catalog_replay_cache.create_cache(lambda: self.now)
                loader = Mock(return_value=value)
                self.assertEqual(cache.get("a", loader), value)
                for age in (300, 599.999):
                    self.now = age
                    self.assertEqual(cache.get("a", loader), value)
                    loader.assert_called_once_with()
                    self.assertEqual(cache.keys(), ["catalog-response:a"])
                self.now = 600
                self.assertEqual(cache.get("a", loader), value)
                self.assertEqual(loader.call_count, 2)
                self.now = 1200
                self.assertEqual(cache.keys(), [])

    def test_fifo_capacity_includes_absent_lookups_and_reads_keep_order(self):
        loader = Mock(return_value=None)
        self.cache.get("missing", loader)
        for key in ("a", "b"):
            self.cache.get(key, lambda: key)
        self.assertIsNone(self.cache.get("missing", loader))
        loader.assert_called_once_with()
        self.assertEqual(self.cache.keys(), [
            "catalog-response:missing", "catalog-response:a", "catalog-response:b",
        ])
        self.cache.get("c", lambda: "c")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:a", "catalog-response:b", "catalog-response:c",
        ])
        self.assertIsNone(self.cache.get("missing", loader))
        self.assertEqual(loader.call_count, 2)

    def test_expired_entries_free_capacity(self):
        self.cache.get("a", lambda: "a")
        self.now = 100
        for key in ("b", "c"):
            self.cache.get(key, lambda: key)
        self.now = 600
        self.cache.get("d", lambda: "d")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])

    def test_instances_are_independent_and_v2_keeps_its_expiry(self):
        self.cache.get("a", lambda: "replay")
        other = catalog_replay_cache.create_cache(lambda: self.now)
        current = catalog_refresh_cache.create_cache(lambda: self.now)
        self.assertEqual(other.keys(), [])
        self.assertEqual(current.keys(), [])
        self.assertEqual(other.get("a", lambda: "other"), "other")
        self.assertEqual(current.get("a", lambda: "current"), "current")
        self.now = 300
        self.assertEqual(current.keys(), [])
        self.assertEqual(other.get("a", lambda: "unexpected"), "other")
        self.assertEqual(self.cache.get("a", lambda: "unexpected"), "replay")
        self.now = 600
        self.assertEqual(self.cache.keys(), [])
        self.assertEqual(other.keys(), [])
