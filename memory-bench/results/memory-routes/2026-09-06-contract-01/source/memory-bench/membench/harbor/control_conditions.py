"""M3 + M4 — control-condition payload builders + the on-payload leak guard.

Two brute-force controls for the headline grid, built as the distilled-memory arm's
opposites:

* **raw-trajectory (M3)** — the bundle's RAW transcript, undistilled. The injected
  ceiling on "what was in the trajectory". Truncation keeps the TAIL, where the
  resolution lives.
* **full-context (M4)** — ALL in-scope prior work, ``loo_excluded_work_ids`` withheld.
  The brute-force ceiling on "what prior work could help". Records are ordered by
  temporal proximity to the query work, so truncation drops the least relevant.

Both honour two disciplines the premortem (lens 5) named as the controls' failure
modes: truncation to a char budget is REPORTED — never silent, with kept-span offsets
recorded for audit; and every payload is run through the SAME probe leak guard
(``assert_probe_task_clean``) on its KEPT span before it could reach an agent — a raw
transcript or a prior-work dump is far likelier to quote the gold diff / base_commit
than a distilled lesson, so the guard verdict is a fail-loud, first-class signal.

These are the payload + guard core (pure, CI-testable). Baking a control payload
into the Harbor image and adding the condition to the multi-hour Docker grid driver
reuses the existing ``inject_context`` / ``_bake_memory_into_env`` path and is a
separate operational step.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from membench.schemas.bundle import TaskBundle

RAW_TRAJECTORY = "raw-trajectory"
FULL_CONTEXT = "full-context"

# The injected payload lands in this single agent-readable file (the same target the
# distilled-memory arm uses), so one leak-guard call covers the whole payload.
_PAYLOAD_FILE = "MEMORY.md"


class InScopeWork(BaseModel):
    """One in-scope prior-work record for the M4 payload: its rendered text plus
    ``closed_at``, the temporal anchor the payload ordering keys on."""

    model_config = ConfigDict(frozen=True)

    text: str
    closed_at: datetime


class PayloadTruncation(BaseModel):
    """How much of the source survived the char budget. ``truncated`` makes the drop
    explicit so a coverage hole can never read as full coverage.
    ``kept_start``/``kept_end`` are char offsets of the kept span into the source
    text the budget ran on (M3: the raw transcript; M4: the proximity-ordered
    prior-work body), so every payload is auditable against its source."""

    model_config = ConfigDict(frozen=True)

    original_chars: int
    kept_chars: int
    kept_start: int
    kept_end: int
    truncated: bool


class ControlPayload(BaseModel):
    """One control condition's injectable text + its truncation record."""

    model_config = ConfigDict(frozen=True)

    condition: str
    text: str
    truncation: PayloadTruncation


def _truncate(
    text: str, max_chars: int, *, keep: Literal["head", "tail"]
) -> tuple[str, PayloadTruncation]:
    if max_chars < 0:
        raise ValueError(f"max_chars must be >= 0, got {max_chars}")
    n = len(text)
    if n <= max_chars:
        return text, PayloadTruncation(
            original_chars=n, kept_chars=n, kept_start=0, kept_end=n, truncated=False
        )
    start = 0 if keep == "head" else n - max_chars
    end = start + max_chars
    return text[start:end], PayloadTruncation(
        original_chars=n, kept_chars=max_chars, kept_start=start, kept_end=end, truncated=True
    )


def _wrap(header: str, body: str, truncation: PayloadTruncation) -> str:
    note = (
        f"\n\n[TRUNCATED: kept chars {truncation.kept_start}..{truncation.kept_end}"
        f" of {truncation.original_chars}]"
        if truncation.truncated
        else ""
    )
    return f"# {header}\n\n{body}{note}\n"


def raw_trajectory_payload(
    bundle: TaskBundle, transcript_text: str, *, max_chars: int
) -> ControlPayload:
    """M3: the bundle's raw transcript as injected context. Truncation to
    ``max_chars`` is recorded AND surfaced in the payload text — never silent.

    Truncation keeps the transcript TAIL, not the head (mem-io7c): a session opens
    by restating the task — which the probe already injects via instruction.md —
    and the resolution (the fix, the passing gates, the final diff) lands at the
    END. With p90 transcripts over the char budget, head-keep would keep the
    exploration and delete the resolution. Tail-only rather than a head+tail
    split, because the head's content is redundant with the injected instruction."""
    body, truncation = _truncate(transcript_text, max_chars, keep="tail")
    text = _wrap(f"Raw trajectory for {bundle.work_id}", body, truncation)
    return ControlPayload(condition=RAW_TRAJECTORY, text=text, truncation=truncation)


def full_context_payload(
    bundle: TaskBundle, in_scope: Mapping[str, InScopeWork], *, max_chars: int
) -> ControlPayload:
    """M4: all in-scope prior work, LOO-bounded. Records whose work_id is in
    ``loo_excluded_work_ids`` (own work + siblings) are withheld BY ID before the
    payload is built, so the LOO boundary is mechanical, not a content heuristic.

    Records are ordered by temporal proximity to the query work, most relevant
    first: every in-scope record closed strictly BEFORE the query work started
    (the LOO bound), so proximity is simply recency — latest ``closed_at`` first,
    work_id as the deterministic tiebreak. Head-keep truncation then drops the
    LEAST relevant records (mem-io7c), never the closest ones."""
    excluded = set(bundle.loo_excluded_work_ids)
    kept = {wid: work for wid, work in in_scope.items() if wid not in excluded}
    ordered = sorted(sorted(kept.items()), key=lambda kv: kv[1].closed_at, reverse=True)
    body = "\n\n".join(f"## {wid}\n{work.text}" for wid, work in ordered)
    body, truncation = _truncate(body, max_chars, keep="head")
    text = _wrap(f"Full in-scope prior work for {bundle.work_id}", body, truncation)
    return ControlPayload(condition=FULL_CONTEXT, text=text, truncation=truncation)


def assert_control_payload_clean(payload: ControlPayload, bundle: TaskBundle) -> None:
    """Run the probe leak guard on a control payload before it could be baked. A raw
    transcript / prior-work dump that quotes the gold diff, base_commit, or a
    verification marker raises ``OutcomeLeakError`` — the run fails loud, the payload
    is never silently scrubbed.

    The guard runs on the KEPT span (``payload.text``) — exactly what an agent could
    see; text the truncation dropped is never injected, so it cannot leak. This is a
    deliberate interaction with M3's tail-keep (mem-io7c): the tail is where the
    resolution — and so a gold-diff quote — is likeliest to live, so tail-keep makes
    the guard fire MORE often. That is the correct outcome: a ``leak_excluded``
    build is a first-class coverage signal, not a hole to paper over by keeping a
    span the guard would pass.

    ``probe_gate`` is imported lazily: it is the higher-level task-construction
    module (it owns the leak labels) and imports the payload builders here, so a
    module-level import the other way would cycle."""
    from membench.harbor.probe_gate import assert_probe_task_clean

    assert_probe_task_clean({_PAYLOAD_FILE: payload.text}, bundle)
