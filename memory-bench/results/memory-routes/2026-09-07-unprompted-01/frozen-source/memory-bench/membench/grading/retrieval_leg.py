"""M1 + M2 — the white-box retrieval-correctness leg for the headline grid.

The headline grid scores black-box (final diff / repro) and DISCARDS the retrieval
half of the claim. This module surfaces it by reusing the built, tested
``metrics.scorers.score_retrieval``: precision/recall/MRR/nDCG of an arm's retrieved
work_ids against the gold-relevant set. It is reported SEPARATELY from
answer-correctness — never folded into a composite — so a run that retrieves the
wrong thing but still passes repro is visibly divergent.

The gold-relevant set is the bundle's declared source work_ids MINUS its
``loo_excluded_work_ids`` (own work + siblings the LOO boundary withholds). The
coding corpus carries no per-bundle relevance labels, so the source set comes from
an external relevance oracle; absent it the relevant set is empty and the leg is
``None`` — honestly *not measured*, never a fabricated ``0.0``.

M1: a retrieval-bearing result must declare its scoring TARGET (TIAP — raw / source
/ canonical). Scoring an arm's retrieval without declaring against which target is
the measurement-crisis failure this lane exists to prevent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from membench.metrics.scorers import RetrievalInputs, score_retrieval
from membench.schemas.bundle import TaskBundle

RetrievalTarget = Literal["raw", "source", "canonical"]


class RetrievalLeg(BaseModel):
    """White-box retrieval-correctness for one (bundle, arm). All metric fields are
    ``None`` when the relevant set is empty (not measured)."""

    model_config = ConfigDict(frozen=True)

    retrieval_target: RetrievalTarget
    precision: float | None
    recall: float | None
    mrr: float | None
    ndcg: float | None


def gold_relevant_ids(
    bundle: TaskBundle,
    *,
    relevance: Mapping[str, Sequence[str]] | None = None,
) -> tuple[str, ...]:
    """The gold-relevant retrieval set: the bundle's declared source work_ids minus
    ``loo_excluded_work_ids``. With no relevance oracle the set is empty (the leg
    then scores ``None``), so the corpus's missing labels surface as "not measured",
    never as a silently-zero recall."""
    sources = set(relevance.get(bundle.work_id, ())) if relevance else set()
    return tuple(sorted(sources - set(bundle.loo_excluded_work_ids)))


def score_retrieval_leg(
    retrieved_ids: Sequence[str],
    relevant_ids: Sequence[str],
    *,
    target: RetrievalTarget,
) -> RetrievalLeg:
    """Score an arm's retrieved work_ids against the gold-relevant set, reusing the
    built ``score_retrieval``. Empty relevant set ⇒ all metrics ``None``."""
    if not relevant_ids:
        return RetrievalLeg(
            retrieval_target=target, precision=None, recall=None, mrr=None, ndcg=None
        )
    m = score_retrieval(
        RetrievalInputs(retrieved_ids=list(retrieved_ids), required_ids=list(relevant_ids))
    )
    return RetrievalLeg(
        retrieval_target=target,
        precision=m.precision_at_k,
        recall=m.recall_at_k,
        mrr=m.mrr,
        ndcg=m.nDCG,
    )
