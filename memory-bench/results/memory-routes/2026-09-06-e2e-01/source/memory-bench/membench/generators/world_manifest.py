"""§Determinism — freeze a world with a provenance manifest, and verify reproduction.

NeMo world generation is NOT byte-reproducible (the LLM surface varies run to run),
so the FROZEN ``world.json`` is the durable artifact, not the seed. What IS
deterministic is everything downstream: given a frozen world + project, the Phase-2
materialiser re-derives byte-identical sequences from the recorded seed + args,
with no model call.

This module pins that contract:

* ``build_manifest`` records provenance (seed, NIM model, generator versions, task
  args) plus SHA-256 hashes of the frozen world, project and sequences.
* ``write_manifest`` / ``read_manifest`` persist it as ``manifest.json`` beside the
  world (the ``write_world`` location).
* ``verify_world`` reads a frozen world dir, re-hashes the frozen files (detects
  tampering) and RE-MATERIALISES the sequences from the manifest's args (detects
  materialiser drift / non-determinism) — proving the fixture reproduces its task
  instances WITHOUT NeMo. CI-safe: no SDK, no model.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from membench.generators.enterprise_workflow import (
    GENERATOR_VERSION as WORKFLOW_GENERATOR_VERSION,
)
from membench.generators.enterprise_workflow import (
    materialize_world,
)
from membench.generators.nemo.world_builder import read_world
from membench.schemas.sequence import BenchmarkSequence
from membench.schemas.world import WORLD_SCHEMA_VERSION, EnterpriseWorld, Project

WORLD_MANIFEST_VERSION = "world-manifest.v1"
MANIFEST_FILE = "manifest.json"


def _canonical_sha256(payload: Any) -> str:
    """SHA-256 over canonical JSON (sorted keys) so the hash is stable across
    serializer key-order changes."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _hash_model(model: BaseModel) -> str:
    return _canonical_sha256(model.model_dump(mode="json"))


def _hash_sequences(sequences: list[BenchmarkSequence]) -> str:
    return _canonical_sha256([s.model_dump(mode="json") for s in sequences])


class WorldManifest(BaseModel):
    """Provenance + integrity record for one frozen world (mem-ge51)."""

    schema_version: str = WORLD_MANIFEST_VERSION
    world_schema_version: str = WORLD_SCHEMA_VERSION
    workflow_generator_version: str = WORKFLOW_GENERATOR_VERSION
    seed: int
    nim_model: str
    n_tasks: int
    facts_per_task: int
    # Whether the sequences were materialised in the tool-requiring shape (mem-31vl).
    # Load-bearing for verify_world: it must re-materialise with the same flag or the
    # sequence hashes diverge. Defaults False so manifests frozen before this field
    # (text-answer shape) still read back and verify.
    tool_requiring: bool = False
    world_sha256: str
    project_sha256: str
    sequences_sha256: str


def build_manifest(
    world: EnterpriseWorld,
    project: Project,
    sequences: list[BenchmarkSequence],
    *,
    nim_model: str,
    n_tasks: int,
    facts_per_task: int,
    seed: int | None = None,
    tool_requiring: bool = False,
) -> WorldManifest:
    """Build the manifest for a frozen world. ``seed`` defaults to the world's seed
    (the seed the materialiser used). ``tool_requiring`` must match the flag the
    sequences were materialised with so ``verify_world`` reproduces them."""
    return WorldManifest(
        seed=world.seed if seed is None else seed,
        nim_model=nim_model,
        n_tasks=n_tasks,
        facts_per_task=facts_per_task,
        tool_requiring=tool_requiring,
        world_sha256=_hash_model(world),
        project_sha256=_hash_model(project),
        sequences_sha256=_hash_sequences(sequences),
    )


def write_manifest(manifest: WorldManifest, *, world_dir: str | Path) -> Path:
    """Write ``manifest.json`` into a frozen world dir (the ``write_world`` location)."""
    path = Path(world_dir) / MANIFEST_FILE
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return path


def read_manifest(world_dir: str | Path) -> WorldManifest:
    text = (Path(world_dir) / MANIFEST_FILE).read_text(encoding="utf-8")
    return WorldManifest.model_validate_json(text)


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of reproducing a frozen world. ``ok`` is true only when the frozen
    files are intact AND the materialiser re-derives byte-identical sequences;
    ``mismatches`` names every failed check."""

    ok: bool
    mismatches: tuple[str, ...]


def verify_world(world_dir: str | Path) -> VerifyResult:
    """Verify a frozen world reproduces its task instances with no model call.

    Re-hashes the frozen world/project (detects edited fixtures) and re-materialises
    the sequences from the manifest's seed + args (detects materialiser drift),
    comparing every hash to the manifest."""
    world, project = read_world(world_dir)
    manifest = read_manifest(world_dir)
    mismatches: list[str] = []

    if (got := _hash_model(world)) != manifest.world_sha256:
        mismatches.append(f"world_sha256 {got[:12]} != manifest {manifest.world_sha256[:12]}")
    if (got := _hash_model(project)) != manifest.project_sha256:
        mismatches.append(f"project_sha256 {got[:12]} != manifest {manifest.project_sha256[:12]}")

    sequences = materialize_world(
        world,
        project,
        n_tasks=manifest.n_tasks,
        facts_per_task=manifest.facts_per_task,
        seed=manifest.seed,
        tool_requiring=manifest.tool_requiring,
    )
    if (got := _hash_sequences(sequences)) != manifest.sequences_sha256:
        mismatches.append(
            f"sequences_sha256 {got[:12]} != manifest {manifest.sequences_sha256[:12]} "
            "(materialiser is non-deterministic or drifted)"
        )

    return VerifyResult(ok=not mismatches, mismatches=tuple(mismatches))
