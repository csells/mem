"""Gate 0a apparatus — grounded factorial isolation-DAG generator (Tier-0, pure Python).

PRD: ``prd_grounded_factorial_memory_diagnosis_generator.md`` (Gate 0a — INSTRUMENT
validity, the anchor-free half of the construct-validity split). Emits width-K
isolation-DAG ``BenchmarkSequence``s with a full 2^3 factorial over the three
non-depth factors — interference, supersession/staleness, consolidation — laid onto a
frozen-K skeleton so the topology (``antichain_width``) is INVARIANT across every
non-depth toggle. Retrieval-depth is the skeleton axis K, varied across families.

Each factor is realised ONLY in the ``SequenceStep`` factor fields the runner/scorer
already consume — ``distractor_memories`` (Confusion), ``superseded_memory_ids``
(Staleness), ``record_class``/``disposition`` (retention/consolidation oracle) — and
NEVER as a new read/write edge, so single-factor isolation holds by construction (the
antichain width is unchanged). Memory-dependence is inherited from the
``synthetic_task`` spine: the goal step requires every current fact id, so the oracle
arm passes and the no-memory arm cannot (``pilot_filter`` admits it).

Every factor carries a condition where memory is expected to HURT (the PRD
anti-tautology rule): interference plants plausible-but-wrong distractors, supersession
leaves a stale v1 in scope, consolidation schedules a goal-required record for
destruction. A full 2^3 family is balanced by construction (each ``(factor, level)``
appears in exactly four cells).

Deterministic: same ``(seed, width)`` ⇒ byte-identical family. Real per-branch cost is
resampled from a supplied recorded-corpus pool (grounding); with no pool the cost
fields are omitted so CI stays model- and IO-free.

Label opacity + reward-bearing staleness (mem-z3gi): every agent-visible memory id is
an opaque content-keyed hash (``opaque_memory_id``) and truth / stale / distractor
contents share ONE template ("fact {k} is {value}") with authored, globally-distinct
values — no id suffix or verb tense separates the classes. Under supersession the
goal's check carries the stale values as ``forbidden_values``, so an arm that
surfaces (and thus states) a stale value FAILS the goal rather than only ticking the
diagnostic rate.

Modelling simplifications (Gate 0a scope; revisit for Gate 0b realism):
  - Supersession writes the stale v1 alongside the current v2 in the SAME establish
    step (distinct ids), so the staleness signal is scored at the goal's retrieve where
    both are in scope. This keeps the topology width-invariant — a separate earlier
    v1-only step would add an antichain node and break isolation — at the cost of never
    exercising a "v1-only retrieval window" before v2 exists. Depth-≥3 supersession
    chains live in the enterprise materialiser, whose multi-step topology owns them.
  - The consolidation HURTS condition schedules exactly ONE goal-required record (branch
    0) for destruction, so the per-sequence hurt signal is 1/K — a fixed floor, not
    scaled with width. Account for this in any power analysis of the consolidation main
    effect.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations, product
from typing import Any

from membench.generators.opaque_ids import opaque_memory_id
from membench.memory_systems.retention_scheduled_system import RETENTION_POLICY
from membench.schemas.sequence import (
    BenchmarkSequence,
    MemoryProbe,
    OutcomeCheck,
    SequenceStep,
)

GENERATOR_VERSION = "factorial-dag.v2"

# The three binary non-depth factors layered onto a frozen-K skeleton (2^3 cells).
NON_DEPTH_FACTORS: tuple[str, ...] = ("interference", "supersession", "consolidation")

# Interference magnitude when ON (OFF = 0): plausible-but-wrong competitors a top-k arm
# surfaces (Confusion); an id-exact arm never requests them, so its rate stays 0.
DISTRACTOR_ON_COUNT = 4

# Consolidation HURTS condition: branch 0's goal-required record is scheduled under a
# destroy-eligible class, so a schedule-obeying arm wrongfully destroys a fact the goal
# needs. The remaining records are kept live. Both classes are drawn from
# ``RETENTION_POLICY`` (the SSOT) so the generator oracle and the arm cannot drift.
_DESTROY_CLASS = "expired"  # RETENTION_POLICY["expired"] == "destroy"
_KEEP_CLASS = "permanent"  # RETENTION_POLICY["permanent"] == "permanent"

_MISSING_CLASSES = {_DESTROY_CLASS, _KEEP_CLASS} - set(RETENTION_POLICY)
if _MISSING_CLASSES:
    raise ValueError(
        f"factorial_dag consolidation classes must exist in RETENTION_POLICY; "
        f"missing {_MISSING_CLASSES}"
    )


@dataclass(frozen=True)
class FactorCell:
    """One cell of the 2^3 non-depth factorial: each factor present (ON) or absent."""

    interference: bool
    supersession: bool
    consolidation: bool

    def levels(self) -> dict[str, bool]:
        return {
            "interference": self.interference,
            "supersession": self.supersession,
            "consolidation": self.consolidation,
        }

    @property
    def cell_id(self) -> str:
        lv = self.levels()
        return "".join(f"{name[0]}{int(lv[name])}" for name in NON_DEPTH_FACTORS)


def all_factor_cells() -> list[FactorCell]:
    """The full 2^3 non-depth factorial, in a fixed deterministic order."""
    return [
        FactorCell(interference=i, supersession=s, consolidation=c)
        for i, s, c in product((False, True), repeat=3)
    ]


def antichain_width(steps: Sequence[SequenceStep]) -> int:
    """Largest set of mutually-unreachable steps in the memory read/write DAG.

    An edge ``j -> i`` exists when step ``i`` reads a memory ``j`` wrote. The result is
    the isolation-DAG's branch count — invariant across every non-depth factor toggle
    by construction (the factors touch only scalar/dict fields, never read/write edges).
    """
    writers: dict[str, list[int]] = {}
    succ: dict[int, set[int]] = {i: set() for i in range(len(steps))}
    for i, st in enumerate(steps):
        for mid in st.expected_memory_reads:
            for j in writers.get(mid, []):
                succ[j].add(i)
        for mid in st.expected_memory_writes:
            writers.setdefault(mid, []).append(i)

    desc: dict[int, set[int]] = {}

    def walk(n: int) -> set[int]:
        if n in desc:
            return desc[n]
        out: set[int] = set()
        for m in succ[n]:
            out |= {m} | walk(m)
        desc[n] = out
        return out

    for n in succ:
        walk(n)

    comparable: set[tuple[int, int]] = set()
    for a in succ:
        for b in desc[a]:
            comparable.add((a, b))
            comparable.add((b, a))

    nodes = list(succ)
    for size in range(len(nodes), 1, -1):
        for combo in combinations(nodes, size):
            if all((a, b) not in comparable for a, b in combinations(combo, 2)):
                return size
    return 1 if nodes else 0


def _cell_ordinal(cell: FactorCell) -> int:
    lv = cell.levels()
    return sum(int(lv[name]) << i for i, name in enumerate(NON_DEPTH_FACTORS))


def _cost_for(rng: random.Random, cost_pool: Sequence[tuple[int, int]] | None) -> dict[str, Any]:
    """Resample one real ``(turns, tool_calls)`` from the corpus pool (grounding).

    ``None`` ⇒ no grounding (empty state, so CI stays model- and IO-free). An EMPTY
    pool is a caller mistake (the corpus failed to load), not "no grounding" — raise
    rather than silently dropping it."""
    if cost_pool is None:
        return {}
    if not cost_pool:
        raise ValueError("cost_pool must be non-empty or None")
    turns, tools = rng.choice(cost_pool)
    return {"real_cost_turns": turns, "real_cost_tool_calls": tools}


def _fact_content(branch: int, value: str) -> str:
    """THE memory content template — shared verbatim by truth, stale and distractor
    entries so nothing but the value separates the classes (mem-z3gi). The shared
    "fact" token is also what keeps every class inside a token-overlap arm's top-k
    against the goal query ("...the current value of every fact")."""
    return f"fact {branch} is {value}"


def _fact_values(seed: int, width: int) -> tuple[list[str], list[str]]:
    """Authored (current, stale) values per branch: zero-padded 3-digit tokens.

    Drawn from a FAMILY rng keyed on (seed, width) only — never the cell — so all 8
    cells of a family share the same truth surface and a factor toggle moves nothing
    but its own observable (single-factor isolation). Globally distinct within the
    family (one ``sample``), so a stale ``forbidden_values`` entry can never
    word-match a current content and the staleness grade stays mechanical."""
    family_rng = random.Random((seed << 24) ^ (width << 4) ^ 0x5EED)
    values = [f"{v:03d}" for v in family_rng.sample(range(1000), 2 * width)]
    return values[:width], values[width:]


def _distractors(
    prefix: str,
    rng: random.Random,
    *,
    width: int,
    taken_values: frozenset[str],
    interference: bool,
) -> dict[str, str]:
    """The Confusion competitors planted at the goal (OFF ⇒ none). Each names a real
    branch through the SAME content template as the truth — so a token-overlap arm
    ranks it beside the truth (the actual Confusion stressor) — but with a wrong
    value distinct from every current AND stale value, so surfacing a distractor is
    never mis-scored as staleness. Ids are opaque; an id-exact arm never requests
    them, so its ``distractor_retrieval_rate`` stays 0 regardless."""
    if not interference:
        return {}
    candidates = [v for v in (f"{n:03d}" for n in range(1000)) if v not in taken_values]
    return {
        opaque_memory_id(prefix, f"distractor{j}"): _fact_content(j % width, rng.choice(candidates))
        for j in range(DISTRACTOR_ON_COUNT)
    }


def _consolidation_labels(consolidation: bool, *, branch: int) -> tuple[str | None, str | None]:
    """Retention oracle labels for an establishing record. OFF ⇒ unlabelled. ON ⇒
    branch 0's (goal-required) record is scheduled for destruction (the HURTS condition:
    a schedule-obeying arm wrongfully destroys a needed fact); the rest are kept live.
    Class/disposition come from ``RETENTION_POLICY`` (the SSOT)."""
    if not consolidation:
        return None, None
    record_class = _DESTROY_CLASS if branch == 0 else _KEEP_CLASS
    return record_class, RETENTION_POLICY[record_class]


def generate_cell(
    *,
    seed: int,
    width: int,
    cell: FactorCell,
    cost_pool: Sequence[tuple[int, int]] | None = None,
) -> BenchmarkSequence:
    """One factorial cell: a width-K isolation DAG with the cell's factors layered on.

    K independent establishing steps each plant one current fact (and, under
    supersession, a stale v1 alongside it under a distinct id that is never read, so it
    adds no edge); a goal step requires every current fact. Interference adds distractor
    competitors at the goal; consolidation labels records with retention classes. The
    topology is identical for every cell at a given ``width``."""
    if width < 1:
        raise ValueError(f"width must be >= 1, got {width}")

    rng = random.Random((seed << 20) ^ (width << 8) ^ _cell_ordinal(cell))
    prefix = f"factorial-seed{seed}-w{width}-{cell.cell_id}"
    current_values, stale_values = _fact_values(seed, width)

    steps: list[SequenceStep] = []
    current_ids: list[str] = []
    superseded_ids: list[str] = []

    for k in range(width):
        current_id = opaque_memory_id(prefix, f"fact{k}")
        current_ids.append(current_id)
        writes: dict[str, str] = {current_id: _fact_content(k, current_values[k])}

        if cell.supersession:
            stale_id = opaque_memory_id(prefix, f"fact{k}-v1")
            # v1 is written here — an EARLIER step than the goal that marks it stale —
            # but never read, so it adds no read/write edge: the width is unchanged.
            writes[stale_id] = _fact_content(k, stale_values[k])
            superseded_ids.append(stale_id)

        record_class, disposition = _consolidation_labels(cell.consolidation, branch=k)
        steps.append(
            SequenceStep(
                step_id=f"{prefix}-establish{k}",
                user_request=f"Record fact {k}.",
                expected_memory_writes=writes,
                record_class=record_class,
                disposition=disposition,
                environment_state=_cost_for(rng, cost_pool),
            )
        )

    steps.append(
        SequenceStep(
            step_id=f"{prefix}-goal",
            user_request="Produce the deliverable that uses the current value of every fact.",
            expected_memory_reads=list(current_ids),
            outcome_checks=[
                OutcomeCheck(
                    check_id=f"{prefix}-goal-check",
                    description=(
                        "goal requires the current value of every established fact "
                        "and must not state a superseded value"
                    ),
                    requires_memory=list(current_ids),
                    # Reward-bearing staleness (mem-z3gi): stating a stale value
                    # fails the goal; empty when the supersession factor is OFF.
                    forbidden_values=list(stale_values) if cell.supersession else [],
                )
            ],
            memory_probes=[
                MemoryProbe(
                    probe_id=f"{prefix}-probe{i}",
                    expected_memory_id=mid,
                    description="established fact must be recalled at the goal",
                )
                for i, mid in enumerate(current_ids)
            ],
            distractor_memories=_distractors(
                prefix,
                rng,
                width=width,
                taken_values=frozenset(current_values) | frozenset(stale_values),
                interference=cell.interference,
            ),
            superseded_memory_ids=list(superseded_ids),
            environment_state=_cost_for(rng, cost_pool),
        )
    )

    return BenchmarkSequence(
        sequence_id=prefix,
        title=f"factorial isolation-DAG w{width} cell {cell.cell_id}",
        domain="synthetic-factorial",
        goal="use the current value of every planted fact",
        steps=steps,
    )


def generate_factorial_family(
    *,
    seed: int,
    width: int,
    cost_pool: Sequence[tuple[int, int]] | None = None,
) -> list[BenchmarkSequence]:
    """The full 2^3 non-depth factorial at a frozen K=``width`` (8 cells). The topology
    (antichain width) is identical across all 8, and each ``(factor, level)`` appears in
    exactly four cells — balanced by construction."""
    return [
        generate_cell(seed=seed, width=width, cell=cell, cost_pool=cost_pool)
        for cell in all_factor_cells()
    ]
