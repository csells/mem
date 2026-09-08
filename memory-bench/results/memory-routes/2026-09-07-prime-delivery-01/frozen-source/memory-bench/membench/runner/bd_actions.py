"""Pure config.json Write validation shared by prospective scoring and post hoc audits.

Paths are lexical: no reads from the live or historical sandbox, and no claims about
symlink resolution or final state after later mutations. JSON values are decoded before
matching authored tokens; JSON keys and tool metadata cannot supply required values.
"""

from __future__ import annotations

import json
import posixpath
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from membench.metrics.scorers import states_value
from membench.runner.realagent_probe import CONFIG_FILE
from membench.schemas.trace import ToolCall

UNKNOWN_DESTINATION = "unknown_current_directory"


def _destination_reason(path: str, *, cwd: str | Path | None) -> str:
    normalized = posixpath.normpath(path)
    if cwd is None:
        if posixpath.isabs(normalized) and posixpath.basename(normalized) == CONFIG_FILE:
            return UNKNOWN_DESTINATION
        return "qualifies" if normalized == CONFIG_FILE else "wrong_path"
    base = str(cwd)
    if not posixpath.isabs(base) or "\x00" in base:
        raise ValueError("Write validation requires an absolute cwd")
    actual = posixpath.normpath(posixpath.join(base, path))
    expected = posixpath.normpath(posixpath.join(base, CONFIG_FILE))
    return "qualifies" if actual == expected else "wrong_path"


def _reject_constant(value: str) -> Any:
    raise ValueError(f"Non-JSON numeric constant {value}")


def _unique_object(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(items)
    if len(result) != len(items):
        raise ValueError("Duplicate JSON keys")
    return result


def string_values(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from string_values(child)


def write_reason(
    call: ToolCall, *, cwd: str | Path | None, required: Sequence[str], forbidden: Sequence[str]
) -> str:
    if call.name != "Write" or call.result is None or call.is_error:
        return "not_acknowledged_successful_write"
    path, content = call.arguments.get("file_path"), call.arguments.get("content")
    if not isinstance(path, str) or not path or "\x00" in path:
        return "missing_or_invalid_path"
    destination = _destination_reason(path, cwd=cwd)
    if destination == "wrong_path":
        return destination
    if not isinstance(content, str):
        return "missing_string_content"
    try:
        document = json.loads(
            content, parse_constant=_reject_constant, object_pairs_hook=_unique_object
        )
    except ValueError:
        return "invalid_json"
    values = list(string_values(document))
    if not required or not all(
        any(states_value(value, token) for value in values) for token in required
    ):
        return "required_token_absent_from_json_values"
    if any(states_value(json.dumps(document, ensure_ascii=False), token) for token in forbidden):
        return "superseded_token_present"
    return destination


def valid_write(
    call: ToolCall, *, cwd: str | Path | None, required: Sequence[str], forbidden: Sequence[str]
) -> bool:
    return write_reason(call, cwd=cwd, required=required, forbidden=forbidden) == "qualifies"
