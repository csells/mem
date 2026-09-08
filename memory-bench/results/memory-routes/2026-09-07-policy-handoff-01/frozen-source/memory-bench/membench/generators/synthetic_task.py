"""§11 — the synthetic task generator (Tier 0, pure Python).

The spec §11.2 three-stage pipeline, authored deterministically so CI never calls
a model (the package policy — see ``generators.__init__``):

  Stage 1 (blueprint)  : ``TaskBlueprint`` — a multi-step task plan whose early
                         steps ESTABLISH facts and whose goal step REQUIRES them.
  Stage 2 (steps)      : ``expand_blueprint`` turns each ``StepBrief`` into a
                         ``SequenceStep`` (the establishing write) and appends the
                         goal step that depends on every established fact.
  Stage 3 (schema)     : the same pass assigns seed-namespaced ids and emits the
                         deterministic ``BenchmarkSequence`` the runner consumes.

Memory-dependence is STRUCTURAL, not hoped-for: the goal step's ``OutcomeCheck``
requires every fact id an earlier step wrote, so the oracle condition (memory
available) passes it and the no-memory condition cannot. ``pilot_filter`` then
confirms that property held in a real pilot run before a task is admitted.

Given a seed the sequence is byte-reproducible: the seed selects a blueprint from
the authored bank and namespaces every id, and nothing else varies. A local model
may later enrich the surface prose offline into a frozen fixture, but the facts,
the dependency structure, and the ids are always ours.
"""

from __future__ import annotations

from dataclasses import dataclass

from membench.schemas.sequence import (
    BenchmarkSequence,
    MemoryProbe,
    OutcomeCheck,
    SequenceStep,
)

GENERATOR_VERSION = "synthetic-task.v1"


@dataclass(frozen=True)
class StepBrief:
    """One establishing step in a blueprint (spec §11.2 ``step_briefs``). ``purpose``
    is the step's user-facing request; ``fact_key`` is the memory the step establishes
    and ``fact_value`` is its authored ground-truth content — the goal step later
    requires this fact, which is what makes the task memory-dependent."""

    purpose: str
    fact_key: str
    fact_value: str


@dataclass(frozen=True)
class TaskBlueprint:
    """A synthetic task plan (spec §11.2 ``task_blueprint``). The ``step_briefs``
    establish facts; ``final_goal`` is the closing request that depends on all of
    them. Authored here as ground truth — this is the Tier-0 oracle.

    ``shape_id`` links a blueprint to the real fail-to-pass failure shape it
    reproduces (``generators.ftp_shapes``); ``None`` for the generic continuity
    blueprints that mimic no specific real shape."""

    blueprint_id: str
    title: str
    domain: str
    final_goal: str
    step_briefs: tuple[StepBrief, ...]
    shape_id: str | None = None


# A small bank of authored blueprints. Each is a realistic multi-session task whose
# goal cannot be met without recalling facts established in earlier, separate steps.
_BLUEPRINTS: tuple[TaskBlueprint, ...] = (
    TaskBlueprint(
        blueprint_id="incident-runbook",
        title="Write the incident postmortem",
        domain="incident-response",
        final_goal=(
            "Write the postmortem: name the service that failed, the rollback command "
            "used, and the on-call owner who ran it."
        ),
        step_briefs=(
            StepBrief(
                purpose="Record which service paged.",
                fact_key="failing-service",
                fact_value="checkout-api went down at 02:14 UTC",
            ),
            StepBrief(
                purpose="Record the rollback command that resolved it.",
                fact_key="rollback-command",
                fact_value="kubectl rollout undo deploy/checkout-api",
            ),
            StepBrief(
                purpose="Record who was on call.",
                fact_key="oncall-owner",
                fact_value="on-call was priya@ (platform rotation)",
            ),
        ),
    ),
    TaskBlueprint(
        blueprint_id="api-migration",
        title="Migrate the client to the new endpoint",
        domain="api-migration",
        final_goal=(
            "Update the client: use the new endpoint, drop the old one, and respect the "
            "deprecation date."
        ),
        step_briefs=(
            StepBrief(
                purpose="Record the old endpoint being retired.",
                fact_key="old-endpoint",
                fact_value="GET /v1/orders is deprecated",
            ),
            StepBrief(
                purpose="Record the replacement endpoint.",
                fact_key="new-endpoint",
                fact_value="use GET /v2/orders instead",
            ),
            StepBrief(
                purpose="Record the cutoff date.",
                fact_key="deprecation-date",
                fact_value="/v1 is removed on 2026-09-01",
            ),
        ),
    ),
    TaskBlueprint(
        blueprint_id="config-audit",
        title="Reconcile the service config",
        domain="config-audit",
        final_goal=(
            "Reconcile the config: apply the required timeout, the region, and the "
            "feature flag established earlier."
        ),
        step_briefs=(
            StepBrief(
                purpose="Record the agreed request timeout.",
                fact_key="request-timeout",
                fact_value="request timeout is 30s",
            ),
            StepBrief(
                purpose="Record the deployment region.",
                fact_key="deploy-region",
                fact_value="primary region is us-east-1",
            ),
            StepBrief(
                purpose="Record the feature flag state.",
                fact_key="feature-flag",
                fact_value="checkout_v2 flag is enabled",
            ),
        ),
    ),
)


def blueprint_for_seed(seed: int) -> TaskBlueprint:
    """Select an authored blueprint deterministically from the bank. Same seed ⇒ same
    blueprint; the selection is the only seed-dependent choice the pipeline makes."""
    return _BLUEPRINTS[seed % len(_BLUEPRINTS)]


