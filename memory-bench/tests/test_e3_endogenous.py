"""E3b — the endogenous read/write seam: does the agent CHOOSE to use the tool?

E3a graded a FORCED loop: the harness retrieved, the harness recorded, and ``closure_rate``
measured whether the loop closed. That is the right ceiling to establish first, and it answers a
different question from the one beads#5877 is about. Once the harness performs the read, a
``closure_rate`` of 1.0 says the plumbing works, not that an agent would ever reach for it —
arXiv 2607.20972 measured voluntary memory use at approximately zero against a pre-seeded store,
which is a result you cannot even observe on a forced loop.

So these tests pin the seam where the choice becomes visible, and every one of them is about
keeping the SUBJECT out of its own measurement:

* the counter reads observed ``tool_use`` argv, never the agent's account of what it did;
* ``available_ids`` on an endogenous-read step comes from the same observed argv;
* an agent that never calls the tool is recorded as exactly that, distinct from a memory failure;
* the read seam refuses an unbounded enumerate, which would let a leg reach a value without
  having recorded where it put it;
* the closure driver refuses ``--endogenous-read`` on any arm that resolves from ``requested_ids``.
"""

from __future__ import annotations

import pytest

from membench.metrics.scorers import content_recovered_write_ids, score_efficiency
from membench.report.e3_closure import ENDOGENOUS_READ_ARMS, _main
from membench.runner.agent import AgentStepResult
from membench.runner.metrics import compute_metrics
from membench.runner.tool_surface import (
    MEMORY_READ_VERBS,
    MEMORY_WRITE_VERBS,
    MemoryToolError,
    assert_recall_is_bounded,
    enumerate_invocations,
    memory_invocations_in_command,
    observed_requested_ids,
)
from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation
from membench.schemas.sequence import OutcomeCheck, SequenceStep
from membench.schemas.trace import ToolCall


def bash(command: str, output: str | None = None) -> ToolCall:
    """One observed Bash tool_use — the shape a real memory call arrives in."""
    return ToolCall(name="Bash", arguments={"command": command}, result=output)


def step(**overrides: object) -> SequenceStep:
    """A goal step that offers the memory tool (Bash) and requires one check."""
    fields: dict[str, object] = {
        "step_id": "s1",
        "user_request": "apply the current value",
        "available_tools": ["Bash", "Write"],
        "outcome_checks": [OutcomeCheck(check_id="c1", description="d")],
    }
    fields.update(overrides)
    return SequenceStep(**fields)  # type: ignore[arg-type]


def result(tool_calls: list[ToolCall], **overrides: object) -> AgentStepResult:
    fields: dict[str, object] = {
        "final_answer": "done",
        "check_results": {"c1": True},
        "writes_performed": {},
        "tool_calls": tool_calls,
    }
    fields.update(overrides)
    return AgentStepResult(**fields)  # type: ignore[arg-type]


def _harness_write_event(written_id: str) -> MemoryEvent:
    """One harness-performed write event — the id-exact path's input."""
    return MemoryEvent(
        event_id="e1",
        trial_id="t",
        session_id="sess",
        step_id="s1",
        timestamp="2026-01-01T00:00:00Z",
        concrete_tool="harness",
        normalized_operation=MemoryOperation.WRITE,
        backend=MemoryBackend.FILESYSTEM,
        written_ids=[written_id],
    )


def test_tool_events_reach_trial() -> None:
    """An agent that calls the tool three times yields three endogenous calls in the bundle.

    The pre-E3b bundle built its memory counts from the harness retrieve alone, so this read 0
    however many times the agent reached for the tool — the measured behaviour was invisible in
    the very metric that was supposed to carry it."""
    calls = [
        bash("bd recall auth-key"),
        bash("bd memories rotation"),
        bash(
            "bd remember 'rotate on the 1st' --key rotation-plan",
            "Remembered [rotation-plan]: rotate on the 1st",
        ),
    ]
    bundle = compute_metrics(step(), result(calls), None, [], reads_enabled=False)
    assert bundle.efficiency.endogenous_memory_tool_calls == 3
    assert bundle.efficiency.endogenous_memory_reads == 2
    assert bundle.efficiency.endogenous_memory_writes == 1
    # The harness performed none of these, so its own counter must stay clean: summing the two
    # would make an arm that retrieves FOR the agent look like an agent that chose to.
    assert bundle.efficiency.memory_tool_calls == 0
    assert bundle.efficiency.non_memory_tool_calls == 0


