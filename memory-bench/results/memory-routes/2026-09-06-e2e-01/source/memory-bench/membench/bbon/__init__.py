"""bBoN comparative-judge machinery, ported from engram (sjarmak/engram) for the
mem-0ut warm-vs-cold brain-selection A/B.

`armcompare.py` measures the *mechanical* effect size (tokens, tool calls,
iterations-to-green) per arm. This package is the *qualitative* layer that says
WHAT a warm-forked run did differently from a cold one: it builds an `Attempt`
(one arm's run of a bead) with its trace `AttemptStep`s, aligns two attempts into
a deterministic `NarrativeDiff` (the mechanical "what changed" artifact), and runs
a pairwise `ComparativeJudge` over that diff (the delegated semantic judgment) to
pick a winner with a confidence and rationale.

The judge is headless `claude -p` (`ClaudeComparativeJudge`) — engram's hardcoded
OpenAI call is gone (D4/D16 forbid a paid managed API; the local Claude CLI is the
OAuth seam, not a paid host). Every test and the whole pipeline run on the offline
`StubComparativeJudge`, so no model or network is touched unless explicitly asked.

Ported faithfully in machinery, adapted in signal: the diff and pros/cons read
membench's real axes (status, tool-call count, iterations-to-green, tokens) rather
than engram's `learn_complete` rollout fields, which have no membench analog.
"""

from membench.bbon.aggregate import (
    Comparison,
    build_comparison,
    summarize_comparisons,
)
from membench.bbon.comparative_judge import (
    ClaudeComparativeJudge,
    ComparativeJudge,
    ComparativeJudgeError,
    StubComparativeJudge,
    build_judge_prompt,
    compare_attempts,
    judge_cache_key,
    parse_judgment_reply,
)
from membench.bbon.extract import build_attempt, steps_from_stream, terminal_status
from membench.bbon.local_stack_judge import LocalStackComparativeJudge
from membench.bbon.models import (
    AlignedStep,
    Attempt,
    AttemptStep,
    Delta,
    Judgment,
    NarrativeDiff,
    ProsCons,
    canonicalize,
    deterministic_id,
)
from membench.bbon.narrative_diff import generate_narrative_diff

__all__ = [
    "AlignedStep",
    "Attempt",
    "AttemptStep",
    "ClaudeComparativeJudge",
    "ComparativeJudge",
    "ComparativeJudgeError",
    "Comparison",
    "Delta",
    "Judgment",
    "LocalStackComparativeJudge",
    "NarrativeDiff",
    "ProsCons",
    "StubComparativeJudge",
    "build_attempt",
    "build_comparison",
    "build_judge_prompt",
    "canonicalize",
    "compare_attempts",
    "deterministic_id",
    "generate_narrative_diff",
    "judge_cache_key",
    "parse_judgment_reply",
    "steps_from_stream",
    "summarize_comparisons",
    "terminal_status",
]
