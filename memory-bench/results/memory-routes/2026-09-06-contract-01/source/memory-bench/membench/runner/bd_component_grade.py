"""Run the frozen post-session grader in an offline Bubblewrap namespace."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from membench.runner import bd_real_runtime as runtime


def _json(path: Path, value: dict[str, Any]) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _grader_inventory(directory: Path) -> dict[str, str]:
    if not directory.is_absolute() or not directory.is_dir() or directory.is_symlink():
        raise ValueError("Grader must be an absolute, real frozen directory")
    inventory = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Grader assets cannot contain symlinks")
        if path.is_file():
            inventory[str(path.relative_to(directory))] = _hash(path)
    if "grade.py" not in inventory:
        raise ValueError("Frozen grade.py is required")
    return inventory


def _extract(snapshot: Path, cwd: Path) -> None:
    if snapshot.is_symlink() or not snapshot.is_file():
        raise ValueError("Snapshot must be a real file")
    with tarfile.open(snapshot) as archive:
        archive.extractall(cwd, filter="data")
    for path in cwd.rglob("*"):
        if path.is_symlink() and not path.resolve().is_relative_to(cwd):
            raise ValueError("Snapshot symlink escapes candidate")


def _setup(
    root: Path, grader: Path, python: Path, bd: Path, out: Path
) -> tuple[list[str], dict[str, str]]:
    cwd, config, shim = root / "candidate", root / "config", root / "bin"
    for path in (cwd, config, shim):
        path.mkdir(exist_ok=True)
    python, bd = runtime._executable(python), runtime._executable(bd)
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise ValueError("Bubblewrap is required for candidate grading")
    mounts = (*runtime._mounts(python, python, bd), (grader, grader))
    base = runtime._base_argv(bwrap, mounts, root, cwd)
    base.remove("--share-net")
    env = runtime._environment(
        {"PATH": str(shim), "LANG": "C.UTF-8", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        root=root,
        cwd=cwd,
        config=config,
        agent_python=python,
        cli=python,
        bd=bd,
        python_path=str(cwd / "lib"),
    )
    probe = subprocess.run(
        [*base, "--", "/bin/true"], env=env, text=True, capture_output=True, check=False, timeout=10
    )
    _json(
        out / "namespace-probe.json",
        {"returncode": probe.returncode, "stdout": probe.stdout, "stderr": probe.stderr},
    )
    if probe.returncode != 0:
        raise RuntimeError("Grader namespace probe failed")
    argv = [*base, "--", str(python), "-I", str(grader / "grade.py"), str(cwd)]
    _json(
        out / "runtime.json",
        {
            "schema": "bd-component-grade-runtime.v1",
            "argv": argv,
            "network": "isolated",
            "readonly_mounts": [{"source": str(a), "destination": str(b)} for a, b in mounts],
            "writable_root": str(root),
            "environment": env,
            "executable_sha256": {str(p): _hash(p) for p in (python, bd, Path(bwrap))},
        },
    )
    return argv, env


def _text(value: str | bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def _run(argv: list[str], env: dict[str, str], out: Path, timeout: float) -> dict[str, Any]:
    try:
        process = subprocess.run(
            argv, env=env, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as error:
        (out / "stdout.txt").write_text(_text(error.stdout))
        (out / "stderr.txt").write_text(_text(error.stderr))
        _json(out / "process.json", {"status": "timeout", "timeout_s": timeout})
        raise
    (out / "stdout.txt").write_text(process.stdout)
    (out / "stderr.txt").write_text(process.stderr)
    _json(out / "process.json", {"status": "exited", "returncode": process.returncode})
    payload = json.loads(process.stdout)
    if not isinstance(payload, dict) or payload.get("status") not in {"pass", "fail", "error"}:
        raise ValueError("Grader returned invalid JSON status")
    expected = 0 if payload["status"] == "pass" else 1
    if process.returncode != expected:
        raise ValueError("Grader JSON status disagrees with process exit")
    return {"status": payload["status"], "grader": payload, "returncode": process.returncode}


def grade_snapshot(
    snapshot: Path,
    grader_dir: Path,
    agent_python: Path,
    bd_binary: Path,
    out: Path,
    timeout_s: float = 180,
) -> dict[str, Any]:
    """Grade one immutable snapshot; preserve infrastructure errors separately from failure."""
    if out.resolve().is_relative_to(grader_dir.resolve()):
        raise ValueError("External evidence cannot reside in grader mount")
    if out.exists() or out.is_symlink():
        raise ValueError("Grader output exists; do not overwrite evidence")
    out.mkdir(parents=True)
    try:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("Grader timeout must be finite and positive")
        grader = grader_dir.absolute()
        inventory = _grader_inventory(grader)
        _json(
            out / "inputs.json",
            {
                "snapshot": str(snapshot),
                "snapshot_sha256": _hash(snapshot),
                "grader_dir": str(grader),
                "grader_sha256": inventory,
            },
        )
        with tempfile.TemporaryDirectory(prefix="bd-component-grade-") as temporary:
            root = Path(temporary)
            cwd = root / "candidate"
            cwd.mkdir()
            _extract(snapshot, cwd)
            argv, env = _setup(root, grader, agent_python, bd_binary, out)
            result = _run(argv, env, out, timeout_s)
        if _grader_inventory(grader) != inventory:
            raise ValueError("Frozen grader changed during execution")
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.TimeoutExpired,
        tarfile.TarError,
    ) as error:
        result = {"status": "error", "error_type": type(error).__name__, "error": str(error)}
    _json(out / "result.json", result)
    return result