def test_read_and_write_verbs_are_disjoint() -> None:
    """A verb cannot count as both halves of the choice, and a deletion is neither."""
    assert not set(MEMORY_READ_VERBS) & set(MEMORY_WRITE_VERBS)
    assert "forget" not in set(MEMORY_READ_VERBS) | set(MEMORY_WRITE_VERBS)


def test_available_ids_from_harness_not_agent() -> None:
    """``available_ids`` on an endogenous-read step derives from harness-observed tool events.

    The agent populates ``writes_performed`` and ``final_answer`` itself. If either fed
    ``available_ids``, the subject would be grading its own read and every synthesis number
    downstream would inherit the self-report."""
    calls = [bash("bd recall auth-key"), bash("bd recall rotation-plan")]
    assert observed_requested_ids(calls) == ["auth-key", "rotation-plan"]
    checks = [OutcomeCheck(check_id="c1", description="d", requires_memory=["auth-key"])]
    bundle = compute_metrics(
        step(read_is_endogenous=True, outcome_checks=checks),
        result(calls, writes_performed={"fabricated-id": "not asked for"}),
        None,
        [],
        reads_enabled=False,
    )
    # The id the agent actually asked for supports the check; the id it merely claimed does not
    # appear anywhere in the graded inputs.
    assert bundle.synthesis.supporting_memories_required == 1
    assert bundle.synthesis.supporting_memories_used == 1

    # And with no observed call, nothing is available: an endogenous read that did not happen
    # scores as absent rather than falling back to the harness's answer-key ids.
    empty = compute_metrics(
        step(read_is_endogenous=True, outcome_checks=checks),
        result([], writes_performed={"auth-key": "self-reported"}),
        None,
        [],
        reads_enabled=False,
    )
    assert empty.synthesis.supporting_memories_required == 1
    assert empty.synthesis.supporting_memories_used == 0


def test_recall_is_bounded() -> None:
    """A bare list-all is refused at the read seam; a keyed recall and a bounded search are not.

    An unbounded enumerate hands a later leg every stored value, so it could close the loop
    without ever having recorded where it put anything, and ``closure_rate`` would saturate for a
    reason that is not memory use."""
    assert enumerate_invocations([bash("bd memories")])
    assert not enumerate_invocations([bash("bd memories rotation")])
    assert not enumerate_invocations([bash("bd recall auth-key")])

    assert_recall_is_bounded([bash("bd recall auth-key"), bash("bd memories rotation")])
    with pytest.raises(MemoryToolError, match="unbounded memory enumeration"):
        assert_recall_is_bounded([bash("bd memories")])
    # Reached through a shell wrapper it is the same call and must not slip the guard.
    with pytest.raises(MemoryToolError, match="unbounded memory enumeration"):
        assert_recall_is_bounded([bash("cd /tmp && bd --json memories")])

    # A keyed recall names exactly one memory, so it needs no top_k to be bounded.
    [keyed] = memory_invocations_in_command("bd recall auth-key")
    assert keyed.requested_ids == ("auth-key",)
    # A search operand is a QUERY, not an id: crediting it as one would score the agent as having
    # asked for whatever the search happened to return.
    [search] = memory_invocations_in_command("bd memories rotation")
    assert search.requested_ids == ()

    # And the guard is live where it matters: an endogenous-read step carrying an enumerate must
    # fail the run rather than quietly score a saturated read.
    with pytest.raises(MemoryToolError):
        compute_metrics(
            step(read_is_endogenous=True),
            result([bash("bd memories")]),
            None,
            [],
            reads_enabled=False,
        )


