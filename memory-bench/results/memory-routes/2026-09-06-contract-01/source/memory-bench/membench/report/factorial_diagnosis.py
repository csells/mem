"""Gate 0a diagnosis reporter — factorial main effects + interactions (ZFC arithmetic).

PRD ``prd_grounded_factorial_memory_diagnosis_generator.md`` (Should-Have: diagnosis
reporter; Gate 0a recovery half). Consumes per-cell graded responses keyed by factor
levels + replicate and emits the failure/benefit-mode map: every main effect and
interaction over the factors, each with an effect size and a paired-bootstrap CI.

The response is a single scalar per (cell, replicate) — a graded score
(``grading.graded``) for a per-config map, or a cross-arm memory-benefit delta
(``benefit_observations``) for the failure/benefit-mode map the PRD wants ("config X
fails specifically under supersession*interference"). Higher response = better, so a
positive effect HELPS and a negative effect HURTS.

The estimator is the standard 2^k factorial contrast, computed per matched group
(remaining factors fixed at one corner, same replicate) so it reuses the existing
matched-pair paired-bootstrap seam (``handoff_efficiency.bootstrap_median_ci``). The
reported effect is the **median** of the per-group contrasts (not the textbook ANOVA
mean) — robust to an outlier group, at the cost of a small bias when the contrast
distribution is skewed; in symmetric noise it equals the mean. The
``shuffle_responses`` negative control is the other half of Gate 0a recovery: once the
cell→response link is destroyed there is no effect in expectation, so across shuffles
the recovered effect collapses (CI spans 0) — any single shuffle is one random draw.

ZFC: every response is the model's (the graded judge); this module is pure arithmetic
over those scores — contrast sums, bootstrap resampling, sign of the CI. No semantic
judgment, no hardcoded thresholds beyond the CI's "clears 0" reading.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import combinations

from membench.generators.factorial_dag import NON_DEPTH_FACTORS
from membench.handoff_efficiency import bootstrap_median_ci


# Intentionally NOT frozen: ``levels`` holds a plain mapping, which a frozen dataclass
# could not hash (its generated ``__hash__`` would raise), so freezing would advertise a
# hashability contract it cannot keep. Treat instances as immutable DTOs — never mutate;
# derive a new one with ``dataclasses.replace``.
@dataclass
class Observation:
    """One graded response for a factorial cell in one replicate. ``levels`` maps every
    factor name to its ON/OFF level; ``replicate`` is the matched key the paired
    bootstrap resamples within (e.g. a seed); ``response`` is the scalar attributed."""

    levels: Mapping[str, bool]
    replicate: str
    response: float


@dataclass(frozen=True)
class FactorEffect:
    """The estimated effect of a factor subset on the response. ``factors`` is the
    subset (length 1 = main effect, ≥2 = interaction); ``effect`` is the median
    contrast with ``ci_low``/``ci_high`` percentile-bootstrap bounds; ``n_contrasts``
    is how many complete matched groups contributed; ``direction`` reads the CI."""

    factors: tuple[str, ...]
    effect: float
    ci_low: float
    ci_high: float
    n_contrasts: int
    direction: str  # "helps" | "hurts" | "inconclusive"

    @property
    def label(self) -> str:
        return "*".join(self.factors)


@dataclass(frozen=True)
class FactorialDiagnosis:
    """The failure/benefit-mode map: every main effect and interaction over the
    factors, plus the count of incomplete matched groups that were skipped (surfaced,
    never silently dropped — a fractional design loses contrasts here).

    ``skipped_incomplete_groups`` counts ``(effect-subset, matched-group)`` pairs, NOT
    unique dropped observations: one missing corner of a full 3-factor factorial leaves
    seven effects each missing one group, so it increments by seven."""

    effects: tuple[FactorEffect, ...]
    n_observations: int
    skipped_incomplete_groups: int

    def effect_for(self, *factors: str) -> FactorEffect:
        """The effect for an exact factor subset (order-independent)."""
        want = frozenset(factors)
        for eff in self.effects:
            if frozenset(eff.factors) == want:
                return eff
        raise KeyError(f"no effect estimated for {sorted(want)}")


def _direction(ci_low: float, ci_high: float) -> str:
    if ci_low > 0.0:
        return "helps"
    if ci_high < 0.0:
        return "hurts"
    return "inconclusive"


def _contrasts_for_subset(
    observations: Sequence[Observation],
    factors: tuple[str, ...],
    subset: tuple[str, ...],
) -> tuple[list[float], int]:
    """The per-matched-group factorial contrast over ``subset``: group observations by
    (replicate, remaining-factor levels), and within each complete group of 2^|subset|
    corners take the signed Yates contrast. Returns the contrast values and the number
    of incomplete groups skipped."""
    remaining = tuple(f for f in factors if f not in subset)
    groups: dict[tuple[str, tuple[bool, ...]], dict[tuple[bool, ...], float]] = {}
    for obs in observations:
        rem_key = tuple(obs.levels[f] for f in remaining)
        sub_key = tuple(obs.levels[f] for f in subset)
        cell_map = groups.setdefault((obs.replicate, rem_key), {})
        if sub_key in cell_map:
            raise ValueError(
                f"duplicate observation for replicate {obs.replicate!r}, "
                f"remaining {rem_key}, corner {sub_key}"
            )
        cell_map[sub_key] = obs.response

    n_corners = 2 ** len(subset)
    norm = float(2 ** (len(subset) - 1))
    contrasts: list[float] = []
    skipped = 0
    for cell_map in groups.values():
        if len(cell_map) != n_corners:
            skipped += 1
            continue
        total = 0.0
        for sub_key, resp in cell_map.items():
            sign = 1
            for level in sub_key:
                sign *= 1 if level else -1
            total += sign * resp
        contrasts.append(total / norm)
    return contrasts, skipped


def diagnose(
    observations: Sequence[Observation],
    *,
    factors: Sequence[str] = NON_DEPTH_FACTORS,
    n_resamples: int = 5000,
    conf: float = 0.95,
    seed: int = 0,
) -> FactorialDiagnosis:
    """Attribute the response to every factor main effect and interaction.

    For each factor subset (1 = main, ≥2 = interaction) the per-group Yates contrasts
    are bootstrapped (``bootstrap_median_ci``) into an effect size + CI. Raises if any
    observation is missing a factor level, or if a requested effect has no complete
    matched group (the design cannot estimate it — fail loud, never report a phantom)."""
    if not observations:
        raise ValueError("diagnose needs at least one observation")
    factor_tuple = tuple(factors)
    if len(set(factor_tuple)) != len(factor_tuple):
        raise ValueError(f"duplicate factor names: {factor_tuple}")
    for obs in observations:
        missing = set(factor_tuple) - set(obs.levels)
        if missing:
            raise ValueError(f"observation missing factor levels {sorted(missing)}")

    effects: list[FactorEffect] = []
    total_skipped = 0
    for r in range(1, len(factor_tuple) + 1):
        for subset in combinations(factor_tuple, r):
            contrasts, skipped = _contrasts_for_subset(observations, factor_tuple, subset)
            total_skipped += skipped
            if not contrasts:
                raise ValueError(
                    f"no complete matched group for effect {subset}; design too incomplete"
                )
            point, lo, hi = bootstrap_median_ci(
                contrasts, n_resamples=n_resamples, conf=conf, seed=seed
            )
            effects.append(
                FactorEffect(
                    factors=subset,
                    effect=point,
                    ci_low=lo,
                    ci_high=hi,
                    n_contrasts=len(contrasts),
                    direction=_direction(lo, hi),
                )
            )
    return FactorialDiagnosis(
        effects=tuple(effects),
        n_observations=len(observations),
        skipped_incomplete_groups=total_skipped,
    )


def _match_key(obs: Observation, factors: Sequence[str]) -> tuple[str, tuple[bool, ...]]:
    return obs.replicate, tuple(obs.levels[f] for f in factors)


def benefit_observations(
    arm: Sequence[Observation],
    baseline: Sequence[Observation],
    *,
    factors: Sequence[str] = NON_DEPTH_FACTORS,
) -> list[Observation]:
    """Pair an arm's responses against a baseline's by (replicate, factor levels) and
    return the memory-benefit response (arm - baseline) per matched cell — the
    failure/benefit-mode response. The two sets must cover exactly the same cells; an
    unmatched or duplicated cell raises (never a silently dropped pair)."""
    factor_tuple = tuple(factors)
    base_by_key: dict[tuple[str, tuple[bool, ...]], Observation] = {}
    for obs in baseline:
        key = _match_key(obs, factor_tuple)
        if key in base_by_key:
            raise ValueError(f"duplicate baseline observation for {key}")
        base_by_key[key] = obs

    out: list[Observation] = []
    seen: set[tuple[str, tuple[bool, ...]]] = set()
    for obs in arm:
        key = _match_key(obs, factor_tuple)
        if key in seen:
            raise ValueError(f"duplicate arm observation for {key}")
        seen.add(key)
        base = base_by_key.get(key)
        if base is None:
            raise ValueError(f"arm observation {key} has no matching baseline")
        out.append(replace(obs, response=obs.response - base.response))

    unmatched = base_by_key.keys() - seen
    if unmatched:
        raise ValueError(f"baseline cells with no matching arm observation: {sorted(unmatched)}")
    return out


def shuffle_responses(observations: Sequence[Observation], *, seed: int) -> list[Observation]:
    """The Gate 0a negative control: permute responses across observations, destroying
    the cell→response link. With no link, there is no effect in expectation, so across
    shuffles the recovered effects collapse (CI spans 0) — judge the control in
    aggregate over several seeds, since any single shuffle is one random draw that can
    still show a spurious effect. Seeded ⇒ reproducible."""
    responses = [o.response for o in observations]
    rng = random.Random(seed)
    rng.shuffle(responses)
    return [replace(o, response=r) for o, r in zip(observations, responses, strict=True)]
