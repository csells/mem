"""§11 enterprise-workflow materialiser (Tier 0, pure Python).

Turns a NeMo-generated ``EnterpriseWorld`` + ``Project`` (the surface/cast) into N
memory-dependent ``BenchmarkSequence``s. Mirrors ``synthetic_task`` but draws its
cast (personas, channels) from the world and authors a richer fact graph:

* establishing steps write authored "decision facts" attributed to world personas;
* one subject per task — its position varied by seed — is SUPERSEDED through a chain
  of ``SUPERSESSION_DEPTH`` versions under distinct ids; each superseding step marks
  its predecessor (the Staleness signal) and the goal depends on the FINAL version
  only;
* the goal step carries ``distractor_memories`` — plausible-but-wrong values for the
  same subjects (the Confusion signal);
* the goal's ``OutcomeCheck`` requires every current id AND forbids stating any
  superseded value (``forbidden_values``), so staleness is reward-bearing: an arm
  that surfaces a stale version fails the goal instead of only ticking the
  ``stale_memory_retrieval_rate`` diagnostic (mem-z3gi);
* no agent-visible string separates the classes (mem-z3gi): memory ids are opaque
  content-keyed hashes (``opaque_memory_id``), and truth / stale / distractor all
  render through the SAME ``_fact`` template — only the value (and the drawn
  attribution) differs. Labels live in harness-side fields only (step ids, probe
  descriptions), which the runner never shows the agent.

ZFC boundary (the generators policy): NeMo supplied only the cast and prose; every
fact, value, dependency, distractor and supersession here is authored in pure
Python and is seed-reproducible. ``distractor_memories`` / ``superseded_memory_ids``
are the authored ground truth the runner seeds + scores Confusion/Staleness
against (mem-zt1c); the values are deliberately absent from the goal query, so a
naive top-k retriever cannot rank the truth above a distractor — that hardness is
the point.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from membench.generators.opaque_ids import opaque_memory_id
from membench.metrics.scorers import states_value
from membench.schemas.sequence import (
    BenchmarkSequence,
    ExpectedAction,
    MemoryProbe,
    OutcomeCheck,
    SequenceStep,
)
from membench.schemas.world import EnterpriseWorld, Persona, Project

GENERATOR_VERSION = "enterprise-workflow.v3"

# The tool the tool-requiring goal variant demands (mem-31vl): success requires
# invoking it with the CURRENT (supersession-aware) value as its argument, so a
# naive arm that surfaces a stale version drives a stale argument and fails.
_APPLY_TOOL = "apply_config"

# Supersession chain length for the one superseded subject (mem-z3gi): versions
# v1..vD under distinct opaque ids, each superseding step marking its predecessor;
# only vD is goal-required. Depth >= 3 exercises multi-hop staleness.
SUPERSESSION_DEPTH = 3

# The ONE establishing request template. Every establishing step — including each
# link of the supersession chain — uses it verbatim, so the request wording cannot
# mark the superseded subject to the agent ("initial"/"corrected" would).
_RECORD_REQUEST = "Record the current value of {prompt}."


@dataclass(frozen=True)
class _Subject:
    """A decision a task must recall. ``values`` are the authored ground-truth
    candidates; the materialiser picks the current one (and distinct stale/wrong
    ones) deterministically per task."""

    key: str
    prompt: str
    values: tuple[str, ...]


# Authored decision subjects — domain-agnostic operational facts an enterprise task
# would need to recall. Each has > SUPERSESSION_DEPTH distinct values so a full
# supersession chain plus a distinct distractor value always exist, and no value is
# a word-boundary substring of another (the ``states_value`` grading contract).
_SUBJECTS: tuple[_Subject, ...] = (
    _Subject("deploy-timeout", "the production deploy timeout", ("15s", "30s", "45s", "60s")),
    _Subject(
        "primary-region",
        "the primary deployment region",
        ("us-east-1", "us-west-2", "eu-west-1", "ap-south-1"),
    ),
    _Subject(
        "rollback-command",
        "the approved rollback command",
        (
            "kubectl rollout undo",
            "helm rollback",
            "terraform apply -refresh",
            "git revert then redeploy",
        ),
    ),
    _Subject(
        "feature-flag",
        "the checkout_v2 feature flag state",
        ("enabled", "disabled", "canary-10%", "canary-50%"),
    ),
    _Subject("api-version", "the supported API version", ("v1", "v2", "v3", "v4")),
    _Subject(
        "retention-window", "the data retention window", ("30 days", "90 days", "1 year", "7 years")
    ),
)

_SHALLOW = [s.key for s in _SUBJECTS if len(set(s.values)) <= SUPERSESSION_DEPTH]
if _SHALLOW:
    raise ValueError(
        f"every subject needs > {SUPERSESSION_DEPTH} distinct values (chain + distractor); "
        f"too few on {_SHALLOW}"
    )


def _attribution(persona: Persona, channel_name: str | None) -> str:
    where = f" in #{channel_name}" if channel_name else ""
    role = f" ({persona.role})" if persona.role else ""
    return f"{persona.name}{role}{where}"


def _fact(prompt: str, value: str, persona: Persona, channel: str | None) -> str:
    """THE memory content template — shared verbatim by truth, stale and distractor
    entries so no verb tense or attribution shape separates the classes; only the
    value (and the drawn attribution) differs (mem-z3gi)."""
    return f"{prompt} is {value} — by {_attribution(persona, channel)}"


# The inverse of ``_fact``, anchored on the template's own two fixed separators. Non-greedy on
# the prompt so a value may itself contain " is " ("the rollback command is deploy rollback is
# not ..." would still split at the FIRST " is ", which is the prompt/value boundary because no
# authored prompt contains one); non-greedy on the value so the attribution is everything after
# the FIRST " — by ", which no authored value contains. This is a format-anchored parse of a
# string this module minted, not a heuristic over prose.
_FACT_RE = re.compile(r"^(?P<prompt>.+?) is (?P<value>.+?) — by (?P<attribution>.+)$", re.DOTALL)


def fact_value(content: str) -> str:
    """The VALUE a ``_fact``-shaped memory content states (mem-zfm0m).

    The twin corpus inlines the value of every fact a task requires, and the realistic (unscored)
    facts reach it only as ``_fact`` prose. Raises ``ValueError`` on content this template did not
    produce rather than guessing at it."""
    match = _FACT_RE.fullmatch(content)
    if match is None:
        raise ValueError(f"not a fact-shaped memory content: {content!r}")
    return match.group("value")


def fact_subject(content: str) -> str:
    """The SUBJECT a ``_fact``-shaped memory content states a value for — the same
    format-anchored parse as ``fact_value``, off the template's other named group.

    The unnecessary twin needs it to say WHICH subject each value it inlines belongs to. Without
    it the twin can only emit a bare list of opaque tokens, which does not read as a set of
    values at all."""
    match = _FACT_RE.fullmatch(content)
    if match is None:
        raise ValueError(f"not a fact-shaped memory content: {content!r}")
    return match.group("prompt")


def _assert_no_forbidden_value_leak(
    forbidden_values: list[str], surfaced_contents: list[str]
) -> None:
    """Authoring guard: a stale (forbidden) value must never appear in a REQUIRED or
    distractor content, or the goal would fail even when no stale memory was
    surfaced. Holds by construction (values are distinct within a subject, disjoint
    across subjects); raises loudly on subject-bank drift."""
    for value in forbidden_values:
        for content in surfaced_contents:
            if states_value(content, value):
                raise ValueError(
                    f"authored stale value {value!r} appears in non-stale content "
                    f"{content!r}; fix the subject bank"
                )


def _materialize_task(
    world: EnterpriseWorld,
    project: Project,
    *,
    task_index: int,
    facts_per_task: int,
    seed: int,
    charter: tuple[str, str] | None = None,
    establish_charter: bool = False,
    tool_requiring: bool = False,
) -> BenchmarkSequence:
    rng = random.Random((seed << 16) ^ (task_index * 2654435761))
    subjects = rng.sample(_SUBJECTS, facts_per_task)
    # The superseded subject's position is seed-varied (mem-z3gi) — a fixed i==0
    # would let position stand in for the staleness label.
    chain_position = rng.randrange(facts_per_task)
    seq_id = f"{world.world_id}-task{task_index}"

    def draw_persona() -> Persona:
        return world.personas[rng.randrange(len(world.personas))]

    def draw_channel() -> str | None:
        if not world.channels:
            return None
        return world.channels[rng.randrange(len(world.channels))].name

    steps: list[SequenceStep] = []
    required_ids: list[str] = []
    required_contents: list[str] = []
    probes: list[MemoryProbe] = []
    distractors: dict[str, str] = {}
    superseded: list[str] = []
    forbidden_values: list[str] = []
    # The current value of the ONE superseded subject — the value a tool-requiring
    # goal must apply (mem-31vl). None until the chain branch below sets it
    # (chain_position is always visited exactly once); a broken invariant then fails
    # loudly at the assert rather than authoring arg_values=[""] (which would match
    # any text, since states_value(text, "") is true).
    chain_current_value: str | None = None

    for i, subject in enumerate(subjects):
        if i == chain_position:
            # The supersession chain: v1 → … → vD, distinct ids, each superseding
            # step marking its predecessor; the goal depends on vD only and must
            # not state any earlier value.
            chain_values = rng.sample(list(subject.values), SUPERSESSION_DEPTH)
            version_ids = [
                opaque_memory_id(seq_id, f"{subject.key}-v{v}")
                for v in range(1, SUPERSESSION_DEPTH + 1)
            ]
            for v, (version_id, value) in enumerate(zip(version_ids, chain_values, strict=True)):
                steps.append(
                    SequenceStep(
                        step_id=f"{seq_id}-s{i}v{v + 1}-{subject.key}",
                        user_request=_RECORD_REQUEST.format(prompt=subject.prompt),
                        expected_memory_writes={
                            version_id: _fact(subject.prompt, value, draw_persona(), draw_channel())
                        },
                        superseded_memory_ids=[version_ids[v - 1]] if v else [],
                    )
                )
            current_id = version_ids[-1]
            current_value = chain_values[-1]
            chain_current_value = current_value
            superseded.extend(version_ids[:-1])
            forbidden_values.extend(chain_values[:-1])
            taken_values = list(chain_values)
        else:
            current_value = rng.choice(subject.values)
            current_id = opaque_memory_id(seq_id, subject.key)
            steps.append(
                SequenceStep(
                    step_id=f"{seq_id}-s{i}-{subject.key}",
                    user_request=_RECORD_REQUEST.format(prompt=subject.prompt),
                    expected_memory_writes={
                        current_id: _fact(
                            subject.prompt, current_value, draw_persona(), draw_channel()
                        )
                    },
                )
            )
            taken_values = [current_value]

        required_ids.append(current_id)
        required_contents.append(steps[-1].expected_memory_writes[current_id])
        probes.append(
            MemoryProbe(
                probe_id=f"{seq_id}-probe-{subject.key}",
                expected_memory_id=current_id,
                description=f"{subject.prompt} must be recalled at the goal",
            )
        )
        # A plausible-but-wrong value for the same subject, same template, attributed
        # to a freshly drawn persona — the Confusion stressor the goal must not be
        # fooled by. The value is distinct from the current AND every stale value, so
        # surfacing a distractor is never mis-scored as staleness.
        wrong_value = rng.choice([v for v in subject.values if v not in taken_values])
        distractors[opaque_memory_id(seq_id, f"{subject.key}-distractor")] = _fact(
            subject.prompt, wrong_value, draw_persona(), draw_channel()
        )

    # Cross-task continuity: a project charter established in an EARLIER task that
    # this task's goal also requires. Under run_project (shared store) the earlier
    # write is visible; under isolated run_sequence it is not — that gap is the
    # continuity signal. ``establish_charter`` (task 0 only) writes it.
    if charter is not None:
        charter_id, charter_content = charter
        if establish_charter:
            steps.insert(
                0,
                SequenceStep(
                    step_id=f"{seq_id}-charter",
                    user_request="Record the project charter decision.",
                    expected_memory_writes={charter_id: charter_content},
                ),
            )
        required_ids.append(charter_id)
        required_contents.append(charter_content)
        probes.append(
            MemoryProbe(
                probe_id=f"{seq_id}-probe-charter",
                expected_memory_id=charter_id,
                description="the project charter (set in an earlier task) must be recalled",
            )
        )

    _assert_no_forbidden_value_leak(
        forbidden_values, required_contents + list(distractors.values())
    )

    prompts = ", ".join(s.prompt for s in subjects)
    if tool_requiring:
        assert chain_current_value is not None, "chain_position was never visited"
        # Tool-requiring variant (mem-31vl): success requires APPLYING the current
        # value via a tool call, not merely stating it. Staleness moves off the text
        # answer (forbidden_values cleared) onto the tool argument, so the tool action
        # is the sole reward-bearing channel — a stale value fails in the argument, not
        # the prose. That makes memory quality load-bearing THROUGH the action.
        goal_request = (
            f"{project.goal} Using the tool `{_APPLY_TOOL}`, apply the current value "
            f"of: {prompts}."
        )
        goal_check = OutcomeCheck(
            check_id=f"{seq_id}-goal-check",
            description=(
                f"goal requires calling `{_APPLY_TOOL}` with the current value of the "
                "superseded subject and never a stale one"
            ),
            requires_memory=required_ids,
            requires_action=[
                ExpectedAction(
                    tool=_APPLY_TOOL,
                    arg_values=[chain_current_value],
                    forbidden_values=list(forbidden_values),
                )
            ],
        )
        available_tools = [_APPLY_TOOL]
    else:
        goal_request = f"{project.goal} State the current value of: {prompts}."
        goal_check = OutcomeCheck(
            check_id=f"{seq_id}-goal-check",
            description=(
                "goal requires the current value of each established subject "
                "and must not state a superseded value"
            ),
            requires_memory=required_ids,
            forbidden_values=list(forbidden_values),
        )
        available_tools = []
    steps.append(
        SequenceStep(
            step_id=f"{seq_id}-goal",
            user_request=goal_request,
            available_tools=available_tools,
            expected_memory_reads=required_ids,
            outcome_checks=[goal_check],
            memory_probes=probes,
            distractor_memories=distractors,
            superseded_memory_ids=superseded,
        )
    )

    return BenchmarkSequence(
        sequence_id=seq_id,
        title=f"{project.name}: reconcile {facts_per_task} decisions",
        domain=world.domain,
        goal=project.goal,
        steps=steps,
    )


def _validate(
    world: EnterpriseWorld, project: Project, *, facts_per_task: int, n_tasks: int
) -> None:
    if not world.personas:
        raise ValueError(f"world {world.world_id!r} has no personas to attribute facts to")
    if not 1 <= facts_per_task <= len(_SUBJECTS):
        raise ValueError(f"facts_per_task must be in 1..{len(_SUBJECTS)}, got {facts_per_task}")
    if n_tasks < 1:
        raise ValueError(f"n_tasks must be >= 1, got {n_tasks}")
    if project.world_id != world.world_id:
        raise ValueError(
            f"project.world_id {project.world_id!r} != world.world_id {world.world_id!r}"
        )


def materialize_world(
    world: EnterpriseWorld,
    project: Project,
    *,
    n_tasks: int = 2,
    facts_per_task: int = 3,
    seed: int | None = None,
    tool_requiring: bool = False,
) -> list[BenchmarkSequence]:
    """Materialise ``n_tasks`` INDEPENDENT memory-dependent sequences from a world.

    Deterministic: the same (world, project, args, seed) yields byte-identical
    sequences. ``seed`` defaults to the world's seed. Each sequence is memory-
    dependent by construction and clears ``memory_necessity_gate``. ``tool_requiring``
    (mem-31vl) makes the goal demand a tool call carrying the current value instead of
    a text answer, so retrieval quality is load-bearing through the action."""
    _validate(world, project, facts_per_task=facts_per_task, n_tasks=n_tasks)
    base_seed = world.seed if seed is None else seed
    return [
        _materialize_task(
            world,
            project,
            task_index=t,
            facts_per_task=facts_per_task,
            seed=base_seed,
            tool_requiring=tool_requiring,
        )
        for t in range(n_tasks)
    ]


def materialize_project(
    world: EnterpriseWorld,
    project: Project,
    *,
    n_tasks: int = 3,
    facts_per_task: int = 3,
    seed: int | None = None,
    drop_charter: bool = False,
    tool_requiring: bool = False,
) -> list[BenchmarkSequence]:
    """Materialise a PROJECT: ``n_tasks`` linked by a shared charter established in
    task 0 and required by EVERY task's goal — cross-task continuity, meant to run
    under ``runner.project.run_project`` (shared store). Under isolated
    ``run_sequence`` the later tasks fail (they never wrote the charter); that gap is
    the continuity signal.

    ``drop_charter`` omits the establishing step: a missing-context (Recovery)
    variant where the charter is required but never written, so even the oracle pool
    lacks it. Recovery is a dataset annotation — the ScriptedAgent cannot re-derive
    missing memory, so the metric is for real agents under test."""
    _validate(world, project, facts_per_task=facts_per_task, n_tasks=n_tasks)
    base_seed = world.seed if seed is None else seed
    charter_id = opaque_memory_id(world.world_id, "charter")
    charter_content = _fact(
        "the project charter decision",
        "freeze scope at the phase-3 milestone",
        world.personas[0],
        None,
    )
    charter = (charter_id, charter_content)
    return [
        _materialize_task(
            world,
            project,
            task_index=t,
            facts_per_task=facts_per_task,
            seed=base_seed,
            charter=charter,
            establish_charter=(t == 0 and not drop_charter),
            tool_requiring=tool_requiring,
        )
        for t in range(n_tasks)
    ]
