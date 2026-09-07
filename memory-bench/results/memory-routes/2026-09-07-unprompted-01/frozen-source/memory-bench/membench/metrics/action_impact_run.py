"""§4.4 action-impact run harness — roll per-step paired verdicts into per-arm raw
5-axis aggregates for a none / ours / builtin run over the lvp.8 sequences.

This is the deterministic scoring + aggregation core mem-lvp.19 needs: it pairs each
treated arm's per-step tool-call trajectory against its no-memory (``none``) twin,
runs the §12.6 `score_action_impact` seam over each pair, and tallies the five
booleans per arm.

**What this module is NOT.** It does not *produce* the trajectories. An `AttemptStep`
stream comes from a REAL agent run (`bbon.extract.steps_from_stream` over a headless
``claude -p`` transcript). The lvp.8 fixtures carry a ``user_request`` + ``available_tools``
but no Docker rig, so that real-run substrate — a headless-Claude `Agent` that runs a
`SequenceStep` under each arm's injected memory and emits a trajectory — is a SEPARATE
prerequisite (mem-lvp.22). By consuming already-extracted trajectories, this harness
stays pure and hermetically testable with no model, network, or container.

**§4.2 — raw, no composite.** Each of the five axes is tallied independently into a
true/decided count; the harness never folds them into a single scalar. A rate is
emitted only when at least one pair *decided* that axis (the judge or the mechanical
pre-filter returned a non-``None`` value) — an undecided axis stays ``None`` rather
than being imputed to ``0.0``, matching the None-propagation convention used
throughout membench's scorers.

ZFC: pure mechanism — pairing by (sequence, step) key, delegating each verdict to the
injected judge via `score_action_impact`, and counting. The semantic call is the
judge's; this only tallies it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from membench.bbon.comparative_judge import ComparativeJudge
from membench.bbon.models import AttemptStep
from membench.metrics.action_impact import ActionImpactInputs, score_action_impact
from membench.schemas.metrics import ActionImpactMetrics

# The no-memory control arm every treated arm is paired against.
CONTROL_ARM = "none"

# The five §12.6 axes in schema order — the canonical order for the raw vector.
AXIS_KEYS = (
    "memory_changed_tool_choice",
    "memory_changed_plan",
    "memory_changed_output",
    "memory_prevented_known_failure",
    "memory_improved_verification",
)


@dataclass(frozen=True)
class ArmStepTrajectory:
    """One arm's run of one sequence step: the tool-call trajectory plus the context
    `score_action_impact` needs. ``steps`` is the `bbon.extract`-produced stream;
    ``status`` is the terminal outcome (``completed``/``failed``/``unknown``) when known.
    ``known_failure`` is set only when this step targets a specific known failure (the
    `memory_prevented_known_failure` axis)."""

    arm: str
    sequence_id: str
    step_id: str
    steps: tuple[AttemptStep, ...] = ()
    status: str | None = None
    work_id: str | None = None
    known_failure: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        """The (sequence, step) identity a treated trajectory pairs to its control on."""
        return (self.sequence_id, self.step_id)


def pair_trajectories(control: ArmStepTrajectory, treated: ArmStepTrajectory) -> ActionImpactInputs:
    """Build the `ActionImpactInputs` for one paired step: ``on`` = the memory-enabled
    (treated) arm, ``off`` = the no-memory control. Raises if the two are not the same
    sequence step — pairing mismatched steps would silently compare unrelated work."""
    if control.key != treated.key:
        raise ValueError(
            f"cannot pair trajectories from different steps: control={control.key} "
            f"treated={treated.key}"
        )
    return ActionImpactInputs(
        on_steps=tuple(treated.steps),
        off_steps=tuple(control.steps),
        on_status=treated.status,
        off_status=control.status,
        work_id=treated.work_id,
        known_failure=treated.known_failure,
    )


@dataclass(frozen=True)
class AxisTally:
    """One axis's raw count over a run: ``true_count`` of the ``decided_count`` pairs
    whose verdict for this axis was not ``None``. ``rate`` is ``true/decided`` — or
    ``None`` when no pair decided the axis (never imputed to 0.0)."""

    axis: str
    true_count: int
    decided_count: int

    @property
    def rate(self) -> float | None:
        if self.decided_count == 0:
            return None
        return self.true_count / self.decided_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "true_count": self.true_count,
            "decided_count": self.decided_count,
            "rate": self.rate,
        }


@dataclass(frozen=True)
class ArmActionImpact:
    """A treated arm's §12.6 action-impact readout vs the ``none`` control: the raw
    5-axis tally vector (no composite) plus the per-pair metrics as the evidence
    trail."""

    arm: str
    n_pairs: int
    tallies: tuple[AxisTally, ...]
    per_pair: tuple[ActionImpactMetrics, ...]

    def axes(self) -> tuple[float | None, ...]:
        """The raw 5-axis rate vector in canonical (`AXIS_KEYS`) order. A `None` entry
        marks an axis no pair decided — read alongside the tallies' decided counts."""
        return tuple(t.rate for t in self.tallies)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "n_pairs": self.n_pairs,
            "axes": {t.axis: t.to_dict() for t in self.tallies},
        }