def test_the_seams_see_a_quoted_capture() -> None:
    """Every E3b seam is pinned against the QUOTED spelling, not only the bare one.

    5e45493's parser copied characters through a double-quoted run, so ``v="$(bd recall k)"``
    reached all three seams as no call at all: the endogenous counter read 0, ``available_ids``
    came back empty, and a quoted ``bd memories`` walked straight past the bounded-read guard to
    hand a later leg the whole store. Capturing a recall into a variable and quoting it is how an
    agent actually writes this, so these fixtures live here as well as in the tool-surface table -
    E3b's guards must not be green only for the spelling that bead happened to enumerate."""
    quoted = [
        bash('v="$(bd recall auth-key)"'),
        bash(
            "echo \"$(bd remember 'rotate on the 1st' --key rotation-plan)\"",
            "Remembered [rotation-plan]: rotate on the 1st",
        ),
    ]
    bundle = compute_metrics(step(), result(quoted), None, [], reads_enabled=False)
    assert bundle.efficiency.endogenous_memory_reads == 1
    assert bundle.efficiency.endogenous_memory_writes == 1
    assert bundle.efficiency.tool_not_called is False

    assert observed_requested_ids(quoted) == ["auth-key"]

    # The AC4 hazard, quoted: this is the form that reached the whole store unguarded.
    with pytest.raises(MemoryToolError, match="unbounded memory enumeration"):
        assert_recall_is_bounded([bash('echo "$(bd memories)"')])
    # And the over-count direction stays refused: a single-quoted run is literal text.
    assert enumerate_invocations([bash("echo '$(bd memories)'")]) == []


def test_tool_call_counter() -> None:
    """An agent that answers in prose and never calls the tool is recorded as ``tool_not_called``.

    That is not a memory failure and must not be scored as one: on an endogenous step it is the
    primary observation (arXiv 2607.20972's near-zero voluntary use is exactly this reading)."""
    silent = compute_metrics(step(), result([]), None, [], reads_enabled=False)
    assert silent.efficiency.tool_not_called is True
    assert silent.efficiency.endogenous_memory_tool_calls == 0

    called = compute_metrics(step(), result([bash("bd recall k")]), None, [], reads_enabled=False)
    assert called.efficiency.tool_not_called is False

    # Non-memory tool work is not a memory call: an agent that only ran `ls` still did not choose
    # to consult memory.
    other = compute_metrics(
        step(),
        result([ToolCall(name="Bash", arguments={"command": "ls -la"})]),
        None,
        [],
        reads_enabled=False,
    )
    assert other.efficiency.tool_not_called is True
    assert other.efficiency.non_memory_tool_calls == 1

    # A step that offers no Bash cannot receive a memory call, so its silence says nothing about
    # the agent and must not read as a miss.
    no_tool = compute_metrics(
        step(available_tools=["Write"]), result([]), None, [], reads_enabled=False
    )
    assert no_tool.efficiency.tool_not_called is False


def test_score_efficiency_keeps_the_two_channels_apart() -> None:
    """Harness-performed and agent-chosen memory calls never merge into one number."""
    eff = score_efficiency(
        input_tokens=1,
        output_tokens=2,
        non_memory_tool_calls=0,
        memory_events=[],
        endogenous_reads=2,
        endogenous_writes=1,
        memory_tool_offered=True,
    )
    assert eff.memory_tool_calls == 0
    assert eff.endogenous_memory_tool_calls == 3
    assert eff.tool_not_called is False


def test_endogenous_flags_default_false() -> None:
    """Every existing fixture keeps E3a's forced-loop semantics untouched."""
    plain = SequenceStep(step_id="s", user_request="r")
    assert plain.read_is_endogenous is False
    assert plain.write_is_endogenous is False


def test_endogenous_read_halts_on_a_cued_arm() -> None:
    """``--endogenous-read`` is refused on any arm that resolves strictly from requested_ids.

    Such an arm returns the fixture's own answer-key ids whatever the agent asked for, so the
    read rate would measure the cue. The refusal is the point: falling back to the cued path is
    how a fabricated endogenous number would enter the record."""
    for arm in ("oracle", "filesystem", "consolidating", "retention_scheduled", "openwiki"):
        assert arm not in ENDOGENOUS_READ_ARMS
        with pytest.raises(SystemExit) as excinfo:
            _main(["--seeds", "20", "--arm", arm, "--endogenous-read"])
        assert excinfo.value.code == 2
    assert "lexical" in ENDOGENOUS_READ_ARMS


