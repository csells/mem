"""Shuffled/placebo memory condition (mem-hhto) — deterministic donor selection.

No probe condition injects equal-volume IRRELEVANT memory, so an ``ours`` win over
``none-clean`` is still consistent with "any authoritative-looking prior-session
text changes behavior" — content attribution stays open. The ``shuffled`` condition
closes it: the SAME clean-room base, rendering, and leak guards as ``ours``, but the
injected payload is the ours payload retrieved for a DIFFERENT bundle. If shuffled
moves the metric like ours does, the win was volume, not content.

This module is the selection core only (pure, CI-testable); task construction
reuses `build_probe_task`'s existing `inject_context` / `_bake_memory_into_env`
path verbatim. Selection is deterministic given the bundle set — no randomness,
input-order independent:

- donors come from a DIFFERENT repo, so the placebo is not partially relevant
  (a same-rig retrieval payload talks about the recipient's own codebase);
- among other-repo donors the pick volume-matches: the closest rendered payload
  size to the recipient's own ours payload, ties broken by donor work_id;
- when no other-repo donor with a non-empty payload exists, selection falls back
  to same-repo donors and RECORDS the reason — a potentially partially-relevant
  placebo is flagged in provenance, never silent.

The returned `ShuffledSelection` is the provenance record `build_probe_task`
persists (``shuffled-donor.json`` + the task.toml metadata), so analysis can
verify each run's donor irrelevance.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from membench.schemas.bundle import TaskBundle

SHUFFLED = "shuffled"

SAME_REPO_FALLBACK_REASON = (
    "no other-repo donor with a non-empty ours payload; volume-matched among "
    "same-repo donors — the placebo may be partially relevant"
)


def payload_chars(payloads: Mapping[str, str]) -> int:
    """A payload set's rendered volume: the char count of the exact text
    `build_probe_task` writes to ``memory/MEMORY.md`` (newline-joined values)."""
    return len("\n".join(payloads.values()))


class ShuffledSelection(BaseModel):
    """One recipient's donor pick + the volume-match accounting — the provenance
    record analysis reads to verify the injected placebo was irrelevant."""

    model_config = ConfigDict(frozen=True)

    work_id: str  # the recipient bundle
    donor_work_id: str
    recipient_repo: str
    donor_repo: str
    recipient_chars: int = Field(ge=0)
    donor_chars: int = Field(ge=0)
    # None when the other-repo constraint held; otherwise the recorded reason the
    # donor came from the recipient's own repo.
    fallback_reason: str | None = None


def select_donor(
    bundle: TaskBundle,
    bundles: Sequence[TaskBundle],
    payloads: Mapping[str, Mapping[str, str]],
) -> ShuffledSelection:
    """Pick ``bundle``'s placebo donor from ``bundles`` given each bundle's ours
    payload set (``payloads``: work_id -> source-id -> rendered payload).

    Candidates exclude the recipient itself, its LOO-excluded ids, any bundle
    that LOO-excludes the recipient (shared work), and empty-payload bundles.
    An empty RECIPIENT payload is a caller bug: there is no volume to match —
    such bundles reuse the ``none-clean`` run, exactly as the ours arm does."""
    recipient_payload = payloads.get(bundle.work_id) or {}
    if not recipient_payload:
        raise ValueError(
            f"{bundle.work_id}: the shuffled condition volume-matches the recipient's own "
            "ours payload; an empty retrieval has no volume to match (reuse the none-clean "
            "run, as the ours arm does)"
        )
    excluded = set(bundle.loo_excluded_work_ids) | {bundle.work_id}
    candidates = [
        donor
        for donor in bundles
        if donor.work_id not in excluded
        and bundle.work_id not in donor.loo_excluded_work_ids
        and payloads.get(donor.work_id)
    ]
    if not candidates:
        raise ValueError(
            f"{bundle.work_id}: no donor bundle with a non-empty ours payload in the set"
        )
    other_repo = [donor for donor in candidates if donor.env.repo != bundle.env.repo]
    pool, fallback_reason = (
        (other_repo, None) if other_repo else (candidates, SAME_REPO_FALLBACK_REASON)
    )
    target = payload_chars(recipient_payload)
    donor = min(pool, key=lambda b: (abs(payload_chars(payloads[b.work_id]) - target), b.work_id))
    return ShuffledSelection(
        work_id=bundle.work_id,
        donor_work_id=donor.work_id,
        recipient_repo=bundle.env.repo,
        donor_repo=donor.env.repo,
        recipient_chars=target,
        donor_chars=payload_chars(payloads[donor.work_id]),
        fallback_reason=fallback_reason,
    )
