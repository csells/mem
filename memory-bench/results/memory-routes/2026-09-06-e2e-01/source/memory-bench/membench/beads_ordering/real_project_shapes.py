from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from statistics import fmean
from typing import Protocol

from membench.beads_ordering.analysis import percentile
from membench.beads_ordering.models import CompactMemory, DiscoveryPage, OrderingArm

_PROBE_PROTOCOL = "native-compact-v1"
_TOKEN_RE = re.compile(r"[a-z][a-z0-9]{3,}")
_PROBE_KINDS = ("key-token", "content-bigram")
_ALLOWED_FAILURE_CODES = frozenset(
    {
        "bd-error",
        "duplicate-workspace",
        "malformed-output",
        "timeout",
        "unsupported-memory-surface",
    }
)


class DiscoveryClient(Protocol):
    def page(self, query: str, arm: OrderingArm, continuation: str = "") -> DiscoveryPage: ...


@dataclass(frozen=True)
class ProjectShape:
    """Private-free numeric result for one workspace.

    The source path, Memory records, and derived probes deliberately do not
    survive the per-project collection boundary.
    """

    memory_count: int
    key_match_counts: tuple[int, ...] = ()
    content_match_counts: tuple[int, ...] = ()
    link_outdegrees: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        values = (*self.key_match_counts, *self.content_match_counts)
        if self.memory_count < 0 or any(value < 0 for value in values):
            raise ValueError("Memory and match counts must be non-negative")
        if self.link_outdegrees is not None and any(value < 0 for value in self.link_outdegrees):
            raise ValueError("link outdegrees must be non-negative")

    def to_private_free_dict(self) -> dict[str, int]:
        return {
            "memory_count": self.memory_count,
            "key_probe_count": len(self.key_match_counts),
            "content_probe_count": len(self.content_match_counts),
            "link_observation_count": (
                0 if self.link_outdegrees is None else len(self.link_outdegrees)
            ),
        }


@dataclass(frozen=True)
class ShapeSampling:
    workspace_candidates: int
    unique_workspaces: int
    workspaces_scanned: int
    workspaces_with_memories: int
    unique_memory_snapshots: int
    duplicate_memory_snapshots: int
    failures_by_code: Mapping[str, int]

    def __post_init__(self) -> None:
        counts = (
            self.workspace_candidates,
            self.unique_workspaces,
            self.workspaces_scanned,
            self.workspaces_with_memories,
            self.unique_memory_snapshots,
            self.duplicate_memory_snapshots,
            *self.failures_by_code.values(),
        )
        if any(value < 0 for value in counts):
            raise ValueError("sampling counts must be non-negative")


@dataclass(frozen=True)
class ShapeProvenance:
    mem_git_sha: str
    mem_git_diff_sha256: str
    beads_git_sha: str
    beads_git_diff_sha256: str
    beads_bin_sha256: str
    collector_source_sha256: str
    mem_git_dirty: bool
    beads_git_dirty: bool

    def __post_init__(self) -> None:
        for name, value, length in (
            ("mem_git_sha", self.mem_git_sha, 40),
            ("mem_git_diff_sha256", self.mem_git_diff_sha256, 64),
            ("beads_git_sha", self.beads_git_sha, 40),
            ("beads_git_diff_sha256", self.beads_git_diff_sha256, 64),
            ("beads_bin_sha256", self.beads_bin_sha256, 64),
            ("collector_source_sha256", self.collector_source_sha256, 64),
        ):
            if len(value) != length or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError(f"{name} must be a lowercase {length}-character hex digest")


@dataclass(frozen=True)
class WorkspaceDiscovery:
    workspace_candidates: int
    workspaces: tuple[Path, ...]


ClientFactory = Callable[[Path], DiscoveryClient]


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(value.lower()))


def _bounded_probe_set(
    candidates: Sequence[str], *, kind: str, limit: int, seed: int
) -> tuple[str, ...]:
    unique = set(candidates)
    ordered = sorted(
        unique,
        key=lambda value: hashlib.sha256(f"{seed}\0{kind}\0{value}".encode()).hexdigest(),
    )
    return tuple(ordered[:limit])


