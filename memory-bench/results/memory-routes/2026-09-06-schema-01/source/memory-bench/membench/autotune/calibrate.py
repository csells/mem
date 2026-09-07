"""Calibrate the synthetic sweep workload to the harness's real prompt SHAPE.

For throughput / latency / KV tuning, what matters is not prompt *content* but prompt
*shape*: how large the shared memory prefix is, how long the tail is, and how many
requests share a prefix. This module measures that shape from the benchmark sequences
and emits a ``TrialConfig`` whose synthetic ``prefix_sharing_workload`` reproduces it —
so the load you sweep is representative of the real agent workload, not a guess.

The mapping from a ``BenchmarkSequence`` to the prefix-sharing workload:

  - a step's **memory prefix** = the contents of the memories it reads
    (``expected_memory_reads``), resolved against the pool accumulated from earlier
    steps' ``expected_memory_writes`` — exactly the oracle-injected context the agent
    sees. Its word count calibrates ``prefix_words``.
  - a step's **tail** = ``user_request`` (measured, reported; the synthetic tail is a
    fixed short line, so this is informational).
  - **prefix sharing** = the steps of one sequence share that sequence's accumulating
    memory pool, so steps-per-sequence calibrates ``prompts_per_group``; ``groups`` is
    then scaled to hit a target request count while preserving the sharing ratio.

Everything is measured in **words** (whitespace split) — the same tokenizer-free unit
``engines.workload`` uses for ``prefix_words`` — so no tokenizer dependency is added.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from membench.autotune.config import TrialConfig
from membench.engines.sweep import percentile
from membench.schemas.sequence import BenchmarkSequence

# A rough words→tokens factor for turning a measured output-word proxy into a
# ``max_tokens`` default. English averages ~1.3 subword tokens per word; this is a
# documented heuristic, not a precise count, and is overridable.
_TOKENS_PER_WORD = 1.3


def _words(text: str) -> int:
    return len(text.split())


@dataclass(frozen=True)
class ShapeStats:
    """The measured shape of the real prompt distribution. Word-denominated. Fields are
    None when no step supplied the signal (e.g. no step read memory), never silently
    zero — absence and a measured zero are different."""

    n_sequences: int
    n_steps: int
    n_steps_with_memory: int
    prefix_words_p50: float | None
    prefix_words_p90: float | None
    tail_words_p50: float | None
    write_words_p50: float | None
    steps_per_sequence_p50: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "n_sequences": self.n_sequences,
            "n_steps": self.n_steps,
            "n_steps_with_memory": self.n_steps_with_memory,
            "prefix_words_p50": self.prefix_words_p50,
            "prefix_words_p90": self.prefix_words_p90,
            "tail_words_p50": self.tail_words_p50,
            "write_words_p50": self.write_words_p50,
            "steps_per_sequence_p50": self.steps_per_sequence_p50,
        }


def measure_sequences(sequences: Sequence[BenchmarkSequence]) -> ShapeStats:
    """Measure the prompt shape across all sequences. Pure.

    Walks each sequence in order, accumulating an id→content memory pool from
    ``expected_memory_writes``; at each step the prefix is the joined content of the
    ids in ``expected_memory_reads`` that the pool already holds (a forward reference
    to an unwritten memory contributes nothing, as in a real run)."""
    prefix_words: list[float] = []
    tail_words: list[float] = []
    write_words: list[float] = []
    steps_per_seq: list[float] = []
    n_steps = 0
    n_with_memory = 0

    for seq in sequences:
        steps_per_seq.append(float(len(seq.steps)))
        pool: dict[str, str] = {}
        for step in seq.steps:
            n_steps += 1
            tail_words.append(float(_words(step.user_request)))
            read_contents = [pool[mid] for mid in step.expected_memory_reads if mid in pool]
            if read_contents:
                n_with_memory += 1
                prefix_words.append(float(_words(" ".join(read_contents))))
            step_write_words = sum(_words(c) for c in step.expected_memory_writes.values())
            if step.expected_memory_writes:
                write_words.append(float(step_write_words))
            # Writes become available to LATER steps (post-step), matching a real run.
            pool.update(step.expected_memory_writes)

    return ShapeStats(
        n_sequences=len(sequences),
        n_steps=n_steps,
        n_steps_with_memory=n_with_memory,
        prefix_words_p50=percentile(prefix_words, 0.50),
        prefix_words_p90=percentile(prefix_words, 0.90),
        tail_words_p50=percentile(tail_words, 0.50),
        write_words_p50=percentile(write_words, 0.50),
        steps_per_sequence_p50=percentile(steps_per_seq, 0.50),
    )


def calibrated_config(
    stats: ShapeStats,
    *,
    engine: str,
    concurrencies: tuple[int, ...],
    target_requests: int,
    max_tokens: int | None = None,
    temperature: float = 0.0,
) -> TrialConfig:
    """Turn measured shape into a runnable ``TrialConfig``.

    ``prompts_per_group`` mirrors the real steps-per-sequence (the intra-sequence
    prefix sharing); ``groups`` is then scaled so the total request count reaches
    ``target_requests`` — preserving the real *sharing ratio* while giving the sweep
    enough load to actually pressure the engine (the 35-step corpus is too small to
    load anything on its own). ``max_tokens`` defaults from the measured write-word
    proxy (a lower bound on output length, the only output signal the fixtures carry);
    pass an explicit value for a use-case-specific decode length."""
    if target_requests < 1:
        raise ValueError("target_requests must be >= 1")

    ppg = max(1, round(stats.steps_per_sequence_p50 or 1.0))
    groups = max(1, math.ceil(target_requests / ppg))
    # Fall back through prefix → tail → a small floor so a corpus with no memory-bearing
    # steps still yields a usable (if un-shared-prefix) config rather than failing.
    prefix_words = max(1, round(stats.prefix_words_p50 or stats.tail_words_p50 or 50.0))
    if max_tokens is None:
        max_tokens = max(1, round((stats.write_words_p50 or 24.0) * _TOKENS_PER_WORD))

    return TrialConfig(
        engine=engine,
        concurrencies=concurrencies,
        max_tokens=max_tokens,
        temperature=temperature,
        groups=groups,
        prompts_per_group=ppg,
        prefix_words=prefix_words,
    )
