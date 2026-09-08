"""Runnable cache work and independent oracles for the integration screen.

Only initial_scaffold() and stage_task() are public agent inputs. A direct task
must be selected from actual agent-authored Beads, never synthesized from this
corpus. Oracles stay in the parent process and are not files in the agent project.
Exact named source/rationale fields do not certify surrounding prose.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from membench.runner.memory_lifecycle_corpus import StageName, Version


@dataclass(frozen=True)
class E2EStage:
    name: StageName
    component: str
    expected_version: Version
    authored_task: bool = False


@dataclass(frozen=True)
class E2ECase:
    id: str
    v1_policy: dict[str, Any]
    v2_policy: dict[str, Any]
    v1_source: str
    v2_source: str
    v1_rationale: str
    v2_rationale: str
    stages: tuple[E2EStage, ...]
    decoys: dict[str, str]


def build_e2e_case() -> E2ECase:
    """One fixed case shared by both delivery arms and both supported hosts."""
    initial: dict[str, Any] = {
        "project": "catalog-api",
        "cache": {
            "ttl_seconds": 600,
            "max_entries": 3,
            "eviction_policy": "fifo",
            "namespace": "catalog-response",
            "cache_misses": True,
        },
    }
    revised = copy.deepcopy(initial)
    revised["cache"]["ttl_seconds"] = 300
    return E2ECase(
        id="memory-e2e-catalog-response-cache-v1",
        v1_policy=initial,
        v2_policy=revised,
        v1_source="Architecture approval CACHE-17 (2026-09-06), version v1",
        v2_source="Operations approval CACHE-18 (2026-09-06), version v2",
        v1_rationale=(
            "Share response-cache behavior across catalog readers; cache absent lookups "
            "to avoid repeated backend reads."
        ),
        v2_rationale=(
            "Reduce stale catalog responses while retaining the other approved cache settings."
        ),
        stages=(
            E2EStage("establish", "catalog_cache.py", "v1"),
            E2EStage("direct", "catalog_detail_cache.py", "v1", True),
            E2EStage("search", "catalog_listing_cache.py", "v1"),
            E2EStage("revise", "catalog_refresh_cache.py", "v2"),
            E2EStage("revised_direct", "catalog_preview_cache.py", "v2", True),
            E2EStage("revised_search", "catalog_summary_cache.py", "v2"),
            E2EStage("supplied", "catalog_public_cache.py", "v2"),
            E2EStage("historical", "catalog_replay_cache.py", "v1"),
        ),
        decoys={
            "catalog-admin.response-cache": (
                "Approved catalog-admin response-cache policy: project catalog-admin; "
                "TTL 60 seconds, capacity 20, FIFO, namespace admin-response, no cached misses."
            ),
            "catalog-api.rendered-pages": (
                "Approved catalog-api rendered-page cache; this is HTML rendering, not response "
                "caching. TTL 120 seconds, capacity 50, namespace rendered-pages."
            ),
            "inventory-api.response-cache": (
                "Approved inventory-api response-cache agreement: TTL 900 seconds, capacity 10, "
                "FIFO, namespace inventory-response, cached misses enabled."
            ),
            "catalog-api.export-format": (
                "Approved catalog-api export format: CSV with comma delimiter and UTF-8 encoding."
            ),
        },
    )


_ENGINE = '''"""Generic cache engine; policy belongs to each component."""
from collections import OrderedDict


class ResponseCache:
    def __init__(self, policy, clock):
        if policy["eviction_policy"] != "fifo":
            raise ValueError("only FIFO is implemented by this engine")
        self.policy = dict(policy)
        self.clock = clock
        self.entries = OrderedDict()

    def _purge(self):
        now = self.clock()
        for key, (created, _) in list(self.entries.items()):
            if now - created >= self.policy["ttl_seconds"]:
                del self.entries[key]

    def get(self, key, loader):
        self._purge()
        stored_key = self.policy["namespace"] + ":" + key
        if stored_key in self.entries:
            return self.entries[stored_key][1]
        value = loader()
        if value is not None or self.policy["cache_misses"]:
            while len(self.entries) >= self.policy["max_entries"]:
                self.entries.popitem(last=False)
            self.entries[stored_key] = (self.clock(), value)
        return value

    def keys(self):
        self._purge()
        return list(self.entries)
'''

_README = """# Catalog reader components

This disposable Python project supplies a generic in-memory `ResponseCache` in
`cache_engine.py`. Implement the component requested by the assigned issue.
Python's standard library is sufficient; no dependency installation is required.

Each component module exports:

- `POLICY`: the complete approved nested policy, preserving JSON keys and types.
- `SOURCE` and `RATIONALE`: the exact named approval fields; keep interpretations
  separate from these fields.
- `create_cache(clock)`: returns a working cache governed by that policy. `clock`
  is an injected function returning seconds. Reusing the generic engine is fine.

