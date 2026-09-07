"""Frozen eight-session schedules with globally audited, no-repurchase journals."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from membench.runner.e1_grid import out_lock, write_json_new
from membench.runner.resume_cache import digest

SessionRunner = Callable[[Mapping[str, Any], Mapping[str, Any], Path], dict[str, Any]]
SCHEMA = "bd-component-experiment.v1"
GUIDANCE_SCHEMA = "bd-guidance-experiment.v1"
CONFIRMATION_SCHEMA = "bd-confirmation-experiment.v1"
STATES = {"completed", "terminal_timeout", "blocked_integrity_or_infrastructure"}
EXPECTED = {
    ("capture", intervention, condition, "empty" if intervention == "opportunity" else "seeded")
    for intervention in ("opportunity", "already_known")
    for condition in ("current", "focused")
} | {
    ("retrieval", intervention, "current", "empty" if intervention == "empty" else "seeded")
    for intervention in ("optional", "explicit", "empty", "briefed")
}


GUIDANCE_EXPECTED = {
    ("capture", intervention, guidance, "empty" if intervention == "opportunity" else "seeded")
    for intervention in ("opportunity", "already_known")
    for guidance in ("current", "explicit")
} | {
    ("retrieval", intervention, guidance, "seeded")
    for intervention in ("optional", "explicit")
    for guidance in ("current", "procedural")
}


CONFIRMATION_EXPECTED = {
    (component, intervention, replicate, store)
    for component, intervention, store in (
        ("capture", "opportunity", "empty"),
        ("capture", "already_known", "seeded"),
        ("retrieval", "seeded", "seeded"),
        ("retrieval", "empty", "empty"),
    )
    for replicate in (1, 2)
}


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing or symlink journal: {path}")
    return _object(json.loads(path.read_text()), str(path))


def _new(path: Path, value: Mapping[str, Any]) -> None:
    # The shared helper otherwise creates attempt sidecars: forbidden in this journal.
    if path.exists() or path.is_symlink():
        raise ValueError(f"Write-once journal already exists: {path}")
    write_json_new(path, value)


def _relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("Expected a nonempty safe relative path")
    path = Path(value)
    if path.is_absolute() or any(part in (".", "..") for part in value.split("/")):
        raise ValueError("Unsafe relative path")
    return value


def _hash(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Missing or symlink artifact: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(root: Path, value: Any) -> None:
    record = _object(value, "artifact")
    name = _relative(record.get("path"))
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Artifact escapes input root")
    if _hash(path) != record.get("sha256"):
        raise ValueError(f"Artifact identity changed: {path}")


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Check the exact schedule and every frozen input before invocation."""
    if (
        manifest.get("schema") not in {SCHEMA, GUIDANCE_SCHEMA, CONFIRMATION_SCHEMA}
        or manifest.get("planned_sessions") != 8
        or manifest.get("failure_policy") != "stop_and_review"
    ):
        raise ValueError("Expected the frozen eight-session protocol")
    config = _object(manifest.get("configuration"), "configuration")
    for key in ("input_root", "repo_absolute", "agent_python", "bd_binary"):
        value = config.get(key)
        if not isinstance(value, str) or "\x00" in value or not Path(value).is_absolute():
            raise ValueError(f"Absolute {key} is required")
    for key in ("model", "cli_version", "seed_key"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"Pinned {key} is required")
    if not re.fullmatch("[a-f0-9]{40}", str(config.get("base_commit", ""))):
        raise ValueError("Exact base commit is required")
    timeout = config.get("timeout_s")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("Finite positive timeout is required")
    _schedule(manifest, Path(config["input_root"]))
    pins = manifest.get("pins")
    if not isinstance(pins, list) or not pins:
        raise ValueError("Immutable execution pins are required")
    seen = set()
    for pin in pins:
        record = _object(pin, "pin")
        path = Path(record.get("path", ""))
        if not path.is_absolute() or str(path) in seen or _hash(path) != record.get("sha256"):
            raise ValueError("Missing, duplicate or changed execution pin")
        seen.add(str(path))
    if not {str(Path(config[key]).resolve()) for key in ("agent_python", "bd_binary")} <= seen:
        raise ValueError("Interpreter and bd must be artifact-pinned")


