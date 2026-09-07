"""JSON fixture loaders for the compare bridge — shared by the driver
(`scripts/run_compare_ours_mem0.py`) and the runnable example. Validation happens
at the boundary: a malformed row raises rather than seeding a half-built arm.

File shapes:
  corpus.json     list of {work_id, rig, text, closed?, convoy_id?, pr?,
                  external_ref?, supersedes?[]}
  queries.json    list of {work_id, rig, started, query_text, convoy_id?, pr?,
                  external_ref?}
  relevance.json  object {query_work_id: [relevant_work_id, ...]}
"""

from __future__ import annotations

import json
from pathlib import Path

from membench.validity import QueryWork, WorkRef


def _as_dict(value: object, ctx: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{ctx}: expected a JSON object, got {type(value).__name__}")
    return value


def _req_str(row: dict[str, object], key: str, ctx: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{ctx}: missing or non-string field {key!r}")
    return value


def _opt_str(row: dict[str, object], key: str, ctx: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{ctx}: field {key!r} must be a string when present")
    return value


def _str_list(value: object, ctx: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{ctx}: expected a JSON list of strings")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{ctx}: list entries must be strings")
        out.append(item)
    return out


def load_corpus(path: Path) -> tuple[list[WorkRef], dict[str, str]]:
    """Parse the corpus file into LOO WorkRefs + the per-work seed text."""
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: corpus must be a JSON list")
    refs: list[WorkRef] = []
    text: dict[str, str] = {}
    for i, entry in enumerate(raw):
        row = _as_dict(entry, f"{path}[{i}]")
        work_id = _req_str(row, "work_id", f"{path}[{i}]")
        refs.append(
            WorkRef(
                work_id=work_id,
                rig=_req_str(row, "rig", f"{path}[{i}]"),
                closed=_opt_str(row, "closed", f"{path}[{i}]"),
                convoy_id=_opt_str(row, "convoy_id", f"{path}[{i}]"),
                pr=_opt_str(row, "pr", f"{path}[{i}]"),
                external_ref=_opt_str(row, "external_ref", f"{path}[{i}]"),
                supersedes=tuple(_str_list(row.get("supersedes", []), f"{path}[{i}].supersedes")),
            )
        )
        text[work_id] = _req_str(row, "text", f"{path}[{i}]")
    return refs, text


def load_queries(path: Path) -> list[tuple[QueryWork, str]]:
    """Parse query works + their derived query_text (the string the semantic arm
    embeds; e.g. `B`'s failure message or title)."""
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: queries must be a JSON list")
    out: list[tuple[QueryWork, str]] = []
    for i, entry in enumerate(raw):
        row = _as_dict(entry, f"{path}[{i}]")
        query = QueryWork(
            work_id=_req_str(row, "work_id", f"{path}[{i}]"),
            rig=_req_str(row, "rig", f"{path}[{i}]"),
            started=_req_str(row, "started", f"{path}[{i}]"),
            convoy_id=_opt_str(row, "convoy_id", f"{path}[{i}]"),
            pr=_opt_str(row, "pr", f"{path}[{i}]"),
            external_ref=_opt_str(row, "external_ref", f"{path}[{i}]"),
        )
        out.append((query, _req_str(row, "query_text", f"{path}[{i}]")))
    return out


def load_relevance(path: Path) -> dict[str, list[str]]:
    raw = _as_dict(json.loads(path.read_text(encoding="utf-8")), str(path))
    return {key: _str_list(value, f"{path}[{key}]") for key, value in raw.items()}
