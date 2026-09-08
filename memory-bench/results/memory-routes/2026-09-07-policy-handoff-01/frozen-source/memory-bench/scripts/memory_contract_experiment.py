"""Matched installed-workflow lifecycles with one public contract-check intervention.

Only --fire launches models. Both conditions reuse the prior E2E session runtime
without modifying its sources, prompts, instruction package, or native settings.
The checker is installed once and actual edits/removal survive. Independent checks
run afterward with canonical public assertions and hidden artifact grading, with
no model feedback. Started attempts and earlier evidence are never repurchased.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from membench.runner.memory_contract_check import PUBLIC_TEST_PATH, PUBLIC_TEST_SOURCE
from membench.runner.memory_e2e_corpus import build_e2e_case, find_successor_task, stage_task
from membench.runner.memory_e2e_grade import grade_retained
from membench.runner.memory_routes_runtime import make_profile
from scripts import memory_e2e_experiment as e2e
from scripts import memory_routes_experiment as base

CONDITIONS = ("baseline", "checker")


def checker_digest() -> str:
    return hashlib.sha256(PUBLIC_TEST_SOURCE.encode()).hexdigest()


def source_hashes() -> dict[str, str]:
    """Pin reused runtime plus new checker, driver, and their verification tests."""
    hashes = e2e.sources()
    for relative in (
        "memory-bench/tests/test_memory_contract_check.py",
        "memory-bench/tests/test_memory_contract_experiment.py",
    ):
        path = base.REPO / relative
        if path.is_file():
            hashes[relative] = base.sha(path)
    return dict(sorted(hashes.items()))


def checker_state(workspace: Path) -> dict[str, Any]:
    path = workspace / PUBLIC_TEST_PATH
    symlink = path.is_symlink()
    try:
        within_workspace = path.resolve().is_relative_to(workspace.resolve())
    except (OSError, RuntimeError):
        within_workspace = False
    regular = within_workspace and path.is_file() and not symlink
    digest = base.sha(path) if regular else None
    return {
        "path": PUBLIC_TEST_PATH,
        "exists": path.exists() or symlink,
        "regular_file": regular,
        "resolved_within_workspace": within_workspace,
        "symlink": os.readlink(path) if symlink else None,
        "sha256": digest,
        "canonical": digest == checker_digest(),
    }


def install_checker(workspace: Path, condition: str) -> None:
    """Add only the treatment file; never replace an existing destination."""
    if condition not in CONDITIONS:
        raise ValueError("Unknown public-check condition")
    if condition == "baseline":
        return
    relative = Path(PUBLIC_TEST_PATH)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Checker path must be project relative")
    path = workspace / relative
    for parent in (path.parent, *path.parents):
        if parent.is_symlink():
            raise ValueError("Checker destination has a symlink ancestor")
        if parent == workspace:
            break
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as target:
        target.write(PUBLIC_TEST_SOURCE)


def _offline_proof(path: Path) -> dict[str, Any]:
    proof = json.loads(path.read_text())
    if (
        proof.get("schema") != "memory-contract-check-static.v1"
        or proof.get("public_test_sha256") != checker_digest()
        or proof.get("target_passed") != 19
        or proof.get("target_rejected") != 13
        or proof.get("all_target_results_match_prior_shape_verdict") is not True
        or len(proof.get("rows", [])) != 32
        or not all(row.get("input_files_preserved") is True for row in proof["rows"])
    ):
        raise ValueError("Public checker lacks matching complete offline qualification")
    for name, digest in proof["source_sha256"].items():
        if base.sha(base.REPO / name) != digest:
            raise ValueError(f"Public checker qualification source changed: {name}")
    return {"path": str(path.resolve()), "sha256": base.sha(path), "proof": proof}


def freeze(out: Path, smokes: dict[str, Path], checker_checks: Path) -> dict[str, Any]:
    """Reuse qualified host smokes only when every preexisting pinned input agrees."""
    if out.exists():
        raise FileExistsError("Cohort evidence already exists")
    source = source_hashes()
    binaries = e2e.binary_hashes()
    checker_proof = _offline_proof(checker_checks)
    smoke_reuse = {}
    common_prior: set[str] | None = None
    for host in e2e.MODELS:
        path = smokes[host].resolve()
        proof = json.loads((path / "result.json").read_text())
        prior = json.loads((path / "source-sha256.json").read_text())
        prior_binaries = json.loads((path / "binary-sha256.json").read_text())
        if proof.get("admitted") is not True or proof.get("host") != host:
            raise ValueError(f"{host} smoke was not admitted for this host")
        if not prior or any(source.get(name) != digest for name, digest in prior.items()):
            raise ValueError(f"{host} smoke source/package changed or was removed")
        if prior_binaries != binaries:
            raise ValueError(f"{host} smoke executable differs from current inputs")
        if common_prior is not None and set(prior) != common_prior:
            raise ValueError("Host smoke source scopes differ")
        common_prior = set(prior)
        smoke_reuse[host] = {
            "path": str(path),
            "input_hashes_unchanged": True,
            "source_count": len(prior),
            "proof_sha256": base.sha(path / "result.json"),
            "source_manifest_sha256": base.sha(path / "source-sha256.json"),
            "binary_manifest_sha256": base.sha(path / "binary-sha256.json"),
            "model": e2e.MODELS[host],
        }
    coverage: dict[str, Any] = {
        host: {"admitted": True, "model": model, "smoke": smoke_reuse[host]["path"]}
        for host, model in e2e.MODELS.items()
    }
    coverage.update(
        {
            "gemini": {
                "admitted": False,
                "blocker": "previous depleted credits; no qualified adapter",
            },
            "copilot": {
                "admitted": False,
                "blocker": "previous launcher without CLI; no qualified adapter",
            },
            "opencode": {
                "admitted": False,
                "blocker": "previous context truncation; no qualified adapter",
            },
        }
    )
    case = build_e2e_case()
    manifest = {
        "schema": "memory-contract-screen.v1",
        "planned_sessions": 32,
        "cases": [
            {"host": host, "condition": condition, "arm": "installed", "id": f"{host}-{condition}"}
            for host, conditions in (("claude", CONDITIONS), ("codex", tuple(reversed(CONDITIONS))))
            for condition in conditions
        ],
        "stages": [stage.name for stage in case.stages],
        "case": json.loads(json.dumps(dataclasses.asdict(case))),
        "models": dict(e2e.MODELS),
        "source_sha256": source,
        "binary_sha256": binaries,
        "source_additions_since_smoke": sorted(set(source) - (common_prior or set())),
        "smoke_reuse": smoke_reuse,
        "coverage": coverage,
        "checker": {
            "path": PUBLIC_TEST_PATH,
            "source_sha256": checker_digest(),
            "qualification": checker_proof,
            "intervention": "Only checker condition initially receives the public unittest file",
            "retention": (
                "Retain agent edits/removal/additions; never repair or halt for checker changes"
            ),
        },
        "runtime": "Unmodified scripts.memory_e2e_experiment.run_session, installed arm",
        "native_mode": "normal in fresh isolated state, actual native records carried forward",
        "timeout_s": e2e.TIMEOUT,
        "requested_budget_usd_per_session": e2e.BUDGET,
        "budget_limit": "Claude CLI USD cap; Codex wall time only, USD cost unreported",
        "prompts": (
            "Identical harness-authored stage issue bodies; actual agent-authored "
            "follow-ups may differ. Initial request Work on <actual-task-id>."
        ),
        "interruption_policy": "Never rerun a started lifecycle; resume only untouched cases",
        "grading": "Canonical public assertion plus unchanged hidden artifact oracle; no feedback",
    }
    out.mkdir(parents=True, exist_ok=False)
    e2e.write_json(out / "manifest.json", manifest)
    for name in source:
        target = out / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base.REPO / name, target)
    return manifest


def assert_frozen(manifest: dict[str, Any]) -> None:
    e2e.assert_frozen(manifest)
    if (
        manifest.get("schema") != "memory-contract-screen.v1"
        or manifest["models"] != e2e.MODELS
        or manifest["timeout_s"] != e2e.TIMEOUT
        or manifest["requested_budget_usd_per_session"] != e2e.BUDGET
        or manifest["checker"]["source_sha256"] != checker_digest()
        or manifest["case"] != json.loads(json.dumps(dataclasses.asdict(build_e2e_case())))
    ):
        raise ValueError("Frozen experiment configuration differs from runtime")
    proof = manifest["checker"]["qualification"]
    if base.sha(Path(proof["path"])) != proof["sha256"]:
        raise ValueError("Frozen checker qualification changed")


_CHECK_PROBE = r"""
import io
import json
import pathlib
import sys
import unittest

