"""Test captured cache prose with an explicit current output schema.

Run ``python -m scripts.memory_routes_schema_control --out PATH`` to freeze a
two-session plan. Add --fire after review. Only the original task's output shape
is added; the captured values and all five decoys remain exactly as recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

from membench.runner.memory_routes_corpus import build_tasks
from membench.runner.memory_routes_grade import grade_capture
from membench.runner.memory_routes_runtime import experiment_env
from scripts import memory_routes_experiment as driver

SEED = 20260906
ROUTES = ("direct", "search")
DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "results/memory-routes/2026-09-06-main-02"
OUTPUT_SHAPE = """
OUTPUT SHAPE (field names, JSON types, and nesting only):
The root object has exactly two fields: project (string) and cache (object).
The cache object has exactly these fields:
- ttl_seconds (integer)
- max_entries (integer)
- eviction_policy (string)
- namespace (string)
- cache_misses (boolean)
Recover the field values from the earlier agreement. This section supplies no
configuration values; it specifies the output schema for the current task.
"""


def read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Required regular evidence file is unavailable: {path}")
    return json.loads(path.read_text())


def make_plan(source: Path, budget: float) -> tuple[dict[str, Any], dict[str, str], bytes]:
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("Session budget must be finite and positive")
    task = next(task for task in build_tasks(SEED) if task.domain == "cache")
    relative = Path("cases") / f"{task.id}-examples"
    names = [Path("manifest.json"), relative / "result.json", relative / "establish/memory.json"]
    manifest, completed, captured = [read_json(source / name) for name in names]
    matching = [
        item
        for item in manifest.get("tasks", [])
        if isinstance(item, dict) and item.get("id") == task.id
    ]
    if (
        manifest.get("schema") != "memory-routes-macos.v1"
        or manifest.get("seed") != SEED
        or len(matching) != 1
        or matching[0].get("expected_config") != task.expected_config
        or matching[0].get("goal_prompt_direct") != task.goal_prompt_direct
        or matching[0].get("goal_prompt_search") != task.goal_prompt_search
    ):
        raise ValueError("Source manifest does not match the original cache task")
    if (
        completed.get("task") != task.id
        or completed.get("policy") != "examples"
        or not isinstance(completed.get("legs"), dict)
        or set(completed["legs"]) != {"establish", "direct", "search", "unnecessary"}
        or completed.get("capture", {}).get("passed", "absent") is not None
    ):
        raise ValueError("Source examples case must be complete with a literal-capture unknown")
    for leg, result in completed["legs"].items():
        name = relative / leg / "result.json"
        if read_json(source / name) != result:
            raise ValueError("Source case and session results differ")
        names.append(name)
    if (
        not isinstance(captured, dict)
        or any(not isinstance(k, str) or not isinstance(v, str) for k, v in captured.items())
        or not captured.get(task.key)
        or not set(task.decoys).issubset(captured)
    ):
        raise ValueError("Source must retain the canonical memory and five decoys")
    if grade_capture(captured, task.key, task.expected_config)["passed"] is not None:
        raise ValueError("This control requires the original unsupported prose representation")
    snapshot = (source / names[2]).read_bytes()
    sources = [
        Path(__file__).resolve(),
        Path(driver.__file__).resolve(),
        *sorted((driver.REPO / "memory-bench/membench").rglob("*.py")),
    ]
    plan = {
        "schema": "memory-routes-schema-control.v1",
        "source_run": str(source.resolve()),
        "source_evidence_sha256": {str(n): driver.sha(source / n) for n in names},
        "source_memory_sha256": hashlib.sha256(snapshot).hexdigest(),
        "canonical_key": task.key,
        "canonical_body_sha256": hashlib.sha256(captured[task.key].encode()).hexdigest(),
        "source_sha256": {str(p.relative_to(driver.REPO)): driver.sha(p) for p in sources},
        "binary_sha256": {str(p): driver.sha(p) for p in (driver.BD, driver.CLAUDE, driver.PYTHON)},
        "model": driver.MODEL,
        "policy": "examples",
        "policy_prompt": driver.BASE + driver.EXAMPLES,
        "expected_config": task.expected_config,
        "output_shape": OUTPUT_SHAPE,
        "prompts": {
            route: getattr(task, f"goal_prompt_{route}") + "\n" + OUTPUT_SHAPE for route in ROUTES
        },
        "schedule": list(ROUTES),
        "planned_sessions": 2,
        "session_budget_usd": budget,
        "interpretation": (
            "Targeted output-schema intervention on one existing examples capture. Original "
            "prose and decoys are transferred without repair. It tests whether the original "
            "values remain usable when output nesting/types are supplied, not fresh capture "
            "or the general necessity of JSON memory. Literal payload grading remains unknown "
            "for this prose; exact original-body exposure and final artifact success are "
            "reported separately. Surrounding prose is not semantically certified."
        ),
    }
    return plan, captured, snapshot


def run_route(out: Path, route: str, plan: dict[str, Any], captured: dict[str, str]) -> None:
    directory = out / "cases" / route
    directory.mkdir(parents=True)
    scratch = Path(tempfile.mkdtemp(prefix="mem-shape-", dir="/tmp")).resolve()
    driver.new_json(directory / "started.json", {"route": route, "scratch": str(scratch)})
    try:
        setup = scratch / "setup"
        setup.mkdir()
        for name in ("config", "tmp", "bin"):
            (setup / name).mkdir()
        env = experiment_env(setup / "config", setup / "tmp", setup / "bin")
        store = scratch / "store"
        driver.initialize_store(store, env, directory / "initialization.json")
        for key, body in captured.items():
            driver.checked_bd(["remember", body, "--key", key], store, env)
        transferred = driver.memories(store, env)
        if transferred != captured:
            raise RuntimeError("Transferred memory differs from the original captured bytes")
        driver.new_json(directory / "transferred-memory.json", transferred)
        session = directory / "session"
        result, _ = driver.run_leg(
            case=scratch,
            evidence=session,
            leg=route,
            policy="examples",
            prompt=plan["prompts"][route],
            store=store,
            native_from=None,
            expected=plan["expected_config"],
            budget=plan["session_budget_usd"],
        )
        body = captured[plan["canonical_key"]]
        observed = any(
            op["is_read"]
            and op["output_observed"]
            and op["returncode"] == 0
            and body in op["content"]
            for op in result["memory_evidence"]["operations"]
        )
        driver.new_json(
            directory / "result.json",
            {
                "route": route,
                "artifact": result["artifact"],
                "original_prose_body_observed": observed,
                "session_result_sha256": driver.sha(session / "result.json"),
                "session_result": result,
            },
        )
        print(
            f"SCHEMA {route}: artifact={result['artifact']['passed']} prose={observed}", flush=True
        )
    except Exception as exc:
        driver.new_json(directory / "halt.json", {"type": type(exc).__name__, "message": str(exc)})
        raise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--session-budget", type=float, default=0.75)
    parser.add_argument("--fire", action="store_true")
    args = parser.parse_args(argv)
    plan, captured, original_bytes = make_plan(args.source_run, args.session_budget)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = args.out / "manifest.json"
    snapshot = args.out / "source-memory.json"
    if manifest.exists():
        if read_json(manifest) != plan or snapshot.read_bytes() != original_bytes:
            raise ValueError("Frozen schema plan or source snapshot differs; use a new output")
    else:
        if any(args.out.iterdir()):
            raise ValueError("Nonempty schema-control output has no manifest")
        driver.new_json(manifest, plan)
        with snapshot.open("xb") as target:
            target.write(original_bytes)
    print(f"PLAN 2 schema-control sessions at {args.out}", flush=True)
    if not args.fire:
        return
    pending = []
    for route in ROUTES:
        directory = args.out / "cases" / route
        if not directory.exists():
            pending.append(route)
            continue
        if not (directory / "result.json").exists():
            raise ValueError(f"Interrupted control cannot be repurchased: {directory}")
        result = read_json(directory / "result.json")
        if (
            result.get("route") != route
            or result.get("session_result_sha256") != driver.sha(directory / "session/result.json")
            or result.get("session_result") != read_json(directory / "session/result.json")
        ):
            raise ValueError(f"Completed control evidence differs: {directory}")
    for route in pending:
        run_route(args.out, route, plan, captured)


if __name__ == "__main__":
    main()
