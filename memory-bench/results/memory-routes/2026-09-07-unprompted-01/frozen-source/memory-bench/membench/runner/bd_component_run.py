"""Explicit plan/fire entrypoint for the frozen eight-session component diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from membench.runner.bd_component_experiment import execute, freeze
from membench.runner.bd_experiment import resolve_bd_identity, source_fingerprint
from membench.runner.bd_real_experiment import _archive_source
from membench.runner.headless_agent import resolve_cli_version

ENVIRONMENT_CODE = """import hashlib, importlib.metadata, json, sys
packages = []
for item in importlib.metadata.distributions():
    record = item.read_text('RECORD')
    packages.append((item.metadata['Name'], item.version,
        hashlib.sha256(record.encode()).hexdigest() if record is not None else None))
print(json.dumps({'version': sys.version, 'prefix': sys.prefix,
    'packages': sorted(packages)}, sort_keys=True))
"""


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def archive_identity(repository: Path, commit: str) -> str:
    return sha256(
        subprocess.check_output(
            ["git", "-C", str(repository), "archive", "--format=tar", commit], timeout=60
        )
    )


def environment_identity(python: Path) -> dict[str, Any]:
    body = json.loads(
        subprocess.check_output([str(python), "-I", "-c", ENVIRONMENT_CODE], timeout=60)
    )
    if not isinstance(body, dict):
        raise ValueError("Interpreter environment identity must be an object")
    return body


def runtime_executable_identity() -> dict[str, dict[str, str]]:
    identities = {}
    for name in ("claude", "dolt", "bwrap"):
        found = shutil.which(name)
        if found is None:
            raise ValueError(f"Required runtime executable unavailable: {name}")
        path = Path(found).absolute()
        identities[name] = {
            "path": str(path),
            "resolved": str(path.resolve(strict=True)),
            "sha256": sha256(path.read_bytes()),
        }
    return identities


def verify_inventory(root: Path) -> None:
    root = root.resolve(strict=True)
    inventory = json.loads((root / "SHA256.json").read_text())
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError("Dataset inventory must be nonempty")
    for name, expected in inventory.items():
        path = root / name
        if (
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or not path.resolve().is_relative_to(root)
            or not path.is_file()
            or sha256(path.read_bytes()) != expected
        ):
            raise ValueError(f"Dataset inventory mismatch: {name}")


def verify_live_identity(manifest: Mapping[str, Any]) -> None:
    configuration = manifest["configuration"]
    if source_fingerprint() != configuration["source_fingerprint"]:
        raise ValueError("Harness source identity changed")
    if resolve_bd_identity() != configuration["bd_identity"]:
        raise ValueError("bd executable identity changed")
    if resolve_cli_version() != configuration["cli_version"]:
        raise ValueError("CLI identity changed")
    if runtime_executable_identity() != configuration["runtime_executables"]:
        raise ValueError("Runtime executable path or contents changed")
    python = Path(configuration["agent_python"])
    if str(python.resolve(strict=True)) != configuration["python_resolved"]:
        raise ValueError("Interpreter symlink target changed")
    if environment_identity(python) != configuration["python_environment"]:
        raise ValueError("Interpreter environment changed")
    if (
        archive_identity(Path(configuration["repo_absolute"]), configuration["base_commit"])
        != configuration["candidate_archive_sha256"]
    ):
        raise ValueError("Candidate archive identity changed")
    verify_inventory(Path(configuration["dataset_root"]))
    archive_dir = Path(configuration["source_archive_dir"])
    if not (archive_dir / "harness-source.zip").is_file():
        raise ValueError("Missing frozen source archive")
    _archive_source(archive_dir)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fire", action="store_true")
    parser.add_argument("--max-sessions", type=int, default=1)
    args = parser.parse_args(argv)
    if args.fire and (
        os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    ):
        raise ValueError("Execution requires subscription OAuth and no ANTHROPIC_API_KEY")
    manifest = json.loads(args.manifest.read_text())
    verify_live_identity(manifest)
    freeze(args.out, manifest)
    result: dict[str, Any] = {"planned_sessions": 8, "fired": False}
    if args.fire:
        from membench.runner.bd_component_session import run_component_session

        result = execute(
            args.out,
            manifest,
            session_runner=run_component_session,
            identity_check=lambda: verify_live_identity(manifest),
            max_sessions=args.max_sessions,
        )
    print(json.dumps(result, sort_keys=True))
    return 1 if result.get("halted") else 0


if __name__ == "__main__":
    raise SystemExit(main())
