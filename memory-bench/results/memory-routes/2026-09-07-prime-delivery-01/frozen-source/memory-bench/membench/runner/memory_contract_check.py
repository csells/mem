"""Public component-interface check for a new experiment condition.

The installed test checks structure/types, not approved facts or runtime behavior.
It contains no oracle imports, source labels, version identifiers, or approved
configuration values. Run it through the project's existing unittest discovery.
Offline callers may execute this same source and call check_component(path) for
one preserved artifact; its normal test still checks every present component.
"""

PUBLIC_TEST_PATH = "tests/test_component_contract.py"

PUBLIC_TEST_SOURCE = '''"""Check the public component interface, not approved values or behavior."""

import importlib.util
import sys
import unittest
from pathlib import Path


class ComponentContractTest(unittest.TestCase):
    def check_component(self, path):
        self.assertFalse(path.is_symlink(), "Component must be a regular file")
        self.assertTrue(path.is_file(), "Component file is missing")
        root = str(path.parent.resolve())
        if root not in sys.path:
            sys.path.insert(0, root)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        self.assertTrue(hasattr(module, "POLICY"), "Missing POLICY export")
        policy = module.POLICY
        self.assertIs(type(policy), dict, "POLICY must be a dict")
        self.assertEqual(set(policy), {"project", "cache"}, "POLICY keys")
        self.assertIs(type(policy["project"]), str, "POLICY.project must be a str")
        cache = policy["cache"]
        self.assertIs(type(cache), dict, "POLICY.cache must be a dict")
        fields = {
            "ttl_seconds": int,
            "max_entries": int,
            "eviction_policy": str,
            "namespace": str,
            "cache_misses": bool,
        }
        self.assertEqual(set(cache), set(fields), "POLICY.cache keys")
        for field, expected_type in fields.items():
            self.assertIs(type(cache[field]), expected_type, "POLICY.cache." + field)
        for name in ("SOURCE", "RATIONALE"):
            self.assertTrue(hasattr(module, name), "Missing " + name + " export")
            self.assertIs(type(getattr(module, name)), str, name + " must be a str")
        self.assertTrue(callable(getattr(module, "create_cache", None)),
                        "create_cache must be callable")

    def test_public_contract(self):
        root = Path(__file__).resolve().parents[1]
        paths = sorted(root.glob("catalog_*cache.py"))
        self.assertTrue(paths, "No catalog cache components found")
        for path in paths:
            with self.subTest(component=path.name):
                self.check_component(path)


if __name__ == "__main__":
    unittest.main()
'''
