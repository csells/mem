"""The agent interface + a deterministic reference agent for the skeleton.

The real agent-under-test is Claude Code / Opus / Sonnet / Haiku, run on our Claude
account (OAuth subscription) through Harbor (plan §A, DIV-1) — that path is the
`environment/` + `task.toml` emitted by the Harbor adapter and is exercised by
`harbor run`, not in-process.

`ScriptedAgent` is the in-process reference agent that makes the skeleton runnable
and its pipeline testable WITHOUT Docker or any paid API: its outcome is a
deterministic function of which required memory the harness surfaced to it. It is
test/reference infrastructure, not a stand-in for production agent logic.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from membench.metrics.scorers import outcome_check_passes
from membench.runtime import StepContext
from membench.schemas.sequence import SequenceStep
from membench.schemas.trace import ToolCall, TraceMessage


@dataclass
class AgentStepResult:
    final_answer: str
    check_results: dict[str, bool]  # check_id → passed
    writes_performed: dict[str, str]  # memory_id → content the agent chose to persist
    messages: list[TraceMessage] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    turns: int = 1
    # The raw agent transcript stream (Claude Code stream-json), kept verbatim so the
    # §12.6 action-impact path can derive `AttemptStep`s from it via
    # `bbon.extract.steps_from_stream`. Empty for the `ScriptedAgent` (no real stream —
    # an honest absence, never fabricated); populated by `HeadlessClaudeAgent`.
    raw_stream: str = ""


@runtime_checkable
class Agent(Protocol):
    agent_config_id: str

    def run_step(
        self,
        step: SequenceStep,
        available_memory: dict[str, str],
        ctx: StepContext,
    ) -> AgentStepResult: ...


class ScriptedAgent:
    """Deterministic reference agent.

    A step's outcome check is graded by `outcome_check_passes`: every memory id the
    check requires must be present in `available_memory` (what the harness surfaced
    this step), and the agent's stated answer must not state a forbidden
    (superseded) value. The reference agent "states" every memory it recalled — the
    surfaced contents ARE its answer material — so surfacing a stale value fails a
    check that forbids it (reward-bearing staleness, mem-z3gi). When a check
    `requires_action` (mem-31vl), the agent also "uses" that recalled content: it
    invokes the step's tool with the recalled text as the argument, so a stale value
    riding into the tool argument fails the action just as it would the answer.
    Checks that require no memory and forbid nothing pass statelessly. The agent
    persists the step's `expected_memory_writes` — its (skeleton) write decision is
    write-all; a learned write policy replaces this later.
    """

    def __init__(self, agent_config_id: str = "scripted-ref") -> None:
        self.agent_config_id = agent_config_id

    def run_step(
        self,
        step: SequenceStep,
        available_memory: dict[str, str],
        ctx: StepContext,
    ) -> AgentStepResult:
        have = set(available_memory)
        recalled_text = "\n".join(available_memory.values())
        # The reference agent "uses" what it recalled: on a step whose checks require
        # a tool action it invokes each available tool with the recalled content as
        # the argument (mem-31vl). An arm that surfaced clean current-only memory
        # drives a clean tool argument (passes); one that surfaced a stale version
        # drives a stale-contaminated argument (fails); empty recall -> empty argument
        # -> the required current value is absent (fails). Non-action steps keep the
        # empty-arg call, so efficiency accounting is unchanged.
        requires_action = any(check.requires_action for check in step.outcome_checks)
        tool_calls = [
            ToolCall(
                name=t,
                arguments={"value": recalled_text} if requires_action else {},
                latency_ms=ctx.clock.latency_ms(),
            )
            for t in step.available_tools
        ]
        check_results: dict[str, bool] = {}
        for check in step.outcome_checks:
            check_results[check.check_id] = outcome_check_passes(
                check,
                available_ids=have,
                stated_text=recalled_text,
                tool_calls=tool_calls,
            )

        messages = [
            TraceMessage(role="user", content=step.user_request),
            TraceMessage(
                role="assistant",
                content=f"step {step.step_id}: used {len(have)} memories",
            ),
        ]
        passed = sum(check_results.values())
        final_answer = f"{passed}/{len(check_results)} checks satisfied"
        # Deterministic token accounting from payload sizes (no model call).
        input_tokens = len(step.user_request.split()) + sum(
            len(v.split()) for v in available_memory.values()
        )
        output_tokens = len(final_answer.split())
        return AgentStepResult(
            final_answer=final_answer,
            check_results=check_results,
            writes_performed=dict(step.expected_memory_writes),
            messages=messages,
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


class NeverWritesAgent(ScriptedAgent):
    """The closure FLOOR control: behaves like ``ScriptedAgent`` but persists nothing.

    Everything else — recall, grading, the tool call — is identical, so the only
    difference between it and the reference agent is the write. Under a write-bearing
    arm that makes it the clean floor for E3a: a later step can only read what an
    earlier step wrote, so closure must collapse to 0. It is a control, not a model of
    a real agent's write policy.
    """

    def __init__(self, agent_config_id: str = "never-writes") -> None:
        super().__init__(agent_config_id=agent_config_id)

    def run_step(
        self,
        step: SequenceStep,
        available_memory: dict[str, str],
        ctx: StepContext,
    ) -> AgentStepResult:
        result = super().run_step(step, available_memory, ctx)
        result.writes_performed = {}
        return result
