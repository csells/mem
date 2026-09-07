"""Schema-induction headline: the recombine-vs-dedupe PAIR, never synthetic-only.

The S1 result is publishable only as the joint per-mode
``(Δschema_recall, confabulation_rate)`` — never a scalar. The decision rule: a
``recombine`` gain in schema recall counts ONLY if confabulation does not also rise
(else it is "recombine trades faithfulness for fluency", not a win). And the
headline requires BOTH a synthetic leg AND a real-anchor leg — ``summarize_schema_induction``
RAISES on a missing real anchor, mechanising the "never synthetic-only" discipline
that B-1 made load-bearing (the real corpus can't carry the signal, so the headline
would otherwise be a pure artifact of our own generator).
"""

from __future__ import annotations

from dataclasses import dataclass

from membench.memory_systems.consolidating_system import ClusterSummarizer, ConsolidatingMemory
from membench.metrics.schema_scorers import (
    ConfabulationFindings,
    confabulation_findings,
    episode_source_texts,
    schema_recall,
)
from membench.runner.conditions import SequenceRun, run_sequence
from membench.schemas.conditions import Condition
from membench.schemas.config import ExperimentConfig
from membench.schemas.sequence import BenchmarkSequence

_MODES = ("recombine", "dedupe_only")


@dataclass(frozen=True)
class SchemaInductionScore:
    """One (arm-mode) run's schema-induction readout: did it recover the rule, and
    was the recovery faithful to the source episodes?"""

    schema_recall: float
    confabulation: ConfabulationFindings
    n_schema_rows: int


def score_schema_induction_run(seq: BenchmarkSequence, run: SequenceRun) -> SchemaInductionScore:
    """Score the MEMORY_ENABLED consolidation output of ``run`` against ``seq``'s
    latent-rule oracle + its episode source set."""
    consolidation = run.consolidations.get(Condition.MEMORY_ENABLED.value)
    items = consolidation.items if consolidation is not None else ()
    recall = schema_recall(seq.latent_rule or "", items)
    confab = confabulation_findings(items, episode_source_texts(seq))
    return SchemaInductionScore(
        schema_recall=recall, confabulation=confab, n_schema_rows=len(items)
    )


def run_schema_induction_modes(
    seq: BenchmarkSequence,
    experiment: ExperimentConfig,
    *,
    summarizer: ClusterSummarizer | None = None,
) -> dict[str, SchemaInductionScore]:
    """Drive ``ConsolidatingMemory`` in BOTH modes through ``run_sequence`` over
    ``seq`` and score each — the decisive ablation, on the sequence-runner track."""
    out: dict[str, SchemaInductionScore] = {}
    for mode in _MODES:
        arm = ConsolidatingMemory(mode=mode, summarizer=summarizer)
        run = run_sequence(
            seq, experiment, conditions=[Condition.MEMORY_ENABLED], memory_system=arm
        )
        out[mode] = score_schema_induction_run(seq, run)
    return out


def _pair(scores: dict[str, SchemaInductionScore]) -> dict[str, float | bool]:
    rec = scores["recombine"]
    ded = scores["dedupe_only"]
    delta = rec.schema_recall - ded.schema_recall
    confab_rose = rec.confabulation.rate > ded.confabulation.rate
    return {
        "recombine_recall": rec.schema_recall,
        "dedupe_recall": ded.schema_recall,
        "delta_recall": delta,
        "recombine_confab": rec.confabulation.rate,
        "dedupe_confab": ded.confabulation.rate,
        "confab_rose": confab_rose,
        # A recombine gain counts only if faithfulness did not degrade.
        "recombine_wins": delta > 0.0 and not confab_rose,
    }


def summarize_schema_induction(
    *,
    synthetic: dict[str, SchemaInductionScore],
    real_anchor: dict[str, SchemaInductionScore] | None,
    generator_version: str,
    success_threshold: float,
) -> dict[str, object]:
    """The headline. RAISES without a real-anchor leg (never synthetic-only, B-1).
    ``headline_win`` requires recombine to win on BOTH legs AND the synthetic Δ to
    clear the pre-registered threshold (recorded, not set after the fact)."""
    if real_anchor is None:
        raise ValueError(
            "never synthetic-only: a schema-induction headline requires a real-anchor "
            "leg (B-1 — the coding corpus cannot carry the latent-rule signal)"
        )
    syn = _pair(synthetic)
    real = _pair(real_anchor)
    headline_win = bool(
        syn["recombine_wins"]
        and real["recombine_wins"]
        and syn["delta_recall"] >= success_threshold
    )
    return {
        "generator_version": generator_version,
        "success_threshold": success_threshold,
        "synthetic": syn,
        "real_anchor": real,
        "headline_win": headline_win,
        "decision_rule": (
            "recombine wins iff Δschema_recall > 0 AND confabulation did not rise, on "
            "BOTH the synthetic generator AND the real anchor (never synthetic-only); "
            "the synthetic Δ must also clear the pre-registered success_threshold"
        ),
    }
