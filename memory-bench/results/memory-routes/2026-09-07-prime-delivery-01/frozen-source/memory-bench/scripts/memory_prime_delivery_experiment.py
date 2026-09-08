"""Frozen matched prime/startup delivery study; only --run starts scored agents."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import itertools
import json
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from membench.runner import memory_model_profiles as profiles
from membench.runner import memory_policy_handoff_package as previous_package
from membench.runner import memory_prime_delivery_package as package
from membench.runner import memory_unprompted_hosts as hosts
from scripts import memory_e2e_experiment as e2e
from scripts import memory_policy_handoff_experiment as policy
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
PHASES = ("phase1", "phase2")
PLAN = base.REPO / "specs/plans/0007-memory-prime-delivery.md"


def schedule() -> list[dict[str, Any]]:
    rows = []
    permutations = list(itertools.permutations(package.ARMS))
    for index, profile_id in enumerate(PROFILE_IDS):
        prior_index = list(profiles.PROFILES).index(profile_id)
        profile = profiles.get_profile(profile_id)
        families = list(policy.WORLDS)
        if index % 2:
            families.reverse()
        for phase, stages in (("phase1", range(1, 3)), ("phase2", range(3, 7))):
            for family in families:
                family_index = list(policy.WORLDS).index(family)
                world = (policy.WORLD_PATTERN[prior_index] + family_index) % 2
                route = "indexed" if (prior_index + family_index) % 2 == 0 else "search-only"
                for arm in permutations[index]:
                    lifecycle = f"{profile_id}-{family}-{arm}-isolated"
                    for stage in stages:
                        rows.append(
                            {
                                "slot": f"{lifecycle}-{stage}",
                                "lifecycle": lifecycle,
                                "profile_id": profile_id,
                                "host": profile.host,
                                "family": family,
                                "corpus_family": policy.WORLDS[family][world],
                                "arm": arm,
                                "catalog_mode": route,
                                "mode": "isolated",
                                "stage": stage,
                                "phase": phase,
                            }
                        )
    return rows


def review_paths() -> set[str]:
    return {
        *policy.tree_hashes(policy.CORPUS),
        *policy.tree_hashes(policy.PACKAGE),
        *policy.tree_hashes(previous_package.OLD),
        str(PLAN.relative_to(base.REPO)),
        "memory-bench/scripts/memory_prime_delivery_experiment.py",
        "memory-bench/scripts/memory_prime_delivery_runtime.py",
        "memory-bench/scripts/memory_prime_delivery_qualification.py",
        "memory-bench/membench/runner/memory_prime_delivery_package.py",
        "memory-bench/tests/test_memory_prime_delivery_experiment.py",
        "memory-bench/tests/test_memory_prime_delivery_runtime.py",
        "memory-bench/tests/test_memory_prime_delivery_package.py",
        "memory-bench/tests/test_memory_prime_delivery_qualification.py",
    }


def freeze(out: Path, admission: Path) -> None:
    review = json.loads(admission.read_text())
    if review.get("approved") is not True or set(review.get("admitted_profile_ids", [])) != set(
        PROFILE_IDS
    ):
        raise ValueError("Independent admission must cover all six declared profiles")
    if not review_paths().issubset(review.get("reviewed_sha256", {})):
        raise ValueError("Review must cover every corpus, guidance and new delivery input")
    for name, digest in review["reviewed_sha256"].items():
        if base.sha(base.REPO / name) != digest:
            raise ValueError(f"Reviewed input changed: {name}")
    qualification = Path(review["qualification_path"])
    if base.sha(qualification) != review["qualification_sha256"]:
        raise ValueError("Reviewed qualification changed")
    qualified = json.loads(qualification.read_text())
    if qualified.get("planned") != 12 or qualified.get("assessed") != 12:
        raise ValueError("All 12 declared delivery qualifications require assessed receipts")
    if set(qualified.get("interface_admitted_profiles", [])) != set(PROFILE_IDS):
        raise ValueError("Qualification must explicitly account for each selected interface")
    if qualified.get("briefing_sha256") != hashlib.sha256(package.briefing().encode()).hexdigest():
        raise ValueError("Qualified briefing differs from the current guidance")
    if qualified.get("actual_prime_equivalence") is not True:
        raise ValueError("Qualification must establish actual prime equivalence")
    policy.validate_corpus()
    sources = e2e.sources()
    trees = {
        str(p.relative_to(base.REPO)): policy.tree_hashes(p)
        for p in (policy.CORPUS, policy.PACKAGE, previous_package.OLD)
    }
    for values in trees.values():
        sources.update(values)
    for name in review_paths():
        sources[name] = base.sha(base.REPO / name)
    sources[str(qualification.relative_to(base.REPO))] = base.sha(qualification)
    binaries = e2e.binary_hashes()
    for path in (hosts.OPENCODE, hosts.ZCODE, hosts.ZCODE.parent.parent / "vendor/zcode.cjs"):
        binaries[str(path)] = base.sha(path)
    manifest = {
        "schema": "memory-prime-delivery.v1",
        "created_ns": time.time_ns(),
        "slots": schedule(),
        "admitted_profile_ids": list(PROFILE_IDS),
        "worker_order": [
            "opencode-qwen",
            "zcode-glm",
            "codex-astra",
            "claude-haiku",
            "claude-sonnet",
            "codex-luna",
        ],
        "max_concurrent_workers": 4,
        "model_profiles": {
            name: {
                "host": profiles.get_profile(name).host,
                "model": profiles.get_profile(name).model,
                "reasoning_effort": profiles.get_profile(name).reasoning_effort,
            }
            for name in PROFILE_IDS
        },
        "source_sha256": sources,
        "input_tree_sha256": trees,
        "binary_sha256": binaries,
        "profile_sha256": legacy.profile_hashes(include_claude=True),
        "timeout_seconds": legacy.TIMEOUT,
        "claude_cli_budget_usd": legacy.BUDGET,
        "no_automatic_retries": True,
        "require_phase_review": True,
        "phases": {"phase1": 72, "phase2": 144},
        "briefing_sha256": qualified["briefing_sha256"],
        "briefing_bytes": len(package.briefing().encode()),
        "actual_prime_equivalence": qualified["actual_prime_equivalence"],
        "primary_use": (
            "before behavior edit or informing subsequent test/validation; "
            "excludes post-test confirmation"
        ),
        "startup_delivery": (
            "common briefing plus separately labeled task in one initial user message; "
            "thin prime retained"
        ),
        "admission": review,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    }
    out.mkdir(parents=True, exist_ok=False)
    legacy.write(out / "manifest.json", manifest)
    for relative in sources:
        target = out / "frozen-source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base.REPO / relative, target)
    print("FROZEN 216 slots; zero scored model calls", flush=True)


def run_phase(out: Path, phase: str) -> None:
    """Reuse the prior phase lifecycle, with this study's explicit session runner.

    Derived from memory_unprompted_experiment.run_phase. Differences are fixed
    study phases, direct delivery.run_session dispatch and the reviewed corpus.
    No shared module is rebound while workers run.
    """
    if phase not in PHASES:
        raise ValueError("Unknown scored phase")
    manifest = json.loads((out / "manifest.json").read_text())
    legacy.assert_frozen(manifest)
    phase_root = out / "phases" / phase
    if phase != PHASES[0]:
        prior = out / "phases" / PHASES[PHASES.index(phase) - 1]
        summary = next(
            (prior / n for n in ("completed.json", "failed.json") if (prior / n).exists()), None
        )
        if summary is None:
            raise ValueError("Prior phase must complete and be reviewed before continuation")
        review_file = prior / "reviewed.json"
        review = json.loads(review_file.read_text()) if review_file.is_file() else {}
        if review.get("approved") is not True or review.get("summary_sha256") != base.sha(summary):
            raise ValueError("Prior phase needs explicit review of its exact final summary")
    phase_root.mkdir(parents=True, exist_ok=False)
    stop = threading.Event()
    order = manifest["worker_order"]
    if len(order) != len(set(order)) or set(order) != set(manifest["admitted_profile_ids"]):
        raise ValueError("Worker order must cover each admitted profile exactly once")

    def worker(identity: str) -> None:
        host = profiles.get_profile(identity).host
        server = log = endpoint = None
        blocked = out / "blocked" / f"{identity}.json"
        if blocked.exists():
            print(
                f"BLOCKED {identity}: preserving earlier failure; no replacement runs", flush=True
            )
            return
        try:
            rows = [
                r for r in manifest["slots"] if r["phase"] == phase and r["profile_id"] == identity
            ]
            if host == "opencode":
                folder = phase_root / "ollama"
                folder.mkdir()
                scratch = Path(tempfile.mkdtemp(prefix="prime-server-", dir="/tmp")).resolve()
                server, endpoint, log = smoke.ollama_start(scratch, folder)
            for row in rows:
                if stop.is_set():
                    break
                legacy.assert_frozen(manifest)
                result = delivery.run_session(
                    out, row, endpoint, corpus_root=policy.CORPUS, package_installer=package.install
                )
                legacy.assert_frozen(manifest)
                print("PROGRESS " + json.dumps(legacy.progress(out, manifest)), flush=True)
                if result["infrastructure_fault"]:
                    raise RuntimeError(
                        f"Infrastructure fault in {row['slot']}; inspect preserved evidence"
                    )
        except BaseException as exc:
            failure = {"type": type(exc).__name__, "message": str(exc), "phase": phase}
            if isinstance(exc, legacy.FrozenInputsChangedError):
                stop.set()
            else:
                blocked.parent.mkdir(exist_ok=True)
                legacy.write(blocked, failure)
            legacy.write(phase_root / f"{identity}-failure.json", failure)
            raise
        finally:
            if server is not None:
                smoke.stop_owned_server(server)
            if log is not None:
                log.close()

    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(worker, identity): identity for identity in order}
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                failures.append({"profile": futures[future], "error": str(exc)})
    try:
        legacy.assert_frozen(manifest)
    except legacy.FrozenInputsChangedError as exc:
        failures.append({"profile": "shared-inputs", "error": str(exc)})
    if failures:
        legacy.write(
            phase_root / "failed.json",
            {"failures": failures, "progress": legacy.progress(out, manifest)},
        )
        raise RuntimeError("Phase stopped with preserved failures; no automatic reruns")
    legacy.write(phase_root / "completed.json", legacy.progress(out, manifest))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--run", choices=PHASES)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if sum([args.freeze, bool(args.run), args.status]) != 1:
        parser.error("Choose exactly one of --freeze, --run or --status")
    if args.freeze:
        if args.admission is None:
            parser.error("--freeze requires --admission")
        freeze(args.out, args.admission)
    elif args.run:
        manifest = json.loads((args.out / "manifest.json").read_text())
        if manifest.get("schema") != "memory-prime-delivery.v1":
            raise ValueError("Wrong experiment manifest")
        run_phase(args.out, args.run)
    else:
        print(
            json.dumps(
                legacy.progress(args.out, json.loads((args.out / "manifest.json").read_text())),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
