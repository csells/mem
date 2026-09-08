"""Reviewed second operational deviation: effective Codex configuration is fixed.

Only --run can launch models. The root launches this supervisor detached with both
output descriptors directed to the same exclusive regular log file. Original
failure markers and all prior evidence remain unchanged.

Copied from recovery-01 runner SHA256
9d62bf1669f9563324a338c97f337d5a54e725ce2ceec55e4c341e9c07be9dcc.
Only condition-validation and prior-deviation admission change. Session selection,
execution, phase claims, logging, stop behavior, and original model runner remain.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import stat
import sys
import tempfile
import threading
import time
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

# This standalone, result-local recovery helper imports unchanged frozen modules.
# ruff: noqa: E402
BENCH = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BENCH))
from membench.runner import memory_host_codex
from membench.runner import memory_model_profiles as profiles
from membench.runner import memory_prime_delivery_package as package
from scripts import memory_policy_handoff_experiment as policy
from scripts import memory_prime_delivery_runtime as delivery
from scripts import memory_routes_experiment as base
from scripts import memory_unprompted_experiment as legacy
from scripts import memory_unprompted_smoke as smoke

EXPECTED_SOURCE = Path("/Users/csells/.codex")
REQUIRED_CONDITION_SOURCES = (
    "memory-bench/membench/runner/memory_host_codex.py",
    "memory-bench/membench/runner/memory_e2e_hosts.py",
    "memory-bench/membench/runner/memory_model_profiles.py",
)


def assert_effective_frozen(manifest: dict[str, Any]) -> dict[str, Any]:
    """Permit only irrelevant raw Codex TOML drift; keep all other checks exact."""
    try:
        if memory_host_codex._source_home() != EXPECTED_SOURCE.resolve():
            raise ValueError("Codex source home differs from the reviewed source")
        config = EXPECTED_SOURCE / "config.toml"
        original = manifest["profile_sha256"][str(config)]
        payload = config.read_bytes()
        settings = tomllib.loads(payload.decode())
        consumed = {
            "model_reasoning_effort": settings.get("model_reasoning_effort", "high"),
            "service_tier": settings.get("service_tier", "default"),
        }
        if not all(isinstance(value, str) for value in consumed.values()):
            raise ValueError("Codex consumed effort/tier values must remain strings")
        for source in REQUIRED_CONDITION_SOURCES:
            if source not in manifest["source_sha256"]:
                raise ValueError("Effective condition proof requires frozen adapter sources")
        for identity in ("codex-astra", "codex-luna"):
            profile = profiles.get_profile(identity)
            frozen = manifest["model_profiles"][identity]
            if profile.reasoning_effort != "high" or frozen != {
                "host": profile.host,
                "model": profile.model,
                "reasoning_effort": "high",
            }:
                raise ValueError("Codex profile model or fixed high effort changed")
        actual_hash = hashlib.sha256(payload).hexdigest()
        effective = {
            **manifest,
            "profile_sha256": {**manifest["profile_sha256"], str(config): actual_hash},
        }
        # The unchanged validator rechecks the exact bytes just parsed plus every
        # source, binary, other profile, and fixture. The original manifest object
        # and file are untouched. This is not a global monkeypatch.
        legacy.assert_frozen(effective)
        return {
            "path": str(config),
            "original_sha256": original,
            "observed_sha256": actual_hash,
            "raw_profile_drift": original != actual_hash,
            "consumed_values": consumed,
            "effective_effort": "high",
            "effective_service_tier": "default",
            "source_home": str(EXPECTED_SOURCE),
        }
    except (OSError, ValueError, KeyError) as exc:
        raise legacy.FrozenInputsChangedError(str(exc)) from exc


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_input(name: str) -> Path:
    path = Path(name)
    return path if path.is_absolute() else base.REPO / path


def slot_disposition(cohort: Path, row: dict[str, Any]) -> str:
    evidence = legacy.session_path(cohort, row)
    if evidence.exists() or evidence.is_symlink():
        return (
            "preserved_result"
            if (evidence / "result.json").is_file()
            else "censored_existing_claim"
        )
    case = cohort / "cases" / row["lifecycle"]
    if row["stage"] == 1:
        return "censored_existing_lifecycle" if case.exists() or case.is_symlink() else "launch"
    previous = legacy.session_path(cohort, {**row, "stage": row["stage"] - 1})
    return "launch" if (previous / "result.json").is_file() else "censored_missing_predecessor"


def assert_durable_output(log: Path, descriptors: tuple[int, int] = (1, 2)) -> None:
    expected = log.stat()
    for descriptor in descriptors:
        actual = os.fstat(descriptor)
        if not stat.S_ISREG(actual.st_mode):
            raise ValueError("Supervisor output must be a regular file, never a pipe or terminal")
        if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise ValueError("Supervisor output is not the declared durable log file")


def original_logging_markers(cohort: Path, identities: list[str]) -> dict[str, str]:
    expected = {"type": "BrokenPipeError", "message": "[Errno 32] Broken pipe", "phase": "phase1"}
    hashes = {}
    for identity in identities:
        path = cohort / "blocked" / f"{identity}.json"
        if json.loads(path.read_text()) != expected:
            raise ValueError("Only the reviewed original BrokenPipeError marker may be overridden")
        hashes[str(path)] = sha(path)
    return hashes


def freeze(cohort: Path, review_path: Path, plan_path: Path) -> dict[str, Any]:
    if plan_path.exists() or plan_path.is_symlink():
        raise FileExistsError(plan_path)
    manifest_path = cohort / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    condition_evidence = assert_effective_frozen(manifest)
    if manifest.get("schema") != "memory-prime-delivery.v1":
        raise ValueError("Wrong original experiment")
    review = json.loads(review_path.read_text())
    if review.get("approved") is not True:
        raise ValueError("Independent recovery review is required")
    reviewed = {str(resolve_input(p).resolve()): h for p, h in review["reviewed_sha256"].items()}
    required = {
        Path(__file__).resolve(),
        Path(__file__).with_name("test_continue_untouched.py").resolve(),
        (cohort / "OPERATIONAL-RECOVERY-02.md").resolve(),
    }
    prior_plan_path = cohort / "recovery-01/operational-plan.json"
    prior_summary_path = cohort / "recovery-01/phase1/summary.json"
    prior_plan = json.loads(prior_plan_path.read_text())
    validate_plan(prior_plan)
    prior_summary = json.loads(prior_summary_path.read_text())
    shared = prior_summary.get("shared_input_fault", {})
    expected_fault = {
        "type": "FrozenInputsChangedError",
        "message": "A selected host's live profile changed after freeze",
    }
    if (
        prior_summary.get("phase") != "phase1"
        or prior_summary.get("operational_plan_sha256") != sha(prior_plan_path)
        or shared != expected_fault
        or any(
            p.get("failure")
            and {"type": p["failure"]["type"], "message": p["failure"]["message"]} != expected_fault
            for p in prior_summary["profiles"]
        )
    ):
        raise ValueError("Prior continuation has an unreviewed fault")
    proofs = review.get("effective_condition_proof_paths", [])
    if not proofs:
        raise ValueError("Independent effective-condition proof is required")
    required.update(resolve_input(p).resolve() for p in proofs)
    required.update({prior_plan_path.resolve(), prior_summary_path.resolve()})
    required.update(Path(p).resolve() for p in prior_plan["recovery_input_sha256"])
    originals = original_logging_markers(cohort, manifest["admitted_profile_ids"])
    failed = cohort / "phases/phase1/failed.json"
    failures = json.loads(failed.read_text())
    if {r["profile"] for r in failures["failures"]} != set(manifest["admitted_profile_ids"]):
        raise ValueError("Original failure summary does not cover the reviewed profiles")
    if any(r["error"] != "[Errno 32] Broken pipe" for r in failures["failures"]):
        raise ValueError("Original phase has a failure other than the reviewed broken pipe")
    originals[str(failed)] = sha(failed)
    for path in (cohort / "phases/phase1").glob("*-failure.json"):
        originals[str(path)] = sha(path)
    for path in (cohort / "recovery-01/phase1").glob("*.json"):
        originals[str(path)] = sha(path)
    existing_results = {}
    claims = []
    censored_lifecycles = set()
    recovered = []
    for row in manifest["slots"]:
        evidence = legacy.session_path(cohort, row)
        result = evidence / "result.json"
        if result.is_file():
            existing_results[str(result)] = sha(result)
            value = json.loads(result.read_text())
            if value.get("infrastructure_fault"):
                if not value.get("recovered_assessment") or value.get("exit_code") is not None:
                    raise ValueError(
                        "An existing infrastructure failure lacks reviewed posthoc assessment"
                    )
                required.update({result.resolve(), (evidence / "recovery.json").resolve()})
                recovered.append(str(result))
        elif (
            evidence.exists()
            or evidence.is_symlink()
            or (row["stage"] == 1 and (cohort / "cases" / row["lifecycle"]).exists())
        ):
            claims.append(row["slot"])
            censored_lifecycles.add(row["lifecycle"])
    if recovered:
        helper = resolve_input(review["posthoc_helper_path"]).resolve()
        approval = resolve_input(review["posthoc_review_path"]).resolve()
        required.update({helper, approval})
        approved = json.loads(approval.read_text())
        if approved.get("approved") is not True or approved.get("helper_sha256") != sha(helper):
            raise ValueError("Posthoc helper needs its exact independent approval")
        if approved.get("manifest_sha256") != sha(manifest_path):
            raise ValueError("Posthoc approval belongs to another original manifest")
        for result_name in recovered:
            value = json.loads(Path(result_name).read_text())
            if value["recovered_assessment"]["source_sha256"] != sha(helper):
                raise ValueError("Recovered result does not identify the approved helper")
    if not {str(p) for p in required}.issubset(reviewed):
        raise ValueError("Recovery review must hash driver, tests, deviation and posthoc inputs")
    for input_name, expected in reviewed.items():
        if sha(Path(input_name)) != expected:
            raise ValueError(f"Reviewed recovery input changed: {input_name}")
    plan = {
        "schema": "prime-operational-continuation.v1",
        "created_ns": time.time_ns(),
        "cohort": str(cohort),
        "manifest_sha256": sha(manifest_path),
        "review_path": str(review_path),
        "review_sha256": sha(review_path),
        "recovery_input_sha256": reviewed,
        "original_failure_sha256": originals,
        "preexisting_result_sha256": existing_results,
        "preexisting_claims_without_result": claims,
        "censored_lifecycles": sorted(censored_lifecycles),
        "admitted_recovered_results": recovered,
        "phase_order": ["phase1", "phase2"],
        "max_workers": 4,
        "no_retries_or_replacements": True,
        "conditions": (
            "All tasks, models, guidance, host bounds, native settings, graders and "
            "retained records remain the original frozen conditions."
        ),
        "effective_codex_condition": condition_evidence,
        "prior_operational_plan_sha256": sha(prior_plan_path),
        "prior_shared_fault_summary_sha256": sha(prior_summary_path),
    }
    legacy.write(plan_path, plan)
    return plan


def validate_plan(
    plan: dict[str, Any],
    *,
    condition_observer: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    cohort = Path(plan["cohort"])
    manifest_path = cohort / "manifest.json"
    if checked_hash(manifest_path) != plan["manifest_sha256"]:
        raise legacy.FrozenInputsChangedError("Original manifest changed")
    expected = {
        **plan["recovery_input_sha256"],
        **plan["original_failure_sha256"],
        **plan["preexisting_result_sha256"],
        plan["review_path"]: plan["review_sha256"],
    }
    for name, digest in expected.items():
        if checked_hash(Path(name)) != digest:
            raise legacy.FrozenInputsChangedError(f"Operational recovery input changed: {name}")
    manifest: dict[str, Any] = json.loads(manifest_path.read_text())
    condition = assert_effective_frozen(manifest)
    if condition_observer is not None:
        condition_observer(condition)
    return manifest


def checked_hash(path: Path) -> str:
    try:
        return sha(path)
    except OSError as exc:
        raise legacy.FrozenInputsChangedError(f"Required frozen input unavailable: {path}") from exc


def prior_phase_gate(
    phase: str, plan_hash: str, summary: Path | None, review: Path | None
) -> set[str]:
    if phase == "phase1":
        if summary is not None or review is not None:
            raise ValueError("Initial continuation has no prior recovery phase")
        return set()
    if phase != "phase2" or summary is None or review is None:
        raise ValueError("Phase2 requires an exact phase1 continuation summary review")
    prior = json.loads(summary.read_text())
    decision = json.loads(review.read_text())
    if (
        prior.get("phase") != "phase1"
        or prior.get("operational_plan_sha256") != plan_hash
        or decision.get("approved") is not True
        or decision.get("summary_sha256") != sha(summary)
    ):
        raise ValueError("Phase2 requires review of the exact phase1 continuation summary")
    if prior.get("shared_input_fault") is not None:
        raise ValueError("A shared input fault requires a new operational decision")
    return set(prior["blocked_profiles"])


def run_phase(
    plan_path: Path,
    phase: str,
    output: Path,
    log_path: Path,
    prior_summary: Path | None = None,
    prior_review: Path | None = None,
) -> dict[str, Any]:
    # Test logging before creating any attempt or starting a model.
    assert_durable_output(log_path)
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    plan = json.loads(plan_path.read_text())
    if (
        plan.get("schema") != "prime-operational-continuation.v1"
        or phase not in plan["phase_order"]
    ):
        raise ValueError("Wrong operational plan or phase")
    plan_hash = sha(plan_path)
    condition_observations: dict[str, dict[str, Any]] = {}
    condition_lock = threading.Lock()

    def remember_condition(condition: dict[str, Any]) -> None:
        with condition_lock:
            digest = condition["observed_sha256"]
            if digest in condition_observations:
                return
            observation = {**condition, "observed_ns": time.time_ns()}
            condition_observations[digest] = observation
            if output.is_dir():
                legacy.write(output / f"codex-profile-{digest}.json", observation)
            print("CODEX EFFECTIVE CONFIG " + json.dumps(observation), flush=True)

    manifest = validate_plan(plan, condition_observer=remember_condition)
    inherited_blocks = prior_phase_gate(phase, plan_hash, prior_summary, prior_review)
    order = manifest["worker_order"]
    if len(order) != len(set(order)) or set(order) != set(manifest["admitted_profile_ids"]):
        raise ValueError("Invalid frozen worker order")
    cohort = Path(plan["cohort"])
    # Changing --out must not bypass a prior continuation attempt or its new
    # profile failures. A new operational plan would require a new review.
    claim = plan_path.with_name(plan_path.stem + f".{phase}.claim.json")
    legacy.write(
        claim,
        {
            "phase": phase,
            "output": str(output),
            "pid": os.getpid(),
            "operational_plan_sha256": plan_hash,
        },
    )
    output.mkdir(parents=True, exist_ok=False)
    for digest, observation in condition_observations.items():
        legacy.write(output / f"codex-profile-{digest}.json", observation)
    legacy.write(
        output / "attempt.json",
        {
            "phase": phase,
            "pid": os.getpid(),
            "started_ns": time.time_ns(),
            "operational_plan_sha256": plan_hash,
            "stdout_log": str(log_path),
            "prior_summary_sha256": sha(prior_summary) if prior_summary else None,
            "prior_review_sha256": sha(prior_review) if prior_review else None,
        },
    )
    stop = threading.Event()

    def validate() -> None:
        if checked_hash(plan_path) != plan_hash:
            raise legacy.FrozenInputsChangedError("Operational plan changed during execution")
        validate_plan(plan, condition_observer=remember_condition)

    def worker(identity: str) -> dict[str, Any]:
        ledger = []
        failure = None
        server = handle = endpoint = None
        try:
            for row in [
                r for r in manifest["slots"] if r["phase"] == phase and r["profile_id"] == identity
            ]:
                if stop.is_set():
                    ledger.append({"slot": row["slot"], "status": "not_started_shared_input_fault"})
                    continue
                if identity in inherited_blocks:
                    ledger.append(
                        {"slot": row["slot"], "status": "not_started_prior_recovery_profile_fault"}
                    )
                    continue
                validate()
                disposition = slot_disposition(cohort, row)
                if row["lifecycle"] in plan["censored_lifecycles"]:
                    disposition = "censored_preexisting_lifecycle"
                if disposition != "launch":
                    ledger.append({"slot": row["slot"], "status": disposition})
                    print(f"PRESERVE {row['slot']} {disposition}", flush=True)
                    continue
                if profiles.get_profile(identity).host == "opencode" and server is None:
                    folder = output / "ollama"
                    folder.mkdir()
                    scratch = Path(
                        tempfile.mkdtemp(prefix="prime-continuation-server-", dir="/tmp")
                    ).resolve()
                    server, endpoint, handle = smoke.ollama_start(scratch, folder)
                # The unchanged runner also refuses any concurrent claim before launch.
                result = delivery.run_session(
                    cohort,
                    row,
                    endpoint,
                    corpus_root=policy.CORPUS,
                    package_installer=package.install,
                )
                ledger.append(
                    {
                        "slot": row["slot"],
                        "status": "assessed_new",
                        "result_sha256": sha(legacy.session_path(cohort, row) / "result.json"),
                    }
                )
                validate()
                print("PROGRESS " + json.dumps(legacy.progress(cohort, manifest)), flush=True)
                if result["infrastructure_fault"]:
                    raise RuntimeError(
                        f"New infrastructure fault in {row['slot']}; no profile override"
                    )
        except Exception as exc:
            failure = {"profile": identity, "type": type(exc).__name__, "message": str(exc)}
            if isinstance(exc, legacy.FrozenInputsChangedError):
                stop.set()
            legacy.write(output / f"{identity}-failure.json", failure)
        finally:
            if server is not None:
                smoke.stop_owned_server(server)
            if handle is not None:
                handle.close()
        result = {"profile": identity, "ledger": ledger, "failure": failure}
        legacy.write(output / f"{identity}-ledger.json", result)
        return result

    collected = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(worker, identity) for identity in order]
        for future in concurrent.futures.as_completed(futures):
            collected.append(future.result())
    shared_fault = None
    try:
        validate()
    except Exception as exc:
        shared_fault = {"type": type(exc).__name__, "message": str(exc)}
    blocked = inherited_blocks | {r["profile"] for r in collected if r["failure"]}
    slots = [r for r in manifest["slots"] if r["phase"] == phase]
    assessed = sum((legacy.session_path(cohort, r) / "result.json").is_file() for r in slots)
    report = {
        "schema": "prime-operational-phase-summary.v1",
        "phase": phase,
        "finished_ns": time.time_ns(),
        "operational_plan_sha256": plan_hash,
        "manifest_sha256": plan["manifest_sha256"],
        "planned_phase_slots": len(slots),
        "phase_assessed": assessed,
        "all_planned_phase_slots_assessed": assessed == len(slots),
        "profiles": collected,
        "blocked_profiles": sorted(blocked),
        "shared_input_fault": shared_fault,
        "censored_lifecycles": plan["censored_lifecycles"],
        "effective_codex_condition_observations": list(condition_observations.values()),
        "progress": legacy.progress(cohort, manifest),
        "status": (
            "stopped_with_new_fault"
            if blocked or shared_fault
            else "finished_with_censoring" if assessed < len(slots) else "finished"
        ),
    }
    legacy.write(output / "summary.json", report)
    print(
        "CONTINUATION FINISHED "
        + json.dumps(
            {k: report[k] for k in ("phase", "phase_assessed", "planned_phase_slots", "status")}
        ),
        flush=True,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", choices=["phase1", "phase2"])
    parser.add_argument("--cohort", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--prior-summary", type=Path)
    parser.add_argument("--prior-review", type=Path)
    args = parser.parse_args()
    if bool(args.freeze) == bool(args.run):
        parser.error("Choose exactly one of --freeze or --run")
    if args.freeze:
        if args.cohort is None or args.review is None:
            parser.error("--freeze requires --cohort and --review")
        plan = freeze(args.cohort.resolve(), args.review.resolve(), args.plan.resolve())
        print(
            json.dumps(
                {
                    "plan": str(args.plan),
                    "sha256": sha(args.plan),
                    "censored_lifecycles": plan["censored_lifecycles"],
                }
            )
        )
    else:
        if args.out is None or args.log is None:
            parser.error("--run requires --out and --log")
        result = run_phase(
            args.plan.resolve(),
            args.run,
            args.out.resolve(),
            args.log.resolve(),
            args.prior_summary,
            args.prior_review,
        )
        if result["blocked_profiles"] or result["shared_input_fault"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
