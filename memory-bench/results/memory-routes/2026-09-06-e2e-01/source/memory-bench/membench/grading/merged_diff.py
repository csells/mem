"""Merged-diff outcome source — the locked headline oracle, where constructible.

Feasibility is a conjunction (architect findings H2/M4): the bead must have a
`merged` PR outcome AND a recorded `commit_sha` AND a rig that maps to a repo. The
stored `commit_sha` is the *merge* commit (`outcomes.ts` `pr.mergeCommit.oid`), and
the repo is not persisted, so walking to the base commit and fetching the PR diff
both need a clone — they are reported as `unresolved` rather than claimed here. The
clone-time confirmation + the verifier itself are mem-apg.2/.3.
"""

from collections.abc import Mapping
from typing import Any

from membench.config.rigs import repo_for_rig
from membench.grading.base import Feasibility, OutcomeSource


class MergedDiffSource(OutcomeSource):
    name = "merged_diff"

    def __init__(self, rig_map: Mapping[str, str] | None = None) -> None:
        self.rig_map = rig_map

    def can_build(self, record: Mapping[str, Any]) -> Feasibility:
        outcome = record.get("outcome") or {}
        if outcome.get("pr_state") != "merged":
            return Feasibility(self.name, False, "no merged-PR outcome")
        if not outcome.get("commit_sha"):
            return Feasibility(self.name, False, "merged PR but no commit_sha recorded")
        # The bead IS a merged-diff candidate, so an unmapped rig is a config gap,
        # not a legitimate "infeasible" — fail loud (M6).
        repo = repo_for_rig(record["rig"], self.rig_map)
        return Feasibility(
            source=self.name,
            feasible=True,
            reason=f"merged-diff constructible against {repo} (clone-pending)",
            unresolved=("base_commit_walk", "merge_diff_fetch"),
        )