def expand_blueprint(blueprint: TaskBlueprint, *, seed: int) -> BenchmarkSequence:
    """Stages 2-3: expand a blueprint into a deterministic ``BenchmarkSequence``.

    Each ``StepBrief`` becomes one establishing step that writes its fact under a
    seed-namespaced id; a final goal step then requires every established id (via an
    ``OutcomeCheck`` and per-fact ``MemoryProbe``s), so the task only passes when the
    earlier memory is available. Ids are namespaced by blueprint + seed so sequences
    from different seeds never share a memory scope."""
    if not blueprint.step_briefs:
        raise ValueError(f"blueprint {blueprint.blueprint_id!r} has no step_briefs")

    prefix = f"{blueprint.blueprint_id}-seed{seed}"

    steps: list[SequenceStep] = []
    established: dict[str, str] = {}
    for i, brief in enumerate(blueprint.step_briefs):
        memory_id = f"{prefix}-{brief.fact_key}"
        established[memory_id] = brief.fact_value
        steps.append(
            SequenceStep(
                step_id=f"{prefix}-s{i}-{brief.fact_key}",
                user_request=brief.purpose,
                expected_memory_writes={memory_id: brief.fact_value},
            )
        )

    required = list(established)
    steps.append(
        SequenceStep(
            step_id=f"{prefix}-s{len(blueprint.step_briefs)}-goal",
            user_request=blueprint.final_goal,
            expected_memory_reads=required,
            outcome_checks=[
                OutcomeCheck(
                    check_id=f"{prefix}-goal-check",
                    description="goal requires every fact established in earlier steps",
                    requires_memory=required,
                )
            ],
            memory_probes=[
                MemoryProbe(
                    probe_id=f"{prefix}-probe-{i}",
                    expected_memory_id=memory_id,
                    description="established fact must be recalled at the goal",
                )
                for i, memory_id in enumerate(required)
            ],
        )
    )

    return BenchmarkSequence(
        sequence_id=prefix,
        title=blueprint.title,
        domain=blueprint.domain,
        goal=blueprint.final_goal,
        steps=steps,
    )


def generate_synthetic_sequence(*, seed: int) -> BenchmarkSequence:
    """Emit a deterministic synthetic ``BenchmarkSequence`` for ``seed`` (the full
    §11 pipeline: blueprint → steps → schema). Same seed ⇒ byte-identical sequence."""
    return expand_blueprint(blueprint_for_seed(seed), seed=seed)


# Shape-grounded blueprints (mem-bxhh.5): tasks whose surface reproduces a real
# fail-to-pass failure shape (``generators.ftp_shapes``) while keeping the same
# structural memory-dependence — the goal cannot be met without recalling every fact
# an earlier step established. Held in a SEPARATE bank so the generic ``_BLUEPRINTS``
# seed→blueprint mapping (and the byte-reproducibility of existing seeds) is untouched.
SHAPE_BLUEPRINTS: tuple[TaskBlueprint, ...] = (
    TaskBlueprint(
        blueprint_id="token-rollup",
        title="Emit the per-arm token-count rollup",
        domain="experiment-aggregation",
        shape_id="aggregation-projection",
        final_goal=(
            "Emit the token-count rollup: sum the prompt and completion tokens each "
            "arm reported earlier, and project the per-arm totals into the summary."
        ),
        step_briefs=(
            StepBrief(
                purpose="Record arm A's reported token counts.",
                fact_key="tokens-arm-a",
                fact_value="arm-a used 1200 prompt + 340 completion tokens",
            ),
            StepBrief(
                purpose="Record arm B's reported token counts.",
                fact_key="tokens-arm-b",
                fact_value="arm-b used 980 prompt + 410 completion tokens",
            ),
            StepBrief(
                purpose="Record arm C's reported token counts.",
                fact_key="tokens-arm-c",
                fact_value="arm-c used 1530 prompt + 275 completion tokens",
            ),
        ),
    ),
    TaskBlueprint(
        blueprint_id="quota-exclusion",
        title="Summarize scores excluding the quota-voided task",
        domain="scoring-stats",
        shape_id="exclusion-filter",
        final_goal=(
            "Report the mean score, excluding the task that was quota-voided earlier "
            "so the paired comparison is not contaminated by the missing run."
        ),
        step_briefs=(
            StepBrief(
                purpose="Record task-1's score.",
                fact_key="score-task-1",
                fact_value="task-1 scored 0.82",
            ),
            StepBrief(
                purpose="Record task-2's score.",
                fact_key="score-task-2",
                fact_value="task-2 scored 0.64",
            ),
            StepBrief(
                purpose="Record which task hit the quota and must be excluded.",
                fact_key="quota-voided-task",
                fact_value="task-3 was quota-voided — exclude it from every aggregate",
            ),
        ),
    ),
)


def generate_shape_sequences() -> list[BenchmarkSequence]:
    """Expand every shape-grounded blueprint into a deterministic ``BenchmarkSequence``.

    These are the synthetic tasks the mem-bxhh.5 calibration runs the arms over: each
    reproduces a real fail-to-pass shape (its ``shape_id``) yet stays memory-dependent
    by construction. Ids are namespaced per blueprint, so the sequences never collide."""
    return [expand_blueprint(bp, seed=i) for i, bp in enumerate(SHAPE_BLUEPRINTS)]
