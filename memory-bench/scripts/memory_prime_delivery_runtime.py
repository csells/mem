"""Separate startup guidance from ordinary task text for a new delivery experiment."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
import urllib.request
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from membench.runner import memory_e2e_receipts as receipts
from membench.runner import memory_model_profiles as model_profiles
from membench.runner import memory_unprompted_hosts as hosts
from membench.runner.memory_e2e_audit import classify_operation
from membench.runner.memory_host_shell import shell_environment
from membench.runner.memory_routes_runtime import experiment_env, make_profile
from scripts import memory_e2e_experiment as e2e
from scripts import memory_routes_experiment as base
from scripts import memory_unprompted_smoke as smoke
from scripts.memory_unprompted_experiment import (
    BUDGET,
    CORPUS,
    TIMEOUT,
    PackageInstaller,
    catalog_evidence,
    corpus,
    grade,
    native_snapshot,
    prepare_catalog,
    session_path,
    setup,
    write,
)


def compose_prompt(arm: str, task_prompt: str, briefing_text: str) -> str:
    """Deliver common guidance as user-role startup context, never a changed task."""
    if arm == "startup-briefing":
        return "# Project startup briefing\n\n" + briefing_text + "\n# Task\n\n" + task_prompt
    if arm in {"thin-prime", "rich-prime"}:
        return task_prompt
    raise ValueError(f"Unknown prime delivery arm: {arm}")


def record_delivery(
    evidence: Path,
    arm: str,
    task_prompt: str,
    briefing_text: str,
    actual_prime: str,
    expected_prime: str,
) -> dict[str, Any]:
    """Record exact launch bytes without conflating thin prime with rich startup text."""
    launch_prompt = compose_prompt(arm, task_prompt, briefing_text)
    if actual_prime != expected_prime:
        raise ValueError("Actual prime output differs from the frozen delivery arm")
    files = {
        "prompt.txt": task_prompt,
        "task-prompt.txt": task_prompt,
        "launch-prompt.txt": launch_prompt,
        "startup-briefing.txt": briefing_text,
    }
    for name in [*files, "delivery.json"]:
        if (evidence / name).exists() or (evidence / name).is_symlink():
            raise FileExistsError(evidence / name)
    for name, body in files.items():
        with (evidence / name).open("x", encoding="utf-8", newline="") as target:
            target.write(body)
    delivery = {
        "schema": "memory-prime-delivery.v1",
        "arm": arm,
        "startup_briefing_injected": arm == "startup-briefing",
        "startup_instruction_role": "user-message section" if arm == "startup-briefing" else None,
        "task_prompt_sha256": hashlib.sha256(task_prompt.encode()).hexdigest(),
        "launch_prompt_sha256": hashlib.sha256(launch_prompt.encode()).hexdigest(),
        "briefing_sha256": hashlib.sha256(briefing_text.encode()).hexdigest(),
        "actual_prime_sha256": hashlib.sha256(actual_prime.encode()).hexdigest(),
        "expected_prime_sha256": hashlib.sha256(expected_prime.encode()).hexdigest(),
        "actual_prime_equals_briefing": actual_prime == briefing_text,
        "prime_observation": "lifecycle setup prime.json; harness invocation before agent launch",
        "task_specific_memory_cues_added": False,
    }
    write(evidence / "delivery.json", delivery)
    return delivery


# Copied orchestration only; dependencies stay in the reviewed existing modules.
# Intentional changes: default new package; capture/validate delivery evidence;
# refuse modified PRIME.md or an unmatched actual setup-prime receipt before
# launch; pass the composed prompt; append delivery metadata to launch/result.
ORIGINAL_RUNTIME_SHA256 = "dc0bb311b4f5d9ce9750999925e298ab6c103bc3a4b4ea30a456cff04e86a354"
ORIGINAL_RUN_SESSION_SHA256 = "6e7d6aa239e29d0a5d8b43e39e2f8fb971b6998e8c14ed94a6d1fffa139f9150"


def run_session(
    out: Path,
    row: dict[str, Any],
    endpoint: str | None,
    *,
    corpus_root: Path | None = None,
    package_installer: PackageInstaller | None = None,
    model_profile_id: str | None = None,
    catalog_mode: str | None = None,
) -> dict[str, Any]:
    evidence = session_path(out, row)
    if evidence.exists():
        if (evidence / "result.json").exists():
            print(f"PRESERVED {row['slot']}", flush=True)
            existing: dict[str, Any] = json.loads((evidence / "result.json").read_text())
            return existing
        raise RuntimeError(f"Claimed but unfinished slot cannot be rerun: {row['slot']}")
    from membench.runner import memory_prime_delivery_package as package

    selected_installer = package.install if package_installer is None else package_installer
    state = setup(out, row, corpus_root=corpus_root, package_installer=selected_installer)
    evidence.mkdir(exist_ok=False)
    scratch, workspace, store = (Path(state[k]) for k in ("scratch", "workspace", "store"))
    stage = row["stage"]
    local = scratch / f"stage-{stage}"
    local.mkdir()
    (local / "work").symlink_to(workspace, target_is_directory=True)
    for name in ("config", "tmp"):
        (local / name).mkdir()
    native = local / "native"
    if stage == 1:
        native.mkdir()
    else:
        previous = session_path(out, {**row, "stage": stage - 1})
        if not (previous / "result.json").exists():
            raise RuntimeError("Missing completed predecessor; no repair or replacement")
        shutil.copytree(scratch / f"stage-{stage-1}" / "native", native, symlinks=True)
    source_root = CORPUS if corpus_root is None else corpus_root
    family = row.get("corpus_family", row["family"])
    _, tasks = corpus(family, corpus_root=source_root)
    spec = tasks[stage - 1]
    public = spec.get("public_tests")
    if public:
        source = source_root / family / public
        target = workspace / public
        if target.exists() or target.is_symlink():
            raise FileExistsError("Stage public examples already exist; preserve and inspect")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    task = e2e.create_task(state, spec["title"], spec["body"])
    write(evidence / "task.json", task)
    write(evidence / "tasks-before.json", e2e.all_tasks(store, state["env"]))
    e2e.snapshot(workspace, evidence / "workspace-before")
    before = base.memories(store, state["env"])
    write(evidence / "memory-before.json", before)
    invocation = uuid.uuid4().hex
    log, _ = receipts.prepare(
        local / "bin", store, str(stage), invocation, binary=base.BD, python=base.PYTHON
    )
    env = shell_environment(local, experiment_env(local / "config", local / "tmp", local / "bin"))
    selected_catalog_mode = catalog_mode or row.get("catalog_mode", "none")
    catalog = prepare_catalog(local, before, selected_catalog_mode, env)
    if catalog is not None:
        write(evidence / "memory-catalog-before.json", catalog)
    if endpoint:
        env["MEMBENCH_OLLAMA_BASE_URL"] = endpoint
    prompt = f"Work on {task['id']}."
    expected_prime = package.briefing() if row["arm"] == "rich-prime" else package.thin_prime()
    for installed_prime in (workspace / ".beads/PRIME.md", store / ".beads/PRIME.md"):
        if installed_prime.read_text() != expected_prime:
            raise ValueError("Installed prime changed from the frozen delivery arm")
    prime_receipt = json.loads((evidence.parent / "prime.json").read_text())
    if prime_receipt.get("actor") != "harness" or not isinstance(prime_receipt.get("stdout"), str):
        raise ValueError("Missing actual lifecycle prime output")
    delivery = record_delivery(
        evidence, row["arm"], prompt, package.briefing(), prime_receipt["stdout"], expected_prime
    )
    launch_prompt = compose_prompt(row["arm"], prompt, package.briefing())
    profile_id = model_profile_id or row.get("profile_id")
    if profile_id is not None:
        selected_model = model_profiles.get_profile(profile_id)
        if selected_model.host != row["host"]:
            raise ValueError("Model profile host does not match scheduled host")
        requested_model = selected_model.model
        launch = model_profiles.prepare(profile_id, local, env, launch_prompt, row["mode"], BUDGET)
    else:
        requested_model = hosts.MODELS[row["host"]]
        launch = hosts.prepare(
            row["host"], local, env, launch_prompt, requested_model, row["mode"], BUDGET
        )
    profile = make_profile(
        local / "sandbox.sb",
        [local, workspace, store],
        [local, workspace, store, *launch.readable_roots],
    )
    argv = ["/usr/bin/sandbox-exec", "-f", str(profile), *launch.argv]
    write(
        evidence / "launch.json",
        {
            "argv": argv,
            "settings": {
                **launch.public_settings,
                "delivery_arm": row["arm"],
                "startup_briefing_injected": delivery["startup_briefing_injected"],
                "launch_prompt_sha256": delivery["launch_prompt_sha256"],
                "catalog_mode": selected_catalog_mode,
                "catalog_contents": (
                    "actual before-snapshot keys only" if catalog is not None else None
                ),
            },
            "harness_session": invocation,
        },
    )
    start = time.monotonic()
    print(f"START {row['slot']} deadline={TIMEOUT}s", flush=True)
    timed_out = False
    with (
        (local / "stdout-private.jsonl").open("x") as stdout,
        (local / "stderr-private.txt").open("x") as stderr,
    ):
        proc = subprocess.Popen(
            argv,
            cwd=workspace,
            env=launch.env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        write(evidence / "process.json", {"pid": proc.pid, "started_ns": time.time_ns()})
        process_deadline = time.monotonic() + TIMEOUT
        while True:
            try:
                code = proc.wait(timeout=min(30, max(0.01, process_deadline - time.monotonic())))
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= process_deadline:
                    timed_out = True
                    os.killpg(proc.pid, signal.SIGKILL)
                    code = proc.wait()
                    break
                print(
                    f"HEARTBEAT {row['slot']} elapsed={time.monotonic()-start:.1f}s "
                    f"pid={proc.pid} stdout_bytes={(local/'stdout-private.jsonl').stat().st_size}",
                    flush=True,
                )
    secrets = smoke.secret_values(launch.env, local)
    stream, leaked = smoke.sanitize((local / "stdout-private.jsonl").read_text(), secrets)
    stderr_text, stderr_leaked = smoke.sanitize((local / "stderr-private.txt").read_text(), secrets)
    (evidence / "stream.jsonl").write_text(stream)
    (evidence / "stderr.txt").write_text(stderr_text)
    observed = (
        model_profiles.observe(profile_id, stream, local)
        if profile_id is not None
        else hosts.observe(row["host"], stream, local)
    )
    rows_text, receipt_leaked = smoke.sanitize(json.dumps(receipts.read(log)), secrets)
    rows = json.loads(rows_text)
    write(evidence / "raw-receipts.json", rows)
    write(evidence / "tool-calls.json", [c.model_dump(mode="json") for c in observed.calls])
    ops = receipts.assess(
        rows,
        root_pid=proc.pid,
        leg=str(stage),
        session=invocation,
        tool_outputs=[str(c.result or "") for c in observed.calls],
        binary=str(base.BD),
        store=str(store),
    )
    after = base.memories(store, state["env"])
    write(evidence / "memory-after.json", after)
    actual_tasks = e2e.all_tasks(store, state["env"])
    write(evidence / "tasks-after.json", actual_tasks)
    e2e.snapshot(workspace, evidence / "workspace-after")
    native_snapshot(native, evidence / "native-after")
    if profile_id is not None:
        model_profiles.export_evidence(profile_id, local, evidence / "host-evidence")
    else:
        hosts.export_evidence(row["host"], local, evidence / "host-evidence")
    if catalog is not None:
        write(
            evidence / "memory-catalog-after.json",
            catalog_evidence(local / "memory-catalog.json"),
        )
    artifact = grade(workspace, local, row, corpus_root=source_root)
    write(evidence / "artifact-grade.json", artifact)
    actions = [
        classify_operation(
            e["operation_argv"], e["returncode"], e["stdout"], e["stderr"], before, after
        )
        for e in ops["executions"]
    ]
    package_changes = [
        p
        for p, digest in state["package"]["files"].items()
        if not Path(p).is_file() or base.sha(Path(p)) != digest
    ]
    result = {
        **row,
        "task_id": task["id"],
        "delivery": delivery,
        "model_requested": requested_model,
        "models_observed": observed.models,
        "session_id": observed.session_id,
        "exit_code": code,
        "timed_out": timed_out,
        "host_completed": observed.completed,
        "host_success": observed.success,
        "errors": observed.errors,
        "duration_s": time.monotonic() - start,
        "cost_usd": observed.cost_usd,
        "usage": observed.usage,
        "artifact_passed": artifact["passed"],
        "artifact_correct": artifact["correct"],
        "artifact_total": artifact["total"],
        "memory_before_count": len(before),
        "memory_after_count": len(after),
        "record_unchanged": before == after,
        "actions": actions,
        "action_counts": dict(Counter(a["action"] for a in actions)),
        "receipt_assessment": ops,
        "credential_redaction_required": leaked or stderr_leaked or receipt_leaked,
        "task_closed": any(
            t.get("id") == task["id"] and t.get("status") == "closed" for t in actual_tasks
        ),
        "package_changed_paths": package_changes,
        "administrative_memory_reads": 2,
        **e2e.instruction_reads([c.model_dump(mode="json") for c in observed.calls], workspace),
    }
    if endpoint:
        with urllib.request.urlopen(
            endpoint.removesuffix("/v1") + "/api/ps", timeout=5
        ) as response:
            context = json.load(response)
        write(evidence / "ollama-context.json", context)
        result["runtime_context_qualified"] = bool(
            context.get("models")
            and all(m.get("context_length", 0) >= 32768 for m in context["models"])
        )
    result["infrastructure_fault"] = bool(
        leaked
        or stderr_leaked
        or receipt_leaked
        or ops["unknown_execution"]
        or observed.models != [requested_model]
        or not observed.session_id
        or result.get("runtime_context_qualified") is False
    )
    write(evidence / "result.json", result)
    print(
        f"DONE {row['slot']} artifact={artifact['correct']}/{artifact['total']} "
        f"actions={result['action_counts']} exit={code}",
        flush=True,
    )
    return result