def _schedule(manifest: Mapping[str, Any], root: Path) -> None:
    rows = manifest.get("schedule")
    if not isinstance(rows, list) or len(rows) != 8:
        raise ValueError("Exactly eight rows required")
    ids: set[str] = set()
    combinations = []
    seeds = []
    capture_sources = []
    capture_prompts: dict[str, list[dict[str, Any]]] = {}
    guidance_protocol = manifest["schema"] == GUIDANCE_SCHEMA
    confirmation_protocol = manifest["schema"] == CONFIRMATION_SCHEMA
    label = (
        "replicate" if confirmation_protocol else "guidance" if guidance_protocol else "condition"
    )
    for value in rows:
        row = _object(value, "row")
        row_id = row.get("row_id")
        if (
            not isinstance(row_id, str)
            or not re.fullmatch("[a-z0-9][a-z0-9_-]*", row_id)
            or row_id in ids
        ):
            raise ValueError("Unique safe row IDs are required")
        ids.add(row_id)
        if (guidance_protocol or confirmation_protocol) and row.get("condition") != "current":
            raise ValueError("Guidance/confirmation requires the current adapter condition")
        if confirmation_protocol and type(row.get("replicate")) is not int:
            raise ValueError("Confirmation replicate must be an integer")
        combinations.append(
            tuple(row.get(k) for k in ("component", "intervention", label, "initial_store"))
        )
        _artifact(root, row.get("prompt"))
        sources = row.get("sources")
        if not isinstance(sources, list):
            raise ValueError("Row source inventory required")
        targets = []
        for source in sources:
            _artifact(root, source)
            targets.append(_relative(source.get("target_path")))
        if len(set(targets)) != len(targets):
            raise ValueError("Duplicate source destination")
        if row.get("component") == "retrieval" and sources:
            raise ValueError("Retrieval cannot receive capture sources")
        if row.get("component") == "capture":
            if not sources:
                raise ValueError("Capture requires prior evidence")
            capture_sources.append(sources)
            group = str(row.get("guidance")) if guidance_protocol else "all"
            capture_prompts.setdefault(group, []).append(row["prompt"])
        if row.get("initial_store") == "seeded":
            _artifact(root, row.get("seed"))
            seeds.append(row["seed"])
        elif row.get("seed") is not None:
            raise ValueError("Empty rows cannot receive seeds")
    expected = (
        CONFIRMATION_EXPECTED
        if confirmation_protocol
        else GUIDANCE_EXPECTED if guidance_protocol else EXPECTED
    )
    if set(combinations) != expected:
        raise ValueError("Schedule intervention combinations differ from protocol")
    if any(prompt != prompts[0] for prompts in capture_prompts.values() for prompt in prompts):
        raise ValueError("Capture prompts must match within each guidance group")
    if any(seed != seeds[0] for seed in seeds) or any(
        sources != capture_sources[0] for sources in capture_sources
    ):
        raise ValueError("Seed and capture evidence must match across conditions")
    if confirmation_protocol:
        _confirmation_inputs(rows, seeds[0])


def _confirmation_inputs(rows: list[dict[str, Any]], seed: Mapping[str, Any]) -> None:
    """Keep confirmation interventions in store state, not visible source/prompt changes."""
    prompts = [row["prompt"] for row in rows if row["component"] == "retrieval"]
    if any(prompt != prompts[0] for prompt in prompts):
        raise ValueError("Confirmation retrieval prompts must match")
    for row in rows:
        for artifact in [row["prompt"], *row["sources"]]:
            if artifact["path"] == seed["path"] or artifact["sha256"] == seed["sha256"]:
                raise ValueError("Seed artifact cannot be supplied as a prompt or source")


