from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from membench.beads_ordering.models import FrozenCorpus, MemoryFixture

RANKED_SEARCHING_PRIORS: tuple[str, ...] = (
    "indegree",
    "outdegree",
    "pagerank",
    "reverse-pagerank",
    "hits-authority",
    "hits-hub",
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


class StructuralOrderSourceError(RuntimeError):
    pass


def _resolve_structural_order_module(source: Path) -> Path:
    """Find the benchmark entrypoint without depending on its checkout name."""

    entrypoint = Path("cmd") / "benchmark0" / "main.go"
    if (source / entrypoint).is_file():
        return source
    modules = sorted(path.parent.parent.parent for path in source.glob(f"**/{entrypoint}"))
    if not modules:
        raise StructuralOrderSourceError(
            f"structural-order source has no {entrypoint} entrypoint: {source}"
        )
    if len(modules) > 1:
        rendered = ", ".join(str(module) for module in modules)
        raise StructuralOrderSourceError(
            f"structural-order source has multiple benchmark entrypoints: {rendered}"
        )
    return modules[0]


def _artifact_memory(memory: MemoryFixture) -> dict[str, object]:
    return {
        "id": memory.id,
        "project_id": "membench-beads-ordering",
        "title": memory.title,
        "body": memory.body,
        "key": memory.key,
        "aliases": list(memory.aliases),
        "references": [
            {"target_id": target, "kind": "fixture-authored"} for target in memory.references
        ],
        "stored_provenance": {
            "kind": memory.provenance,
            "source_path": f"frozen/{memory.id}.md",
            "source_type": "membench-fixture",
        },
    }


def artifact_structural_orders(
    memories: tuple[MemoryFixture, ...],
    *,
    artifact_repo: Path,
    runner: Runner = subprocess.run,
) -> dict[str, tuple[str, ...]]:
    """Invoke the pinned structural-order implementation and extract static orders."""

    module = _resolve_structural_order_module(artifact_repo)
    with tempfile.TemporaryDirectory(prefix="membench-structural-order-") as raw:
        temp = Path(raw)
        corpus_path = temp / "corpus.json"
        spec_path = temp / "spec.json"
        out = temp / "out"
        corpus_path.write_text(
            json.dumps([_artifact_memory(memory) for memory in memories]), encoding="utf-8"
        )
        spec_path.write_text(
            json.dumps(
                [
                    {
                        "id": "membench-full-structural-order",
                        "difficulty": "mechanical",
                        "prompt": "Materialize the complete frozen corpus order.",
                        "search": "Operational note",
                        "checkpoints": [
                            {
                                "id": "never-resolves",
                                "description": "order extraction only",
                                "evidence_any": ["__membench_unreachable_evidence__"],
                            }
                        ],
                    }
                ]
            ),
            encoding="utf-8",
        )
        completed = runner(
            [
                "go",
                "run",
                "./cmd/benchmark0",
                "-corpus",
                str(corpus_path),
                "-spec",
                str(spec_path),
                "-out",
                str(out),
            ],
            cwd=module,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
        if completed.returncode != 0:
            raise StructuralOrderSourceError(
                f"structural-order source failed: {completed.stderr.strip()}"
            )
        try:
            trials = json.loads((out / "trials.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StructuralOrderSourceError(
                "structural-order source did not emit valid trials.json"
            ) from exc

    expected = {memory.id for memory in memories}
    orders: dict[str, tuple[str, ...]] = {}
    for trial in trials:
        if not isinstance(trial, dict) or trial.get("ordering") not in RANKED_SEARCHING_PRIORS:
            continue
        name = str(trial["ordering"])
        ids = tuple(str(memory_id) for memory_id in trial.get("matched_ids", []))
        if name not in orders:
            orders[name] = ids
        elif orders[name] != ids:
            raise StructuralOrderSourceError(
                f"structural-order source emitted inconsistent {name} orders across policies"
            )
    if set(orders) != set(RANKED_SEARCHING_PRIORS):
        raise StructuralOrderSourceError(
            "structural-order source omitted one or more requested structural priors"
        )
    for name, ids in orders.items():
        if len(ids) != len(expected) or set(ids) != expected:
            raise StructuralOrderSourceError(
                f"structural-order source {name} is not a permutation of the corpus"
            )
    return orders


def enrich_with_ranked_searching(
    corpus: FrozenCorpus,
    *,
    artifact_repo: Path,
    order_fn: Callable[..., Mapping[str, tuple[str, ...]]] = artifact_structural_orders,
) -> FrozenCorpus:
    ranks_by_id: dict[str, dict[str, dict[str, int]]] = {
        memory.id: {
            size: dict(priors) for size, priors in memory.structural_ranks_by_corpus.items()
        }
        for memory in corpus.memories
    }
    for size in sorted({task.corpus_size for task in corpus.tasks}):
        memories = corpus.memories[:size]
        orders = order_fn(memories, artifact_repo=artifact_repo)
        for prior, ids in orders.items():
            for position, memory_id in enumerate(ids, start=1):
                ranks_by_id[memory_id].setdefault(str(size), {})[prior] = position
    enriched = tuple(
        memory.model_copy(update={"structural_ranks_by_corpus": ranks_by_id[memory.id]})
        for memory in corpus.memories
    )
    source_sha = corpus.structural_order_source_git_sha
    if order_fn is artifact_structural_orders:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=artifact_repo,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0:
            raise StructuralOrderSourceError(
                f"cannot resolve structural-order source commit: {completed.stderr.strip()}"
            )
        source_sha = completed.stdout.strip()
    return corpus.model_copy(
        update={
            "memories": enriched,
            "structural_order_source_git_sha": source_sha,
        }
    )
