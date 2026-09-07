"""Explicitly triggered, read-only cross-host verification with preserved logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PYTHON = ROOT / ".venv/bin/python"


def write(path: Path, data: object) -> None:
    with path.open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def hashes() -> dict[str, str]:
    paths = [
        path
        for folder in ("membench", "scripts", "tests", "examples")
        for path in (ROOT / folder).rglob("*.py")
    ] + [ROOT / "pyproject.toml"]
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--label", default="gates-01")
    args = parser.parse_args()
    if Path(args.label).name != args.label or args.label in {".", ".."}:
        raise ValueError("Output label must be a new direct child directory")
    scripts = sorted(
        {
            str(path.relative_to(ROOT))
            for pattern in (
                "scripts/memory_hosts_*.py",
                "scripts/memory_lifecycle_*.py",
                "scripts/memory_routes_*.py",
            )
            for path in ROOT.glob(pattern)
        }
    )
    tests = sorted(
        {
            str(path.relative_to(ROOT))
            for pattern in (
                "tests/test_memory_host*.py",
                "tests/test_memory_lifecycle_*.py",
                "tests/test_memory_routes_*.py",
                "tests/test_bd_receipts.py",
                "tests/test_bd_receipt_surface.py",
                "tests/test_native_memory_hook.py",
                "tests/test_bd_real_metrics.py",
            )
            for path in ROOT.glob(pattern)
        }
    )
    if not args.execute:
        print(json.dumps({"not_started": True, "script_files": scripts, "test_files": tests}))
        return
    target = OUT / args.label
    target.mkdir()
    runtime = Path(tempfile.mkdtemp(prefix="memory-hosts-verification-", dir="/private/tmp"))
    for name in ("tmp", "cache", "config"):
        (runtime / name).mkdir()
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {
            "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE",
            "TZ", "TERM", "USERPROFILE", "SYSTEMROOT",
        }
    }
    env.update(
        PATH=f"{ROOT}/.venv/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        TMPDIR=str(runtime / "tmp"), TMP=str(runtime / "tmp"), TEMP=str(runtime / "tmp"),
        XDG_CONFIG_HOME=str(runtime / "config"), XDG_CACHE_HOME=str(runtime / "cache"),
        GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
        RUFF_CACHE_DIR=str(runtime / "cache/ruff"), MYPY_CACHE_DIR=str(runtime / "cache/mypy"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    commands = [
        ("ruff", [str(PYTHON), "-m", "ruff", "check", "."]),
        ("black", [str(PYTHON), "-m", "black", "--check", "."]),
        ("mypy", [str(PYTHON), "-m", "mypy", "--strict"]),
        (
            "scripts-mypy",
            [str(PYTHON), "-m", "mypy", "--strict", "--explicit-package-bases", *scripts],
        ),
        (
            "pytest-collect",
            [str(PYTHON), "-m", "pytest", "--collect-only", "-q", *tests,
             "-o", f"cache_dir={runtime}/cache/pytest"],
        ),
        (
            "pytest",
            [str(PYTHON), "-m", "pytest", "-vv", *tests,
             "--basetemp", str(runtime / "pytest-temp"),
             "-o", f"cache_dir={runtime}/cache/pytest", "--junitxml", str(target / "pytest.xml")],
        ),
    ]
    write(target / "scope.json", {
        "script_files": scripts, "test_files": tests,
        "python": str(PYTHON), "path_policy": env["PATH"],
        "tracked_head": subprocess.check_output(
            ["/usr/bin/git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "runtime_scratch": str(runtime), "no_model_calls": True, "source_mutation": False,
        "prior_verification_preserved": "../verification-lifecycle-2026-09-06-01",
        "excluded_scope": "Unchanged TypeScript and unrelated full Python runtime suite",
    })
    initial = hashes()
    write(target / "source-sha256-before.json", initial)
    results = []
    for index, (name, argv) in enumerate(commands, 1):
        before = hashes()
        start = time.monotonic()
        print(f"[{index}/{len(commands)}] START {name}", flush=True)
        with (target / f"{name}.log").open("x") as log:
            process = subprocess.Popen(
                argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end="", flush=True)
            code = process.wait()
        after = hashes()
        changed = sorted(
            path for path in set(before) | set(after) if before.get(path) != after.get(path)
        )
        detail = {
            "command": argv, "returncode": code, "elapsed_s": time.monotonic() - start,
            "source_hashes_before": before, "source_hashes_after": after,
            "changed_during_check": changed,
        }
        write(target / f"{name}.json", detail)
        results.append({
            "gate": name, "returncode": code, "elapsed_s": detail["elapsed_s"],
            "changed_during_check": changed,
        })
        print(f"[{index}/{len(commands)}] END {name}: exit {code}, source changes {len(changed)}", flush=True)
    final = hashes()
    write(target / "source-sha256-after.json", final)
    write(target / "results.json", {
        "gates": results,
        "changed_during_verification": sorted(
            path for path in set(initial) | set(final) if initial.get(path) != final.get(path)
        ),
    })
    ok = all(row["returncode"] == 0 and not row["changed_during_check"] for row in results)
    print(f"COMPLETE: {sum(row['returncode'] == 0 for row in results)}/{len(commands)} commands passed", flush=True)
    raise SystemExit(0 if ok and initial == final else 1)


if __name__ == "__main__":
    main()
