"""Whole-agent filesystem/process isolation using the installed Bubblewrap runtime.

Provider networking is shared intentionally. Host source, gold artifacts, process
roots and credentials are not filesystem mounts. Only the supplied pair root is
writable persistently; runtime evidence is written outside it before agent execution.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from membench.spawn import Runner

PLATFORM_DIRS = ("/usr", "/bin", "/lib", "/lib64", "/etc")


def _executable(path: Path) -> Path:
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"required absolute executable unavailable: {path}")
    return path


def _contained(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_dir() or not resolved.is_relative_to(root):
        raise ValueError("runtime directory must be inside pair root")
    return resolved


def _python_mount(python: Path) -> tuple[Path, Path] | None:
    prefix = python.parent.parent
    if (prefix / "pyvenv.cfg").is_file():
        return prefix.resolve(), prefix
    if not python.resolve().is_relative_to("/usr"):
        raise ValueError("Python requires a venv or the mounted platform runtime")
    return None


def _mounts(cli: Path, agent_python: Path, bd: Path) -> tuple[tuple[Path, Path], ...]:
    dolt = shutil.which("dolt")
    if not dolt:
        raise ValueError("dolt executable required for isolated bd")
    package = Path(__file__).resolve().parents[1]
    resolver = Path("/etc/resolv.conf").resolve(strict=True)
    if not resolver.is_file():
        raise ValueError("resolver configuration must be a readable file")
    candidates = [
        (cli.resolve(), cli),
        (bd.resolve(), bd),
        (Path(dolt).resolve(), Path(dolt)),
        (package, package),
        (resolver, resolver),
    ]
    for python in (agent_python, Path(sys.executable)):
        mount = _python_mount(_executable(python))
        if mount is not None:
            candidates.append(mount)
    unique = {str(destination): (source, destination) for source, destination in candidates}
    directories = [destination for source, destination in unique.values() if source.is_dir()]
    return tuple(
        (source, destination)
        for _, (source, destination) in sorted(unique.items())
        if source.is_dir()
        or not any(
            destination.is_relative_to(directory)
            for directory in [*directories, Path("/usr"), Path("/bin")]
        )
    )


def _base_argv(bwrap: str, mounts: Sequence[tuple[Path, Path]], root: Path, cwd: Path) -> list[str]:
    argv = [
        bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--share-net",
        "--cap-drop",
        "ALL",
    ]
    for path in PLATFORM_DIRS:
        if not Path(path).is_dir():
            raise ValueError(f"platform directory unavailable: {path}")
        argv.extend(("--ro-bind", path, path))
    argv.extend(("--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/home"))
    for source, destination in mounts:
        argv.extend(("--ro-bind", str(source), str(destination)))
    argv.extend(
        (
            "--bind",
            str(root),
            str(root),
            "--chdir",
            str(cwd),
            "--remount-ro",
            "/tmp",
            "--remount-ro",
            "/home",
            "--remount-ro",
            "/",
        )
    )
    return argv


def _environment(
    original: dict[str, str],
    *,
    root: Path,
    cwd: Path,
    config: Path,
    agent_python: Path,
    cli: Path,
    bd: Path,
    python_path: str,
) -> dict[str, str]:
    first = Path(original.get("PATH", "").split(os.pathsep)[0])
    shim = _contained(first, root)
    home = config / "home"
    home.mkdir(exist_ok=True)
    bd_config = home / ".config" / "bd"
    bd_config.mkdir(parents=True, exist_ok=True)
    (bd_config / "config.yaml").write_text("metrics:\n  disabled: true\n  notice_shown: true\n")
    temporary = config / "tmp"
    temporary.mkdir(exist_ok=True)
    path = list(
        dict.fromkeys(
            (
                str(shim),
                str(agent_python.parent),
                str(cli.parent),
                str(bd.parent),
                str(Path(shutil.which("dolt") or "").parent),
                "/usr/bin",
                "/bin",
            )
        )
    )
    return {
        **original,
        "HOME": str(home),
        "TMPDIR": str(temporary),
        "PWD": str(cwd),
        "CLAUDE_CONFIG_DIR": str(config),
        "PYTHONPATH": python_path,
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": os.pathsep.join(path),
    }


def _write_record(
    path: Path,
    argv: list[str],
    env: dict[str, str],
    mounts: Sequence[tuple[Path, Path]],
    python: Path,
    cli: Path,
    bd: Path,
) -> None:
    identities = {
        str(executable): hashlib.sha256(executable.read_bytes()).hexdigest()
        for executable in (python, cli, bd, Path(argv[0]))
    }
    body = {
        "schema": "bd-real-runtime.v1",
        "argv": argv,
        "network": "host-shared",
        "namespace_probe_returncode": 0,
        "readonly_mounts": [{"source": str(src), "destination": str(dst)} for src, dst in mounts],
        "executable_sha256": identities,
        "environment": {
            key: env[key]
            for key in (
                "HOME",
                "TMPDIR",
                "PWD",
                "CLAUDE_CONFIG_DIR",
                "PATH",
                "PYTHONPATH",
                "PYTHONNOUSERSITE",
            )
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as target:
        target.write(json.dumps(body, indent=2) + "\n")


def _candidate_pythonpath(cwd: Path, paths: tuple[str, ...]) -> str:
    if not isinstance(paths, tuple) or not paths:
        raise ValueError("Python import roots must be a nonempty tuple")
    for name in paths:
        if (
            not isinstance(name, str)
            or not name
            or os.pathsep in name
            or Path(name).is_absolute()
            or ".." in Path(name).parts
            or not (cwd / name).resolve().is_relative_to(cwd)
        ):
            raise ValueError("Python import roots must stay inside the candidate")
    return os.pathsep.join(str(cwd / name) for name in paths)


def wrap_agent_runner(
    inner: Runner,
    *,
    pair_root: Path,
    cwd: Path,
    agent_python: Path,
    bd_binary: Path,
    config_dir: Path,
    record_path: Path,
    python_paths: tuple[str, ...] = ("src",),
) -> Runner:
    """Validate dependencies, probe isolation, then invoke the actual runner inside it.

    The inner runner should preserve argv/streams outside pair_root. No fallback to
    an unsandboxed call exists. This wrapper never invokes a provider during probing.
    """
    root = pair_root.resolve(strict=True)
    if root in {Path(path) for path in (*PLATFORM_DIRS, "/", "/home", "/tmp", "/var")}:
        raise ValueError("runtime requires a dedicated pair root")
    cwd, config = _contained(cwd, root), _contained(config_dir, root)
    python_path = _candidate_pythonpath(cwd, python_paths)
    python, bd = _executable(agent_python), _executable(bd_binary)
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise ValueError("Bubblewrap is required; unsandboxed execution refused")
    if not isinstance(record_path, Path):
        raise ValueError("record_path must name external runtime evidence")
    record = record_path.resolve()
    if record.is_relative_to(root):
        raise ValueError("runtime evidence must stay outside pair root")

    def run(argv: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if not argv or not isinstance(kwargs.get("env"), dict):
            raise ValueError("agent argv and explicit environment required")
        if Path(kwargs.get("cwd", "")).resolve() != cwd:
            raise ValueError("agent cwd differs from isolated candidate")
        environment = kwargs["env"]
        found = shutil.which(argv[0], path=environment.get("PATH"))
        if not found:
            raise ValueError("agent executable unavailable")
        cli = _executable(Path(found).absolute())
        mounts = _mounts(cli, python, bd)
        if any(
            source.is_relative_to(root) or destination.is_relative_to(root)
            for source, destination in mounts
        ):
            raise ValueError("dedicated pair root cannot contain host runtime dependencies")
        base = _base_argv(bwrap, mounts, root, cwd)
        env = _environment(
            environment,
            root=root,
            cwd=cwd,
            config=config,
            agent_python=python,
            cli=cli,
            bd=bd,
            python_path=python_path,
        )
        probe = subprocess.run(
            [*base, "--", "/bin/true"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if probe.returncode != 0:
            raise RuntimeError(f"filesystem namespace probe failed: {probe.stderr.strip()}")
        wrapped = [*base, "--", str(cli), *argv[1:]]
        _write_record(record, wrapped, env, mounts, python, cli, bd)
        return inner(wrapped, **{**kwargs, "env": env})

    return run
