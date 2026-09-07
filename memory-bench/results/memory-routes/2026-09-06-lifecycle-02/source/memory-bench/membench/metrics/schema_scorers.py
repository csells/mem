"""S2 — deterministic scorers for schema induction + confabulation.

Both are pure arithmetic over token sets (no judge, no model) — the no-judge Tier-2
floor the premortem requires to ship day 1:

* ``schema_recall`` — fraction of the latent rule's salient tokens recovered by the
  union of the consolidated schema rows. ``recombine`` (which emits rule-bearing
  rows) scores high; ``dedupe_only`` (no schema rows) scores 0 — the decisive mode
  contrast.
* ``confabulation_findings`` — a schema row is confabulated if it asserts a salient
  token absent from EVERY source episode it cites (token re-derivability). A faithful
  recombination (shared-token summary) is 0 by construction; a fabricated claim is
  flagged. This feeds the safety_gates confabulation gate, which stays flag-and-
  quarantine until κ-calibration (B-2).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from membench.memory_systems.consolidation import ConsolidatedItem
from membench.schemas.sequence import BenchmarkSequence
from membench.signals import SalienceSignals


class ConfabulationFindings(BaseModel):
    """The deterministic confabulation readout: the rate, the offending row ids, and
    the claim count (so a 0-of-0 run is distinguishable from a 0-of-N clean run)."""

    model_config = ConfigDict(frozen=True)

    rate: float
    unverified_claim_ids: tuple[str, ...]
    n_claims: int


def episode_source_texts(seq: BenchmarkSequence) -> dict[str, str]:
    """The written-episode id → content map (the source set a schema row must be
    re-derivable from). This IS the source-trace set referenced by the S2 oracle."""
    return {
        mid: content for step in seq.steps for mid, content in step.expected_memory_writes.items()
    }


def schema_recall(
    latent_rule: str,
    items: Sequence[ConsolidatedItem],
    *,
    signals: SalienceSignals | None = None,
) -> float:
    """Fraction of the latent rule's salient tokens recovered by the union of the
    consolidated schema rows. 0.0 when no schema row was emitted."""
    sig = signals or SalienceSignals()
    rule_tokens = sig.tokenize(latent_rule)
    if not rule_tokens:
        return 0.0
    covered: set[str] = set()
    for item in items:
        covered |= sig.tokenize(item.content)
    return len(rule_tokens & covered) / len(rule_tokens)


def confabulation_findings(
    items: Sequence[ConsolidatedItem],
    source_texts: dict[str, str],
    *,
    signals: SalienceSignals | None = None,
) -> ConfabulationFindings:
    """Token-re-derivability proxy: a schema row is confabulated if any of its
    salient tokens is absent from the union of its cited source episodes' tokens."""
    sig = signals or SalienceSignals()
    unverified: list[str] = []
    for item in items:
        cited: set[str] = set()
        for tid in item.source_trace_ids:
            cited |= sig.tokenize(source_texts.get(tid, ""))
        if not sig.tokenize(item.content).issubset(cited):
            unverified.append(item.memory_id)
    rate = len(unverified) / len(items) if items else 0.0
    return ConfabulationFindings(
        rate=rate, unverified_claim_ids=tuple(unverified), n_claims=len(items)
    )
