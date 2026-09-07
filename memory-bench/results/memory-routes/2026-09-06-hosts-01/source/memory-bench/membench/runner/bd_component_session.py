"""One component observation using the existing isolated agent and receipt lifecycle."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from membench.runner import bd_real_pair as pair
from membench.runner.sandbox import assert_neutral_ancestry
from membench.runner.tool_surface import MemoryToolSurface, provision_memory_tool
from membench.spawn import Runner

BD_RUNNER: Runner = subprocess.run
REQUIRED_ARTIFACTS = (
    "component-result.json",
    "initial-memory.json",
    "initial-bd-store.tar",
    "leg-0-input-files.json",
    "leg-0-input.tar",
    "leg-0-output-files.json",
    "establish-output.tar",
    "leg-0-bd-store.tar",
    "leg-0-snapshots.json",
    "leg-0/result.json",
    "leg-0/process.json",
    "leg-0/raw.stream.jsonl",
    "leg-0/receipts.json",
    "leg-0/runtime.json",
    "leg-0/instructions.md",
    "leg-0/instruction-delivery.json",
    "leg-0/settings.json",
    "leg-0/argv.json",
)


def _artifact(root: Path, artifact: Mapping[str, Any]) -> bytes:
    relative = Path(artifact["path"])
    path = root / relative
    if relative.is_absolute() or ".." in relative.parts or not path.resolve().is_relative_to(root):
        raise ValueError("input artifact escapes frozen input root")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != artifact["sha256"]:
        raise ValueError(f"input artifact hash mismatch: {relative}")
    return content


def _inputs(row: Mapping[str, Any], configuration: Mapping[str, Any]) -> dict[str, bytes]:
    if row["component"] not in {"capture", "retrieval"} or row["condition"] not in {
        "current",
        "focused",
    }:
        raise ValueError("unsupported component or condition")
    if row["initial_store"] not in {"empty", "seeded"}:
        raise ValueError("unsupported initial store condition")
    if (row["initial_store"] == "seeded") != (row.get("seed") is not None):
        raise ValueError("seed artifact and initial store condition disagree")
    root = Path(configuration["input_root"]).resolve()
    result = {"prompt": _artifact(root, row["prompt"])}
    if row.get("seed") is not None:
        result["seed"] = _artifact(root, row["seed"])
    for source in row["sources"]:
        target = Path(source["target_path"])
        if (
            not target.parts
            or target.as_posix() in {"seed", "prompt"}
            or target.is_absolute()
            or ".." in target.parts
            or target.parts[0] == ".git"
        ):
            raise ValueError("source destination must be contained and outside .git")
        if target.as_posix() in result:
            raise ValueError("duplicate source destination")
        result[target.as_posix()] = _artifact(root, source)
    return result


def _bd(surface: MemoryToolSurface, args: list[str], out: Path, name: str) -> str:
    argv = [surface.bd_binary, "-C", str(surface.store_dir), *args]
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("BEADS_", "BD_", "DOLT_"))
    }
    try:
        result = BD_RUNNER(argv, capture_output=True, text=True, check=False, timeout=30, env=env)
    except (OSError, subprocess.TimeoutExpired) as error:
        pair._json(out / f"{name}.json", {"argv": argv, "status": "error", "error": str(error)})
        raise
    pair._json(
        out / f"{name}.json",
        {
            "argv": argv,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "provenance": "harness_only_not_agent_memory_use",
            "binary": surface.bd_binary,
        },
    )
    if result.returncode:
        raise RuntimeError(f"harness bd operation failed: {name}")
    return result.stdout


def _inventory(raw: str) -> dict[str, str]:
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("unexpected bd memory inventory schema")
    result = {key: content for key, content in value.items() if key != "schema_version"}
    if not all(isinstance(content, str) for content in result.values()):
        raise ValueError("bd inventory values must be strings")
    return result


def _initialize_memory(
    surface: MemoryToolSurface,
    inputs: Mapping[str, bytes],
    configuration: Mapping[str, Any],
    out: Path,
) -> dict[str, str]:
    evidence = out / "harness-seed"
    evidence.mkdir()
    if _inventory(_bd(surface, ["memories", "--json"], evidence, "empty-check")):
        raise RuntimeError("new store is not empty")
    expected = {}
    if "seed" in inputs:
        content = inputs["seed"].decode("utf-8")
        key = str(configuration["seed_key"])
        if not key or not content:
            raise ValueError("seed key and content must be nonempty")
        _bd(surface, ["remember", content, "--key", key], evidence, "write")
        readback = json.loads(_bd(surface, ["recall", key, "--json"], evidence, "readback"))
        if readback != {"schema_version": 1, "found": True, "key": key, "value": content}:
            raise RuntimeError("seed readback does not exactly match the frozen content")
        expected = {key: content}
    actual = _inventory(_bd(surface, ["memories", "--json"], evidence, "initial-inventory"))
    if actual != expected:
        raise RuntimeError("initial memory inventory differs from the frozen condition")
    pair._json(out / "initial-memory.json", actual)
    pair._snapshot(surface.store_dir, out / "initial-bd-store.tar")
    return actual


def _workspace(
    row: Mapping[str, Any], configuration: Mapping[str, Any], inputs: Mapping[str, bytes], cwd: Path
) -> None:
    if row["component"] == "retrieval":
        pair._archive_base(configuration, cwd)
    for name, content in inputs.items():
        if name in {"prompt", "seed"}:
            continue
        destination = cwd / name
        if destination.exists() or destination.is_symlink():
            raise ValueError("declared source would overwrite an archived repository file")
        if not destination.resolve().is_relative_to(cwd):
            raise ValueError("source destination escapes workspace")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


def _preserve_incomplete(root: Path, cwd: Path, out: Path) -> None:
    errors = {}
    for name, directory in (("store", root / "memory/store"), ("workspace", cwd)):
        if directory.exists():
            try:
                pair._snapshot(directory, out / f"setup-or-failed-{name}.tar")
            except Exception as failure:
                errors[name] = {"type": type(failure).__name__, "message": str(failure)}
    if errors:
        pair._json(out / "incomplete-snapshot-errors.json", errors)


def _execute(
    row: Mapping[str, Any], configuration: Mapping[str, Any], inputs: Mapping[str, bytes], out: Path
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    with tempfile.TemporaryDirectory(prefix="bd-component-", dir="/tmp") as temporary:
        root = Path(temporary)
        cwd = root / "workspace"
        cwd.mkdir()
        assert_neutral_ancestry(cwd)
        try:
            _workspace(row, configuration, inputs, cwd)
            surface = provision_memory_tool(
                root / "memory", sandbox=cwd, bd_binary=configuration["bd_binary"]
            )
            initial = _initialize_memory(surface, inputs, configuration, out)
            # Use a retained, verified literal copy, so the helper cannot reopen a changed prompt.
            (out / "prompt.txt").write_bytes(inputs["prompt"])
            agent = pair._run_snapshotted_leg(
                cwd=cwd,
                surface=surface,
                condition=row["condition"],
                out=out,
                leg=0,
                root=root,
                corpus_dir=out,
                artifacts={"prompt": {"path": "prompt.txt"}},
                prompt_key="prompt",
                model=configuration["model"],
                cli_version=configuration["cli_version"],
                timeout_s=float(configuration["timeout_s"]),
                agent_python=Path(configuration["agent_python"]),
                python_paths=tuple(configuration.get("python_paths", ["src"])),
            )
            return agent, initial
        finally:
            if not (out / "leg-0-snapshots.json").exists():
                _preserve_incomplete(root, cwd, out)


def timeout_evidence_valid(agent: Mapping[str, Any]) -> bool:
    """Only a missing terminal response is expected when a validated session times out."""
    errors = agent.get("integrity_errors")
    session = agent.get("session_id")
    return (
        agent.get("status") == "timeout"
        and isinstance(session, str)
        and bool(session.strip())
        and isinstance(errors, list)
        and all(error == "missing_or_failed_terminal_result" for error in errors)
    )


def run_component_session(
    row: Mapping[str, Any], configuration: Mapping[str, Any], out: Path
) -> dict[str, Any]:
    """Spend at most one invocation; scheduler owns immutable start and no-repurchase journals."""
    if out.exists():
        raise RuntimeError("session output already exists; never repurchase")
    out.mkdir(parents=True)
    agent: dict[str, Any] | None = None
    initial: dict[str, str] = {}
    error: dict[str, str] | None = None
    status = "blocked_integrity_or_infrastructure"
    try:
        pair.assert_managed_settings_absent()
        inputs = _inputs(row, configuration)
        agent, initial = _execute(row, configuration, inputs, out)
        if agent is not None and agent.get("status") == "ok" and not agent.get("integrity_errors"):
            status = "completed"
    except Exception as failure:
        error = {"type": type(failure).__name__, "message": str(failure)}
        try:
            agent = json.loads((out / "leg-0/result.json").read_text())
            initial = json.loads((out / "initial-memory.json").read_text())
            snapshot = json.loads((out / "leg-0-snapshots.json").read_text())
            process = json.loads((out / "leg-0/process.json").read_text())
            if (
                timeout_evidence_valid(agent)
                and snapshot.get("completed") is True
                and process.get("status") == "timeout"
                and process.get("returncode") is None
            ):
                status = "terminal_timeout"
        except (OSError, ValueError, AttributeError):
            pass  # The original error remains explicit; absent partial evidence is not a timeout.
    result = _result(row, status, agent, initial, error)
    pair._json(out / "component-result.json", result)
    return result


def _result(
    row: Mapping[str, Any],
    status: str,
    agent: dict[str, Any] | None,
    initial: dict[str, str],
    error: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "row_id": row["row_id"],
        "component": row["component"],
        "intervention": row["intervention"],
        "condition": row["condition"],
        "status": status,
        "agent": agent,
        "initial_memory": initial,
        "error": error,
        "task_check": {
            "status": (
                "pending_offline_grading" if row["component"] == "retrieval" else "not_applicable"
            )
        },
        "artifacts": {
            "workspace_after": "establish-output.tar",
            "store_after": "leg-0-bd-store.tar",
        },
    }
