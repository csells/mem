"""The trial objective: collapse a sweep's frontier into one comparable scalar.

autoresearch compares experiments by a single number (``val_bpb``, lower-is-better).
The rig analog, higher-is-better: the **maximum sustained output-token throughput**
across the swept concurrency levels, subject to a **TTFT p50 service-level objective**.
A config that pushes more tokens/sec only counts if it still answers fast enough.

If no swept cell meets the SLO, the score is 0.0 — a latency-blown config is not
"slightly worse", it fails the bar. Pure: a function of the rows and the SLO.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from membench.engines.sweep import SweepRow


@dataclass(frozen=True)
class TrialObjective:
    """The scored outcome of one trial.

    ``score`` is the comparable scalar (output tokens/sec at the best SLO-meeting
    concurrency, else 0.0). The rest is provenance: which cell won, and whether the
    SLO was ever met — so a 0.0 from "no cell ran" is distinguishable from a 0.0 from
    "every cell blew the latency bar"."""

    score: float
    slo_met: bool
    best_concurrency: int | None
    best_output_tps: float | None
    best_ttft_p50_s: float | None
    ttft_p50_slo_s: float
    cells_evaluated: int


def score_rows(rows: Sequence[SweepRow], *, ttft_p50_slo_s: float) -> TrialObjective:
    """Score a sweep. The winning cell is the SLO-meeting one with the highest output-
    token throughput; ties break toward lower concurrency (cheaper, less KV pressure
    for the same throughput)."""
    if ttft_p50_slo_s <= 0:
        raise ValueError("ttft_p50_slo_s must be > 0")

    eligible = [
        r
        for r in rows
        if r.ttft_p50_s is not None
        and r.output_token_throughput is not None
        and r.ttft_p50_s <= ttft_p50_slo_s
    ]
    if not eligible:
        return TrialObjective(
            score=0.0,
            slo_met=False,
            best_concurrency=None,
            best_output_tps=None,
            best_ttft_p50_s=None,
            ttft_p50_slo_s=ttft_p50_slo_s,
            cells_evaluated=len(rows),
        )

    # Max throughput, tie-break toward lower concurrency. ``output_token_throughput``
    # is non-None for every eligible row (filtered above); assert-free via the key.
    best = max(eligible, key=lambda r: (r.output_token_throughput or 0.0, -r.concurrency))
    return TrialObjective(
        score=best.output_token_throughput or 0.0,
        slo_met=True,
        best_concurrency=best.concurrency,
        best_output_tps=best.output_token_throughput,
        best_ttft_p50_s=best.ttft_p50_s,
        ttft_p50_slo_s=ttft_p50_slo_s,
        cells_evaluated=len(rows),
    )