def derive_native_probes(
    items: Sequence[CompactMemory], *, max_per_kind: int = 20, seed: int = 5879
) -> dict[str, tuple[str, ...]]:
    """Derive private, deterministic probes from the compact R6 projection.

    Probes exist only long enough to call the unchanged Beads lexical matcher.
    Callers must persist the resulting counts, never these strings.
    """

    if max_per_kind < 1:
        raise ValueError("max_per_kind must be positive")
    key_candidates: list[str] = []
    content_candidates: list[str] = []
    for item in items:
        key_candidates.extend(_tokens(item.key))
        content_tokens = _tokens(f"{item.title} {item.excerpt}")
        content_candidates.extend(f"{left} {right}" for left, right in pairwise(content_tokens))
    return {
        "key-token": _bounded_probe_set(
            key_candidates, kind="key-token", limit=max_per_kind, seed=seed
        ),
        "content-bigram": _bounded_probe_set(
            content_candidates, kind="content-bigram", limit=max_per_kind, seed=seed
        ),
    }


def measure_project_shape(
    client: DiscoveryClient,
    *,
    max_probes_per_kind: int = 20,
    seed: int = 5879,
    inventory: DiscoveryPage | None = None,
) -> ProjectShape:
    """Measure one project and discard all content-bearing values at return."""

    inventory = inventory or client.page("", OrderingArm.KEY)
    if not inventory.complete or len(inventory.items) != inventory.total_matched:
        raise ValueError("unbounded Memory inventory was incomplete")
    probes = derive_native_probes(inventory.items, max_per_kind=max_probes_per_kind, seed=seed)

    def counts(kind: str) -> tuple[int, ...]:
        return tuple(client.page(probe, OrderingArm.KEY).total_matched for probe in probes[kind])

    return ProjectShape(
        memory_count=inventory.total_matched,
        key_match_counts=counts("key-token"),
        content_match_counts=counts("content-bigram"),
        # Legacy keyed Memory exposes no canonical Bead References. Treating
        # frontmatter-looking prose as links would fabricate structure.
        link_outdegrees=None,
    )


def _excluded_scan_path(path: Path) -> bool:
    parts = path.parts
    if any(part in {".git", ".mem", ".venv", "node_modules", "__pycache__"} for part in parts):
        return True
    normalized = path.as_posix()
    return "/memory-bench/results/" in f"{normalized}/"


def discover_beads_workspaces(roots: Sequence[Path]) -> WorkspaceDiscovery:
    """Find workspace roots without retaining their names in evidence output."""

    candidates: list[Path] = []
    for root in roots:
        resolved_root = root.expanduser().resolve()
        if not resolved_root.is_dir():
            continue
        for current, directories, _files in os.walk(resolved_root):
            current_path = Path(current)
            directories[:] = [
                name
                for name in directories
                if not _excluded_scan_path(current_path / name) and name != ".beads"
            ]
            beads_dir = current_path / ".beads"
            if beads_dir.is_dir():
                candidates.append(current_path)
    unique = tuple(sorted(set(candidates), key=lambda path: path.as_posix()))
    return WorkspaceDiscovery(workspace_candidates=len(candidates), workspaces=unique)


def collect_real_project_shapes(
    discovery: WorkspaceDiscovery,
    *,
    client_factory: ClientFactory,
    max_probes_per_kind: int = 20,
    seed: int = 5879,
) -> tuple[list[ProjectShape], ShapeSampling]:
    """Collect only numeric shapes and deduplicate identical Memory snapshots."""

    shapes: list[ProjectShape] = []
    failures: dict[str, int] = {}
    seen_candidate_digests: set[str] = set()
    scanned = 0
    with_memories = 0
    duplicates = 0
    for workspace in discovery.workspaces:
        client = client_factory(workspace)
        try:
            inventory = client.page("", OrderingArm.KEY)
            scanned += 1
            if not inventory.complete or len(inventory.items) != inventory.total_matched:
                raise ValueError("unbounded Memory inventory was incomplete")
            if inventory.total_matched == 0:
                continue
            with_memories += 1
            if inventory.candidate_digest in seen_candidate_digests:
                duplicates += 1
                continue
            seen_candidate_digests.add(inventory.candidate_digest)
            shapes.append(
                measure_project_shape(
                    client,
                    max_probes_per_kind=max_probes_per_kind,
                    seed=seed,
                    inventory=inventory,
                )
            )
        except (subprocess.TimeoutExpired, TimeoutError):
            failures["timeout"] = failures.get("timeout", 0) + 1
        except (RuntimeError, ValueError):
            # Error text may contain a path or provider diagnostic; retain only
            # this fixed category and discard the exception at this boundary.
            failures["bd-error"] = failures.get("bd-error", 0) + 1
    return shapes, ShapeSampling(
        workspace_candidates=discovery.workspace_candidates,
        unique_workspaces=len(discovery.workspaces),
        workspaces_scanned=scanned,
        workspaces_with_memories=with_memories,
        unique_memory_snapshots=len(shapes),
        duplicate_memory_snapshots=duplicates,
        failures_by_code=failures,
    )


