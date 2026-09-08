"""Qualification scheduling preserves each started diagnostic and its accounting."""

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import memory_model_qualification as qualification


def test_profiles_run_once_and_partial_failure_retains_cost_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_run(out: Path, host: str, profile_id: str) -> dict[str, Any]:
        calls.append(profile_id)
        out.mkdir()
        leg_dir = out / "capture"
        leg_dir.mkdir()
        (leg_dir / "process.json").write_text('{"pid":123}')
        leg = {"passed": True, "timed_out": False, "cost_usd": 0.25}
        (leg_dir / "result.json").write_text(json.dumps(leg))
        if profile_id == "claude-sonnet":
            raise RuntimeError("new reuse session could not be prepared")
        return {"passed": True, "host": host, "profile_id": profile_id, "legs": [leg]}

    monkeypatch.setattr(qualification.smoke, "run", fake_run)
    monkeypatch.setattr(qualification.e2e, "sources", lambda: {})
    monkeypatch.setattr(qualification, "configuration_hashes", lambda: {"source": "same"})
    out = tmp_path / "new"
    report = qualification.run(out, ["claude-sonnet", "claude-opus"], 2)
    assert sorted(calls) == ["claude-opus", "claude-sonnet"]
    assert report["planned_slots"] == 4
    assert report["started_slots"] == report["assessed_slots"] == 2
    assert report["unstarted_slots"] == 2
    assert report["reported_cost_usd"] == 0.5
    assert not report["passed"]
    assert (out / "claude-sonnet/capture/result.json").is_file()
    assert (out / "claude-sonnet/failure.json").is_file()
    before = (out / "result.json").read_bytes()
    with pytest.raises(FileExistsError):
        qualification.run(out, ["claude-sonnet", "claude-opus"], 2)
    assert len(calls) == 2
    assert (out / "result.json").read_bytes() == before


def test_repeated_or_unknown_profiles_do_not_create_output(tmp_path: Path) -> None:
    out = tmp_path / "never-started"
    for profiles in [["claude-opus", "claude-opus"], ["sonnet"], []]:
        with pytest.raises(ValueError):
            qualification.run(out, profiles, 1)
        assert not out.exists()


def test_no_run_flag_never_creates_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "never-started"
    monkeypatch.setattr("sys.argv", ["qualification", "--out", str(out)])
    assert qualification.main() == 0
    assert "No inference launched" in capsys.readouterr().out
    assert not out.exists()


def test_existing_profile_evidence_does_not_receive_new_failure_file(tmp_path: Path) -> None:
    with pytest.raises(FileExistsError):
        qualification.qualify_profile(tmp_path, "claude-opus")
    assert list(tmp_path.iterdir()) == []
