"""Real fail-to-pass failure SHAPES, extracted from the cross-rig corpus (mem-bxhh.2).

This is the construct-validity bridge for mem-bxhh.5: the synthetic generator's
tasks should reproduce the *phenomenology* of the failures real multi-agent work
actually produces. The corpus (``data/ftp-oracle/{scix_experiments,codeprobe}.json``)
holds 32 BEHAVIORAL fail-to-pass tests — the ones a memory of prior decisions could
plausibly bear on, as opposed to the far larger feature-presence set (a test that
fails only because the symbol does not exist yet).

Each ``FtpShape`` is an *authored* label over named real tests — a small curated
dataset, not a runtime classifier. We deliberately do NOT keyword-match arbitrary
test names into shapes (that semantic call belongs to a human/model, per the ZFC
boundary); instead every shape lists the exact corpus tests it covers, and
``assert_shapes_grounded`` re-checks that those names are still behavioral ftp in the
frozen corpus, so the taxonomy cannot drift into fabrication.

``memory_dependent`` records whether recalling a fact established earlier in the run
is what the test guards — the only shapes the synthetic memory substrate can honestly
reproduce. The aggregation and exclusion shapes are: an agent that forgot a prior
step's token count cannot emit the rollup; one that forgot which task was quota-voided
cannot exclude it from the mean.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parents[2] / "data" / "ftp-oracle"


@dataclass(frozen=True)
class FtpShape:
    """One real failure-mode shape and the corpus tests that exhibit it.

    ``example_tests`` are exact ``rig`` + dotted-test-id pairs drawn from the behavioral
    ftp corpus; ``assert_shapes_grounded`` verifies they remain present so the label
    stays honest. ``memory_dependent`` marks shapes whose failure a cross-step memory
    could prevent — the ones the synthetic generator can reproduce."""

    shape_id: str
    summary: str
    memory_dependent: bool
    example_tests: tuple[tuple[str, str], ...] = field(default_factory=tuple)


# The taxonomy. Shape ids are stable strings (the synthetic blueprints reference them).
# Counts in the summaries are the behavioral-ftp tallies observed in the mem-bxhh.2 corpus.
FTP_SHAPES: tuple[FtpShape, ...] = (
    FtpShape(
        shape_id="aggregation-projection",
        summary=(
            "Aggregate/roll up values produced across earlier steps into a final "
            "projection (token-count rollups, score-result projection, raw counts in "
            "JSON); emit nothing when the inputs are unavailable."
        ),
        memory_dependent=True,
        example_tests=(
            ("codeprobe", "tests.test_experiment_cmd::test_aggregate_emits_token_count_rollups"),
            (
                "codeprobe",
                "tests.test_experiment_cmd::test_aggregate_token_rollups_none_when_unavailable",
            ),
            (
                "codeprobe",
                "tests.test_scoring_unified_contract.TestExecutorDiagnosticsContract::test_scoring_json_emits_raw_token_counts",
            ),
            ("codeprobe", "tests.test_executor::test_build_scoring_details_projects_score_result"),
        ),
    ),
    FtpShape(
        shape_id="exclusion-filter",
        summary=(
            "Exclude a flagged subset (quota-errored tasks) from a downstream "
            "aggregate so paired scores and per-config means are not contaminated."
        ),
        memory_dependent=True,
        example_tests=(
            (
                "codeprobe",
                "tests.test_stats.TestQuotaExclusion::test_compare_configs_paired_scores_exclude_quota",
            ),
            (
                "codeprobe",
                "tests.test_stats.TestQuotaExclusion::test_summarize_completed_tasks_mean_excludes_quota",
            ),
            (
                "codeprobe",
                "tests.test_stats.TestQuotaExclusion::test_summarize_config_mean_excludes_quota",
            ),
        ),
    ),
    FtpShape(
        shape_id="cli-usage-guard",
        summary=(
            "Precondition/usage guard with a distinct exit code at a threshold "
            "boundary (free-disk floor: passes at the exact floor, refuses below)."
        ),
        memory_dependent=False,
        example_tests=(
            (
                "scix_experiments",
                "tests.test_extract_citation_contexts_cli.TestEnforceFreeDiskGuard::test_refuses_when_below_floor",
            ),
            (
                "scix_experiments",
                "tests.test_extract_citation_contexts_cli.TestEnforceFreeDiskGuard::test_passes_at_exact_floor",
            ),
        ),
    ),
    FtpShape(
        shape_id="lenient-adapter-parse",
        summary=(
            "Tolerantly parse an external/LLM adapter response — accept trailing text "
            "on the score/review line without dropping the structured value."
        ),
        memory_dependent=False,
        example_tests=(
            (
                "scix_experiments",
                "tests.test_persona_judge.TestParseUmbrelaResponse::test_tolerates_trailing_text_on_score_line",
            ),
            (
                "scix_experiments",
                "tests.test_persona_judge.TestParseUmbrelaResponse::test_tolerates_trailing_text_on_review_line",
            ),
        ),
    ),
    FtpShape(
        shape_id="empty-input-structure",
        summary=(
            "Return the full deterministic structure (all requested sections, immutable "
            "tuples) even when inputs are empty, rather than crashing or omitting keys."
        ),
        memory_dependent=False,
        example_tests=(
            (
                "scix_experiments",
                "tests.test_synthesize_findings.TestEmptyInputs::test_empty_working_set_returns_empty_structure",
            ),
            (
                "scix_experiments",
                "tests.test_synthesize_findings.TestDeterministicStructure::test_returns_all_requested_sections_even_when_empty",
            ),
        ),
    ),
    FtpShape(
        shape_id="batch-query-shape",
        summary=(
            "Hold the batch-query contract: one query not N for a large working set, "
            "skip empty inputs, fill missing rows, preserve the nested return shape."
        ),
        memory_dependent=False,
        example_tests=(
            (
                "scix_experiments",
                "tests.test_session_working_set.TestCitationTraverseWorkingSet::test_large_working_set_is_one_query_not_n",
            ),
            (
                "scix_experiments",
                "tests.test_session_working_set.TestCitationEdgesBatch::test_empty_bibcodes_skips_query",
            ),
        ),
    ),
)


def _behavioral_index() -> dict[str, set[str]]:
    """Map each corpus rig -> the set of its behavioral fail-to-pass test ids."""
    index: dict[str, set[str]] = {}
    for path in sorted(CORPUS_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or "commits" not in data:
            continue
        rig = data.get("rig", path.stem)
        tests: set[str] = index.setdefault(rig, set())
        for commit in data["commits"]:
            tests.update(commit.get("behavioral", []))
    return index


def assert_shapes_grounded(shapes: tuple[FtpShape, ...] = FTP_SHAPES) -> None:
    """Fail closed if any shape names a test absent from the behavioral ftp corpus.

    Keeps the taxonomy honest: a shape is a label over *real* failures, so a renamed
    or dropped corpus test must surface here rather than silently leaving a shape
    pointing at nothing."""
    index = _behavioral_index()
    missing: list[str] = []
    for shape in shapes:
        for rig, test in shape.example_tests:
            if test not in index.get(rig, set()):
                missing.append(f"{shape.shape_id}: {rig} :: {test}")
    if missing:
        raise ValueError(
            "ftp shapes reference tests absent from the behavioral corpus:\n  "
            + "\n  ".join(missing)
        )


def memory_dependent_shapes(shapes: tuple[FtpShape, ...] = FTP_SHAPES) -> tuple[FtpShape, ...]:
    """The shapes the synthetic memory substrate can honestly reproduce."""
    return tuple(s for s in shapes if s.memory_dependent)
