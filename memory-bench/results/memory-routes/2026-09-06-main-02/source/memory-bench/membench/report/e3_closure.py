"""E3a headline — write→later-read CLOSURE, and the first headline consumer of
``score_retrieval`` / ``score_retention``.

One seed = one three-step world (``generators.e3_closure_world``) driven through
``runner.conditions.run_sequence``. The endpoint is the B step's reward: closure
holds for a seed iff the apply step deployed with the pin an EARLIER step wrote.
``closure_rate`` is the Bernoulli mean over seeds.

The lattice this module exists to establish, before any arm is compared:

- **CEILING** — ``ScriptedAgent`` on an id-exact arm must reach ``closure_rate ==
  1.0``. Anything less means the fixture, not the arm, is the finding; the run
  reports ``halt: true`` and the CLI exits non-zero rather than printing an
  uninterpretable number.
- **FLOOR** — ``NeverWritesAgent`` on the same write-bearing arm must reach ``0.0``.
  That is what proves closure measures the WRITE and not the prompt.

Honest absences, carried in the summary rather than silently reported as zeros:

- ``supersession_correct`` / ``stale_memory_removed`` are UNMEASURABLE here. The
  ``MemorySystem`` ABC has no removal op, so ``removed_ids`` is always empty and
  passing ``superseded_expected_ids`` would flip both fields from constant-True to
  constant-FALSE for every arm — a fabricated penalty, not a measurement. The
  channel that still separates a read-everything arm from a compliant one is the
  outcome check's forbidden-value list, and it is read through the reward.
- ``correct_scope_rate`` is a pass-through default in the deterministic path (no
  arm here distinguishes scope), so it is reported as unmeasured, not as a 1.0 win.

Four further disclosures ride the summary so no number here is read as more than it
is (see the constants below for the emitted text):

- EVERY reported retrieval field is ANSWER-KEY CUED (``ANSWER_KEY_CUE``): on this
  fixture no retrieval field discriminates among arms that honor ``requested_ids``;
  only a NON-COMPLIANT read-everything arm moves any of them;
- ``forbidden_write_rate`` is a channel no wired agent exercises
  (``FORBIDDEN_WRITE_NOT_EXERCISED``), decided on the WRITE COUNT on forbidden-bearing
  steps rather than on the rate, which cannot tell "wrote nothing" from "wrote clean";
- the floor is an ID-PRESENCE short-circuit, so non-id-keyed arms score 0 by
  construction (``FLOOR_IS_ID_PRESENCE``);
- a control-condition arm performs zero writes, so its ceiling is not a closure
  (``CONDITION_CAVEAT``).

Validity gates ride THIS summary, never a per-cell metric vector: a gate folded into
a per-seed vector flattens into the paired mean and stops being a gate.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from statistics import mean

from membench.generators.e3_closure_world import (
    GENERATOR_VERSION,
    ClosureWorld,
    assert_unguessable,
    generate_closure_world,
)
from membench.runner.agent import Agent, NeverWritesAgent, ScriptedAgent
from membench.runner.conditions import SequenceRun, run_sequence
from membench.schemas.conditions import Condition
from membench.schemas.config import AgentConfig, ExperimentConfig, MemoryConfig

# A two-step Bernoulli endpoint read at 5 seeds cannot separate 0.8 from 1.0; the
# driver refuses rather than emitting a number nobody should quote.
MIN_SEEDS = 20

# arm name → the condition it is driven under. `oracle` and `none` are the fixed
# controls (the runner picks their system itself); every other name is the
# memory_enabled system under test.
_CONTROL_CONDITIONS = {
    "oracle": Condition.ORACLE_MEMORY,
    "none": Condition.NO_MEMORY,
}

# Arms whose retrieval is exact-by-id, so a ScriptedAgent ceiling of 1.0 is the
# expected reading. A non-id-exact arm may legitimately come in below 1.0 and is
# NOT a fixture failure — the ceiling gate only applies to these.
ID_EXACT_ARMS = frozenset({"oracle", "filesystem"})

# Arms an endogenous READ can be measured on. Every other arm resolves STRICTLY from
# `requested_ids` — `run_sequence` hands it the ids the fixture already knows are right — so it
# cannot answer a query the agent composed itself. Run one under `--endogenous-read` and the arm
# would return the answer-key ids no matter what the agent asked for, and the read rate would
# measure the cue rather than the choice. `lexical` is the exception because it RANKS a query.
# This is a refusal, not a default: silently falling back to the cued path is precisely how a
# fabricated endogenous number would enter the record.
ENDOGENOUS_READ_ARMS = frozenset({"lexical"})

_AGENTS: dict[str, type[Agent]] = {
    "scripted": ScriptedAgent,
    "never-writes": NeverWritesAgent,
}

# The store-level temporal LOO of the real corpus does not apply to a generated
# world; these are the three STRUCTURAL substitutes that actually hold here. Named
# in the summary so no reader mistakes this for `closedBefore`-bounded retrieval.
LOO_SUBSTITUTES = (
    "_oracle_pool raises on a same-id/different-content rewrite, so the oracle "
    "cannot hand an early step a later step's content (within-sequence future leak)",
    "_assert_superseded_written raises unless every superseded id was written by a "
    "STRICTLY EARLIER step, so the stale signal is retrievable rather than silently 0",
    "run_sequence resets the memory system once per condition on a per-condition "
    "scope root, so no condition inherits another condition's store",
)

# DISCLOSURE — retrieval on this path is ANSWER-KEY CUED. run_sequence builds
# RetrievalRequest(requested_ids=step.expected_memory_reads)
# (runner/conditions.py), i.e. it hands the arm the ids the fixture already knows
# are the right ones. Any arm that honors requested_ids therefore reads
# relevant_memory_retrieved_rate == 1.0 and distractor_retrieval_rate == 0.0 by
# construction — and because the fixture requests ONLY the v2 id, the SAME cue pins
# stale_memory_retrieval_rate and missed_required_memory_count at 0.0 / 0.0 (measured
# across 20 seeds on filesystem AND oracle). ALL FOUR are reported as CUED, never as
# retrieval quality: among arms that honor requested_ids no retrieval field here
# discriminates. Only a NON-COMPLIANT read-everything arm moves any of them.
ANSWER_KEY_CUED_FIELDS = (
    "relevant_memory_retrieved_rate",
    "distractor_retrieval_rate",
    "stale_memory_retrieval_rate",
    "missed_required_memory_count",
)
ANSWER_KEY_CUE = (
    "run_sequence issues RetrievalRequest(requested_ids=step.expected_memory_reads) and "
    "the generator requests ONLY the v2 id, so for any arm honoring requested_ids these "
    "fields are GUARANTEED 1.0 / 0.0 / 0.0 / 0.0. They are a cue-compliance check, NOT a "
    "measurement of retrieval quality: no retrieval field here discriminates among "
    "compliant arms, and only a non-compliant read-everything arm moves them."
)

# The B step is the only step carrying forbidden_memory_writes, and it expects no
# writes; both wired agents persist exactly ``expected_memory_writes``. So a 0.0
# here is STRUCTURAL, not a clean result. A WritesStaleAgent that rewrites the
# superseded id would move it, but inventing a third reference agent to green a
# channel is exactly the move this bead already rejected for over_retention_rate;
# the channel is labeled not-exercised instead, and its unit coverage lives in
# test_forbidden_write_rate_is_a_directed_channel (scorer level, where it moves).
FORBIDDEN_WRITE_DENOMINATOR = (
    "DENOMINATOR: averaged ONLY over steps carrying forbidden_memory_writes (the apply "
    "step); other steps have no forbidden ids and _ratio(x, 0) = 0.0 would dilute the "
    "rate toward zero if they were averaged in"
)
FORBIDDEN_WRITE_NOT_EXERCISED = (
    "NOT EXERCISED: ZERO writes occurred on any step carrying forbidden ids "
    "(ScriptedAgent/NeverWritesAgent persist exactly expected_memory_writes, and the "
    "apply step expects none), so 0.0 is structural rather than a measured clean run"
)

# The never-writes FLOOR of 0.0 comes from outcome_check_passes short-circuiting on
# requires_memory not being a subset of available_memory ids — an id-presence check,
# not the v2 literal being unobtainable. An agent that already held the answer with
# zero memory would still floor at 0.0.
FLOOR_IS_ID_PRESENCE = (
    "closure's 0.0 floor comes from the requires_memory ID-PRESENCE short-circuit, not "
    "from the v2 literal being unobtainable. CONSEQUENCE: any arm not keyed on harness "
    "ids - native/builtin agent memory, i.e. the whole E1/E2 line - scores 0 here even "
    "if it genuinely closed the write->read loop. This endpoint reads id-keyed arms only."
)

# On a non-MEMORY_ENABLED condition the agent performs no writes at all
# (runner/conditions.py gates the write loop on MEMORY_ENABLED), so a 1.0 there is
# the oracle handing over the content, not a write->read closure.
CONDITION_CAVEAT = (
    "this arm runs under a CONTROL condition, where run_sequence performs ZERO agent "
    "writes; closure_rate here reflects the oracle/no-memory path, NOT a write->read "
    "closure. Only MEMORY_ENABLED runs measure the loop."
)


# --arm oracle satisfies the ceiling gate without exercising the write path at all
# (ORACLE_MEMORY performs zero agent writes), so its 1.0 is a WEAKER check than the
# MEMORY_ENABLED ceiling: it certifies delivery, not closure.
CEILING_KIND_CAVEAT = (
    "DELIVERY-ONLY ceiling: this ceiling run is on a control condition with ZERO agent "
    "writes, so it certifies the delivery path only. It is WEAKER than the "
    "MEMORY_ENABLED ceiling and does not certify the write->read closure. "
    "retention.write_hit_rate likewise reads 0.0 here, for the same reason."
)


@dataclass(frozen=True)
class ClosureCell:
    """One seed's readout. Per-cell metrics ONLY — the validity gates live on the
    summary, deliberately not in here."""

    seed: int
    sequence_id: str
    closure: bool
    apply_reward: float
    # From MetricsBundle.retrieval on the apply step.
    relevant_memory_retrieved: bool
    distractor_retrieval_rate: float
    stale_memory_retrieval_rate: float
    missed_required_memory_count: int
    # From MetricsBundle.retention, summed over the sequence's write-bearing steps.
    write_hit_rate: float
    forbidden_write_rate: float
    # How many ids the agent wrote on the steps that CARRY forbidden ids. A rate of
    # 0.0 is ambiguous on its own — it reads the same whether the agent wrote nothing
    # there or wrote only permitted ids — so the count is carried alongside it and is
    # what "exercised" is decided on.
    forbidden_step_write_count: int


def _experiment(arm: str, agent_config_id: str) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"e3-closure-{arm}-{agent_config_id}",
        agent=AgentConfig(agent_config_id=agent_config_id),
        memory=MemoryConfig(memory_config_id=arm, system=arm),
        dataset_id="e3-closure-world",
        conditions=[_CONTROL_CONDITIONS.get(arm, Condition.MEMORY_ENABLED)],
    )


def score_closure_run(world: ClosureWorld, run: SequenceRun) -> ClosureCell:
    """Read one seed's closure cell off the run's trials.

    The apply (B) step's trial carries the endpoint. Each retention channel is
    averaged over the steps where it is DEFINED — write_hit_rate over write-expecting
    steps, forbidden_write_rate over steps carrying forbidden ids — so neither is
    diluted by a step whose vacuous denominator scores 0.0."""
    # Trials are keyed by step_id, so a multi-condition run would collapse
    # last-write-wins and make closure depend on CONDITION ORDER rather than on the
    # write. Refuse instead of scoring a silently condition-dependent cell.
    conditions = sorted({t.condition.value for t in run.trials})
    if len(conditions) > 1:
        raise ValueError(
            "score_closure_run scores a SINGLE-condition run; got "
            f"{conditions} - keying trials by step_id across conditions is "
            "last-write-wins and would make closure depend on condition order"
        )
    trials = {t.step_id: t for t in run.trials}
    apply_trial = trials[world.apply_step_id]
    metrics = apply_trial.metrics
    retrieval = metrics.retrieval

    write_steps = [s.step_id for s in world.sequence.steps if s.expected_memory_writes]
    write_hits = [trials[sid].metrics.retention.write_hit_rate for sid in write_steps]
    # forbidden_write_rate is _ratio(n_forbidden, len(written)) and _ratio(x, 0) is 0.0,
    # so averaging over trials whose step carries no forbidden ids understates the rate
    # (~3x on this three-step world). Restrict to the steps where the channel is
    # defined, exactly as write_hit_rate is restricted to write-expecting steps.
    forbidden_steps = [s.step_id for s in world.sequence.steps if s.forbidden_memory_writes]
    forbidden = [trials[sid].metrics.retention.forbidden_write_rate for sid in forbidden_steps]
    # _ratio(n_forbidden, len(written)) collapses "wrote nothing here" and "wrote only
    # permitted ids here" to the same 0.0. The write COUNT on those steps separates
    # them, so `exercised` can mean "a write actually happened on a forbidden-bearing
    # step" rather than the weaker "the forbidden rate came out above zero".
    forbidden_writes = sum(len(trials[sid].trace.files_written) for sid in forbidden_steps)

    return ClosureCell(
        seed=world.seed,
        sequence_id=world.sequence.sequence_id,
        closure=metrics.task.reward == 1.0,
        apply_reward=metrics.task.reward,
        relevant_memory_retrieved=retrieval.relevant_memory_retrieved,
        distractor_retrieval_rate=retrieval.distractor_retrieval_rate,
        stale_memory_retrieval_rate=retrieval.stale_memory_retrieval_rate,
        missed_required_memory_count=retrieval.missed_required_memory_count,
        write_hit_rate=mean(write_hits) if write_hits else 0.0,
        forbidden_write_rate=mean(forbidden) if forbidden else 0.0,
        forbidden_step_write_count=forbidden_writes,
    )


def run_closure_cells(seeds: list[int], *, arm: str, agent_name: str) -> list[ClosureCell]:
    """Drive every seed's world through ``run_sequence`` and score its cell."""
    if agent_name not in _AGENTS:
        raise ValueError(f"unknown agent {agent_name!r} (known: {', '.join(sorted(_AGENTS))})")
    agent = _AGENTS[agent_name]()
    experiment = _experiment(arm, agent.agent_config_id)
    cells: list[ClosureCell] = []
    for seed in seeds:
        world = generate_closure_world(seed)
        # The leak proof runs on every scored world, not only under --check-unguessable:
        # a closure number from a leaked world would be meaningless.
        assert_unguessable(world)
        run = run_sequence(world.sequence, experiment, agent)
        cells.append(score_closure_run(world, run))
    return cells