A cache supports `get(key, loader)`, returning a cached value or calling the
zero-argument loader. Its `keys()` exposes live namespaced keys. Expiry occurs at
age greater than or equal to TTL; reads do not change FIFO insertion order;
expired entries do not consume capacity. The policy decides whether loader
results of `None` are cached. A cache instance owns its own entries.

Retain earlier components and project history. Each new reader is a sibling
component; implementing one does not require deleting earlier work. Run
`python3 -m unittest discover -s tests` for the public API check, and add relevant
component tests when implementing behavior. These checks do not certify that a
component uses the approved policy.
"""

_PUBLIC_TEST = """import unittest
from cache_engine import ResponseCache


class CacheApiTest(unittest.TestCase):
    def test_parameterized_engine(self):
        now = [0]
        policy = {"ttl_seconds": 2, "max_entries": 2, "eviction_policy": "fifo",
                  "namespace": "example", "cache_misses": False}
        cache = ResponseCache(policy, lambda: now[0])
        self.assertEqual(cache.get("a", lambda: "first"), "first")
        self.assertEqual(cache.get("a", lambda: "later"), "first")
        self.assertEqual(cache.keys(), ["example:a"])
        now[0] = 2
        self.assertEqual(cache.get("a", lambda: "later"), "later")
"""


def initial_scaffold(case: E2ECase) -> dict[str, str]:
    """Return public files without target settings or approval text."""
    if case.id != "memory-e2e-catalog-response-cache-v1":
        raise ValueError("unsupported integration corpus")
    return {"cache_engine.py": _ENGINE, "README.md": _README, "tests/test_api.py": _PUBLIC_TEST}


def _title(stage: E2EStage) -> str:
    return f"Implement {Path(stage.component).stem} component"


def _approval(case: E2ECase, version: Version) -> str:
    policy = case.v1_policy if version == "v1" else case.v2_policy
    source = case.v1_source if version == "v1" else case.v2_source
    rationale = case.v1_rationale if version == "v1" else case.v2_rationale
    return (
        "```json\n" + json.dumps(policy, indent=2) + "\n```\n\n"
        f"SOURCE: {source}\n\nRATIONALE: {rationale}"
    )


def _follow_up(case: E2ECase, name: Literal["direct", "revised_direct"]) -> str:
    successor = next(stage for stage in case.stages if stage.name == name)
    return (
        f"\n\nCreate one follow-up issue titled '{_title(successor)}'. Its body must ask "
        f"a teammate to implement `{successor.component}` using the same approved response-cache "
        "agreement and the README component API, including create_cache, POLICY, SOURCE, and "
        "RATIONALE. Include a usable reference to the durable agreement you actually retained "
        "and explain why it applies. Do not implement that follow-up component now."
    )


def stage_task(case: E2ECase, stage: E2EStage) -> dict[str, str]:
    """Describe real issue work; authored direct task bodies are never runner inputs."""
    body = (
        f"Implement `{stage.component}` for project catalog-api using the component API in "
        "README.md: POLICY, SOURCE, RATIONALE, and a working create_cache(clock). Verify the "
        "resulting behavior. Preserve earlier project files and components.\n\n"
    )
    if stage.name == "establish":
        body += (
            "The architecture review has approved the following reusable response-cache "
            "agreement for catalog readers. Implement this initial approval (v1). Future "
            "readers use the standing agreement; audit replay must also remain able to "
            "reproduce this original approval after a permanent revision.\n\n"
            + _approval(case, "v1")
            + _follow_up(case, "direct")
        )
    elif stage.name == "revise":
        body += (
            "Operations permanently revises the standing catalog-api response-cache "
            "agreement to v2. Apply only the change below, retaining every other approved "
            "setting and type. This is a lasting change for future catalog readers. Earlier "
            "components remain historical implementations; keep the original v1 approval "
            "available for audit replay.\n\n```json\n"
            '{"cache": {"ttl_seconds": 300}}\n```\n\n'
            f"SOURCE: {case.v2_source}\n\nRATIONALE: {case.v2_rationale}"
            + _follow_up(case, "revised_direct")
        )
    elif stage.name == "supplied":
        body += (
            "This public reader reproduces the existing v2 agreement below. These are the "
            "complete policy and approval fields needed for this task.\n\n" + _approval(case, "v2")
        )
    elif stage.name == "historical":
        body += (
            "This audit replay must reproduce the original response-cache approval CACHE-17, "
            "version v1. The standing agreement remains v2; this historical implementation "
            "does not revise it. Use the original settings and approval fields."
        )
    else:
        version = "original v1" if stage.expected_version == "v1" else "permanently revised v2"
        body += (
            "This new catalog reader needs the existing agreement for caching API responses "
            f"in catalog-api, {version}. Reproduce that agreement and its approval fields. "
            "This is another consumer of the agreement."
        )
    return {"title": _title(stage), "body": body}


def find_successor_task(tasks: Sequence[dict[str, Any]], title: str) -> dict[str, Any]:
    """Select an actual author-created issue; missing references remain missing."""
    matched = [task for task in tasks if task.get("title") == title]
    status = "selected" if len(matched) == 1 else "missing" if not matched else "ambiguous"
    return {
        "status": status,
        "task": matched[0] if status == "selected" else None,
        "matches": [task.get("id") for task in matched],
    }


# This generic probe receives a module path, not expected policy values. Its fixed
# observations cover both versions; only the parent decides which result is right.
_PROBE = r"""
import importlib.util
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("tested_component", root / sys.argv[2])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

