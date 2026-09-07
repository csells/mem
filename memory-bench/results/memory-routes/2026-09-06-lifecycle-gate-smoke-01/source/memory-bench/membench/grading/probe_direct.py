"""PROBE-GRADE direct scorer for the dynamic-range gate (mem-75t.7.6, plan §9.2).

The gate's only question is whether the none-rung floor and a cheap upper-bound rung
are SEPARABLE on ~10 admitted bundles. That needs a probe, not the full mem-75t.7.5
dual-verifier port: a purely mechanical diff-vs-diff similarity plus the efficiency
axis (the metric most likely to retain dynamic range if success-rate saturates,
plan §9.5). Three legs live here:

- `score_probe_direct`: candidate diff vs gold diff, pure arithmetic.

  * **file-set F1** -- precision/recall over the changed-file path sets. Both diffs
    must be per-file mappings in the SAME coordinate space (checkout-relative git
    paths, as `bundle.replay.gold_diff` emits for both the gold and candidate
    checkouts); this module does no path normalization.
  * **hunk overlap** -- per overlapping file, the Jaccard of the sign-tagged
    changed-line sets ``{("+", line)} | {("-", line)}`` projected from the unified
    diff (file headers ``+++``/``---`` excluded). Set semantics: duplicate identical
    lines collapse -- a mechanical comparison, not a positional alignment. Two empty
    sets (e.g. mode-only diffs) are an identical change, Jaccard 1.0. The bundle
    score is the unweighted mean over overlapping files; with no overlap it is 0.0
    (and file F1 is necessarily 0.0 too, so the legs cannot disagree about "nothing
    matched").
  * **combined = file_f1 x hunk_overlap** (multiplicative, NOT a mean). Both
    "edited the right files" and "made the right edits" must hold for a high score;
    a mean would put a 0.5 floor under any files-only match and compress exactly
    the dynamic range the gate exists to measure. Endpoints: identical diffs -> 1.0,
    disjoint file sets -> 0.0.

  An empty GOLD diff raises: admission (mem-75t.7.2) pins empty replays out, so an
  empty output leg here is an upstream bug, never a 0.0 to tally. An empty
  CANDIDATE diff is a legitimate run outcome (the agent edited nothing) and scores
  0.0 across the board.

- `extract_efficiency`: tokens/turns/tool-call counts from a Claude Code stream-json
  transcript. Same line-walk tolerance as `harbor_exec.project_claude_stream`
  (non-JSON lines and shapeless events skipped), but keyed on ``assistant`` events:
  one assistant message event = one turn; ``tool_use`` blocks within them are the
  tool calls; token fields sum the per-event ``message.usage`` values. A token field
  is ``None`` when NO event carries it (typed absence -- some transcript shapes
  record no usage), never silently 0. The cumulative ``result`` event is deliberately
  not a token source: it would double-count the per-event sums and make the total
  depend on which shapes a transcript happens to include.

- `gold_file_list`: the poor-man oracle-rung payload -- the bundle's gold-diff file
  paths, sorted. The gate injects this as the cheap upper-bound context (no curated
  oracle needed, plan §9.2).

ZFC: pure mechanism -- structural parsing, set arithmetic, sums. No model calls, no
semantic heuristics. Not exported from ``membench.grading.__init__``: this module
imports `membench.schemas.bundle`, whose import chain reaches `harbor.grid`, which
imports the ``grading`` package -- keeping it out of the package ``__init__`` keeps
that graph acyclic (same convention as ``schemas.bundle`` itself). Import it as
``membench.grading.probe_direct``.
"""

import json
from collections.abc import Mapping
from statistics import fmean

from pydantic import BaseModel, ConfigDict, Field, field_validator

from membench.schemas.bundle import TaskBundle


class ProbeDirectScore(BaseModel):
    """The probe's direct-leg score for one candidate-vs-gold diff pair.

    ``per_file_overlap`` covers exactly the overlapping files (candidate ∩ gold),
    stored as sorted ``(path, jaccard)`` pairs (a dict field inside a frozen model is
    still mutable in place; a mapping passed at construction is converted);
    ``hunk_overlap`` is its unweighted mean (0.0 when no files overlap);
    ``combined = file_f1 * hunk_overlap`` (rule documented in the module docstring)."""

    model_config = ConfigDict(frozen=True)

    file_precision: float = Field(ge=0.0, le=1.0)
    file_recall: float = Field(ge=0.0, le=1.0)
    file_f1: float = Field(ge=0.0, le=1.0)
    per_file_overlap: tuple[tuple[str, float], ...]
    hunk_overlap: float = Field(ge=0.0, le=1.0)
    combined: float = Field(ge=0.0, le=1.0)

    @field_validator("per_file_overlap", mode="before")
    @classmethod
    def _per_file_overlap_as_pairs(cls, value: object) -> object:
        if isinstance(value, Mapping):
            return tuple(sorted(value.items()))
        return value


