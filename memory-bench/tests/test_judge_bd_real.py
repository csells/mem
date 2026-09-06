"""Blinded semantic review plumbing, with fake CLI responses only."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/judge_bd_real.py"
spec = importlib.util.spec_from_file_location("judge_bd_real", SCRIPT)
assert spec and spec.loader
judge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(judge)


@pytest.fixture(autouse=True)
def stub_corpus_git_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        judge,
        "corpus_identity",
        lambda root: {"manifest_sha256": judge._hash(root / "manifest.json")},
    )


def seal_experiment(root: Path, corpus: Path) -> None:
    from membench.runner.bd_real_experiment import _evidence_inventory

    pair = {"task_id": "task", "condition": "current", "variant": "unbriefed"}
    manifest = {"schedule": [pair], "corpus_sha256": judge._hash(corpus / "manifest.json")}
    (root / "manifest.json").write_text(json.dumps(manifest))
    directory = judge._directory(root, pair)
    old = root / "pairs/current-task-unbriefed"
    if old.exists():
        old.rename(directory)
    identity = {"pair": pair, "manifest_digest": judge.digest(manifest)}
    (directory / "started.json").write_text(json.dumps(identity))
    run = directory / "run"
    result = json.loads((run / "result.json").read_text())
    for leg, record in enumerate(result["legs"]):
        record.update({"leg": leg, "status": "ok"})
        folder = run / f"leg-{leg}"
        folder.mkdir(exist_ok=True)
        for name in ("raw.stream.jsonl", "receipts.json", "argv.json", "process.json"):
            (folder / name).write_text("{}")
        (folder / "result.json").write_text(json.dumps(record))
    (run / "result.json").write_text(json.dumps(result))
    (run / "task_check.json").write_text(json.dumps(result["task_check"]))
    (run / "goal-candidate.tar").write_bytes(b"test-only")
    cell = {**identity, "result": result, "artifact_sha256": _evidence_inventory(directory, result)}
    (directory / "cell.json").write_text(json.dumps(cell))


def prepared(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root, corpus, out = tmp_path / "experiment", tmp_path / "corpus", tmp_path / "judge"
    run = root / "pairs/current-task-unbriefed/run"
    run.mkdir(parents=True)
    corpus.mkdir()
    (root / "JUDGE_PROTOCOL.md").write_text(
        "Frozen source-only fidelity and initial-task relevance."
    )
    (corpus / "source.md").write_text("Source: count measured input tokens.")
    (corpus / "goal.md").write_text("Add a report of token counts.")
    (corpus / "manifest.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_id": "task",
                        "artifacts": {
                            "source_packet": {"path": "source.md"},
                            "goal_unbriefed": {"path": "goal.md"},
                        },
                    }
                ]
            }
        )
    )
    op = {
        "accepted_write": True,
        "is_read": True,
        "output_observed": True,
        "content": ["Count input tokens."],
        "invocation_id": "private-operation",
    }
    (run / "result.json").write_text(
        json.dumps(
            {
                "task_id": "task",
                "condition": "current",
                "variant": "unbriefed",
                "task_check": {"passed": False},
                "legs": [{"memory": {"operations": [op]}}, {"memory": {"operations": [op]}}],
            }
        )
    )
    seal_experiment(root, corpus)
    judge.prepare(root, corpus, out)
    packet = json.loads((out / "fidelity.packet.json").read_text())
    return out, packet


def test_packets_exclude_treatment_outcome_and_gold(tmp_path: Path) -> None:
    out, packet = prepared(tmp_path)
    assert len(packet["items"]) == 1
    assert set(packet["items"][0]) == {"item_id", "memory_text", "sources"}
    assert packet["items"][0]["sources"] == [
        {"source_id": "S1", "text": "Source: count measured input tokens."}
    ]
    text = json.dumps(packet)
    for forbidden in ("condition", "task_check", "private-operation", "current-task", "unbriefed"):
        assert forbidden not in text
    relevance = json.loads((out / "relevance.packet.json").read_text())
    assert relevance["items"][0]["sources"][0]["text"] == "Add a report of token counts."
    assert json.loads((out / "mapping.json").read_text())


def verdict(packet: dict[str, Any]) -> dict[str, Any]:
    item = packet["items"][0]
    return {
        "judgments": [
            {
                "item_id": item["item_id"],
                "label": "faithful",
                "claims": [
                    {
                        "claim": "Matches source",
                        "support": "supported",
                        "citations": [{"source_id": "S1", "quote": "count measured input tokens"}],
                    }
                ],
            }
        ]
    }


@pytest.mark.parametrize("fault", ["label", "quote", "source", "missing", "extra"])
def test_schema_and_citations_fail_closed(tmp_path: Path, fault: str) -> None:
    _, packet = prepared(tmp_path)
    response = verdict(packet)
    item = response["judgments"][0]
    if fault == "label":
        item["label"] = "perfect"
    if fault == "quote":
        item["claims"][0]["citations"][0]["quote"] = "invented evidence"
    if fault == "source":
        item["claims"][0]["citations"][0]["source_id"] = "gold"
    if fault == "missing":
        response["judgments"] = []
    if fault == "extra":
        item["condition"] = "current"
    with pytest.raises(ValueError):
        judge.validate_response(response, packet)


def test_one_batch_records_raw_usage_and_never_rebuys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, packet = prepared(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-not-real")
    calls: list[list[str]] = []

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv == ["claude", "--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="2.1.261 (Claude Code)\n", stderr="")
        assert argv[argv.index("--tools") + 1] == ""
        assert argv[argv.index("--setting-sources") + 1] == "user"
        settings = json.loads(
            (Path(kwargs["env"]["CLAUDE_CONFIG_DIR"]) / "settings.json").read_text()
        )
        assert settings["autoMemoryEnabled"] is False
        events = [
            {
                "type": "system",
                "subtype": "init",
                "model": judge.MODEL,
                "claude_code_version": judge.CLI_VERSION,
                "session_id": "fake-session",
            },
            {
                "type": "result",
                "is_error": False,
                "result": json.dumps(verdict(packet)),
                "total_cost_usd": 0.01,
                "usage": {"input_tokens": 50},
            },
        ]
        return subprocess.CompletedProcess(
            argv, 0, stdout="\n".join(map(json.dumps, events)), stderr=""
        )

    judge.fire(out, max_batches=1, runner=runner)
    assert len([call for call in calls if "-p" in call]) == 1
    batch = out / "batches/fidelity-0"
    assert (batch / "raw.stream.jsonl").exists()
    assert json.loads((batch / "result.json").read_text())["total_cost_usd"] == 0.01
    (out / "batches/fidelity-1").mkdir()
    (out / "batches/fidelity-1/started.json").write_text("{}")
    with pytest.raises(RuntimeError, match="unfinished"):
        judge.fire(out, max_batches=1, runner=runner)
    assert len([call for call in calls if "-p" in call]) == 1


def test_changed_packet_refuses_spend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out, _ = prepared(tmp_path)
    (out / "fidelity.packet.json").write_text("{}")
    with pytest.raises(RuntimeError, match="changed"):
        judge.fire(out, runner=lambda *args, **kwargs: pytest.fail("must not spawn"))


def test_no_eligible_items_schedules_no_calls(tmp_path: Path) -> None:
    prepared(tmp_path)
    root = tmp_path / "experiment"
    result_path = next(root.glob("pairs/*/run/result.json"))
    result = json.loads(result_path.read_text())
    for leg in result["legs"]:
        leg["memory"]["operations"] = []
    result_path.write_text(json.dumps(result))
    seal_experiment(root, tmp_path / "corpus")
    manifest = judge.prepare(root, tmp_path / "corpus", tmp_path / "empty-judge")
    assert manifest["batches"] == []
    assert set(manifest["empty_axes"]) == {"fidelity", "relevance"}


def test_invalid_cli_judgment_is_retained_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, _ = prepared(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-not-real")
    spawns = []

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="2.1.261 (Claude Code)", stderr="")
        spawns.append(argv)
        events = [
            {
                "type": "system",
                "subtype": "init",
                "model": judge.MODEL,
                "claude_code_version": judge.CLI_VERSION,
                "session_id": "fake",
            },
            {
                "type": "result",
                "is_error": False,
                "result": '{"judgments": []}',
                "total_cost_usd": 0.01,
            },
        ]
        return subprocess.CompletedProcess(
            argv, 0, stdout="\n".join(map(json.dumps, events)), stderr=""
        )

    with pytest.raises(RuntimeError, match="retained"):
        judge.fire(out, runner=runner)
    assert (out / "batches/fidelity-0/error.json").exists()
    assert "total_cost_usd" in (out / "batches/fidelity-0/raw.stream.jsonl").read_text()
    with pytest.raises(RuntimeError, match="unfinished"):
        judge.fire(out, runner=runner)
    assert len(spawns) == 1


def test_partial_result_file_is_not_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, _ = prepared(tmp_path)
    directory = out / "batches/fidelity-0"
    directory.mkdir(parents=True)
    (directory / "started.json").write_text("{}")
    (directory / "result.json").write_text('{"judgments":')
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-not-real")
    with pytest.raises(RuntimeError, match="unfinished"):
        judge.fire(out, runner=lambda *args, **kwargs: pytest.fail("must not spawn"))


def test_later_unfinished_batch_blocks_all_spend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, _ = prepared(tmp_path)
    directory = out / "batches/relevance-1"
    directory.mkdir(parents=True)
    (directory / "started.json").write_text("{}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-not-real")
    with pytest.raises(RuntimeError, match="unfinished"):
        judge.fire(out, runner=lambda *args, **kwargs: pytest.fail("must not spawn"))


def test_empty_completed_inventories_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, _ = prepared(tmp_path)
    for axis in ("fidelity", "relevance"):
        for replicate in range(2):
            directory = out / "batches" / f"{axis}-{replicate}"
            directory.mkdir(parents=True)
            (directory / "completed.json").write_text('{"files":{}}')
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-not-real")
    with pytest.raises(RuntimeError):
        judge.fire(out, runner=lambda *args, **kwargs: pytest.fail("must not spawn"))


def test_prepare_rejects_unscheduled_and_changed_evidence(tmp_path: Path) -> None:
    prepared(tmp_path)
    root, corpus = tmp_path / "experiment", tmp_path / "corpus"
    extra = root / "pairs/unscheduled"
    extra.mkdir()
    with pytest.raises(RuntimeError, match="unscheduled"):
        judge.prepare(root, corpus, tmp_path / "new-judge")
    extra.rmdir()
    stream = next(root.glob("pairs/*/run/leg-0/raw.stream.jsonl"))
    stream.write_text("changed")
    with pytest.raises(ValueError, match="evidence changed"):
        judge.prepare(root, corpus, tmp_path / "new-judge")


def test_prepare_requires_corpus_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared(tmp_path)

    def invalid(root: Path) -> dict[str, Any]:
        raise ValueError("corpus source hash changed")

    monkeypatch.setattr(judge, "corpus_identity", invalid)
    with pytest.raises(ValueError, match="source hash changed"):
        judge.prepare(tmp_path / "experiment", tmp_path / "corpus", tmp_path / "new-judge")


def test_prepare_and_fire_share_output_lock(tmp_path: Path) -> None:
    out, _ = prepared(tmp_path)
    with judge.out_lock(out):
        with pytest.raises(RuntimeError, match="exists"):
            judge.fire(out, runner=lambda *args, **kwargs: pytest.fail("must not spawn"))
        with pytest.raises(RuntimeError, match="exists"):
            judge.prepare(tmp_path / "experiment", tmp_path / "corpus", out)


def reconciled_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    import tarfile
    import zipfile

    prepared(tmp_path)
    root, corpus = tmp_path / "experiment", tmp_path / "corpus"
    module_spec = importlib.util.spec_from_file_location(
        "continuation_fixture", SCRIPT.with_name("continue_bd_real.py")
    )
    assert module_spec and module_spec.loader
    continuation = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(continuation)
    package = tmp_path / "membench"
    package.mkdir()
    (package / "fixture.py").write_text("# pinned harness fixture")
    continuation.PACKAGE_ROOT = package
    monkeypatch.setattr(judge, "_continuation_module", lambda: continuation, raising=False)
    for kind, base in (("harness", package), ("corpus", corpus)):
        archive = root / f"{kind}-source.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            for path in base.rglob("*"):
                if path.is_file():
                    bundle.write(
                        path, str(path.relative_to(base.parent if kind == "harness" else base))
                    )
        (root / f"{kind}-source-sha256.json").write_text(
            json.dumps({"archive_sha256" if kind == "harness" else "sha256": judge._hash(archive)})
        )
    plan = json.loads((root / "manifest.json").read_text())
    pair = plan["schedule"][0]
    directory = judge._directory(root, pair)
    (directory / "cell.json").unlink()
    (directory / "run/result.json").unlink()
    (directory / "run/task_check.json").unlink()
    (directory / "halt.json").write_text(
        json.dumps({"type": "RuntimeError", "error": "leg 1 timeout; evidence retained"})
    )
    for leg in (0, 1):
        folder = directory / "run" / f"leg-{leg}"
        record = json.loads((folder / "result.json").read_text())
        record.update(
            {
                "status": "timeout" if leg else "ok",
                "terminal_result": {} if leg else {"is_error": False},
                "integrity_errors": ["missing_or_failed_terminal_result"] if leg else [],
            }
        )
        (folder / "result.json").write_text(json.dumps(record))
        (folder / "process.json").write_text(
            json.dumps({"status": record["status"], "returncode": None if leg else 0})
        )
        for name in ("stderr.txt", "settings.json", "native-hook.json"):
            (folder / name).write_text("{}")
        for name in (f"leg-{leg}-input-files.json", f"leg-{leg}-output-files.json"):
            (directory / "run" / name).write_text("{}")
        for name in (f"leg-{leg}-input.tar", f"leg-{leg}-bd-store.tar"):
            with tarfile.open(directory / "run" / name, "w"):
                pass
    for name in ("goal-candidate.tar", "establish-output.tar"):
        with tarfile.open(directory / "run" / name, "w"):
            pass
    amendment = root / "TIMEOUT.md"
    amendment.write_text("Explicitly reconcile retained goal timeout; never retry.")
    identity = continuation._identity(root, amendment, corpus)
    (root / continuation.CONTINUATION).write_text(json.dumps(identity))
    record = {
        "schema": "bd-real-terminal-failure.v1",
        "status": "goal_timeout",
        "pair": pair,
        "identity": identity,
        "artifact_sha256": continuation.terminal_inventory(directory, pair, plan),
    }
    (directory / continuation.FAILURE_RECORD).write_text(json.dumps(record))
    return root, corpus, directory


def test_reconciled_timeout_preserves_positive_memory_eligibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, corpus, directory = reconciled_timeout(tmp_path, monkeypatch)
    out = tmp_path / "timeout-judge"
    manifest = judge.prepare(root, corpus, out)
    for axis in ("fidelity", "relevance"):
        packet = json.loads((out / f"{axis}.packet.json").read_text())
        assert len(packet["items"]) == 1
        assert set(packet["items"][0]) == {"item_id", "memory_text", "sources"}
    assert str(directory / "terminal-failure.json") in manifest["input_identity"]["failure_ledgers"]
    assert not (directory / "run/result.json").exists()


@pytest.mark.parametrize("fault", ["changed", "unreconciled", "missing"])
def test_timeout_judging_refuses_changed_or_unaccounted_pairs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    root, corpus, directory = reconciled_timeout(tmp_path, monkeypatch)
    if fault == "changed":
        (directory / "run/leg-1/raw.stream.jsonl").write_text("changed partial")
    if fault == "unreconciled":
        (directory / "terminal-failure.json").unlink()
    if fault == "missing":
        import shutil

        shutil.rmtree(directory)
    with pytest.raises((ValueError, RuntimeError)):
        judge.prepare(root, corpus, tmp_path / "invalid-judge")
