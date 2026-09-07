"""Finite cross-batch reservations and global no-repurchase campaign auditing."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from membench.runner import bd_component_experiment as component
from membench.runner.e1_grid import out_lock
from membench.runner.resume_cache import digest

LIMITS = {"total": 96, "development": 24, "replication": 24, "transfer": 48}
POLICY = {
    "schema": "bd-reliability-campaign.v1",
    "limits": LIMITS,
    "batch_sessions": 8,
    "failure_policy": "stop_and_review",
    "session_identity": "batch_id/row_id",
}


def _policy(out: Path) -> None:
    if out.is_symlink() or component._read(out / "campaign.json") != POLICY:
        raise ValueError("Campaign policy is missing or changed")


def initialize(out: Path) -> None:
    """Create the fixed finite campaign ledger, without registering or executing work."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out_lock(out):
        if out.is_symlink():
            raise ValueError("Campaign root cannot be a symlink")
        out.mkdir(exist_ok=True)
        if (out / "campaign.json").exists():
            _policy(out)
        elif any(out.iterdir()):
            raise ValueError("Nonempty campaign has no policy; refusing initialization")
        else:
            component._new(out / "campaign.json", POLICY)


def _registered(path: Path) -> dict[str, Any]:
    record = component._read(path)
    body = {key: value for key, value in record.items() if key != "registration_digest"}
    if record.get("registration_digest") != digest(body):
        raise ValueError("Batch registration identity changed")
    if (
        body.get("campaign_digest") != digest(POLICY)
        or body.get("batch_id") != path.stem
        or body.get("stage") not in LIMITS
        or body["stage"] == "total"
        or body.get("planned_sessions") != 8
        or path.suffix != ".json"
    ):
        raise ValueError("Invalid campaign batch registration")
    return record


def _registration(
    batch: Path, record: Mapping[str, Any], *, active: bool = False
) -> dict[str, Any]:
    if batch.is_symlink() or not batch.is_dir():
        raise ValueError("Batch must be a contained real directory")
    if component._read(batch / "registration.json") != record:
        raise ValueError("Batch differs from independent registration receipt")
    allowed = {"registration.json", "run", "run.lock"} if active else {"registration.json", "run"}
    if {p.name for p in batch.iterdir()} != allowed:
        raise ValueError("Batch has missing or unrecognized journal entries")
    if active:
        lock = batch / "run.lock"
        if lock.is_symlink() or lock.read_text().strip() != str(os.getpid()):
            raise ValueError("Active batch lock ownership changed")
    manifest = component._read(batch / "run/manifest.json")
    if digest(manifest) != record.get("manifest_digest"):
        raise ValueError("Batch frozen manifest changed")
    if manifest.get("planned_sessions") != record["planned_sessions"]:
        raise ValueError("Reservation differs from actual planned session count")
    # Saved pins, not previous verify_live_identity against the new executing source.
    component.validate_manifest(manifest)
    return manifest


def _consumed(out: Path, batch: Path, manifest_digest: str) -> tuple[int, list[str]]:
    sessions, ledger = batch / "run/sessions", out / "invocations" / batch.name
    if sessions.is_symlink() or ledger.is_symlink():
        raise ValueError("Invocation directories cannot be symlinks")
    observed = (
        {p.name for p in sessions.iterdir() if (p / "started.json").exists()}
        if sessions.is_dir()
        else set()
    )
    entries = list(ledger.iterdir()) if ledger.is_dir() else []
    if any(path.is_symlink() or not path.is_file() or path.suffix != ".json" for path in entries):
        raise ValueError("Unrecognized invocation receipt entry")
    if len({path.stem for path in entries}) != len(entries):
        raise ValueError("Duplicate invocation receipt identity")
    receipts = {path.stem: path for path in entries}
    issues = []
    if observed != set(receipts):
        issues.append(f"{batch.name}: started rows differ from independent invocation receipts")
    for row_id, path in receipts.items():
        try:
            receipt = component._read(path)
            expected = {
                "batch_id": batch.name,
                "row_id": row_id,
                "manifest_digest": manifest_digest,
                "started": component._read(sessions / row_id / "started.json"),
            }
            if receipt != expected or path.suffix != ".json":
                raise ValueError("Invocation receipt differs from started row")
        except (OSError, ValueError, TypeError) as error:
            issues.append(f"{batch.name}/{row_id}: {type(error).__name__}: {error}")
    return len(observed | set(receipts)), issues


def audit_campaign(out: Path) -> dict[str, Any]:
    """Inspect all registered batches without changing any journal or acquiring a lock."""
    return _audit_campaign(out)


def _roots(out: Path) -> tuple[Path, Path, list[str]]:
    issues = []
    if {p.name for p in out.iterdir()} - {
        "campaign.json",
        "batches",
        "registrations",
        "invocations",
    }:
        issues.append("Unrecognized campaign journal entries")
    root, registry = out / "batches", out / "registrations"
    for directory in (root, registry, out / "invocations"):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError(f"Invalid campaign directory: {directory.name}")
    known = {p.stem for p in registry.iterdir()} if registry.exists() else set()
    actual = {p.name for p in root.iterdir()} if root.exists() else set()
    invocation_root = out / "invocations"
    invocation_batches = (
        {p.name for p in invocation_root.iterdir()} if invocation_root.exists() else set()
    )
    if invocation_batches - known:
        issues.append("Invocation history exists for an unregistered batch")
    if known != actual:
        issues.append(
            "Registered batch directories missing or unregistered batch directories present"
        )
    return root, registry, issues


def _batch_status(
    batch: Path, record: Mapping[str, Any], active: bool, consumed: int
) -> dict[str, Any]:
    manifest = _registration(batch, record, active=active)
    states = component._audit(batch / "run", manifest)
    result = {
        "stage": record["stage"],
        "reserved": record["planned_sessions"],
        "started": consumed,
        "states": states,
        "manifest_digest": record["manifest_digest"],
    }
    if any(state not in {"completed", "reconciled_timeout"} for state in states.values()):
        raise ValueError("Unreconciled terminal failure blocks new campaign sessions")
    return result


def _cap_issues(reserved: int, started: int, stages: Mapping[str, Any]) -> list[str]:
    issues = []
    if reserved > LIMITS["total"] or started > LIMITS["total"]:
        issues.append("Global campaign session cap exceeded")
    for stage, counts in stages.items():
        if counts["reserved"] > LIMITS[stage] or counts["started"] > LIMITS[stage]:
            issues.append(f"{stage}: campaign stage session cap exceeded")
    return issues


def _orphan_counts(out: Path, registered: set[str]) -> tuple[int, list[str]]:
    names: set[str] = set()
    for root in (out / "batches", out / "invocations"):
        if root.exists():
            names.update(path.name for path in root.iterdir())
    count, issues = 0, []
    for name in names - registered:
        consumed, errors = _consumed(out, out / "batches" / name, "unregistered")
        count += consumed
        issues.extend(errors)
    return count, issues


def _observed_starts(out: Path, batch: Path) -> int:
    """Count both histories before trusting a potentially corrupt registration."""
    sessions, ledger = batch / "run/sessions", out / "invocations" / batch.name
    observed = set()
    if not batch.is_symlink() and not sessions.is_symlink() and sessions.is_dir():
        observed = {path.name for path in sessions.iterdir() if (path / "started.json").exists()}
    receipts = (
        {path.stem for path in ledger.iterdir()}
        if ledger.is_dir() and not ledger.is_symlink()
        else set()
    )
    return len(observed | receipts)


def _audit_campaign(out: Path, active_batch: str | None = None) -> dict[str, Any]:
    _policy(out)
    stages = {stage: {"reserved": 0, "started": 0} for stage in LIMITS if stage != "total"}
    root, registry, issues = _roots(out)
    batches: dict[str, Any] = {}
    seen_digests: set[str] = set()
    reserved, started = 0, 0
    unknown_reservations: list[str] = []
    unknown_stage_started = 0
    for path in sorted(registry.iterdir()) if registry.exists() else []:
        batch = root / path.stem
        consumed = _observed_starts(out, batch)
        started += consumed
        registered = False
        try:
            record = _registered(path)
            registered = True
            amount, stage = record["planned_sessions"], record["stage"]
            reserved += amount
            stages[stage]["reserved"] += amount
            stages[stage]["started"] += consumed
            _, invocation_issues = _consumed(out, batch, record["manifest_digest"])
            issues.extend(invocation_issues)
            if record["manifest_digest"] in seen_digests:
                raise ValueError("Duplicate manifest registered under another batch ID")
            seen_digests.add(record["manifest_digest"])
            batches[batch.name] = _batch_status(batch, record, batch.name == active_batch, consumed)
        except (OSError, ValueError, TypeError) as error:
            issues.append(f"{path.stem}: {type(error).__name__}: {error}")
            batches[batch.name] = {"started": consumed, "integrity": "unknown"}
            if not registered:
                unknown_reservations.append(batch.name)
                unknown_stage_started += consumed
    orphaned, orphan_issues = _orphan_counts(out, set(batches))
    started += orphaned
    issues.extend(orphan_issues)
    issues.extend(_cap_issues(reserved, started, stages))
    return {
        "limits": dict(LIMITS),
        "reserved": reserved,
        "started": started,
        "reservation_unknown_batches": unknown_reservations,
        "unknown_stage_started": unknown_stage_started + orphaned,
        "stages": stages,
        "batches": batches,
        "issues": issues,
    }


