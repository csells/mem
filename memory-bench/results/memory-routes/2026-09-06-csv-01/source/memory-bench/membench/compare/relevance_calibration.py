"""Relevance-label calibration store + pre-registered frozen judge-vs-human gate (mem-lvp.33).

The defensibility anchor for the judged-relevance lane (`judged_relevance.py`): the
quantitative detector of failure-signature circularity re-entering through the judge.
It calibrates the judge's relevance LABELS — the binary ``relevant?`` /  graded 0-3
verdicts `relevance_judge.py` emits — against a frozen human-labelled subset, and
gates on the SAME pre-registered bar `grading.safety_gates` uses for confabulation:
``kappa >= 0.6 AND fpr <= 0.05``. Thresholds live in code (here and re-exported from
safety_gates) BEFORE any rate is measured — the minority-report-B discipline: the bar
cannot be set after seeing the numbers.

This is deliberately NOT `grading.judge.Calibration`, which reports mean-absolute-error
and a within-tolerance rate. That shape fits a continuous [0,1] quality score; it is
the WRONG instrument for a categorical relevance label, where a near-miss numeric gap
is meaningless and chance-corrected agreement (Cohen's kappa) plus the per-class
false-positive rate are the operative statistics. Binary-vs-graded is fixed at
pre-registration, so the store supports BOTH behind one interface: binary mode reports
Cohen's kappa + per-class precision/recall/FPR; graded mode reports quadratic-weighted
kappa.

Agreement is broken out per CONTRIBUTING ARM (``ours`` vs ``semantic`` vs
``overlap``) and per HARD STRATUM (same-error/no-fix distractors vs
different-wording/real-fix transfers), and the gate adds a pre-registered per-arm
FPR-GAP bound ``|fpr_ours - fpr_semantic| <= 0.05`` — the direct test that the judge
is not systematically more permissive toward ours's own hits. On gate FAIL the judged
retrieval metrics are win-INELIGIBLE / diagnostic-only: a flag the compare envelope
carries so a failed calibration can never become the headline.

ZFC boundary: the relevance JUDGMENT stays in the judge (`relevance_judge.py`). Every
statistic here — kappa, FPR, quadratic-weighted kappa, the FPR gap — is deterministic
arithmetic over hand-labelled pairs, pure mechanism, never a semantic decision. The
store is fully fixture-testable: no Ollama, no network, no live judge.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from membench.compare.relevance_judge import GRADE_MAX, GRADE_MIN, RelevanceMode
from membench.grading.safety_gates import PREREGISTERED_FPR_MAX, PREREGISTERED_KAPPA_MIN

# Pre-registered in code BEFORE measuring (minority report B). The per-arm FPR-gap
# bound is the third operative criterion alongside the κ-floor and FPR-ceiling the
# safety_gates SSOT already pins: a judge that clears the global FPR bar can still be
# systematically more permissive toward ONE arm, and that asymmetry is exactly the
# failure-signature circularity this calibration exists to catch. Set at the same 5%.
PREREGISTERED_FPR_GAP_MAX = 0.05

# The two contributing arms whose per-arm FPRs the gap bound compares. ``overlap`` is
# the third breakdown bucket (candidates both arms surfaced) but is not part of the
# directional gap test.
_OURS_ARM = "ours"
_SEMANTIC_ARM = "semantic"


@dataclass(frozen=True)
class BinaryLabelPair:
    """One human-vs-judge BINARY relevance observation. ``arm`` is the contributing
    retrieval arm (``ours`` / ``semantic`` / ``overlap``) and ``stratum`` the hard
    bucket (``distractor`` / ``transfer``) the pooled candidate came from; both are
    optional so a pooled set with no provenance still calibrates globally."""

    human: bool
    judge: bool
    arm: str | None = None
    stratum: str | None = None


@dataclass(frozen=True)
class GradedLabelPair:
    """One human-vs-judge GRADED relevance observation, each grade in [GRADE_MIN,
    GRADE_MAX]. Same optional ``arm`` / ``stratum`` provenance as the binary pair."""

    human: int
    judge: int
    arm: str | None = None
    stratum: str | None = None


@dataclass(frozen=True)
class ClassMetrics:
    """Per-class binary agreement over one slice (global, one arm, or one stratum):
    raw percent-agreement plus the relevant-class precision/recall/FPR (binary) or the
    quadratic-weighted κ (graded). ``kappa`` is Cohen's κ for a binary slice and
    ``None`` for a graded one; ``weighted_kappa`` is the reverse — each κ variant in
    its own field so a consumer never mistakes the weighted value for the linear one.
    ``precision`` / ``recall`` / ``fpr`` are binary-only and ``None`` in graded mode,
    and binary-side ``None`` whenever the underlying ratio is undefined (no
    judge-positive / human-positive / human-negative respectively) — surfaced as
    absence, never a silently-zero rate."""

    n: int
    percent_agreement: float
    kappa: float | None
    weighted_kappa: float | None
    precision: float | None
    recall: float | None
    fpr: float | None


@dataclass(frozen=True)
class CalibrationGateVerdict:
    """The pre-registered gate readout. ``passed`` requires the operative κ ≥ bar AND
    (when FPR is defined) fpr ≤ bar AND (when both arms are present) the per-arm FPR gap
    ≤ bar. ``kappa`` is Cohen's κ in binary mode, ``None`` in graded mode;
    ``weighted_kappa`` is quadratic-weighted κ in graded mode, ``None`` in binary —
    each statistic in its own field, never one masquerading as the other. ``fpr`` is
    ``None`` when undefined (graded mode, or a binary set with no human-negative): an
    undefined statistic is surfaced as absence, not coerced to a meaningful-looking
    zero. ``win_eligible`` is the negation of ``diagnostic_only`` — on FAIL the judged
    retrieval metrics are diagnostic-only and the compare envelope must never headline
    them. The pre-registered thresholds ride on the verdict as provenance."""

    mode: RelevanceMode
    passed: bool
    win_eligible: bool
    diagnostic_only: bool
    kappa: float | None
    weighted_kappa: float | None
    fpr: float | None
    fpr_gap: float | None
    reason: str
    prereg_kappa_min: float = PREREGISTERED_KAPPA_MIN
    prereg_fpr_max: float = PREREGISTERED_FPR_MAX
    prereg_fpr_gap_max: float = PREREGISTERED_FPR_GAP_MAX


@dataclass(frozen=True)
class CalibrationReport:
    """The agreement summary over the labelled calibration set. Binary mode populates
    ``kappa`` + per-class ``precision``/``recall``/``fpr`` and leaves
    ``weighted_kappa`` ``None``; graded mode populates ``weighted_kappa`` and leaves
    the binary-only fields ``None`` (one interface, two shapes). ``per_arm`` /
    ``per_stratum`` break agreement out by contributing arm and hard stratum;
    ``fpr_gap`` is ``|fpr_ours - fpr_semantic|`` when both arms are labelled, else
    ``None``."""

    mode: RelevanceMode
    n: int
    percent_agreement: float
    kappa: float | None
    weighted_kappa: float | None
    precision: float | None
    recall: float | None
    fpr: float | None
    fpr_gap: float | None
    per_arm: dict[str, ClassMetrics]
    per_stratum: dict[str, ClassMetrics]

    def gate(self) -> CalibrationGateVerdict:
        """Apply the pre-registered bar. Binary mode gates on Cohen's κ; graded mode on
        the quadratic-weighted κ (the same floor). The FPR ceiling is gated only where
        FPR is DEFINED (binary mode with a human-negative); an undefined FPR (graded
        mode, or no negatives) is reported as absence and noted in ``reason``, never
        coerced to a passing zero. The per-arm FPR-gap bound applies when both arms are
        labelled. A FAIL marks the judged metrics diagnostic-only / win-ineligible."""
        kappa_value = self.weighted_kappa if self.mode == "graded" else self.kappa
        if kappa_value is None:
            raise ValueError("report has no κ to gate on — empty or malformed slice")

        reasons: list[str] = []
        if kappa_value < PREREGISTERED_KAPPA_MIN:
            label = "weighted_kappa" if self.mode == "graded" else "kappa"
            reasons.append(f"{label} {kappa_value:.3f} < {PREREGISTERED_KAPPA_MIN}")
        if self.fpr is None:
            reasons.append("fpr undefined (no human-negative items) — FPR criterion not evaluated")
        elif self.fpr > PREREGISTERED_FPR_MAX:
            reasons.append(f"fpr {self.fpr:.3f} > {PREREGISTERED_FPR_MAX}")
        if self.fpr_gap is not None and self.fpr_gap > PREREGISTERED_FPR_GAP_MAX:
            reasons.append(f"per-arm fpr gap {self.fpr_gap:.3f} > {PREREGISTERED_FPR_GAP_MAX}")

        # An undefined FPR is reported as a caveat but does NOT itself fail a binary
        # gate that otherwise clears κ; the binary path always has negatives in a real
        # calibration set, so this only fires on a degenerate all-positive fixture.
        # Graded mode gates on weighted-κ alone (FPR is not a graded statistic).
        blocking = [r for r in reasons if "not evaluated" not in r]
        passed = not blocking
        return CalibrationGateVerdict(
            mode=self.mode,
            passed=passed,
            win_eligible=passed,
            diagnostic_only=not passed,
            kappa=self.kappa,
            weighted_kappa=self.weighted_kappa,
            fpr=self.fpr,
            fpr_gap=self.fpr_gap,
            reason="; ".join(reasons) if reasons else "calibration cleared the pre-registered bar",
        )

    def breakdown(self) -> dict[str, Any]:
        """The per-arm / per-stratum agreement breakdown as plain JSON, for the frozen
        artifact and the compare envelope."""
        return {
            "per_arm": {arm: _class_metrics_to_dict(m) for arm, m in self.per_arm.items()},
            "per_stratum": {s: _class_metrics_to_dict(m) for s, m in self.per_stratum.items()},
        }

    def write_frozen(self, path: Path, *, prompt_version: str) -> None:
        """Freeze the human-subset calibration to one self-describing JSON artifact:
        ``{frozen: true, prompt_version, kappa, fpr, weighted_kappa, gate verdict,
        per-arm/per-stratum breakdown}``. ``load_frozen_calibration`` asserts
        ``frozen`` before any consumer trusts the labels."""
        verdict = self.gate()
        blob: dict[str, Any] = {
            "frozen": True,
            "prompt_version": prompt_version,
            "mode": self.mode,
            "n": self.n,
            "percent_agreement": self.percent_agreement,
            "kappa": self.kappa,
            "weighted_kappa": self.weighted_kappa,
            "precision": self.precision,
            "recall": self.recall,
            "fpr": self.fpr,
            "fpr_gap": self.fpr_gap,
            "gate": {
                "passed": verdict.passed,
                "win_eligible": verdict.win_eligible,
                "diagnostic_only": verdict.diagnostic_only,
                "reason": verdict.reason,
                "prereg_kappa_min": verdict.prereg_kappa_min,
                "prereg_fpr_max": verdict.prereg_fpr_max,
                "prereg_fpr_gap_max": verdict.prereg_fpr_gap_max,
            },
            "breakdown": self.breakdown(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(blob, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class FrozenCalibration:
    """A loaded frozen human-subset calibration artifact. ``frozen`` is asserted true
    by `load_frozen_calibration` before construction, so a consumer holding this object
    can trust the labels were not edited after freezing."""

    frozen: bool
    prompt_version: str
    mode: RelevanceMode
    kappa: float | None
    weighted_kappa: float | None
    fpr: float | None
    fpr_gap: float | None
    gate_passed: bool
    breakdown: dict[str, Any]


class RelevanceCalibration:
    """A calibration store for judge-vs-human relevance LABELS, supporting BOTH the
    binary and graded label shapes behind one interface (the choice is fixed at
    pre-registration). Pure mechanism: it validates inputs, stores hand-labelled
    pairs, and aggregates into a `CalibrationReport`. The relevance judgment itself is
    the judge's; this store never makes one."""

    def __init__(self, mode: RelevanceMode | Literal["binary", "graded"]) -> None:
        if mode not in ("binary", "graded"):
            raise ValueError(f"unknown calibration mode {mode!r}; expected binary or graded")
        self._mode: RelevanceMode = mode
        self._binary: list[BinaryLabelPair] = []
        self._graded: list[GradedLabelPair] = []

    @property
    def mode(self) -> RelevanceMode:
        return self._mode

    def record_binary(self, pair: BinaryLabelPair) -> None:
        """Store one binary observation. Raises if the store is in graded mode — a
        mismatched label shape is a real error, never silently coerced."""
        if self._mode != "binary":
            raise ValueError("cannot record a binary pair into a graded calibration store")
        self._binary.append(pair)

    def record_graded(self, pair: GradedLabelPair) -> None:
        """Store one graded observation, each grade validated into [GRADE_MIN,
        GRADE_MAX]. Raises if the store is in binary mode or a grade is out of range."""
        if self._mode != "graded":
            raise ValueError("cannot record a graded pair into a binary calibration store")
        for who, grade in (("human", pair.human), ("judge", pair.judge)):
            if not GRADE_MIN <= grade <= GRADE_MAX:
                raise ValueError(f"{who} grade out of range [{GRADE_MIN}, {GRADE_MAX}]: {grade}")
        self._graded.append(pair)

    def report(self) -> CalibrationReport:
        """Aggregate the recorded pairs into the agreement summary. Raises on an empty
        set — an agreement statistic over zero observations is undefined, never a
        defaulted zero."""
        if self._mode == "binary":
            return self._binary_report()
        return self._graded_report()

    # ----------------------------------------------------------------- binary
    def _binary_report(self) -> CalibrationReport:
        if not self._binary:
            raise ValueError("calibration set is empty — record at least one pair first")
        pairs = [(p.human, p.judge) for p in self._binary]
        global_m = _binary_class_metrics(pairs)

        per_arm = self._binary_slice("arm")
        per_stratum = self._binary_slice("stratum")
        fpr_gap = _fpr_gap(per_arm)

        return CalibrationReport(
            mode="binary",
            n=global_m.n,
            percent_agreement=global_m.percent_agreement,
            kappa=global_m.kappa,
            weighted_kappa=None,
            precision=global_m.precision,
            recall=global_m.recall,
            fpr=global_m.fpr,
            fpr_gap=fpr_gap,
            per_arm=per_arm,
            per_stratum=per_stratum,
        )

    def _binary_slice(self, attr: Literal["arm", "stratum"]) -> dict[str, ClassMetrics]:
        buckets: dict[str, list[tuple[bool, bool]]] = {}
        for p in self._binary:
            key = getattr(p, attr)
            if key is None:
                continue
            buckets.setdefault(key, []).append((p.human, p.judge))
        return {key: _binary_class_metrics(rows) for key, rows in buckets.items()}

    # ----------------------------------------------------------------- graded
    def _graded_report(self) -> CalibrationReport:
        if not self._graded:
            raise ValueError("calibration set is empty — record at least one pair first")
        pairs = [(p.human, p.judge) for p in self._graded]
        wk = _quadratic_weighted_kappa(pairs)
        agree = sum(1 for h, j in pairs if h == j) / len(pairs)
        per_arm = self._graded_slice("arm")
        per_stratum = self._graded_slice("stratum")
        return CalibrationReport(
            mode="graded",
            n=len(pairs),
            percent_agreement=agree,
            kappa=None,
            weighted_kappa=wk,
            precision=None,
            recall=None,
            fpr=None,
            fpr_gap=None,
            per_arm=per_arm,
            per_stratum=per_stratum,
        )

    def _graded_slice(self, attr: Literal["arm", "stratum"]) -> dict[str, ClassMetrics]:
        buckets: dict[str, list[tuple[int, int]]] = {}
        for p in self._graded:
            key = getattr(p, attr)
            if key is None:
                continue
            buckets.setdefault(key, []).append((p.human, p.judge))
        out: dict[str, ClassMetrics] = {}
        for key, rows in buckets.items():
            agree = sum(1 for h, j in rows if h == j) / len(rows)
            out[key] = ClassMetrics(
                n=len(rows),
                percent_agreement=agree,
                kappa=None,
                weighted_kappa=_quadratic_weighted_kappa(rows),
                precision=None,
                recall=None,
                fpr=None,
            )
        return out


