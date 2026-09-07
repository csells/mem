"""The `ours` vs semantic-arm retrieval-quality bridge (mem-compare).

Why a bridge is needed: `ours` (`OursMemory`, replay-only) consumes
``RetrievalRequest.query_work`` and retrieves over the work-audit graph; the
semantic arms (`AbstractSemanticArm`: mem0 / a-mem / …) consume
``RetrievalRequest.query_text`` and retrieve over whatever was *written* into their
per-trial scope. Each raises if handed the other family's request. To compare them
head-to-head we put both on ONE task surface:

- the harness LOO-bounded set (`validity.loo_bounded`) is the corpus for both arms;
- `ours` runs through the existing `replay.replay_arm` (no reimplementation);
- the semantic arm is **seeded** with the same LOO set, then queried with a
  `query_text` derived from `B`; both arms' work_ids are scored against one
  authored relevant set and re-checked with `assert_no_leak`.

The id-translation wrinkle: a semantic backend mints its OWN id per write
(`semantic_base.AbstractSemanticArm.write` records ``written_ids``) and keys its
hits off it (`retrieve` payloads), NOT the work_id. So seeding captures a
``backend_id -> work_id`` map and retrieval is translated back through it before any
scoring or leak-check — otherwise every hit would read as an "unknown id" leak.

ZFC: pure mechanism. The relevant set is EXPLICIT INPUT (authored ground truth),
never derived here from either arm's retrieval mechanism — deriving it from one
arm's signature/embedding would silently bias the comparison toward that arm.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from membench.grading.retrieval_leg import RetrievalTarget, score_retrieval_leg
from membench.memory_systems.base import MemorySystem, RetrievalRequest
from membench.replay import replay_arm
from membench.runtime import IdClock, StepContext
from membench.validity import QueryWork, WorkRef, assert_no_leak, loo_bounded

# `ours` is dual-track (Decision 7); the headline comparison fixes one track so the
# two arms line up 1:1. cross_rig is the strict/headline track (retrieve.ts SCOPES).
DEFAULT_OURS_SCOPE = "cross_rig"


@dataclass(frozen=True)
class ArmHarvest:
    """One arm's RAW retrieve-once result for one query — what the arm returned,
    already translated to work_ids and LOO re-checked, but NOT yet scored.

    This is the single retrieve-once product (mem-lvp.30): the same ``retrieved_ids``
    feed BOTH the equal-depth pooler and the per-arm scoring, so an arm can never be
    pooled on one retrieval and scored on a second (the desync this split removes)."""

    arm: str
    scope: str | None
    retrieved_ids: list[str]
    injected_context_chars: int
    latency_ms: float
    retrieval_truncated: bool
    leak_checked: bool


class ArmComparison(BaseModel):
    """One arm's retrieval-quality readout for one query work. Metric fields are
    ``None`` when the relevant set is empty (not measured) — never a fabricated
    ``0.0`` (mirrors `grading.retrieval_leg.RetrievalLeg`).

    HARD RULE (mem-lvp eval design, mem-lvp.29/.31): the relevant set these metrics
    are scored against must come from a semantic judge over candidate TEXT, never
    from any arm's id-set, failure signature, or structured match — deriving it from
    `ours`'s own retrieval mechanism would make the comparison circular."""

    model_config = ConfigDict(frozen=True)

    arm: str
    scope: str | None
    # The arm's retrieved set, already translated to work_ids (semantic backend ids
    # mapped back) so both arms are reported in the same id space.
    retrieved_ids: list[str]
    precision: float | None
    # POOL-RELATIVE recall when the relevant set is a pooled+judged ground truth
    # (mem-lvp.30/.32): an item NO arm retrieved is never pooled, never judged, and
    # so absent from the denominator. It is recall-within-pool, not recall against
    # the true (unknowable) relevant set — never report it as the latter.
    recall: float | None
    mrr: float | None
    ndcg: float | None
    # Decision-10 precision guard: outcome lift is gameable by over-injection, so
    # the injected-context volume is reported alongside, never hidden.
    injected_context_chars: int
    latency_ms: float
    # True once the arm's output passed the harness LOO re-check (`assert_no_leak`).
    leak_checked: bool
    # The arm's retrieval hit its FTS candidate-scan cap (ours), so the retrieved set
    # may be incomplete — surfaced per Decision 10, never scored as if complete. A
    # vector arm's top_k is a deliberate bound, not a truncation, so it stays False.
    retrieval_truncated: bool


