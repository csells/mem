"""Pool -> judge -> relevant_ids glue + the judged-relevance artifact (mem-lvp.32).

This is the single seam that turns the mechanism pooler (mem-lvp.30) and the model
relevance judge (mem-lvp.31) into the ``dict{query_work_id -> [work_id]}`` that
`io.load_relevance` returns and `retrieval_compare.compare_arms` consumes — so a
real run no longer hand-authors ``relevance.json``: it is *derived* from the judge
over the pooled candidate union, with the judge identity recorded for the V2
confound.

The flow per query ``B``:

1. **Harvest once** — run `ours` and the semantic arm through the .30
   ``harvest_*`` helpers (retrieve-once; pooled == scored).
2. **Pool** — ``pool_candidates`` takes EXACTLY top-D from each arm; the union at
   depth ``D`` is the *only* set judged, so the judge budget is bounded by
   construction (candidates/query ≤ |pool|).
3. **Judge each pooled candidate** — ``score_relevance`` over the .31 seam answers
   "would consulting this past work help solve B?". A per-pair cache keyed on
   (query, candidate, prompt_version, judge_model) means an overlapping pool or a
   re-run never re-pays for a verdict.
4. **Emit** — the candidates the judge marked relevant become ``relevant_ids[B]``,
   the exact shape `compare_arms` already takes.

Resumability: every verdict is appended to a JSONL cache the moment it is produced
(one pair per line, `PairCache`), so a crash mid-run resumes from the cache with no
total loss and no re-payment. The self-describing artifact (`JudgedRelevance.write`)
freezes ``pool_depth``, ``judge_model``, ``prompt_version``, the emitted
``relevant_ids``, and every per-pair verdict+rationale to one JSON blob.

Fail loud, end to end: a dead judge raises `LocalStackUnavailableError` (no paid-API
fallback); a malformed reply raises `RelevanceJudgeError`; a transient ``TimeoutError``
is retried EXACTLY ONCE and then surfaced (no hiding loop). None of these are
swallowed or coerced to a default verdict.

ZFC: the relevance decision IS the delegated model judgment (the judge). This
module's own code is pure mechanism — harvest orchestration, pooling, a deterministic
cache, IO, and a bounded retry policy.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from membench.bbon.comparative_judge import ComparativeJudge
from membench.compare.relevance_judge import (
    DEFAULT_PROMPT_VERSION,
    RelevanceInputs,
    RelevanceMode,
    RelevanceResult,
    relevance_cache_key,
    score_relevance,
)
from membench.compare.retrieval_compare import (
    DEFAULT_OURS_SCOPE,
    harvest_ours,
    harvest_semantic,
    pool_candidates,
)
from membench.memory_systems.base import MemorySystem
from membench.runtime import IdClock
from membench.validity import QueryWork, WorkRef

# A transient ``TimeoutError`` from the judge backend is retried EXACTLY this many
# extra times before the failure is surfaced. One retry absorbs a single flaky
# daemon/CLI hiccup without becoming a failure-hiding loop.
JUDGE_RETRIES = 1


@dataclass(frozen=True)
class JudgedPair:
    """One (query, candidate) verdict — the per-pair cache record and artifact row.

    ``relevant`` is the binary verdict (``None`` in graded mode); ``grade`` the graded
    verdict (``None`` in binary mode). The pair is fully self-describing so the JSONL
    cache line, replayed on resume, reconstructs the verdict without re-judging."""

    query_work_id: str
    candidate_work_id: str
    relevant: bool | None
    grade: int | None
    transferable_lesson: str
    rationale: str
    cache_key: str

    def to_row(self) -> dict[str, Any]:
        return {
            "query_work_id": self.query_work_id,
            "candidate_work_id": self.candidate_work_id,
            "relevant": self.relevant,
            "grade": self.grade,
            "transferable_lesson": self.transferable_lesson,
            "rationale": self.rationale,
            "cache_key": self.cache_key,
        }

    @classmethod
    def from_result(
        cls, query_work_id: str, candidate_work_id: str, result: RelevanceResult
    ) -> JudgedPair:
        v = result.verdict
        return cls(
            query_work_id=query_work_id,
            candidate_work_id=candidate_work_id,
            relevant=v.relevant,
            grade=v.grade,
            transferable_lesson=v.transferable_lesson,
            rationale=v.rationale,
            cache_key=result.cache_key,
        )

    def is_relevant(self) -> bool:
        """A pair counts toward ``relevant_ids`` if the binary verdict is true, or the
        graded verdict is positive (any grade > 0 = some useful transfer)."""
        if self.relevant is not None:
            return self.relevant
        return self.grade is not None and self.grade > 0


def _row_to_pair(row: dict[str, Any]) -> JudgedPair:
    """Reconstruct a `JudgedPair` from a cache JSONL row, validating shape at the
    boundary — a corrupt cache line fails loud rather than silently dropping a verdict."""
    relevant = row.get("relevant")
    grade = row.get("grade")
    if relevant is not None and not isinstance(relevant, bool):
        raise ValueError(f"cache row 'relevant' must be bool or null: {relevant!r}")
    if grade is not None and (isinstance(grade, bool) or not isinstance(grade, int)):
        raise ValueError(f"cache row 'grade' must be int or null: {grade!r}")
    return JudgedPair(
        query_work_id=str(row["query_work_id"]),
        candidate_work_id=str(row["candidate_work_id"]),
        relevant=relevant,
        grade=grade,
        transferable_lesson=str(row["transferable_lesson"]),
        rationale=str(row["rationale"]),
        cache_key=str(row["cache_key"]),
    )


class PairCache:
    """A resumable per-pair verdict cache backed by an append-only JSONL file.

    Each judged pair is appended as ONE line the instant it is produced, so a crash
    mid-run resumes from whatever was already written — never a total loss. On
    construction the existing file (if any) is read into an in-memory ``cache_key ->
    JudgedPair`` index, so a re-run skips every pair already on disk and re-pays for
    none of them. A duplicate cache_key on disk keeps the first occurrence (verdicts
    for a given key are deterministic, so later lines are redundant)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._index: dict[str, JudgedPair] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                pair = _row_to_pair(json.loads(line))
                self._index.setdefault(pair.cache_key, pair)

    def get(self, cache_key: str) -> JudgedPair | None:
        return self._index.get(cache_key)

    def put(self, pair: JudgedPair) -> None:
        """Record ``pair`` in memory and append it to disk immediately. A cache_key
        already present is a no-op (the verdict is deterministic), so a resumed run
        never duplicates a line."""
        if pair.cache_key in self._index:
            return
        self._index[pair.cache_key] = pair
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(pair.to_row(), sort_keys=True) + "\n")


