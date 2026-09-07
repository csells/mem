"""Dual-verifier scoring (mem-75t.7.5, plan §4 P4) -- port of codeprobe's DualScorer
(``core/scoring/scorers.py`` + ``prd_dual_verifier_mining.md``).

A completed agent run on a bundle is scored along two INDEPENDENT legs, both always
run, both preserved -- a single score collapses two distinct failure modes (writes
correct code but can't say what's relevant vs. identifies the right files but can't
implement the fix):

- **direct** (`score_direct`) -- did the run reproduce the change?
  PRIMARY is test reproduction: apply the candidate diff and run the bundle's gold
  tests (SWE-bench fail-to-pass shape), available when the gold diff carries test
  files. The runner is injected (`ReproRunner`) -- the live `git apply` + test
  command is integration-time, the same seam as the curator's `claude -p`. When no
  test files are present, or the runner is absent, or it errors, the leg FALLS BACK
  to diff similarity (`probe_direct.score_probe_direct`) -- brittle (many valid fixes
  differ textually), hence the fallback, not the headline (bead review revision 1).

- **comprehension** (`score_artifact`) -- did the run identify the right files?
  F1 of the agent-identified file set vs the bundle's curated oracle. When the oracle
  carries `oracle_tiers`, recall is tier-weighted (required=2.0, supplementary=1.0,
  context=0.5 -- codeprobe `_weighted_f1`), so missing a required file costs more
  than missing context.

Both sub-scores are stored on `BundleVerification`; `automated_score` is composed per
`scoring_policy` (default ``direct`` -- backwards-compatible; ``min``/``mean``/
``weighted``). The efficiency axis (tokens / turns / tool calls, reused from
`probe_direct.extract_efficiency`) is recorded first-class on the result: the
base-rate spike says success-rate may saturate on this corpus, so efficiency is the
metric most likely to retain dynamic range (bead review revision 2). Per-bundle
paired sub-scores are emitted; the grid composes paired deltas (never pooled means).

Graceful degradation: a missing leg input degrades THAT leg without taking the run
down -- a run with no identified-files artifact scores ``artifact=0.0`` with the
direct leg intact (acceptance); a bundle with no oracle leaves artifact unscoreable
(``None``) rather than a misleading 0.0.

ZFC: pure mechanism -- set arithmetic, exit-code interpretation, composition. The one
external judgement (do the tests pass?) is the test runner's, delegated like the
curator's model call. Not exported from ``grading.__init__`` (it imports
`schemas.bundle`, whose chain reaches `harbor.grid` -> the grading package) -- import
as ``membench.grading.dual_verifier`` (same convention as `probe_direct`).
"""

from __future__ import annotations

import posixpath
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from statistics import fmean
from typing import Literal, Protocol

from membench.grading.probe_direct import (
    ProbeDirectScore,
    ProbeEfficiency,
    extract_efficiency,
    score_probe_direct,
)
from membench.schemas.bundle import BundleVerification, CuratedOracle, ScoringPolicy, TaskBundle

# A file F1 / direct combined at or above this counts as a passing leg -- one
# threshold shared with the grid's pass-rate (codeprobe R15-XR: F1>0 and the 0.5
# pass rule must not disagree).
PASS_THRESHOLD = 0.5

# Recall tier weights (codeprobe ``_weighted_f1``): a required oracle file matters
# more than context. A file with no tier defaults to ``required`` -- the
# conservative weight, so an untiered oracle scores like a flat required set.
TIER_WEIGHTS: dict[str, float] = {"required": 2.0, "supplementary": 1.0, "context": 0.5}
_DEFAULT_TIER_WEIGHT = TIER_WEIGHTS["required"]

# Path suffixes / segments that mark a test file across the rigs (TS vitest, Go,
# pytest). Mechanical shape match only -- the gold diff already says which files exist.
_TEST_SUFFIXES = (".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.tsx", "_test.go")
_TEST_SEGMENTS = ("/tests/", "/test/", "/__tests__/")


def is_test_path(path: str) -> bool:
    """True when ``path`` is a test file by shape -- the predicate behind
    `gold_has_tests`, shared with the live repro runner (which must split a gold
    diff into its test and implementation halves). Purely structural (no IO)."""
    norm = posixpath.normpath(path)
    base = posixpath.basename(norm)
    if norm.endswith(_TEST_SUFFIXES):
        return True
    if base.startswith("test_") or base.endswith("_test.py"):
        return True
    return any(seg in f"/{norm}" for seg in _TEST_SEGMENTS)


