from __future__ import annotations

import json

import pytest

from membench.runner.memory_unprompted_grade import grade_record


@pytest.mark.parametrize("wrapper", ["{}", "A readable preview. {}", "Preview\n```json\n{}\n```"])
def test_complete_payload_in_readable_record(wrapper: str) -> None:
    expected = {"scope": "project-a", "policy": {"enabled": True, "count": 3}}
    result = grade_record(wrapper.format(json.dumps(expected)), expected)
    assert result["passed"] is True
    assert result["surrounding_prose_verified"] is False


@pytest.mark.parametrize(
    "body",
    [
        '{"wrapper":{"enabled":true}}',
        '{"enabled":true,"enabled":false}',
        '{"enabled":1}',
        '{"enabled":true} {"enabled":false}',
    ],
)
def test_no_nested_fragment_coercion_duplicate_or_ambiguous_credit(body: str) -> None:
    assert grade_record(body, {"enabled": True})["passed"] is False


def test_pure_prose_is_unknown_not_automatically_wrong() -> None:
    assert grade_record("Enabled for this project.", {"enabled": True})["passed"] is None