@dataclass(frozen=True)
class JudgedRelevance:
    """The judged-relevance artifact: the pooled candidate union per query, every
    per-pair verdict, the emitted ``relevant_ids``, and the judge identity.

    Self-describing and frozen to disk (`write`): ``pool_depth``, ``judge_model``,
    ``prompt_version``, the ``relevant_ids`` mapping, and every per-pair
    verdict+rationale ride in one JSON blob, so a downstream consumer can reproduce
    the denominator and audit each call without the live judge."""

    pool_depth: int
    judge_model: str
    prompt_version: str
    pooled: dict[str, list[str]]
    pairs: list[JudgedPair]
    judged_pairs: int
    base_telemetry: Mapping[str, str] = field(default_factory=dict)

    def relevant_ids(self) -> dict[str, list[str]]:
        """The ``dict{query_work_id -> [work_id]}`` `io.load_relevance` returns and
        `compare_arms` consumes: per query, the pooled candidates the judge marked
        relevant, in pooled order."""
        relevant: dict[str, set[str]] = {q: set() for q in self.pooled}
        for pair in self.pairs:
            if pair.is_relevant():
                relevant[pair.query_work_id].add(pair.candidate_work_id)
        return {q: [c for c in pool if c in relevant[q]] for q, pool in self.pooled.items()}

    def telemetry(self) -> dict[str, str]:
        """The semantic-stack telemetry MERGED with the JUDGE identity (V2 confound):
        ``judge_model`` and ``judge_prompt_version`` are added so the recorded
        provenance covers the judge that produced the relevant set, not only the
        semantic arm. Pass the result as ``compare_arms(stack_telemetry=...)``."""
        return {
            **dict(self.base_telemetry),
            "judge_model": self.judge_model,
            "judge_prompt_version": self.prompt_version,
        }

    def write(self, path: Path) -> None:
        """Freeze the artifact to one self-describing JSON blob."""
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = {
            "pool_depth": self.pool_depth,
            "judge_model": self.judge_model,
            "prompt_version": self.prompt_version,
            "judged_pairs": self.judged_pairs,
            "relevant_ids": self.relevant_ids(),
            "pooled": self.pooled,
            "pairs": [pair.to_row() for pair in self.pairs],
        }
        path.write_text(json.dumps(blob, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _judge_one_pair(
    inp: RelevanceInputs,
    judge: ComparativeJudge,
    *,
    mode: RelevanceMode,
    prompt_version: str,
) -> RelevanceResult:
    """Judge one pair with a bounded retry policy. A transient ``TimeoutError`` is
    retried EXACTLY ``JUDGE_RETRIES`` times and then re-raised (no hiding loop). Every
    other failure — a dead judge (`LocalStackUnavailableError`) or a malformed reply
    (`RelevanceJudgeError`) — propagates immediately, never retried, never swallowed."""
    attempts = JUDGE_RETRIES + 1
    last: TimeoutError | None = None
    for _ in range(attempts):
        try:
            return score_relevance(inp, judge, mode=mode, prompt_version=prompt_version)
        except TimeoutError as exc:
            last = exc
    assert last is not None  # the loop ran ≥1 time and only TimeoutError reaches here
    raise last


def _candidate_inputs(
    query: QueryWork,
    query_text: str,
    candidate_work_id: str,
    corpus_text: Mapping[str, str],
) -> RelevanceInputs:
    """Assemble the neutral (query_text, candidate_text) projection for one pooled
    candidate, plus B's high-entropy identifiers for the assembled-prompt leak scan.
    A pooled candidate with no text raises (`compare_arms` already asserts this, but
    the glue judges before that call, so it must guard here too)."""
    candidate_text = corpus_text.get(candidate_work_id)
    if candidate_text is None:
        raise ValueError(
            f"pooled candidate {candidate_work_id!r} has no corpus_text; every judged "
            "candidate must have judgeable text."
        )
    return RelevanceInputs(
        query_work_id=query.work_id,
        candidate_work_id=candidate_work_id,
        query_text=query_text,
        candidate_text=candidate_text,
        b_work_id=query.work_id,
        b_pr=query.pr,
        b_external_ref=query.external_ref,
    )


def harvest_and_judge(
    query: QueryWork,
    query_text: str,
    corpus: list[WorkRef],
    corpus_text: Mapping[str, str],
    *,
    ours: MemorySystem,
    semantic: MemorySystem,
    pool_depth: int,
    judge: ComparativeJudge,
    cache: PairCache,
    scope: str = DEFAULT_OURS_SCOPE,
    mode: RelevanceMode = "binary",
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    shuffle_seed: int | None = None,
    stack_telemetry: Mapping[str, str] | None = None,
) -> JudgedRelevance:
    """Harvest both arms ONCE, pool to depth ``pool_depth``, judge every pooled
    candidate against ``query``, and assemble the `JudgedRelevance` artifact whose
    ``relevant_ids()`` drops straight into `compare_arms`.

    The judge budget is the pooled union at depth ``D`` — every candidate is judged
    exactly once, with a hit on ``cache`` skipping the call. Each fresh verdict is
    persisted to ``cache`` the moment it is produced (resumable). The judge identity
    and ``prompt_version`` are carried into the artifact telemetry for the V2 confound."""
    harvests = [
        harvest_ours(ours, query, corpus, scope=scope),
        harvest_semantic(
            semantic, query, query_text, corpus, corpus_text, scope=scope, clock=IdClock()
        ),
    ]
    pooled = pool_candidates(harvests, depth=pool_depth, shuffle_seed=shuffle_seed)

    pairs: list[JudgedPair] = []
    judged = 0
    for candidate_work_id in pooled:
        key = relevance_cache_key(query.work_id, candidate_work_id, prompt_version, judge.model)
        cached = cache.get(key)
        if cached is not None:
            pairs.append(cached)
            continue
        inp = _candidate_inputs(query, query_text, candidate_work_id, corpus_text)
        result = _judge_one_pair(inp, judge, mode=mode, prompt_version=prompt_version)
        pair = JudgedPair.from_result(query.work_id, candidate_work_id, result)
        cache.put(pair)  # persist BEFORE appending to the in-memory list — resumable
        pairs.append(pair)
        judged += 1

    return JudgedRelevance(
        pool_depth=pool_depth,
        judge_model=judge.model,
        prompt_version=prompt_version,
        pooled={query.work_id: list(pooled)},
        pairs=pairs,
        judged_pairs=judged,
        base_telemetry=dict(stack_telemetry or {}),
    )


def judge_relevance(
    queries: Sequence[tuple[QueryWork, str]],
    corpus: list[WorkRef],
    corpus_text: Mapping[str, str],
    *,
    ours: MemorySystem,
    semantic: MemorySystem,
    pool_depth: int,
    judge: ComparativeJudge,
    cache: PairCache,
    scope: str = DEFAULT_OURS_SCOPE,
    mode: RelevanceMode = "binary",
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    shuffle_seed: int | None = None,
    stack_telemetry: Mapping[str, str] | None = None,
) -> JudgedRelevance:
    """Run `harvest_and_judge` over many queries, merging their pooled sets and
    per-pair verdicts into ONE artifact whose ``relevant_ids()`` spans every query —
    the driver's pooled-judge mode. The shared ``cache`` resumes across queries."""
    pooled: dict[str, list[str]] = {}
    pairs: list[JudgedPair] = []
    judged = 0
    base = dict(stack_telemetry or {})
    for query, query_text in queries:
        one = harvest_and_judge(
            query,
            query_text,
            corpus,
            corpus_text,
            ours=ours,
            semantic=semantic,
            pool_depth=pool_depth,
            judge=judge,
            cache=cache,
            scope=scope,
            mode=mode,
            prompt_version=prompt_version,
            shuffle_seed=shuffle_seed,
            stack_telemetry=base,
        )
        pooled.update(one.pooled)
        pairs.extend(one.pairs)
        judged += one.judged_pairs

    return JudgedRelevance(
        pool_depth=pool_depth,
        judge_model=judge.model,
        prompt_version=prompt_version,
        pooled=pooled,
        pairs=pairs,
        judged_pairs=judged,
        base_telemetry=base,
    )