def freeze(out: Path, manifest: Mapping[str, Any]) -> None:
    """Freeze a manifest without executing any session."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out_lock(out):
        validate_manifest(manifest)
        if out.is_symlink():
            raise ValueError("Output cannot be a symlink")
        out.mkdir(exist_ok=True)
        if (out / "manifest.json").exists():
            _frozen(out, manifest)
        elif any(out.iterdir()):
            raise ValueError("Nonempty output has no frozen manifest")
        else:
            _new(out / "manifest.json", manifest)


def _frozen(out: Path, manifest: Mapping[str, Any]) -> None:
    if out.is_symlink() or _read(out / "manifest.json") != manifest:
        raise ValueError("Frozen manifest changed")


def _identity(row: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {"row": dict(row), "manifest_digest": digest(manifest)}


def _inventory(directory: Path) -> dict[str, str]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Missing run evidence directory")
    inventory = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink in raw evidence")
        if path.is_file():
            inventory[str(path.relative_to(directory))] = _hash(path)
        elif not path.is_dir():
            raise ValueError("Unsupported raw evidence file type")
    return inventory


def _result(directory: Path, row: Mapping[str, Any], result: Any) -> dict[str, Any]:
    value = _object(result, "session result")
    if any(value.get(k) != row[k] for k in ("row_id", "component", "intervention", "condition")):
        raise ValueError("Returned session identity differs from row")
    if value.get("status") not in STATES:
        raise ValueError("Unknown terminal status")
    if _read(directory / "run/component-result.json") != value:
        raise ValueError("Persisted result differs from returned result")
    inventory = _inventory(directory / "run")
    if value["status"] != "blocked_integrity_or_infrastructure":
        _required_evidence(directory, row, value, inventory)
    agent = value.get("agent")
    if value["status"] != "blocked_integrity_or_infrastructure":
        agent = _object(agent, "agent evidence")
        if value["status"] == "terminal_timeout":
            from membench.runner.bd_component_session import timeout_evidence_valid

            process = _read(directory / "run/leg-0/process.json")
            if (
                not timeout_evidence_valid(agent)
                or process.get("status") != "timeout"
                or process.get("returncode") is not None
            ):
                raise ValueError("Terminal timeout lacks valid agent/process evidence")
        elif agent.get("status") != "ok" or agent.get("integrity_errors") != []:
            raise ValueError("Terminal state does not match agent integrity/status")
    return inventory


def _required_evidence(
    directory: Path, row: Mapping[str, Any], value: Mapping[str, Any], inventory: Mapping[str, str]
) -> None:
    from membench.runner.bd_component_session import REQUIRED_ARTIFACTS

    required = set(REQUIRED_ARTIFACTS) | {
        "prompt.txt",
        "harness-seed/empty-check.json",
        "harness-seed/initial-inventory.json",
    }
    if row["initial_store"] == "seeded":
        required |= {"harness-seed/write.json", "harness-seed/readback.json"}
    if not required <= inventory.keys():
        raise ValueError(
            f"Missing required raw session evidence: {sorted(required - inventory.keys())}"
        )
    run = directory / "run"
    if _read(run / "leg-0/result.json") != value.get("agent"):
        raise ValueError("Persisted agent evidence differs from component result")
    if _read(run / "initial-memory.json") != value.get("initial_memory"):
        raise ValueError("Initial memory evidence differs from component result")
    if _read(run / "leg-0-snapshots.json").get("completed") is not True:
        raise ValueError("Incomplete snapshots cannot satisfy terminal observation")


def _audit(out: Path, manifest: Mapping[str, Any]) -> dict[str, str]:
    root = out / "sessions"
    rows = manifest["schedule"]
    if root.is_symlink():
        raise ValueError("Sessions directory cannot be a symlink")
    if root.exists() and {p.name for p in root.iterdir()} - {r["row_id"] for r in rows}:
        raise ValueError("Unscheduled session evidence exists")
    states = {}
    for row in rows:
        directory = root / row["row_id"]
        if not directory.exists():
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Invalid session directory")
        identity = _identity(row, manifest)
        if _read(directory / "started.json") != identity:
            raise ValueError("Started identity changed")
        terminal = _read(directory / "terminal.json")
        if terminal.get("identity") != identity:
            raise ValueError("Terminal identity changed")
        inventory = _result(directory, row, terminal.get("result"))
        if terminal.get("artifact_sha256") != inventory or not inventory:
            raise ValueError("Terminal raw evidence changed")
        allowed = {"started.json", "terminal.json", "run"}
        status = terminal["result"]["status"]
        if (directory / "reconciliation.json").exists():
            allowed.add("reconciliation.json")
            _reconciliation(directory, terminal)
            status = "reconciled_timeout"
        if {p.name for p in directory.iterdir()} != allowed:
            raise ValueError("Unrecognized session journal files")
        states[row["row_id"]] = status
    return states


def _reconciliation(directory: Path, terminal: Mapping[str, Any]) -> None:
    value = _read(directory / "reconciliation.json")
    if (
        terminal["result"]["status"] != "terminal_timeout"
        or value.get("terminal_digest") != digest(terminal)
        or not isinstance(value.get("reviewer"), str)
        or not value["reviewer"].strip()
        or not isinstance(value.get("reason"), str)
        or not value["reason"].strip()
    ):
        raise ValueError("Invalid timeout reconciliation")


def reconcile_timeout(
    out: Path, manifest: Mapping[str, Any], row_id: str, *, reviewer: str, reason: str
) -> None:
    """Record a reviewed timeout skip; never replace its consumed invocation slot."""
    with out_lock(out):
        _frozen(out, manifest)
        validate_manifest(manifest)
        states = _audit(out, manifest)
        if states.get(row_id) != "terminal_timeout" or not reviewer.strip() or not reason.strip():
            raise ValueError("Only an audited timeout can be reconciled")
        directory = out / "sessions" / row_id
        _new(
            directory / "reconciliation.json",
            {
                "terminal_digest": digest(_read(directory / "terminal.json")),
                "reviewer": reviewer,
                "reason": reason,
            },
        )


def _run(
    directory: Path, row: Mapping[str, Any], manifest: Mapping[str, Any], runner: SessionRunner
) -> str:
    directory.mkdir(parents=True)
    identity = _identity(row, manifest)
    _new(directory / "started.json", identity)
    try:
        result = runner(row, manifest["configuration"], directory / "run")
        inventory = _result(directory, row, result)
        _new(
            directory / "terminal.json",
            {"identity": identity, "result": result, "artifact_sha256": inventory},
        )
        return str(result["status"])
    except BaseException as exc:
        _new(directory / "halt.json", {"type": type(exc).__name__, "error": str(exc)})
        raise


def execute(
    out: Path,
    manifest: Mapping[str, Any],
    *,
    session_runner: SessionRunner,
    identity_check: Callable[[], None],
    max_sessions: int = 8,
) -> dict[str, Any]:
    """Audit every scheduled cell before spending on any untouched row."""
    if isinstance(max_sessions, bool) or not 1 <= max_sessions <= 8:
        raise ValueError("max_sessions must be between one and eight")
    new = 0
    with out_lock(out):
        _frozen(out, manifest)
        validate_manifest(manifest)
        states = _audit(out, manifest)
        if any(status not in {"completed", "reconciled_timeout"} for status in states.values()):
            raise ValueError(
                "Terminal failure requires reviewed reconciliation before new sessions"
            )
        reused = len(states)
        for row in manifest["schedule"]:
            if row["row_id"] in states or new >= max_sessions:
                continue
            _frozen(out, manifest)
            validate_manifest(manifest)
            _audit(out, manifest)
            identity_check()
            status = _run(out / "sessions" / row["row_id"], row, manifest, session_runner)
            new += 1
            if status != "completed":
                return {"new_sessions": new, "reused_sessions": reused, "halted": True}
    return {"new_sessions": new, "reused_sessions": reused, "halted": False}
