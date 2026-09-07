"""Validate immutable real-task corpus inputs before launching paid agent sessions."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

ARTIFACT_KEYS = ("source_packet", "establish_prompt", "goal_unbriefed", "goal_briefed")


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("expected nonempty string without NUL")
    return value


def _hex(value: Any, length: int) -> str:
    text = _text(value)
    if not re.fullmatch(f"[0-9a-f]{{{length}}}", text):
        raise ValueError(f"expected {length}-character hex digest")
    return text


def _relative(value: Any) -> PurePosixPath:
    text = _text(value)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or "\\" in text or str(path) == ".":
        raise ValueError("unsafe relative path")
    return path


def _artifact(root: Path, value: Any, *, prefix: str) -> tuple[str, bytes]:
    spec = _mapping(value)
    relative = _relative(spec.get("path"))
    if prefix and not str(relative).startswith(prefix + "/"):
        raise ValueError(f"artifact must be under {prefix}")
    resolved = (root / str(relative)).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("artifact escapes root")
    if prefix and not resolved.is_relative_to(root.resolve() / prefix):
        raise ValueError("artifact escapes designated directory")
    payload = resolved.read_bytes()
    if hashlib.sha256(payload).hexdigest() != _hex(spec.get("sha256"), 64):
        raise ValueError(f"artifact hash mismatch: {relative}")
    return str(relative), payload


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"git validation failed ({result.returncode}): {args[0]}")
    return result.stdout


def _source(task: dict[str, Any], packet: bytes) -> dict[str, str]:
    repo = Path(_text(task.get("repo_absolute")))
    if not repo.is_absolute():
        raise ValueError("repository must be absolute")
    base, landing = (_hex(task.get(key), 40) for key in ("base_commit", "landing_commit"))
    for commit in (base, landing):
        _git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
    if base == landing:
        raise ValueError("base must be a proper ancestor of landing")
    _git(repo, "merge-base", "--is-ancestor", base, landing)
    source = _mapping(task.get("source"))
    git_path = str(_relative(source.get("git_path")))
    blob = _git(repo, "show", f"{base}:{git_path}")
    if hashlib.sha256(blob).hexdigest() != _hex(source.get("blob_sha256"), 64):
        raise ValueError("source blob hash mismatch")
    oid = _git(repo, "rev-parse", f"{base}:{git_path}").decode().strip()
    if oid != _hex(source.get("git_blob_oid"), 40):
        raise ValueError("source git blob mismatch")
    start, end = source.get("start_line"), source.get("end_line")
    lines = blob.splitlines(keepends=True)
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
        raise ValueError("invalid source excerpt range")
    if b"".join(lines[start - 1 : end]) not in packet:
        raise ValueError("source excerpt absent from packet")
    return {
        "repo_absolute": str(repo),
        "base_commit": base,
        "landing_commit": landing,
        "git_blob_oid": oid,
    }


def _selected_nodes(ids: list[Any], targets: set[str]) -> list[str]:
    nodes = []
    for value in ids:
        test_id = _text(value)
        head, separator, tail = test_id.partition("::")
        matches = [
            target
            for target in targets
            if head == target[:-3].replace("/", ".")
            or head.startswith(target[:-3].replace("/", ".") + ".")
        ]
        if not separator or len(matches) != 1:
            raise ValueError("grader selection must name a declared module")
        target = matches[0]
        classes = head[len(target[:-3].replace("/", ".")) :].removeprefix(".")
        names = ([*classes.split(".")] if classes else []) + tail.split("::")
        if not all(name.isidentifier() for name in names):
            raise ValueError("invalid grader selection identifiers")
        nodes.append(target + "::" + "::".join(names))
    if len(nodes) != len(set(nodes)):
        raise ValueError("duplicate grader selection")
    return nodes


def _grader(root: Path, task: dict[str, Any]) -> dict[str, str]:
    grader = _mapping(task.get("grader"))
    if grader.get("withheld_from_agents") is not True:
        raise ValueError("grader assets must be withheld")
    command = grader.get("check_command")
    if not isinstance(command, list) or len(command) < 4:
        raise ValueError("grader command must be argv")
    argv = [_text(arg) for arg in command]
    if (
        not Path(argv[0]).is_absolute()
        or not Path(argv[0]).name.startswith("python")
        or argv[1:3] != ["-m", "pytest"]
    ):
        raise ValueError("grader requires absolute Python -m pytest")
    modules = grader.get("modules")
    ids = grader.get("test_ids")
    if not isinstance(modules, list) or not modules or not isinstance(ids, list) or not ids:
        raise ValueError("grader modules and test_ids required")
    for test_id in ids:
        _text(test_id)
    inventory = {}
    targets: set[str] = set()
    for module in modules:
        path, payload = _artifact(root, module, prefix=f'grader-assets/{task["task_id"]}/tests')
        target = str(_relative(_mapping(module).get("target_path")))
        if not target.startswith("tests/") or not target.endswith(".py"):
            raise ValueError("grader target must be a contained Python test path")
        if not path.endswith(".py.txt") or "corpus:" + path in inventory or target in targets:
            raise ValueError("invalid or duplicate grader module")
        targets.add(target)
        inventory["corpus:" + path] = hashlib.sha256(payload).hexdigest()
    prefix = ["-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider"]
    if argv[1:] != prefix + _selected_nodes(ids, targets):
        raise ValueError("grader command selection differs from declared test_ids")
    return inventory


def _validate(corpus_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = (corpus_dir / "manifest.json").read_bytes()
    manifest = _mapping(json.loads(raw))
    if manifest.get("schema") != "bd-real-memory.v1":
        raise ValueError("unsupported corpus schema")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("nonempty tasks required")
    seen: set[str] = set()
    inventory: dict[str, str] = {}
    pins = []
    for value in tasks:
        task = _mapping(value)
        task_id = _text(task.get("task_id"))
        if not re.fullmatch("[A-Za-z0-9_-]+", task_id) or task_id in seen:
            raise ValueError("invalid or duplicate task_id")
        seen.add(task_id)
        _text(task.get("work_id"))
        _text(task.get("repo"))
        artifacts = _mapping(task.get("artifacts"))
        if set(artifacts) != set(ARTIFACT_KEYS):
            raise ValueError("runtime artifact keys mismatch")
        packets = {}
        for key in ARTIFACT_KEYS:
            path, payload = _artifact(corpus_dir, artifacts[key], prefix=task_id)
            inventory["corpus:" + path] = hashlib.sha256(payload).hexdigest()
            packets[key] = payload
        inventory.update(_grader(corpus_dir, task))
        pins.append(_source(task, packets["source_packet"]))
        # Bundles belong to this repository's existing .mem store, not the runtime corpus.
        path, payload = _artifact(
            corpus_dir.resolve().parents[2], task.get("bundle"), prefix=".mem"
        )
        inventory["bundle:" + path] = hashlib.sha256(payload).hexdigest()
    path, payload = _artifact(corpus_dir, manifest.get("preflight"), prefix="preflight")
    inventory["corpus:" + path] = hashlib.sha256(payload).hexdigest()
    return tasks, {
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "artifact_sha256": dict(sorted(inventory.items())),
        "repo_pins": pins,
    }


def load_corpus(corpus_dir: Path) -> list[dict[str, Any]]:
    """Return unchanged task records only after every pinned input validates."""
    return _validate(corpus_dir)[0]


def corpus_identity(corpus_dir: Path) -> dict[str, Any]:
    """Revalidate and return manifest/artifact digests and verified git pins."""
    return _validate(corpus_dir)[1]
