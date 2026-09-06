#!/usr/bin/env python3
"""Explicitly reconcile a witnessed goal timeout, then buy only untouched frozen pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import membench
from membench.runner.bd_real_corpus import load_corpus
from membench.runner.bd_real_experiment import _completed, _directory, _identity_check, _run_pair
from membench.runner.bd_real_pair import run_real_pair
from membench.runner.e1_grid import out_lock, write_json_new
from membench.runner.resume_cache import digest

FAILURE_RECORD = "terminal-failure.json"
CONTINUATION = "continuation.json"
PACKAGE_ROOT = Path(membench.__file__).resolve().parent


def _read(path: Path) -> Any:
    return json.loads(path.read_text())


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _archives(out: Path, corpus: Path) -> dict[str, str]:
    expected_sources = {
        "harness": {
            str(path.relative_to(PACKAGE_ROOT.parent)): path.read_bytes()
            for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        },
        "corpus": {
            str(path.relative_to(corpus)): path.read_bytes()
            for path in sorted(corpus.rglob("*"))
            if path.is_file()
        },
    }
    hashes = {}
    for kind, expected in expected_sources.items():
        path = out / f"{kind}-source.zip"
        sidecar = out / f"{kind}-source-sha256.json"
        if not path.is_file() or not sidecar.is_file():
            raise ValueError("frozen source archive evidence is missing")
        field = "archive_sha256" if kind == "harness" else "sha256"
        if _read(sidecar) != {field: _hash(path)}:
            raise ValueError("frozen source archive hash changed")
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if (
                len(names) != len(set(names))
                or set(names) != set(expected)
                or archive.testzip() is not None
                or any(archive.read(name) != content for name, content in expected.items())
            ):
                raise ValueError("frozen source archive contents changed")
        hashes[path.name] = _hash(path)
        hashes[sidecar.name] = _hash(sidecar)
    return hashes


def _identity(out: Path, amendment: Path, corpus: Path) -> dict[str, Any]:
    return {
        "archives": _archives(out, corpus),
        "manifest_digest": digest(_read(out / "manifest.json")),
        "manifest_sha256": _hash(out / "manifest.json"),
        "amendment_path": str(amendment.resolve(strict=True)),
        "amendment_sha256": _hash(amendment),
        "continuation_script_sha256": _hash(Path(__file__)),
    }


def terminal_inventory(
    directory: Path, pair: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, str]:
    """Accept only the observed completed-establish / bounded-goal-timeout evidence shape."""
    if (directory / "cell.json").exists() or (directory / "run/result.json").exists():
        raise ValueError("terminal timeout must not carry successful pair completion")
    if _read(directory / "started.json") != {"pair": pair, "manifest_digest": digest(manifest)}:
        raise ValueError("timeout start identity differs from frozen pair")
    halt = _read(directory / "halt.json")
    if set(halt) != {"type", "error"} or halt["type"] != "RuntimeError":
        raise ValueError("timeout must have a retained terminal runner halt")
    run = directory / "run"
    required = {"establish-output.tar", "goal-candidate.tar"}
    for leg in (0, 1):
        required.update(
            f"leg-{leg}/{name}"
            for name in (
                "result.json",
                "process.json",
                "raw.stream.jsonl",
                "stderr.txt",
                "argv.json",
                "receipts.json",
                "settings.json",
                "native-hook.json",
            )
        )
        required.update(
            f"leg-{leg}-{suffix}"
            for suffix in ("input-files.json", "output-files.json", "input.tar", "bd-store.tar")
        )
    if any(not (run / name).is_file() or (run / name).is_symlink() for name in required):
        raise ValueError("timeout evidence inventory is incomplete")
    establish, goal = (_read(run / f"leg-{leg}/result.json") for leg in (0, 1))
    if (
        establish.get("leg") != 0
        or establish.get("status") != "ok"
        or establish.get("integrity_errors") != []
        or establish.get("terminal_result", {}).get("is_error") is not False
        or _read(run / "leg-0/process.json") != {"status": "ok", "returncode": 0}
    ):
        raise ValueError("establish evidence is not a completed successful process")
    if (
        goal.get("leg") != 1
        or goal.get("status") != "timeout"
        or goal.get("terminal_result") != {}
        or goal.get("integrity_errors") != ["missing_or_failed_terminal_result"]
        or _read(run / "leg-1/process.json") != {"status": "timeout", "returncode": None}
    ):
        raise ValueError("goal evidence does not prove the narrowly admitted timeout")
    for name in required:
        if name.endswith(".tar") and not tarfile.is_tarfile(run / name):
            raise ValueError("timeout snapshot is not a readable tar archive")
    files = [directory / "started.json", directory / "halt.json", *sorted(run.rglob("*"))]
    if any(path.is_symlink() for path in files):
        raise ValueError("retained evidence must not be symlinked")
    return {str(path.relative_to(directory)): _hash(path) for path in files if path.is_file()}


def _failure_done(
    directory: Path,
    pair: Mapping[str, Any],
    manifest: Mapping[str, Any],
    identity: Mapping[str, Any],
) -> bool:
    path = directory / FAILURE_RECORD
    if not path.exists():
        return False
    record = _read(path)
    expected = {
        "schema": "bd-real-terminal-failure.v1",
        "status": "goal_timeout",
        "pair": pair,
        "identity": identity,
        "artifact_sha256": terminal_inventory(directory, pair, manifest),
    }
    if record != expected:
        raise ValueError("reconciled terminal evidence or identity changed")
    return True


def _audit(out: Path, manifest: Mapping[str, Any], identity: Mapping[str, Any]) -> list[str]:
    directories = [_directory(out, pair) for pair in manifest["schedule"]]
    if len(directories) != len(set(directories)):
        raise ValueError("duplicate frozen pair")
    if (out / "pairs").exists() and not set((out / "pairs").iterdir()) <= set(directories):
        raise ValueError("unscheduled pair directory")
    statuses = []
    for pair, directory in zip(manifest["schedule"], directories, strict=True):
        if _failure_done(directory, pair, manifest, identity):
            statuses.append("terminal_failure")
        elif _completed(directory, pair, digest(manifest)):
            statuses.append("completed")
        else:
            statuses.append("missing")
    return statuses


def reconcile(out: Path, *, corpus_dir: Path, amendment: Path, pair_key: str) -> dict[str, Any]:
    with out_lock(out):
        manifest = _read(out / "manifest.json")
        tasks = load_corpus(corpus_dir)
        _identity_check(corpus_dir, tasks, manifest)()
        matches = [pair for pair in manifest["schedule"] if _directory(out, pair).name == pair_key]
        if len(matches) != 1:
            raise ValueError("reconciliation must identify exactly one scheduled pair")
        identity = _identity(out, amendment, corpus_dir)
        continuation_path = out / CONTINUATION
        if continuation_path.exists() and _read(continuation_path) != identity:
            raise ValueError("continuation identity changed")
        pair = matches[0]
        directory = _directory(out, pair)
        inventory = terminal_inventory(directory, pair, manifest)
        record = {
            "schema": "bd-real-terminal-failure.v1",
            "status": "goal_timeout",
            "pair": pair,
            "identity": identity,
            "artifact_sha256": inventory,
        }
        path = directory / FAILURE_RECORD
        if path.exists():
            if _read(path) != record:
                raise ValueError("terminal reconciliation already exists with different evidence")
        else:
            write_json_new(path, record)
        statuses = _audit(out, manifest, identity)
        if not continuation_path.exists():
            write_json_new(continuation_path, identity)
        return {"statuses": statuses, "reconciled_pair": pair_key}


def fire(
    out: Path,
    *,
    corpus_dir: Path,
    amendment: Path,
    max_pairs: int = 1,
    pair_runner: Callable[..., dict[str, Any]] = run_real_pair,
) -> dict[str, int]:
    if not 1 <= max_pairs <= 12:
        raise ValueError("max_pairs must be between 1 and 12")
    with out_lock(out):
        manifest = _read(out / "manifest.json")
        identity = _identity(out, amendment, corpus_dir)
        if _read(out / CONTINUATION) != identity:
            raise ValueError("continuation script, amendment, or manifest changed")
        tasks = load_corpus(corpus_dir)
        identity_check = _identity_check(corpus_dir, tasks, manifest)
        identity_check()
        statuses = _audit(out, manifest, identity)
        indexed = {task["task_id"]: task for task in tasks}
        new_pairs = 0
        for pair, status in zip(manifest["schedule"], statuses, strict=True):
            if status != "missing":
                continue
            if new_pairs >= max_pairs:
                break
            identity_check()
            if _identity(out, amendment, corpus_dir) != identity:
                raise ValueError("continuation identity changed before purchase")
            _run_pair(
                _directory(out, pair),
                pair,
                indexed[pair["task_id"]],
                manifest,
                corpus_dir,
                pair_runner,
            )
            new_pairs += 1
        return {
            "new_pairs": new_pairs,
            "completed_pairs_reused": statuses.count("completed"),
            "terminal_failures_preserved": statuses.count("terminal_failure"),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--amendment", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--reconcile", metavar="PAIR_KEY")
    mode.add_argument("--fire", action="store_true")
    parser.add_argument("--max-pairs", type=int, default=1)
    args = parser.parse_args()
    if args.fire:
        if os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            raise ValueError("continuation requires subscription OAuth and no API key")
        result = fire(
            args.out, corpus_dir=args.corpus, amendment=args.amendment, max_pairs=args.max_pairs
        )
    else:
        result = reconcile(
            args.out, corpus_dir=args.corpus, amendment=args.amendment, pair_key=args.reconcile
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
