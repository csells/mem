"""Measure candidate-generation recall under the preregistered budgets (mem-lbuvd).

The gate here is a SUBSET assertion, and it lives in this package rather than in
`beads_ordering`. `beads_ordering.client.candidate_parity` is an arm-versus-arm
gate that raises when two arms return different candidate sets, and it runs at
`beads_ordering/runner.py:258` before the label check executes. An experiment that
varies candidate generation makes differing candidate sets the expected outcome.
Relaxing that shared symbol would weaken it for `beads_ordering.runner` and
`density_linkage_evidence`, which both call it and both need it strict.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from membench.beads_ordering.models import OrderingTask
from membench.lexical_recall.generators import CandidateGenerator
from membench.lexical_recall.models import (
    RECALL_AT_10,
    FrozenMissCorpus,
    Generator,
    MissKind,
    TaskClass,
    TaskRecall,
)

G1_RECOVERS = 0.50
G1_DOES_NOT_RECOVER = 0.20
G2_PRESERVES = 0.95
G2_REGRESSES = 0.80


class LexicalRecallError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskSpec:
    """One task flattened to what recall needs, so both classes share a code path."""

    task_id: str
    task_class: TaskClass
    miss_kind: MissKind | None
    query: str
    primary_relevant: str
    useful_ids: frozenset[str]
    labelled: frozenset[str]
    corpus_size: int


def miss_specs(corpus: FrozenMissCorpus) -> tuple[TaskSpec, ...]:
    size = len(corpus.memories)
    return tuple(
        TaskSpec(
            task_id=task.task_id,
            task_class=TaskClass.LEXICAL_MISS,
            miss_kind=task.miss_kind,
            query=task.query,
            primary_relevant=task.primary_relevant,
            useful_ids=frozenset({task.primary_relevant, *task.acceptable_entry_points}),
            labelled=frozenset(
                {task.primary_relevant, *task.acceptable_entry_points, *task.distractors}
            ),
            corpus_size=size,
        )
        for task in corpus.tasks
    )


def control_specs(tasks: Sequence[OrderingTask]) -> tuple[TaskSpec, ...]:
    return tuple(
        TaskSpec(
            task_id=task.task_id,
            task_class=TaskClass.LEXICAL_HIT_CONTROL,
            miss_kind=None,
            query=task.query,
            primary_relevant=task.primary_relevant,
            useful_ids=frozenset({task.primary_relevant, *task.acceptable_entry_points}),
            labelled=frozenset(
                {task.primary_relevant, *task.acceptable_entry_points, *task.distractors}
            ),
            corpus_size=task.corpus_size,
        )
        for task in tasks
    )


def validate_lexical_miss_truth(spec: TaskSpec, literal_ids: Sequence[str]) -> None:
    """The subset gate for the lexical-miss class.

    Equality is the wrong assertion here: the whole point of the class is that the
    literal matcher returns strictly less than the labelled set. What must hold is
    that it returns nothing OUTSIDE the labels, and that it does not return the
    primary.
    """

    if spec.task_class is not TaskClass.LEXICAL_MISS:
        raise LexicalRecallError(f"{spec.task_id} is not a lexical-miss task")
    returned = set(literal_ids)
    stray = returned - spec.labelled
    if stray:
        raise LexicalRecallError(
            f"{spec.task_id}: literal candidate set is not a subset of the labels "
            f"({len(stray)} unlabelled ids)"
        )
    if spec.primary_relevant in returned:
        raise LexicalRecallError(
            f"{spec.task_id}: the literal matcher returned the primary Memory, "
            "so this task is not a lexical miss at run time"
        )
    if not returned:
        raise LexicalRecallError(
            f"{spec.task_id}: the literal matcher returned nothing, so recall would "
            "be 0 for a degenerate reason rather than a missed candidate"
        )


def validate_control_truth(spec: TaskSpec, literal_ids: Sequence[str]) -> None:
    """The control class keeps the ordering experiment's equality property.

    It is re-measured rather than assumed: 'recall is 1.0 by construction' is the
    claim this whole bead exists to make explicit, so it gets evidence.
    """

    if set(literal_ids) != spec.labelled:
        raise LexicalRecallError(
            f"{spec.task_id}: literal candidate set does not equal the labelled set"
        )


def _rank_of(ranked: Sequence[str], wanted: frozenset[str]) -> int | None:
    for position, memory_id in enumerate(ranked, start=1):
        if memory_id in wanted:
            return position
    return None


def measure(
    spec: TaskSpec,
    generator: Generator,
    ranked: Sequence[str],
    matched_k: int,
) -> TaskRecall:
    primary_rank = _rank_of(ranked, frozenset({spec.primary_relevant}))
    useful_rank = _rank_of(ranked, spec.useful_ids)
    return TaskRecall(
        task_id=spec.task_id,
        task_class=spec.task_class,
        miss_kind=spec.miss_kind,
        generator=generator,
        corpus_size=spec.corpus_size,
        matched_k=matched_k,
        candidate_set_size=len(ranked),
        n_labelled_non_primary=len(spec.labelled - {spec.primary_relevant}),
        primary_rank=primary_rank,
        useful_rank=useful_rank,
        primary_at_matched_k=primary_rank is not None and primary_rank <= matched_k,
        primary_at_10=primary_rank is not None and primary_rank <= RECALL_AT_10,
        primary_unbounded=primary_rank is not None,
        useful_at_matched_k=useful_rank is not None and useful_rank <= matched_k,
    )


def run_class(
    specs: Sequence[TaskSpec],
    generators_for: Callable[[int], dict[Generator, CandidateGenerator]],
) -> tuple[TaskRecall, ...]:
    """Measure every generator on every task, with matched-k set by the literal arm.

    Generators are looked up by corpus size rather than passed in directly: the
    ordering corpus is nested (a 50-task sees the first 50 Memories, a 500-task all
    500), so each size needs its own index and its own seeded workspace.
    """

    rows: list[TaskRecall] = []
    for spec in specs:
        generators = generators_for(spec.corpus_size)
        if Generator.LITERAL not in generators:
            raise LexicalRecallError("the literal arm sets matched-k and cannot be omitted")
        literal_ranked = generators[Generator.LITERAL].rank(spec.query)
        if spec.task_class is TaskClass.LEXICAL_MISS:
            validate_lexical_miss_truth(spec, literal_ranked)
        else:
            validate_control_truth(spec, literal_ranked)
        matched_k = len(literal_ranked)
        for name, generator in generators.items():
            ranked = literal_ranked if name is Generator.LITERAL else generator.rank(spec.query)
            rows.append(measure(spec, name, ranked, matched_k))
    return tuple(rows)


def _mean(values: Sequence[bool]) -> float:
    if not values:
        raise LexicalRecallError("cannot average an empty set of tasks")
    return sum(1 for value in values if value) / len(values)


def recall_summary(rows: Sequence[TaskRecall]) -> dict[str, object]:
    """Per class, per generator, with the per-kind strata and their n."""

    summary: dict[str, object] = {}
    for task_class in TaskClass:
        per_generator: dict[str, object] = {}
        for generator in Generator:
            selected = [
                row for row in rows if row.task_class is task_class and row.generator is generator
            ]
            if not selected:
                continue
            distinct = {row.task_id for row in selected}
            if len(distinct) != len(selected):
                raise LexicalRecallError(
                    f"{task_class.value}/{generator.value}: {len(selected)} rows for "
                    f"{len(distinct)} tasks; the independent unit is the task, so a "
                    "repeated row would silently reweight every statistic here"
                )
            entry: dict[str, object] = {
                "n_tasks": len(distinct),
                "primary_recall_at_matched_k": _mean([r.primary_at_matched_k for r in selected]),
                "primary_recall_at_10": _mean([r.primary_at_10 for r in selected]),
                "primary_recall_unbounded": _mean([r.primary_unbounded for r in selected]),
                "useful_recall_at_matched_k": _mean([r.useful_at_matched_k for r in selected]),
                "median_candidate_set_size": statistics.median(
                    [r.candidate_set_size for r in selected]
                ),
                "median_matched_k": statistics.median([r.matched_k for r in selected]),
            }
            if task_class is TaskClass.LEXICAL_MISS:
                by_kind: dict[str, object] = {}
                for kind in MissKind:
                    stratum = [r for r in selected if r.miss_kind is kind]
                    if not stratum:
                        continue
                    by_kind[kind.value] = {
                        "n_tasks": len(stratum),
                        "primary_recall_at_matched_k": _mean(
                            [r.primary_at_matched_k for r in stratum]
                        ),
                        "primary_recall_at_10": _mean([r.primary_at_10 for r in stratum]),
                    }
                entry["by_miss_kind"] = by_kind
            per_generator[generator.value] = entry
        if per_generator:
            summary[task_class.value] = per_generator
    return summary


def _percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank: the smallest value at or above the given fraction of the data.

    `round(fraction * (n - 1))` is half-to-even, so at n=6 it rounds 4.5 down and
    returns the 5th of 6 as the "p90". Correct at the n=36 this file reports today,
    wrong at the n=9 of a per-kind stratum, which the preregistration also treats
    as a reported unit.
    """

    if not values:
        raise LexicalRecallError("cannot take a percentile of nothing")
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def g1_verdict(value: float) -> str:
    if value >= G1_RECOVERS:
        return "recovers"
    if value <= G1_DOES_NOT_RECOVER:
        return "does_not_recover"
    return "inconclusive"


