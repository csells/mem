"""Shared parsers for ``claude`` CLI replies.

These two helpers were copy-pasted across ``grading``, ``bbon``, and ``oracle``
(each kept its own copy to avoid one subpackage importing another). They live
here at the package root so every caller depends on a neutral module instead,
with no cross-subpackage coupling.
"""

from __future__ import annotations

import json
from collections.abc import Mapping


def unwrap_cli_json(stdout: str) -> str:
    """The model text from ``claude --output-format json`` stdout: the wrapper's
    ``result`` field, or the raw stdout when it is not the documented wrapper (so a
    plain-text reply still parses downstream)."""
    try:
        wrapper = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout
    if isinstance(wrapper, Mapping) and isinstance(wrapper.get("result"), str):
        return str(wrapper["result"])
    return stdout


def first_json_object(text: str) -> str | None:
    """The first balanced ``{...}`` block in ``text``, tolerating surrounding prose
    and braces inside string literals (port of tom-swe's `extractFirstJsonObject`)."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
        elif in_string:
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