def gold_has_tests(gold_paths: Sequence[str]) -> bool:
    """True when any gold-diff path is a test file -- the trigger for the primary
    test-reproduction direct leg."""
    return any(is_test_path(path) for path in gold_paths)


# ---------------------------------------------------------------------------
# Comprehension leg -- F1 of identified files vs the oracle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactScore:
    """The comprehension leg detail. ``score`` is ``weighted_f1`` when the oracle is
    tiered, else the unweighted ``f1`` -- the single number the dual score consumes;
    precision/recall are kept for the report."""

    precision: float
    recall: float
    f1: float
    weighted_recall: float | None
    weighted_f1: float | None
    n_identified: int
    n_oracle: int

    @property
    def score(self) -> float:
        return self.weighted_f1 if self.weighted_f1 is not None else self.f1


def score_artifact(identified_files: Sequence[str], oracle: CuratedOracle) -> ArtifactScore:
    """F1 of the agent-identified file set vs ``oracle.oracle_answer``.

    Precision is standard (unweighted). When ``oracle_tiers`` is present recall is
    tier-weighted (codeprobe `_weighted_f1`): a matched required file contributes
    more than a matched context file. The caller guarantees a non-empty oracle (an
    empty oracle is unscoreable, handled one layer up)."""
    expected = frozenset(oracle.oracle_answer)
    answer = frozenset(identified_files)
    if not expected:
        raise ValueError("empty oracle: artifact F1 is undefined; caller must guard")

    intersection = expected & answer
    precision = len(intersection) / len(answer) if answer else 0.0
    recall = len(intersection) / len(expected)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    tiers = dict(oracle.oracle_tiers)
    weighted_recall: float | None = None
    weighted_f1: float | None = None
    if tiers:
        hit = sum(
            TIER_WEIGHTS.get(tiers.get(f, "required"), _DEFAULT_TIER_WEIGHT) for f in intersection
        )
        total = sum(
            TIER_WEIGHTS.get(tiers.get(f, "required"), _DEFAULT_TIER_WEIGHT) for f in expected
        )
        weighted_recall = hit / total if total > 0 else 0.0
        wdenom = precision + weighted_recall
        weighted_f1 = 2 * precision * weighted_recall / wdenom if wdenom > 0 else 0.0

    return ArtifactScore(
        precision=precision,
        recall=recall,
        f1=f1,
        weighted_recall=weighted_recall,
        weighted_f1=weighted_f1,
        n_identified=len(answer),
        n_oracle=len(expected),
    )


# ---------------------------------------------------------------------------
# Direct leg -- test reproduction (primary) with diff-similarity fallback
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReproOutcome:
    """The fail-to-pass result of running the gold tests against the candidate diff.
    Exit-code semantics (SWE-bench shape): the gold tests pass after applying the
    candidate, or they do not. ``error`` set => the run could not be scored (apply
    failed, runner crashed) and the leg falls back to diff similarity.

    ``tests_passed`` / ``tests_total`` are the S1 per-test-FILE partial-credit counts
    (mem-g6a): how many of the gold-diff's test files passed when each is run on its
    own. They are the graded *resolution underneath* the binary anchor, never a
    replacement for it -- ``passed`` (and ``score``) stay the ungameable all-or-nothing
    floor. Both are None when the leg did not run a per-file count (a stub outcome, or
    an ``error`` outcome that never reached the test loop), so ``test_ratio`` is a typed
    absence rather than a misleading 0.0."""

    passed: bool
    error: str | None = None
    tests_passed: int | None = None
    tests_total: int | None = None

    @property
    def score(self) -> float:
        return 1.0 if self.passed else 0.0

    @property
    def test_ratio(self) -> float | None:
        """S1 partial credit: ``tests_passed / tests_total`` in [0, 1], or None when
        the per-file counts were not recorded. A passed run is necessarily 1.0 (every
        file passed); a failed run lands strictly below 1.0 only when some files
        passed -- the resolution the binary anchor cannot see."""
        if self.tests_passed is None or self.tests_total is None or self.tests_total == 0:
            return None
        return self.tests_passed / self.tests_total


class ReproRunner(Protocol):
    """Applies a bundle's candidate diff and runs its gold tests, returning a
    `ReproOutcome`. Injected so the pure scoring path needs no checkout or test
    process -- the live runner is integration-time."""

    def run(self, *, bundle: TaskBundle, candidate_diff: Mapping[str, str]) -> ReproOutcome: ...


