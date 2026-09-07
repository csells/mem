"""Token-overlap (lexical) circularity baseline — the cheap third guard (mem-lvp.34).

The calibration gate (`relevance_calibration.py`) catches a judge that is
systematically more permissive toward ours's own hits. This is the complementary,
model-free guard: run a DUMB token-overlap retriever (`LexicalTopKMemory`) over the
IDENTICAL scope-filtered candidate pool the comparison uses, score it through the
SAME `score_harvest` path against the JUDGED ``relevant_ids``, and ask one question:

    Does the dumb baseline score about as well as `ours` against the judged set?

If it does, the judged ground truth may be a proxy for ours's own keyword /
failure-signature mechanism — i.e. the "relevant" set is just the high-token-overlap
set, which any lexical retriever recovers. That would make the head-to-head circular.
The verdict flags it LIVE (a boolean + both arms' scores) so the compare envelope can
carry it ALONGSIDE the calibration verdict.

DIAGNOSTIC-ONLY (HARD): this never gates the headline by itself. ``win_eligible`` is
always True and ``diagnostic_only`` always True — a flagged circularity informs the
write-up, it does not remove a win. (Contrast `relevance_calibration`, whose gate FAIL
*does* make the metrics win-ineligible.)

ZFC boundary: the token-overlap scoring is the lexical arm's deterministic mechanism
(already the calibrated-similarity / explicit-tiebreaker exception, lexical_system.py),
and the ~= comparison is a documented absolute-difference rule over ONE named metric
with an explicit threshold (`DEFAULT_CIRCULARITY_DELTA`) — pure mechanism, no hidden
threshold masquerading as judgment, no semantic decision. Fully fixture-testable: no
Ollama, no network, no live judge.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from membench.compare.retrieval_compare import (
    DEFAULT_OURS_SCOPE,
    ArmComparison,
    harvest_ours,
    harvest_semantic,
    score_harvest,
)
from membench.grading.retrieval_leg import RetrievalTarget
from membench.memory_systems.base import MemorySystem
from membench.runtime import IdClock
from membench.validity import QueryWork, WorkRef

# The closeness rule, pre-stated in code (not tuned after seeing numbers): `ours` is
# "explained by" the token-overlap baseline when their scores on the judged set differ
# by at most this absolute amount. 0.05 mirrors the pre-registered tolerances the
# calibration gate uses (PREREGISTERED_FPR_MAX / GAP_MAX), keeping one bar across the
# defensibility lane. Caller-overridable, but always an explicit input — never hidden.
DEFAULT_CIRCULARITY_DELTA = 0.05

# The single headline metric the closeness rule compares. precision is the default
# because the circularity worry is specifically about WHAT a retriever surfaces being
# the same set the judge calls relevant — precision (relevant ∩ retrieved / retrieved)
# is the direct read of that. Caller may select another scored metric.
CircularityMetric = Literal["precision", "recall", "mrr", "ndcg"]
_METRICS: tuple[str, ...] = ("precision", "recall", "mrr", "ndcg")


@dataclass(frozen=True)
class CircularityVerdict:
    """The token-overlap circularity readout for one query work.

    ``flagged`` is True when the token-overlap baseline scores within
    ``closeness_threshold`` of `ours` on ``metric`` against the JUDGED relevant set AND
    the baseline actually scored (a baseline of 0 — the dumb retriever finds nothing —
    is the *opposite* of circularity, so it never flags). When the judged set is empty
    both scores are ``None`` (not measured) and ``flagged`` is False.

    DIAGNOSTIC-ONLY: ``diagnostic_only`` is always True and ``win_eligible`` always
    True — this verdict informs the write-up and rides in the compare envelope, but it
    can never gate the headline on its own."""

    flagged: bool
    diagnostic_only: bool
    win_eligible: bool
    metric: str
    ours_score: float | None
    baseline_score: float | None
    delta: float | None
    closeness_threshold: float
    baseline: ArmComparison
    reason: str

    def to_envelope(self) -> dict[str, Any]:
        """The flat JSON the compare envelope carries ALONGSIDE the calibration
        verdict — a boolean plus the per-arm scores, so the circularity check is
        visible in the recorded run, never buried."""
        return {
            "circularity_flagged": self.flagged,
            "diagnostic_only": self.diagnostic_only,
            "win_eligible": self.win_eligible,
            "metric": self.metric,
            "ours_score": self.ours_score,
            "baseline_score": self.baseline_score,
            "delta": self.delta,
            "closeness_threshold": self.closeness_threshold,
            "baseline_arm": self.baseline.arm,
            "baseline_retrieved_ids": list(self.baseline.retrieved_ids),
            "reason": self.reason,
        }


def _metric_value(arm: ArmComparison, metric: str) -> float | None:
    """Pull the named scored metric off an `ArmComparison`. ``None`` (not measured)
    propagates — never coerced to a meaningful-looking zero."""
    value = getattr(arm, metric)
    assert value is None or isinstance(value, float)
    return value


def circularity_check(
    query: QueryWork,
    query_text: str,
    corpus: list[WorkRef],
    corpus_text: Mapping[str, str],
    *,
    ours: MemorySystem,
    baseline: MemorySystem,
    relevant_ids: Sequence[str],
    scope: str = DEFAULT_OURS_SCOPE,
    target: RetrievalTarget = "canonical",
    metric: CircularityMetric | str = "precision",
    delta: float = DEFAULT_CIRCULARITY_DELTA,
) -> CircularityVerdict:
    """Run the token-overlap ``baseline`` over the SAME scope-filtered pool `ours` uses,
    score BOTH through the SAME `score_harvest` path against the JUDGED ``relevant_ids``,
    and flag circularity when they score ~= on ``metric``.

    The baseline is harvested through the existing `harvest_semantic` seam — seeded with
    the scope pool, queried once on ``query_text``, LOO re-checked — so it draws from
    the identical candidate set and is scored by the identical scorer (no duplicate
    pooler, no duplicate scorer). `ours` is harvested through `harvest_ours`, the same
    seam `compare_arms` uses.

    The closeness rule is explicit mechanism: ``|ours - baseline| <= delta`` on the one
    named ``metric`` (default precision, default 0.05). A baseline that scored 0 — the
    dumb retriever recovered nothing of the judged set — is NOT circularity and never
    flags, regardless of how `ours` scored.

    ``relevant_ids`` is taken as the JUDGED relevant set (binary judge output, mem-lvp.31/.32)
    already keyed to ``query``; an empty set means the leg is not measured (both scores
    ``None``, no flag)."""
    if metric not in _METRICS:
        raise ValueError(f"unknown metric {metric!r}; expected one of {_METRICS}")
    if delta < 0:
        raise ValueError(f"delta must be >= 0, got {delta}")

    # ours through the same seam compare_arms uses; baseline through the semantic seam
    # (seed the scope pool, retrieve once, LOO re-check) — the SAME pool, SAME scorer.
    ours_harvest = harvest_ours(ours, query, corpus, scope=scope)
    ours_arm = score_harvest(ours_harvest, relevant_ids, target=target)
    baseline_harvest = harvest_semantic(
        baseline, query, query_text, corpus, corpus_text, scope=scope, clock=IdClock()
    )
    baseline_arm = score_harvest(baseline_harvest, relevant_ids, target=target)

    ours_score = _metric_value(ours_arm, metric)
    baseline_score = _metric_value(baseline_arm, metric)

    gap = (
        abs(ours_score - baseline_score)
        if ours_score is not None and baseline_score is not None
        else None
    )
    flagged, reason = _decide(ours_score, baseline_score, gap, metric=metric, delta=delta)
    return CircularityVerdict(
        flagged=flagged,
        diagnostic_only=True,
        win_eligible=True,
        metric=metric,
        ours_score=ours_score,
        baseline_score=baseline_score,
        delta=gap,
        closeness_threshold=delta,
        baseline=baseline_arm,
        reason=reason,
    )


def _decide(
    ours_score: float | None,
    baseline_score: float | None,
    gap: float | None,
    *,
    metric: str,
    delta: float,
) -> tuple[bool, str]:
    """Apply the documented closeness rule and return (flagged, human-readable reason).
    ``gap`` is ``|ours - baseline|`` when both scores are measured, else ``None``.

    - ``gap`` None (empty judged set) -> not measured, no flag.
    - Baseline scored 0 (dumb retriever found nothing relevant) -> the judged set is
      NOT recoverable by token overlap, the opposite of circularity -> no flag.
    - gap <= delta -> ours's edge is explained by token overlap -> flag.
    - otherwise -> ours clears the baseline by more than delta -> no flag."""
    if gap is None or ours_score is None or baseline_score is None:
        return (
            False,
            f"{metric} not measured (empty judged relevant set); circularity not evaluated",
        )
    if baseline_score <= 0.0:
        return (
            False,
            f"token-overlap baseline {metric}={baseline_score:.3f} recovered nothing of the "
            "judged set — the judged ground truth is not a token-overlap proxy (no circularity)",
        )
    if gap <= delta:
        return (
            True,
            f"ours {metric}={ours_score:.3f} ~= token-overlap baseline "
            f"{metric}={baseline_score:.3f} (|Δ|={gap:.3f} <= {delta}); ours's advantage over "
            "the judged set is explained by token overlap — the judged ground truth may be a "
            "proxy for ours's keyword mechanism",
        )
    return (
        False,
        f"ours {metric}={ours_score:.3f} clears the token-overlap baseline "
        f"{metric}={baseline_score:.3f} by |Δ|={gap:.3f} > {delta}; the judged advantage is "
        "not explained by token overlap",
    )
