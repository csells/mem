"""mem-bxhh.5 — calibrate the synthetic generator against the real fail-to-pass anchor.

The synthetic-generator PRD is gated on Gate 0 (construct validity): the per-config
ranking the memory arms produce on the SYNTHETIC suite must rank-correlate with the
ranking the SAME arms produce on a held-out REAL task set
(``prd_grounded_factorial_memory_diagnosis_generator.md`` §Gate 0; acceptance
Spearman rho ≥ 0.6). The bead asks for that correlation "or its absence" — and the
absence, with a concrete reason, is itself the PRD's named valid exit (the honest
null).

This module computes the verdict mechanically and is hardened with the premortem's R1
flat-anchor detector: it refuses to certify a correlation against an anchor that does
not itself rank the configs non-flatly (a flat-vs-flat rho is spurious). It is general —
a future non-flat anchor with shared arms yields a real rho and a GO — but on the anchor
recorded today (mem-1fl8/mem-58rp) it returns NO-GO for two independent reasons:

* the real anchor is statistically flat (no arm's lift CI clears 0 at N=8), and
* the only discriminating real arms (``ours``, ``builtin``) have no synthetic
  counterpart — ``ours`` is replay-only and ``builtin`` is the paid-Harbor built-in
  memory path; the synthetic scripted suite and the real anchor share only the
  ``none`` baseline, so the cross-suite rank-correlation is uncomputable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from membench.grading.base_rate import Z_95


@dataclass(frozen=True)
class RealAnchor:
    """The held-out real fail-to-pass anchor: each arm's pass count over ``n`` scored
    bundles. ``lift`` is ``pass_rate(arm) - pass_rate(baseline)`` — the same arm-none
    delta the synthetic suite reports — so the two suites are ranked on one axis.

    Recorded, not recomputed here: re-running the arms is a paid Harbor grid. Default
    is the mem-1fl8 sound-oracle eval (mem-58rp / wanz.9)."""

    pass_counts: dict[str, int]
    n: int
    baseline_arm: str
    source: str

    def __post_init__(self) -> None:
        if self.n <= 0:
            raise ValueError("anchor n must be positive")
        if self.baseline_arm not in self.pass_counts:
            raise ValueError(f"baseline arm {self.baseline_arm!r} not among pass_counts")
        for arm, k in self.pass_counts.items():
            if not 0 <= k <= self.n:
                raise ValueError(f"arm {arm!r} pass count {k} out of range [0, {self.n}]")

    def pass_rate(self, arm: str) -> float:
        return self.pass_counts[arm] / self.n

    def lifts(self) -> dict[str, float]:
        """Per-arm lift over the baseline (baseline lift is 0 by construction)."""
        base = self.pass_rate(self.baseline_arm)
        return {arm: self.pass_rate(arm) - base for arm in self.pass_counts}


def mem1fl8_anchor() -> RealAnchor:
    """The recorded real anchor: the recovered-oracle eval over the 407 sound oracles
    (mem-9xvb commit-message linkage), of which 8 were scorable. none 0/8, ours 0/8
    (+0.000), builtin 1/8 (+0.125). See bd memory ``mem-wanz-sound-tier-headline-null``
    and ``docs/mem-outcome-linkage-lever-status.md``."""
    return RealAnchor(
        pass_counts={"none-clean": 0, "ours": 0, "builtin": 1},
        n=8,
        baseline_arm="none-clean",
        source="mem-1fl8/mem-58rp wanz.9 sound-oracle eval (branch mem-58rp-wanz9-run @ adff941)",
    )


def canonical_arm(name: str) -> str:
    """Fold arm aliases so the suites align on one name. The real harness names its
    fresh clean-room baseline ``none-clean``; the synthetic scripted suite names it
    ``none``. Everything else is passed through unchanged."""
    folded = name.strip().lower()
    return "none" if folded in {"none", "none-clean", "none_clean"} else folded


def _lift_ci_excludes_zero(k_arm: int, k_base: int, n: int) -> bool:
    """Does the arm-baseline lift's 95% CI exclude 0? (difference of two proportions
    over the same ``n`` scored bundles).

    A Wald interval on the *difference* — the anchor records only aggregate pass counts
    per arm, not paired per-bundle outcomes, so a single-proportion Wilson bound
    (``grading.base_rate``) does not apply, and a paired test (mcnemar) has no per-bundle
    data to consume. The verdict is robust to the interval choice at the recorded anchor:
    1/8 vs 0/8 includes 0 under any reasonable construction (the Wilson intervals of the
    two arms overlap), so the flat conclusion does not hinge on the Wald approximation."""
    p_arm = k_arm / n
    p_base = k_base / n
    lift = p_arm - p_base
    var = p_arm * (1 - p_arm) / n + p_base * (1 - p_base) / n
    half = Z_95 * math.sqrt(var)
    return (lift - half) > 0 or (lift + half) < 0


def _average_ranks(values: list[float]) -> list[float]:
    """1-based ranks with ties averaged (the Spearman tie correction)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for pos in range(i, j + 1):
            ranks[order[pos]] = avg
        i = j + 1
    return ranks


