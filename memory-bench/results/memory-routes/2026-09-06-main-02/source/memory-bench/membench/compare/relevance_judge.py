"""Pointwise relevance judge for the compare lane (mem-lvp.31).

Step 2 of the judged-relevance pipeline: given a held-out query work ``B`` and ONE
pooled candidate ``A``, decide whether consulting ``A`` would plausibly help solve
``B``. The decision is the delegated MODEL judgment over the same ``complete(prompt)
-> str`` seam the bbon comparative judge exposes
(`membench.bbon.comparative_judge.ComparativeJudge`): reuse ``ClaudeComparativeJudge``
for the headless-claude path, the LocalModelStack-backed OSS judge for the §4.1 local
path, or a pointwise ``StubComparativeJudge(fn=...)`` to drive the parse path offline
in tests. This module's own code is pure plumbing: prompt assembly, a leak scan, and a
STRICT reply parser that RAISES — never coerces a default verdict.

Three invariants make the judged relevant set non-circular and leak-free:

* **Pre-registered criterion = USEFULNESS.** The relevance question is "would
  consulting this past work plausibly help solve B", NOT "does A mention the same
  error as B". The prompt explicitly forbids surface error-token overlap as
  sufficient and requires the rationale to name the transferable lesson.

* **Anti-circularity via neutral projections.** The judge sees ONLY
  ``(query_text, candidate_text)`` — neutral text projections that EXCLUDE every
  failure-signature / parse field ``ours`` retrieves on (`SIGNATURE_FIELD_NAMES`:
  `leak_guard.IDENTIFYING_KEYS` + the D6-10 signature fields). A test asserts no such
  field NAME appears in any assembled prompt, so the judge can never re-derive ours's
  own retrieval key and rubber-stamp ours's hits.

* **Outcome / B-identity leak scan on the FULLY ASSEMBLED prompt.** Before EVERY
  judge call, the assembled prompt is scanned (reusing
  `grading.leak_guard.assert_no_outcome_leak`) for B's high-entropy identifiers
  (work_id / pr / external_ref / resolution). A hit RAISES loudly — a leaked
  B-identity would let the judge recognize the held-out answer.

The choice of binary vs graded output is fixed at PRE-REGISTRATION (the caller passes
``mode``); both ride one rubric. ``prompt_version`` is pinned and recorded in the
deterministic per-pair cache key alongside the judge model; temperature is 0 by
construction (the judge backends never sample for these structural verdicts).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from membench._claude_cli import first_json_object
from membench.bbon.comparative_judge import ComparativeJudge
from membench.bbon.models import deterministic_id
from membench.grading.leak_guard import IDENTIFYING_KEYS, assert_no_outcome_leak

RelevanceMode = Literal["binary", "graded"]

# The pinned prompt version. Changing the prompt MUST bump this so cached verdicts
# (keyed on it) are invalidated rather than silently reused.
DEFAULT_PROMPT_VERSION = "rel-v1"

# Graded rubric range, inclusive: 0 (irrelevant) .. 3 (directly solves B's problem).
GRADE_MIN = 0
GRADE_MAX = 3

# The field NAMES `ours` keys retrieval on — the answer-revealing surface the neutral
# projections must exclude. IDENTIFYING_KEYS (pr/commit_sha/base_commit, the
# leak_guard SSOT) plus the D6-10 failure-signature / parse fields (the recurrence
# signature and its parts: tool, file, line, error_class). A test asserts none of
# these names appears in any assembled prompt, so the judge cannot reconstruct ours's
# retrieval key from the prompt and judge in ours's favor by construction.
SIGNATURE_FIELD_NAMES: tuple[str, ...] = (
    *IDENTIFYING_KEYS,
    "signature",
    "error_class",
    "file",
    "line",
    "tool",
)


class RelevanceJudgeError(RuntimeError):
    """A relevance-judge invocation produced an unusable verdict (no JSON, a
    missing/wrong-typed/out-of-range field, or an empty rationale / transferable
    lesson). A malformed verdict is a real failure, surfaced loudly — never coerced
    to a default verdict."""


@dataclass(frozen=True)
class RelevanceInputs:
    """One (query, candidate) pair's worth of judge evidence.

    ``query_text`` and ``candidate_text`` are the ONLY content the judge sees: neutral
    text projections that EXCLUDE every failure-signature field ``ours`` retrieves on.
    The ``b_*`` fields are NOT shown to the judge — they are the held-out query's
    high-entropy identifiers, scanned against the fully assembled prompt so a B-identity
    that leaked into ``candidate_text`` (or anywhere) fails the call loudly."""

    query_work_id: str
    candidate_work_id: str
    query_text: str
    candidate_text: str
    b_work_id: str | None = None
    b_pr: str | None = None
    b_external_ref: str | None = None
    b_resolution: str | None = None


@dataclass(frozen=True)
class RelevanceVerdict:
    """A parsed, validated relevance verdict. Exactly one of ``relevant`` (binary
    mode) / ``grade`` (graded mode) is set; the other is ``None``. ``transferable_lesson``
    names the lesson A carries for B (the anti-error-token-overlap requirement);
    ``rationale`` is the free-text justification."""

    relevant: bool | None
    grade: int | None
    transferable_lesson: str
    rationale: str


@dataclass(frozen=True)
class RelevanceResult:
    """``score_relevance``'s output: the verdict, the pair cache key, and a flag
    proving the assembled prompt passed the B-identity leak scan before the call."""

    verdict: RelevanceVerdict
    cache_key: str
    judge_prompt_leak_checked: bool


def relevance_cache_key(
    query_work_id: str, candidate_work_id: str, prompt_version: str, judge_model: str
) -> str:
    """Deterministic per-pair cache key: same (query, candidate, prompt_version,
    judge_model) -> same key, so a verdict is reusable. Mirrors
    `bbon.comparative_judge.judge_cache_key`'s shape over the relevance pair."""
    return deterministic_id(
        {
            "query_work_id": query_work_id,
            "candidate_work_id": candidate_work_id,
            "prompt_version": prompt_version,
            "judge_model": judge_model,
        }
    )


