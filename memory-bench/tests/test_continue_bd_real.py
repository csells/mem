"""Explicit timeout reconciliation never turns failure into completion or retries it."""

from __future__ import annotations

import importlib.util
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

from membench.runner import bd_real_experiment as experiment
from membench.runner.resume_cache import digest

spec = importlib.util.spec_from_file_location(
    "continue_bd_real", Path(__file__).parents[1] / "scripts/continue_bd_real.py"
)
assert spec and spec.loader
continuation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(continuation)


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, dict[str, Any], Path]:
    out = tmp_path / "pilot"
    amendment = tmp_path / "AMENDMENT.md"
    amendment.write_text("Continue untouched pairs; preserve observed goal timeout without retry.")
    tasks = [{"task_id": "task"}]
    plan = experiment.build_manifest(
        tasks,
        corpus_sha256="a" * 64,
        model="test",
        cli_version="test",
        bd_identity={"path": "/bd", "sha256": "b" * 64, "version": "test"},
        source="frozen",
        timeout_s=300,
        seed=1,
    )
    experiment.freeze(out, plan)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "manifest.json").write_text("{}")
    package = tmp_path / "membench"
    package.mkdir()
    (package / "module.py").write_text("# fixture")
    monkeypatch.setattr(continuation, "PACKAGE_ROOT", package)
    for kind, base in (("harness", package), ("corpus", corpus)):
        archive = out / f"{kind}-source.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            for path in base.rglob("*"):
                if path.is_file():
                    bundle.write(
                        path, str(path.relative_to(base.parent if kind == "harness" else base))
                    )
        write(
            out / f"{kind}-source-sha256.json",
            {"archive_sha256" if kind == "harness" else "sha256": continuation._hash(archive)},
        )
    monkeypatch.setattr(continuation, "load_corpus", lambda path: tasks)
    monkeypatch.setattr(continuation, "_identity_check", lambda *args: lambda: None)
    pair = plan["schedule"][1]
    directory = experiment._directory(out, pair)
    write(directory / "started.json", {"pair": pair, "manifest_digest": digest(plan)})
    write(
        directory / "halt.json",
        {"type": "RuntimeError", "error": "leg 1 timeout; evidence retained"},
    )
    for leg in (0, 1):
        folder = directory / "run" / f"leg-{leg}"
        for name in ("argv.json", "receipts.json", "settings.json", "native-hook.json"):
            write(folder / name, {})
        (folder / "raw.stream.jsonl").write_text("partial" if leg else "establish")
        (folder / "stderr.txt").write_text("")
        write(
            folder / "process.json",
            {"status": "timeout" if leg else "ok", "returncode": None if leg else 0},
        )
        write(
            folder / "result.json",
            {
                "leg": leg,
                "status": "timeout" if leg else "ok",
                "integrity_errors": ["missing_or_failed_terminal_result"] if leg else [],
                "terminal_result": {} if leg else {"is_error": False},
            },
        )
        for name in (f"leg-{leg}-input-files.json", f"leg-{leg}-output-files.json"):
            write(directory / "run" / name, {})
        for name in (f"leg-{leg}-input.tar", f"leg-{leg}-bd-store.tar"):
            with tarfile.open(directory / "run" / name, "w"):
                pass
    for name in ("establish-output.tar", "goal-candidate.tar"):
        with tarfile.open(directory / "run" / name, "w"):
            pass
    return out, amendment, plan, directory


