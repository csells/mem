"""E3a — the write→later-read CLOSURE world: a seed-reproducible A/B sequence.

The shape is three steps and one question: *did what session A wrote reach session
B?*

- ``s0-establish``  (A1) writes a v1 pin for a service.
- ``s1-supersede``  (A2) writes a DISTINCT v2 id and marks v1 superseded (the
  runner's oracle pool rejects same-id rewrites, so supersession is v1→v2 ids).
- ``s2-apply``      (B)  must call a tool whose argument carries the v2 literal and
  NOT the v1 literal, and depends on the v2 memory id being available.

That makes B's reward strictly conditional on the earlier write surviving into B:
with no memory the required id is unavailable and the check short-circuits; with
memory that surfaces BOTH versions the v1 literal rides into the tool argument and
trips ``ExpectedAction.forbidden_values``. Distractor memories are seeded at B so a
read-everything arm pays precision, and the v1 id is authored as a forbidden WRITE
at B so re-persisting the stale version is scored (``forbidden_write_rate``).

Unguessability is the leak proof and it is MECHANICAL, not a condition leg: the v2
literal is a seeded high-entropy token that must appear in no step's
``user_request`` / ``available_tools`` / ``environment_state``. ``--check-unguessable``
asserts exactly that (see ``assert_unguessable``); the NO_MEMORY leg cannot prove it,
because ``outcome_check_passes`` short-circuits on the missing required id before the
answer text is ever consulted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass

from membench.schemas.sequence import (
    BenchmarkSequence,
    ExpectedAction,
    OutcomeCheck,
    SequenceStep,
)

GENERATOR_VERSION = "e3-closure-world.v1"

# The service surface the world is authored over. The seed picks one; nothing about
# the choice is secret (it appears in the prompts) — only the PIN literals are.
_SERVICES: tuple[str, ...] = (
    "checkout",
    "ledger",
    "ingest",
    "router",
    "indexer",
)

_DISTRACTOR_SUBJECTS: tuple[str, ...] = ("cache", "queue", "scheduler")


def _literal(seed: int, tag: str) -> str:
    """A high-entropy, seed-reproducible pin literal.

    Derived by digesting ``(seed, tag)`` so the value is byte-stable for a seed and
    cannot be guessed from any prompt surface — the property ``assert_unguessable``
    checks mechanically."""
    digest = hashlib.sha256(f"{GENERATOR_VERSION}:{seed}:{tag}".encode()).hexdigest()
    return f"PIN-{digest[:12]}"


@dataclass(frozen=True)
class ClosureWorld:
    """The authored ground truth for one seed, alongside its sequence."""

    seed: int
    service: str
    v1_id: str
    v2_id: str
    v1_literal: str
    v2_literal: str
    apply_step_id: str
    sequence: BenchmarkSequence


def generate_closure_world(seed: int) -> ClosureWorld:
    """Emit the deterministic E3a closure world for ``seed`` (same seed ⇒ same bytes)."""
    service = _SERVICES[seed % len(_SERVICES)]
    v1_id = f"deploy-pin-v1-{service}-s{seed}"
    v2_id = f"deploy-pin-v2-{service}-s{seed}"
    v1_literal = _literal(seed, "v1")
    v2_literal = _literal(seed, "v2")
    apply_step_id = "s2-apply"

    distractors = {
        f"note-{subject}-{service}-s{seed}": (
            f"unrelated {subject} note for {service}: no deploy pin here"
        )
        for subject in _DISTRACTOR_SUBJECTS
    }

    steps = [
        SequenceStep(
            step_id="s0-establish",
            user_request=f"Session A1: record the current deploy pin for the {service} service.",
            expected_memory_writes={v1_id: f"{service} deploy pin is {v1_literal}"},
        ),
        SequenceStep(
            step_id="s1-supersede",
            user_request=(
                f"Session A2: the {service} deploy pin was rotated. Record the new pin "
                "and treat the previous one as stale."
            ),
            expected_memory_writes={v2_id: f"{service} deploy pin is now {v2_literal}"},
            superseded_memory_ids=[v1_id],
        ),
        SequenceStep(
            step_id=apply_step_id,
            user_request=(
                f"Session B: deploy the {service} service using the pin recorded earlier. "
                "The pin is not in this request; recall it."
            ),
            available_tools=["deploy"],
            expected_memory_reads=[v2_id],
            distractor_memories=distractors,
            superseded_memory_ids=[v1_id],
            forbidden_memory_writes=[v1_id],
            outcome_checks=[
                OutcomeCheck(
                    check_id="deploys-with-current-pin",
                    description=(
                        "the deploy call carries the current (v2) pin and not the "
                        "superseded (v1) pin"
                    ),
                    requires_memory=[v2_id],
                    requires_action=[
                        ExpectedAction(
                            tool="deploy",
                            arg_values=[v2_literal],
                            forbidden_values=[v1_literal],
                        )
                    ],
                )
            ],
        ),
    ]

    sequence = BenchmarkSequence(
        sequence_id=f"e3-closure-{service}-s{seed}",
        title=f"E3a write-to-later-read closure: {service}",
        domain="memory-closure",
        goal=f"deploy {service} with the pin established in an earlier session",
        steps=steps,
    )
    return ClosureWorld(
        seed=seed,
        service=service,
        v1_id=v1_id,
        v2_id=v2_id,
        v1_literal=v1_literal,
        v2_literal=v2_literal,
        apply_step_id=apply_step_id,
        sequence=sequence,
    )


def _prompt_surfaces(step: SequenceStep) -> dict[str, str]:
    """Every surface the agent can read WITHOUT memory, as text."""
    return {
        "user_request": step.user_request,
        "available_tools": " ".join(step.available_tools),
        "environment_state": json.dumps(step.environment_state, sort_keys=True),
    }


def assert_unguessable(world: ClosureWorld) -> None:
    """RAISE if the v2 literal is reachable from any memory-free prompt surface.

    This is the leak proof for E3a. It is a substring check over the B step's
    ``user_request`` / ``available_tools`` / ``environment_state`` (and, for good
    measure, every other step's — an A-step leak would be just as fatal), because a
    condition leg cannot prove it: NO_MEMORY fails the check on the missing required
    id before the answer is graded at all."""
    for step in world.sequence.steps:
        for surface, text in _prompt_surfaces(step).items():
            if world.v2_literal in text:
                raise ValueError(
                    f"leak: v2 literal {world.v2_literal!r} appears in step "
                    f"{step.step_id!r} {surface}; B could answer without reading memory"
                )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E3a closure-world generator")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--check-unguessable",
        action="store_true",
        help="assert the v2 literal appears in no memory-free prompt surface",
    )
    args = parser.parse_args(argv)

    world = generate_closure_world(args.seed)
    if args.check_unguessable:
        assert_unguessable(world)
    summary = {
        "generator_version": GENERATOR_VERSION,
        "seed": world.seed,
        "sequence_id": world.sequence.sequence_id,
        "service": world.service,
        "v1_id": world.v1_id,
        "v2_id": world.v2_id,
        "apply_step_id": world.apply_step_id,
        "unguessable_checked": bool(args.check_unguessable),
        "n_steps": len(world.sequence.steps),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(_main())