class ComparisonResult(BaseModel):
    """Both arms on one query work, plus the shared denominators that make the
    per-arm metrics interpretable and the pinned model identity (V2 confound)."""

    model_config = ConfigDict(frozen=True)

    work_id: str
    retrieval_target: RetrievalTarget
    # Size of the scope-filtered candidate pool both arms drew from (LOO-eligible ∩
    # the track's rig predicate) — distinguishes an empty result from an empty pool.
    eligible_count: int
    # Size of the authored relevant set after intersecting with the LOO set.
    relevant_count: int
    arms: list[ArmComparison]
    # The equal-depth contribution `D` (mem-lvp.30): EXACTLY top-D from each arm was
    # pooled, regardless of native length, removing the ours-uncapped / semantic-top_k
    # contribution bias. Recorded so a downstream judge's denominator is reproducible.
    pool_depth: int
    # The shared pooled+deduped candidate set both arms drew from, in the order the
    # judge will see it. The shuffle severs position→arm provenance (no arm's items
    # cluster at the top), so the seed is recorded to make that order reproducible.
    pooled_candidates: list[str]
    shuffle_seed: int | None
    # `LocalModelStack.telemetry_dict()` — which models produced the semantic side.
    stack_telemetry: dict[str, str]


def _scope_eligible(eligible: Sequence[WorkRef], query: QueryWork, scope: str) -> list[WorkRef]:
    """The candidate pool BOTH arms draw from under one Decision-7 track: the
    LOO-eligible records filtered by the track's rig predicate, matching what `ours`
    applies internally (retrieve.ts SCOPES). ``cross_rig`` = other rigs only (the
    strict generalization track); ``same_rig_temporal`` = the query's rig only.

    Seeding the semantic arm from THIS pool — not the full LOO set — is what keeps the
    comparison fair: a same-rig record `ours` could never surface on ``cross_rig`` must
    not be reachable by the semantic arm either, or the two arms would be answering
    over different candidate sets and the retrieval-mechanism question is confounded
    with a candidate-pool difference."""
    if scope == "cross_rig":
        return [ref for ref in eligible if ref.rig != query.rig]
    if scope == "same_rig_temporal":
        return [ref for ref in eligible if ref.rig == query.rig]
    raise ValueError(f"unknown scope {scope!r}; expected cross_rig or same_rig_temporal")


def _relevant_within_pool(relevant_ids: Iterable[str], pool: Sequence[WorkRef]) -> tuple[str, ...]:
    """Intersect the authored relevant set with the candidate pool. A relevant id
    outside the pool — LOO-withheld, or the wrong rig for this track — is unreachable
    by construction, so counting it in the recall denominator would understate every
    arm equally and falsely (mirrors `grading.retrieval_leg.gold_relevant_ids`
    subtracting the excluded set)."""
    pool_ids = {ref.work_id for ref in pool}
    return tuple(sorted(set(relevant_ids) & pool_ids))


def seed_semantic_arm(
    arm: MemorySystem,
    eligible: Sequence[WorkRef],
    corpus_text: Mapping[str, str],
    ctx: StepContext,
) -> dict[str, str]:
    """Write each LOO-eligible record's text into ``arm`` under ``ctx.trial_id`` and
    return the ``backend_id -> work_id`` map captured from the write events.

    A missing text entry RAISES: a silently-skipped seed would hand the semantic arm
    a smaller corpus than `ours` sees and quietly bias the comparison. The map is the
    only way to translate the arm's backend-keyed hits back to work_ids."""
    backend_to_work: dict[str, str] = {}
    for ref in eligible:
        text = corpus_text.get(ref.work_id)
        if text is None:
            raise ValueError(
                f"no corpus_text for eligible work_id {ref.work_id!r}; cannot seed the "
                "semantic arm without it (a skipped seed silently biases the comparison)."
            )
        event = arm.write(ref.work_id, text, ctx)
        if not event.written_ids:
            raise ValueError(
                f"semantic arm {arm.name!r} returned no written_ids for {ref.work_id!r}; "
                "cannot map its backend id back to the work_id."
            )
        backend_to_work[event.written_ids[0]] = ref.work_id
    return backend_to_work


