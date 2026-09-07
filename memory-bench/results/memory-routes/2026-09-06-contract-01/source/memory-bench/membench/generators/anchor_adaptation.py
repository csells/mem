"""Offline adaptation of BIG-bench ``list_functions`` into the real-anchor JSONL.

The real-anchor leg of the schema-induction headline needs an EXTERNAL corpus
where a latent rule must be INDUCED from instances (mem-mmuu: the prior anchor
was 2 hand-written rows with the rule verbatim in every episode). BIG-bench
``list_functions`` (Apache-2.0) carries exactly that shape: each subtask states
a natural-language target function (the latent rule) and gives numeric
input→output examples (the episodes) that never contain the rule text.

The pipeline is a frozen, mechanical transform:

* ``fixtures/external_anchor/raw/`` holds the upstream ``task.json`` files
  byte-for-byte, fetched once at a pinned upstream commit (the data-prep step,
  ``scripts/adapt_external_anchor.py fetch``);
* ``adapt_raw_dir`` + ``render_anchor_jsonl`` derive the anchor JSONL
  deterministically from the raw files — regex rule extraction, fixed episode
  formatting, no model call;
* ``AnchorManifest`` records provenance (upstream repo/commit/license, canary
  GUID) plus SHA-256 hashes of every raw file and of the rendered JSONL, and
  ``verify_anchor`` fails closed on raw tampering, fixture edits, adapter
  drift, a corpus below the ``MIN_ANCHOR_TASKS`` floor, and any row whose
  latent rule leaks into its episodes/probe (mirrors
  ``world_manifest.verify_world``).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from membench.generators.external_anchor import load_external_schema_sequences
from membench.generators.world_manifest import VerifyResult

ADAPTER_VERSION = "list-functions-anchor.v2"
ANCHOR_MANIFEST_VERSION = "anchor-manifest.v1"
MANIFEST_FILE = "manifest.json"
RAW_DIR = "raw"

# The anchor must stay a real sample, not a toy: the mem-mmuu audit flagged the
# 2-row hand-written fixture as carrying zero induction signal.
MIN_ANCHOR_TASKS = 24
EPISODES_PER_TASK = 8

_RULE_RE = re.compile(r'The target function is "([^"]*)"')
_SOURCE = "bigbench-list-functions"
_SOURCE_REPO = "google/BIG-bench"
_SOURCE_LICENSE = "Apache-2.0"
_PROBE = (
    "What function maps each input list to its output list in the examples "
    "recorded above? State the rule in natural language."
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def adapt_raw_task(raw: dict[str, Any]) -> dict[str, Any]:
    """Adapt one upstream ``task.json`` into an anchor row — pure and mechanical.

    The latent rule is the quoted target function in the task description; the
    episodes are the first ``EPISODES_PER_TASK`` input→output examples. Fails
    closed when the rule sentence or enough examples are missing."""
    name = raw["name"]
    match = _RULE_RE.search(raw["description"])
    if match is None:
        raise ValueError(f"task {name!r}: no 'The target function is ...' sentence to extract")
    latent_rule = match.group(1)
    if not latent_rule.strip():
        raise ValueError(
            f"task {name!r}: extracted latent_rule is empty — an empty rule would "
            "silently bypass the downstream verbatim-leak check"
        )

    examples = raw["examples"][:EPISODES_PER_TASK]
    if len(examples) < 3:
        raise ValueError(f"task {name!r}: need >= 3 examples, got {len(examples)}")
    episodes = [
        f"example {i}: input {ex['input']} -> output {ex['target']}"
        for i, ex in enumerate(examples)
    ]
    return {
        "task_id": f"list-functions-{name}",
        "source": _SOURCE,
        "latent_rule": latent_rule,
        "episodes": episodes,
        "probe": _PROBE,
    }


def adapt_raw_dir(raw_dir: str | Path) -> list[dict[str, Any]]:
    """Adapt every raw task file, in sorted-filename order (determinism)."""
    paths = sorted(Path(raw_dir).glob("*.json"))
    if not paths:
        raise ValueError(f"no raw task files in {raw_dir}")
    return [adapt_raw_task(json.loads(p.read_text(encoding="utf-8"))) for p in paths]


def render_anchor_jsonl(rows: list[dict[str, Any]]) -> str:
    """Canonical JSONL rendering — sorted keys, compact, one row per line."""
    return (
        "\n".join(
            json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            for row in rows
        )
        + "\n"
    )


class AnchorManifest(BaseModel):
    """Provenance + integrity record for the frozen external anchor (mem-mmuu)."""

    schema_version: str = ANCHOR_MANIFEST_VERSION
    adapter_version: str = ADAPTER_VERSION
    source: str = _SOURCE
    source_repo: str = _SOURCE_REPO
    source_commit: str
    source_license: str = _SOURCE_LICENSE
    canary_guid: str
    n_tasks: int
    episodes_per_task: int = EPISODES_PER_TASK
    raw_sha256: dict[str, str]
    anchor_sha256: str


def build_anchor_manifest(
    anchor_dir: str | Path, anchor_path: str | Path, *, source_commit: str
) -> AnchorManifest:
    """Hash the frozen raw corpus + the rendered anchor into a manifest.

    The canary GUID is read off the raw files (BIG-bench asks derived artifacts
    to carry it) and must be a single consistent value."""
    raw_dir = Path(anchor_dir) / RAW_DIR
    raw_paths = sorted(raw_dir.glob("*.json"))
    canaries = {json.loads(p.read_text(encoding="utf-8")).get("canary", "") for p in raw_paths}
    if len(canaries) != 1:
        raise ValueError(f"raw corpus has {len(canaries)} distinct canary strings, expected 1")

    return AnchorManifest(
        source_commit=source_commit,
        canary_guid=canaries.pop(),
        n_tasks=len(raw_paths),
        raw_sha256={p.name: _sha256_bytes(p.read_bytes()) for p in raw_paths},
        anchor_sha256=_sha256_bytes(Path(anchor_path).read_bytes()),
    )


def write_anchor_manifest(manifest: AnchorManifest, anchor_dir: str | Path) -> Path:
    path = Path(anchor_dir) / MANIFEST_FILE
    path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def read_anchor_manifest(anchor_dir: str | Path) -> AnchorManifest:
    text = (Path(anchor_dir) / MANIFEST_FILE).read_text(encoding="utf-8")
    return AnchorManifest.model_validate_json(text)


def verify_anchor(anchor_dir: str | Path, anchor_path: str | Path) -> VerifyResult:
    """Verify the frozen anchor reproduces from its raw corpus with no network.

    Fail-closed checks against the manifest: raw-file hashes (upstream tamper),
    the checked-in JSONL's hash (fixture edits), manifest metadata consistency
    (``n_tasks`` vs the hash dict, the ``MIN_ANCHOR_TASKS`` floor, one canary
    GUID across the raw corpus), a full re-adaptation of raw → JSONL (adapter
    drift / non-determinism), and a load through the anchor loader so the
    verbatim-leak rejection is part of this gate rather than left to whichever
    caller happens to load the fixture (mem-mmuu: the toy-anchor failure mode
    must fail verification, not just loading)."""
    anchor_dir = Path(anchor_dir)
    manifest = read_anchor_manifest(anchor_dir)
    mismatches: list[str] = []

    raw_dir = anchor_dir / RAW_DIR
    raw_paths = sorted(raw_dir.glob("*.json"))
    if {p.name for p in raw_paths} != set(manifest.raw_sha256):
        mismatches.append("raw file set differs from manifest")
    for p in raw_paths:
        expected = manifest.raw_sha256.get(p.name)
        if expected is not None and (got := _sha256_bytes(p.read_bytes())) != expected:
            mismatches.append(f"raw {p.name} sha256 {got[:12]} != manifest {expected[:12]}")

    if (got := _sha256_bytes(Path(anchor_path).read_bytes())) != manifest.anchor_sha256:
        mismatches.append(f"anchor sha256 {got[:12]} != manifest {manifest.anchor_sha256[:12]}")

    hashes_ok = not mismatches

    if manifest.n_tasks != len(manifest.raw_sha256):
        mismatches.append(
            f"manifest n_tasks {manifest.n_tasks} != {len(manifest.raw_sha256)} hashed raw files"
        )
    if manifest.n_tasks < MIN_ANCHOR_TASKS:
        mismatches.append(
            f"n_tasks {manifest.n_tasks} is below the MIN_ANCHOR_TASKS floor "
            f"{MIN_ANCHOR_TASKS} — the anchor must not be a toy sample"
        )
    canaries = {json.loads(p.read_text(encoding="utf-8")).get("canary", "") for p in raw_paths}
    if canaries and canaries != {manifest.canary_guid}:
        mismatches.append("raw corpus canary GUIDs differ from the manifest canary_guid")

    if hashes_ok:
        rerendered = render_anchor_jsonl(adapt_raw_dir(raw_dir))
        if (got := _sha256_bytes(rerendered.encode("utf-8"))) != manifest.anchor_sha256:
            mismatches.append(
                f"re-adapted anchor sha256 {got[:12]} != manifest "
                f"{manifest.anchor_sha256[:12]} (adapter drifted or is non-deterministic)"
            )
        try:
            load_external_schema_sequences(anchor_path)
        except ValueError as err:
            mismatches.append(f"anchor fails the loader's induction-honesty checks: {err}")

    return VerifyResult(ok=not mismatches, mismatches=tuple(mismatches))