def persist_pair(task: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    out = kwargs["out"]
    pair = json.loads((out.parent / "started.json").read_text())["pair"]
    result = {**pair, "legs": [{"leg": leg, "status": "ok"} for leg in (0, 1)]}
    for leg, record in enumerate(result["legs"]):
        for name in ("raw.stream.jsonl", "receipts.json", "argv.json", "process.json"):
            write(out / f"leg-{leg}" / name, {})
        write(out / f"leg-{leg}/result.json", record)
    for name in ("result.json", "task_check.json"):
        write(out / name, result if name == "result.json" else {"passed": True})
    (out / "goal-candidate.tar").write_bytes(b"fixture")
    return result


def test_reconciliation_skips_timeout_and_completed_without_rebuy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, amendment, plan, failed = fixture(tmp_path, monkeypatch)
    first = plan["schedule"][0]
    experiment._run_pair(
        experiment._directory(out, first), first, {"task_id": "task"}, plan, tmp_path, persist_pair
    )
    continuation.reconcile(
        out, corpus_dir=tmp_path / "corpus", amendment=amendment, pair_key=failed.name
    )
    assert not (failed / "cell.json").exists()
    before = (failed / "run/leg-1/raw.stream.jsonl").read_bytes()
    calls = []

    def runner(task: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["out"].parent.name)
        return persist_pair(task, **kwargs)

    result = continuation.fire(
        out, corpus_dir=tmp_path / "corpus", amendment=amendment, max_pairs=4, pair_runner=runner
    )
    assert result["new_pairs"] == 2 and failed.name not in calls
    assert (failed / "run/leg-1/raw.stream.jsonl").read_bytes() == before
    assert (
        continuation.fire(
            out,
            corpus_dir=tmp_path / "corpus",
            amendment=amendment,
            max_pairs=4,
            pair_runner=runner,
        )["new_pairs"]
        == 0
    )


@pytest.mark.parametrize("fault", ["raw", "status", "archive", "unknown"])
def test_ambiguous_or_changed_evidence_blocks_all_purchase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    out, amendment, plan, failed = fixture(tmp_path, monkeypatch)
    continuation.reconcile(
        out, corpus_dir=tmp_path / "corpus", amendment=amendment, pair_key=failed.name
    )
    if fault == "raw":
        (failed / "run/leg-1/raw.stream.jsonl").write_text("changed")
    if fault == "status":
        write(failed / "run/leg-1/process.json", {"status": "error", "returncode": None})
    if fault == "archive":
        (failed / "run/goal-candidate.tar").unlink()
    if fault == "unknown":
        experiment._directory(out, plan["schedule"][-1]).mkdir()
    with pytest.raises((ValueError, RuntimeError)):
        continuation.fire(
            out,
            corpus_dir=tmp_path / "corpus",
            amendment=amendment,
            max_pairs=1,
            pair_runner=lambda *args, **kwargs: pytest.fail("must not spend"),
        )


@pytest.mark.parametrize(
    "name",
    [
        "harness-source.zip",
        "corpus-source.zip",
        "harness-source-sha256.json",
        "corpus-source-sha256.json",
    ],
)
def test_missing_frozen_archive_refuses_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    out, amendment, _, failed = fixture(tmp_path, monkeypatch)
    (out / name).unlink()
    with pytest.raises(ValueError, match="archive"):
        continuation.reconcile(
            out, corpus_dir=tmp_path / "corpus", amendment=amendment, pair_key=failed.name
        )
    assert not (failed / continuation.FAILURE_RECORD).exists()


def test_changed_archive_with_updated_sidecar_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, amendment, _, failed = fixture(tmp_path, monkeypatch)
    archive = out / "corpus-source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("manifest.json", "wrong bytes")
    write(out / "corpus-source-sha256.json", {"sha256": continuation._hash(archive)})
    with pytest.raises(ValueError, match="contents"):
        continuation.reconcile(
            out, corpus_dir=tmp_path / "corpus", amendment=amendment, pair_key=failed.name
        )


def test_changed_amendment_and_identity_block_fire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, amendment, _, failed = fixture(tmp_path, monkeypatch)
    continuation.reconcile(
        out, corpus_dir=tmp_path / "corpus", amendment=amendment, pair_key=failed.name
    )
    amendment.write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        continuation.fire(
            out,
            corpus_dir=tmp_path / "corpus",
            amendment=amendment,
            pair_runner=lambda *args, **kwargs: pytest.fail("must not spend"),
        )


def test_new_failure_stops_without_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out, amendment, _, failed = fixture(tmp_path, monkeypatch)
    continuation.reconcile(
        out, corpus_dir=tmp_path / "corpus", amendment=amendment, pair_key=failed.name
    )
    calls = []

    def runner(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["out"])
        raise RuntimeError("new failure")

    with pytest.raises(RuntimeError, match="new failure"):
        continuation.fire(
            out,
            corpus_dir=tmp_path / "corpus",
            amendment=amendment,
            max_pairs=6,
            pair_runner=runner,
        )
    with pytest.raises(ValueError, match="reconciliation"):
        continuation.fire(
            out,
            corpus_dir=tmp_path / "corpus",
            amendment=amendment,
            max_pairs=6,
            pair_runner=runner,
        )
    assert len(calls) == 1
