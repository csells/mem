"""Frozen schedules and no-repurchase execution for curated real-work memory trials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import zipfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from membench.runner.e1_grid import out_lock, write_json_new
from membench.runner.resume_cache import digest

CONDITIONS = ("current", "focused")
VARIANTS = ("unbriefed", "briefed")
MAX_PILOT_PAIRS = 12


def build_manifest(
    tasks: Sequence[Mapping[str, Any]],
    *,
    corpus_sha256: str,
    model: str,
    cli_version: str,
    bd_identity: Mapping[str, str],
    source: str,
    timeout_s: float,
    seed: int,
) -> dict[str, Any]:
    ids = [task["task_id"] for task in tasks]
    if not ids or len(set(ids)) != len(ids) or timeout_s <= 0:
        raise ValueError("Unique tasks and a positive timeout are required")
    if not all((corpus_sha256, model, cli_version, source)) or not all(
        bd_identity.get(key) for key in ("path", "sha256", "version")
    ):
        raise ValueError("All execution identities must be pinned")
    rng = random.Random(seed)
    blocks = [(task_id, variant) for task_id in ids for variant in VARIANTS]
    rng.shuffle(blocks)
    schedule: list[dict[str, Any]] = []
    for task_id, variant in blocks:
        conditions = list(CONDITIONS)
        rng.shuffle(conditions)
        schedule.extend(
            {"task_id": task_id, "variant": variant, "condition": condition}
            for condition in conditions
        )
    if len(schedule) > MAX_PILOT_PAIRS:
        raise ValueError("Pilot exceeds the frozen 12-pair ceiling")
    return {
        "schema": "bd-real-experiment.v1",
        "protocol_revision": 3,
        "execution_boundary": "bubblewrap filesystem allowlist and private process namespace",
        "agent_python": "task grader interpreter with candidate src on PYTHONPATH",
        "pairing": "constructed_parent_context",
        "model": model,
        "cli_version": cli_version,
        "bd_identity": dict(bd_identity),
        "source_fingerprint": source,
        "corpus_sha256": corpus_sha256,
        "timeout_s": timeout_s,
        "seed": seed,
        "setting_sources": "user",
        "instruction_delivery": "assembled workspace CLAUDE.md copied to isolated user CLAUDE.md",
        "native_memory_settings": {"autoMemoryEnabled": True},
        "session_carryover": "bd store only; fresh per-leg config and restored goal workspace",
        "native_memory_hook": "redirect",
        "automatic_memory_preload": "disabled; unexpected startup evidence refuses continuation",
        "planned_pairs": len(schedule),
        "planned_sessions": 2 * len(schedule),
        "schedule": schedule,
    }


def freeze(out: Path, manifest: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with out_lock(out):
        _freeze(out, manifest)


def _freeze(out: Path, manifest: Mapping[str, Any]) -> None:
    path = out / "manifest.json"
    if path.exists():
        if json.loads(path.read_text()) != manifest:
            raise ValueError("Frozen experiment identity changed")
    elif any(out.iterdir()):
        raise ValueError("Nonempty output directory has no frozen identity")
    else:
        write_json_new(path, manifest)


def _directory(out: Path, pair: Mapping[str, Any]) -> Path:
    key = hashlib.sha256(json.dumps(dict(pair), sort_keys=True).encode()).hexdigest()[:16]
    return out / "pairs" / key


def _completed(directory: Path, pair: Mapping[str, Any], manifest_digest: str) -> bool:
    path = directory / "cell.json"
    if path.exists():
        cell = json.loads(path.read_text())
        if cell.get("pair") != pair or cell.get("manifest_digest") != manifest_digest:
            raise ValueError("Completed pair identity differs from frozen schedule")
        inventory = cell.get("artifact_sha256")
        if not isinstance(inventory, dict) or not inventory:
            raise ValueError("Completed pair is missing raw evidence inventory")
        if _evidence_inventory(directory, cell.get("result")) != inventory:
            raise ValueError("Completed pair raw evidence changed")
        return True
    if directory.exists():
        raise ValueError("Started pair requires evidence reconciliation; no automatic retry")
    return False


def _evidence_inventory(directory: Path, result: Any) -> dict[str, str]:
    run = directory / "run"
    if not isinstance(result, dict) or not isinstance(result.get("legs"), list):
        raise ValueError("Missing pair result evidence")
    if len(result["legs"]) != 2:
        raise ValueError("Two persisted legs are required for completion evidence")
    pair = json.loads((directory / "started.json").read_text())["pair"]
    if any(result.get(key) != value for key, value in pair.items()):
        raise ValueError("Returned task identity differs from journal")
    required = ["result.json", "task_check.json", "goal-candidate.tar"]
    required += [
        f"leg-{leg}/{name}"
        for leg in range(2)
        for name in [
            "result.json",
            "raw.stream.jsonl",
            "receipts.json",
            "argv.json",
            "process.json",
        ]
    ]
    if any(not (run / name).is_file() for name in required):
        raise ValueError("Missing raw pair evidence")
    for leg, record in enumerate(result["legs"]):
        if record.get("leg") != leg or record.get("status") != "ok":
            raise ValueError("Incomplete leg evidence cannot satisfy completion")
        if json.loads((run / f"leg-{leg}/result.json").read_text()) != record:
            raise ValueError("Persisted leg evidence differs from pair result")
    if json.loads((run / "result.json").read_text()) != result:
        raise ValueError("Persisted pair evidence differs from returned result")
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(run.rglob("*"))
        if path.is_file()
    }


def _run_pair(
    directory: Path,
    pair: Mapping[str, Any],
    task: Mapping[str, Any],
    manifest: Mapping[str, Any],
    corpus_dir: Path,
    runner: Callable[..., dict[str, Any]],
) -> None:
    directory.mkdir(parents=True)
    identity = {"pair": dict(pair), "manifest_digest": digest(manifest)}
    write_json_new(directory / "started.json", identity)
    try:
        result = runner(
            task,
            corpus_dir=corpus_dir,
            out=directory / "run",
            condition=pair["condition"],
            variant=pair["variant"],
            model=manifest["model"],
            cli_version=manifest["cli_version"],
            bd_binary=manifest["bd_identity"]["path"],
            timeout_s=manifest["timeout_s"],
        )
        inventory = _evidence_inventory(directory, result)
        write_json_new(
            directory / "cell.json", {**identity, "result": result, "artifact_sha256": inventory}
        )
    except BaseException as exc:
        write_json_new(directory / "halt.json", {"type": type(exc).__name__, "error": str(exc)})
        raise


def execute(
    out: Path,
    manifest: Mapping[str, Any],
    *,
    tasks: Sequence[Mapping[str, Any]],
    corpus_dir: Path,
    max_pairs: int,
    pair_runner: Callable[..., dict[str, Any]],
    identity_check: Callable[[], None],
) -> dict[str, int]:
    if not 0 < max_pairs <= MAX_PILOT_PAIRS:
        raise ValueError("max_pairs must be between 1 and 12")
    if json.loads((out / "manifest.json").read_text()) != manifest:
        raise ValueError("Execution identity differs from frozen manifest")
    indexed = {task["task_id"]: task for task in tasks}
    if len(indexed) != len(tasks):
        raise ValueError("Duplicate task identity")
    new_pairs = 0
    reused_pairs = 0
    with out_lock(out):
        completed = [
            _completed(_directory(out, pair), pair, digest(manifest))
            for pair in manifest["schedule"]
        ]
        for pair, done in zip(manifest["schedule"], completed, strict=True):
            directory = _directory(out, pair)
            if done:
                reused_pairs += 1
                continue
            if new_pairs >= max_pairs:
                break
            identity_check()
            _run_pair(directory, pair, indexed[pair["task_id"]], manifest, corpus_dir, pair_runner)
            new_pairs += 1
    return {"new_pairs": new_pairs, "reused_pairs": reused_pairs}


def _archive_source(out: Path) -> None:
    archive = out / "harness-source.zip"
    package = Path(__file__).resolve().parents[1]
    if archive.exists():
        identity = out / "harness-source-sha256.json"
        if (
            not identity.is_file()
            or json.loads(identity.read_text()).get("archive_sha256")
            != hashlib.sha256(archive.read_bytes()).hexdigest()
        ):
            raise ValueError("Source archive evidence is incomplete or changed")
        with zipfile.ZipFile(archive) as existing:
            if existing.testzip() is not None:
                raise ValueError("Source archive integrity failed")
            expected = {
                str(path.relative_to(package.parent)): path.read_bytes()
                for path in sorted(package.rglob("*.py"))
            }
            if set(existing.namelist()) != set(expected) or any(
                existing.read(name) != content for name, content in expected.items()
            ):
                raise ValueError("Archived source contents differ from pinned harness")
        return
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as target:
        for path in sorted(package.rglob("*.py")):
            target.write(path, str(path.relative_to(package.parent)))
    write_json_new(
        out / "harness-source-sha256.json",
        {"archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()},
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("data/bd-real-memory-v1"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--expect-cli-version", required=True)
    parser.add_argument("--timeout-s", type=float, default=300)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--fire", action="store_true")
    parser.add_argument("--max-pairs", type=int, default=1)
    return parser.parse_args(argv)


def _identity_check(
    corpus: Path, tasks: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]
) -> Callable[[], None]:
    from membench.runner.bd_experiment import resolve_bd_identity, source_fingerprint
    from membench.runner.bd_real_corpus import load_corpus
    from membench.runner.headless_agent import resolve_cli_version

    def identity_check() -> None:
        if load_corpus(corpus) != tasks:
            raise ValueError("Corpus identity changed")
        if (
            hashlib.sha256((corpus / "manifest.json").read_bytes()).hexdigest()
            != manifest["corpus_sha256"]
        ):
            raise ValueError("Corpus manifest identity changed")
        if source_fingerprint() != manifest["source_fingerprint"]:
            raise ValueError("Harness source changed")
        if (
            resolve_bd_identity() != manifest["bd_identity"]
            or resolve_cli_version() != manifest["cli_version"]
        ):
            raise ValueError("Executable identity changed")

    return identity_check


def main(argv: Sequence[str] | None = None) -> int:
    from membench.runner.bd_experiment import resolve_bd_identity, source_fingerprint
    from membench.runner.bd_real_corpus import load_corpus
    from membench.runner.bd_real_pair import run_real_pair
    from membench.runner.headless_agent import resolve_cli_version

    args = _parse_args(argv)
    if args.fire and (
        os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    ):
        raise ValueError("Execution requires subscription OAuth and no ANTHROPIC_API_KEY")
    corpus = args.corpus.resolve(strict=True)
    tasks = load_corpus(corpus)
    cli_version = resolve_cli_version()
    if cli_version != args.expect_cli_version:
        raise ValueError("CLI version differs from the requested pin")
    manifest = build_manifest(
        tasks,
        corpus_sha256=hashlib.sha256((corpus / "manifest.json").read_bytes()).hexdigest(),
        model=args.model,
        cli_version=cli_version,
        bd_identity=resolve_bd_identity(),
        source=source_fingerprint(),
        timeout_s=args.timeout_s,
        seed=args.seed,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    with out_lock(args.out):
        _freeze(args.out, manifest)
        _archive_source(args.out)

    result = (
        execute(
            args.out,
            manifest,
            tasks=tasks,
            corpus_dir=corpus,
            max_pairs=args.max_pairs,
            pair_runner=run_real_pair,
            identity_check=_identity_check(corpus, tasks, manifest),
        )
        if args.fire
        else {"planned_pairs": manifest["planned_pairs"]}
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
