"""RUN leg of the mem-ovi realism metric (mem-ovi.2): the 3-axis verdict MATRIX.

Computes the realism of the frozen synthetic corpus versus the real reference
corpora on all three landed axes, UNDER EACH reference-definition fork combination
(Fork A corpus subset x Fork B session->step segmentation x Fork C kickoff-boilerplate
handling). The output is a matrix, not a verdict: it resolves NO fork and applies NO
threshold, so Stephanie decides the reference definition with the data in hand
(mem-ovi forks A/B/C are PENDING #mem sign-off).

This module is orchestration + fork-option REGISTRIES only. Every realism NUMBER
comes from the landed framework, not from new metric logic here:

* STRUCTURAL -> ``perfeature_reference.per_feature_reference`` (the signed-off
  per-feature KS vector, no aggregate and no gate; #mem 2026-06-21).
* SEMANTIC   -> ``semantic.aggregate_semantic`` over ``score_semantic_realism``
  (the raw mean rating / believable fraction, not the placeholder ``passes`` gate).
  Synthetic-only, so it is fork-INDEPENDENT and computed once.
* CONSTRUCT  -> ``construct.construct_validity_from_arms`` when real+synthetic
  arm-performance is supplied; here it is reported N/A (offline, no arm scores).

The three axes are reported SEPARATELY (per ZFC + the 4.2 raw-vector style); this
module never assembles the gated ``report.RealismReport.defensible`` boolean.

Numbers are HELD (publication freeze): ``main`` writes the matrix under ``.mem/ovi2/``
(gitignored) for per-action surfacing to mem-pl, never to a tracked path. The
SEMANTIC axis reuses the local qwen2.5 judge (free, self-hosted Ollama) via
``LocalStackComparativeJudge``; there is no paid-API fallback.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from membench.bbon.comparative_judge import ComparativeJudge
from membench.corpus import CorpusRunner
from membench.realism.features import TaskFeatures, features_from_sequence
from membench.realism.mem_corpus import (
    MessageFilter,
    TranscriptEntry,
    TranscriptReader,
    _entry_text,
    _read_transcript_file,
    default_message_filter,
    load_real_corpus,
)
from membench.realism.perfeature_reference import PerFeatureReference, per_feature_reference
from membench.realism.real_loader import Segmenter, _turn_texts, load_real_features
from membench.realism.semantic import (
    SemanticAggregate,
    SemanticVerdict,
    aggregate_semantic,
    score_semantic_realism,
)
from membench.schemas.sequence import BenchmarkSequence
from membench.schemas.trace import Trace

logger = logging.getLogger(__name__)

SEQUENCES_FILE = "sequences.json"
MANIFEST_FILE = "manifest.json"

# repo root = <root>/memory-bench/membench/realism/run_verdict.py -> parents[3].
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MEM_BIN = str(_PROJECT_ROOT / "bin" / "mem")


# --- Fork A: which real records enter the reference corpus (mem query filters) ---
#
# Candidate subsets, each a mapping onto ``mem query`` CLI flags (see mem_corpus.
# load_work_records). This is a SWEEP, not a resolution: the reference-corpus
# definition is Stephanie's #mem call. ``all-closed`` is the whole closed real
# substrate across rigs; ``mem-closed`` is the same-rig reference. A caller may pass
# its own mapping to widen the sweep.
FORK_A_SUBSETS: dict[str, dict[str, str]] = {
    "all-closed": {"status": "closed"},
    "mem-closed": {"rig": "mem", "status": "closed"},
}


# --- Fork B: SESSION -> STEP segmentation (real_loader.Segmenter) ---


def _all_message_texts(trace: Trace) -> list[str]:
    """Fork B alternative: one step per MESSAGE (user and assistant), not only user
    turns. Upholds the ``Segmenter`` non-empty contract with the same fallback as
    ``real_loader._turn_texts`` (a session with no messages is a single empty step)."""
    if trace.messages:
        return [m.content for m in trace.messages]
    return [""]


# ``userturn`` is real_loader's signed default (one step per user turn); ``allmsg``
# is the wider alternative (every message a step). Both are injected into the loader
# unchanged.
FORK_B_SEGMENTERS: dict[str, Segmenter] = {
    "userturn": _turn_texts,
    "allmsg": _all_message_texts,
}


# --- Fork C: kickoff-boilerplate handling (mem_corpus.MessageFilter) ---
#
# For an autonomous worker-pool session the surviving non-meta, non-tool_result user
# turn set is typically just the orchestrator kickoff line ("Run `gc prime` ..."),
# so n_steps / task_text_length on these sessions measure something structurally
# different from a synthetic task's authored user_request. ``strip-kickoff`` is a
# PROXY for resolving that: it additionally drops any surviving message CONTAINING a
# known harness kickoff marker. A substring test (not a prefix test) is deliberate --
# the real kickoff turn is a session header ("[rig] <path> - <ts>") followed by the
# injected instruction, so the marker is not at position 0. Matching the harness's own
# verbatim instruction string is mechanical policy (the same category as the format's
# ``isMeta`` / ``tool_result`` markers), specific enough that a human turn would not
# reproduce it, NOT semantic classification -- Stephanie owns the exact marker set.
KICKOFF_MARKERS: tuple[str, ...] = (
    "run `gc prime` to initialize",
    "gc prime` to initialize your context",
    "run `bd prime`",
)


def _is_kickoff(entry: TranscriptEntry) -> bool:
    """True when the entry's plain text contains a known orchestrator kickoff marker
    (case-insensitive). Reuses ``mem_corpus._entry_text`` so the text is flattened
    identically to how the corpus loader reads it."""
    text = _entry_text(entry).lower()
    return any(marker in text for marker in KICKOFF_MARKERS)


def _strip_kickoff_filter(entry: TranscriptEntry) -> bool:
    """Fork C alternative: the default filter AND drop kickoff-boilerplate turns."""
    return default_message_filter(entry) and not _is_kickoff(entry)


FORK_C_FILTERS: dict[str, MessageFilter] = {
    "default": default_message_filter,
    "strip-kickoff": _strip_kickoff_filter,
}


def load_synthetic_corpus(world_dir: str | Path) -> list[BenchmarkSequence]:
    """Load the frozen synthetic corpus (``sequences.json``) as ``BenchmarkSequence``
    objects. Reads the freeze verbatim -- no NIM/generator invocation -- so the run
    stays free and deterministic."""
    path = Path(world_dir) / SEQUENCES_FILE
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path} must hold a JSON list of sequences, got {type(raw).__name__}")
    return [BenchmarkSequence.model_validate(item) for item in raw]


def _world_sha(world_dir: str | Path) -> str | None:
    """The frozen world's ``sequences_sha256`` from its manifest, recorded in the
    output for provenance. Absent manifest -> None (not an error; provenance only)."""
    path = Path(world_dir) / MANIFEST_FILE
    if not path.exists():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    value = manifest.get("sequences_sha256") if isinstance(manifest, Mapping) else None
    return str(value) if isinstance(value, str) else None


def _cap_traces(traces: list[Trace], cap: int | None, label: str) -> list[Trace]:
    """Bound a real corpus to ``cap`` records, LOGGING the drop (no silent
    truncation). ``cap=None`` keeps the whole corpus."""
    if cap is not None and len(traces) > cap:
        logger.warning("fork-A subset %s: capping real corpus %d -> %d", label, len(traces), cap)
        return traces[:cap]
    return traces


@dataclass(frozen=True)
class StructuralCell:
    """One (Fork A, Fork B, Fork C) cell of the structural matrix: the signed-off
    per-feature KS reference between the synthetic corpus and this real subset,
    under this segmentation and boilerplate handling. No aggregate, no gate."""

    fork_a: str
    fork_b: str
    fork_c: str
    n_synthetic: int
    n_real: int
    reference: PerFeatureReference

    def to_dict(self) -> dict[str, object]:
        return {
            "fork_a": self.fork_a,
            "fork_b": self.fork_b,
            "fork_c": self.fork_c,
            "n_synthetic": self.n_synthetic,
            "n_real": self.n_real,
            "matchable": self.reference.matchable,
            "memory_op": self.reference.memory_op,
            "worst_matchable": list(self.reference.worst_matchable),
        }


def structural_matrix(
    synthetic_features: Sequence[TaskFeatures],
    store_path: str,
    *,
    subsets: Mapping[str, dict[str, str]] = FORK_A_SUBSETS,
    segmenters: Mapping[str, Segmenter] = FORK_B_SEGMENTERS,
    filters: Mapping[str, MessageFilter] = FORK_C_FILTERS,
    mem_bin: str | None = None,
    runner: CorpusRunner | None = None,
    transcript_reader: TranscriptReader = _read_transcript_file,
    real_cap: int | None = None,
) -> list[StructuralCell]:
    """Sweep the structural axis over every (A, C) real-corpus reduction and every B
    segmentation, comparing each against the fixed synthetic feature set.

    The real corpus is loaded once per (Fork A subset, Fork C filter) -- the two forks
    that change which records/messages survive -- and every Fork B segmentation reuses
    those traces (segmentation is a cheap re-reduction). Forks B and C never touch the
    synthetic side, so ``synthetic_features`` is computed once by the caller and shared.
    """
    cells: list[StructuralCell] = []
    for a_key, subset in subsets.items():
        for c_key, message_filter in filters.items():
            traces = load_real_corpus(
                store_path,
                mem_bin=mem_bin,
                runner=runner,
                filters=subset,
                message_filter=message_filter,
                transcript_reader=transcript_reader,
            )
            traces = _cap_traces(traces, real_cap, f"{a_key}/{c_key}")
            if not traces:
                logger.warning("fork-A/C %s/%s resolved 0 real traces; skipping", a_key, c_key)
                continue
            for b_key, segmenter in segmenters.items():
                real_features = load_real_features(traces, segmenter=segmenter)
                reference = per_feature_reference(synthetic_features, real_features)
                cells.append(
                    StructuralCell(
                        fork_a=a_key,
                        fork_b=b_key,
                        fork_c=c_key,
                        n_synthetic=len(synthetic_features),
                        n_real=len(real_features),
                        reference=reference,
                    )
                )
    return cells


@dataclass(frozen=True)
class SemanticAxis:
    """The fork-independent semantic axis: the raw corpus aggregate plus every
    per-task verdict. No ``passes`` gate is surfaced -- thresholds stay Stephanie's."""

    aggregate: SemanticAggregate
    per_task: tuple[tuple[str, SemanticVerdict], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.per_task[0][1].model if self.per_task else "",
            "mean_realism": self.aggregate.mean_realism,
            "real_fraction": self.aggregate.real_fraction,
            "n": self.aggregate.n,
            "per_task": [
                {
                    "task_id": task_id,
                    "realism": v.realism,
                    "reads_real": v.reads_real,
                    "rationale": v.rationale,
                }
                for task_id, v in self.per_task
            ],
        }


