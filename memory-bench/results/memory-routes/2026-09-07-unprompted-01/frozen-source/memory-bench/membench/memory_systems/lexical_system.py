"""`lexical` — a deterministic query/top-k retrieval arm (§7; the Confusion/Staleness probe).

Unlike the id-exact reference arms (`oracle`, `filesystem`), which return precisely the
ids the harness requested, this arm RANKS the whole store by token-overlap against the
step's ``query_text`` and returns the top-k — so it can (and does) surface seeded
distractors and superseded v1 entries as competitors. That is what makes
``distractor_retrieval_rate`` (Confusion) and ``stale_memory_retrieval_rate`` (Staleness)
non-zero for this arm while they stay 0 for the exact arms (mem-zt1c).

The ranking is mechanical and deterministic: integer token-overlap, ties broken by id
(ascending). This is the calibrated-similarity / explicit-tiebreaker exception the ZFC
boundary allows (patterns.md §ZFC) — there is no semantic judgement here. Token overlap
deliberately CANNOT separate a distractor from the truth (both name the same subject; the
distinguishing value is absent from the query), which is exactly the stressor's hardness:
a smarter (supersession-aware / semantic) arm is the lever that drives the rate back down,
not this baseline.
"""

import re
from pathlib import Path

from membench.memory_systems.base import (
    MemorySystem,
    RetrievalRequest,
    RetrieveResult,
    validate_top_k,
)
from membench.runtime import StepContext
from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation

DEFAULT_TOP_K = 10
_WORD = re.compile(r"\w+")


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens. A set: overlap is membership, not frequency, so a
    repeated word cannot inflate a single item's score."""
    return {m.group(0) for m in _WORD.finditer(text.lower())}


class LexicalTopKMemory(MemorySystem):
    name = "lexical"
    backend = MemoryBackend.FILESYSTEM
    supports_write = True

    def __init__(self, base_dir: str | Path | None = None, *, top_k: int = DEFAULT_TOP_K) -> None:
        # ``base_dir`` is accepted for factory parity with ``filesystem`` (the runner may
        # pass it) but this arm is in-memory: ranking needs every item's content in hand,
        # so persistence buys nothing here. Recorded only to stay signature-compatible.
        validate_top_k(top_k)
        self._base_dir = Path(base_dir) if base_dir is not None else None
        self._top_k = top_k
        self._store: dict[str, str] = {}

    def reset(self, trial_id: str) -> None:
        self._store = {}

    def retrieve(self, request: RetrievalRequest, ctx: StepContext) -> RetrieveResult:
        # Rank the WHOLE store by query-overlap, NOT by request.requested_ids — that id set
        # is the harness's relevant set for scoring, never a pre-filter here; pre-filtering
        # to it would make the arm trivially exact and the Confusion/Staleness rates 0.
        query = request.query_text or ""
        q_tokens = _tokenize(query)
        scored = sorted(
            (
                (len(q_tokens & _tokenize(content)), mid, content)
                for mid, content in self._store.items()
            ),
            # overlap desc, then id asc — a transparent deterministic tiebreak.
            key=lambda row: (-row[0], row[1]),
        )
        # Keep only items that actually overlap the query (a real search returns matches,
        # not the whole store), then cap at top_k.
        top = [row for row in scored if row[0] > 0][: self._top_k]
        payloads = {mid: content for _, mid, content in top}
        event = MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool=f"lexical.search(top_k={self._top_k})",
            normalized_operation=MemoryOperation.SEARCH,
            backend=self.backend,
            query=query or None,
            retrieved_ids=list(payloads),
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )
        return RetrieveResult(payloads=payloads, event=event, total_matched=len(top))

    def write(self, memory_id: str, content: str, ctx: StepContext) -> MemoryEvent:
        self._store[memory_id] = content
        return MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool=f"lexical.add({memory_id})",
            normalized_operation=MemoryOperation.WRITE,
            backend=self.backend,
            written_ids=[memory_id],
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )
