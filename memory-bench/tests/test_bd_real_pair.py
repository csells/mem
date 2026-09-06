"""Paired lifecycle tests; no bd or model execution."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from membench.runner import bd_real_pair as pair
from membench.runner.tool_surface import MemoryToolSurface


@pytest.fixture(autouse=True)
def fake_runtime_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    def wrap(inner: Any, **context: Any) -> Any:
        context["record_path"].write_text('{"runtime":"explicit-unit-test-double"}')
        return inner

    monkeypatch.setattr(pair, "wrap_agent_runner", wrap, raising=False)


def fixture_task(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ("init",),
        ("config", "user.email", "test@example.invalid"),
        ("config", "user.name", "test"),
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    (repo / "base.py").write_text("base\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    artifacts = {}
    for name in ("source_packet", "establish_prompt", "goal_unbriefed", "goal_briefed"):
        (corpus / f"{name}.md").write_text(name)
        artifacts[name] = {"path": f"{name}.md"}
    grader = corpus / "grader-assets/task/tests/check.py.txt"
    grader.parent.mkdir(parents=True)
    grader.write_text("withheld\n")
    return {
        "task_id": "task",
        "repo_absolute": str(repo),
        "base_commit": commit,
        "artifacts": artifacts,
        "grader": {
            "modules": [
                {"path": "grader-assets/task/tests/check.py.txt", "target_path": "tests/check.py"}
            ],
            "check_command": ["fake-python", "-m", "pytest"],
        },
    }, corpus


def fake_surface(root: Path, **_: Any) -> MemoryToolSurface:
    store, bin_dir = root / "store", root / "bin"
    store.mkdir(parents=True)
    bin_dir.mkdir()
    return MemoryToolSurface(
        store_dir=store,
        bin_dir=bin_dir,
        bd_binary="/fake/bd",
        bd_context={"AGENTS.md": "bd deployment"},
    )


@pytest.mark.parametrize("snapshot_failure", [False, True])
def test_timeout_snapshot_completion_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, snapshot_failure: bool
) -> None:
    root, cwd, out = (tmp_path / name for name in ("root", "cwd", "out"))
    cwd.mkdir()
    out.mkdir()
    surface = fake_surface(root)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task")

    def failed_leg(**kwargs: Any) -> Any:
        raise RuntimeError("agent timeout")

    original = pair._snapshot

    def snapshot(path: Path, target: Path) -> dict[str, str]:
        if snapshot_failure and target.name.endswith("bd-store.tar"):
            target.write_bytes(b"partial archive")
            raise RuntimeError("snapshot failure")
        return original(path, target)

    monkeypatch.setattr(pair, "_leg", failed_leg)
    monkeypatch.setattr(pair, "_snapshot", snapshot)
    with pytest.raises(RuntimeError, match="snapshot failure" if snapshot_failure else "timeout"):
        pair._run_snapshotted_leg(
            cwd=cwd,
            surface=surface,
            condition="current",
            out=out,
            leg=0,
            root=root,
            corpus_dir=tmp_path,
            artifacts={"prompt": {"path": "prompt.md"}},
            prompt_key="prompt",
            model="test",
            cli_version="test",
            timeout_s=1,
            agent_python=Path("/usr/bin/python3"),
        )
    marker = out / "leg-0-snapshots.json"
    if snapshot_failure:
        assert not marker.exists()
    else:
        assert json.loads(marker.read_text()) == {"completed": True}


def test_pair_keeps_only_bd_and_withholds_grader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, corpus = fixture_task(tmp_path)
    calls: list[tuple[Path, Path]] = []

    def agent_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cwd, config = Path(kwargs["cwd"]), Path(kwargs["env"]["CLAUDE_CONFIG_DIR"])
        calls.append((cwd, config))
        assert kwargs["env"]["PWD"] == str(cwd)
        assert (config / "CLAUDE.md").read_bytes() == (cwd / "CLAUDE.md").read_bytes()
        assert pair.COMMON_R4 in (config / "CLAUDE.md").read_text()
        assert "--setting-sources" in argv and argv[argv.index("--setting-sources") + 1] == "user"
        assert "--include-hook-events" in argv
        assert not (cwd / ".git").exists()
        assert not (cwd / "tests/check.py").exists()
        store = config.parent / "store"
        if len(calls) == 1:
            assert (cwd / "source_packet.md").exists() and not (cwd / "base.py").exists()
            (cwd / "leftover").write_text("prior")
            (config.parent.parent / "sibling-carryover").write_text("must disappear")
            (config.parent / "extra-memory-file").write_text("must disappear")
            (config.parent / "bin/extra-tool").write_text("must disappear")
            (config / "native.txt").write_text("prior native")
            (store / "saved").write_text("persistent bd")
        else:
            assert (cwd / "base.py").read_text() == "base\n"
            assert not (cwd / "leftover").exists()
            assert not (config.parent.parent / "sibling-carryover").exists()
            assert not (config.parent / "extra-memory-file").exists()
            assert not (config.parent / "bin/extra-tool").exists()
            assert not (cwd / "source_packet.md").exists()
            assert not (config / "native.txt").exists()
            assert (store / "saved").exists()
            (cwd / "base.py").write_text("candidate\n")
        stream = (
            json.dumps(
                {
                    "type": "system",
                    "subtype": "init",
                    "claude_code_version": "test-cli",
                    "model": "test-model",
                    "session_id": str(len(calls)),
                }
            )
            + "\n"
        )
        stream += json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.01}) + "\n"
        return subprocess.CompletedProcess(argv, 0, stdout=stream, stderr="")

    def check_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cwd = Path(kwargs["cwd"])
        assert (cwd / "tests/check.py").read_text() == "withheld\n"
        assert (cwd / "base.py").read_text() == "candidate\n"
        return subprocess.CompletedProcess(argv, 1, stdout="behavior failed", stderr="")

    monkeypatch.setattr(pair, "provision_memory_tool", fake_surface)
    monkeypatch.setattr(pair, "AGENT_RUNNER", agent_runner)
    monkeypatch.setattr(pair, "CHECK_RUNNER", check_runner)
    monkeypatch.setattr(pair, "assert_managed_settings_absent", lambda: None)
    out = tmp_path / "out"
    result = pair.run_real_pair(
        task,
        corpus_dir=corpus,
        out=out,
        condition="current",
        variant="unbriefed",
        model="test-model",
        cli_version="test-cli",
        bd_binary="/fake/bd",
        timeout_s=10,
    )
    assert len(calls) == 2 and calls[0][0] == calls[1][0] and calls[0][1] != calls[1][1]
    assert result["task_check"]["passed"] is False
    assert (out / "goal-candidate.tar").exists()
    assert (out / "leg-0/raw.stream.jsonl").exists()
    assert (out / "leg-1/receipts.json").exists()


def test_timeout_keeps_partial_stream_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, corpus = fixture_task(tmp_path)
    calls = []

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        raise subprocess.TimeoutExpired(
            argv, 1, output="partial evidence", stderr="bounded timeout"
        )

    monkeypatch.setattr(pair, "provision_memory_tool", fake_surface)
    monkeypatch.setattr(pair, "AGENT_RUNNER", runner)
    monkeypatch.setattr(pair, "assert_managed_settings_absent", lambda: None)
    out = tmp_path / "out"
    with pytest.raises(RuntimeError):
        pair.run_real_pair(
            task,
            corpus_dir=corpus,
            out=out,
            condition="current",
            variant="unbriefed",
            model="test",
            cli_version="test-cli",
            bd_binary="/fake/bd",
            timeout_s=1,
        )
    assert len(calls) == 1
    assert (out / "leg-0/raw.stream.jsonl").read_text() == "partial evidence"
    assert json.loads((out / "leg-0/result.json").read_text())["status"] == "timeout"


@pytest.mark.parametrize(
    "event",
    [
        {"type": "system", "subtype": "hook_started", "hook_event": "SessionStart"},
        {"type": "system", "subtype": "hook_response", "hook_event": "SessionEnd"},
    ],
)
def test_unexpected_lifecycle_hook_is_rejected(event: dict[str, Any]) -> None:
    assert pair._unexpected_hooks(json.dumps(event))
    assert not pair._unexpected_hooks(json.dumps({**event, "hook_event": "PreToolUse"}))


@pytest.mark.parametrize("fault", ["version", "terminal", "hook", "receipt"])
def test_integrity_failure_is_saved_and_stops_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    task, corpus = fixture_task(tmp_path)
    calls = []

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        config = Path(kwargs["env"]["CLAUDE_CONFIG_DIR"])
        events: list[dict[str, Any]] = [
            {
                "type": "system",
                "subtype": "init",
                "claude_code_version": "wrong" if fault == "version" else "test-cli",
            },
            {"type": "result", "is_error": fault == "terminal"},
        ]
        if fault == "hook":
            events.append(
                {"type": "system", "subtype": "hook_started", "hook_event": "SessionStart"}
            )
        if fault == "receipt":
            import hashlib

            identity = hashlib.sha256(str(config.resolve()).encode()).hexdigest()[:16]
            (config / f"bd-{identity}-leg-0.jsonl").write_text(
                '{"instrumentation_error":"unattributed prime"}\n'
            )
        return subprocess.CompletedProcess(
            argv, 0, stdout="\n".join(json.dumps(event) for event in events), stderr=""
        )

    monkeypatch.setattr(pair, "provision_memory_tool", fake_surface)
    monkeypatch.setattr(pair, "AGENT_RUNNER", runner)
    monkeypatch.setattr(pair, "assert_managed_settings_absent", lambda: None)
    out = tmp_path / "out"
    with pytest.raises(RuntimeError, match="integrity"):
        pair.run_real_pair(
            task,
            corpus_dir=corpus,
            out=out,
            condition="focused",
            variant="briefed",
            model="test",
            cli_version="test-cli",
            bd_binary="/fake/bd",
            timeout_s=1,
        )
    assert len(calls) == 1
    record = json.loads((out / "leg-0/result.json").read_text())
    assert record["status"] == "error" and record["integrity_errors"]
    assert (out / "establish-output.tar").exists()


def test_existing_output_refuses_execution(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="already exists"):
        pair.run_real_pair(
            {},
            corpus_dir=tmp_path,
            out=tmp_path,
            condition="current",
            variant="unbriefed",
            model="test",
            cli_version="test",
            bd_binary="/fake/bd",
            timeout_s=1,
        )


def test_grader_infrastructure_failure_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, corpus = fixture_task(tmp_path)
    cwd = tmp_path / "snapshot"
    cwd.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(
        pair,
        "CHECK_RUNNER",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 2, stdout="collection error", stderr=""
        ),
    )
    with pytest.raises(RuntimeError, match="infrastructure"):
        pair._grade(task, corpus, cwd, out, 1)
    record = json.loads((out / "task_check.json").read_text())
    assert record["passed"] is None and record["returncode"] == 2


@pytest.mark.parametrize("changes", [{"model": "wrong"}, {"session_id": ""}, {"session_id": None}])
def test_init_identity_mismatch_stops_before_goal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changes: dict[str, Any]
) -> None:
    task, corpus = fixture_task(tmp_path)
    calls = []

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        events = [
            {
                "type": "system",
                "subtype": "init",
                "claude_code_version": "test-cli",
                "model": "test",
                "session_id": "session-1",
                **changes,
            },
            {"type": "result", "is_error": False},
        ]
        return subprocess.CompletedProcess(
            argv, 0, stdout="\n".join(map(json.dumps, events)), stderr=""
        )

    monkeypatch.setattr(pair, "provision_memory_tool", fake_surface)
    monkeypatch.setattr(pair, "AGENT_RUNNER", runner)
    monkeypatch.setattr(pair, "assert_managed_settings_absent", lambda: None)
    with pytest.raises(RuntimeError, match="integrity"):
        pair.run_real_pair(
            task,
            corpus_dir=corpus,
            out=tmp_path / "out",
            condition="current",
            variant="unbriefed",
            model="test",
            cli_version="test-cli",
            bd_binary="/fake/bd",
            timeout_s=1,
        )
    assert len(calls) == 1


def test_grader_refuses_external_package_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    task, corpus = fixture_task(tmp_path)
    external = tmp_path / "external"
    package = external / "codeprobe"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    cwd = tmp_path / "candidate"
    cwd.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    task["grader"]["check_command"] = [sys.executable, "-m", "pytest", "--version"]

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        kwargs["env"] = {**kwargs["env"], "PYTHONPATH": str(external)}
        return pair.run_in_session(argv, **kwargs)

    monkeypatch.setattr(pair, "CHECK_RUNNER", runner)
    with pytest.raises(RuntimeError, match="infrastructure"):
        pair._grade(task, corpus, cwd, out, 10)
    assert "outside candidate" in (out / "task-check.stderr").read_text()


def test_grader_records_candidate_import_proof(tmp_path: Path) -> None:
    import sys

    task, corpus = fixture_task(tmp_path)
    cwd = tmp_path / "candidate"
    package = cwd / "src/codeprobe"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    out = tmp_path / "out"
    out.mkdir()
    task["grader"]["check_command"] = [sys.executable, "-m", "pytest", "--version"]
    result = pair._grade(task, corpus, cwd, out, 10)
    assert result["passed"] is True
    stdout = (out / "task-check.stdout").read_text()
    assert "candidate_import_origin" in stdout and "candidate_module_origins" in stdout
    assert str(package / "__init__.py") in stdout


def test_user_scope_instruction_delivery_preserves_bytes(tmp_path: Path) -> None:
    cwd, config, out = (tmp_path / name for name in ("cwd", "config", "out"))
    for directory in (cwd, config, out):
        directory.mkdir()
    original = b"Repository instructions.\n\n" + pair.COMMON_R4.encode() + b"\n"
    (cwd / "CLAUDE.md").write_bytes(original)
    record = pair.deliver_user_instructions(cwd, config, out)
    assert (config / "CLAUDE.md").read_bytes() == original
    assert (cwd / "CLAUDE.md").read_bytes() == original
    assert (out / "instructions.md").read_bytes() == original
    assert record == json.loads((out / "instruction-delivery.json").read_text())
    assert record["setting_sources"] == "user"


@pytest.mark.parametrize("fault", ["missing", "empty", "symlink", "import"])
def test_invalid_instruction_delivery_refuses_before_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    cwd, config = tmp_path / "cwd", tmp_path / "config"
    cwd.mkdir()
    guidance = cwd / "CLAUDE.md"
    if fault == "empty":
        guidance.write_text(" \n")
    if fault == "import":
        guidance.write_text("Load project conventions from @docs/conventions.md\n")
    if fault == "symlink":
        target = tmp_path / "target.md"
        target.write_text("real guidance")
        guidance.symlink_to(target)
    surface = fake_surface(tmp_path / "memory")
    from dataclasses import replace

    surface = replace(surface, config_dir=config)
    monkeypatch.setattr(
        pair, "AGENT_RUNNER", lambda *args, **kwargs: pytest.fail("must not invoke agent")
    )
    with pytest.raises(RuntimeError, match="instruction"):
        pair._leg(
            cwd=cwd,
            surface=surface,
            prompt="task",
            pair_root=tmp_path,
            agent_python=Path("/fake/python"),
            leg=0,
            out=tmp_path / "out",
            model="test",
            cli_version="test-cli",
            timeout_s=1,
        )


def test_runtime_wrapper_records_actual_command_and_task_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, corpus = fixture_task(tmp_path)
    contexts = []

    def wrap(inner: Any, **context: Any) -> Any:
        contexts.append(context)
        assert context["cwd"].is_relative_to(context["pair_root"])
        assert not context["record_path"].is_relative_to(context["pair_root"])
        assert context["agent_python"] == Path(task["grader"]["check_command"][0])
        context["record_path"].write_text('{"runtime":"test-boundary"}')

        def run(argv: Any, **kwargs: Any) -> Any:
            return inner(["test-bwrap", "--", *argv], **kwargs)

        return run

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert argv[0] == "test-bwrap"
        events = [
            {
                "type": "system",
                "subtype": "init",
                "claude_code_version": "test-cli",
                "model": "test",
                "session_id": str(len(contexts)),
            },
            {"type": "result", "is_error": False},
        ]
        return subprocess.CompletedProcess(
            argv, 0, stdout="\n".join(map(json.dumps, events)), stderr=""
        )

    monkeypatch.setattr(pair, "wrap_agent_runner", wrap, raising=False)
    monkeypatch.setattr(pair, "AGENT_RUNNER", runner)
    monkeypatch.setattr(
        pair,
        "CHECK_RUNNER",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout="", stderr=""),
    )
    monkeypatch.setattr(pair, "provision_memory_tool", fake_surface)
    monkeypatch.setattr(pair, "assert_managed_settings_absent", lambda: None)
    out = tmp_path / "out"
    pair.run_real_pair(
        task,
        corpus_dir=corpus,
        out=out,
        condition="current",
        variant="unbriefed",
        model="test",
        cli_version="test-cli",
        bd_binary="/fake/bd",
        timeout_s=1,
    )
    assert len(contexts) == 2
    for leg in (0, 1):
        assert json.loads((out / f"leg-{leg}/argv.json").read_text())[0] == "test-bwrap"
        assert (
            json.loads((out / f"leg-{leg}/runtime.json").read_text())["runtime"] == "test-boundary"
        )


def test_unavailable_runtime_refuses_agent_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, corpus = fixture_task(tmp_path)

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("required isolation unavailable")

    monkeypatch.setattr(pair, "wrap_agent_runner", unavailable, raising=False)
    monkeypatch.setattr(
        pair, "AGENT_RUNNER", lambda *args, **kwargs: pytest.fail("must not call model")
    )
    monkeypatch.setattr(pair, "provision_memory_tool", fake_surface)
    monkeypatch.setattr(pair, "assert_managed_settings_absent", lambda: None)
    with pytest.raises(RuntimeError, match="isolation unavailable"):
        pair.run_real_pair(
            task,
            corpus_dir=corpus,
            out=tmp_path / "out",
            condition="current",
            variant="unbriefed",
            model="test",
            cli_version="test-cli",
            bd_binary="/fake/bd",
            timeout_s=1,
        )