def aggregate_metrics(arm: str, metrics: Sequence[ActionImpactMetrics]) -> ArmActionImpact:
    """Tally a sequence of per-pair `ActionImpactMetrics` into one arm's raw 5-axis
    vector. For each axis, ``decided`` counts the pairs whose value is not ``None`` and
    ``true`` counts those that are ``True`` — so a ``None`` (undecided) axis lowers
    neither count, keeping the rate an honest fraction of decided pairs."""
    tallies = []
    for key in AXIS_KEYS:
        decided = 0
        true_count = 0
        for m in metrics:
            value = getattr(m, key)
            if value is None:
                continue
            decided += 1
            if value:
                true_count += 1
        tallies.append(AxisTally(axis=key, true_count=true_count, decided_count=decided))
    return ArmActionImpact(
        arm=arm,
        n_pairs=len(metrics),
        tallies=tuple(tallies),
        per_pair=tuple(metrics),
    )


def score_arm_run(
    control_arm: Sequence[ArmStepTrajectory],
    treated_arm: Sequence[ArmStepTrajectory],
    *,
    treated_name: str,
    judge: ComparativeJudge | None = None,
) -> ArmActionImpact:
    """Score one treated arm against the ``none`` control across all its steps.

    Each treated trajectory is paired to the control trajectory with the same
    (sequence, step) key, scored via `score_action_impact`, and the per-pair metrics
    are aggregated. A treated step with no matching control twin raises — a missing
    control would otherwise drop the pair silently and bias the rate. ``judge=None``
    runs the mechanical pre-filter only (semantic axes stay ``None``)."""
    control_by_key: dict[tuple[str, str], ArmStepTrajectory] = {}
    for traj in control_arm:
        if traj.key in control_by_key:
            raise ValueError(f"duplicate control trajectory for step {traj.key}")
        control_by_key[traj.key] = traj

    metrics: list[ActionImpactMetrics] = []
    for treated in treated_arm:
        control = control_by_key.get(treated.key)
        if control is None:
            raise ValueError(
                f"no '{CONTROL_ARM}' control trajectory for treated step {treated.key}"
            )
        inp = pair_trajectories(control, treated)
        metrics.append(score_action_impact(inp, judge=judge))
    return aggregate_metrics(treated_name, metrics)


def run_action_impact(
    arms: Mapping[str, Sequence[ArmStepTrajectory]],
    *,
    judge: ComparativeJudge | None = None,
) -> dict[str, ArmActionImpact]:
    """Score every treated arm in ``arms`` against the ``none`` control and return the
    per-arm raw 5-axis readouts keyed by arm name.

    ``arms`` maps arm name -> that arm's per-step trajectories; it MUST contain the
    ``none`` control. Treated arms are every other key (e.g. ``ours``, ``builtin``),
    each scored independently — there is no cross-arm composite (§4.2)."""
    if CONTROL_ARM not in arms:
        raise ValueError(f"arms must include the '{CONTROL_ARM}' control; got {sorted(arms)}")
    control = arms[CONTROL_ARM]
    return {
        name: score_arm_run(control, trajectories, treated_name=name, judge=judge)
        for name, trajectories in arms.items()
        if name != CONTROL_ARM
    }