def spearman_rho(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation (Pearson on average ranks). Raises if fewer than two
    points or if either series is constant (rank variance 0 ⇒ correlation undefined)."""
    if len(xs) != len(ys):
        raise ValueError("xs and ys must be the same length")
    if len(xs) < 2:
        raise ValueError("need at least two points for a rank correlation")
    rx = _average_ranks(xs)
    ry = _average_ranks(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        raise ValueError("a series is constant; rank correlation is undefined")
    return cov / math.sqrt(vx * vy)


@dataclass(frozen=True)
class CalibrationVerdict:
    """The Gate-0 readout. ``go`` is True only when the anchor discriminates AND the
    synthetic↔real rank correlation clears the threshold over the shared arms."""

    go: bool
    gate0: str
    reason: str
    rho: float | None
    rho_threshold: float
    shared_discriminating_arms: tuple[str, ...]
    anchor_flat: bool
    anchor_span: float
    synthetic_lifts: dict[str, float] = field(default_factory=dict)
    anchor_lifts: dict[str, float] = field(default_factory=dict)


def calibrate(
    synthetic_lifts: dict[str, float],
    anchor: RealAnchor,
    *,
    rho_threshold: float = 0.6,
) -> CalibrationVerdict:
    """Compare the synthetic per-arm lift ranking against the real anchor's.

    Order of checks (R1 hardening first): a flat anchor cannot be correlated against,
    and an anchor whose discriminating arms have no synthetic counterpart leaves nothing
    to correlate. Only when both hurdles clear is rho computed and compared to threshold."""
    anchor_lifts = anchor.lifts()
    anchor_span = max(anchor_lifts.values()) - min(anchor_lifts.values())

    # R1: does ANY non-baseline arm's lift CI clear 0? If none, the anchor is flat.
    base_k = anchor.pass_counts[anchor.baseline_arm]
    discriminating = [
        arm
        for arm, k in anchor.pass_counts.items()
        if arm != anchor.baseline_arm and _lift_ci_excludes_zero(k, base_k, anchor.n)
    ]
    anchor_flat = not discriminating

    syn = {canonical_arm(a): v for a, v in synthetic_lifts.items()}
    anc = {canonical_arm(a): v for a, v in anchor_lifts.items()}
    baseline = canonical_arm(anchor.baseline_arm)
    # Shared arms that carry rank information: present in both suites, not the baseline.
    shared = tuple(sorted(a for a in syn.keys() & anc.keys() if a != baseline))

    if anchor_flat:
        return CalibrationVerdict(
            go=False,
            gate0="NO-GO (flat anchor)",
            reason=(
                f"real anchor does not rank memory configs non-flatly: no arm's lift CI "
                f"clears 0 at N={anchor.n} (span={anchor_span:.3f}). Gate 0 is uncomputable "
                f"— the PRD's honest-null exit. Source: {anchor.source}."
            ),
            rho=None,
            rho_threshold=rho_threshold,
            shared_discriminating_arms=shared,
            anchor_flat=True,
            anchor_span=anchor_span,
            synthetic_lifts=syn,
            anchor_lifts=anc,
        )

    if len(shared) < 2:
        unmatched = sorted(a for a in anc.keys() - syn.keys() if a != baseline)
        return CalibrationVerdict(
            go=False,
            gate0="NO-GO (uncomputable: arm overlap < 2)",
            reason=(
                f"the real anchor's discriminating arms {unmatched} have no synthetic "
                f"counterpart (ours is replay-only; builtin is the paid-Harbor built-in "
                f"path), so the suites share only the baseline. A cross-suite rank "
                f"correlation needs ≥2 shared non-baseline arms; have {len(shared)}."
            ),
            rho=None,
            rho_threshold=rho_threshold,
            shared_discriminating_arms=shared,
            anchor_flat=False,
            anchor_span=anchor_span,
            synthetic_lifts=syn,
            anchor_lifts=anc,
        )

    rho = spearman_rho([syn[a] for a in shared], [anc[a] for a in shared])
    go = rho >= rho_threshold
    return CalibrationVerdict(
        go=go,
        gate0="GO" if go else f"NO-GO (rho {rho:.3f} < {rho_threshold})",
        reason=(
            f"Spearman rho={rho:.3f} over {len(shared)} shared arms {list(shared)} "
            f"vs threshold {rho_threshold}."
        ),
        rho=rho,
        rho_threshold=rho_threshold,
        shared_discriminating_arms=shared,
        anchor_flat=False,
        anchor_span=anchor_span,
        synthetic_lifts=syn,
        anchor_lifts=anc,
    )


def format_calibration_report(verdict: CalibrationVerdict) -> str:
    """A compact text readout of the Gate-0 verdict."""
    lines = [
        "# mem-bxhh.5 — synthetic↔real-ftp calibration (Gate 0)",
        f"verdict      : {verdict.gate0}",
        f"reason       : {verdict.reason}",
        f"spearman rho   : {'n/a' if verdict.rho is None else f'{verdict.rho:.3f}'}"
        f"  (threshold {verdict.rho_threshold})",
        f"anchor flat  : {verdict.anchor_flat}  (span {verdict.anchor_span:.3f})",
        f"shared arms  : {list(verdict.shared_discriminating_arms) or '— (baseline only)'}",
        "",
        f"{'arm':<14}{'synthetic lift':>16}{'real-anchor lift':>18}",
        "-" * 48,
    ]
    arms = sorted(set(verdict.synthetic_lifts) | set(verdict.anchor_lifts))
    for arm in arms:
        s = verdict.synthetic_lifts.get(arm)
        a = verdict.anchor_lifts.get(arm)
        s_cell = "—" if s is None else f"{s:.3f}"
        a_cell = "—" if a is None else f"{a:.3f}"
        lines.append(f"{arm:<14}{s_cell:>16}{a_cell:>18}")
    return "\n".join(lines)
