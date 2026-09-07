import json
import unittest
from unittest.mock import Mock

import catalog_summary_cache


class CatalogSummaryCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.clock = lambda: self.now
        self.cache = catalog_summary_cache.create_cache(self.clock)

    def test_approved_v2_policy_and_fields(self):
        approved = {
            "project": "catalog-api",
            "cache": {
                "ttl_seconds": 300,
                "max_entries": 3,
                "eviction_policy": "fifo",
                "namespace": "catalog-response",
                "cache_misses": True,
            },
        }
        self.assertEqual(json.dumps(catalog_summary_cache.POLICY, sort_keys=True),
                         json.dumps(approved, sort_keys=True))
        self.assertEqual(catalog_summary_cache.SOURCE,
                         "Operations approval CACHE-18 (2026-09-06), version v2")
        self.assertEqual(catalog_summary_cache.RATIONALE,
                         "Reduce stale catalog responses while retaining the other approved cache settings.")

    def test_values_and_none_expire_at_300_seconds(self):
        for value in (["summary"], None):
            with self.subTest(value=value):
                self.now = 0
                cache = catalog_summary_cache.create_cache(self.clock)
                loader = Mock(return_value=value)
                self.assertEqual(cache.get("summary", loader), value)
                self.now = 299.999
                self.assertEqual(cache.get("summary", loader), value)
                loader.assert_called_once_with()
                self.assertEqual(cache.keys(), ["catalog-response:summary"])
                self.now = 300
                replacement = Mock(return_value=["updated"])
                self.assertEqual(cache.get("summary", replacement), ["updated"])
                replacement.assert_called_once_with()
                self.now = 600
                self.assertEqual(cache.keys(), [])

    def test_fifo_capacity_counts_none_and_reads_keep_order(self):
        self.cache.get("a", lambda: None)
        for key in ("b", "c"):
            self.cache.get(key, lambda: "stored")
        loader = Mock(return_value="found")
        self.assertIsNone(self.cache.get("a", loader))
        loader.assert_not_called()
        self.cache.get("d", lambda: "new")
        self.assertEqual(self.cache.keys(), [
            "catalog-response:b", "catalog-response:c", "catalog-response:d",
        ])
        self.assertEqual(self.cache.get("a", loader), "found")
        loader.assert_called_once_with()

    def test_expired_entries_release_capacity(self):
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
        self.cache.get("summary", lambda: "first")
        other = catalog_summary_cache.create_cache(self.clock)
        self.assertEqual(other.keys(), [])
        self.assertEqual(other.get("summary", lambda: "second"), "second")
        unused = Mock()
        self.assertEqual(self.cache.get("summary", unused), "first")
        unused.assert_not_called()