def _distribution(values: Sequence[int]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "p50": None, "p90": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": fmean(values),
        "p50": percentile(values, 0.5),
        "p90": percentile(values, 0.9),
        "min": min(values),
        "max": max(values),
    }


def _match_distribution(values: Sequence[int], page_sizes: Sequence[int]) -> dict[str, object]:
    result: dict[str, object] = dict(_distribution(values))
    result["nonzero_fraction"] = (
        None if not values else sum(value > 0 for value in values) / len(values)
    )
    result["fraction_gt_page_size"] = {
        str(size): None if not values else sum(value > size for value in values) / len(values)
        for size in page_sizes
    }
    return result


def _sanitized_failures(failures: Mapping[str, int]) -> dict[str, int]:
    sanitized = dict.fromkeys(sorted(_ALLOWED_FAILURE_CODES), 0)
    other = 0
    for code, count in failures.items():
        if code in _ALLOWED_FAILURE_CODES:
            sanitized[code] += count
        else:
            other += count
    if other:
        sanitized["other"] = other
    return {code: count for code, count in sanitized.items() if count}


def summarize_real_project_shapes(
    shapes: Sequence[ProjectShape],
    *,
    sampling: ShapeSampling,
    provenance: ShapeProvenance,
    experimental_candidate_levels: Sequence[int] = (10, 40, 150),
    page_sizes: Sequence[int] = (5, 10, 20, 50),
    max_probes_per_kind: int = 20,
    probe_seed: int = 5879,
) -> dict[str, object]:
    if any(
        value < 1 for value in (*experimental_candidate_levels, *page_sizes, max_probes_per_kind)
    ):
        raise ValueError("candidate levels, page sizes, and probe limit must be positive")
    corpus_sizes = [shape.memory_count for shape in shapes]
    key_counts = [value for shape in shapes for value in shape.key_match_counts]
    content_counts = [value for shape in shapes for value in shape.content_match_counts]
    all_counts = [*key_counts, *content_counts]
    link_values = [
        value
        for shape in shapes
        if shape.link_outdegrees is not None
        for value in shape.link_outdegrees
    ]
    link_projects = sum(shape.link_outdegrees is not None for shape in shapes)
    if link_projects:
        link_density: dict[str, object] = {
            "available": True,
            "project_count": link_projects,
            "outdegree": _distribution(link_values),
        }
    else:
        link_density = {
            "available": False,
            "project_count": 0,
            "reason": "canonical-memory-references-not-observable",
        }
    return {
        "schema_version": 1,
        "study": "beads-memory-real-project-shapes",
        "privacy_projection": "aggregate counts and distributions only",
        "probe_protocol": _PROBE_PROTOCOL,
        "sampling_frame": {
            "discovery": "recursive .beads workspaces beneath operator-supplied roots",
            "exclusions": [
                ".git",
                ".mem",
                ".venv",
                "node_modules",
                "__pycache__",
                "memory-bench/results",
            ],
            "deduplication": "identical compact candidate snapshots counted once",
            "failure_handling": "fixed aggregate categories only; diagnostics discarded",
        },
        "probe_configuration": {
            "max_per_kind_per_project": max_probes_per_kind,
            "seed": probe_seed,
        },
        "sampling": {
            "workspace_candidates": sampling.workspace_candidates,
            "unique_workspaces": sampling.unique_workspaces,
            "workspaces_scanned": sampling.workspaces_scanned,
            "workspaces_with_memories": sampling.workspaces_with_memories,
            "unique_memory_snapshots": sampling.unique_memory_snapshots,
            "duplicate_memory_snapshots": sampling.duplicate_memory_snapshots,
            "failures_by_code": _sanitized_failures(sampling.failures_by_code),
        },
        "provenance": {
            "mem_git_sha": provenance.mem_git_sha,
            "mem_git_diff_sha256": provenance.mem_git_diff_sha256,
            "beads_git_sha": provenance.beads_git_sha,
            "beads_git_diff_sha256": provenance.beads_git_diff_sha256,
            "beads_bin_sha256": provenance.beads_bin_sha256,
            "collector_source_sha256": provenance.collector_source_sha256,
            "mem_git_dirty": provenance.mem_git_dirty,
            "beads_git_dirty": provenance.beads_git_dirty,
        },
        "corpus_size": _distribution(corpus_sizes),
        "match_set_size": {
            "key_token_probes": _match_distribution(key_counts, page_sizes),
            "content_bigram_probes": _match_distribution(content_counts, page_sizes),
            "all_native_probes": _match_distribution(all_counts, page_sizes),
        },
        "link_density": link_density,
        "experimental_regime_comparison": {
            str(level): {
                "fraction_observed_at_or_below": (
                    None
                    if not all_counts
                    else sum(value <= level for value in all_counts) / len(all_counts)
                )
            }
            for level in experimental_candidate_levels
        },
        "limitations": [
            "local workspace discovery is a convenience sample, not a random population",
            "native probes are derived mechanically from compact legacy Memory records",
            "derived probes approximate lexical conditions and are not observed user searches",
            "available projects expose keyed Memory values, not canonical Memory Bead references",
            "reference density is unavailable rather than assumed to be zero",
        ],
    }


