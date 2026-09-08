"""Real legacy-bd mechanical completion controls; no agents or model calls.

Every invocation uses deliberately synthetic tool attribution, a fresh scratch
store, and the same installed CLI/Stop implementation as the lifecycle driver.
Output directories are exclusive: an interrupted control is never overwritten.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from membench.runner import memory_lifecycle_gate
from membench.runner.memory_lifecycle_corpus import LifecycleTask, build_lifecycles
from membench.runner.memory_routes_grade import grade_artifact
from membench.runner.memory_routes_runtime import experiment_env, make_profile
from scripts import memory_lifecycle_experiment as driver
from scripts import memory_routes_experiment as base


def reserve_output(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)


def assert_observation(observation: dict[str, Any], *, blocked: bool, stop: bool = False) -> None:
    events = observation["gate_events"]
    if not events:
        raise RuntimeError("Missing actual gate evidence")
    if any(
        event.get("infrastructure_error") or "invalid_receipts" in event.get("reasons", [])
        for event in events
    ):
        raise RuntimeError("Completion-check infrastructure failure")
    assert len(events) == 1, "Expected exactly one actual completion check"
    assert events[0]["passed"] is not blocked, events
    assert observation["returncode"] == (0 if stop or not blocked else 2), observation
    if stop:
        response = json.loads(observation["stdout"])
        assert response.get("decision") == "block" if blocked else response == {}


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class MechanicalSession:
    def __init__(self, out: Path, scratch: Path, task: LifecycleTask, name: str) -> None:
        self.out = out / name
        self.out.mkdir()
        self.local = scratch / name
        self.local.mkdir()
        for child in ("work", "config", "tmp"):
            (self.local / child).mkdir()
        self.store = self.local / "store"
        self.env = experiment_env(self.local / "config", self.local / "tmp", self.local / "bin")
        self.env.update(
            MEMBENCH_BD_SESSION_ID=f"mechanical-no-model-{name}",
            MEMBENCH_BD_LEG_ID=f"mechanical-no-model-{name}",
        )
        print(f"INITIALIZE {name}: disposable store", flush=True)
        base.initialize_store(self.store, self.env, self.out / "initialization.json")
        created = json.loads(
            base.checked_bd(
                ["create", f"Mechanical control: {name}", "--json"], self.store, self.env
            )
        )
        self.task_id = created["id"]
        base.new_json(self.out / "task-created.json", created)
        base.prepare_instrumentation(self.local / "bin", self.store, name)
        hooks = driver.install_checks(self.local, self.store, self.task_id, stage=task.stages[0])
        base.new_json(self.out / "installed-hooks.json", hooks)
        self.profile = make_profile(
            self.local / "sandbox.sb", writable_roots=[self.local], readable_roots=[self.local]
        )
        self.observations: list[dict[str, Any]] = []
        self.commands = 0
        base.new_json(
            self.out / "runtime.json", {"scratch": str(self.local), "task_id": self.task_id}
        )

    def invoke(self, label: str, args: list[str], *, stop: bool = False) -> dict[str, Any]:
        before = len(_rows(self.local / "gate-events.jsonl"))
        self.commands += 1
        env = dict(self.env)
        env["MEMBENCH_BD_TOOL_USE_ID"] = f"mechanical-no-model-{self.commands:02d}-{label}"
        target = (
            [str(base.PYTHON), str(self.local / "bin/stop.py")]
            if stop
            else [str(self.local / "bin/bd"), *args]
        )
        argv = ["/usr/bin/sandbox-exec", "-f", str(self.profile), *target]
        started = time.monotonic()
        result = subprocess.run(
            argv,
            cwd=self.local / "work",
            env=env,
            input=(
                json.dumps({"hook_event_name": "Stop", "stop_hook_active": False}) if stop else None
            ),
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        observation = {
            "label": label,
            "attribution": "synthetic mechanical invocation; no model observation",
            "argv": argv,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "elapsed_s": time.monotonic() - started,
            "gate_events": _rows(self.local / "gate-events.jsonl")[before:],
        }
        base.new_json(self.out / f"{self.commands:02d}-{label}.json", observation)
        self.observations.append(observation)
        if "bd receipt instrumentation:" in result.stderr:
            raise RuntimeError("CLI receipt infrastructure failed")
        receipt_rows = _rows(self.local / "receipts.jsonl")
        memory_lifecycle_gate._finished(receipt_rows)
        print(f"CONTROL {self.out.name}/{label}: exit {result.returncode}", flush=True)
        return observation

    def command(self, label: str, args: list[str]) -> None:
        observation = self.invoke(label, args)
        if observation["returncode"]:
            raise RuntimeError(f"Mechanical setup command {label} failed: {observation['stderr']}")

    def completion(self, label: str, *, blocked: bool, stop: bool = False) -> dict[str, Any]:
        observation = self.invoke(label, ["close", self.task_id], stop=stop)
        assert_observation(observation, blocked=blocked, stop=stop)
        return observation

    def finish(self, expected: dict[str, Any]) -> dict[str, Any]:
        memory = base.memories(self.store, self.env)
        base.new_json(self.out / "memory.json", memory)
        assigned = json.loads(
            base.checked_bd(["show", self.task_id, "--json"], self.store, self.env)
        )
        base.new_json(self.out / "task-final.json", assigned)
        for name in ("receipts.jsonl", "gate-events.jsonl"):
            shutil.copyfile(self.local / name, self.out / name)
        shutil.copytree(self.local / "bin", self.out / "installed-bin")
        shutil.copyfile(self.local / "work/config.json", self.out / "config.json")
        verdict = grade_artifact(self.out / "config.json", expected)
        base.new_json(self.out / "artifact-grade.json", verdict)
        return {
            "task_closed": assigned[0]["status"] == "closed",
            "artifact": verdict,
            "controls": self.observations,
        }


def _body(config: dict[str, Any]) -> str:
    return (
        "Mechanical fixture only; no agent-authored capture.\n```json\n"
        + json.dumps(config)
        + "\n```"
    )


def run(out: Path) -> None:
    reserve_output(out)
    scratch = Path(tempfile.mkdtemp(prefix="mem-lifecycle-gate-smoke-", dir="/tmp")).resolve()
    task = next(task for task in build_lifecycles(20260907) if task.domain == "cache")
    sources = sorted(
        {
            Path(__file__).resolve(),
            Path(driver.__file__).resolve(),
            Path(base.__file__).resolve(),
            *sorted((base.REPO / "memory-bench/membench").rglob("*.py")),
        }
    )
    manifest = {
        "schema": "memory-lifecycle-gate-mechanical.v1",
        "interpretation": "Real bd and installed hooks, synthetic tool attribution; no model calls "
        "or model-observed delivery. This tests procedure enforcement, "
        "not agent adoption or meaning.",
        "scratch": str(scratch),
        "task": dataclasses.asdict(task),
        "bd_version": subprocess.check_output([str(base.BD), "--version"], text=True).strip(),
        "binary_sha256": {str(path): base.sha(path) for path in (base.BD, base.PYTHON)},
        "source_sha256": {str(path.relative_to(base.REPO)): base.sha(path) for path in sources},
        "controls": [
            "missing_capture",
            "malformed_body",
            "missing_readback",
            "exact_readback",
            "wrong_consistent",
            "stop_incomplete",
            "stop_unclosed",
            "stop_complete",
        ],
    }
    for name in manifest["source_sha256"]:
        target = out / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base.REPO / name, target)
    base.new_json(out / "manifest.json", manifest)
    try:
        correct = MechanicalSession(out, scratch, task, "correct-contract")
        base.new_json(correct.local / "work/config.json", task.initial_config)
        correct.completion("stop-incomplete", blocked=True, stop=True)
        missing = correct.completion("missing-capture", blocked=True)
        assert all(
            f"missing_write:{key}" in missing["gate_events"][0]["reasons"]
            for key in task.stages[0].required_write_keys
        )
        for index, key in enumerate(task.stages[0].required_write_keys):
            correct.command(f"malformed-write-{index}", ["remember", "not JSON", "--key", key])
            correct.command(f"malformed-readback-{index}", ["recall", key])
        malformed = correct.completion("malformed-body", blocked=True)
        assert all(
            f"saved_body_mismatch:{key}" in malformed["gate_events"][0]["reasons"]
            for key in task.stages[0].required_write_keys
        )
        for index, key in enumerate(task.stages[0].required_write_keys):
            correct.command(
                f"exact-write-{index}", ["remember", _body(task.initial_config), "--key", key]
            )
        unread = correct.completion("missing-readback", blocked=True)
        assert all(
            f"missing_readback:{key}" in unread["gate_events"][0]["reasons"]
            for key in task.stages[0].required_write_keys
        )
        for index, key in enumerate(task.stages[0].required_write_keys):
            correct.command(f"exact-readback-{index}", ["recall", key])
        unclosed = correct.completion("stop-unclosed", blocked=True, stop=True)
        assert unclosed["gate_events"][0]["reasons"] == ["assigned_task_not_closed"]
        correct.completion("exact-readback-close", blocked=False)
        correct.completion("stop-complete", blocked=False, stop=True)
        good = correct.finish(task.initial_config)
        assert good["task_closed"] and good["artifact"]["passed"]

        wrong = MechanicalSession(out, scratch, task, "wrong-consistent-contract")
        wrong_config = copy.deepcopy(task.initial_config)
        wrong_config["cache"]["ttl_seconds"] += 1
        base.new_json(wrong.local / "work/config.json", wrong_config)
        for index, key in enumerate(task.stages[0].required_write_keys):
            wrong.command(f"wrong-write-{index}", ["remember", _body(wrong_config), "--key", key])
            wrong.command(f"wrong-readback-{index}", ["recall", key])
        wrong.completion("wrong-consistent-close", blocked=False)
        wrong.completion("wrong-consistent-stop", blocked=False, stop=True)
        bad = wrong.finish(task.initial_config)
        assert bad["task_closed"] and not bad["artifact"]["passed"]
        base.new_json(
            out / "result.json",
            {
                "passed": True,
                "model_calls": 0,
                "correct_contract": good,
                "wrong_consistent": bad,
                "limitation": "Passing the procedural gate does not certify the approved values. "
                "Stop responses were invoked directly, "
                "not exercised through a Claude model session.",
            },
        )
        print("COMPLETE: all eight mechanical controls passed; model calls 0", flush=True)
    except Exception as exc:
        base.new_json(out / "halt.json", {"type": type(exc).__name__, "message": str(exc)})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.out.resolve())


if __name__ == "__main__":
    main()
