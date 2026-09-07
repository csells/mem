"""bBoN data models + content-addressed IDs (ported from engram).

`canonicalize` / `deterministic_id` reproduce engram's RFC8785-style canonical
JSON + SHA-256 (`src/utils/canonicalize.ts`, `src/utils/id.ts`): the same content
always hashes to the same 64-hex id, so attempts and steps dedup by identity
rather than by a random key. The canonical form is sorted-key, compact-separator
JSON; non-integer floats use Python's shortest round-trip repr (the id inputs in
this package are strings/ints, so float formatting is never on the hot path and
is not promised to be byte-identical to engram's `Number.toString`).

The schemas mirror engram's `src/schemas/bbon.ts`, adapted to the membench
substrate: an `Attempt` is one *arm's* run of a bead (warm or cold), not one of N
parallel rollout attempts — membench has a single trace per arm per bead, so
engram's run/ordinal/seed rollout fields are dropped (keeping them would be a
single-value-never-varied field set, i.e. dead structure). `result` carries the
mechanical metric vector so the comparative judge sees the same numbers the
mechanical readout reports.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# One run of a bead under one experiment arm; 'unknown' when the trace carries no
# pass/fail outcome to terminalize on (typed absence, not an assumed failure).
AttemptStatus = Literal["completed", "failed", "unknown"]

# A deterministic id is a lowercase 64-char hex SHA-256 digest.
ID_PATTERN = r"^[a-f0-9]{64}$"


def canonicalize(obj: Any) -> str:
    """RFC8785-style canonical JSON: sorted object keys, compact separators, so the
    serialization is identity-stable. ``None`` serializes to ``null`` (Python has no
    JS ``undefined`` to omit); non-finite floats raise rather than emit ``NaN``."""
    if obj is None:
        return "null"
    if obj is True:
        return "true"
    if obj is False:
        return "false"
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, int):  # bool already handled above (bool is an int subclass)
        return str(obj)
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(f"cannot canonicalize non-finite float: {obj}")
        return str(int(obj)) if obj.is_integer() else repr(obj)
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(canonicalize(x) for x in obj) + "]"
    if isinstance(obj, Mapping):
        pairs = (
            f"{json.dumps(str(k), ensure_ascii=False)}:{canonicalize(v)}"
            for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))
        )
        return "{" + ",".join(pairs) + "}"
    raise TypeError(f"cannot canonicalize type {type(obj).__name__}")


def deterministic_id(obj: Any) -> str:
    """Content-addressed 64-hex id: SHA-256 over the canonical JSON of ``obj``."""
    return hashlib.sha256(canonicalize(obj).encode("utf-8")).hexdigest()


class AttemptStep(BaseModel):
    """One trace step within an attempt — a single tool call, in stream order.

    ``kind`` is the membench tool name (``Read``/``Edit``/``Bash``/...); ``input``
    is that tool's input block. ``output``/``observation`` are kept for engram
    schema parity (and future enrichment) but are empty for membench tool-use
    steps, which carry no post-hoc result in the stream."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=ID_PATTERN)
    attempt_id: str = Field(pattern=ID_PATTERN)
    step_index: int = Field(ge=0)
    kind: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    observation: dict[str, Any] = Field(default_factory=dict)


class Attempt(BaseModel):
    """One arm's run of a bead. ``id`` is content-addressed over (work_id, arm), so
    the same bead-arm always yields the same id (dedup). ``result`` is the mechanical
    metric vector the judge is shown alongside the narrative diff."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=ID_PATTERN)
    work_id: str
    arm: str
    status: AttemptStatus
    result: dict[str, Any] = Field(default_factory=dict)


class AlignedStep(BaseModel):
    """One index-aligned slot across the two attempts' step lists. Either side may
    be absent (the other ran longer); ``delta`` names the difference at this index
    when there is one (kind mismatch, output/observation mismatch, or one-sided)."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    left_step: AttemptStep | None = None
    right_step: AttemptStep | None = None
    delta: str | None = None


class Delta(BaseModel):
    """One attempt-level difference (status, step count, errors, tokens, ...).
    ``type`` follows engram's added/removed/modified/same vocabulary."""

    model_config = ConfigDict(frozen=True)

    type: Literal["added", "removed", "modified", "same"]
    path: str
    left_value: Any = None
    right_value: Any = None
    description: str


class ProsCons(BaseModel):
    """The mechanically-derived advantages/disadvantages of each side — the grounded
    bullets the judge weighs (it is not asked to re-derive them from raw traces)."""

    model_config = ConfigDict(frozen=True)

    left_pros: list[str] = Field(default_factory=list)
    left_cons: list[str] = Field(default_factory=list)
    right_pros: list[str] = Field(default_factory=list)
    right_cons: list[str] = Field(default_factory=list)


class NarrativeDiff(BaseModel):
    """The deterministic comparison artifact: step alignment + attempt-level deltas
    + pros/cons + a human-readable summary. Pure mechanism — no model judgment."""

    model_config = ConfigDict(frozen=True)

    left_attempt_id: str = Field(pattern=ID_PATTERN)
    right_attempt_id: str = Field(pattern=ID_PATTERN)
    aligned_steps: list[AlignedStep]
    deltas: list[Delta]
    pros_cons: ProsCons
    summary: str


class Judgment(BaseModel):
    """The comparative judge's verdict over one narrative diff: which attempt won,
    how confident, and why. ``content_hash`` is the deterministic cache key over
    (left_id, right_id, prompt_version, model) — same pair + prompt + model reuse it."""

    model_config = ConfigDict(frozen=True)

    left_attempt_id: str = Field(pattern=ID_PATTERN)
    right_attempt_id: str = Field(pattern=ID_PATTERN)
    winner_attempt_id: str = Field(pattern=ID_PATTERN)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    model: str
    prompt_version: str
    content_hash: str = Field(pattern=ID_PATTERN)
