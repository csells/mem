"""The three candidate generators under comparison (mem-lbuvd).

All three index exactly the string `MemoryFixture.stored_value(corpus_size)`
produces, which is also the value Beads stores. No arm sees text another arm does
not; that is the fairness control the preregistration locks.

Each generator returns a RANKED tuple of Memory ids. Applying a budget is the
caller's job, because the preregistration reports recall at three different
budgets over the same ranking.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import subprocess
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from membench.beads_ordering.models import MemoryFixture
from membench.lexical_recall.models import Generator

_TOKEN = re.compile(r"[0-9a-z]+", re.IGNORECASE)


class GeneratorError(RuntimeError):
    pass


def document_text(memory: MemoryFixture, corpus_size: int) -> str:
    """The one document string every arm indexes."""

    return memory.stored_value(corpus_size)


class CandidateGenerator(Protocol):
    # Read-only, so a frozen implementation satisfies the protocol. A mutable
    # attribute here would exclude `LiteralGenerator`, which is frozen because
    # nothing about a shelled-out binary should be reconfigured mid-run.
    @property
    def name(self) -> Generator: ...

    def rank(self, query: str) -> tuple[str, ...]:
        """Return Memory ids best-first. May be shorter than the corpus."""


@dataclass(frozen=True)
class LiteralGenerator:
    """Beads' shipped case-insensitive substring matcher, reached through the real
    binary rather than reimplemented.

    `--experimental-order key` with `--page-size all` returns the whole candidate
    map in one page. Candidate generation in the pinned binary is identical to
    stock: BM25F reorders the map `memoryops.List` already returned and cannot add
    or remove a candidate, so this arm sees the same candidate sets the ordering
    experiment saw.
    """

    beads_bin: str
    workspace: Path
    name: Generator = Generator.LITERAL

    def rank(self, query: str) -> tuple[str, ...]:
        argv = [
            self.beads_bin,
            "--json",
            "memories",
            query,
            "--experimental-order",
            "key",
            "--page-size",
            "all",
        ]
        completed = subprocess.run(
            argv,
            cwd=self.workspace,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            raise GeneratorError(f"bd memories exited {completed.returncode}")
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise GeneratorError("bd memories emitted malformed JSON") from exc
        payload = raw.get("data", raw) if isinstance(raw, dict) else raw
        if not isinstance(payload, dict):
            raise GeneratorError("bd memories emitted an unexpected payload")
        items = payload.get("items") or ()
        if not isinstance(items, list):
            raise GeneratorError("bd memories emitted a non-list items field")
        ranked: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                raise GeneratorError("bd memories emitted a non-object item")
            identifier = item.get("id")
            if not isinstance(identifier, str):
                raise GeneratorError("bd memories emitted an item without a string id")
            ranked.append(identifier)
        self._require_whole_page(payload, len(ranked))
        return tuple(ranked)

    @staticmethod
    def _require_whole_page(payload: dict[str, object], returned: int) -> None:
        """Reject a truncated page instead of measuring one.

        `matched_k` is the size of this candidate set, and every arm's budget is
        scaled by it, so a short page shrinks the whole experiment silently. The
        control class would catch that through its equality gate; the lexical-miss
        class would not, because dropping a distractor leaves the returned set a
        strict subset of the labels, still missing the primary and still non-empty,
        which is exactly what its subset gate asserts. `beads_ordering.client`
        checks these same three fields for the same reason.
        """

        complete = payload.get("complete")
        if complete is False:
            raise GeneratorError(
                f"bd memories returned an incomplete page (continuation="
                f"{payload.get('continuation')!r}); matched-k would be understated"
            )
        total = payload.get("total_matched")
        if isinstance(total, int) and total != returned:
            raise GeneratorError(
                f"bd memories reported total_matched={total} but returned {returned} "
                "items; matched-k would be understated"
            )


def fts_match_expression(query: str) -> str:
    """Bag-of-words OR, one quoted term per token.

    A phrase query would require adjacency and would sink the morphological and
    synonym kinds for a tokenizer-unrelated reason. OR over terms is what a search
    index actually does. This choice moves the recall number, so it is locked in
    the preregistration rather than tuned once results exist.
    """

    terms = _TOKEN.findall(query)
    if not terms:
        raise GeneratorError(f"query yields no FTS terms: {query!r}")
    return " OR ".join(f'"{term}"' for term in terms)


@dataclass
class Fts5Generator:
    """SQLite FTS5, `porter unicode61`, ranked by bm25().

    No FTS index exists over these fixtures today; this one is built in process
    and lives only for the run.
    """

    memories: Sequence[MemoryFixture]
    corpus_size: int
    name: Generator = Generator.FTS

    def __post_init__(self) -> None:
        self._connection = sqlite3.connect(":memory:")
        self._connection.execute(
            "CREATE VIRTUAL TABLE documents USING fts5("
            "memory_id UNINDEXED, text, tokenize='porter unicode61')"
        )
        self._connection.executemany(
            "INSERT INTO documents (memory_id, text) VALUES (?, ?)",
            [(memory.id, document_text(memory, self.corpus_size)) for memory in self.memories],
        )
        self._connection.commit()

    def rank(self, query: str) -> tuple[str, ...]:
        rows = self._connection.execute(
            "SELECT memory_id FROM documents WHERE documents MATCH ? ORDER BY bm25(documents)",
            (fts_match_expression(query),),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)


class OllamaEmbedder:
    """Batch embeddings from a local Ollama daemon, cached in memory.

    The cache is keyed on the exact text, so the three repeats the preregistration
    asks for re-embed only the QUERY. Re-embedding 680 documents per repeat would
    measure the daemon's throughput, not the arm's stability.
    """

    def __init__(self, base_url: str, model: str, *, timeout: float = 600.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._cache: dict[str, tuple[float, ...]] = {}

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: Sequence[str], *, use_cache: bool = True) -> list[tuple[float, ...]]:
        pending = [
            text for text in dict.fromkeys(texts) if not use_cache or text not in self._cache
        ]
        for start in range(0, len(pending), 32):
            batch = pending[start : start + 32]
            for text, vector in zip(batch, self._post(batch), strict=True):
                self._cache[text] = vector
        return [self._cache[text] for text in texts]

    def _post(self, batch: Sequence[str]) -> list[tuple[float, ...]]:
        request = urllib.request.Request(
            f"{self._base_url}/api/embed",
            data=json.dumps({"model": self._model, "input": list(batch)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        vectors = payload.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise GeneratorError("ollama returned an embedding count that does not match the batch")
        result: list[tuple[float, ...]] = []
        for vector in vectors:
            if not isinstance(vector, list) or not vector:
                raise GeneratorError("ollama returned a malformed embedding")
            result.append(tuple(float(value) for value in vector))
        return result


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise GeneratorError("cosine is undefined for a zero vector")
    return numerator / (left_norm * right_norm)


@dataclass
class EmbeddingGenerator:
    """Dense retrieval by exact in-process cosine, no ANN.

    Exact cosine over the whole corpus is deterministic given the embeddings, so
    any variation across the preregistered repeats comes from the served model
    rather than from an approximate index.

    A dense ranker has no natural cutoff, so this returns every Memory ranked. The
    budget rule in the endpoint is what turns that into a candidate set.
    """

    memories: Sequence[MemoryFixture]
    corpus_size: int
    embedder: OllamaEmbedder
    name: Generator = Generator.EMBEDDING

    def __post_init__(self) -> None:
        texts = [document_text(memory, self.corpus_size) for memory in self.memories]
        vectors = self.embedder.embed(texts)
        self._documents = tuple(
            (memory.id, vector) for memory, vector in zip(self.memories, vectors, strict=True)
        )

    def rank(self, query: str) -> tuple[str, ...]:
        query_vector = self.embedder.embed([query], use_cache=False)[0]
        scored = [
            (_cosine(query_vector, vector), memory_id) for memory_id, vector in self._documents
        ]
        # Ties break on id so the ranking is total and reproducible.
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return tuple(memory_id for _, memory_id in scored)