# ---------------------------------------------------------------- arithmetic
def _binary_class_metrics(pairs: list[tuple[bool, bool]]) -> ClassMetrics:
    """Confusion-matrix arithmetic over (human, judge) binary pairs: percent-agreement,
    Cohen's κ, and relevant-class precision/recall/FPR. Pure deterministic math."""
    n = len(pairs)
    tp = sum(1 for h, j in pairs if h and j)
    fp = sum(1 for h, j in pairs if not h and j)
    fn = sum(1 for h, j in pairs if h and not j)
    tn = sum(1 for h, j in pairs if not h and not j)

    agreement = (tp + tn) / n
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    human_neg = fp + tn
    fpr = fp / human_neg if human_neg else None
    return ClassMetrics(
        n=n,
        percent_agreement=agreement,
        kappa=_cohen_kappa(tp=tp, fp=fp, fn=fn, tn=tn),
        weighted_kappa=None,
        precision=precision,
        recall=recall,
        fpr=fpr,
    )


def _cohen_kappa(*, tp: int, fp: int, fn: int, tn: int) -> float:
    """Cohen's κ from a 2x2 confusion matrix: ``(p_o - p_e) / (1 - p_e)``. When both
    raters agree perfectly by chance (``p_e == 1`` — one rater used a single class for
    every item) κ is degenerate; we return 1.0 iff observed agreement is also perfect,
    else 0.0 (no chance-corrected signal)."""
    n = tp + fp + fn + tn
    p_o = (tp + tn) / n
    # Marginal probabilities of the positive class for each rater.
    human_pos = (tp + fn) / n
    judge_pos = (tp + fp) / n
    p_e = human_pos * judge_pos + (1 - human_pos) * (1 - judge_pos)
    if p_e >= 1.0:
        return 1.0 if p_o >= 1.0 else 0.0
    return (p_o - p_e) / (1 - p_e)


def _quadratic_weighted_kappa(pairs: list[tuple[int, int]]) -> float:
    """Quadratic-weighted Cohen's κ over graded labels in [GRADE_MIN, GRADE_MAX]. The
    quadratic weighting ``w_ij = ((i-j)/(K-1))^2`` makes a near-miss penalise far less
    than a far miss. Returns 1.0 when the weighted disagreement is zero by chance (a
    single-grade column/row) iff observed disagreement is also zero, else 0.0."""
    k = GRADE_MAX - GRADE_MIN + 1
    if k <= 1:
        return 1.0
    n = len(pairs)
    denom = (k - 1) ** 2

    def weight(i: int, j: int) -> float:
        return ((i - j) ** 2) / denom

    # Observed and expected (marginal-product) histograms over the K x K grid.
    human_hist = [0] * k
    judge_hist = [0] * k
    observed: dict[tuple[int, int], int] = {}
    for h, j in pairs:
        hi, ji = h - GRADE_MIN, j - GRADE_MIN
        human_hist[hi] += 1
        judge_hist[ji] += 1
        observed[(hi, ji)] = observed.get((hi, ji), 0) + 1

    num = 0.0
    den = 0.0
    for i in range(k):
        for j in range(k):
            w = weight(i, j)
            o = observed.get((i, j), 0) / n
            e = (human_hist[i] / n) * (judge_hist[j] / n)
            num += w * o
            den += w * e
    if den == 0.0:
        return 1.0 if num == 0.0 else 0.0
    return 1.0 - num / den