def semantic_axis(synthetic: Sequence[BenchmarkSequence], judge: ComparativeJudge) -> SemanticAxis:
    """Score every synthetic task with the model judge and aggregate. Fork-independent
    (synthetic-only). Raises through ``score_semantic_realism`` on a malformed reply --
    a semantic number is never fabricated from a bad judge response."""
    if not synthetic:
        raise ValueError("semantic_axis needs at least one synthetic task")
    verdicts = [(seq.sequence_id, score_semantic_realism(seq, judge)) for seq in synthetic]
    aggregate = aggregate_semantic([v for _, v in verdicts])
    return SemanticAxis(aggregate=aggregate, per_task=tuple(verdicts))


def construct_axis() -> dict[str, object]:
    """The construct axis is N/A for this free offline run.

    Construct validity rank-correlates memory-arm PERFORMANCE on synthetic vs real
    (construct.py). Real arm scores are the bxhh.5 bridge -- NO-GO at N~8 -- and are
    not measurable offline: the ftp-oracle corpus (memory-bench/data/ftp-oracle/) is
    the real construct-bridge substrate but supplies fail-to-pass task shapes, not the
    per-arm scores construct needs, which require a paid/heavy Harbor eval out of scope
    here. Reported N/A rather than fabricated (the framework already treats an absent
    construct axis as non-contradicting)."""
    return {
        "status": "N/A",
        "reason": (
            "real arm-performance not measurable offline (bxhh.5 NO-GO at N~8); "
            "ftp-oracle referenced as the real construct-bridge corpus but per-arm "
            "scores require a paid/heavy eval, out of scope for this free run"
        ),
    }


