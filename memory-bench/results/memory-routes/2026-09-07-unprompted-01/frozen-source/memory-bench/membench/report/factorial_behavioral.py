"""Gate 0a behavioral driver — run the factorial family and read REAL ScriptedAgent
scores into ``factorial_diagnosis.Observation`` lists (the realization half).

PRD ``prd_grounded_factorial_memory_diagnosis_generator.md`` (Gate 0a — INSTRUMENT
validity). ``factorial_diagnosis`` recovers main effects FROM responses; this module
PRODUCES those responses by actually running each generated cell through the live
sequence runner (``run_sequence``, ``ScriptedAgent``, the chosen arm under
MEMORY_ENABLED) and reading the mechanical scores the runner/scorer already emit:

* interference   → ``distractor_retrieval_rate`` (Confusion) at the goal retrieve
* supersession   → ``stale_memory_retrieval_rate`` (Staleness) at the goal retrieve
* consolidation  → a destroy-disposition indicator (1.0 if the goal-required branch-0
  record was swept to ``destroy`` by the retention arm, else 0.0)

Each observable is a property of the CELL under the arm, scored from the run — never a
planted number. ``replicate`` is the seed, so the paired bootstrap in ``diagnose``
resamples matched cells within a seed.

Sign convention: higher confusion/staleness/destruction is WORSE, but
``factorial_diagnosis`` reads "higher response = better". So this driver NEGATES each
observable before building the ``Observation`` (``response = -rate``): a factor that
RAISES confusion then reads as a negative effect, i.e. ``direction == "hurts"`` — the
sign the diagnosis is meant to recover. The raw rate is preserved on the returned
``CellObservables`` for the realization assertions.

ZFC: pure plumbing. Run the cell, read the arm/scorer's mechanical outputs, build
``Observation``s. No semantic judgment, no thresholds. Fail loud if an expected
observable is structurally absent (the goal step never retrieved, or the arm cannot
report a disposition) — a missing observable is a wiring bug, not a 0.
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from dataclasses import dataclass

from membench.generators.factorial_dag import (
    FactorCell,
    all_factor_cells,
    generate_factorial_family,
)
from membench.generators.opaque_ids import opaque_memory_id
from membench.memory_systems.retention_scheduled_system import RetentionScheduledMemory
from membench.report.factorial_diagnosis import Observation
from membench.runner.conditions import StepTrial, run_sequence
from membench.schemas.conditions import Condition
from membench.schemas.config import AgentConfig, ExperimentConfig, MemoryConfig
from membench.schemas.sequence import BenchmarkSequence

# The three observables the driver reads, one per non-depth factor. Each name matches a
# ``NON_DEPTH_FACTORS`` entry so the diagnosis can be asked for the matching main effect.
INTERFERENCE = "interference"
SUPERSESSION = "supersession"
CONSOLIDATION = "consolidation"


@dataclass(frozen=True)
class CellObservables:
    """The three RAW (worse-is-higher) observables read from one cell's live run, plus
    the cell's factor levels and replicate seed. ``confusion``/``staleness`` are the mean
    rate over the cell's read-attempted MEMORY_ENABLED trials (the goal retrieve);
    ``destruction`` is 1.0 iff the goal-required branch-0 record was swept to ``destroy``.

    Kept distinct from ``Observation`` so the realization assertions can read raw rates
    while ``observations_for`` emits the sign-flipped diagnosis responses."""

    cell: FactorCell
    replicate: str
    confusion: float
    staleness: float
    destruction: float

    def raw(self, observable: str) -> float:
        if observable == INTERFERENCE:
            return self.confusion
        if observable == SUPERSESSION:
            return self.staleness
        if observable == CONSOLIDATION:
            return self.destruction
        raise KeyError(f"unknown observable {observable!r}")


def _experiment(arm: str) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"factorial-behavioral-{arm}",
        agent=AgentConfig(agent_config_id="scripted-ref", runtime="scripted"),
        memory=MemoryConfig(memory_config_id=arm, system=arm),
        dataset_id="synthetic-factorial",
        conditions=[Condition.MEMORY_ENABLED],
    )


def _mean_rates(trials: Sequence[StepTrial]) -> tuple[float, float]:
    """Mean distractor / stale retrieval rate over the read-attempted MEMORY_ENABLED
    trials (the steps that actually retrieved — only the goal step does here). An
    establishing step never retrieves, so it carries no Confusion/Staleness signal and
    is excluded rather than diluted in as 0. Raises if NO step retrieved: a factorial
    cell whose goal never reads is a broken sequence, not a 0-rate cell."""
    confusion: list[float] = []
    staleness: list[float] = []
    for t in trials:
        if t.condition is Condition.MEMORY_ENABLED and t.metrics.retrieval.read_attempted:
            confusion.append(t.metrics.retrieval.distractor_retrieval_rate)
            staleness.append(t.metrics.retrieval.stale_memory_retrieval_rate)
    if not confusion:
        raise ValueError(
            "no read-attempted MEMORY_ENABLED trial in cell run — the goal step never "
            "retrieved, so Confusion/Staleness are unobservable (broken sequence)"
        )
    return sum(confusion) / len(confusion), sum(staleness) / len(staleness)


def _branch_zero_id(seq: BenchmarkSequence) -> str:
    """The goal-required branch-0 record id — ``opaque_memory_id(sequence_id, "fact0")``
    by construction (``generate_cell`` derives every agent-visible id through the
    opaque hash; the label→id mapping is recomputed on demand, never stored). The
    consolidation HURTS condition schedules exactly this record for destruction."""
    return opaque_memory_id(seq.sequence_id, "fact0")


def _destruction_indicator(arm: RetentionScheduledMemory, seq: BenchmarkSequence) -> float:
    """1.0 iff the retention sweep applied the ``destroy`` disposition to the
    goal-required branch-0 record, else 0.0. Reads ``applied_disposition`` (populated by
    ``consolidate()``), mirroring ``report/retention_schedule``. Raises if the sweep
    never ran for branch-0 (``applied_disposition`` is None) — that means the
    consolidation wiring did not fire, a bug we must not paper over with a 0."""
    branch0 = _branch_zero_id(seq)
    applied = arm.applied_disposition(branch0)
    if applied is None:
        raise ValueError(
            f"retention sweep never set a disposition for branch-0 record {branch0!r}; "
            "the consolidation wiring did not fire (cannot read a destruction indicator)"
        )
    return 1.0 if applied == "destroy" else 0.0


def run_cell_observables(
    seq: BenchmarkSequence,
    cell: FactorCell,
    *,
    seed: int,
    arm: str,
) -> CellObservables:
    """Run one factorial cell through the live runner under ``arm`` (MEMORY_ENABLED only)
    and read its three raw observables. Confusion/Staleness come from the goal retrieve;
    destruction from the retention sweep when ``arm == 'retention_scheduled'`` (the only
    arm that reports a disposition), else 0.0 (an id-exact arm never schedules a destroy,
    so its consolidation observable is honestly 0 — the factor is inert for it)."""
    if arm == "retention_scheduled":
        # A fresh classifying arm per cell so ``applied_disposition`` reflects only this
        # cell's sweep; injected via the runner's ``memory_system`` seam.
        retention = RetentionScheduledMemory()
        run = run_sequence(
            seq,
            _experiment(arm),
            memory_system=retention,
            conditions=[Condition.MEMORY_ENABLED],
        )
        confusion, staleness = _mean_rates(run.trials)
        destruction = _destruction_indicator(retention, seq)
        return CellObservables(
            cell=cell,
            replicate=str(seed),
            confusion=confusion,
            staleness=staleness,
            destruction=destruction,
        )

    # Non-classifying arms (filesystem/lexical/...) read Confusion/Staleness only; the
    # consolidation observable is 0 (no schedule, the factor cannot realize for them).
    with tempfile.TemporaryDirectory() as d:
        run = run_sequence(
            seq,
            _experiment(arm),
            conditions=[Condition.MEMORY_ENABLED],
            fs_base_dir=d,
        )
    confusion, staleness = _mean_rates(run.trials)
    return CellObservables(
        cell=cell,
        replicate=str(seed),
        confusion=confusion,
        staleness=staleness,
        destruction=0.0,
    )


def run_family_observables(
    seeds: Sequence[int],
    *,
    width: int,
    arm: str,
) -> list[CellObservables]:
    """Run the full 2^3 factorial family for every seed (one replicate per seed) under
    ``arm`` and return the per-cell raw observables. Each ``(seed, cell)`` is one
    replicate-cell; the order is family order within each seed."""
    if not seeds:
        raise ValueError("run_family_observables needs at least one seed")
    cells = all_factor_cells()
    out: list[CellObservables] = []
    for seed in seeds:
        family = generate_factorial_family(seed=seed, width=width)
        if len(family) != len(cells):
            raise ValueError(
                f"factorial family size {len(family)} != cell count {len(cells)} "
                f"(seed {seed}); the generator and the cell enumeration disagree"
            )
        for seq, cell in zip(family, cells, strict=True):
            out.append(run_cell_observables(seq, cell, seed=seed, arm=arm))
    return out


def observations_for(
    cells: Sequence[CellObservables],
    observable: str,
) -> list[Observation]:
    """Project the per-cell raw observable into ``factorial_diagnosis.Observation``s,
    NEGATING the rate so "higher response = better" holds (a factor that raises the
    worse-is-higher rate then reads as ``direction == 'hurts'``). One Observation per
    cell, keyed by the cell's factor levels and replicate seed."""
    if observable not in (INTERFERENCE, SUPERSESSION, CONSOLIDATION):
        raise KeyError(f"unknown observable {observable!r}")
    return [
        Observation(
            levels=co.cell.levels(),
            replicate=co.replicate,
            response=-co.raw(observable),
        )
        for co in cells
    ]