@dataclass(frozen=True)
class StubReproRunner:
    """Deterministic, offline test runner: returns a fixed `ReproOutcome`. The whole
    scoring pipeline and every test run on this."""

    outcome: ReproOutcome

    def run(self, *, bundle: TaskBundle, candidate_diff: Mapping[str, str]) -> ReproOutcome:
        return self.outcome


DirectMode = Literal["test_repro", "diff_sim"]


@dataclass(frozen=True)
class DirectScore:
    """The direct-leg detail. Exactly one of ``test_outcome`` / ``diff_sim`` is set,
    per ``mode``; ``score`` is the leg's [0,1] value either way. ``repro_error`` is set
    only when the primary test-reproduction leg was attempted and FAILED to score, so
    a ``diff_sim`` result records WHY it fell back -- a fallback never hides which path
    won."""

    mode: DirectMode
    score: float
    test_outcome: ReproOutcome | None = None
    diff_sim: ProbeDirectScore | None = None
    repro_error: str | None = None
    # S1 per-test-file partial credit, carried up from ``test_outcome`` when the
    # primary test-reproduction leg ran; None on the diff-sim fallback (no tests ran).
    test_ratio: float | None = None


def score_direct(
    bundle: TaskBundle,
    candidate_diff: Mapping[str, str],
    *,
    test_runner: ReproRunner | None = None,
) -> DirectScore:
    """Score the direct leg. Test reproduction is PRIMARY when the gold diff carries
    test files and a runner is supplied; on no-tests / no-runner / a runner error the
    leg falls back to diff similarity. An empty candidate diff is a legitimate
    no-edit run -- diff similarity scores it 0.0 (it never reaches a test run)."""
    gold = dict(bundle.output.file_diffs)

    repro_error: str | None = None
    if candidate_diff and test_runner is not None and gold_has_tests(list(gold)):
        outcome = test_runner.run(bundle=bundle, candidate_diff=candidate_diff)
        if outcome.error is None:
            return DirectScore(
                mode="test_repro",
                score=outcome.score,
                test_outcome=outcome,
                test_ratio=outcome.test_ratio,
            )
        # Runner could not score (apply failed, crash): record WHY on the fallback so
        # a diff_sim result is never an unexplained downgrade from the primary leg.
        repro_error = outcome.error

    diff_sim = score_probe_direct(candidate_diff, gold)
    return DirectScore(
        mode="diff_sim", score=diff_sim.combined, diff_sim=diff_sim, repro_error=repro_error
    )


# ---------------------------------------------------------------------------
# Composition + the run entry point
# ---------------------------------------------------------------------------


def compose_automated_score(
    score_direct_value: float | None,
    score_artifact_value: float | None,
    *,
    policy: ScoringPolicy,
    weight_direct: float,
    weight_artifact: float,
) -> float | None:
    """Compose the headline ``automated_score`` from the two legs.

    ``direct`` (default) returns the direct leg verbatim -- backwards-compatible, the
    bead's stated default. ``min``/``mean``/``weighted`` combine both legs, treating
    an unscoreable leg (``None``) as 0.0 so a composite is always defined once a
    policy asks for one. ``weighted`` requires its weights to sum to 1.0."""
    if policy == "direct":
        return score_direct_value
    direct = score_direct_value if score_direct_value is not None else 0.0
    artifact = score_artifact_value if score_artifact_value is not None else 0.0
    if policy == "min":
        return min(direct, artifact)
    if policy == "mean":
        return fmean([direct, artifact])
    if policy == "weighted":
        if abs(weight_direct + weight_artifact - 1.0) > 1e-6:
            raise ValueError(
                f"weighted policy needs weights summing to 1.0, got "
                f"{weight_direct} + {weight_artifact}"
            )
        return weight_direct * direct + weight_artifact * artifact
    raise ValueError(f"unknown scoring policy {policy!r}")


@dataclass(frozen=True)
class RunResult:
    """A completed agent run on a bundle -- the scorer's input. ``candidate_diff`` is
    the run's per-file diff (same coordinate space as the gold diff);
    ``identified_files`` is the comprehension artifact (``None`` => the run produced
    none, which scores artifact 0.0); ``transcript`` feeds the efficiency axis."""

    candidate_diff: Mapping[str, str] = field(default_factory=dict)
    identified_files: tuple[str, ...] | None = None
    transcript: str | None = None


