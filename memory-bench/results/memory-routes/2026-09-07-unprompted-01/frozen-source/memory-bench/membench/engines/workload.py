"""Workloads for the throughput sweep — built to exercise the prefix-cache lever.

The point of running SGLang next to vLLM, for a *memory* harness, is prefix reuse:
retrieval-augmented trials share a large, stable memory-context prefix and vary only
in a short tail. ``prefix_sharing_workload`` builds exactly that shape so the sweep
can measure the TTFT / KV-pressure delta that prefix caching buys — the experiment
that actually matters here, not a synthetic stand-in.

``load_prompts_jsonl`` is the escape hatch for replaying a real prompt distribution
(one JSON object per line, ``{"messages": [...]}`` or ``{"prompt": "..."}``).

Pure: builds message lists, touches no network.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

# A deterministic filler sentence (~12 words) repeated to reach a target prefix size.
# Deterministic so two sweep runs build byte-identical prefixes — the prefix cache can
# only hit if the prefix is stable, and a reproducible sweep needs a stable corpus.
_FILLER = "The memory context records a prior decision and the rationale behind it. "


def _approx_prefix(target_words: int) -> str:
    """A stable filler block of approximately ``target_words`` words. Tokenization is
    the engine's job; words are a tokenizer-agnostic proxy for prefix size here."""
    words_per_block = len(_FILLER.split())
    blocks = max(1, target_words // words_per_block)
    return (_FILLER * blocks).strip()


def prefix_sharing_workload(
    *,
    groups: int,
    prompts_per_group: int,
    prefix_words: int,
    cache_bust: str = "",
) -> list[list[dict[str, str]]]:
    """Build ``groups * prompts_per_group`` chat prompts.

    Every prompt in a group shares one large system prefix (the "retrieved memory");
    prompts differ only in a one-line user tail. Across groups the prefix differs, so
    a run sees both cache hits (within a group) and misses (first of each group) —
    the spread that makes a prefix-cache hit-rate measurement meaningful.

    ``groups=1`` is the maximal-sharing case (every request after the first should hit
    the prefix cache); ``prompts_per_group=1`` is the no-sharing baseline.

    ``cache_bust`` prepends a per-cell salt to every prefix. The sweep replays one
    workload against a *live* engine whose prefix cache persists across cells; without
    a salt, cell N hits the blocks cell N-1 already cached (identical prompts) and the
    measured hit rate reflects replay, not the cell's own sharing structure. A unique
    salt per cell isolates each cell to a cold cache while leaving the within-cell
    sharing intact. Empty (default) reproduces the original byte-stable prefix."""
    if groups < 1 or prompts_per_group < 1:
        raise ValueError("groups and prompts_per_group must both be >= 1")
    prompts: list[list[dict[str, str]]] = []
    for g in range(groups):
        # A per-group marker keeps each group's prefix distinct (a real cache miss at
        # the group boundary) while staying byte-stable across sweep reruns. The
        # cache_bust salt (if any) leads, so a salted cell shares no prefix block with
        # any other-salted cell.
        prefix = f"{cache_bust}[memory-group-{g}] {_approx_prefix(prefix_words)}"
        for i in range(prompts_per_group):
            prompts.append(
                [
                    {"role": "system", "content": prefix},
                    {
                        "role": "user",
                        "content": f"Question {i}: summarize the decision in one sentence.",
                    },
                ]
            )
    return prompts


def load_prompts_jsonl(path: Path) -> list[list[dict[str, str]]]:
    """Load a real prompt distribution from JSONL. Each line is either
    ``{"messages": [{"role": ..., "content": ...}, ...]}`` or ``{"prompt": "..."}``
    (wrapped into a single user message). Fails loud on a malformed line — a silently
    skipped prompt would understate load."""
    prompts: list[list[dict[str, str]]] = []
    for lineno, line in _nonblank_lines(path):
        obj = json.loads(line)
        if isinstance(obj, dict) and isinstance(obj.get("messages"), list):
            prompts.append([_as_message(m) for m in obj["messages"]])
        elif isinstance(obj, dict) and isinstance(obj.get("prompt"), str):
            prompts.append([{"role": "user", "content": obj["prompt"]}])
        else:
            raise ValueError(f"{path}:{lineno}: expected 'messages' list or 'prompt' string")
    return prompts


def _as_message(raw: object) -> dict[str, str]:
    if (
        isinstance(raw, dict)
        and isinstance(raw.get("role"), str)
        and isinstance(raw.get("content"), str)
    ):
        return {"role": raw["role"], "content": raw["content"]}
    raise ValueError(f"malformed message: {raw!r}")


def _nonblank_lines(path: Path) -> Iterator[tuple[int, str]]:
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if line:
                yield lineno, line