@dataclass(frozen=True)
class VerdictMatrix:
    """The full held mem-ovi.2 output: the structural matrix + the fork-independent
    semantic axis + the N-flagged construct axis, plus run provenance. The three axes
    are reported side by side; nothing here composes them into one score."""

    structural: tuple[StructuralCell, ...]
    semantic: SemanticAxis | None
    construct: dict[str, object]
    provenance: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "provenance": self.provenance,
            "structural": [cell.to_dict() for cell in self.structural],
            "semantic": self.semantic.to_dict() if self.semantic is not None else None,
            "construct": self.construct,
        }


def run(
    world_dir: str | Path,
    store_path: str,
    *,
    judge: ComparativeJudge | None = None,
    subsets: Mapping[str, dict[str, str]] = FORK_A_SUBSETS,
    segmenters: Mapping[str, Segmenter] = FORK_B_SEGMENTERS,
    filters: Mapping[str, MessageFilter] = FORK_C_FILTERS,
    mem_bin: str | None = None,
    runner: CorpusRunner | None = None,
    transcript_reader: TranscriptReader = _read_transcript_file,
    real_cap: int | None = None,
) -> VerdictMatrix:
    """Compute the whole fork matrix. ``judge=None`` skips the semantic axis (structural
    matrix only) so the deterministic, model-free part runs without a live daemon."""
    synthetic = load_synthetic_corpus(world_dir)
    synthetic_features = [features_from_sequence(seq) for seq in synthetic]

    structural = structural_matrix(
        synthetic_features,
        store_path,
        subsets=subsets,
        segmenters=segmenters,
        filters=filters,
        mem_bin=mem_bin,
        runner=runner,
        transcript_reader=transcript_reader,
        real_cap=real_cap,
    )
    semantic = semantic_axis(synthetic, judge) if judge is not None else None
    provenance: dict[str, object] = {
        "world_dir": str(world_dir),
        "store_path": store_path,
        "sequences_sha256": _world_sha(world_dir),
        "n_synthetic": len(synthetic),
        "fork_a": sorted(subsets),
        "fork_b": sorted(segmenters),
        "fork_c": sorted(filters),
        "real_cap": real_cap,
        "held": True,
    }
    return VerdictMatrix(
        structural=tuple(structural),
        semantic=semantic,
        construct=construct_axis(),
        provenance=provenance,
    )


