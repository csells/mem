"""The oracle-source coverage probe (mem-apg.1).

For each held-out WorkRecord, run every `OutcomeSource.can_build` and collect the
result. The coverage table is a byproduct of the protocol (finding M5), and the
per-task recommendation follows one explicit precedence rule — merged-diff when
constructible, else ablation (finding M7) — not a scoring heuristic.

An unmapped rig on a merged bead raises `UnmappedRigError` at the source; the probe
catches it into an explicit, non-feasible CONFIG-GAP bucket and `summarize` reports
the offending rigs. The gap is surfaced loudly, never silently reclassified to
ablation-only (finding M6).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from membench.config.rigs import UnmappedRigError
from membench.grading.base import Feasibility, OutcomeSource

_RIG_GAP_REASON = "config gap: rig has no repo mapping"
# Deterministic precedence: the first source in this order that is feasible wins.
_PRECEDENCE = ("merged_diff", "ablation")


@dataclass(frozen=True)
class SourceCoverage:
    """One record's feasibility across every probed source."""

    work_id: str
    rig: str
    feasibilities: Mapping[str, Feasibility]


@dataclass(frozen=True)
class SourceCount:
    feasible: int
    infeasible: int


@dataclass(frozen=True)
class CoverageSummary:
    per_source: Mapping[str, SourceCount]
    unmapped_rigs: frozenset[str]


def coverage_table(
    records: Sequence[Mapping[str, Any]], sources: Sequence[OutcomeSource]
) -> list[SourceCoverage]:
    table: list[SourceCoverage] = []
    for record in records:
        feasibilities: dict[str, Feasibility] = {}
        for source in sources:
            try:
                feasibilities[source.name] = source.can_build(record)
            except UnmappedRigError:
                feasibilities[source.name] = Feasibility(
                    source=source.name,
                    feasible=False,
                    reason=_RIG_GAP_REASON,
                    unresolved=("rig_repo_mapping",),
                )
        table.append(
            SourceCoverage(
                work_id=record["work_id"],
                rig=record["rig"],
                # Read-only view: frozen dataclass + immutable mapping, so a row
                # cannot be mutated between building the table and summarizing it.
                feasibilities=MappingProxyType(feasibilities),
            )
        )
    return table


def summarize(table: Sequence[SourceCoverage]) -> CoverageSummary:
    # Source names in first-seen order (dict preserves insertion order). Counts use
    # `.get` so a row that did not probe a given source counts toward neither tally
    # rather than raising — robust to non-uniform tables a future caller may build.
    names = dict.fromkeys(name for row in table for name in row.feasibilities)
    per_source = {
        name: SourceCount(
            feasible=sum(1 for row in table if (f := row.feasibilities.get(name)) and f.feasible),
            infeasible=sum(
                1
                for row in table
                if (f := row.feasibilities.get(name)) is not None and not f.feasible
            ),
        )
        for name in names
    }
    unmapped = frozenset(
        row.rig
        for row in table
        for feas in row.feasibilities.values()
        if "rig_repo_mapping" in feas.unresolved
    )
    return CoverageSummary(per_source=MappingProxyType(per_source), unmapped_rigs=unmapped)


def recommend_source(row: SourceCoverage) -> str:
    """The source to grade `row` with, by the stated precedence (merged-diff then
    ablation). Raises if no probed source is feasible — ablation must always be
    probed and is always feasible, so a falsy result means a malformed row, not a
    silent fallback."""
    for name in _PRECEDENCE:
        feas = row.feasibilities.get(name)
        if feas is not None and feas.feasible:
            return name
    raise ValueError(f"no feasible source for {row.work_id!r}; ablation must always be probed")