def summarize_closure(
    cells: list[ClosureCell], *, arm: str, agent_name: str, n_seeds: int
) -> dict[str, object]:
    """The emitted summary — endpoint, aggregates, validity gates, honest absences.

    ``halt`` is the fixture-validity gate: a ceiling run (the reference agent on an
    id-exact arm) that does not reach ``closure_rate == 1.0`` means the fixture is
    broken and NO closure number from it is interpretable."""
    closure_rate = mean(1.0 if c.closure else 0.0 for c in cells) if cells else 0.0
    is_ceiling_run = agent_name == "scripted" and arm in ID_EXACT_ARMS
    halt = is_ceiling_run and closure_rate != 1.0
    condition = _CONTROL_CONDITIONS.get(arm, Condition.MEMORY_ENABLED)
    # Exercised = a write actually OCCURRED on a forbidden-bearing step. Reading it
    # off the rate instead would call the channel unexercised whenever an agent wrote
    # there but happened to write only permitted ids - which is a measured clean run,
    # the one case the "structural 0.0" caveat must NOT be attached to.
    forbidden_exercised = any(c.forbidden_step_write_count > 0 for c in cells)
    return {
        "generator_version": GENERATOR_VERSION,
        "arm": arm,
        "agent": agent_name,
        "n_seeds": n_seeds,
        "min_seeds": MIN_SEEDS,
        "closure_rate": closure_rate,
        "retrieval": {
            "relevant_memory_retrieved_rate": (
                mean(1.0 if c.relevant_memory_retrieved else 0.0 for c in cells) if cells else 0.0
            ),
            "distractor_retrieval_rate": (
                mean(c.distractor_retrieval_rate for c in cells) if cells else 0.0
            ),
            "stale_memory_retrieval_rate": (
                mean(c.stale_memory_retrieval_rate for c in cells) if cells else 0.0
            ),
            "missed_required_memory_count": (
                mean(float(c.missed_required_memory_count) for c in cells) if cells else 0.0
            ),
            "answer_key_cued": list(ANSWER_KEY_CUED_FIELDS),
            "answer_key_cue": ANSWER_KEY_CUE,
        },
        "retention": {
            "write_hit_rate": mean(c.write_hit_rate for c in cells) if cells else 0.0,
            "forbidden_write_rate": (mean(c.forbidden_write_rate for c in cells) if cells else 0.0),
            "forbidden_write_rate_exercised": forbidden_exercised,
            "forbidden_step_write_count": sum(c.forbidden_step_write_count for c in cells),
            "forbidden_write_rate_denominator": FORBIDDEN_WRITE_DENOMINATOR,
            "forbidden_write_rate_note": (
                FORBIDDEN_WRITE_DENOMINATOR
                if forbidden_exercised
                else f"{FORBIDDEN_WRITE_DENOMINATOR}. {FORBIDDEN_WRITE_NOT_EXERCISED}"
            ),
        },
        "validity": {
            "is_ceiling_run": is_ceiling_run,
            "ceiling_kind": (
                ""
                if not is_ceiling_run
                else (
                    "write_read_closure"
                    if condition is Condition.MEMORY_ENABLED
                    else "delivery_only"
                )
            ),
            "ceiling_caveat": (
                ""
                if (not is_ceiling_run) or condition is Condition.MEMORY_ENABLED
                else CEILING_KIND_CAVEAT
            ),
            "ceiling_ok": (not is_ceiling_run) or closure_rate == 1.0,
            "halt": halt,
            "halt_reason": (
                "ceiling below 1.0 on an id-exact arm: the fixture is broken, so no "
                "closure number from it is interpretable"
                if halt
                else ""
            ),
            "leak_proof": (
                "mechanical substring check: the v2 literal appears in no step's "
                "user_request / available_tools / environment_state "
                "(generators.e3_closure_world.assert_unguessable). The NO_MEMORY leg is "
                "a SMOKE check only — outcome_check_passes short-circuits on the missing "
                "required id, so it would read 0 whether or not the answer leaked."
            ),
            "loo_substitutes": list(LOO_SUBSTITUTES),
            "condition": condition.value,
            "write_read_closure_path": condition is Condition.MEMORY_ENABLED,
            "condition_caveat": ("" if condition is Condition.MEMORY_ENABLED else CONDITION_CAVEAT),
            "floor_is_id_presence": FLOOR_IS_ID_PRESENCE,
        },
        "unmeasurable_endpoints": {
            "supersession_correct": (
                "no removal op on the MemorySystem ABC, so removed_ids is always empty; "
                "reporting it would fabricate a constant FALSE for every arm"
            ),
            "stale_memory_removed": "same absence as supersession_correct",
            "correct_scope_rate": (
                "no arm on this path distinguishes memory scope; the scorer's "
                "pass-through default would read as a 1.0 win, not a measurement"
            ),
        },
        "cells": [asdict(c) for c in cells],
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E3a write→later-read closure")
    parser.add_argument("--seeds", type=int, required=True, help=f"seed count (>= {MIN_SEEDS})")
    parser.add_argument("--arm", default="filesystem")
    parser.add_argument("--agent", default="scripted", choices=sorted(_AGENTS))
    parser.add_argument("--json", action="store_true", help="emit compact JSON")
    parser.add_argument(
        "--endogenous-read",
        action="store_true",
        help=(
            "grade the read as the agent's choice rather than a harness retrieve; only "
            f"supported on {sorted(ENDOGENOUS_READ_ARMS)}"
        ),
    )
    args = parser.parse_args(argv)

    if args.endogenous_read and args.arm not in ENDOGENOUS_READ_ARMS:
        parser.error(
            f"--endogenous-read is unsupported on arm {args.arm!r}: it resolves strictly from "
            "requested_ids, so it would return the fixture's own answer-key ids whatever the "
            f"agent asked for. Supported arms: {sorted(ENDOGENOUS_READ_ARMS)}"
        )

    if args.seeds < MIN_SEEDS:
        parser.error(
            f"--seeds {args.seeds} is below the seed floor: a two-step Bernoulli "
            f"endpoint needs at least {MIN_SEEDS} seeds to be readable"
        )

    cells = run_closure_cells(list(range(args.seeds)), arm=args.arm, agent_name=args.agent)
    summary = summarize_closure(cells, arm=args.arm, agent_name=args.agent, n_seeds=args.seeds)
    print(json.dumps(summary) if args.json else json.dumps(summary, indent=2))
    return 2 if summary["validity"]["halt"] else 0  # type: ignore[index]


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(_main())