def _render_report(evidence: Mapping[str, object]) -> str:
    corpus = evidence["corpus_size"]
    matches = evidence["match_set_size"]
    sampling = evidence["sampling"]
    assert isinstance(corpus, Mapping)
    assert isinstance(matches, Mapping)
    assert isinstance(sampling, Mapping)
    all_native = matches["all_native_probes"]
    assert isinstance(all_native, Mapping)
    return (
        "# Real-project Memory shape telemetry\n\n"
        "Only aggregate numeric distributions are retained. Workspace paths, Memory "
        "identifiers, keys, compact text, derived probes, and command diagnostics are "
        "discarded.\n\n"
        "## Method\n\n"
        "- Sampling frame: recursively discovered `.beads` workspaces beneath "
        "operator-supplied roots; generated, dependency, cache, and experiment-result "
        "trees were excluded.\n"
        "- Probe derivation: bounded deterministic key tokens and title/excerpt bigrams "
        "from the compact discovery projection.\n"
        "- Snapshot deduplication: identical compact candidate snapshots were counted "
        "once.\n"
        "- Failure handling: only fixed aggregate categories survive; diagnostics are "
        "discarded.\n\n"
        "## Results\n\n"
        f"- Workspace candidates: {sampling['workspace_candidates']}\n"
        f"- Workspaces scanned: {sampling['workspaces_scanned']}\n"
        f"- Workspaces with Memory records: {sampling['workspaces_with_memories']}\n"
        f"- Corpus size p50/p90: {corpus['p50']}/{corpus['p90']}\n"
        f"- Native-probe match size p50/p90: {all_native['p50']}/{all_native['p90']}\n"
        "- Canonical Memory-reference density: unavailable in the observed legacy surface; "
        "it is not reported as zero.\n"
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_real_project_shape_evidence(
    shapes: Sequence[ProjectShape],
    out: Path,
    *,
    sampling: ShapeSampling,
    provenance: ShapeProvenance,
    experimental_candidate_levels: Sequence[int] = (10, 40, 150),
    page_sizes: Sequence[int] = (5, 10, 20, 50),
    max_probes_per_kind: int = 20,
    probe_seed: int = 5879,
) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    evidence = summarize_real_project_shapes(
        shapes,
        sampling=sampling,
        provenance=provenance,
        experimental_candidate_levels=experimental_candidate_levels,
        page_sizes=page_sizes,
        max_probes_per_kind=max_probes_per_kind,
        probe_seed=probe_seed,
    )
    analysis_path = out / "analysis.json"
    report_path = out / "report.md"
    analysis_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_path.write_text(_render_report(evidence), encoding="utf-8")
    manifest: dict[str, object] = {
        "schema_version": 1,
        "privacy_projection": evidence["privacy_projection"],
        "artifact_names": ["analysis.json", "report.md"],
        "artifact_sha256s": {
            "analysis.json": _file_sha256(analysis_path),
            "report.md": _file_sha256(report_path),
        },
        "provenance": evidence["provenance"],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest
