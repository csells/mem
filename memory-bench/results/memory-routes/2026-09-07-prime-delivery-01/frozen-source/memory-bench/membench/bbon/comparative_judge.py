"""Pairwise comparative judge (port of engram's `src/agents/judge/comparativeJudge.ts`).

Given a `NarrativeDiff` of two attempts, the judge picks a winner with a
confidence and a short rationale. Engram called the OpenAI chat API; that is gone.
The membench judge is headless **`claude -p`** (`ClaudeComparativeJudge`) — the
local Claude CLI is the OAuth seam, not a paid managed API, so it does not trip the
D4/D16 no-paid-API fence the single-output `grading.judge` guards. The spawn
pattern follows tom-swe's `llm-analyze.ts` and membench's own `mem_cli` seam:
injectable runner, hard timeout, typed failure that surfaces loudly.

`StubComparativeJudge` is the deterministic, offline judge every test and the whole
pipeline run on — no model, no network — exactly as `grading.judge.StubJudge` is to
the single-output judge. A real `claude -p` call happens only when an experimenter
explicitly wires in `ClaudeComparativeJudge`.

ZFC: the winner choice IS the delegated model judgment (correct — the model decides,
not a coded heuristic). This module's own code is pure plumbing: prompt assembly,
subprocess IO, JSON parsing, and structural validation.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from membench._claude_cli import first_json_object, unwrap_cli_json
from membench.bbon.models import Attempt, Judgment, NarrativeDiff, deterministic_id
from membench.judge_config import (
    IsolatedClaudeCallsite,
    IsolatedJudgeConfig,
    run_isolated_claude,
)
from membench.spawn import Runner

DEFAULT_PROMPT_VERSION = "v1"

# claude -p is local CLI inference; a comparison prompt resolves in seconds, so a
# minute-plus bound means a wedged subprocess, not slow inference.
DEFAULT_TIMEOUT_S = 90.0

# Recorded model identity when no model is pinned — the CLI's own configured default
# is used (no --model flag passed). Overridable via the env var below.
CLI_DEFAULT_MODEL = "cli-default"
ENV_MODEL = "MEMBENCH_COMPARATIVE_JUDGE_MODEL"


class ComparativeJudgeError(RuntimeError):
    """A comparative-judge invocation failed (missing binary, timeout, non-zero
    exit, or an unusable reply). The pipeline break is always surfaced, never
    degraded to a default winner."""


class ComparativeJudge(Protocol):
    """Returns a raw model reply for a built judge prompt. ``model`` is the identity
    recorded in the cache key and `Judgment` so a reply is attributable."""

    @property
    def model(self) -> str: ...

    def complete(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class StubComparativeJudge:
    """A deterministic, injectable judge — NO model, NO network. The whole pipeline
    and every test run on this. Supply exactly one of: a fixed verdict
    (``winner`` ``"A"``/``"B"`` with ``confidence``/``rationale``) or ``fn`` (a pure
    function from prompt to a raw reply string), so the full parse path is exercised."""

    winner: str | None = None
    confidence: float = 1.0
    rationale: str = "stub verdict"
    fn: Callable[[str], str] | None = None
    model: str = "stub"

    def __post_init__(self) -> None:
        if (self.winner is None) == (self.fn is None):
            raise ValueError("StubComparativeJudge needs exactly one of winner or fn")
        if self.winner is not None and self.winner not in ("A", "B"):
            raise ValueError(f"winner must be 'A' or 'B', got {self.winner!r}")

    def complete(self, prompt: str) -> str:
        if self.fn is not None:
            return self.fn(prompt)
        return json.dumps(
            {"winner": self.winner, "confidence": self.confidence, "rationale": self.rationale}
        )


@dataclass(frozen=True)
class ClaudeComparativeJudge(IsolatedClaudeCallsite):
    """A judge backed by headless ``claude -p ... --output-format json``.

    ``model`` pins the CLI model; left empty it reads ``MEMBENCH_COMPARATIVE_JUDGE_MODEL``
    and otherwise falls back to the CLI's own default (no ``--model`` flag, recorded as
    ``cli-default``). ``runner`` is injected so tests drive the parse path without
    spawning a real claude. Every failure raises `ComparativeJudgeError`.

    ``isolation`` (mem-9ld4 / mem-hv9l) is the clean-config surface the subprocess
    runs under -- load-bearing here because the NarrativeDiff content this judge
    reads is exactly the reviewable-diff shape that triggered the original graded
    hijack (mem-eacq); lazy semantics and the marker contract live on
    `IsolatedClaudeCallsite`."""

    _isolation_label = "comparative"

    model: str = ""
    timeout_s: float = DEFAULT_TIMEOUT_S
    runner: Runner = subprocess.run
    isolation: IsolatedJudgeConfig | None = None
    _pass_model: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        resolved = self.model or os.environ.get(ENV_MODEL, "")
        object.__setattr__(self, "_pass_model", bool(resolved))
        object.__setattr__(self, "model", resolved or CLI_DEFAULT_MODEL)

    def complete(self, prompt: str) -> str:
        reply = run_isolated_claude(
            prompt,
            isolation=self._resolved_isolation(),
            runner=self.runner,
            timeout_s=self.timeout_s,
            model=self.model if self._pass_model else None,
            callsite="comparative judge",
            error=ComparativeJudgeError,
        )
        return unwrap_cli_json(reply)


def judge_cache_key(
    left_attempt_id: str, right_attempt_id: str, prompt_version: str, model: str
) -> str:
    """Deterministic cache key for a comparison (engram's `computeJudgeCacheKey`):
    same pair + prompt version + model → same key, so a verdict is reusable."""
    return deterministic_id(
        {
            "left_attempt_id": left_attempt_id,
            "right_attempt_id": right_attempt_id,
            "prompt_version": prompt_version,
            "model": model,
        }
    )


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None"


def build_judge_prompt(
    left: Attempt,
    right: Attempt,
    narrative_diff: NarrativeDiff,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> str:
    """The judge prompt for one comparison. Only ``v1`` is defined; an unknown
    version raises (the version is recorded in the cache key, so changing the prompt
    invalidates cached verdicts)."""
    if prompt_version != "v1":
        raise ValueError(f"unknown prompt version: {prompt_version!r}")
    pc = narrative_diff.pros_cons
    return f"""You are a comparative judge evaluating two runs of the same coding task \
from a brain-selection A/B experiment. Attempt A is the {left.arm} arm; Attempt B \
is the {right.arm} arm. Decide which run did the better work.

# Attempt A: {left.arm} ({left.id[:8]})

Status: {left.status}
Metrics: {json.dumps(left.result, sort_keys=True)}

# Attempt B: {right.arm} ({right.id[:8]})

Status: {right.status}
Metrics: {json.dumps(right.result, sort_keys=True)}

# Narrative diff

{narrative_diff.summary}

## Attempt A pros
{_bullets(pc.left_pros)}

## Attempt A cons
{_bullets(pc.left_cons)}

## Attempt B pros
{_bullets(pc.right_pros)}

## Attempt B cons
{_bullets(pc.right_cons)}

## Deltas
{_bullets([d.description for d in narrative_diff.deltas])}

# Instructions

Weigh, in order: (1) did the run complete the task, (2) fewer iterations to green,
(3) efficiency — fewer tokens and fewer tool calls for the same outcome.

Respond with JSON only, no prose:

{{"winner": "A" | "B", "confidence": 0.0-1.0, "rationale": "2-3 sentence explanation"}}

Confidence: 1.0 clear winner, 0.8 strong, 0.6 moderate, 0.5 essentially tied
(still pick one). Be decisive but honest about confidence."""


def parse_judgment_reply(
    reply: str,
    left: Attempt,
    right: Attempt,
    *,
    content_hash: str,
    model: str,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> Judgment:
    """Parse a raw judge reply into a validated `Judgment`. A reply with no JSON,
    invalid JSON, a winner that is not ``A``/``B``, a non-numeric/out-of-range
    confidence, or a missing rationale raises `ComparativeJudgeError` — a malformed
    verdict is a real failure, never silently coerced to a default winner."""
    block = first_json_object(reply)
    if block is None:
        raise ComparativeJudgeError(f"judge reply has no JSON object: {reply[:200]!r}")
    try:
        parsed: Any = json.loads(block)
    except json.JSONDecodeError as exc:
        raise ComparativeJudgeError(f"judge reply is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ComparativeJudgeError(f"judge reply is not a JSON object: {parsed!r}")

    winner = parsed.get("winner")
    if winner not in ("A", "B"):
        raise ComparativeJudgeError(f"judge winner must be 'A' or 'B', got {winner!r}")
    confidence = parsed.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ComparativeJudgeError(f"judge confidence is not a number: {confidence!r}")
    if not 0.0 <= confidence <= 1.0:
        raise ComparativeJudgeError(f"judge confidence out of [0, 1]: {confidence}")
    rationale = parsed.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ComparativeJudgeError(f"judge rationale missing or empty: {rationale!r}")

    winner_id = left.id if winner == "A" else right.id
    return Judgment(
        left_attempt_id=left.id,
        right_attempt_id=right.id,
        winner_attempt_id=winner_id,
        confidence=float(confidence),
        rationale=rationale,
        model=model,
        prompt_version=prompt_version,
        content_hash=content_hash,
    )


def compare_attempts(
    left: Attempt,
    right: Attempt,
    narrative_diff: NarrativeDiff,
    judge: ComparativeJudge,
    *,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> Judgment:
    """Run ``judge`` over the narrative diff of ``left`` vs ``right`` and return the
    validated `Judgment`. Orchestration only: build the cache key and prompt, call
    the judge, parse and validate the reply."""
    content_hash = judge_cache_key(left.id, right.id, prompt_version, judge.model)
    prompt = build_judge_prompt(left, right, narrative_diff, prompt_version)
    reply = judge.complete(prompt)
    return parse_judgment_reply(
        reply,
        left,
        right,
        content_hash=content_hash,
        model=judge.model,
        prompt_version=prompt_version,
    )