def g2_verdict(value: float) -> str:
    if value >= G2_PRESERVES:
        return "preserves_literal_recall"
    if value <= G2_REGRESSES:
        return "regresses"
    return "inconclusive"


def _budget_diagnostic(rows: Sequence[TaskRecall]) -> dict[str, object]:
    """How much room G1's budget actually leaves for the primary.

    A recall-at-k statistic is only informative when k can hold the primary. On the
    lexical-miss class each task ships `matched_k` distractors carrying the query
    verbatim plus an entry Memory, so at least `matched_k + 1` labelled documents
    can outrank the primary inside a budget of `matched_k`. Without this block a
    consumer reads `does_not_recover` as a fact about the ranker when it is a fact
    about the fixture, which is the same by-construction error the sibling ordering
    experiment made and this bead exists to avoid repeating.
    """

    saturable = [r for r in rows if r.n_labelled_non_primary >= r.matched_k]
    headroom = sorted(r.primary_rank - r.matched_k for r in rows if r.primary_rank is not None)
    return {
        "n_tasks": len(rows),
        "n_tasks_budget_saturable_by_non_primary_labels": len(saturable),
        "median_matched_k": statistics.median([r.matched_k for r in rows]),
        "median_labelled_non_primary": statistics.median([r.n_labelled_non_primary for r in rows]),
        "n_tasks_primary_retrieved_at_any_depth": len(headroom),
        "primary_rank_minus_matched_k": (
            {"min": headroom[0], "median": statistics.median(headroom), "max": headroom[-1]}
            if headroom
            else None
        ),
        # Structural, not a verdict: it says the budget CAN be filled by non-primary
        # labels on every task, which is why G1 is bounded below the ceiling. A
        # ranker that puts the primary above all of them still scores, as the dense
        # arm does on 2 of 36, so this is not a claim that G1 is unfalsifiable.
        "budget_saturable_on_every_task": len(saturable) == len(rows),
    }


