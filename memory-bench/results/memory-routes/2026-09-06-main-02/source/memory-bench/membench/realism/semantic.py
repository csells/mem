"""Semantic realism (axis 2): a MODEL judge rates whether a synthetic task reads
like genuine real agent work.

The structural axis (``distance.py``) can be satisfied by templated prose that
happens to match the real corpus on counts; this axis asks the question counts
cannot — *would a reviewer believe this task came from a real session?* Per ZFC
that judgment MUST be model-delegated, never regex/keyword: this module is pure
plumbing (prompt assembly, JSON parsing, structural validation) and the rating
itself is the model's call.

It reuses the existing ``ComparativeJudge`` seam from ``bbon.comparative_judge``:
``StubComparativeJudge`` for tests and the whole offline pipeline,
``ClaudeComparativeJudge`` (headless ``claude -p``) or — per mem-ovi, the intended
real backend — ``bbon.local_stack_judge.LocalStackComparativeJudge`` (self-hosted
Ollama serving the pinned qwen2.5 / llama3.1, free, scix-batch). Any judge
implementing the protocol drops in here; this module never names a backend.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from membench.bbon.comparative_judge import ComparativeJudge
from membench.schemas.sequence import BenchmarkSequence

PROMPT_VERSION = "realism-semantic-v1"

# Default floors for the aggregate semantic verdict. PLACEHOLDERS pending
# Stephanie's #mem sign-off — thresholds, not architecture.
DEFAULT_MIN_REALISM = 0.60
DEFAULT_MIN_REAL_FRACTION = 0.60


class SemanticJudgeError(RuntimeError):
    """A semantic-realism verdict could not be obtained or parsed. Surfaced
    loudly — a malformed reply is a real failure, never coerced to a default
    rating (which would silently fabricate a realism number)."""


@dataclass(frozen=True)
class SemanticVerdict:
    """One task's model-judged realism: a rating in ``[0, 1]``, a boolean 'would a
    reviewer believe it', and the model's rationale."""

    realism: float
    reads_real: bool
    rationale: str
    model: str


def task_text_for_sequence(seq: BenchmarkSequence) -> str:
    """Assemble the human-readable task text a judge reads — the title, goal, and
    each step's request, in order. This is the synthetic artifact whose realism is
    being rated, rendered the way a reviewer would skim it."""
    lines = [f"Title: {seq.title}"]
    if seq.goal:
        lines.append(f"Goal: {seq.goal}")
    lines.append("")
    for idx, step in enumerate(seq.steps, start=1):
        lines.append(f"Step {idx}: {step.user_request}")
    return "\n".join(lines)


def build_semantic_prompt(task_text: str) -> str:
    """The judge prompt for one task. Asks for a realism rating, a believability
    boolean, and a short rationale, as JSON only."""
    return f"""You are a reviewer auditing a benchmark of AI agent coding tasks. Some \
tasks were drawn from real agent sessions; others were authored by a synthetic \
generator. Judge ONE task below.

# Task

{task_text}

# Question

Would an experienced reviewer believe this task came from a REAL agent session \
(as opposed to a templated synthetic generator)? Weigh whether the request reads \
like genuine work — specific, plausibly motivated, naturally phrased — versus \
formulaic, placeholder, or template-stamped prose.

Respond with JSON only, no prose:

{{"realism": 0.0-1.0, "reads_real": true | false, "rationale": "2-3 sentence explanation"}}

realism: 1.0 indistinguishable from real work, 0.5 ambiguous, 0.0 obviously \
synthetic. reads_real: your believability call. Be decisive but honest."""


def _balanced_objects(text: str) -> list[str]:
    """Every balanced ``{...}`` block in ``text``, in order, tolerating surrounding
    prose and braces inside string literals. Prose between objects (and before the
    first ``{``) is skipped, so a stray quote in the preamble cannot mis-toggle the
    string state of a later object."""
    blocks: list[str] = []
    depth = 0
    in_string = False
    escaped = False
    start = -1
    for i, ch in enumerate(text):
        if depth == 0:
            if ch == "{":
                depth, start, in_string, escaped = 1, i, False, False
            continue
        if escaped:
            escaped = False
        elif in_string:
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blocks.append(text[start : i + 1])
    return blocks


def _select_verdict_object(reply: str) -> dict[str, Any]:
    """The verdict object in a judge reply: the first balanced JSON object that
    parses to a dict carrying a ``realism`` key. A judge may emit a reasoning
    object before its verdict — selecting on the key rather than blindly taking the
    first object stops that preamble from shadowing the real verdict. Raises when no
    such object is present."""
    for block in _balanced_objects(reply):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "realism" in parsed:
            return parsed
    raise SemanticJudgeError(
        f"judge reply has no JSON object with a 'realism' field: {reply[:200]!r}"
    )


def parse_semantic_verdict(reply: str, *, model: str) -> SemanticVerdict:
    """Parse a raw judge reply into a validated `SemanticVerdict`. A reply with no
    verdict object, an out-of-range realism, a non-boolean ``reads_real``, or a
    missing rationale raises `SemanticJudgeError`."""
    parsed = _select_verdict_object(reply)

    realism = parsed.get("realism")
    if isinstance(realism, bool) or not isinstance(realism, (int, float)):
        raise SemanticJudgeError(f"judge realism is not a number: {realism!r}")
    if not 0.0 <= realism <= 1.0:
        raise SemanticJudgeError(f"judge realism out of [0, 1]: {realism}")
    reads_real = parsed.get("reads_real")
    if not isinstance(reads_real, bool):
        raise SemanticJudgeError(f"judge reads_real is not a boolean: {reads_real!r}")
    rationale = parsed.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise SemanticJudgeError(f"judge rationale missing or empty: {rationale!r}")

    return SemanticVerdict(
        realism=float(realism), reads_real=reads_real, rationale=rationale, model=model
    )


def score_semantic_realism(seq: BenchmarkSequence, judge: ComparativeJudge) -> SemanticVerdict:
    """Rate one synthetic task's realism with ``judge``. Orchestration only: build
    the task text, build the prompt, call the judge, parse and validate."""
    prompt = build_semantic_prompt(task_text_for_sequence(seq))
    reply = judge.complete(prompt)
    return parse_semantic_verdict(reply, model=judge.model)


@dataclass(frozen=True)
class SemanticAggregate:
    """The corpus-level semantic verdict over per-task ratings."""

    mean_realism: float
    real_fraction: float
    n: int
    min_realism: float
    min_real_fraction: float

    @property
    def passes(self) -> bool:
        return (
            self.mean_realism >= self.min_realism and self.real_fraction >= self.min_real_fraction
        )


def aggregate_semantic(
    verdicts: Sequence[SemanticVerdict],
    *,
    min_realism: float = DEFAULT_MIN_REALISM,
    min_real_fraction: float = DEFAULT_MIN_REAL_FRACTION,
) -> SemanticAggregate:
    """Aggregate per-task verdicts into a corpus realism summary: mean rating and
    the fraction judged believable, against tunable floors. Raises on an empty
    corpus — there is no realism to summarize."""
    if not verdicts:
        raise ValueError("aggregate_semantic needs at least one verdict")
    n = len(verdicts)
    mean_realism = sum(v.realism for v in verdicts) / n
    real_fraction = sum(1 for v in verdicts if v.reads_real) / n
    return SemanticAggregate(
        mean_realism=mean_realism,
        real_fraction=real_fraction,
        n=n,
        min_realism=min_realism,
        min_real_fraction=min_real_fraction,
    )