def _require_mode(mode: str) -> RelevanceMode:
    if mode not in ("binary", "graded"):
        raise ValueError(f"unknown relevance mode {mode!r}; expected binary or graded")
    return mode  # type: ignore[return-value]


def _require_nonempty_str(parsed: dict[str, Any], key: str) -> str:
    value = parsed.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RelevanceJudgeError(f"verdict {key!r} missing or empty: {value!r}")
    return value


def parse_relevance_verdict(reply: str, *, mode: str) -> RelevanceVerdict:
    """Parse a raw judge reply into a validated `RelevanceVerdict`. A reply with no
    JSON object, a missing/wrong-typed verdict field, an out-of-range grade, or an
    empty rationale / transferable lesson raises `RelevanceJudgeError` — never
    silently defaulted. Mirrors `metrics.action_impact.parse_action_impact_verdict`."""
    resolved = _require_mode(mode)
    block = first_json_object(reply)
    if block is None:
        raise RelevanceJudgeError(f"verdict reply has no JSON object: {reply[:200]!r}")
    try:
        parsed: Any = json.loads(block)
    except json.JSONDecodeError as exc:
        raise RelevanceJudgeError(f"verdict reply is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RelevanceJudgeError(f"verdict reply is not a JSON object: {parsed!r}")

    relevant: bool | None = None
    grade: int | None = None
    if resolved == "binary":
        value = parsed.get("relevant")
        # bool first: bool is an int subclass, so an int would otherwise slip through.
        if not isinstance(value, bool):
            raise RelevanceJudgeError(f"verdict 'relevant' must be a boolean, got {value!r}")
        relevant = value
    else:
        raw = parsed.get("grade")
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise RelevanceJudgeError(f"verdict 'grade' must be an integer, got {raw!r}")
        if not GRADE_MIN <= raw <= GRADE_MAX:
            raise RelevanceJudgeError(
                f"verdict 'grade' out of range [{GRADE_MIN}, {GRADE_MAX}]: {raw}"
            )
        grade = raw

    transferable_lesson = _require_nonempty_str(parsed, "transferable_lesson")
    rationale = _require_nonempty_str(parsed, "rationale")
    return RelevanceVerdict(
        relevant=relevant,
        grade=grade,
        transferable_lesson=transferable_lesson,
        rationale=rationale,
    )


_CRITERION = """\
The relevance CRITERION is problem/solution USEFULNESS: would consulting this past \
work plausibly HELP SOLVE the current task? Judge transfer of a lesson, fix, or \
approach — NOT whether the two works mention the same error.

Surface error-token overlap is NOT sufficient: two works can name the same error \
message yet share no transferable lesson, and two works can share a deep lesson \
while naming different errors. You MUST name the concrete transferable lesson the \
past work carries for the current task; if you cannot name one, the past work is \
not relevant."""

_BINARY_RESPONSE = """\
Respond with JSON only, no prose:

{"relevant": true|false, "transferable_lesson": "the concrete lesson A carries for \
the current task", "rationale": "2-3 sentence justification grounded in the lesson"}"""

_GRADED_RESPONSE = """\
Respond with JSON only, no prose. Grade 0 (no useful transfer) .. 3 (directly \
addresses the current task's problem):

{"grade": 0|1|2|3, "transferable_lesson": "the concrete lesson A carries for the \
current task", "rationale": "2-3 sentence justification grounded in the lesson"}"""


def build_relevance_prompt(
    inp: RelevanceInputs,
    *,
    mode: str,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> str:
    """Assemble the pointwise relevance prompt from ONLY the neutral
    ``(query_text, candidate_text)`` projections. Pure plumbing: template
    substitution, no semantic decision here. An unknown ``prompt_version`` raises
    (the version is recorded in the cache key, so changing the prompt must invalidate
    cached verdicts).

    No identifier, failure-signature, or parse field is rendered — only the two
    free-text projections — so no `SIGNATURE_FIELD_NAMES` entry can reach the judge."""
    resolved = _require_mode(mode)
    if prompt_version != DEFAULT_PROMPT_VERSION:
        raise ValueError(f"unknown prompt version: {prompt_version!r}")
    response = _BINARY_RESPONSE if resolved == "binary" else _GRADED_RESPONSE
    return f"""You are judging whether a piece of PAST work would help with a CURRENT task.

{_CRITERION}

# Current task
{inp.query_text}

# Past work under consideration
{inp.candidate_text}

# Instructions
{response}"""


def _b_identity_labels(inp: RelevanceInputs) -> list[str]:
    """B's high-entropy identifiers to scan the assembled prompt for: the held-out
    query's work_id / pr / external_ref / resolution. None/blank values are dropped
    by the leak guard so they cannot match every document."""
    return [
        v for v in (inp.b_work_id, inp.b_pr, inp.b_external_ref, inp.b_resolution) if v is not None
    ]


def score_relevance(
    inp: RelevanceInputs,
    judge: ComparativeJudge,
    *,
    mode: str,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> RelevanceResult:
    """Judge one (query, candidate) pair. Builds the neutral prompt, scans the FULLY
    ASSEMBLED prompt for any B-identity leak (raises `OutcomeLeakError` on a hit, never
    silently strips), calls the injected judge, and STRICTLY parses the reply (raises
    `RelevanceJudgeError` on a malformed verdict). Returns the verdict, the pair cache
    key, and ``judge_prompt_leak_checked=True`` proving the scan ran before the call."""
    resolved = _require_mode(mode)
    prompt = build_relevance_prompt(inp, mode=resolved, prompt_version=prompt_version)
    # Leak scan on the FULLY ASSEMBLED prompt, before the call — fail loud.
    assert_no_outcome_leak(prompt, _b_identity_labels(inp))
    verdict = parse_relevance_verdict(judge.complete(prompt), mode=resolved)
    return RelevanceResult(
        verdict=verdict,
        cache_key=relevance_cache_key(
            inp.query_work_id, inp.candidate_work_id, prompt_version, judge.model
        ),
        judge_prompt_leak_checked=True,
    )