def _fpr_gap(per_arm: dict[str, ClassMetrics]) -> float | None:
    """The directional per-arm FPR gap ``|fpr_ours - fpr_semantic|`` — the test that
    the judge is not systematically more permissive toward ours's own hits. ``None``
    when either arm is absent or has no human-negative to define an FPR."""
    ours = per_arm.get(_OURS_ARM)
    semantic = per_arm.get(_SEMANTIC_ARM)
    if ours is None or semantic is None or ours.fpr is None or semantic.fpr is None:
        return None
    return abs(ours.fpr - semantic.fpr)


def _class_metrics_to_dict(m: ClassMetrics) -> dict[str, Any]:
    return {
        "n": m.n,
        "percent_agreement": m.percent_agreement,
        "kappa": m.kappa,
        "weighted_kappa": m.weighted_kappa,
        "precision": m.precision,
        "recall": m.recall,
        "fpr": m.fpr,
    }


# ----------------------------------------------------------- frozen artifact
def load_frozen_calibration(path: Path) -> FrozenCalibration:
    """Load a frozen human-subset calibration artifact, asserting ``frozen == true``
    before returning it. An unfrozen or flag-missing artifact raises — a consumer must
    never trust labels that could have been edited after the human-labelling act."""
    blob = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(blob, dict):
        raise ValueError(f"calibration artifact is not a JSON object: {blob!r}")
    if blob.get("frozen") is not True:
        raise ValueError(
            f"calibration artifact at {path} is not frozen (frozen={blob.get('frozen')!r}); "
            "refusing to trust un-frozen labels"
        )
    prompt_version = blob.get("prompt_version")
    if not isinstance(prompt_version, str) or not prompt_version:
        raise ValueError(f"frozen calibration artifact at {path} has no prompt_version")
    if "mode" not in blob:
        raise ValueError(f"frozen calibration artifact at {path} has no mode")
    gate = blob.get("gate") or {}
    return FrozenCalibration(
        frozen=True,
        prompt_version=prompt_version,
        mode=_require_mode(blob["mode"]),
        kappa=blob.get("kappa"),
        weighted_kappa=blob.get("weighted_kappa"),
        fpr=blob.get("fpr"),
        fpr_gap=blob.get("fpr_gap"),
        gate_passed=bool(gate.get("passed", False)),
        breakdown=blob.get("breakdown", {}),
    )


def relevance_calibration_authority(calibration_path: Path | None) -> str:
    """Win-eligibility authority for the judged-relevance lane, mirroring
    `safety_gates.confabulation_authority`: ``cleared`` only when a frozen calibration
    artifact on disk passes the FULL pre-registered gate (κ ≥ 0.6 AND fpr ≤ 0.05 AND
    per-arm gap ≤ 0.05), else ``flag``. Absent or unfrozen ⇒ ``flag`` by construction
    — the bar is earned, never granted by a config flag."""
    if calibration_path is None or not calibration_path.exists():
        return "flag"
    try:
        loaded = load_frozen_calibration(calibration_path)
    except ValueError:
        return "flag"
    return "cleared" if loaded.gate_passed else "flag"


def _require_mode(mode: Any) -> RelevanceMode:
    if mode == "binary":
        return "binary"
    if mode == "graded":
        return "graded"
    raise ValueError(f"unknown calibration mode {mode!r}; expected binary or graded")
