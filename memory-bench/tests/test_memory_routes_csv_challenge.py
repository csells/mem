"""Behavioral CSV oracles and immutable, goal-only challenge execution."""

from __future__ import annotations

import codecs
import copy
import csv
import io
import json
from pathlib import Path
from typing import Any

import pytest

from membench.runner.memory_routes_corpus import build_tasks
from scripts import memory_routes_csv_challenge as challenge
from scripts import memory_routes_experiment as driver

GOLDEN = (
    b'client\tamount\n"Caf\xc3\xa9 ""North"", LLC;\tWest"\t12.3457\n'
    b"South & Sons\t-0.0101\nEast\t0.0000\n"
)


def config(**changes: Any) -> dict[str, Any]:
    task = next(task for task in build_tasks(challenge.SEED) if task.domain == "csv_export")
    value = copy.deepcopy(task.expected_config)
    value["csv_export"].update(changes)
    return value


def source_case(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    task = next(task for task in build_tasks(challenge.SEED) if task.domain == "csv_export")
    source = tmp_path / "source"
    case = source / "cases" / f"{task.id}-protocol"
    (case / "establish").mkdir(parents=True)
    captured = {**task.decoys, task.key: task.context_note}
    establish = {"exit_code": 0, "is_error": False, "artifact": {"passed": True}}
    values = {
        source
        / "manifest.json": {
            "schema": "memory-routes-macos.v1",
            "seed": challenge.SEED,
            "tasks": [{"id": task.id, "expected_config": task.expected_config}],
        },
        case
        / "result.json": {
            "task": task.id,
            "policy": "protocol",
            "legs": {
                "establish": establish,
                "direct": {},
                "search": {},
                "unnecessary": {},
            },
        },
        case / "establish/result.json": establish,
        case / "establish/memory.json": captured,
    }
    for path, value in values.items():
        driver.new_json(path, value)
    return source, case, captured


@pytest.fixture
def runtime_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / "fake-runtime"
    binary.write_bytes(b"pinned-test-runtime")
    for name in ("BD", "CLAUDE", "PYTHON"):
        monkeypatch.setattr(driver, name, binary)


def test_original_contract_matches_independently_authored_bytes(tmp_path: Path) -> None:
    path = tmp_path / "invoices.csv"
    path.write_bytes(GOLDEN)
    assert challenge.grade_csv(path, config())["passed"] is True
    assert challenge.canonical_csv(config()) == GOLDEN
    assert challenge.expected_rows(config()) == [
        ["client", "amount"],
        ['Café "North", LLC;\tWest', "12.3457"],
        ["South & Sons", "-0.0101"],
        ["East", "0.0000"],
    ]


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
@pytest.mark.parametrize("ending", ["LF", "CRLF"])
def test_equivalent_quoting_and_utf16_endianness_are_allowed(
    tmp_path: Path, encoding: str, ending: str
) -> None:
    expected = config(encoding=encoding, line_ending=ending, delimiter=";", decimal_separator=",")
    output = io.StringIO(newline="")
    csv.writer(
        output,
        delimiter=";",
        lineterminator="\n" if ending == "LF" else "\r\n",
        quoting=csv.QUOTE_ALL,
    ).writerows(
        [
            ["client", "amount"],
            ['Café "North", LLC;\tWest', "12,3457"],
            ["South & Sons", "-0,0101"],
            ["East", "0,0000"],
        ]
    )
    raw = (
        codecs.BOM_UTF16_BE + output.getvalue().encode("utf-16-be")
        if encoding == "utf-16"
        else output.getvalue().encode(encoding)
    )
    path = tmp_path / "invoices.csv"
    path.write_bytes(raw)
    result = challenge.grade_csv(path, expected)
    assert result["passed"] is True
    assert result["canonical_bytes_match"] is False


@pytest.mark.parametrize(
    ("raw", "settings", "reason"),
    [
        (codecs.BOM_UTF8 + GOLDEN, {}, "bom_mismatch"),
        (GOLDEN, {"encoding": "utf-8-sig"}, "bom_mismatch"),
        (GOLDEN, {"encoding": "utf-16"}, "bom_mismatch"),
        (GOLDEN.replace(b"Caf\xc3\xa9", b"Caf\xff"), {}, "encoding_mismatch"),
        (GOLDEN.replace(b"\n", b"\r\n"), {}, "line_ending_mismatch"),
        (GOLDEN[:-1], {}, "line_ending_mismatch"),
        (GOLDEN, {"delimiter": ";"}, "malformed_csv"),
        (GOLDEN.replace(b"12.3457", b"12.3456"), {}, "header_rows_or_format_mismatch"),
        (GOLDEN.replace(b"0.0000", b"0"), {}, "header_rows_or_format_mismatch"),
        (GOLDEN.replace(b"client", b"customer"), {}, "header_rows_or_format_mismatch"),
        (GOLDEN.replace(b'""North""', b"North"), {}, "header_rows_or_format_mismatch"),
        (GOLDEN + b"extra\t1.0000\n", {}, "header_rows_or_format_mismatch"),
    ],
)
def test_bad_actual_csv_fails_despite_a_correct_json_contract(
    tmp_path: Path, raw: bytes, settings: dict[str, Any], reason: str
) -> None:
    path = tmp_path / "invoices.csv"
    path.write_bytes(raw)
    result = challenge.grade_csv(path, config(**settings))
    assert result == {"passed": False, "reason": reason}


def test_missing_or_symlink_csv_is_not_credited(tmp_path: Path) -> None:
    path = tmp_path / "invoices.csv"
    assert challenge.grade_csv(path, config())["passed"] is False
    target = tmp_path / "elsewhere.csv"
    target.write_bytes(GOLDEN)
    path.symlink_to(target)
    assert challenge.grade_csv(path, config())["reason"] == "artifact_symlink"


def test_temporal_prompts_require_distinct_effective_contracts() -> None:
    task = next(task for task in build_tasks(challenge.SEED) if task.domain == "csv_export")
    original = copy.deepcopy(task.expected_config)
    legs = challenge.challenge_legs(task)
    assert task.expected_config == original
    assert legs["search"]["expected_config"] == original
    assert legs["historical"]["expected_config"] == original
    assert legs["current"]["expected_config"] == config(delimiter=";")
    assert "BEFORE" in legs["historical"]["prompt"]
    assert "All other settings remain" in legs["current"]["prompt"]
    for leg in challenge.LEGS:
        assert task.key not in legs[leg]["prompt"]
        assert "both config.json and invoices.csv" in legs[leg]["prompt"]


@pytest.mark.parametrize("kind", ["missing", "prose", "wrong", "missing-decoy"])
def test_unusable_source_capture_blocks_without_repair(tmp_path: Path, kind: str) -> None:
    source, case, captured = source_case(tmp_path)
    task = next(task for task in build_tasks(challenge.SEED) if task.domain == "csv_export")
    if kind == "missing":
        del captured[task.key]
    elif kind == "prose":
        captured[task.key] = "Acme uses tabs, UTF-8, LF, four decimal places and a dot."
    elif kind == "wrong":
        captured[task.key] = json.dumps(config(delimiter=";"))
    else:
        del captured[next(iter(task.decoys))]
    memory = case / "establish/memory.json"
    memory.write_text(json.dumps(captured))
    before = memory.read_bytes()
    with pytest.raises(ValueError, match="capture"):
        challenge.load_capture(source)
    assert memory.read_bytes() == before


def test_incomplete_source_case_blocks(tmp_path: Path) -> None:
    source, case, _ = source_case(tmp_path)
    result = json.loads((case / "result.json").read_text())
    del result["legs"]["search"]
    (case / "result.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="not completed"):
        challenge.load_capture(source)


@pytest.mark.usefixtures("runtime_binary")
def test_plan_freezes_original_capture_prompts_and_semantic_oracle(tmp_path: Path) -> None:
    source, case, captured = source_case(tmp_path)
    plan, loaded = challenge.make_plan(source, list(challenge.LEGS), 0.5)
    assert loaded == captured
    assert plan["planned_sessions"] == 4
    assert plan["source_run"] == str(source.resolve())
    relative = str((case / "establish/memory.json").relative_to(source))
    assert plan["source_evidence_sha256"][relative] == driver.sha(case / "establish/memory.json")
    assert plan["legs"]["search"]["canonical_csv_hex"] == GOLDEN.hex()
    assert plan["legs"]["historical"]["canonical_csv_hex"] == GOLDEN.hex()
    assert plan["legs"]["current"]["canonical_csv_hex"] != GOLDEN.hex()
    assert "scripts/memory_routes_csv_challenge.py" in " ".join(plan["source_sha256"])


@pytest.mark.parametrize("legs", [[], ["search", "search"], ["other"]])
def test_invalid_leg_selection_fails_before_loading_source(tmp_path: Path, legs: list[str]) -> None:
    with pytest.raises(ValueError, match="Legs"):
        challenge.make_plan(tmp_path / "absent", legs, 0.5)


@pytest.mark.parametrize("budget", [0, -1, float("inf"), float("nan")])
def test_invalid_budget_fails_before_loading_source(tmp_path: Path, budget: float) -> None:
    with pytest.raises(ValueError, match="budget"):
        challenge.make_plan(tmp_path / "absent", ["search"], budget)


@pytest.mark.usefixtures("runtime_binary")
def test_main_requires_fire_and_branches_capture_without_repurchasing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, source_directory, captured = source_case(tmp_path)
    before = (source_directory / "establish/memory.json").read_bytes()
    states: dict[Path, dict[str, str]] = {}
    calls: list[dict[str, Any]] = []

    def initialize(store: Path, env: dict[str, str], evidence: Path) -> None:
        store.mkdir()
        states[store] = {}
        driver.new_json(evidence, {"returncode": 0})

    def checked(args: list[str], store: Path, env: dict[str, str]) -> str:
        assert args[0] == "remember" and args[2] == "--key"
        states[store][args[3]] = args[1]
        return "Remembered"

    def run_leg(**kwargs: Any) -> tuple[dict[str, Any], Path]:
        calls.append(kwargs)
        assert kwargs["policy"] == "protocol"
        assert kwargs["native_from"] is None
        assert states[kwargs["store"]] == captured
        states[kwargs["store"]]["goal-only-mutation"] = kwargs["leg"]
        work = kwargs["case"] / kwargs["leg"] / "work"
        work.mkdir(parents=True)
        (work / "config.json").write_text(json.dumps(kwargs["expected"]))
        (work / "invoices.csv").write_bytes(challenge.canonical_csv(kwargs["expected"]))
        kwargs["evidence"].mkdir()
        (kwargs["evidence"] / "stream.jsonl").write_text("")
        result = {
            "leg": kwargs["leg"],
            "artifact": {"passed": True},
            "memory_evidence": {"operations": []},
        }
        driver.new_json(kwargs["evidence"] / "result.json", result)
        return result, kwargs["case"] / "unused-native"

    monkeypatch.setattr(challenge, "experiment_env", lambda *args: {})
    monkeypatch.setattr(driver, "initialize_store", initialize)
    monkeypatch.setattr(driver, "checked_bd", checked)
    monkeypatch.setattr(driver, "memories", lambda store, env: dict(states[store]))
    monkeypatch.setattr(driver, "run_leg", run_leg)
    out = tmp_path / "out"
    argv = ["--out", str(out), "--source-run", str(source), "--legs", "search,current,historical"]
    challenge.main(argv)
    assert calls == []
    assert json.loads((out / "manifest.json").read_text())["planned_sessions"] == 3
    challenge.main([*argv, "--fire"])
    assert [call["leg"] for call in calls] == ["search", "current", "historical"]
    for leg in ("search", "current", "historical"):
        result = json.loads((out / "cases" / leg / "result.json").read_text())
        assert result["passed"] is True
        assert result["original_contract_route"]["bd_correct_payload_observed"] is False
        assert json.loads((out / "cases" / leg / "transferred-memory.json").read_text()) == captured
    assert (source_directory / "establish/memory.json").read_bytes() == before
    challenge.main([*argv, "--fire"])
    assert len(calls) == 3
    with pytest.raises(ValueError, match="differs"):
        challenge.main([*argv, "--session-budget", "0.6", "--fire"])
    assert len(calls) == 3


@pytest.mark.usefixtures("runtime_binary")
def test_interrupted_leg_blocks_all_new_model_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _, _ = source_case(tmp_path)
    out = tmp_path / "out"
    argv = ["--out", str(out), "--source-run", str(source), "--legs", "search,supplied"]
    challenge.main(argv)
    (out / "cases/supplied").mkdir(parents=True)

    def must_not_run(*args: Any, **kwargs: Any) -> None:
        pytest.fail("An interrupted run must not launch even an earlier pending leg")

    monkeypatch.setattr(challenge, "run_challenge", must_not_run)
    with pytest.raises(ValueError, match="cannot be repurchased"):
        challenge.main([*argv, "--fire"])
