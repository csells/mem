"""Twelve explicit delivery diagnostics; only --run starts inference, never retries."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from membench.runner import memory_model_profiles as profiles
from membench.runner import memory_policy_handoff_package as previous
from membench.runner import memory_prime_delivery_package as package
from membench.runner import memory_unprompted_hosts as hosts
from membench.runner.memory_routes_runtime import experiment_env
from scripts import memory_e2e_experiment as e2e
from scripts import memory_model_qualification as prior_qualification
from scripts import memory_prime_delivery_runtime as delivery
from scripts import memory_routes_experiment as base
from scripts import memory_unprompted_experiment as legacy
from scripts import memory_unprompted_smoke as smoke

PROFILE_IDS = (
    "codex-astra",
    "codex-luna",
    "claude-sonnet",
    "claude-haiku",
    "opencode-qwen",
    "zcode-glm",
)
ARMS = ("rich-prime", "startup-briefing")


def create_corpus(root: Path) -> None:
    """Create a qualification-only explicit task; no scored policy answers."""
    family = root / "diagnostic"
    family.mkdir(parents=True, exist_ok=False)
    (family / "starter").mkdir()
    (family / "graders").mkdir()
    (family / "starter/main.py").write_text('import json\nprint(json.dumps({"ready": True}))\n')
    legacy.write(family / "manifest.json", {"entrypoint": "main.py"})
    legacy.write(
        family / "tasks.json",
        {
            "tasks": [
                {
                    "stage": 1,
                    "title": "Verify project workflow delivery",
                    "prompt": (
                        "This is an explicit CLI delivery diagnostic, not product work. "
                        "Run `bd prime --no-memories` and inspect its complete output. "
                        "Create delivery-receipt.json containing exactly "
                        '{"marker":"prime-delivery-ok"}. '
                        "The existing main.py needs no change."
                    ),
                }
            ]
        },
    )
    legacy.write(
        family / "graders/stage-1.json",
        [
            {
                "name": "diagnostic-json-receipt",
                "artifact_json_path": "delivery-receipt.json",
                "expected": {"marker": "prime-delivery-ok"},
            }
        ],
    )


def static_prime_checks(out: Path) -> dict[str, Any]:
    """Exercise real bd in disposable stores, preserving sentinel and all outputs."""
    out.mkdir(parents=True, exist_ok=False)
    checks = []
    for arm in package.ARMS:
        case = out / arm
        case.mkdir()
        scratch = Path(tempfile.mkdtemp(prefix="prime-static-", dir="/tmp")).resolve()
        admin = scratch / "admin"
        for name in ("config", "tmp", "bin"):
            (admin / name).mkdir(parents=True)
        env = experiment_env(admin / "config", admin / "tmp", admin / "bin")
        store, work = scratch / "store", scratch / "work"
        base.initialize_store(store, env, case / "initialization.json")
        installed = package.install(work, store, arm)
        base.checked_bd(
            ["remember", "STATIC-ONLY-SENTINEL-BODY", "--key", "static-only-sentinel-key"],
            store,
            env,
        )
        before = base.memories(store, env)
        actual = base.checked_bd(["prime", "--no-memories"], store, env)
        after = base.memories(store, env)
        expected = package.briefing() if arm == "rich-prime" else package.thin_prime()
        check = {
            "arm": arm,
            "scratch": str(scratch),
            "package": installed,
            "actor": "harness; deterministic qualification only",
            "stdout": actual,
            "actual_sha256": hashlib.sha256(actual.encode()).hexdigest(),
            "expected_sha256": hashlib.sha256(expected.encode()).hexdigest(),
            "exact_output": actual == expected,
            "no_sentinel_key_or_body": "STATIC-ONLY-SENTINEL" not in actual
            and "static-only-sentinel-key" not in actual,
            "memory_unchanged": before == after,
            "memory_before": before,
            "memory_after": after,
        }
        legacy.write(case / "result.json", check)
        checks.append(check)
    result = {
        "passed": all(
            c["exact_output"] and c["no_sentinel_key_or_body"] and c["memory_unchanged"]
            for c in checks
        ),
        "checks": checks,
    }
    legacy.write(out / "result.json", result)
    return result


def assess_session(result: dict[str, Any], evidence: Path) -> dict[str, Any]:
    """Separate authentic host execution, complete prime delivery and task compliance."""
    arm = result["arm"]
    expected = package.briefing() if arm == "rich-prime" else package.thin_prime()
    task = (evidence / "task-prompt.txt").read_text()
    prompt = (evidence / "launch-prompt.txt").read_text()
    submitted = prompt == delivery.compose_prompt(arm, task, package.briefing())
    executions = result["receipt_assessment"]["executions"]
    exact_prime = any(
        e.get("command") == "prime" and e.get("returncode") == 0 and e.get("stdout") == expected
        for e in executions
    )
    calls = json.loads((evidence / "tool-calls.json").read_text())
    visible = exact_prime and any(
        not c.get("is_error")
        and isinstance(c.get("result"), str)
        and e2e.body_delivered(c["result"], expected)
        for c in calls
    )
    interface = bool(
        result["models_observed"] == [profiles.get_profile(result["profile_id"]).model]
        and result["session_id"]
        and result["host_success"]
        and result["exit_code"] == 0
        and not result["timed_out"]
        and not result["infrastructure_fault"]
        and not result["receipt_assessment"]["unknown_execution"]
    )
    return {
        "interface_passed": interface,
        "diagnostic_passed": bool(
            interface and result["artifact_passed"] and visible and submitted
        ),
        "marker_artifact_correct": result["artifact_passed"],
        "agent_prime_exact_output": exact_prime,
        "agent_prime_full_output_visible": visible,
        "rich_prime_model_output_visible": bool(arm == "rich-prime" and visible),
        "launch_prompt_matches_expected": submitted,
        "startup_briefing_submitted": bool(arm == "startup-briefing" and submitted),
        "limits": (
            "Submitted prompt is transport evidence, not proof of model understanding. "
            "Full text visibility is checked across captured tool outputs; identical file reads "
            "can also deliver that text."
        ),
    }


def run(out: Path) -> dict[str, Any]:
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    configuration_before = prior_qualification.configuration_hashes()
    create_corpus(out / "corpus")
    static = static_prime_checks(out / "static-prime")
    if static["passed"] is not True:
        raise ValueError("Real scratch prime checks failed; no inference authorized by this runner")
    sources = e2e.sources()
    for folder in (previous.OLD, previous.NEW, out / "corpus"):
        for path in folder.rglob("*"):
            if path.is_file():
                sources[str(path)] = base.sha(path)
    binaries = e2e.binary_hashes()
    for path in (hosts.OPENCODE, hosts.ZCODE, hosts.ZCODE.parent.parent / "vendor/zcode.cjs"):
        binaries[str(path)] = base.sha(path)
    frozen = {
        "planned": 12,
        "profile_ids": list(PROFILE_IDS),
        "arms": list(ARMS),
        "workers": 4,
        "scope": "explicit delivery diagnostics only; no adoption credit",
        "timeout_seconds": legacy.TIMEOUT,
        "claude_cli_budget_usd": legacy.BUDGET,
        "mode": "isolated",
        "retries": 0,
        "source_sha256": sources,
        "binary_sha256": binaries,
        "profile_sha256": legacy.profile_hashes(include_claude=True),
        "configuration_sha256_before": configuration_before,
        "briefing_sha256": hashlib.sha256(package.briefing().encode()).hexdigest(),
    }
    legacy.write(out / "plan.json", frozen)
    stop = threading.Event()
    results: list[dict[str, Any]] = []
    started = time.monotonic()
    print("QUALIFICATION 12 explicit slots; maximum 4 workers; no retries", flush=True)

    def worker(profile_id: str) -> list[dict[str, Any]]:
        profile = profiles.get_profile(profile_id)
        rows = []
        server = log = endpoint = None
        try:
            if profile.host == "opencode":
                folder = out / "ollama"
                folder.mkdir()
                scratch = Path(tempfile.mkdtemp(prefix="prime-qual-server-", dir="/tmp")).resolve()
                server, endpoint, log = smoke.ollama_start(scratch, folder)
            for arm in ARMS:
                if stop.is_set():
                    break
                legacy.assert_frozen(frozen)
                lifecycle = f"{profile_id}-{arm}-qualification"
                row = {
                    "slot": f"{lifecycle}-1",
                    "lifecycle": lifecycle,
                    "stage": 1,
                    "profile_id": profile_id,
                    "host": profile.host,
                    "family": "diagnostic",
                    "arm": arm,
                    "mode": "isolated",
                    "catalog_mode": "none",
                    "phase": "qualification",
                }
                try:
                    result = delivery.run_session(out, row, endpoint, corpus_root=out / "corpus")
                    assessed = assess_session(result, legacy.session_path(out, row))
                    receipt = {**row, **assessed, "result": result}
                    legacy.write(legacy.session_path(out, row) / "qualification.json", assessed)
                    rows.append(receipt)
                    print(
                        f"QUALIFIED {row['slot']} interface={assessed['interface_passed']} "
                        f"diagnostic={assessed['diagnostic_passed']}",
                        flush=True,
                    )
                except Exception as exc:
                    failure = {
                        **row,
                        "interface_passed": False,
                        "diagnostic_passed": False,
                        "exception": type(exc).__name__,
                        "message": str(exc),
                    }
                    legacy.write(out / f"{lifecycle}-failure.json", failure)
                    rows.append(failure)
                legacy.assert_frozen(frozen)
        except Exception as exc:
            if isinstance(exc, legacy.FrozenInputsChangedError):
                stop.set()
            legacy.write(
                out / f"{profile_id}-worker-failure.json",
                {
                    "exception": type(exc).__name__,
                    "message": str(exc),
                    "profile_id": profile_id,
                },
            )
        finally:
            if server is not None:
                smoke.stop_owned_server(server)
            if log is not None:
                log.close()
        return rows

    order = (
        "opencode-qwen",
        "zcode-glm",
        "codex-astra",
        "claude-haiku",
        "claude-sonnet",
        "codex-luna",
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(worker, profile_id): profile_id for profile_id in order}
        for completed_profiles, future in enumerate(concurrent.futures.as_completed(futures), 1):
            results.extend(future.result())
            print(
                f"QUALIFICATION PROGRESS assessed={sum('result' in r for r in results)}/12 "
                f"completed_profiles={completed_profiles}/6",
                flush=True,
            )
    configuration_after = prior_qualification.configuration_hashes()
    immutable = configuration_before == configuration_after
    frozen_error = None
    try:
        legacy.assert_frozen(frozen)
    except legacy.FrozenInputsChangedError as exc:
        frozen_error = str(exc)
    admitted = [
        p
        for p in PROFILE_IDS
        if len([r for r in results if r["profile_id"] == p]) == 2
        and all(r["interface_passed"] for r in results if r["profile_id"] == p)
    ]
    if not immutable or frozen_error:
        admitted = []
    report = {
        "schema": "memory-prime-delivery-qualification.v1",
        "planned": 12,
        "assessed": sum("result" in r for r in results),
        "interface_admitted_profiles": admitted,
        "diagnostic_passes": sum(r["diagnostic_passed"] for r in results),
        "actual_prime_equivalence": static["passed"],
        "briefing_sha256": frozen["briefing_sha256"],
        "rows": results,
        "configuration_sha256_before": configuration_before,
        "configuration_sha256_after": configuration_after,
        "configuration_unchanged": immutable,
        "frozen_input_error": frozen_error,
        "reported_cost_usd": sum(r["result"]["cost_usd"] or 0 for r in results if "result" in r),
        "cost_unknown_sessions": sum(
            r["result"]["cost_usd"] is None for r in results if "result" in r
        ),
        "elapsed_seconds": time.monotonic() - started,
        "scope": "Explicit command-delivery qualification, not voluntary memory adoption.",
    }
    legacy.write(out / "result.json", report)
    print(
        f"QUALIFICATION DONE {report['assessed']}/12 assessed; "
        f"{report['diagnostic_passes']}/12 diagnostics",
        flush=True,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run", action="store_true", required=True)
    args = parser.parse_args()
    run(args.out)


if __name__ == "__main__":
    main()