@dataclass(frozen=True)
class DualScore:
    """The full per-bundle dual score. The two sub-scores + policy land on the
    bundle's `BundleVerification`; the rich detail (leg modes, F1 breakdown,
    efficiency, degradations) lives here, the codeprobe ``scoring_details`` analogue."""

    score_direct: float | None
    score_artifact: float | None
    automated_score: float | None
    scoring_policy: ScoringPolicy
    weight_direct: float
    weight_artifact: float
    direct: DirectScore
    artifact: ArtifactScore | None
    efficiency: ProbeEfficiency | None
    degradations: tuple[tuple[str, str], ...]
    passed_direct: bool
    passed_artifact: bool
    # S1/S2 graded side-signals (mem-g6a), additive layers under the binary anchor:
    # ``test_ratio`` is the per-test-file partial credit (None on the diff-sim
    # fallback, where no tests ran); ``diff_sim`` is the ALWAYS-ON bounded structural
    # similarity -- promoted from error-only fallback to a side signal computed on
    # every run, never a gate (its known equivalent-fix bias is carried in the report).
    test_ratio: float | None
    diff_sim: ProbeDirectScore


def score_run(
    bundle: TaskBundle,
    run: RunResult,
    *,
    test_runner: ReproRunner | None = None,
    scoring_policy: ScoringPolicy | None = None,
    weight_direct: float = 0.5,
    weight_artifact: float = 0.5,
) -> tuple[DualScore, TaskBundle]:
    """Score ``run`` against ``bundle``, returning the `DualScore` and a NEW bundle
    with `verification` populated. Both legs always run; a missing leg input degrades
    that leg only. ``scoring_policy`` overrides the bundle's stored policy (default
    ``direct``). Immutable: the input bundle is never mutated."""
    policy: ScoringPolicy = scoring_policy or bundle.verification.scoring_policy
    degradations: list[tuple[str, str]] = []

    direct = score_direct(bundle, run.candidate_diff, test_runner=test_runner)
    sd: float | None = direct.score
    if not run.candidate_diff:
        degradations.append(("direct", "run produced no candidate diff -> direct 0.0"))

    # S2: always-on bounded diff similarity (mem-g6a) -- a continuous side signal on
    # EVERY run, not just the repro-error fallback. Reuse the fallback's computation
    # when the direct leg already produced it (same candidate vs same gold); otherwise
    # compute it once here. An empty candidate scores 0.0; gold is non-empty by
    # admission (`score_probe_direct` raises on an empty gold, an upstream bundle bug).
    diff_sim = (
        direct.diff_sim
        if direct.diff_sim is not None
        else score_probe_direct(run.candidate_diff, dict(bundle.output.file_diffs))
    )

    # Comprehension leg: a missing artifact scores 0.0 (acceptance); a missing oracle
    # is unscoreable (None) -- a 0.0 there would falsely blame the run.
    artifact: ArtifactScore | None = None
    sa: float | None
    oracle = bundle.oracle_context
    if run.identified_files is None:
        sa = 0.0
        degradations.append(("artifact", "run produced no identified-files artifact -> 0.0"))
    elif oracle is None or not oracle.oracle_answer:
        sa = None
        degradations.append(("artifact", "bundle has no oracle_context to score against"))
    else:
        artifact = score_artifact(run.identified_files, oracle)
        sa = artifact.score

    efficiency = extract_efficiency(run.transcript) if run.transcript is not None else None
    if efficiency is None:
        degradations.append(("efficiency", "run carried no transcript -> efficiency unrecorded"))

    automated = compose_automated_score(
        sd, sa, policy=policy, weight_direct=weight_direct, weight_artifact=weight_artifact
    )

    verification = BundleVerification(
        scoring_policy=policy,
        weight_direct=weight_direct,
        weight_artifact=weight_artifact,
        score_direct=sd,
        score_artifact=sa,
    )
    new_bundle = bundle.model_copy(update={"verification": verification})

    dual = DualScore(
        score_direct=sd,
        score_artifact=sa,
        automated_score=automated,
        scoring_policy=policy,
        weight_direct=weight_direct,
        weight_artifact=weight_artifact,
        direct=direct,
        artifact=artifact,
        efficiency=efficiency,
        degradations=tuple(degradations),
        passed_direct=sd is not None and sd >= PASS_THRESHOLD,
        passed_artifact=sa is not None and sa >= PASS_THRESHOLD,
        test_ratio=direct.test_ratio,
        diff_sim=diff_sim,
    )
    return dual, new_bundle
