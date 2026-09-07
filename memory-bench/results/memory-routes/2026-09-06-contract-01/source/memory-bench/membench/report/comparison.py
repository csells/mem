"""Aggregate a SequenceRun into a 3-condition comparison + §4 interpretation.

The interpretation applies the spec §4 result-pattern table as a deterministic
ranking with an explicit ≈ tolerance (`EPSILON`) — transparent arithmetic, not a
hidden semantic judgment (an allowed ZFC exception). The oracle-vs-no_memory
relationship is also the task-validity gate (plan §A, DIV-3).
"""

from dataclasses import asdict, dataclass, field
from typing import Any

from membench.runner.conditions import SequenceRun, StepTrial
from membench.schemas.conditions import Condition

EPSILON = 0.05  # rewards within EPSILON are treated as "≈".


@dataclass
class ConditionSummary:
    condition: str
    n_steps: int
    mean_reward: float
    pass_rate: float
    total_tokens: int
    memory_tool_calls: int
    mean_precision_at_k: float
    mean_recall_at_k: float
    mean_mrr: float
    mean_ndcg: float
    write_hit_rate: float
    over_retention_rate: float
    cross_session_success_rate: float


def _summarize(condition: Condition, trials: list[StepTrial]) -> ConditionSummary:
    def mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    # A context_gated trial (mem-1m0s) skips retrieval by design, so its retrieval
    # metrics are a fabricated 0.0 (retrieved_ids=[]), not a measured rate — excluded
    # from these 4 means the same way _confusion_staleness excludes it in
    # report/synthetic_arms.py. n_steps and the other means still cover every trial.
    retrieving = [t for t in trials if not t.metrics.retrieval.context_gated]

    return ConditionSummary(
        condition=condition.value,
        n_steps=len(trials),
        mean_reward=mean([t.metrics.task.reward for t in trials]),
        pass_rate=mean([1.0 if t.metrics.task.pass_ else 0.0 for t in trials]),
        total_tokens=sum(t.metrics.efficiency.total_tokens for t in trials),
        memory_tool_calls=sum(t.metrics.efficiency.memory_tool_calls for t in trials),
        mean_precision_at_k=mean([t.metrics.retrieval.precision_at_k for t in retrieving]),
        mean_recall_at_k=mean([t.metrics.retrieval.recall_at_k for t in retrieving]),
        mean_mrr=mean([t.metrics.retrieval.mrr for t in retrieving]),
        mean_ndcg=mean([t.metrics.retrieval.nDCG for t in retrieving]),
        write_hit_rate=mean([t.metrics.retention.write_hit_rate for t in trials]),
        over_retention_rate=mean([t.metrics.retention.over_retention_rate for t in trials]),
        cross_session_success_rate=mean(
            [1.0 if t.metrics.synthesis.cross_session_dependency_success else 0.0 for t in trials]
        ),
    )


def _interpret(summaries: dict[str, ConditionSummary]) -> str:
    none = summaries.get(Condition.NO_MEMORY.value)
    oracle = summaries.get(Condition.ORACLE_MEMORY.value)
    mem = summaries.get(Condition.MEMORY_ENABLED.value)
    if not (none and oracle and mem):
        return "incomplete: all three conditions required for interpretation"

    n, o, m = none.mean_reward, oracle.mean_reward, mem.mean_reward

    def approx(a: float, b: float) -> bool:
        return abs(a - b) <= EPSILON

    if approx(o, n):
        return "oracle ≈ no_memory: task is not discriminating — redesign it (DIV-3 gate fails)"
    if m < n - EPSILON:
        return "memory < no_memory: memory is adding noise / stale state / harmful instructions"
    if approx(m, n):
        return "oracle > no_memory, memory ≈ no_memory: system failed to retain/retrieve/use memory"
    if approx(m, o):
        return "memory ≈ oracle > no_memory: memory system is performing well on this task class"
    if o > m > n:
        return (
            "oracle > memory > no_memory: memory helps,"
            " but retrieval/ranking/synthesis limits gains"
        )
    return "mixed: inspect per-step metrics"


@dataclass
class ComparisonReport:
    sequence_id: str
    experiment_id: str
    summaries: dict[str, ConditionSummary] = field(default_factory=dict)
    interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence_id": self.sequence_id,
            "experiment_id": self.experiment_id,
            "summaries": {k: asdict(v) for k, v in self.summaries.items()},
            "interpretation": self.interpretation,
        }

    def to_markdown(self) -> str:
        order = [
            Condition.NO_MEMORY.value,
            Condition.ORACLE_MEMORY.value,
            Condition.MEMORY_ENABLED.value,
        ]
        lines = [
            f"# Comparison — {self.sequence_id} ({self.experiment_id})",
            "",
            (
                "| condition | steps | mean_reward | pass_rate | tokens"
                " | mem_calls | precision@k | recall@k | mrr | nDCG | write_hit"
                " | over_retention | x_session |"
            ),
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for c in order:
            s = self.summaries.get(c)
            if s is None:
                continue
            lines.append(
                f"| {s.condition} | {s.n_steps} | {s.mean_reward:.3f} | "
                f"{s.pass_rate:.3f} | {s.total_tokens} | {s.memory_tool_calls} | "
                f"{s.mean_precision_at_k:.3f} | {s.mean_recall_at_k:.3f} | "
                f"{s.mean_mrr:.3f} | {s.mean_ndcg:.3f} | "
                f"{s.write_hit_rate:.3f} | {s.over_retention_rate:.3f} | "
                f"{s.cross_session_success_rate:.3f} |"
            )
        lines += ["", f"**Interpretation (§4):** {self.interpretation}"]
        return "\n".join(lines)


def build_comparison(run: SequenceRun) -> ComparisonReport:
    by_cond = run.by_condition()
    summaries = {c.value: _summarize(c, trials) for c, trials in by_cond.items()}
    return ComparisonReport(
        sequence_id=run.sequence_id,
        experiment_id=run.experiment_id,
        summaries=summaries,
        interpretation=_interpret(summaries),
    )
