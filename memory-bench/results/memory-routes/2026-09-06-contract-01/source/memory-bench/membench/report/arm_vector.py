"""Per-arm raw 5-axis report for a replay run (Decision 12; fork 2: raw, no
weighted composite).

The five controller axes are reported as a *raw vector* per (arm, track) — never
collapsed into a single weighted score. Composite/weighting is an eval-design
decision the contract does not make here (it would HALT to mem-pl), so this module
deliberately does not provide one.

Axes (D12):
1. task_perf — agent outcome. Agent-dependent (the paid Harbor re-run); `None`
   in the deterministic replay skeleton rather than a fabricated number.
2. token_budget — injected-context volume (Decision-10 precision guard). Measured
   here as characters of injected memory text (the substrate is language-agnostic
   text; tokenization is the agent's, on the Harbor path).
3. latency — arm retrieval latency.
4. privacy — measured-not-acted (D12); `None` until the privacy phase (mem-lvp).
5. interruption — measured-not-acted (D12); `None` until the interruption phase.

The retrieval-side instruments behind the axes (retrieved count, total_matched,
the near-duplicate guard, eligible_count) travel with the vector so an empty
result is never mistaken for an empty corpus.
"""

from dataclasses import asdict, dataclass
from typing import Any

from membench.replay import ReplayRun


@dataclass(frozen=True)
class ArmAxisVector:
    arm: str
    scope: str | None
    # --- the 5 raw axes (no composite) ---
    task_perf: float | None
    token_budget_chars: int
    latency_ms: float
    privacy: float | None
    interruption: float | None
    # --- retrieval instruments behind the axes ---
    retrieved: int
    total_matched: int
    near_duplicate_top: bool
    fts_truncated: bool
    eligible_count: int

    @property
    def axes(self) -> tuple[float | None, int, float, float | None, float | None]:
        """The raw 5-axis vector in canonical order. `None` marks an axis this
        path does not measure — kept explicit, never zero-filled."""
        return (
            self.task_perf,
            self.token_budget_chars,
            self.latency_ms,
            self.privacy,
            self.interruption,
        )


def build_arm_vectors(run: ReplayRun) -> list[ArmAxisVector]:
    return [
        ArmAxisVector(
            arm=r.arm,
            scope=r.scope,
            task_perf=None,  # Harbor path; not measured in deterministic replay
            token_budget_chars=r.injected_context_chars,
            latency_ms=r.latency_ms,
            privacy=None,  # stub (D12: measured, not acted on)
            interruption=None,  # stub (D12: measured, not acted on)
            retrieved=len(r.retrieved_ids),
            total_matched=r.total_matched,
            near_duplicate_top=r.near_duplicate_top,
            fts_truncated=r.fts_truncated,
            eligible_count=r.eligible_count,
        )
        for r in run.results
    ]


def to_dict(run: ReplayRun) -> dict[str, Any]:
    return {
        "work_id": run.work_id,
        "rig": run.rig,
        "eligible_count": run.eligible_count,
        "arms": [asdict(v) for v in build_arm_vectors(run)],
    }


def _fmt(value: float | None) -> str:
    return "—" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))


def to_markdown(run: ReplayRun) -> str:
    lines = [
        f"# Replay 5-axis (raw) — {run.work_id} ({run.rig})",
        (
            f"_LOO-eligible corpus: {run.eligible_count} record(s)."
            " Axes are raw — no composite (fork 2)._"
        ),
        "",
        (
            "| arm | track | task_perf | token_budget (chars) | latency_ms"
            " | privacy | interruption | retrieved | matched | near_dup | fts_trunc |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for v in build_arm_vectors(run):
        lines.append(
            f"| {v.arm} | {v.scope or '—'} | {_fmt(v.task_perf)} | {v.token_budget_chars} | "
            f"{v.latency_ms:.3f} | {_fmt(v.privacy)} | {_fmt(v.interruption)} | "
            f"{v.retrieved} | {v.total_matched} | {'yes' if v.near_duplicate_top else 'no'} | "
            f"{'yes' if v.fts_truncated else 'no'} |"
        )
    return "\n".join(lines)
