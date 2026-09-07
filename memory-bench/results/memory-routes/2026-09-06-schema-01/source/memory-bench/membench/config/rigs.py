"""Interim rig -> repo mapping for env reconstruction (mem-apg.1, finding M6).

The repo a bead belongs to IS known at ingest (`src/ingest/outcomes.ts`
`resolveBranchOutcome`) but is NOT persisted to the WorkRecord schema. Until that
gap is backfilled (bead mem-bme), this module is the source of truth for
rig -> repo.

It is intentionally fail-loud: an unmapped rig on a bead that needs a repo raises
`UnmappedRigError` rather than silently reclassifying the bead as env-infeasible.
`RIG_REPOS` is seeded intentionally partial — the coverage probe surfaces every
rig that still needs a mapping as a CONFIG GAP, which is the signal to fill it in.
"""

from collections.abc import Mapping


class UnmappedRigError(KeyError):
    """A rig has no repo mapping. Add it to `RIG_REPOS` (or backfill `repo` into the
    WorkRecord via mem-bme) — never silently treat the bead as env-infeasible."""


RIG_REPOS: dict[str, str] = {}


def repo_for_rig(rig: str, rig_map: Mapping[str, str] | None = None) -> str:
    """Resolve `rig` to its repo, or raise `UnmappedRigError`. Pass `rig_map` to
    override the module default (injectable for tests / experiments)."""
    mapping = RIG_REPOS if rig_map is None else rig_map
    try:
        return mapping[rig]
    except KeyError as exc:
        raise UnmappedRigError(
            f"rig {rig!r} has no repo mapping (config/rigs.py RIG_REPOS); add it "
            "or backfill repo into the WorkRecord (mem-bme) — do not silently "
            "reclassify as env-infeasible."
        ) from exc