def test_endogenous_write_is_graded_on_content_not_id() -> None:
    """A right fact under a self-chosen key is a HIT; a right key over a wrong fact is not.

    The id-namespace half of this bead. The read side is keyed on ids, so an agent that picks its
    own write id produces an id no harness-authored id set can name — grading the write by id
    equality therefore scores ``write_hit_rate`` as id-naming discipline, and an agent that stored
    exactly the required literal scores zero for choosing a different key. Both directions are
    pinned because only one of them is a loosening: the second asserts the content grade did not
    become a free pass for anything written under the expected name."""
    expected = {"rotation-plan": "rotate on the 1st"}
    endogenous = step(write_is_endogenous=True, expected_memory_writes=expected)

    own_key = compute_metrics(
        endogenous,
        result(
            [
                bash(
                    "bd remember 'rotate on the 1st' --key my-own-note",
                    "Remembered [my-own-note]: rotate on the 1st",
                )
            ]
        ),
        None,
        [],
        reads_enabled=False,
    )
    assert own_key.retention.write_hit_rate == 1.0
    assert own_key.retention.expected_memory_written is True

    # Harness-named key, wrong content: the key is excluded from the graded text, so naming the
    # id right earns nothing.
    right_id_wrong_fact = compute_metrics(
        endogenous,
        result(
            [
                bash(
                    "bd remember 'rotate on the 15th' --key rotation-plan",
                    "Remembered [rotation-plan]: rotate on the 15th",
                )
            ]
        ),
        None,
        [],
        reads_enabled=False,
    )
    assert right_id_wrong_fact.retention.write_hit_rate == 0.0
    assert right_id_wrong_fact.retention.expected_memory_written is False
    assert right_id_wrong_fact.retention.write_miss_rate == 1.0

    # This is valid content with an implicit key, but the absent result cannot prove storage.
    unacknowledged = compute_metrics(
        endogenous,
        result([bash("bd remember 'rotate on the 1st'")]),
        None,
        [],
        reads_enabled=False,
    )
    assert unacknowledged.retention.write_hit_rate == 0.0

    silent = compute_metrics(endogenous, result([]), None, [], reads_enabled=False)
    assert silent.retention.write_hit_rate == 0.0


def test_id_exact_write_grade_is_untouched_off_the_endogenous_path() -> None:
    """The forced-loop arms keep id equality: a self-chosen key is a MISS when the flag is off.

    factorial_behavioral / synthetic_arms / memory_necessity_gate all grade writes the harness
    performed, and their expectations move the moment the content path leaks onto a default step.
    """
    expected = {"rotation-plan": "rotate on the 1st"}
    forced = step(expected_memory_writes=expected)
    calls = [
        bash(
            "bd remember 'rotate on the 1st' --key my-own-note",
            "Remembered [my-own-note]: rotate on the 1st",
        )
    ]

    hit = compute_metrics(
        forced,
        result(calls),
        None,
        [_harness_write_event("rotation-plan")],
        reads_enabled=False,
    )
    assert hit.retention.write_hit_rate == 1.0

    # Nothing recorded: observed argv is NOT consulted off the endogenous path, so the agent's own
    # store of the literal does not rescue the score.
    miss = compute_metrics(forced, result(calls), None, [], reads_enabled=False)
    assert miss.retention.write_hit_rate == 0.0


def test_empty_authored_literal_is_never_a_free_write() -> None:
    """An empty literal must never be a hit: ``states_value`` matches it at any boundary."""
    assert content_recovered_write_ids("rotate on the 1st!", {"blank": ""}) == []
    assert content_recovered_write_ids("rotate on the 1st", {"k": "rotate on the 1st"}) == ["k"]
    # Word-boundary anchored, like every other authored-literal match in scorers.py.
    assert content_recovered_write_ids("checkout_v2 shipped", {"k": "v2"}) == []