now = [0]
loads = [0]
def load():
    loads[0] += 1
    return loads[0]
cache = module.create_cache(lambda: now[0])
ttl = []
for moment in (0, 299, 300, 599, 600):
    now[0] = moment
    ttl.append(cache.get("ttl", load))

loads[0] = 0
cache = module.create_cache(lambda: 0)
fifo = [cache.get(key, load) for key in ("a", "b", "c", "a", "d", "b", "a")]
cache = module.create_cache(lambda: 0)
cache.get("item", lambda: "value")
keys = cache.keys()
misses = [0]
def miss():
    misses[0] += 1
    return None
cache = module.create_cache(lambda: 0)
miss_values = [cache.get("missing", miss), cache.get("missing", miss)]
print(json.dumps({"policy": module.POLICY, "source": module.SOURCE,
                  "rationale": module.RATIONALE, "ttl": ttl, "fifo": fifo,
                  "namespaced_keys": keys, "miss_loads": misses[0],
                  "miss_values": miss_values}, allow_nan=False))
"""


def _exact(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _exact(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _exact(left, right) for left, right in zip(actual, expected, strict=True)
        )
    return bool(actual == expected)


def grade_component(
    workspace: Path,
    stage: E2EStage,
    case: E2ECase,
    *,
    timeout_seconds: float = 10,
    process_prefix: Sequence[str] = (),
    python_executable: str | None = None,
) -> dict[str, Any]:
    """Execute actual component behavior; grade against independent parent oracles.

    Environment isolation alone does not protect the filesystem. The experiment
    driver must supply an OS sandbox through process_prefix before importing
    agent-generated code, and an interpreter that its profile permits. Empty
    defaults support trusted test scaffolding. The probe disables bytecode writes,
    exposes no real tools through PATH, and creates no hidden answer file.
    """
    artifact = workspace / stage.component
    if artifact.is_symlink():
        return {"passed": False, "reason": "artifact_symlink"}
    if not artifact.is_file():
        return {"passed": False, "reason": "artifact_missing"}
    try:
        result = subprocess.run(
            [
                *process_prefix,
                python_executable if python_executable is not None else sys.executable,
                "-I",
                "-B",
                "-c",
                _PROBE,
                str(workspace.resolve()),
                stage.component,
            ],
            cwd=workspace,
            env={"PATH": ""},
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {"passed": False, "reason": "probe_timeout"}
    evidence: dict[str, Any] = {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if result.returncode:
        return {"passed": False, "reason": "probe_failed", **evidence}
    try:
        actual = json.loads(result.stdout.splitlines()[-1])
    except (ValueError, IndexError):
        return {"passed": False, "reason": "probe_output_invalid", **evidence}
    if not isinstance(actual, Mapping):
        return {"passed": False, "reason": "probe_output_invalid", **evidence}
    original = stage.expected_version == "v1"
    policy = case.v1_policy if original else case.v2_policy
    checks = {
        "ttl_boundary": _exact(actual.get("ttl"), [1, 1, 1, 1, 2] if original else [1, 1, 2, 2, 3]),
        "fifo_capacity": _exact(actual.get("fifo"), [1, 2, 3, 1, 4, 2, 5]),
        "namespace": _exact(actual.get("namespaced_keys"), ["catalog-response:item"]),
        "cached_misses": (
            _exact(actual.get("miss_loads"), 1) and _exact(actual.get("miss_values"), [None, None])
        ),
    }
    dimensions: dict[str, dict[str, Any]] = {
        "policy": {"passed": _exact(actual.get("policy"), policy)},
        "source": {
            "passed": _exact(actual.get("source"), case.v1_source if original else case.v2_source)
        },
        "rationale": {
            "passed": _exact(
                actual.get("rationale"), case.v1_rationale if original else case.v2_rationale
            )
        },
        "behavior": {"passed": all(checks.values()), "checks": checks},
    }
    return {
        "passed": all(dimension["passed"] for dimension in dimensions.values()),
        **dimensions,
        "surrounding_prose": "not_assessed",
        "observations": actual,
        **evidence,
    }
