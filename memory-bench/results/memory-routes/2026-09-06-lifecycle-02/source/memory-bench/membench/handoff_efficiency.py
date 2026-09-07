"""Handoff efficiency — matched-pair effort deltas from ``trace_runs`` (mem-dsu).

The two efficiency metrics of "Handoff Debt" (arXiv 2606.02875), aligned to the
``trace_runs`` columns we already populate (mem-75t.2; memo
.gc/docs/mem-sxe.1-handoff-debt-investigation.md):

- **agent events** — ``n_turns + n_tool_calls`` (assistant turns ~ the paper's LLM
  actions; tool calls ~ the action/observation pairs). Reported BOTH separately and
  summed: our split is finer-grained than their single "events" count.
- **cumulative prompt tokens** — ``input_tokens + cache_read_tokens +
  cache_creation_tokens`` (the prompt/processed-context side, the rediscovery-reading
  cost). ``output_tokens`` is EXCLUDED — their metric is prompt tokens only.
- **first-prompt tokens** (optional) — the first-turn input, the lever that exposes
  raw-trace's ~12x initial-prompt penalty (the mem-lug compression-cost curve).

Deltas are computed on MATCHED runs — same (interruption point, successor,
checkpoint), the view varying — against the repo-only baseline, as the fraction of
effort the view repaid: ``(repo_only - view) / repo_only`` per metric (positive ⇒
the view cut effort). Medians carry paired bootstrap 95% CIs (the paper's 5k
resamples); the solve-rate companion uses an exact McNemar test on the matched
solved flags. This is a self-contained analysis module (like ``armcompare`` /
``cross_session``); the §12 interruption metric leg imports it.

ZFC: pure mechanism — arithmetic, resampling, exact binomial. No model calls, no
semantic heuristics, no hardcoded thresholds.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import comb
from statistics import median

from pydantic import BaseModel, Field


class RunEfficiency(BaseModel):
    """The prompt-side efficiency axis for ONE takeover run, projected from
    ``trace_runs``. Token fields are ``None`` when the column is absent (typed
    absence — never imputed to zero, except cache fields, which are additive and so
    contribute zero when a run did no caching)."""

    n_turns: int = Field(ge=0)
    n_tool_calls: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    cache_read_tokens: int | None = Field(default=None, ge=0)
    cache_creation_tokens: int | None = Field(default=None, ge=0)
    # Optional derived first-prompt proxy (first-turn input tokens).
    first_input_tokens: int | None = Field(default=None, ge=0)
    # Solve-rate outcome for the McNemar companion; None when the run was not scored.
    solved: bool | None = None


@dataclass(frozen=True)
class MatchedRun:
    """One run located in the matched-pair grid: ``matched_key`` is the (point,
    successor, checkpoint) cell; ``view`` is which arm produced this run."""

    matched_key: str
    view: str
    efficiency: RunEfficiency


_BASELINE_VIEW = "repo-only"


def agent_events(e: RunEfficiency) -> int:
    """The paper's single "agent events" count = turns + tool calls."""
    return e.n_turns + e.n_tool_calls


def prompt_tokens(e: RunEfficiency) -> int | None:
    """Cumulative prompt tokens = input + cache_read + cache_creation (output
    excluded). ``None`` when there is no input measurement at all; cache fields
    absent count as zero (a run that did no caching), not as missing data."""
    if e.input_tokens is None:
        return None
    return e.input_tokens + (e.cache_read_tokens or 0) + (e.cache_creation_tokens or 0)


def first_prompt_tokens(e: RunEfficiency) -> int | None:
    """The first-turn prompt size — the raw-trace initial-prompt penalty lever."""
    return e.first_input_tokens


# The metrics reported per view. ``turns``/``tool_calls`` are the finer split the
# memo asks us to report alongside the summed ``events``.
_METRICS: dict[str, Callable[[RunEfficiency], float | None]] = {
    "turns": lambda e: float(e.n_turns),
    "tool_calls": lambda e: float(e.n_tool_calls),
    "events": lambda e: float(agent_events(e)),
    "prompt_tokens": lambda e: None if (v := prompt_tokens(e)) is None else float(v),
    "first_prompt_tokens": lambda e: None if (v := first_prompt_tokens(e)) is None else float(v),
}


