"""The bd-specific endpoint must survive native reaches, failed tools and missing legs."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from membench.runner.e1_reliability import reliability_report, score_bd_leg
from membench.schemas.trace import ToolCall
from tests.toolreq_helpers import corpus_one


def _bash(command: str, result: str | None = None, *, error: bool = False) -> ToolCall:
    return ToolCall(name="Bash", arguments={"command": command}, result=result, is_error=error)


def _score(task, calls, *, leg=0, status="ok", config_dir=None):
    return score_bd_leg(
        task,
        calls,
        leg=leg,
        role="goal" if leg % 2 else "establish",
        status=status,
        config_dir=config_dir,
    )


def _row(evidence, *, work_id="task", runs=2, rung="R1", variant="necessary"):
    return {
        "rung": rung,
        "variant": variant,
        "work_id": work_id,
        "native_memory_pinned_off": False,
        "metrics": {"runs": runs},
        "bd_evidence": [e.model_dump() for e in evidence],
    }


def test_native_memory_cannot_satisfy_the_bd_endpoint(tmp_path: Path) -> None:
    _, tasks = corpus_one(tmp_path)
    config = tmp_path / "config"
    calls = [
        ToolCall(
            name="Read",
            arguments={"file_path": str(config / "memory/MEMORY.md")},
            result="missing",
            is_error=True,
        )
    ]
    score = _score(tasks[0], calls, leg=1, config_dir=config)
    assert score.native_read_attempts == 1
    assert score.native_answered_reads == 0
    assert score.bd_read_attempts == 0
    assert score.bd_recall_complete is False


@pytest.mark.parametrize("result", [None, 'Error: "list" looks like a command'])
def test_refused_or_unanswered_remember_is_only_an_attempt(tmp_path, result):
    _, tasks = corpus_one(tmp_path)
    score = _score(tasks[0], [_bash("bd remember list", result)])
    assert score.bd_write_attempts == 1
    assert score.bd_accepted_writes == 0
    assert score.bd_capture_complete is False


def test_capture_requires_all_values_in_acknowledged_content_not_the_key(tmp_path):
    _, tasks = corpus_one(tmp_path)
    task = replace(tasks[0], current_opaque_values=("nonce-a", "nonce-b"))
    partial = _bash('bd remember --key nonce-b "nonce-a"', "Remembered [nonce-b]: nonce-a")
    assert _score(task, [partial]).bd_capture_complete is False
    remaining = _bash('bd remember "nonce-b is current"', "Remembered [chosen]: nonce-b is current")
    assert _score(task, [partial, remaining]).bd_capture_complete is True


@pytest.mark.parametrize(
    "command,result,error",
    [
        ("bd recall absent", "not found", False),
        ("bd recall key", None, False),
        ("bd recall key", "nonce-a", True),
        ("bd recall absent; echo nonce-a", "nonce-a", False),
        ("bd recall absent | cat /tmp/file", "nonce-a", False),
        ('bd remember --key k "nonce-a"; bd recall absent', "Remembered [k]: nonce-a", False),
    ],
)
def test_read_attempt_is_not_proof_bd_returned_the_required_value(tmp_path, command, result, error):
    _, tasks = corpus_one(tmp_path)
    task = replace(tasks[0], current_opaque_values=("nonce-a",))
    assert _score(task, [_bash(command, result, error=error)], leg=1).bd_recall_complete is False


def test_bd_read_payload_and_acknowledged_goal_action_are_separate(tmp_path):
    _, tasks = corpus_one(tmp_path)
    task = tasks[0]
    content = " ".join(task.current_opaque_values)
    read = _identified("bd recall current", content)
    goal = ToolCall(
        name="Write",
        arguments={"file_path": "config.json", "content": json.dumps(content)},
        result="File created",
        tool_use_index=2,
        tool_result_index=3,
    )
    assert _score(task, [read], leg=1).bd_recall_complete is True
    assert _score(task, [read], leg=1).goal_action_success is False
    assert _score(task, [read, goal], leg=1).goal_action_success is True
    assert _score(task, [read, goal], leg=1).bd_recall_before_action is True
    reversed_calls = [
        goal.model_copy(update={"tool_use_index": 0, "tool_result_index": 1}),
        read.model_copy(update={"tool_use_index": 2, "tool_result_index": 3}),
    ]
    assert _score(task, reversed_calls, leg=1).bd_recall_before_action is False
    for failed in (
        goal.model_copy(update={"is_error": True}),
        goal.model_copy(update={"result": None}),
    ):
        assert _score(task, [read, failed], leg=1).goal_action_success is False


def test_timeout_outcomes_remain_unknown_even_with_partial_success(tmp_path):
    _, tasks = corpus_one(tmp_path)
    score = _score(tasks[0], [], leg=1, status="timeout")
    assert score.goal_action_success is None


def test_pairs_do_not_borrow_a_write_from_another_repeat_or_task(tmp_path):
    _, tasks = corpus_one(tmp_path)
    base = _score(tasks[0], [])
    wrote = base.model_copy(update={"bd_capture_complete": True, "bd_accepted_writes": 1})
    goal = base.model_copy(
        update={
            "leg": 1,
            "role": "goal",
            "bd_recall_complete": True,
            "goal_action_success": True,
            "bd_recall_before_action": True,
        }
    )
    rows = [
        _row(
            [
                wrote,
                goal.model_copy(update={"bd_recall_complete": False}),
                base.model_copy(update={"leg": 2}),
                goal.model_copy(update={"leg": 3}),
            ],
            runs=4,
        ),
        _row([wrote, goal], work_id="other"),
    ]
    report = reliability_report(rows)
    group = report["groups"][0]
    assert group["pairs"]["scheduled"] == 3
    assert group["pairs"]["bd_handoff_observed"] == 1
    assert group["pairs"]["rate_bounds"] == [1 / 3, 1 / 3]
    assert group["roles"]["establish"]["measured"] == 3
    assert group["roles"]["goal"]["measured"] == 3
    assert len(report["per_task"]) == 2


def test_missing_pairs_expand_bounds_and_legacy_evidence_is_unmeasured(tmp_path):
    _, tasks = corpus_one(tmp_path)
    report = reliability_report([_row([_score(tasks[0], [])], runs=4)])
    assert report["groups"][0]["pairs"]["unknown"] == 1
    assert report["groups"][0]["pairs"]["rate_bounds"] == [0, 0.5]
    legacy = reliability_report([_row([], runs=4)])
    assert legacy["status"] == "unmeasured"
    assert legacy["groups"] == []


def test_missing_whole_cell_stays_in_the_report_denominator(tmp_path):
    _, tasks = corpus_one(tmp_path)
    establish = _score(tasks[0], []).model_copy(update={"bd_capture_complete": True})
    goal = _score(tasks[0], [], leg=1).model_copy(
        update={
            "bd_recall_complete": True,
            "goal_action_success": True,
            "bd_recall_before_action": True,
        }
    )
    report = reliability_report([_row([establish, goal]), _row([], work_id="missing")])
    assert report["groups"][0]["pairs"]["rate_bounds"] == [0.5, 1]
    assert report["groups"][0]["pairs"]["scheduled"] == 2
    assert report["cells_without_evidence"] == 1


@pytest.mark.parametrize(
    "command,result,error",
    [
        (
            'bd remember --key k "nonce-a"; printf "Remembered [k]: nonce-a"',
            "Error: unavailable\nRemembered [k]: nonce-a",
            False,
        ),
        ('bd remember --key k "nonce-a"', "Remembered [k]: nonce-a", True),
    ],
)
def test_failed_or_unattributed_acknowledgements_do_not_prove_capture(
    tmp_path, command, result, error
):
    _, tasks = corpus_one(tmp_path)
    task = replace(tasks[0], current_opaque_values=("nonce-a",))
    assert _score(task, [_bash(command, result, error=error)]).bd_capture_complete is False


@pytest.mark.parametrize(
    "command,result",
    [
        ('bd memories "nonce-a"', 'No memories matching "nonce-a"\n\n'),
        ('bd memories --json "nonce-a"', '{"nonce-a":"unrelated", "schema_version":1}'),
        ("bd recall --json nonce-a", '{"found":false,"key":"nonce-a","value":""}'),
        ("bd recall --json nonce-a", '{"found":true,"key":"nonce-a","value":"unrelated"}'),
    ],
)
def test_search_misses_and_result_keys_are_not_returned_content(tmp_path, command, result):
    _, tasks = corpus_one(tmp_path)
    task = replace(tasks[0], current_opaque_values=("nonce-a",))
    assert _score(task, [_bash(command, result)], leg=1).bd_recall_complete is False


@pytest.mark.parametrize(
    "command,result,complete",
    [
        ("bd recall --json k", '{"found":true,"key":"k","value":"nonce-a"}', True),
        ("bd memories --json nonce", '{"schema_version":1,"k":"nonce-a"}', True),
        ("bd memories nonce", 'Memories matching "nonce":\n\n  k\n    nonce-a\n', True),
        ("bd remember k", '(recalled "k" -- a bare existing key READS.)\nnonce-a', True),
        ("bd recall --json k", '{"found":true,"value":"nonce-a"', False),
        ("bd recall --json k", '["nonce-a"]', False),
    ],
)
def test_shipped_read_formats_match_payloads_only(tmp_path, command, result, complete):
    _, tasks = corpus_one(tmp_path)
    task = replace(tasks[0], current_opaque_values=("nonce-a",))
    assert _score(task, [_bash(command, result)], leg=1).bd_recall_complete is complete


def test_duplicate_or_mislabelled_legs_are_refused(tmp_path):
    _, tasks = corpus_one(tmp_path)
    leg = _score(tasks[0], [])
    with pytest.raises(ValueError, match="duplicate"):
        reliability_report([_row([leg, leg])])
    with pytest.raises(ValueError, match="role"):
        reliability_report([_row([leg.model_copy(update={"role": "goal"})])])


def test_establish_tells_the_truth_about_session_continuity():
    from membench.runner.e1_grid import ESTABLISH_INSTRUCTION, EXECUTION_PROTOCOL_VERSION

    assert "separate session" in ESTABLISH_INSTRUCTION
    assert "later turn in this session" not in ESTABLISH_INSTRUCTION
    assert EXECUTION_PROTOCOL_VERSION >= 4


def test_live_cell_persists_report_through_serialization(tmp_path):
    import subprocess

    from membench.runner.e1_grid import LegRecord, RungCell, run_rung_cell, summarize
    from membench.runner.headless_agent import (
        assistant_event,
        result_event,
        serialize_stream,
        tool_result_event,
    )

    _, tasks = corpus_one(tmp_path)
    task = tasks[0]
    content = " ".join(task.current_opaque_values)
    captured: list[LegRecord] = []

    def runner(argv, **kwargs):
        if len(captured) % 2 == 0:
            stored = subprocess.run(
                ["bd", "remember", "--key", "k", content],
                cwd=kwargs["cwd"],
                env=kwargs["env"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            events = [
                assistant_event([("Bash", {"command": f'bd remember --key k "{content}"'}, "w")]),
                tool_result_event("w", stored.stdout),
            ]
        else:
            recalled = subprocess.run(
                ["bd", "recall", "k"],
                cwd=kwargs["cwd"],
                env=kwargs["env"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            applied = Path(kwargs["cwd"]) / "config.json"
            applied.write_text(json.dumps(recalled.stdout), encoding="utf-8")
            assert all(value in applied.read_text() for value in task.current_opaque_values)
            events = [
                assistant_event([("Bash", {"command": "bd recall k"}, "r")]),
                tool_result_event("r", recalled.stdout),
                assistant_event(
                    [
                        (
                            "Write",
                            {"file_path": str(applied), "content": json.dumps(recalled.stdout)},
                            "g",
                        )
                    ]
                ),
                tool_result_event("g", "File created"),
            ]
        return subprocess.CompletedProcess(argv, 0, serialize_stream([*events, result_event()]), "")

    cell = run_rung_cell(
        task,
        rung="R1",
        repeats=1,
        model="claude-test",
        dry_run=False,
        runner=runner,
        on_leg=captured.append,
    )
    assert all(leg.row()["bd_evidence"] for leg in captured)
    assert all(leg.row()["cwd"] and Path(leg.row()["cwd"]).is_absolute() for leg in captured)
    assert captured[0].cwd == captured[1].cwd
    restored = RungCell.from_row(cell.row())
    summary = summarize([restored], model="claude-test", dry_run=False, repeats=1)
    assert summary["bd_reliability"]["groups"][0]["pairs"]["bd_handoff_observed"] == 1
    legacy_row = cell.row()
    legacy_row["bd_evidence"] = [
        {key: value for key, value in evidence.items() if key != "scoring_version"}
        for evidence in legacy_row["bd_evidence"]
    ]
    cached = RungCell.from_row(legacy_row)
    legacy = summarize([cached], model="claude-test", dry_run=False, repeats=1)
    assert cached.runs == restored.runs
    assert legacy["bd_reliability"]["evidence_versions"] == [0]
    assert legacy["bd_reliability"]["groups"][0]["pairs"]["bd_handoff_observed"] == 0
    assert legacy["bd_reliability"]["groups"][0]["pairs"]["unknown"] == 1


def _receipt(call_id, argv, stdout, *, code=0, leg_id="leg", invocation="i"):
    common = {
        "invocation_id": invocation,
        "tool_use_id": call_id,
        "session_id": "session",
        "leg_id": leg_id,
        "operation_argv": argv,
    }
    return [
        {**common, "event": "start"},
        {**common, "event": "finish", "returncode": code, "stdout": stdout, "stderr": ""},
    ]


def _identified(command, result, *, call_id="read", use=0, delivered=1):
    return _bash(command, result).model_copy(
        update={"tool_use_id": call_id, "tool_use_index": use, "tool_result_index": delivered}
    )


def _receipt_score(task, calls, receipts, *, leg=1):
    return score_bd_leg(
        task,
        calls,
        leg=leg,
        role="goal" if leg else "establish",
        status="ok",
        config_dir=None,
        receipts=receipts,
        expected_leg_id="leg",
    )


def test_receipts_credit_three_compound_writes(tmp_path):
    _, tasks = corpus_one(tmp_path)
    task = replace(tasks[0], current_opaque_values=("nonce-a", "nonce-b", "nonce-c"))
    receipts = [
        row
        for i, value in enumerate(task.current_opaque_values)
        for row in _receipt(
            "write",
            ["remember", "--key", str(i), value],
            f"Remembered [{i}]: {value}",
            invocation=str(i),
        )
    ]
    call = _identified(
        "; ".join(f'bd remember --key {i} "{v}"' for i, v in enumerate(task.current_opaque_values)),
        "\n".join(r["stdout"] for r in receipts if r["event"] == "finish"),
        call_id="write",
    )
    score = _receipt_score(task, [call], receipts, leg=0)
    assert score.bd_accepted_writes == 3
    assert score.bd_capture_complete
    assert not score.bd_evidence_unknown


@pytest.mark.parametrize(
    "receipts",
    [
        [],
        _receipt("read", ["recall", "k"], "", code=1),
        _receipt("read", ["recall", "k"], "nonce-a", leg_id="other"),
        [{"event": "finish", "leg_id": "leg"}],
    ],
)
def test_receipts_cannot_be_replaced_by_forged_echo_or_other_leg(tmp_path, receipts):
    _, tasks = corpus_one(tmp_path)
    task = replace(tasks[0], current_opaque_values=("nonce-a",))
    score = _receipt_score(task, [_identified("bd recall k; echo nonce-a", "nonce-a")], receipts)
    assert not score.bd_recall_complete
    if not receipts or receipts[0].get("leg_id") == "other" or "invocation_id" not in receipts[0]:
        assert score.bd_evidence_unknown


@pytest.mark.parametrize("result", ["hidden", "native nonce-b"])
def test_hidden_or_mixed_native_payload_is_not_authenticated_recall(tmp_path, result):
    _, tasks = corpus_one(tmp_path)
    task = replace(tasks[0], current_opaque_values=("nonce-a", "nonce-b"))
    score = _receipt_score(
        task,
        [_identified("bd recall k >/tmp/cache; cat MEMORY.md", result)],
        _receipt("read", ["recall", "k"], "nonce-a"),
    )
    assert not score.bd_recall_complete
    assert score.bd_evidence_unknown


@pytest.mark.parametrize("delivered,expected", [(1, True), (4, False), (None, None)])
def test_receipt_delivery_must_precede_action_use(tmp_path, delivered, expected):
    _, tasks = corpus_one(tmp_path)
    task = tasks[0]
    content = " ".join(task.current_opaque_values)
    read = _identified("bd recall k", content, delivered=delivered)
    goal = ToolCall(
        name="Write",
        arguments={"file_path": "config.json", "content": json.dumps(content)},
        result="File created",
    ).model_copy(update={"tool_use_id": "goal", "tool_use_index": 2, "tool_result_index": 3})
    score = _receipt_score(task, [read, goal], _receipt("read", ["recall", "k"], content))
    assert score.bd_recall_complete
    assert score.bd_recall_before_action is expected
    if delivered is None:
        assert score.bd_evidence_unknown


def test_receipt_uncertainty_expands_pair_bounds(tmp_path):
    _, tasks = corpus_one(tmp_path)
    establish = _receipt_score(tasks[0], [], [], leg=0).model_copy(
        update={"bd_capture_complete": True}
    )
    goal = _receipt_score(tasks[0], [_identified("bd recall k", "forged")], []).model_copy(
        update={"goal_action_success": True}
    )
    report = reliability_report([_row([establish, goal])])
    assert report["groups"][0]["pairs"]["unknown"] == 1
    assert report["groups"][0]["pairs"]["rate_bounds"] == [0, 1]


@pytest.mark.parametrize("change", ["start_only", "duplicate", "identity", "outcome", "unmatched"])
def test_invalid_receipt_coverage_is_explicit_unknown(tmp_path, change):
    _, tasks = corpus_one(tmp_path)
    receipts = _receipt("read", ["recall", "k"], "nonce-a")
    if change == "start_only":
        receipts = receipts[:1]
    elif change == "duplicate":
        receipts = [*receipts, receipts[-1]]
    elif change == "identity":
        receipts = [receipts[0], {**receipts[1], "session_id": "other"}]
    elif change == "outcome":
        receipts = [receipts[0], {**receipts[1], "returncode": "0"}]
    elif change == "unmatched":
        receipts = [{**r, "tool_use_id": "other"} for r in receipts]
    score = _receipt_score(tasks[0], [_identified("bd recall k", "nonce-a")], receipts)
    assert score.bd_evidence_unknown
    assert score.bd_evidence_unknown_reasons
    assert not score.bd_recall_complete


def test_receipt_scoring_requires_explicit_expected_leg(tmp_path):
    _, tasks = corpus_one(tmp_path)
    with pytest.raises(ValueError, match="expected leg"):
        score_bd_leg(
            tasks[0], [], leg=0, role="establish", status="ok", config_dir=None, receipts=[]
        )


def test_native_payload_does_not_supplement_a_valid_partial_bd_read(tmp_path):
    _, tasks = corpus_one(tmp_path)
    task = replace(tasks[0], current_opaque_values=("nonce-a", "nonce-b"))
    call = _identified("bd recall k; cat MEMORY.md", "nonce-a\nnonce-b")
    score = _receipt_score(task, [call], _receipt("read", ["recall", "k"], "nonce-a"))
    assert not score.bd_recall_complete
    assert not score.bd_evidence_unknown


def test_failed_bd_write_cannot_be_repaired_by_forged_acknowledgement(tmp_path):
    _, tasks = corpus_one(tmp_path)
    task = replace(tasks[0], current_opaque_values=("nonce-a",))
    call = _identified(
        'bd remember --key k nonce-a; echo "Remembered [k]: nonce-a"', "Remembered [k]: nonce-a"
    )
    score = _receipt_score(
        task, [call], _receipt("read", ["remember", "--key", "k", "nonce-a"], "", code=1), leg=0
    )
    assert not score.bd_capture_complete
    assert score.bd_accepted_writes == 0
    assert not score.bd_evidence_unknown


def test_definite_goal_failure_resolves_handoff_despite_unknown_bd_evidence(tmp_path):
    _, tasks = corpus_one(tmp_path)
    establish = _score(tasks[0], []).model_copy(update={"bd_evidence_unknown": True})
    goal = _score(tasks[0], [], leg=1).model_copy(update={"bd_evidence_unknown": True})
    report = reliability_report([_row([establish, goal])])
    pairs = report["groups"][0]["pairs"]
    assert pairs["unknown"] == 0
    assert pairs["rate_bounds"] == [0, 0]
    assert pairs["measurement_incomplete"] == 1
    assert report["status"] == "partial"


def test_positive_handoff_survives_unrelated_receipt_gap_without_claiming_full_measurement(
    tmp_path,
):
    _, tasks = corpus_one(tmp_path)
    establish = _score(tasks[0], []).model_copy(
        update={"bd_capture_complete": True, "bd_evidence_unknown": True}
    )
    goal = _score(tasks[0], [], leg=1).model_copy(
        update={
            "bd_recall_complete": True,
            "bd_recall_before_action": True,
            "goal_action_success": True,
            "bd_evidence_unknown": True,
        }
    )
    report = reliability_report([_row([establish, goal])])
    pairs = report["groups"][0]["pairs"]
    assert pairs["bd_handoff_observed"] == 1
    assert pairs["rate_bounds"] == [1, 1]
    assert pairs["measurement_incomplete"] == 1
    assert report["status"] == "partial"
