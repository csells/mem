"""Shared scaffolding for the tool-requiring real-agent tests.

``test_toolreq_realagent`` (none/oracle/ours) and ``test_toolreq_builtin`` (the builtin arm) test
two grids over the SAME frozen-corpus shape, and each had grown its own copy of it. The copies had
already diverged in surface text, so the two grids read as if they shared a world while being
tested against different ones — and ours-vs-builtin is a comparison ACROSS those grids, which is
exactly the claim a divergent fixture undermines.

A plain module rather than a conftest, matching ``tests.helpers`` / ``tests.paths``: these are
factories a test calls WITH arguments (``toolreq_seq("dup", current="AAA-CUR")``), not injected
fixtures, and a conftest would force a factory-fixture indirection this suite uses nowhere.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from membench.runner.toolreq_realagent import ToolReqRealAgentTask, load_corpus_with_sequences
from membench.schemas.sequence import (
    BenchmarkSequence,
    ExpectedAction,
    OutcomeCheck,
    SequenceStep,
)

# The authored values the adapter opaquifies. Realistic on purpose: a real agent could GUESS these,
# which is why the adapter substitutes opaque tokens for the ones that score.
CURRENT = "30 days"
STALE = "90 days"

# The claude binary a hermetic PAID-path test pretends to have measured on. Never resolved off this
# machine: the suite must not key an identity on whichever CLI happens to be installed, and CI is a
# bare ubuntu-latest with no claude at all.
STUB_CLI_VERSION = "2.1.210"


def toolreq_seq(
    seq_id: str = "w-t0", *, current: str = CURRENT, stale: str = STALE
) -> BenchmarkSequence:
    """A minimal tool-requiring sequence: a v1->v2 superseded retention chain plus a goal whose
    ``apply_config`` action requires the current value and forbids the stale one. Mirrors the frozen
    ``fixtures/worlds-tool`` shape without depending on the (untracked) generated corpus.

    ``current``/``stale`` are parameters rather than constants so a test can express a REGENERATED
    corpus: the same sequence ids over different authored values, hence a disjoint opaque-token
    space — the shape the regenerated-corpus cache defect takes.
    """
    return BenchmarkSequence(
        sequence_id=seq_id,
        title=f"{seq_id} initiative: reconcile retention",
        domain="data-infrastructure",
        goal="Deliver the current initiative.",
        steps=[
            SequenceStep(
                step_id=f"{seq_id}-s0",
                user_request="Record the current value of the data retention window.",
                expected_memory_writes={
                    "m-v1": f"the data retention window is {stale} — by A. Ree in #chat"
                },
            ),
            SequenceStep(
                step_id=f"{seq_id}-s1",
                user_request="Record the current value of the data retention window.",
                expected_memory_writes={
                    "m-v2": f"the data retention window is {current} — by B. Cee in #meeting"
                },
                superseded_memory_ids=["m-v1"],
            ),
            SequenceStep(
                step_id=f"{seq_id}-goal",
                user_request=(
                    "Deliver the current initiative. Using the tool `apply_config`, apply "
                    "the current value of: the data retention window."
                ),
                available_tools=["apply_config"],
                expected_memory_reads=["m-v2"],
                outcome_checks=[
                    OutcomeCheck(
                        check_id=f"{seq_id}-goal-check",
                        description="goal requires apply_config carrying the current value",
                        requires_memory=["m-v2"],
                        requires_action=[
                            ExpectedAction(
                                tool="apply_config",
                                arg_values=[current],
                                forbidden_values=[stale],
                            )
                        ],
                    )
                ],
            ),
        ],
    )


def corpus(
    tmp_path: Path, *work_ids: str
) -> tuple[list[BenchmarkSequence], list[ToolReqRealAgentTask]]:
    """Seed a frozen corpus of ``work_ids`` under ``tmp_path/corpus`` and load it back through
    ``load_corpus_with_sequences`` — rather than calling ``adapt_sequence`` directly — so the
    on-disk ``sequences.json`` round-trip is part of what every driver test exercises. Returns the
    sequences alongside their adapted tasks, the pairing the ``ours`` seeder needs."""
    corpus_dir = tmp_path / "corpus"
    (corpus_dir / "0").mkdir(parents=True)
    (corpus_dir / "0" / "sequences.json").write_text(
        json.dumps([toolreq_seq(work_id).model_dump() for work_id in work_ids]), encoding="utf-8"
    )
    return load_corpus_with_sequences(corpus_dir)


def corpus_one(
    tmp_path: Path, work_id: str = "w-0"
) -> tuple[list[BenchmarkSequence], list[ToolReqRealAgentTask]]:
    """A one-task frozen corpus — the scaffold most driver tests need."""
    return corpus(tmp_path, work_id)


def noop_cli_runner(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """A ``claude -p`` stand-in that spawns nothing and says nothing (an empty stream parses to no
    tool calls and no result) — for tests that care only about WHICH invocations were recorded."""
    return subprocess.CompletedProcess(list(argv), returncode=0, stdout="", stderr="")


# A SECOND subject for the multi-value shape (mem-9q8dg follow-up). One-value tasks are the only
# thing the generator authors today, and every twin test ran on them — so the twin's block-building
# at >1 value, where an ordering of the values first exists, was unexercised.
SECOND_CURRENT = "hourly"
SECOND_STALE = "weekly"


def toolreq_seq_two_subjects(seq_id: str = "w-mv3") -> BenchmarkSequence:
    """A tool-requiring sequence whose goal action scores TWO current values (each with its own
    superseded predecessor), and whose subject list in the request is authored in the OPPOSITE
    order to ``arg_values``.

    That inversion is the point: it is the case where emitting the twin's context block in the
    action's authored order would imply a positional pairing to the request's subject list that is
    simply wrong. The single-value fixture cannot express it — with one value every order is the
    same order.
    """
    subjects = ("the data retention window", "the backup cadence")
    return BenchmarkSequence(
        sequence_id=seq_id,
        title=f"{seq_id} initiative: reconcile retention and cadence",
        domain="data-infrastructure",
        goal="Deliver the current initiative.",
        steps=[
            SequenceStep(
                step_id=f"{seq_id}-s0",
                user_request=f"Record the current value of {subjects[0]}.",
                expected_memory_writes={"m-a1": f"{subjects[0]} is {STALE} — by A. Ree in #chat"},
            ),
            SequenceStep(
                step_id=f"{seq_id}-s1",
                user_request=f"Record the current value of {subjects[0]}.",
                expected_memory_writes={
                    "m-a2": f"{subjects[0]} is {CURRENT} — by B. Cee in #meeting"
                },
                superseded_memory_ids=["m-a1"],
            ),
            SequenceStep(
                step_id=f"{seq_id}-s2",
                user_request=f"Record the current value of {subjects[1]}.",
                expected_memory_writes={
                    "m-b1": f"{subjects[1]} is {SECOND_STALE} — by A. Ree in #chat"
                },
            ),
            SequenceStep(
                step_id=f"{seq_id}-s3",
                user_request=f"Record the current value of {subjects[1]}.",
                expected_memory_writes={
                    "m-b2": f"{subjects[1]} is {SECOND_CURRENT} — by B. Cee in #meeting"
                },
                superseded_memory_ids=["m-b1"],
            ),
            SequenceStep(
                step_id=f"{seq_id}-goal",
                user_request=(
                    "Deliver the current initiative. Using the tool `apply_config`, apply "
                    # subjects reversed relative to arg_values below, on purpose
                    f"the current value of: {subjects[1]}, {subjects[0]}."
                ),
                available_tools=["apply_config"],
                expected_memory_reads=["m-a2", "m-b2"],
                outcome_checks=[
                    OutcomeCheck(
                        check_id=f"{seq_id}-goal-check",
                        description="goal requires apply_config carrying both current values",
                        requires_memory=["m-a2", "m-b2"],
                        requires_action=[
                            ExpectedAction(
                                tool="apply_config",
                                arg_values=[CURRENT, SECOND_CURRENT],
                                forbidden_values=[STALE, SECOND_STALE],
                            )
                        ],
                    )
                ],
            ),
        ],
    )


def multi_value_corpus(
    tmp_path: Path, seq_id: str = "w-mv3"
) -> tuple[list[BenchmarkSequence], list[ToolReqRealAgentTask]]:
    """Seed and load a one-sequence frozen corpus whose single task scores TWO current values."""
    corpus_dir = tmp_path / "corpus"
    (corpus_dir / "0").mkdir(parents=True)
    (corpus_dir / "0" / "sequences.json").write_text(
        json.dumps([toolreq_seq_two_subjects(seq_id).model_dump()]), encoding="utf-8"
    )
    return load_corpus_with_sequences(corpus_dir)


def corpus_scoreable(
    tmp_path: Path,
) -> tuple[list[BenchmarkSequence], list[ToolReqRealAgentTask]]:
    """The smallest frozen corpus a PAID entry will accept: two work_ids, so each arm carries two
    tasks and clears ``MIN_TASKS_PER_ARM``.

    ``corpus_one`` cannot be used to drive a paid entrypoint any more. It seeds one work_id, so
    every arm holds a single task and the geometry guard refuses the fire before any other guard
    is reached — a test aimed at a different refusal would then assert its own message against the
    geometry message and fail for a reason that has nothing to do with what it is testing."""
    return corpus(tmp_path, "w-0", "w-1")