def bootstrap_median_ci(
    deltas: Sequence[float],
    *,
    n_resamples: int = 5000,
    conf: float = 0.95,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Median of ``deltas`` with a percentile bootstrap CI (the paper's 5k
    resamples). Seeded ⇒ reproducible; pure stdlib (no scipy). A single observation
    has no resample spread, so its bounds collapse to the value."""
    if not deltas:
        raise ValueError("bootstrap_median_ci needs at least one delta")
    point = float(median(deltas))
    if len(deltas) < 2:
        return point, point, point
    rng = random.Random(seed)
    n = len(deltas)
    resampled = sorted(
        median(deltas[rng.randrange(n)] for _ in range(n)) for _ in range(n_resamples)
    )
    lo_idx = int((1.0 - conf) / 2.0 * n_resamples)
    hi_idx = min(n_resamples - 1, int((1.0 + conf) / 2.0 * n_resamples))
    return point, float(resampled[lo_idx]), float(resampled[hi_idx])


def _exact_mcnemar_p(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value: a binomial test of the discordant pairs
    against p=0.5. No discordance ⇒ p=1.0. Pure stdlib (``math.comb``)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2.0**n)
    return min(1.0, 2.0 * tail)


def mcnemar(baseline_solved: Sequence[bool], view_solved: Sequence[bool]) -> dict[str, float | int]:
    """McNemar over matched solved flags. ``b`` = baseline solved & view did not;
    ``c`` = view solved & baseline did not; ``n_discordant`` = b + c; ``p_value`` is
    the exact two-sided test. Concordant pairs are uninformative and ignored."""
    if len(baseline_solved) != len(view_solved):
        raise ValueError("baseline and view solved flags must be the same length")
    b = sum(1 for base, view in zip(baseline_solved, view_solved, strict=True) if base and not view)
    c = sum(1 for base, view in zip(baseline_solved, view_solved, strict=True) if view and not base)
    return {"b": b, "c": c, "n_discordant": b + c, "p_value": _exact_mcnemar_p(b, c)}


def _group_by_key(runs: Sequence[MatchedRun]) -> dict[str, dict[str, RunEfficiency]]:
    """Index runs as matched_key → view → efficiency. A repeated (key, view) is a
    caller bug — the matched grid holds one run per cell — so raise rather than
    silently drop."""
    grid: dict[str, dict[str, RunEfficiency]] = {}
    for run in runs:
        cell = grid.setdefault(run.matched_key, {})
        if run.view in cell:
            raise ValueError(f"duplicate run for {run.matched_key!r} / {run.view!r}")
        cell[run.view] = run.efficiency
    return grid


def summarize_handoff_efficiency(
    runs: Sequence[MatchedRun],
    *,
    n_resamples: int = 5000,
    conf: float = 0.95,
    seed: int = 0,
) -> dict[str, dict[str, object]]:
    """Per non-baseline view, the matched-pair effort deltas vs repo-only.

    Returns ``{view: {metric: {median_delta, ci_low, ci_high, n_pairs}, ...,
    "solve_rate": <mcnemar>}}``. Each delta is ``(repo_only - view) / repo_only`` on
    a matched set where BOTH the baseline and the view ran and the baseline metric is
    non-zero; a set missing either side contributes nothing (never imputed). The
    repo-only baseline itself gets no row."""
    grid = _group_by_key(runs)
    views = sorted({run.view for run in runs} - {_BASELINE_VIEW})

    summary: dict[str, dict[str, object]] = {}
    for view in views:
        per_metric: dict[str, object] = {}
        for metric_name, metric in _METRICS.items():
            deltas: list[float] = []
            for cell in grid.values():
                base_eff = cell.get(_BASELINE_VIEW)
                view_eff = cell.get(view)
                if base_eff is None or view_eff is None:
                    continue
                base_value = metric(base_eff)
                view_value = metric(view_eff)
                if base_value is None or view_value is None or base_value == 0:
                    continue
                deltas.append((base_value - view_value) / base_value)
            if not deltas:
                continue
            point, lo, hi = bootstrap_median_ci(
                deltas, n_resamples=n_resamples, conf=conf, seed=seed
            )
            per_metric[metric_name] = {
                "median_delta": point,
                "ci_low": lo,
                "ci_high": hi,
                "n_pairs": len(deltas),
            }

        baseline_solved: list[bool] = []
        view_solved: list[bool] = []
        for cell in grid.values():
            base_eff = cell.get(_BASELINE_VIEW)
            view_eff = cell.get(view)
            if base_eff is None or view_eff is None:
                continue
            if base_eff.solved is None or view_eff.solved is None:
                continue
            baseline_solved.append(base_eff.solved)
            view_solved.append(view_eff.solved)
        if baseline_solved:
            per_metric["solve_rate"] = mcnemar(baseline_solved, view_solved)

        if per_metric:
            summary[view] = per_metric
    return summary
