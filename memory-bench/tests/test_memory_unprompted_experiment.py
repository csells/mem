import json
import sys
from pathlib import Path

import pytest

from membench.runner import memory_unprompted_hosts
from scripts import memory_unprompted_experiment as experiment
from scripts.memory_unprompted_experiment import compare_json, schedule, session_path


def test_complete_schedule_and_checkpoint_denominators() -> None:
    rows = schedule()
    assert len(rows) == 120
    assert len({r["slot"] for r in rows}) == 120
    assert sum(r["phase"] == "checkpoint" for r in rows) == 48
    assert sum(r["mode"] == "normal" for r in rows) == 24
    for host in {r["host"] for r in rows}:
        assert sum(r["host"] == host for r in rows) == 30


def test_completed_or_interrupted_slot_cannot_be_claimed_twice(tmp_path: Path) -> None:
    row = schedule()[0]
    path = session_path(tmp_path, row)
    path.mkdir(parents=True)
    (path / "process.json").write_text(json.dumps({"pid": 999999}))
    with pytest.raises(FileExistsError):
        session_path(tmp_path, row).mkdir()
    assert json.loads((path / "process.json").read_text()) == {"pid": 999999}


def test_exact_artifact_comparison_rejects_boolean_numeric_coercion() -> None:
    assert compare_json('{"enabled": true}', {"enabled": True})
    assert not compare_json('{"enabled": 1}', {"enabled": True})
    assert not compare_json('{"enabled":true,"enabled":false}', {"enabled": False})
    assert not compare_json('prefix {"enabled": true}', {"enabled": True})


def test_task_delivery_contains_business_prompt_and_common_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    family = tmp_path / "business"
    family.mkdir()
    (family / "manifest.json").write_text('{"entrypoint":"main.py"}')
    (family / "tasks.json").write_text(
        json.dumps(
            {
                "common_contract": "Money is integer cents.",
                "tasks": [
                    {"stage": 1, "title": "Add receipts", "prompt": "Return the requested receipt."}
                ],
            }
        )
    )
    monkeypatch.setattr(experiment, "CORPUS", tmp_path)
    _, tasks = experiment.corpus("business")
    assert tasks[0]["body"] == "Money is integer cents.\n\nReturn the requested receipt."


def test_completed_slot_returns_saved_result_without_preparing_a_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = schedule()[0]
    path = session_path(tmp_path, row)
    path.mkdir(parents=True)
    expected = {"slot": row["slot"], "artifact_passed": False}
    (path / "result.json").write_text(json.dumps(expected))
    monkeypatch.setattr(experiment, "setup", lambda *_: pytest.fail("No replacement session"))
    assert experiment.run_session(tmp_path, row, None) == expected


def test_partial_admission_cannot_freeze_unreviewed_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    review = tmp_path / "review.json"
    review.write_text('{"approved":true,"reviewed_sha256":{}}')
    monkeypatch.setattr(experiment, "review_paths", lambda: {"required-task.json"})
    out = tmp_path / "run"
    with pytest.raises(ValueError, match="every corpus"):
        experiment.freeze(out, review)
    assert not out.exists()


def test_complete_result_publication_never_replaces_an_existing_record(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    experiment.write(path, {"result": "original"})
    with pytest.raises(FileExistsError):
        experiment.write(path, {"result": "replacement"})
    assert json.loads(path.read_text()) == {"result": "original"}


def test_change_during_last_slot_cannot_certify_a_frozen_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = {**schedule()[0], "host": "claude"}
    (tmp_path / "manifest.json").write_text(json.dumps({"slots": [row]}))
    monkeypatch.setattr(memory_unprompted_hosts, "MODELS", {"claude": "claude-sonnet-4-6"})
    changed = False

    def check(_: object) -> None:
        if changed:
            raise experiment.FrozenInputsChangedError("Changed during final model call")

    def call(*_: object) -> dict[str, bool]:
        nonlocal changed
        changed = True
        return {"infrastructure_fault": False}

    monkeypatch.setattr(experiment, "assert_frozen", check)
    monkeypatch.setattr(experiment, "run_session", call)
    with pytest.raises(RuntimeError):
        experiment.run_phase(tmp_path, "checkpoint")
    assert not (tmp_path / "phases/checkpoint/completed.json").exists()
    assert (tmp_path / "phases/checkpoint/failed.json").exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="Real macOS isolation profile")
def test_hidden_grader_is_readonly_and_hides_answer_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, local, hidden = (tmp_path / n for n in ("work", "local", "hidden"))
    for p in (workspace, local, hidden):
        p.mkdir()
    answer = hidden / "answer.txt"
    answer.write_text("private answer")
    code = f"""import json
from pathlib import Path
try:
    Path({str(answer)!r}).read_text()
    read = True
except PermissionError:
    read = False
try:
    Path("unauthorized.txt").write_text("changed")
    write = True
except PermissionError:
    write = False
print(json.dumps({{"read": read, "write": write}}))
"""
    (workspace / "main.py").write_text(code)
    family = hidden / "business"
    (family / "graders").mkdir(parents=True)
    (family / "manifest.json").write_text('{"entrypoint":"main.py"}')
    (family / "tasks.json").write_text('{"tasks":[]}')
    (family / "graders/stage-1.json").write_text(
        json.dumps(
            [{"name": "isolation", "stdin": {}, "expected": {"read": False, "write": False}}]
        )
    )
    monkeypatch.setattr(experiment, "CORPUS", hidden)
    assert experiment.grade(workspace, local, {"family": "business", "stage": 1})["passed"]
    assert answer.read_text() == "private answer"
    assert not (workspace / "unauthorized.txt").exists()
