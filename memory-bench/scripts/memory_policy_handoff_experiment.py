"""Freeze and run ordinary policy handoffs without task-authored memory cues.

The 264 planned slots compare generic and explicit-occasion standing guidance.
Admission pins all ten requested model profiles; behavioral qualification failures
are retained diagnostics, not an automatic profile exclusion. No scored inference
can start before a reviewed manifest has been frozen.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from membench.runner import memory_model_profiles as profiles
from membench.runner import memory_unprompted_hosts as hosts
from membench.runner import memory_unprompted_package as legacy_package
from scripts import memory_e2e_experiment as e2e
from scripts import memory_routes_experiment as base
from scripts import memory_unprompted_experiment as runtime

CORPUS = base.REPO / "memory-bench/fixtures/memory-policy-fork-corpus"
PACKAGE = base.REPO / "memory-bench/fixtures/memory-policy-handoff-package"
PLAN = base.REPO / "specs/plans/0006-policy-handoff-model-sweep.md"
QUALIFICATION = (
    base.REPO
    / "memory-bench/results/memory-routes/2026-09-07-policy-handoff-qualification-01"
    / "qualification-admission.json"
)
PHASES = ("phase1", "phase2", "normal")
ARMS = ("generic", "occasions")
WORLDS = {
    "finance": ("finance/account-first", "finance/subscription-first"),
    "webhooks": ("webhooks/global-first", "webhooks/account-first"),
}
ANCHORS = ("codex-astra", "claude-sonnet", "opencode-qwen", "zcode-glm")
# Five of each finance world; the four normal anchors cover all four world/catalog
# combinations. Both guidance arms always share a profile's world and route.
WORLD_PATTERN = (0, 0, 1, 1, 0, 1, 1, 0, 1, 0)


def install(workspace: Path, store: Path, arm: str) -> dict[str, Any]:
    from membench.runner import memory_policy_handoff_package

    return memory_policy_handoff_package.install(workspace, store, arm)


def schedule(profile_ids: list[str] | None = None) -> list[dict[str, Any]]:
    selected = list(profiles.PROFILES) if profile_ids is None else profile_ids
    if len(selected) != len(set(selected)):
        raise ValueError("Duplicate profile admission")
    if any(p not in profiles.PROFILES for p in selected):
        raise ValueError("Unknown model profile in schedule")
    rows: list[dict[str, Any]] = []
    for profile_id in selected:
        index = list(profiles.PROFILES).index(profile_id)
        profile = profiles.get_profile(profile_id)
        cases = [(family, arm) for family in WORLDS for arm in ARMS]
        random.Random(1907 + index).shuffle(cases)
        for phase, stages in (("phase1", range(1, 3)), ("phase2", range(3, 7))):
            for family, arm in cases:
                family_index = list(WORLDS).index(family)
                route = "indexed" if (index + family_index) % 2 == 0 else "search-only"
                world = (WORLD_PATTERN[index] + family_index) % 2
                lifecycle = f"{profile_id}-{family}-{arm}-isolated"
                for stage in stages:
                    rows.append(
                        {
                            "slot": f"{lifecycle}-{stage}",
                            "lifecycle": lifecycle,
                            "profile_id": profile_id,
                            "host": profile.host,
                            "family": family,
                            "corpus_family": WORLDS[family][world],
                            "arm": arm,
                            "catalog_mode": route,
                            "mode": "isolated",
                            "stage": stage,
                            "phase": phase,
                        }
                    )
        if profile_id in ANCHORS:
            lifecycle = f"{profile_id}-finance-occasions-normal"
            for stage in range(1, 7):
                rows.append(
                    {
                        "slot": f"{lifecycle}-{stage}",
                        "lifecycle": lifecycle,
                        "profile_id": profile_id,
                        "host": profile.host,
                        "family": "finance",
                        "corpus_family": WORLDS["finance"][WORLD_PATTERN[index]],
                        "arm": "occasions",
                        "catalog_mode": "indexed" if index % 2 == 0 else "search-only",
                        "mode": "normal",
                        "stage": stage,
                        "phase": "normal",
                    }
                )
    return rows


def tree_hashes(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(base.REPO)): base.sha(p)
        for p in sorted(folder.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def review_paths() -> set[str]:
    return {
        *tree_hashes(CORPUS),
        *tree_hashes(PACKAGE),
        *tree_hashes(legacy_package.FIXTURE),
        str(PLAN.relative_to(base.REPO)),
        str(QUALIFICATION.relative_to(base.REPO)),
        "memory-bench/scripts/memory_policy_handoff_experiment.py",
        "memory-bench/scripts/memory_unprompted_experiment.py",
        "memory-bench/membench/runner/memory_model_profiles.py",
        "memory-bench/membench/runner/memory_policy_handoff_package.py",
    }


def validate_corpus() -> None:
    for worlds in WORLDS.values():
        for family in worlds:
            meta, tasks = runtime.corpus(family, corpus_root=CORPUS)
            if len(tasks) != 6 or meta["entrypoint"] != "main.py":
                raise ValueError(f"Expected six reviewed main.py tasks: {family}")
            previous: set[str] = set()
            for task in tasks:
                path = task["public_tests"]
                relative = Path(path)
                if relative.is_absolute() or ".." in relative.parts or path in previous:
                    raise ValueError("Public suites need unique relative paths")
                previous.add(path)
                if not (CORPUS / family / path).is_file():
                    raise ValueError(f"Missing public suite: {family}/{path}")
                cases = json.loads(
                    (CORPUS / family / "graders" / f"stage-{task['stage']}.json").read_text()
                )
                if not cases or len({c["name"] for c in cases}) != len(cases):
                    raise ValueError("Expected nonempty independently named grader cases")
                for case in cases:
                    if "expected" not in case:
                        raise ValueError("Missing independent expected result")
                    if "artifact_json_path" in case:
                        artifact = Path(case["artifact_json_path"])
                        if (
                            artifact.is_absolute()
                            or not artifact.parts
                            or ".." in artifact.parts
                            or any(k in case for k in ("stdin", "input", "argv"))
                        ):
                            raise ValueError("Artifact case must name one safe relative JSON file")
                    elif "stdin" not in case:
                        raise ValueError("CLI cases require explicit stdin")


def freeze(out: Path, admission: Path) -> None:
    review = json.loads(admission.read_text())
    if review.get("approved") is not True:
        raise ValueError("Independent corpus/package/runtime admission is required")
    admitted = review.get("admitted_profile_ids")
    if not isinstance(admitted, list) or len(admitted) != len(set(admitted)):
        raise ValueError("Admission must explicitly list unique model profiles")
    if set(admitted) != set(profiles.PROFILES):
        raise ValueError("All ten requested profiles require explicit admission for this freeze")
    if not review_paths().issubset(review.get("reviewed_sha256", {})):
        raise ValueError("Admission must cover every new corpus, package, and runtime input")
    for relative, digest in review["reviewed_sha256"].items():
        if base.sha(base.REPO / relative) != digest:
            raise ValueError(f"Reviewed input changed: {relative}")
    validate_corpus()
    sources = e2e.sources()
    trees = {
        str(p.relative_to(base.REPO)): tree_hashes(p)
        for p in (CORPUS, PACKAGE, legacy_package.FIXTURE)
    }
    for entries in trees.values():
        sources.update(entries)
    for path in (PLAN, QUALIFICATION):
        sources[str(path.relative_to(base.REPO))] = base.sha(path)
    binaries = e2e.binary_hashes()
    for p in (
        hosts.OPENCODE,
        hosts.ZCODE,
        hosts.ZCODE.parent.parent / "vendor/zcode.cjs",
    ):
        binaries[str(p)] = base.sha(p)
    model_profiles = {
        profile_id: {
            "host": profiles.get_profile(profile_id).host,
            "model": profiles.get_profile(profile_id).model,
            "reasoning_effort": profiles.get_profile(profile_id).reasoning_effort,
        }
        for profile_id in admitted
    }
    manifest = {
        "schema": "ordinary-policy-handoff.v1",
        "created_ns": time.time_ns(),
        "slots": schedule(admitted),
        "admitted_profile_ids": admitted,
        "worker_order": [
            "opencode-qwen",
            "zcode-glm",
            *[p for p in admitted if p not in {"opencode-qwen", "zcode-glm"}],
        ],
        "max_concurrent_workers": 4,
        "model_profiles": model_profiles,
        "source_sha256": sources,
        "input_tree_sha256": trees,
        "binary_sha256": binaries,
        "profile_sha256": runtime.profile_hashes(include_claude=True),
        "timeout_seconds": runtime.TIMEOUT,
        "claude_cli_budget_usd": runtime.BUDGET,
        "no_automatic_retries": True,
        "require_phase_review": True,
        "phases": {"phase1": 80, "phase2": 160, "normal": 24},
        "admission": review,
        "qualification_policy": (
            "Reviewed auth/model/interface/sandbox compatibility determines admission; "
            "behavioral diagnostic failures are retained and not automatically excluded"
        ),
        "catalog_contract": (
            "Indexed lifecycles expose JSON {keys:[actual before-snapshot keys]} via "
            "BEADS_MEMORY_INDEX; search-only lifecycles expose no index. No bodies, "
            "guessed keys, seeded records, or task-specific instructions."
        ),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    }
    if len(manifest["slots"]) != 264:
        raise ValueError("The admitted registry does not produce the reviewed 264-slot plan")
    out.mkdir(parents=True, exist_ok=False)
    runtime.write(out / "manifest.json", manifest)
    for relative in sources:
        target = out / "frozen-source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base.REPO / relative, target)
    print("FROZEN 264 slots; zero model calls", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--run", choices=PHASES)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if sum([args.freeze, bool(args.run), args.status]) != 1:
        parser.error("Choose exactly one of --freeze, --run, or --status")
    if args.freeze:
        if args.admission is None:
            parser.error("--freeze requires --admission")
        freeze(args.out, args.admission)
    elif args.run:
        manifest = json.loads((args.out / "manifest.json").read_text())
        if manifest.get("schema") != "ordinary-policy-handoff.v1":
            raise ValueError("Wrong experiment manifest")
        runtime.run_phase(
            args.out, args.run, corpus_root=CORPUS, package_installer=install, phases=PHASES
        )
    else:
        manifest = json.loads((args.out / "manifest.json").read_text())
        print(json.dumps(runtime.progress(args.out, manifest), indent=2))


if __name__ == "__main__":
    main()
