from __future__ import annotations

import base64

import pytest

from membench.runner.bd_real_metrics import score_real_leg
from membench.schemas.trace import ToolCall


def receipts(args, out="", code=0):
    start = {
        "event": "start",
        "invocation_id": "inv",
        "tool_use_id": "tool",
        "session_id": "s",
        "leg_id": "leg",
        "operation_argv": args,
        "argv": ["/bin/bd", "-C", "/store", *args],
        "start_monotonic_ns": 1,
    }
    finish = dict(
        start,
        event="finish",
        returncode=code,
        stdout=out,
        stderr="",
        stdout_base64=base64.b64encode(out.encode()).decode(),
        stderr_base64="",
        end_monotonic_ns=2,
    )
    return [start, finish]


def call(command="bd recall k", result="fact"):
    return ToolCall(
        name="Bash",
        arguments={"command": command},
        result=result,
        tool_use_id="tool",
        tool_use_index=2,
        tool_result_index=3,
    )


def score(rows, calls=None, **kwargs):
    return score_real_leg(
        [call()] if calls is None else calls,
        rows,
        leg_id="leg",
        status=kwargs.pop("status", "ok"),
        **kwargs,
    )


def test_successful_compound_write_survives_task_error():
    result = score(
        receipts(["remember", "fact"], "Remembered [k]: fact"),
        [call("bd remember fact; false", "Remembered [k]: fact")],
        status="error",
    )
    assert result.executed_writes == result.accepted_writes == 1
    assert result.operations[0].content == ("fact",)
    assert result.model_dump(mode="json")["leg_id"] == "leg"


@pytest.mark.parametrize("code,out", [(1, "error"), (0, ""), (0, "not an acknowledgement")])
def test_unacknowledged_write(code, out):
    assert score(receipts(["remember", "fact"], out, code)).accepted_writes == 0


@pytest.mark.parametrize(
    "out,visible,content,empty", [("fact", "fact", 1, 0), ("fact", "hidden", 0, 0), ("", "", 0, 1)]
)
def test_reads(out, visible, content, empty):
    result = score(receipts(["recall", "k"], out), [call(result=visible)])
    assert result.executed_reads == 1
    assert result.observed_content_reads == content
    assert result.empty_reads == empty


def test_json_miss_and_key_metadata_are_empty():
    out = '{"found": false, "key": "fact"}'
    assert score(receipts(["recall", "k", "--json"], out), [call(result=out)]).empty_reads == 1


def test_untaken_compound_branch_does_not_claim_receipt_gap():
    result = score([], [call("false && bd recall k", "")])
    assert result.syntactic_read_attempts == 1
    assert result.executed_reads == 0
    assert not result.evidence_unknown


def test_direct_missing_receipt_unknown():
    assert score([]).evidence_unknown


@pytest.mark.parametrize(
    "field,value",
    [
        ("stdout_base64", "!!!"),
        ("stdout", "forged"),
        ("argv", ["/evil"]),
        ("tool_use_id", "other"),
        ("end_monotonic_ns", 0),
    ],
)
def test_bad_receipts(field, value):
    rows = receipts(["recall", "k"], "fact")
    rows[1][field] = value
    result = score(rows)
    assert result.evidence_unknown
    assert result.executed_reads == 0


def test_incomplete_receipt():
    assert score(receipts(["remember", "fact"])[:1]).evidence_unknown


def test_unknown_status_does_not_erase_evidence():
    result = score(receipts(["recall", "k"], "fact"), status="weird")
    assert result.observed_content_reads == 1
    assert "unknown_status" in result.unknown_reasons


@pytest.mark.parametrize(
    "kwargs",
    [{"expected_binary": "/other"}, {"expected_store": "/other"}, {"expected_session": "other"}],
)
def test_pins(kwargs):
    assert score(receipts(["recall", "k"], "fact"), **kwargs).executed_reads == 0


def test_prime_is_exposure():
    result = score(receipts(["prime"], "context"), [call("bd prime", "context")])
    assert result.exposure_commands == 1
    assert result.executed_reads == 0


def test_bare_key_remember_recall():
    out = '(recalled "k" -- a bare existing key READS.)\nfact'
    result = score(receipts(["remember", "k"], out), [call("bd remember k", out)])
    assert result.executed_reads == 1
    assert result.executed_writes == 0
    assert result.observed_content_reads == 1


@pytest.mark.parametrize("out", ["not json", "{}", '{"found":true}', '{"found":"false"}'])
def test_malformed_json_not_empty(out):
    result = score(receipts(["recall", "k", "--json"], out), [call(result=out)])
    assert result.empty_reads == 0
    assert result.evidence_unknown


def test_json_recalled_remember_payload():
    out = '{"action":"recalled","key":"k","value":"fact"}'
    result = score(receipts(["remember", "k", "--json"], out), [call("bd remember k --json", out)])
    assert result.observed_content_reads == 1
    assert result.operations[0].content == ("fact",)


@pytest.mark.parametrize(
    "out,visible",
    [("fact\n", "fact"), ("\n fact \n", "fact"), ("first\nsecond\n", "first\nsecond")],
)
def test_read_delivery_allows_boundary_whitespace_trimming(out, visible):
    result = score(receipts(["recall", "k"], out), [call(result=visible)])
    assert result.observed_content_reads == 1
    assert result.operations[0].stdout == out


@pytest.mark.parametrize("out,visible", [("first\nsecond\n", "first second"), ("\n \n", "")])
def test_read_delivery_does_not_rewrite_internal_text_or_credit_whitespace(out, visible):
    result = score(receipts(["recall", "k"], out), [call(result=visible)])
    assert result.observed_reads == 0


@pytest.mark.parametrize("status", ["timeout", "error"])
def test_incomplete_status_preserves_positive_evidence(status):
    assert score([], [], status=status).evidence_unknown
    result = score(receipts(["recall", "k"], "fact"), status=status)
    assert result.evidence_unknown
    assert result.observed_content_reads == 1


@pytest.mark.parametrize("result,is_error", [(None, False), ("error", True)])
def test_missing_direct_receipt_with_failed_or_unanswered_tool(result, is_error):
    tool = call(result=result).model_copy(update={"is_error": is_error})
    evidence = score([], [tool])
    assert "missing_direct_execution_receipt" in evidence.unknown_reasons
