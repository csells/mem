"""§4.4 — score the §12.6 action-impact axes over `run_grid_3arm`'s PERSISTED runs,
alongside its existing pass/fail oracle (mem-lvp.25).

`scripts/run_grid_3arm.py` already executed the real none/ours/builtin Harbor agents and
left, per (bundle, condition): a stream transcript in a job dir (`*/agent/claude-code.txt`,
read by `probe_gate.load_stream`) and a scored result with `repro_passed` (the pass/fail
oracle). This module is a DETERMINISTIC POST-HOC scorer over those persisted artifacts —
no agent re-run: it loads each arm's stream → `bbon.extract.steps_from_stream` (now with
tool OUTPUT) → an `ArmStepTrajectory` per bundle → pairs none↔ours / none↔builtin →
`metrics.action_impact_run.run_action_impact` with the local judge, and reports the raw
5-axis vector beside the per-arm pass-rate.

**Arm ↔ grid-condition mapping.** The action-impact arms are scored against the no-memory
control; the grid's clean-room conditions map as: ``none`` (control) ← ``none-clean``,
``ours`` ← ``ours``, ``builtin`` ← ``none`` (native project memory ON — exactly the gate
probe's cached runs, per `run_grid_3arm`). One trajectory per bundle (a bundle is one
task), keyed by ``work_id`` so the pairing aligns the same bundle across arms.

**Coverage is honest, never imputed.** A bundle is paired for a treated arm only when BOTH
that arm's and the control's stream exist (`run_grid_3arm`'s economy reuses the control for
retrieval-empty ``ours``, so coverage is naturally partial); the rest are reported as
skipped, not silently dropped. With the cached corpus this yields a small N — that is the
executable-corpus validity wall flagged on mem-lvp.26, not a wiring defect.

ZFC: pure mechanism — file IO, stream parsing, delegation to the judge inside
`score_action_impact`, and pass-rate arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from membench.bbon.comparative_judge import ComparativeJudge
from membench.bbon.extract import steps_from_stream
from membench.bbon.models import deterministic_id
from membench.harbor.bundle_grid import GridConditionResult
from membench.harbor.probe_gate import load_stream
from membench.metrics.action_impact_run import (
    CONTROL_ARM,
    ArmActionImpact,
    ArmStepTrajectory,
    run_action_impact,
)

# The three action-impact arms → the grid job/result CONDITION their stream comes from.
# ``builtin`` rides the ``none`` condition (native memory ON); ``none`` is the clean-room
# control (native memory stripped).
ARM_TO_GRID_CONDITION: dict[str, str] = {
    CONTROL_ARM: "none-clean",
    "ours": "ours",
    "builtin": "none",
}

# A pseudo-sequence id so every bundle's pair shares one space; the bundle work_id is the
# step key the harness pairs arms on.
_GRID_SEQUENCE = "grid-3arm"


@dataclass(frozen=True)
class _ArmLoad:
    """One arm's loaded-or-skipped trajectory for a bundle, plus its pass/fail."""

    trajectory: ArmStepTrajectory | None
    repro_passed: bool | None
    skipped_reason: str | None = None


def _load_repro_passed(grid_dir: Path, work_id: str, condition: str) -> bool | None:
    """The pass/fail oracle for one (bundle, condition) from its scored grid result, or
    ``None`` when the result is absent/unparseable or the direct leg fell back to diff
    similarity (``repro_passed`` is itself ``None`` there). Mirrors `run_grid_3arm`'s
    ``load_grid_result`` without importing the script."""
    path = grid_dir / f"{work_id}.{condition}.json"
    if not path.is_file():
        return None
    try:
        result = GridConditionResult.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return result.repro_passed


