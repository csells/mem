"""One preserved real host/shim smoke, distinct from scored lifecycle trials."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from membench.runner.memory_routes_runtime import experiment_env
from scripts import memory_hosts_experiment as driver
from scripts import memory_routes_experiment as base


def run(out: Path, host: str, model: str, mode: str = "isolated") -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=False)
    sources = [
        Path(__file__),
        Path(driver.__file__),
        *sorted((base.REPO / "memory-bench/membench/runner").glob("memory_host*.py")),
    ]
    base.new_json(
        out / "source-sha256.json", {str(p.relative_to(base.REPO)): base.sha(p) for p in sources}
    )
    for path in sources:
        target = out / "source" / path.relative_to(base.REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    case = Path(tempfile.mkdtemp(prefix="mem-host-common-smoke-", dir="/tmp")).resolve()
    setup = case / "setup"
    for name in ("config", "tmp", "bin"):
        (setup / name).mkdir(parents=True)
    env = experiment_env(setup / "config", setup / "tmp", setup / "bin")
    store = case / "store"
    base.initialize_store(store, env, out / "initialization.json")
    result, _ = driver.run_leg(
        case=case,
        evidence=out / "session",
        leg="adapter-smoke",
        host=host,
        model=model,
        mode=mode,
        prompt=(
            "Adapter verification only. Execute these commands using their exact syntax: "
            "bd remember '{\"smoke\": true}' --key smoke.memory --json; "
            "bd memories 'smoke' --json; bd recall smoke.memory --json. "
            "Then write config.json in the current working directory with exactly "
            '{"smoke": true}. Complete the assigned task.'
        ),
        store=store,
        native_from=None,
        expected={"smoke": True},
        budget=0.75,
        timeout_s=240,
        workflow="This is a bounded CLI adapter check; inspect actual tool results.",
    )
    assigned = json.loads(base.checked_bd(["show", result["task_id"], "--json"], store, env))
    base.new_json(out / "task.json", assigned)
    closed = (
        isinstance(assigned, list) and len(assigned) == 1 and assigned[0].get("status") == "closed"
    )
    proof = {
        "host": host,
        "model": model,
        "mode": mode,
        "adapter_verified": bool(
            result["completed"]
            and result["exit_code"] == 0
            and not result["is_error"]
            and not result["timed_out"]
            and result["artifact"]["passed"]
            and closed
            and result["model_matches"]
            and not result["memory_evidence"]["evidence_unknown"]
            and result["memory_evidence"]["accepted_writes"] == 1
            and result["memory_evidence"]["observed_reads"] == 2
            and result["bd_correct_payload_via_direct"]
            and result["bd_search"]
        ),
        "artifact_passed": result["artifact"]["passed"],
        "result": result,
    }
    base.new_json(out / "result.json", proof)
    print(
        json.dumps(
            {key: proof[key] for key in ("host", "model", "adapter_verified", "artifact_passed")}
        ),
        flush=True,
    )
    return proof


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--host", required=True, choices=driver.HOSTS)
    parser.add_argument("--model", required=True)
    parser.add_argument("--mode", default="isolated", choices=driver.MODES)
    args = parser.parse_args()
    proof = run(args.out.resolve(), args.host, args.model, args.mode)
    if not proof["adapter_verified"]:
        raise SystemExit("Adapter smoke unverified; inspect preserved result, do not overwrite")


if __name__ == "__main__":
    main()
