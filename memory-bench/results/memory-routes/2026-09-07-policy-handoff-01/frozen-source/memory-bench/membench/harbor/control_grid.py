"""Drive the M3/M4 control conditions over a bundle pool (build-or-exclude loop).

The control conditions are brute-force ceilings whose payloads (a raw transcript, an
all-prior-work dump) are FAR likelier to leak the gold diff than a distilled lesson —
so the dominant outcome at scale is a leak-guard exclusion, NOT a score (premortem
lens 5). This runner makes that first-class: each (bundle, condition) either BUILDS a
task dir (ready for the Harbor exec path) or is EXCLUDED with a recorded reason
(leak / no-transcript), and truncation is surfaced. A dry run stops after build —
constructing + leak-validating every task without an agent run — which is the fast,
real exercise of the integration on real data.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from membench.grading.leak_guard import OutcomeLeakError
from membench.harbor.control_conditions import FULL_CONTEXT, RAW_TRAJECTORY, InScopeWork
from membench.harbor.env_recon import DEFAULT_RIG_REPOS
from membench.harbor.probe_gate import DEFAULT_CONTROL_MAX_CHARS, build_probe_task
from membench.schemas.bundle import TaskBundle

# build_probe_task is injectable so the loop is testable without git/reconstruct_env.
TaskBuilder = Callable[..., Path]


@dataclass(frozen=True)
class ControlTaskOutcome:
    """One (bundle, condition) build result. ``status`` is ``built`` |
    ``leak_excluded`` | ``no_transcript``; ``reason`` localizes a non-built status;
    ``truncated`` flags a payload clipped to the char budget."""

    work_id: str
    condition: str
    status: str
    reason: str
    truncated: bool
    task_dir: str | None


def resolve_raw_transcript(bundle: TaskBundle) -> str | None:
    """The raw transcript text from ``bundle.trace_ref`` (the M3 payload source).
    ``None`` when the trace file is absent — a recorded ``no_transcript`` exclusion,
    never a silently-empty payload."""
    path = Path(bundle.trace_ref)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def build_one(
    bundle: TaskBundle,
    condition: str,
    task_dir: Path,
    *,
    rig_repos: Mapping[str, Path] = DEFAULT_RIG_REPOS,
    raw_transcript: str | None = None,
    in_scope_payloads: Mapping[str, InScopeWork] | None = None,
    max_chars: int = DEFAULT_CONTROL_MAX_CHARS,
    builder: TaskBuilder = build_probe_task,
) -> ControlTaskOutcome:
    """Build one control task, converting a leak-guard rejection into a recorded
    exclusion rather than a crash (the run-level coverage signal)."""
    if condition == RAW_TRAJECTORY and raw_transcript is None:
        return ControlTaskOutcome(
            work_id=bundle.work_id,
            condition=condition,
            status="no_transcript",
            reason=f"trace_ref {bundle.trace_ref!r} is absent; cannot build raw-trajectory",
            truncated=False,
            task_dir=None,
        )
    try:
        built = builder(
            bundle,
            condition,
            task_dir,
            rig_repos=rig_repos,
            raw_transcript=raw_transcript,
            in_scope_payloads=in_scope_payloads,
            control_max_chars=max_chars,
        )
    except OutcomeLeakError as exc:
        return ControlTaskOutcome(
            work_id=bundle.work_id,
            condition=condition,
            status="leak_excluded",
            reason=str(exc),
            truncated=False,
            task_dir=None,
        )
    return ControlTaskOutcome(
        work_id=bundle.work_id,
        condition=condition,
        status="built",
        reason="ok",
        truncated=(built / "truncation.json").exists(),
        task_dir=str(built),
    )


def coverage_summary(outcomes: Sequence[ControlTaskOutcome]) -> dict[str, object]:
    """The build-coverage report: counts per status + the excluded work_ids with
    reasons, so a coverage hole is labeled, never silent."""
    by_status: dict[str, list[str]] = {}
    for o in outcomes:
        by_status.setdefault(o.status, []).append(o.work_id)
    return {
        "n": len(outcomes),
        "counts": {k: len(v) for k, v in sorted(by_status.items())},
        "built": sorted(by_status.get("built", [])),
        "excluded": [
            {"work_id": o.work_id, "status": o.status, "reason": o.reason}
            for o in outcomes
            if o.status != "built"
        ],
        "truncated": sorted(o.work_id for o in outcomes if o.truncated),
    }


def run_control_build(
    bundles: Sequence[TaskBundle],
    condition: str,
    out_root: Path,
    *,
    rig_repos: Mapping[str, Path] = DEFAULT_RIG_REPOS,
    transcript_resolver: Callable[[TaskBundle], str | None] = resolve_raw_transcript,
    in_scope_resolver: Callable[[TaskBundle], Mapping[str, InScopeWork]] | None = None,
    max_chars: int = DEFAULT_CONTROL_MAX_CHARS,
    builder: TaskBuilder = build_probe_task,
) -> list[ControlTaskOutcome]:
    """Build (dry-run) every (bundle, condition) task under ``out_root``, resolving
    the M3 transcript / M4 in-scope payloads per bundle. Returns the per-bundle
    outcomes; pair with ``coverage_summary`` for the report."""
    outcomes: list[ControlTaskOutcome] = []
    for bundle in bundles:
        raw = transcript_resolver(bundle) if condition == RAW_TRAJECTORY else None
        in_scope = (
            dict(in_scope_resolver(bundle))
            if (condition == FULL_CONTEXT and in_scope_resolver is not None)
            else None
        )
        outcomes.append(
            build_one(
                bundle,
                condition,
                out_root / f"{bundle.work_id}.{condition}",
                rig_repos=rig_repos,
                raw_transcript=raw,
                in_scope_payloads=in_scope,
                max_chars=max_chars,
                builder=builder,
            )
        )
    return outcomes