def _clean(out: Path, active_batch: str | None = None) -> dict[str, Any]:
    report = _audit_campaign(out, active_batch)
    if report["issues"]:
        raise ValueError("Campaign audit refuses new calls: " + "; ".join(report["issues"]))
    return report


def register_batch(out: Path, batch_id: str, stage: str, manifest: Mapping[str, Any]) -> Path:
    """Reserve a full frozen batch before any calls; repeat registration is an error."""
    if not isinstance(batch_id, str) or not re.fullmatch("[a-z0-9][a-z0-9_-]*", batch_id):
        raise ValueError("Safe unique batch ID required")
    if stage not in LIMITS or stage == "total":
        raise ValueError("Unknown campaign stage")
    with out_lock(out):
        report = _clean(out)
        component.validate_manifest(manifest)
        amount = manifest["planned_sessions"]
        batch = out / "batches" / batch_id
        if batch.exists() or batch.is_symlink():
            raise ValueError("Batch ID already registered or partial; never overwrite")
        if (
            report["reserved"] + amount > LIMITS["total"]
            or report["stages"][stage]["reserved"] + amount > LIMITS[stage]
        ):
            raise ValueError("Campaign reservation exceeds stage or global allowance")
        manifest_digest = digest(manifest)
        if any(row.get("manifest_digest") == manifest_digest for row in report["batches"].values()):
            raise ValueError(
                "Manifest already registered; intentional replication needs a new identity"
            )
        body = {
            "campaign_digest": digest(POLICY),
            "batch_id": batch_id,
            "stage": stage,
            "planned_sessions": amount,
            "manifest_digest": manifest_digest,
        }
        record = {**body, "registration_digest": digest(body)}
        registry = out / "registrations"
        registry.mkdir(exist_ok=True)
        component._new(registry / f"{batch_id}.json", record)
        batch.mkdir(parents=True)
        component._new(batch / "registration.json", record)
        component.freeze(batch / "run", manifest)
        _clean(out)
        return batch / "run"


def execute_batch(
    out: Path,
    batch_id: str,
    *,
    session_runner: component.SessionRunner,
    identity_check: Callable[[], None],
    max_sessions: int = 8,
) -> dict[str, Any]:
    """Hold the campaign lock through unchanged per-batch execution and pre-call audits."""
    with out_lock(out):
        report = _clean(out)
        if batch_id not in report["batches"]:
            raise ValueError("Batch is not registered")
        batch = out / "batches" / batch_id
        manifest = _registration(batch, _registered(out / "registrations" / f"{batch_id}.json"))

        def before_call() -> None:
            current = _clean(out, batch_id)
            stage = current["batches"][batch_id]["stage"]
            if (
                current["started"] >= LIMITS["total"]
                or current["stages"][stage]["started"] >= LIMITS[stage]
            ):
                raise ValueError("No campaign invocation slots remain")
            identity_check()

        def recorded_runner(
            row: Mapping[str, Any], configuration: Mapping[str, Any], run: Path
        ) -> dict[str, Any]:
            ledger = out / "invocations" / batch_id
            ledger.mkdir(parents=True, exist_ok=True)
            started = component._read(run.parent / "started.json")
            if started != component._identity(row, manifest):
                raise ValueError("Campaign invocation start identity changed")
            component._new(
                ledger / f'{row["row_id"]}.json',
                {
                    "batch_id": batch_id,
                    "row_id": row["row_id"],
                    "manifest_digest": digest(manifest),
                    "started": started,
                },
            )
            return session_runner(row, configuration, run)

        return component.execute(
            batch / "run",
            manifest,
            session_runner=recorded_runner,
            identity_check=before_call,
            max_sessions=max_sessions,
        )