def _build_judge() -> ComparativeJudge:
    """The local-stack judge for the semantic axis (free, self-hosted Ollama). Preflighted
    so a missing daemon / unpulled model fails fast at the boundary, never mid-run."""
    from membench.bbon.local_stack_judge import LocalStackComparativeJudge

    judge = LocalStackComparativeJudge()
    judge.preflight()
    return judge


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="mem-ovi.2 3-axis realism verdict matrix (HELD)")
    parser.add_argument("--world-dir", required=True, help="frozen synthetic world dir")
    parser.add_argument("--store", required=True, help="path to .mem/store.db")
    parser.add_argument(
        "--mem-bin",
        default=DEFAULT_MEM_BIN,
        help="path to the built `mem` CLI the real-corpus query shells (needs dist/)",
    )
    parser.add_argument(
        "--out",
        default=".mem/ovi2/verdict_matrix.json",
        help="held output path (gitignored); numbers never go to a tracked path",
    )
    parser.add_argument(
        "--real-cap",
        type=int,
        default=None,
        help="max real records per fork-A/C subset (logged when it truncates)",
    )
    parser.add_argument(
        "--no-semantic",
        action="store_true",
        help="skip the model-judged semantic axis (structural matrix only)",
    )
    args = parser.parse_args(argv)

    judge = None if args.no_semantic else _build_judge()
    matrix = run(
        args.world_dir,
        args.store,
        judge=judge,
        mem_bin=args.mem_bin,
        real_cap=args.real_cap,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(matrix.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info(
        "wrote HELD verdict matrix (%d structural cells) to %s", len(matrix.structural), out
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
