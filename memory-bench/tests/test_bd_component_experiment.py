"""Eight-session lifecycle and immutable evidence tests (no provider calls)."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from membench.runner.bd_component_experiment import execute, freeze, reconcile_timeout


def manifest(tmp_path: Path) -> dict:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for name in ["prompt", "seed", "source", "binary"]:
        (inputs / name).write_text(name)

    def artifact(name: str) -> dict:
        return {"path": name, "sha256": hashlib.sha256((inputs / name).read_bytes()).hexdigest()}

    rows = []
    for intervention in ["opportunity", "already_known"]:
        for condition in ["current", "focused"]:
            rows.append(
                {
                    "row_id": f"{intervention}-{condition}",
                    "component": "capture",
                    "intervention": intervention,
                    "condition": condition,
                    "initial_store": "empty" if intervention == "opportunity" else "seeded",
                    "prompt": artifact("prompt"),
                    "sources": [{**artifact("source"), "target_path": "source.md"}],
                    "seed": None if intervention == "opportunity" else artifact("seed"),
                }
            )
    for intervention in ["optional", "explicit", "empty", "briefed"]:
        rows.append(
            {
                "row_id": intervention,
                "component": "retrieval",
                "intervention": intervention,
                "condition": "current",
                "initial_store": "empty" if intervention == "empty" else "seeded",
                "prompt": artifact("prompt"),
                "sources": [],
                "seed": None if intervention == "empty" else artifact("seed"),
            }
        )
    return {
        "schema": "bd-component-experiment.v1",
        "planned_sessions": 8,
        "failure_policy": "stop_and_review",
        "schedule": rows,
        "configuration": {
            "input_root": str(inputs),
            "repo_absolute": str(tmp_path),
            "base_commit": "a" * 40,
            "agent_python": str(inputs / "binary"),
            "bd_binary": str(inputs / "binary"),
            "model": "pinned",
            "cli_version": "1",
            "timeout_s": 30,
            "seed_key": "lesson",
        },
        "pins": [{"path": str(inputs / "binary"), "sha256": artifact("binary")["sha256"]}],
    }


def fake_runner(calls: list, status: str = "completed"):
    def run(row, configuration, out):
        calls.append(row["row_id"])
        out.mkdir(parents=True)
        result = {k: row[k] for k in ["row_id", "component", "intervention", "condition"]}
        result.update(
            status=status,
            agent={
                "status": "timeout" if status == "terminal_timeout" else "ok",
                "integrity_errors": [],
                "session_id": "local-session",
                "memory": {"accepted_writes": 1},
            },
            initial_memory={},
            artifacts={},
            task_check=None,
        )
        from membench.runner.bd_component_session import REQUIRED_ARTIFACTS

        for name in set(REQUIRED_ARTIFACTS) | {
            "prompt.txt",
            "harness-seed/empty-check.json",
            "harness-seed/initial-inventory.json",
            "harness-seed/write.json",
            "harness-seed/readback.json",
        }:
            path = out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}")
        (out / "component-result.json").write_text(json.dumps(result))
        (out / "leg-0/result.json").write_text(json.dumps(result["agent"]))
        (out / "leg-0/process.json").write_text(
            json.dumps(
                {
                    "status": "timeout" if status == "terminal_timeout" else "exited",
                    "returncode": None if status == "terminal_timeout" else 0,
                }
            )
        )
        (out / "initial-memory.json").write_text(json.dumps(result["initial_memory"]))
        (out / "leg-0-snapshots.json").write_text(json.dumps({"completed": True}))
        (out / "evidence.txt").write_text("actual preserved evidence")
        return result

    return run


def test_exact_eight_and_no_repurchase(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    calls = []
    freeze(out, m)
    result = execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    assert result["new_sessions"] == 8 and len(set(calls)) == 8
    assert (
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)[
            "new_sessions"
        ]
        == 0
    )
    assert len(calls) == 8


@pytest.mark.parametrize(
    "change", ["short", "duplicate", "rogue", "store", "seed", "traversal", "nan"]
)
def test_bad_manifest_before_any_session(tmp_path, change):
    m = manifest(tmp_path)
    if change == "short":
        m["schedule"].pop()
    elif change == "duplicate":
        m["schedule"][1] = copy.deepcopy(m["schedule"][0])
    elif change == "rogue":
        m["schedule"][0]["condition"] = "other"
    elif change == "store":
        m["schedule"][0]["initial_store"] = "seeded"
    elif change == "seed":
        m["schedule"][4]["seed"]["sha256"] = "b" * 64
    elif change == "traversal":
        m["schedule"][0]["prompt"]["path"] = "../secret"
    else:
        m["configuration"]["timeout_s"] = float("nan")
    with pytest.raises(ValueError):
        freeze(tmp_path / "out", m)


def test_late_partial_prevents_earlier_calls(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    freeze(out, m)
    late = out / "sessions" / m["schedule"][-1]["row_id"]
    late.mkdir(parents=True)
    (late / "started.json").write_text("{}")
    calls = []
    with pytest.raises(ValueError):
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    assert not calls


def test_timeout_requires_review_and_never_rebuys(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    freeze(out, m)
    calls = []
    assert execute(
        out, m, session_runner=fake_runner(calls, "terminal_timeout"), identity_check=lambda: None
    )["halted"]
    with pytest.raises(ValueError):
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    terminal = json.loads(
        (out / "sessions" / m["schedule"][0]["row_id"] / "terminal.json").read_text()
    )
    assert terminal["result"]["agent"]["memory"]["accepted_writes"] == 1
    assert terminal["result"]["status"] == "terminal_timeout"
    reconcile_timeout(
        out,
        m,
        m["schedule"][0]["row_id"],
        reviewer="human review",
        reason="Preserved timeout evidence audited",
    )
    assert (
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)[
            "new_sessions"
        ]
        == 7
    )
    assert len(calls) == 8


def test_mutated_terminal_or_pin_refuses(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    freeze(out, m)
    calls = []
    execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None, max_sessions=1)
    (out / "sessions" / m["schedule"][0]["row_id"] / "run/evidence.txt").write_text("altered")
    with pytest.raises(ValueError):
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    assert len(calls) == 1


def test_exception_consumes_slot(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    freeze(out, m)
    calls = []

    def broken(row, configuration, out):
        calls.append(row["row_id"])
        raise RuntimeError("infrastructure failure")

    with pytest.raises(RuntimeError):
        execute(out, m, session_runner=broken, identity_check=lambda: None)
    with pytest.raises(ValueError):
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    assert len(calls) == 1


def test_venv_interpreter_symlink_keeps_lexical_identity(tmp_path):
    m = manifest(tmp_path)
    link = tmp_path / "inputs" / "python"
    link.symlink_to("binary")
    m["configuration"]["agent_python"] = str(link)
    freeze(tmp_path / "out", m)


@pytest.mark.parametrize(
    "damage",
    ["unscheduled", "empty_inventory", "wrong_identity", "symlink", "extra_journal", "pin"],
)
def test_global_tamper_refusal(tmp_path, damage):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    calls = []
    freeze(out, m)
    execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None, max_sessions=1)
    cell = out / "sessions" / m["schedule"][0]["row_id"]
    if damage == "unscheduled":
        (out / "sessions" / "foreign").mkdir()
    elif damage == "extra_journal":
        (cell / "extra").touch()
    elif damage == "pin":
        (tmp_path / "inputs" / "binary").write_text("drift")
    elif damage == "symlink":
        (cell / "run" / "external").symlink_to(tmp_path / "inputs" / "source")
    else:
        p = cell / "terminal.json"
        v = json.loads(p.read_text())
        if damage == "empty_inventory":
            v["artifact_sha256"] = {}
        else:
            v["identity"]["row"]["row_id"] = "forged"
        p.write_text(json.dumps(v))
    with pytest.raises(ValueError):
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    assert len(calls) == 1


def test_wrong_returned_identity_stops_and_consumes(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    calls = []
    freeze(out, m)

    def wrong(row, configuration, path):
        result = fake_runner(calls)(row, configuration, path)
        return {**result, "row_id": "forged"}

    with pytest.raises(ValueError):
        execute(out, m, session_runner=wrong, identity_check=lambda: None)
    with pytest.raises(ValueError):
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    assert len(calls) == 1


def test_lock_shared_freeze_and_execute(tmp_path):
    from membench.runner.e1_grid import ResumeMismatchError, out_lock

    m = manifest(tmp_path)
    out = tmp_path / "out"
    freeze(out, m)
    calls = []
    with out_lock(out):
        with pytest.raises(ResumeMismatchError):
            freeze(out, m)
        with pytest.raises(ResumeMismatchError):
            execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    assert not calls


def test_mutation_after_first_run_stops_following_calls(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    calls = []
    freeze(out, m)

    def mutate(row, configuration, path):
        result = fake_runner(calls)(row, configuration, path)
        (tmp_path / "inputs" / "prompt").write_text("changed")
        return result

    with pytest.raises(ValueError):
        execute(out, m, session_runner=mutate, identity_check=lambda: None)
    assert len(calls) == 1


def test_capture_prompt_must_match_across_conditions(tmp_path):
    m = manifest(tmp_path)
    m["schedule"][1]["prompt"] = m["schedule"][0]["seed"] or {
        "path": "seed",
        "sha256": hashlib.sha256(b"seed").hexdigest(),
    }
    with pytest.raises(ValueError):
        freeze(tmp_path / "out", m)


@pytest.mark.parametrize("status", ["blocked_integrity_or_infrastructure", "unexpected"])
def test_failure_status_never_auto_continues(tmp_path, status):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    calls = []
    freeze(out, m)
    if status == "unexpected":
        with pytest.raises(ValueError):
            execute(out, m, session_runner=fake_runner(calls, status), identity_check=lambda: None)
    else:
        assert execute(
            out, m, session_runner=fake_runner(calls, status), identity_check=lambda: None
        )["halted"]
    with pytest.raises(ValueError):
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    with pytest.raises(ValueError):
        reconcile_timeout(out, m, m["schedule"][0]["row_id"], reviewer="r", reason="reason")
    assert len(calls) == 1


def test_reconciliation_binds_original_timeout_bytes(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    calls = []
    freeze(out, m)
    execute(
        out, m, session_runner=fake_runner(calls, "terminal_timeout"), identity_check=lambda: None
    )
    row = m["schedule"][0]["row_id"]
    reconcile_timeout(out, m, row, reviewer="r", reason="Checked evidence")
    p = out / "sessions" / row / "reconciliation.json"
    v = json.loads(p.read_text())
    v["terminal_digest"] = "forged"
    p.write_text(json.dumps(v))
    with pytest.raises(ValueError):
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    assert len(calls) == 1


def test_freeze_and_limits_fail_closed(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    freeze(out, m)
    freeze(out, m)
    with pytest.raises(ValueError):
        freeze(out, {**m, "extra": "changed"})
    for n in [0, 9, True]:
        with pytest.raises(ValueError):
            execute(
                out, m, session_runner=fake_runner([]), identity_check=lambda: None, max_sessions=n
            )
    other = tmp_path / "other"
    other.mkdir()
    (other / "extra").touch()
    with pytest.raises(ValueError):
        freeze(other, m)


def test_completed_receipt_requires_authentic_artifact_set(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    calls = []
    freeze(out, m)

    def identity_only(row, config, path):
        result = fake_runner(calls)(row, config, path)
        (path / "leg-0/receipts.json").unlink()
        return result

    with pytest.raises(ValueError, match=r"raw|artifact|evidence"):
        execute(out, m, session_runner=identity_only, identity_check=lambda: None)


@pytest.mark.parametrize("damage", ["agent", "initial", "snapshots"])
def test_persisted_session_records_must_agree(tmp_path, damage):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    calls = []
    freeze(out, m)

    def wrong(row, config, path):
        result = fake_runner(calls)(row, config, path)
        if damage == "agent":
            (path / "leg-0/result.json").write_text("{}")
        elif damage == "initial":
            (path / "initial-memory.json").write_text('{"extra":"unexpected"}')
        else:
            (path / "leg-0-snapshots.json").write_text('{"completed":false}')
        return result

    with pytest.raises(ValueError):
        execute(out, m, session_runner=wrong, identity_check=lambda: None)
    assert len(calls) == 1


def test_realistic_timeout_terminal_absence_can_be_reconciled(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "out"
    calls = []
    freeze(out, m)

    def realistic(row, config, path):
        result = fake_runner(calls, "terminal_timeout")(row, config, path)
        agent = {
            **result["agent"],
            "session_id": "local-session",
            "integrity_errors": ["missing_or_failed_terminal_result"],
        }
        result = {**result, "agent": agent}
        (path / "leg-0/result.json").write_text(json.dumps(agent))
        (path / "leg-0/process.json").write_text(
            json.dumps({"status": "timeout", "returncode": None})
        )
        (path / "component-result.json").write_text(json.dumps(result))
        return result

    result = execute(out, m, session_runner=realistic, identity_check=lambda: None)
    assert result["halted"] and len(calls) == 1
    reconcile_timeout(
        out, m, m["schedule"][0]["row_id"], reviewer="reviewer", reason="verified timeout"
    )


def guidance_manifest(tmp_path):
    m = manifest(tmp_path)
    explicit = tmp_path / "inputs" / "capture-explicit"
    explicit.write_text("Explicit capture instructions")
    explicit_artifact = {
        "path": explicit.name,
        "sha256": hashlib.sha256(explicit.read_bytes()).hexdigest(),
    }
    capture = []
    for row in m["schedule"][:4]:
        guidance = "current" if row["condition"] == "current" else "explicit"
        capture.append(
            {
                **row,
                "condition": "current",
                "guidance": guidance,
                "prompt": row["prompt"] if guidance == "current" else explicit_artifact,
            }
        )
    retrieval = []
    for intervention in ["optional", "explicit"]:
        original = next(row for row in m["schedule"] if row["row_id"] == intervention)
        for guidance in ["current", "procedural"]:
            retrieval.append(
                {**original, "row_id": f"{intervention}-{guidance}", "guidance": guidance}
            )
    return {**m, "schema": "bd-guidance-experiment.v1", "schedule": capture + retrieval}


def test_guidance_schema_exact_eight_without_repurchase(tmp_path):
    m = guidance_manifest(tmp_path)
    out = tmp_path / "out"
    calls = []
    freeze(out, m)
    result = execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    assert result["new_sessions"] == 8 and len(set(calls)) == 8
    assert all(row["condition"] == "current" for row in m["schedule"])
    assert sum(row["initial_store"] == "seeded" for row in m["schedule"]) == 6
    assert (
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)[
            "new_sessions"
        ]
        == 0
    )


@pytest.mark.parametrize(
    "damage",
    [
        "adapter_condition",
        "capture_guidance",
        "retrieval_guidance",
        "capture_prompt",
        "missing_row",
        "duplicate",
        "empty_retrieval",
        "seed",
        "old_schema",
    ],
)
def test_guidance_schema_invalid_contrasts_refuse(tmp_path, damage):
    m = guidance_manifest(tmp_path)
    if damage == "adapter_condition":
        m["schedule"][0]["condition"] = "focused"
    elif damage == "capture_guidance":
        m["schedule"][0]["guidance"] = "procedural"
    elif damage == "retrieval_guidance":
        m["schedule"][4]["guidance"] = "explicit"
    elif damage == "capture_prompt":
        m["schedule"][2]["prompt"] = m["schedule"][1]["prompt"]
    elif damage == "missing_row":
        m["schedule"].pop()
    elif damage == "duplicate":
        m["schedule"][1] = copy.deepcopy(m["schedule"][0])
    elif damage == "empty_retrieval":
        m["schedule"][4] = {**m["schedule"][4], "initial_store": "empty", "seed": None}
    elif damage == "seed":
        m["schedule"][4]["seed"] = {
            "path": "source",
            "sha256": hashlib.sha256(b"source").hexdigest(),
        }
    else:
        m["schema"] = "bd-component-experiment.v1"
    with pytest.raises(ValueError):
        freeze(tmp_path / "out", m)


def test_old_schedule_cannot_use_new_schema(tmp_path):
    m = manifest(tmp_path)
    m["schema"] = "bd-guidance-experiment.v1"
    with pytest.raises(ValueError):
        freeze(tmp_path / "out", m)


def test_guidance_late_partial_blocks_all_calls(tmp_path):
    m = guidance_manifest(tmp_path)
    out = tmp_path / "out"
    freeze(out, m)
    calls = []
    late = out / "sessions" / m["schedule"][-1]["row_id"]
    late.mkdir(parents=True)
    (late / "started.json").write_text("{}")
    with pytest.raises(ValueError):
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    assert not calls


def test_guidance_timeout_reconciliation_preserves_slot(tmp_path):
    m = guidance_manifest(tmp_path)
    out = tmp_path / "out"
    freeze(out, m)
    calls = []
    assert execute(
        out, m, session_runner=fake_runner(calls, "terminal_timeout"), identity_check=lambda: None
    )["halted"]
    with pytest.raises(ValueError):
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    reconcile_timeout(out, m, m["schedule"][0]["row_id"], reviewer="reviewer", reason="audited")
    assert (
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)[
            "new_sessions"
        ]
        == 7
    )
    assert len(calls) == 8