class ProbeEfficiency(BaseModel):
    """The efficiency axis for one transcript. Token fields are ``None`` when the
    transcript shape carries no usage data -- typed absence, never a silent zero."""

    model_config = ConfigDict(frozen=True)

    turns: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


def changed_lines(diff_text: str) -> frozenset[tuple[str, str]]:
    """The sign-tagged changed-line set of one unified diff: ``("+", line)`` for
    additions, ``("-", line)`` for removals, file headers (``+++``/``---``) excluded.
    Context, hunk and metadata lines carry no leading +/- and drop out structurally."""
    lines: set[tuple[str, str]] = set()
    for raw in diff_text.splitlines():
        if raw.startswith(("+++", "---")):
            continue
        if raw.startswith(("+", "-")):
            lines.add((raw[0], raw[1:]))
    return frozenset(lines)


def _jaccard(a: frozenset[tuple[str, str]], b: frozenset[tuple[str, str]]) -> float:
    """Set Jaccard; two empty sets are an identical (empty) change -> 1.0."""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def score_probe_direct(
    candidate_diff: Mapping[str, str], gold_diff: Mapping[str, str]
) -> ProbeDirectScore:
    """Score a candidate per-file diff against the bundle's gold per-file diff.

    Both mappings are ``path -> unified diff text`` with paths in the same
    coordinate space (checkout-relative). See the module docstring for the three
    sub-scores and the explicit combination rule."""
    if not gold_diff:
        raise ValueError(
            "empty gold diff: admission guarantees a non-empty output leg, so an "
            "empty gold diff is an upstream bundle bug, not a scoreable run"
        )
    candidate_files = set(candidate_diff)
    gold_files = set(gold_diff)
    overlap_files = candidate_files & gold_files

    precision = len(overlap_files) / len(candidate_files) if candidate_files else 0.0
    recall = len(overlap_files) / len(gold_files)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    per_file_overlap = {
        path: _jaccard(changed_lines(candidate_diff[path]), changed_lines(gold_diff[path]))
        for path in sorted(overlap_files)
    }
    hunk_overlap = fmean(per_file_overlap.values()) if per_file_overlap else 0.0

    return ProbeDirectScore(
        file_precision=precision,
        file_recall=recall,
        file_f1=f1,
        per_file_overlap=tuple(per_file_overlap.items()),  # built over sorted(overlap_files)
        hunk_overlap=hunk_overlap,
        combined=f1 * hunk_overlap,
    )


def extract_efficiency(stream: str) -> ProbeEfficiency:
    """Project a Claude Code stream-json transcript onto the efficiency axis.

    ``stream`` is the transcript text (``claude-code.txt`` / resolved ``.jsonl``).
    Counting rules and the typed-absence token contract are in the module docstring."""
    turns = 0
    tool_calls = 0
    input_tokens: int | None = None
    output_tokens: int | None = None

    for line in stream.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, Mapping) or event.get("type") != "assistant":
            continue
        message = event.get("message")
        if not isinstance(message, Mapping):
            continue
        turns += 1
        content = message.get("content")
        if isinstance(content, list):
            tool_calls += sum(
                1
                for block in content
                if isinstance(block, Mapping) and block.get("type") == "tool_use"
            )
        usage = message.get("usage")
        if isinstance(usage, Mapping):
            if isinstance(usage.get("input_tokens"), int):
                input_tokens = (input_tokens or 0) + usage["input_tokens"]
            if isinstance(usage.get("output_tokens"), int):
                output_tokens = (output_tokens or 0) + usage["output_tokens"]

    return ProbeEfficiency(
        turns=turns,
        tool_calls=tool_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def gold_file_list(bundle: TaskBundle) -> tuple[str, ...]:
    """The cheap-oracle context payload: the bundle's gold-diff file paths, sorted.

    This is the gate's poor-man oracle rung (plan §9.2) -- the upper-bound condition
    injects "the files the gold change touched" with no curation. Paths are
    checkout-relative, exactly as `bundle.replay.gold_diff` recorded them."""
    return tuple(sorted(path for path, _ in bundle.output.file_diffs))