def _load_arm(jobs_dir: Path, grid_dir: Path, work_id: str, arm: str) -> _ArmLoad:
    """Load one (bundle, arm) trajectory from its persisted job dir + grid result. A
    missing job dir / stream / result yields a skip with a reason — never a fabricated
    empty trajectory (which would read as 'the agent did nothing')."""
    condition = ARM_TO_GRID_CONDITION[arm]
    job_dir = jobs_dir / f"{work_id}.{condition}"
    if not job_dir.is_dir():
        return _ArmLoad(None, None, f"no job dir {job_dir.name}")
    try:
        stream = load_stream(job_dir)
    except RuntimeError as exc:
        return _ArmLoad(None, None, f"no stream: {exc}")
    repro_passed = _load_repro_passed(grid_dir, work_id, condition)
    attempt_id = deterministic_id({"arm": arm, "work_id": work_id, "condition": condition})
    steps = steps_from_stream(stream, attempt_id)
    status = "completed" if repro_passed else "failed" if repro_passed is False else None
    traj = ArmStepTrajectory(
        arm=arm,
        sequence_id=_GRID_SEQUENCE,
        step_id=work_id,
        steps=tuple(steps),
        status=status,
        work_id=work_id,
    )
    return _ArmLoad(traj, repro_passed, None)


@dataclass(frozen=True)
class GridActionImpact:
    """The §4.4 readout over the persisted grid: per treated arm, the raw 5-axis
    action-impact vector PLUS the pass-rate of both that arm and the control over the
    bundles they were paired on (outcome-lift headline = treated minus control pass-rate).
    ``skipped`` records bundles dropped for missing artifacts."""

    action_impact: dict[str, ArmActionImpact]
    control_pass_rate: float | None
    treated_pass_rate: dict[str, float | None]
    paired_work_ids: dict[str, list[str]]
    skipped: dict[str, list[str]] = field(default_factory=dict)

    def outcome_lift(self, arm: str) -> float | None:
        """Pass-rate delta (treated minus control) over the bundles this arm paired on,
        or ``None`` when either rate is undefined (no paired bundle with a known oracle)."""
        treated = self.treated_pass_rate.get(arm)
        if treated is None or self.control_pass_rate is None:
            return None
        return treated - self.control_pass_rate


def _pass_rate(values: list[bool | None]) -> float | None:
    known = [v for v in values if v is not None]
    return (sum(1 for v in known if v) / len(known)) if known else None


def score_grid_action_impact(
    grid_dir: Path,
    jobs_dir: Path,
    work_ids: list[str],
    *,
    treated_arms: tuple[str, ...] = ("ours", "builtin"),
    judge: ComparativeJudge | None = None,
) -> GridActionImpact:
    """Score action-impact + pass-rate over the persisted grid for ``work_ids``.

    For each treated arm, a bundle is paired only when BOTH the control and the treated
    stream loaded; those trajectories go through `run_action_impact` (raw 5-axis) and the
    matching ``repro_passed`` through the pass-rate. Bundles missing an artifact are
    recorded in ``skipped`` per arm, never silently excluded."""
    controls: dict[str, _ArmLoad] = {
        w: _load_arm(jobs_dir, grid_dir, w, CONTROL_ARM) for w in work_ids
    }

    action_impact: dict[str, ArmActionImpact] = {}
    treated_pass_rate: dict[str, float | None] = {}
    paired: dict[str, list[str]] = {}
    skipped: dict[str, list[str]] = {}
    # The control pass-rate is over every bundle whose control loaded (shared baseline).
    control_pass_rate = _pass_rate(
        [c.repro_passed for c in controls.values() if c.trajectory is not None]
    )

    for arm in treated_arms:
        control_traj: list[ArmStepTrajectory] = []
        treated_traj: list[ArmStepTrajectory] = []
        treated_oracle: list[bool | None] = []
        paired[arm] = []
        skipped[arm] = []
        for work_id in work_ids:
            ctrl = controls[work_id]
            treat = _load_arm(jobs_dir, grid_dir, work_id, arm)
            if ctrl.trajectory is None or treat.trajectory is None:
                reason = ctrl.skipped_reason or treat.skipped_reason or "unpaired"
                skipped[arm].append(f"{work_id}: {reason}")
                continue
            control_traj.append(ctrl.trajectory)
            treated_traj.append(treat.trajectory)
            treated_oracle.append(treat.repro_passed)
            paired[arm].append(work_id)
        treated_pass_rate[arm] = _pass_rate(treated_oracle)
        if treated_traj:
            scored = run_action_impact({CONTROL_ARM: control_traj, arm: treated_traj}, judge=judge)
            action_impact[arm] = scored[arm]

    return GridActionImpact(
        action_impact=action_impact,
        control_pass_rate=control_pass_rate,
        treated_pass_rate=treated_pass_rate,
        paired_work_ids=paired,
        skipped=skipped,
    )
