"""Independent final-artifact and literal-capture checks for memory-route experiments.

These checks establish exact JSON preservation, not the truth of surrounding prose.
Capture permits one complete JSON object, either as the note or in a Markdown fence.
It never credits a correct fragment inside an otherwise incorrect configuration.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_JSON_FENCE = re.compile(
    r"^[ \t]*```(?:json)?[ \t]*\r?\n(.*?)^[ \t]*```[ \t]*(?:\r?\n|$)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def _json(text: str) -> Any:
    value = json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
    _validate_expected(value)  # Also rejects numeric overflow such as 1e999.
    return value


def _validate_expected(value: Any) -> None:
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise ValueError("expected configuration requires string object keys")
        for child in value.values():
            _validate_expected(child)
    elif type(value) is list:
        for child in value:
            _validate_expected(child)
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError("expected configuration cannot contain non-finite numbers")
    elif type(value) not in (str, int, bool, type(None)):
        raise ValueError("expected configuration must contain only JSON values")


def _expected(value: dict[str, Any]) -> None:
    if type(value) is not dict:
        raise ValueError("expected configuration must be a JSON object")
    _validate_expected(value)


def _failure(reason: str, path: str = "$") -> dict[str, Any]:
    return {"passed": False, "reason": reason, "path": path}


def _compare(actual: Any, expected: Any, path: str = "$") -> dict[str, Any]:
    # Python otherwise equates True with 1 and integers with equal-valued floats.
    if type(actual) is not type(expected):
        return _failure("type_mismatch", path)
    if type(expected) is dict:
        if actual.keys() != expected.keys():
            return _failure("object_keys_mismatch", path)
        for key, value in expected.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            result = _compare(actual[key], value, f"{path}/{escaped}")
            if not result["passed"]:
                return result
    elif type(expected) is list:
        if len(actual) != len(expected):
            return _failure("array_length_mismatch", path)
        for index, (item, value) in enumerate(zip(actual, expected, strict=True)):
            result = _compare(item, value, f"{path}/{index}")
            if not result["passed"]:
                return result
    elif actual != expected:
        return _failure("value_mismatch", path)
    return {"passed": True, "reason": "exact_match"}


def grade_artifact(path: Path, expected_config: dict[str, Any]) -> dict[str, Any]:
    """Read the actual final regular file and compare exact JSON keys, types and values.

    Duplicate keys and non-standard constants are malformed. Symlinks are refused;
    an earlier correct Write event cannot compensate for an incorrect final file.
    Invalid expected data is an oracle error and raises rather than failing an agent.
    """
    _expected(expected_config)
    if path.is_symlink():
        return _failure("artifact_symlink")
    if not path.exists():
        return _failure("artifact_missing")
    if not path.is_file():
        return _failure("artifact_not_file")
    try:
        actual = _json(path.read_text(encoding="utf-8"))
    except OSError:
        return _failure("artifact_unreadable")
    except (ValueError, UnicodeError):
        return _failure("malformed_json")
    return _compare(actual, expected_config)


def grade_capture(
    memories: Mapping[str, str], expected_key: str, expected_config: dict[str, Any]
) -> dict[str, Any]:
    """Check the expected key's final body contains one exact complete JSON object.

    Plain JSON and a single triple-backtick fence labelled ``json`` (or unlabelled)
    are supported. Multiple candidate fences are ambiguous even if one is correct.
    Other stored keys may exist. Unsupported prose returns ``passed: None``;
    surrounding prose is not semantically evaluated even when literal JSON passes.
    """
    _expected(expected_config)
    if not isinstance(expected_key, str) or not expected_key:
        raise ValueError("expected memory key must be nonempty")
    if expected_key not in memories:
        return _failure("memory_key_missing")
    body = memories[expected_key]
    if not isinstance(body, str):
        return _failure("memory_body_not_text")
    try:
        actual = _json(body)
    except ValueError:
        blocks = _JSON_FENCE.findall(body)
        if not blocks:
            return {"passed": None, "reason": "unsupported_capture_representation"}
        if len(blocks) != 1:
            return _failure("memory_json_ambiguous")
        try:
            actual = _json(blocks[0])
        except ValueError:
            return _failure("memory_json_malformed")
    result = _compare(actual, expected_config)
    return {**result, "matched_key": expected_key} if result["passed"] else result