def _cost_ratios(
    rows: Sequence[TaskRecall], literal_rows: Sequence[TaskRecall]
) -> dict[str, object]:
    """Candidate-set size against the literal arm on the SAME task.

    The join key is (task_id, corpus_size), not task_id alone: the control class
    runs tasks at 50, 100 and 500 Memories, and collapsing those onto one key would
    silently compare a task against another size's denominator.
    """

    by_task = {(r.task_id, r.corpus_size): r.candidate_set_size for r in literal_rows}
    if len(by_task) != len(literal_rows):
        raise LexicalRecallError(
            "literal rows collide on (task_id, corpus_size); the cost ratio would "
            "compare a task against another row's denominator"
        )
    ratios: list[float] = []
    for row in rows:
        denominator = by_task.get((row.task_id, row.corpus_size))
        if denominator is None:
            raise LexicalRecallError(
                f"{row.task_id} at corpus_size={row.corpus_size} has no literal row, "
                "so its candidate cost has no denominator"
            )
        if denominator == 0:
            raise LexicalRecallError(
                f"{row.task_id} at corpus_size={row.corpus_size}: the literal arm "
                "returned nothing, so the cost ratio is undefined"
            )
        ratios.append(row.candidate_set_size / denominator)
    return {
        "n_tasks": len(ratios),
        "median_ratio_vs_literal": statistics.median(ratios),
        "p90_ratio_vs_literal": _percentile(ratios, 0.9),
        "threshold": "none, descriptive",
    }


def gate_verdicts(rows: Sequence[TaskRecall]) -> dict[str, object]:
    """G1, G2 and G3 exactly as the preregistration fixes them."""

    verdicts: dict[str, object] = {}
    meets_both: list[str] = []
    for generator in (Generator.FTS, Generator.EMBEDDING):
        per_class = {
            task_class: [r for r in rows if r.task_class is task_class and r.generator is generator]
            for task_class in TaskClass
        }
        literal_by_class = {
            task_class: [
                r for r in rows if r.task_class is task_class and r.generator is Generator.LITERAL
            ]
            for task_class in TaskClass
        }
        miss = per_class[TaskClass.LEXICAL_MISS]
        control = per_class[TaskClass.LEXICAL_HIT_CONTROL]
        g1_value = _mean([r.primary_at_matched_k for r in miss])
        g2_value = _mean([r.primary_at_matched_k for r in control])
        g1 = g1_verdict(g1_value)
        g2 = g2_verdict(g2_value)
        if g1 == "recovers" and g2 == "preserves_literal_recall":
            meets_both.append(generator.value)
        verdicts[generator.value] = {
            "G1_recovery": {
                "statistic": g1_value,
                "verdict": g1,
                "class": TaskClass.LEXICAL_MISS.value,
                "budget_diagnostic": _budget_diagnostic(miss),
            },
            "G2_no_regression": {
                "statistic": g2_value,
                "verdict": g2,
                "class": TaskClass.LEXICAL_HIT_CONTROL.value,
            },
            # Reported per class. The preregistered endpoint is "per generator, per
            # class", and the two differ by two orders of magnitude for a dense arm
            # that returns the whole corpus: one number labelled only "G3" reads as
            # the miss class's cost to a reader of a miss-class experiment.
            "G3_candidate_cost": {
                task_class.value: _cost_ratios(per_class[task_class], literal_by_class[task_class])
                for task_class in TaskClass
                if per_class[task_class]
            },
        }
    verdicts["combined_recommendation"] = {
        "candidate_generation_earns_its_own_arm": bool(meets_both),
        "generators_meeting_both_gates": meets_both,
    }
    return verdicts
