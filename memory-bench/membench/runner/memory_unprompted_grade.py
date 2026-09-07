"""Literal payload grading permits readable notes without weakening the contract.

This checks the complete JSON payload, not the truth of surrounding prose. Pure
prose without an explicit JSON object needs separate semantic assessment.
"""

from __future__ import annotations

import json
from typing import Any

from membench.runner.memory_routes_grade import grade_capture


def grade_record(body: str, expected: dict[str, Any]) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    objects: list[str] = []
    index = 0
    while index < len(body):
        start = body.find("{", index)
        if start < 0:
            break
        try:
            _, length = decoder.raw_decode(body[start:])
        except ValueError:
            return {"passed": None, "reason": "unrecognized_or_malformed_representation"}
        objects.append(body[start : start + length])
        # Skip the whole object: a correct nested fragment cannot rescue a wrong outer contract.
        index = start + length
    if not objects:
        return {"passed": None, "reason": "prose_requires_semantic_assessment"}
    if len(objects) != 1:
        return {"passed": False, "reason": "multiple_payloads_require_disambiguation"}
    result = grade_capture({"record": objects[0]}, "record", expected)
    if result["passed"] is None:
        return {"passed": False, "reason": "malformed_literal_json"}
    return {**result, "surrounding_prose_verified": False}
