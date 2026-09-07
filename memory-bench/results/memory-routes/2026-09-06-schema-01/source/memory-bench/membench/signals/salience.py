"""Pure-arithmetic salience signals (M8).

Two signals, deterministic functions of token sets / a similarity ranking:

* **novelty** — ``1 - max Jaccard`` of a candidate against the existing corpus.
  The write-gate skips low-novelty (near-duplicate) writes; the consolidation
  sampler prioritises high-novelty items; the compaction priority dedupes by it.
* **decay_slope** — the mean per-rank drop of a similarity ranking. A steep slope
  means retrieval quality falls off fast, so the foraging controller (N1) can stop
  early; a flat slope means the tail still carries signal.

No embeddings, no LLM, no network — that is the whole point of a *signal* (vs a
*judge*): the stop/write decision must cost ≪ one model call. Tokenisation is a
deterministic lowercase word split; an alternate tokenizer can be injected for a
different granularity without touching the arithmetic.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

_WORD = re.compile(r"\w+")


def _default_tokenize(text: str) -> frozenset[str]:
    """Lowercase word-set tokenisation (order- and count-insensitive)."""
    return frozenset(m.group(0).lower() for m in _WORD.finditer(text))


@dataclass(frozen=True)
class SalienceSignals:
    """The signal bank. Stateless; the optional ``tokenize`` override only changes
    token granularity, never the arithmetic."""

    tokenize: Callable[[str], frozenset[str]] = field(default=_default_tokenize)

    # -- novelty / near-duplicate ------------------------------------------- #
    def jaccard(self, a: str, b: str) -> float:
        """Jaccard similarity of two texts' token sets, in [0, 1].

        Two empty texts are trivially identical near-duplicates → 1.0; an empty
        text against a non-empty one shares nothing → 0.0 (both documented edges,
        so the write-gate never silently treats "no content" as "fully novel")."""
        ta, tb = self.tokenize(a), self.tokenize(b)
        union = ta | tb
        if not union:
            return 1.0  # both empty ⇒ identical
        return len(ta & tb) / len(union)

    def novelty(self, candidate: str, existing: Iterable[str]) -> float:
        """``1 - max Jaccard(candidate, e)`` over ``existing``; 1.0 against an empty
        corpus (nothing to duplicate). Higher = more novel = more worth keeping."""
        sims = [self.jaccard(candidate, e) for e in existing]
        if not sims:
            return 1.0
        return 1.0 - max(sims)

    # -- decay slope -------------------------------------------------------- #
    def decay_slope(self, similarities: Sequence[float]) -> float:
        """Mean per-rank decrease of a similarity ranking.

        The input is sorted descending first, so the slope keys on the *ranking*,
        not the caller's argument order: ``(s[0] - s[-1]) / (n - 1)``. Flat or
        single/empty rankings have no decay → 0.0."""
        if len(similarities) < 2:
            return 0.0
        ranked = sorted(similarities, reverse=True)
        return (ranked[0] - ranked[-1]) / (len(ranked) - 1)