def harvest_semantic(
    arm: MemorySystem,
    query: QueryWork,
    query_text: str,
    corpus: Sequence[WorkRef],
    corpus_text: Mapping[str, str],
    *,
    scope: str = DEFAULT_OURS_SCOPE,
    clock: IdClock | None = None,
) -> ArmHarvest:
    """Seed ``arm`` with the scope-filtered candidate pool (the same pool `ours` draws
    from under ``scope``), query it ONCE with ``query_text``, translate its
    backend-keyed hits to work_ids, and re-check the boundary. No scoring — the
    returned ids are the single retrieve-once product shared by pooling and scoring."""
    pool = _scope_eligible(loo_bounded(corpus, query), query, scope)
    trial_id = f"{query.work_id}-{arm.name}-{scope}"
    arm.reset(trial_id)

    # Separate clock for seeding so the seed writes never perturb the retrieve event's
    # ids/latency (the conditions.py seeding convention).
    seed_ctx = StepContext(
        trial_id=trial_id, session_id=query.work_id, step_id="seed", clock=IdClock()
    )
    backend_to_work = seed_semantic_arm(arm, pool, corpus_text, seed_ctx)

    ctx = StepContext(
        trial_id=trial_id,
        session_id=query.work_id,
        step_id="replay",
        clock=clock or IdClock(),
    )
    result = arm.retrieve(RetrievalRequest(query_text=query_text), ctx)

    # Translate backend ids -> work_ids. An unmapped id stays as-is so it surfaces as
    # an "unknown id" leak in assert_no_leak rather than being silently dropped.
    retrieved_work_ids = [backend_to_work.get(bid, bid) for bid in result.payloads]
    assert_no_leak(retrieved_work_ids, corpus, query)
    return ArmHarvest(
        arm=arm.name,
        scope=scope,
        retrieved_ids=retrieved_work_ids,
        injected_context_chars=sum(len(v) for v in result.payloads.values()),
        latency_ms=result.event.latency_ms,
        retrieval_truncated=result.fts_truncated,
        leak_checked=True,
    )


def harvest_ours(
    arm: MemorySystem,
    query: QueryWork,
    corpus: list[WorkRef],
    *,
    scope: str = DEFAULT_OURS_SCOPE,
) -> ArmHarvest:
    """Run `ours` ONCE through the existing `replay.replay_arm` (which already
    re-checks the boundary) and return its work_ids unscored — the retrieve-once
    product shared by pooling and scoring."""
    r = replay_arm(arm, query, corpus, scope=scope)
    return ArmHarvest(
        arm=r.arm,
        scope=r.scope,
        retrieved_ids=r.retrieved_ids,
        injected_context_chars=r.injected_context_chars,
        latency_ms=r.latency_ms,
        retrieval_truncated=r.fts_truncated,
        leak_checked=True,
    )


def score_harvest(
    harvest: ArmHarvest,
    relevant_ids: Sequence[str],
    *,
    target: RetrievalTarget = "canonical",
) -> ArmComparison:
    """Score an already-harvested arm against ``relevant_ids`` — no second retrieval.
    The scored ids are exactly ``harvest.retrieved_ids`` (the retrieve-once contract,
    mem-lvp.30: scored == harvested)."""
    leg = score_retrieval_leg(harvest.retrieved_ids, relevant_ids, target=target)
    return ArmComparison(
        arm=harvest.arm,
        scope=harvest.scope,
        retrieved_ids=harvest.retrieved_ids,
        precision=leg.precision,
        recall=leg.recall,
        mrr=leg.mrr,
        ndcg=leg.ndcg,
        injected_context_chars=harvest.injected_context_chars,
        latency_ms=harvest.latency_ms,
        leak_checked=harvest.leak_checked,
        retrieval_truncated=harvest.retrieval_truncated,
    )


def semantic_replay(
    arm: MemorySystem,
    query: QueryWork,
    query_text: str,
    corpus: Sequence[WorkRef],
    corpus_text: Mapping[str, str],
    *,
    relevant_ids: Sequence[str],
    scope: str = DEFAULT_OURS_SCOPE,
    target: RetrievalTarget = "canonical",
    clock: IdClock | None = None,
) -> ArmComparison:
    """Harvest the semantic arm once, then score it — the single-arm convenience over
    `harvest_semantic` + `score_harvest`. ``relevant_ids`` is taken as already
    pool-intersected by the caller."""
    harvest = harvest_semantic(
        arm, query, query_text, corpus, corpus_text, scope=scope, clock=clock
    )
    return score_harvest(harvest, relevant_ids, target=target)


def ours_replay(
    arm: MemorySystem,
    query: QueryWork,
    corpus: list[WorkRef],
    *,
    relevant_ids: Sequence[str],
    scope: str = DEFAULT_OURS_SCOPE,
    target: RetrievalTarget = "canonical",
) -> ArmComparison:
    """Harvest `ours` once, then score it — the single-arm convenience over
    `harvest_ours` + `score_harvest`."""
    harvest = harvest_ours(arm, query, corpus, scope=scope)
    return score_harvest(harvest, relevant_ids, target=target)


def pool_candidates(
    arm_runs: Sequence[ArmHarvest],
    *,
    depth: int,
    shuffle_seed: int | None = None,
) -> tuple[str, ...]:
    """The equal-depth candidate pool: EXACTLY the top-``depth`` work_ids from EACH
    arm (mem-lvp.30), deduped across arms in first-seen order, regardless of any
    arm's native retrieval length.

    Symmetric contribution is the whole point: `ours` returning far more than
    ``depth`` is truncated to its first ``depth`` ids, identically to a semantic arm
    whose backend already caps at ``top_k=depth`` — so neither arm dominates the
    judge's candidate set by sheer volume.

    With ``shuffle_seed`` the final order is permuted under a seeded RNG so candidate
    POSITION carries no arm provenance to a downstream judge; the membership is
    unchanged. The seed is the caller's to record."""
    if depth < 1:
        raise ValueError(f"depth must be >= 1, got {depth}")
    pooled: list[str] = []
    seen: set[str] = set()
    for run in arm_runs:
        for work_id in run.retrieved_ids[:depth]:
            if work_id not in seen:
                seen.add(work_id)
                pooled.append(work_id)
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(pooled)
    return tuple(pooled)


def _assert_pool_in_corpus_text(pooled: Sequence[str], corpus_text: Mapping[str, str]) -> None:
    """Every pooled work_id MUST resolve to corpus_text — that text is the judge's
    only input. A pooled id with no text would be silently un-judgeable, biasing the
    pooled-relative denominator; fail loud instead (mirrors `seed_semantic_arm`)."""
    missing = [wid for wid in pooled if wid not in corpus_text]
    if missing:
        raise ValueError(
            f"pooled work_ids missing from corpus_text: {missing!r}; every pooled "
            "candidate must have judgeable text (a silent drop biases the denominator)."
        )


def compare_arms(
    query: QueryWork,
    query_text: str,
    corpus: list[WorkRef],
    corpus_text: Mapping[str, str],
    *,
    ours: MemorySystem,
    semantic: MemorySystem,
    relevant_ids: Sequence[str],
    pool_depth: int,
    scope: str = DEFAULT_OURS_SCOPE,
    target: RetrievalTarget = "canonical",
    shuffle_seed: int | None = None,
    stack_telemetry: Mapping[str, str] | None = None,
) -> ComparisonResult:
    """Compare `ours` against one semantic arm on a single query work, scoring both
    against the same relevant set, drawn from the same scope-filtered candidate pool,
    under the same LOO boundary.

    Each arm is retrieved EXACTLY ONCE (`harvest_*`); the harvested ids feed both the
    equal-depth ``pool_candidates`` (EXACTLY top-``pool_depth`` per arm) and the
    per-arm scoring, so pooled == scored (mem-lvp.30). Every pooled id is asserted to
    have judgeable text before any relevant_ids enter scoring.

    ``relevant_ids`` MUST be an authored / pooled+judged relevant set over candidate
    TEXT (mem-lvp.31), never derived from any arm's signature or structured match —
    the circularity HARD RULE."""
    pool = _scope_eligible(loo_bounded(corpus, query), query, scope)
    relevant = _relevant_within_pool(relevant_ids, pool)

    harvests = [
        harvest_ours(ours, query, corpus, scope=scope),
        harvest_semantic(semantic, query, query_text, corpus, corpus_text, scope=scope),
    ]
    pooled = pool_candidates(harvests, depth=pool_depth, shuffle_seed=shuffle_seed)
    _assert_pool_in_corpus_text(pooled, corpus_text)
    # The judged set is the pooled set (mem-lvp.32 will hand `pooled` to the judge);
    # the relevant set entering scoring must be a subset of that judged domain, else a
    # "relevant" id no arm pooled would inflate recall against an item never judged.
    if not set(relevant) <= set(pooled):
        raise ValueError(
            "judged-set domain mismatch: relevant_ids "
            f"{sorted(set(relevant) - set(pooled))!r} are not in the pooled candidate "
            "set; the relevant set must be a subset of the pooled+judged domain."
        )

    arms = [score_harvest(h, relevant, target=target) for h in harvests]
    return ComparisonResult(
        work_id=query.work_id,
        retrieval_target=target,
        eligible_count=len(pool),
        relevant_count=len(relevant),
        arms=arms,
        pool_depth=pool_depth,
        pooled_candidates=list(pooled),
        shuffle_seed=shuffle_seed,
        stack_telemetry=dict(stack_telemetry or {}),
    )
