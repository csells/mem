"""A complete prose receipt permits CLI line endings, never missing facts."""

import pytest

from scripts.memory_routes_schema_control import original_body_observed

BODY = "Settings: timeout_seconds=35.\nSource: approved decision."


@pytest.mark.parametrize("ending", ["", "\n", "\r\n"])
def test_complete_visible_body_permits_terminal_newline(ending: str) -> None:
    operation = {
        "is_read": True,
        "output_observed": True,
        "returncode": 0,
        "content": [BODY + ending],
    }
    assert original_body_observed([operation], BODY)


@pytest.mark.parametrize(
    "content,visible,returncode",
    [
        (BODY[:20], True, 0),
        (BODY.replace("35", "50"), True, 0),
        (BODY, False, 0),
        (BODY, True, 1),
        (BODY.replace("\n", " "), True, 0),
    ],
)
def test_missing_changed_or_unobserved_body_is_not_credited(
    content: str, visible: bool, returncode: int
) -> None:
    operation = {
        "is_read": True,
        "output_observed": visible,
        "returncode": returncode,
        "content": [content],
    }
    assert not original_body_observed([operation], BODY)