workspace = pathlib.Path(sys.argv[1])
namespace = {"__name__": "canonical_contract_check", "__file__": str(workspace / sys.argv[2])}
exec(compile(sys.argv[3], "canonical-public-contract", "exec"), namespace)
kind = namespace["ComponentContractTest"]
suite = unittest.defaultTestLoader.loadTestsFromTestCase(kind)
output = io.StringIO()
result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
component = {"passed": True}
try:
    kind("test_public_contract").check_component(workspace / sys.argv[4])
except Exception as exc:
    component = {"passed": False, "error_type": type(exc).__name__, "error": str(exc)}
print(json.dumps({"whole_workspace": {"passed": result.wasSuccessful(),
                  "tests_run": result.testsRun, "output": output.getvalue()},
                  "component": component}))
"""


def audit_checker(
    workspace: Path,
    component: str,
    *,
    process_prefix: Sequence[str],
    python_executable: str,
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    """Execute canonical public assertions; callers sandbox generated-code imports."""
    argv = [
        *process_prefix,
        python_executable,
        "-I",
        "-B",
        "-c",
        _CHECK_PROBE,
        str(workspace.resolve()),
        PUBLIC_TEST_PATH,
        PUBLIC_TEST_SOURCE,
        component,
    ]
    try:
        result = subprocess.run(
            argv,
            cwd=workspace,
            env={"PATH": ""},
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {"completed": False, "reason": "canonical_checker_timeout"}
    evidence: dict[str, Any] = {
        "canonical_source_sha256": checker_digest(),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "model_feedback": False,
    }
    if result.returncode:
        return {"completed": False, "reason": "canonical_checker_process_failed", **evidence}
    try:
        observation = json.loads(result.stdout.splitlines()[-1])
    except (ValueError, IndexError):
        return {"completed": False, "reason": "canonical_checker_output_invalid", **evidence}
    return {"completed": True, **observation, **evidence}


def assess_checker(workspace: Path, component: str, scratch: Path) -> dict[str, Any]:
    profile = make_profile(
        scratch / "contract-check.sb", [], [workspace, Path(sys.base_prefix).resolve()]
    )
    return audit_checker(
        workspace,
        component,
        process_prefix=["/usr/bin/sandbox-exec", "-f", str(profile)],
        python_executable=sys.executable,
    )


def run_lifecycle(out: Path, row: dict[str, str], manifest: dict[str, Any]) -> None:
    case = build_e2e_case()
    directory = out / "cases" / row["id"]
    if directory.exists():
        raise FileExistsError(f"Lifecycle has prior evidence; do not repurchase: {directory}")
    if row.get("arm") != "installed" or row.get("condition") not in CONDITIONS:
        raise ValueError("All contract conditions require the installed workflow")
    if not manifest["coverage"][row["host"]]["admitted"]:
        directory.mkdir(parents=True)
        e2e.write_json(
            directory / "result.json",
            {
                **row,
                "status": "blocked",
                "stages": [
                    {"leg": stage.name, "status": "unrun", "reason": "host not admitted"}
                    for stage in case.stages
                ],
            },
        )
        return
    assert_frozen(manifest)
    state = e2e.setup_case(directory, "installed", case)
    install_checker(Path(state["workspace"]), row["condition"])
    e2e.write_json(
        directory / "condition.json",
        {
            "condition": row["condition"],
            "execution_arm": "installed",
            "initial_checker": checker_state(Path(state["workspace"])),
        },
    )
    native = None
    stages: list[dict[str, Any]] = []
    standing_keys: list[str] | None = None
    history_keys: list[str] | None = None
    initial_memory: dict[str, str] | None = None
    halt: str | None = None
    for stage in case.stages:
        if halt:
            stages.append({"leg": stage.name, "status": "unrun", "reason": halt})
            continue
        assert_frozen(manifest)
        if not e2e.package_unchanged(state):
            halt = "agent changed installed instruction package; retained without repair"
            stages.append({"leg": stage.name, "status": "unrun", "reason": halt})
            continue
        description = stage_task(case, stage)
        if stage.authored_task:
            selected = find_successor_task(
                e2e.all_tasks(Path(state["store"]), state["env"]), description["title"]
            )
            if selected["status"] != "selected":
                stages.append(
                    {
                        "leg": stage.name,
                        "status": "unrun",
                        "reason": "author handoff " + selected["status"],
                        "selection": selected,
                    }
                )
                continue
            task = selected["task"]
        else:
            task = e2e.create_task(state, description["title"], description["body"])
        checker_before = checker_state(Path(state["workspace"]))
        try:
            print(f"CONDITION {row['host']}/{row['condition']}/{stage.name}", flush=True)
            result, native = e2e.run_session(
                directory / stage.name, state, row["host"], task, stage.name, native
            )
            evidence = directory / stage.name
            before = json.loads((evidence / "memory-before.json").read_text())
            after = json.loads((evidence / "memory-after.json").read_text())
            retained = grade_retained(
                before, after, case, stage, standing_keys=standing_keys, history_keys=history_keys
            )
            if stage.name == "establish":
                initial_memory = after
            if stage.name == "revise":
                standing_keys = retained["v2_exact_keys"] or None
                history_keys = retained["v1_exact_keys"] or None
                retained["v1_survivor_body_preservation"] = (
                    {key: initial_memory.get(key) == after.get(key) for key in history_keys}
                    if initial_memory is not None and history_keys is not None
                    else None
                )
                retained["role_evidence"] = (
                    "post-revision content matches, not canonical references"
                )
            workspace = Path(state["workspace"])
            scratch = Path(result["scratch"])
            assessment = {
                "leg": stage.name,
                "status": "completed",
                "condition": row["condition"],
                "execution": result,
                "artifact": e2e.assess_feature(workspace, stage, case, scratch),
                "retained": retained,
                "checker_before": checker_before,
                "checker_after": checker_state(workspace),
                "canonical_public_check": assess_checker(workspace, stage.component, scratch),
                "memory_necessary": False,
                "alternative_sources": "earlier tasks and components retained",
                "instruction_package_unchanged": e2e.package_unchanged(state),
            }
            e2e.write_json(evidence / "assessment.json", assessment)
            stages.append(assessment)
            if not result["success"] or not result["model_matches"]:
                halt = "unsuccessful/interrupted host session retained; later stages unrun"
        except Exception as exc:
            stages.append(
                {
                    "leg": stage.name,
                    "status": "interrupted",
                    "condition": row["condition"],
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            halt = "interrupted attempt; never repurchased"
    e2e.write_json(
        directory / "result.json",
        {
            **row,
            "stages": stages,
            "status": "finished" if halt is None else "halted",
            "halt": halt,
        },
    )


def report(out: Path) -> dict[str, Any]:
    manifest = json.loads((out / "manifest.json").read_text())
    rows: list[dict[str, Any]] = []
    groups = []
    for case in manifest["cases"]:
        directory = out / "cases" / case["id"]
        result_path = directory / "result.json"
        result = json.loads(result_path.read_text()) if result_path.exists() else None
        stages = result["stages"] if result is not None else []
        actual = {stage["leg"]: stage for stage in stages}
        # A paid stage assessment is evidence even if interruption prevented a
        # lifecycle result; keep those observations visible in interim reports.
        for name in manifest["stages"]:
            path = directory / name / "assessment.json"
            if name not in actual and path.exists():
                actual[name] = json.loads(path.read_text())
            if name not in actual:
                started = (directory / name).exists()
                actual[name] = {"leg": name, "status": "interrupted" if started else "unrun"}
        completed = [stage for stage in actual.values() if stage["status"] == "completed"]
        rows.extend({**case, **stage} for stage in actual.values())
        groups.append(
            {
                **case,
                "planned": 8,
                "completed": len(completed),
                "artifacts_correct": sum(stage["artifact"]["passed"] for stage in completed),
                "canonical_target_passed": sum(
                    stage["canonical_public_check"].get("component", {}).get("passed") is True
                    for stage in completed
                ),
                "canonical_workspace_passed": sum(
                    stage["canonical_public_check"].get("whole_workspace", {}).get("passed") is True
                    for stage in completed
                ),
                "checker_changed_stages": sum(
                    stage["checker_before"] != stage["checker_after"] for stage in completed
                ),
            }
        )
    completed = [row for row in rows if row["status"] == "completed"]
    analysis = {
        "schema": "memory-contract-analysis.v1",
        "planned": manifest["planned_sessions"],
        "completed": len(completed),
        "groups": groups,
        "stages": rows,
        "artifacts_correct": sum(row["artifact"]["passed"] for row in completed),
        "known_cost_usd": sum(
            row["execution"]["cost_usd"]
            for row in completed
            if row["execution"]["cost_usd"] is not None
        ),
        "completed_sessions_cost_unknown": sum(
            row["execution"]["cost_usd"] is None for row in completed
        ),
        "counter_note": "Use offline action audit for help/query/list/write semantics",
        "limits": [
            "Four correlated lifecycles; one fixture; not a production reliability estimate",
            "Both conditions use installed guidance; only the public checker differs initially",
            "The agent may alter the checker; canonical post-session audit gives no feedback",
            "Runtime behavior, public shape, exact approved fields, and stored prose differ",
            "Existing code and task history remain legitimate alternative sources",
            "Legacy memory commands do not validate production Memory Bead guarantees",
        ],
    }
    index = 1
    while (out / f"analysis-{index:02}.json").exists() or (out / f"report-{index:02}.md").exists():
        index += 1
    e2e.write_json(out / f"analysis-{index:02}.json", analysis)
    lines = [
        "# Public contract check screen",
        "",
        f"Completed {len(completed)}/32 planned sessions; "
        f"{analysis['artifacts_correct']} complete artifacts.",
        "",
        "| CLI | Condition | Completed | Complete artifacts | Public target | Public workspace |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
        *[
            f"| {row['host']} | {row['condition']} | {row['completed']}/8 | "
            f"{row['artifacts_correct']} | {row['canonical_target_passed']} | "
            f"{row['canonical_workspace_passed']} |"
            for row in groups
        ],
        "",
        f"Known completed-session cost: ${analysis['known_cost_usd']:.6f}; "
        f"{analysis['completed_sessions_cost_unknown']} completed sessions "
        "have unknown dollar cost.",
        "Interrupted/partial attempts and earlier smokes remain separately accounted evidence.",
        "",
        *[f"- {limit}." for limit in analysis["limits"]],
        "",
    ]
    with (out / f"report-{index:02}.md").open("x") as target:
        target.write("\n".join(lines))
    return analysis


def fire(out: Path) -> None:
    manifest = json.loads((out / "manifest.json").read_text())
    assert_frozen(manifest)
    for row in manifest["cases"]:
        directory = out / "cases" / row["id"]
        if (directory / "result.json").exists():
            print(f"PRESERVED {row['id']}: recorded lifecycle is never repurchased", flush=True)
            continue
        if directory.exists():
            raise FileExistsError(
                f"Partial lifecycle exists; inspect without repurchase: {directory}"
            )
        run_lifecycle(out, row, manifest)
    report(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--freeze", action="store_true")
    actions.add_argument("--fire", action="store_true")
    actions.add_argument("--report", action="store_true")
    parser.add_argument("--claude-smoke", type=Path)
    parser.add_argument("--codex-smoke", type=Path)
    parser.add_argument("--checker-checks", type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.freeze:
        if args.claude_smoke is None or args.codex_smoke is None or args.checker_checks is None:
            parser.error("Freeze requires two prior smoke paths and offline --checker-checks proof")
        freeze(out, {"claude": args.claude_smoke, "codex": args.codex_smoke}, args.checker_checks)
    elif args.fire:
        fire(out)
    else:
        report(out)


if __name__ == "__main__":
    main()
