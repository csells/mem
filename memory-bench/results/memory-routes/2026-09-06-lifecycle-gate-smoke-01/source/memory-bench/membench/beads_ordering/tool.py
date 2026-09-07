from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from membench.beads_ordering.models import (
    BM25FConfig,
    ExperimentMode,
    OrderingArm,
    ToolLogEntry,
)

TOOL_CONFIG_ENV = "MEMBENCH_BEADS_TOOL_CONFIG"


class ToolConfig(BaseModel):
    """Hidden, run-specific configuration for the arm-neutral agent tool."""

    model_config = ConfigDict(frozen=True)

    beads_bin: str
    workspace: str
    query: str
    arm: OrderingArm
    page_size: int | str
    bm25f: BM25FConfig = Field(default_factory=BM25FConfig)
    log_path: str
    agent_started_monotonic_ns: int = Field(ge=0)
    max_tool_calls: int = Field(default=12, ge=1)
    mode: ExperimentMode = ExperimentMode.NAVIGATION


class BeadsToolError(RuntimeError):
    pass


def visible_page(raw: dict[str, Any], *, page_size_label: str) -> dict[str, Any]:
    """Return the sole compact page projection visible to the evaluated agent."""

    return {
        "items": raw.get("items", []),
        "query": raw.get("query", ""),
        "total_matched": raw.get("total_matched", 0),
        "page_size": page_size_label,
        "complete": raw.get("complete", False),
        "continuation_available": bool(raw.get("continuation")),
    }


def memory_references(value: str) -> tuple[str, ...]:
    """Read the deliberately small references list from fixture frontmatter."""

    if not value.startswith("---\n"):
        return ()
    end = value.find("\n---\n", 4)
    if end < 0:
        return ()
    for line in value[4:end].splitlines():
        name, separator, raw = line.partition(":")
        if separator and name.strip() == "references":
            raw = raw.strip()
            if not (raw.startswith("[") and raw.endswith("]")):
                return ()
            return tuple(part.strip() for part in raw[1:-1].split(",") if part.strip())
    return ()


def _unwrap(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise BeadsToolError("bd emitted a non-object JSON response")
    data = raw.get("data", raw)
    if not isinstance(data, dict):
        raise BeadsToolError("bd emitted a non-object data payload")
    return data


def _bd(config: ToolConfig, arguments: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        [config.beads_bin, "--json", *arguments],
        cwd=config.workspace,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
        env={**os.environ, "BD_JSON_ENVELOPE": "1"},
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise BeadsToolError(f"bd exited {completed.returncode}: {detail}")
    try:
        return _unwrap(json.loads(completed.stdout))
    except json.JSONDecodeError as exc:
        raise BeadsToolError("bd emitted malformed JSON") from exc


def _discovery_arguments(config: ToolConfig, continuation: str) -> list[str]:
    bm25f = config.bm25f
    arguments = [
        "memories",
        config.query,
        "--experimental-order",
        config.arm.value,
        "--page-size",
        str(config.page_size),
        "--bm25f-key-weight",
        str(bm25f.key_weight),
        "--bm25f-alias-weight",
        str(bm25f.alias_weight),
        "--bm25f-title-weight",
        str(bm25f.title_weight),
        "--bm25f-body-weight",
        str(bm25f.body_weight),
        "--bm25f-k1",
        str(bm25f.k1),
        "--bm25f-b",
        str(bm25f.b),
    ]
    if continuation:
        arguments.extend(("--continuation", continuation))
    return arguments


def _response_bytes(payload: dict[str, Any]) -> tuple[bytes, int]:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    return encoded, (len(encoded) + 3) // 4


def _existing_log_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _existing_logs(path: Path) -> tuple[ToolLogEntry, ...]:
    if not path.exists():
        return ()
    return tuple(
        ToolLogEntry.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _recall_access(config: ToolConfig, log_path: Path, memory_id: str) -> tuple[bool, bool]:
    logs = tuple(entry for entry in _existing_logs(log_path) if entry.error is None)
    visible = {
        candidate_id
        for entry in logs
        if entry.operation in {"search", "continue"}
        for candidate_id in entry.visible_ids
    }
    referenced = {
        target_id for entry in logs if entry.operation == "recall" for target_id in entry.references
    }
    allowed = memory_id in visible
    if config.mode is not ExperimentMode.SEARCH_ONLY:
        allowed = allowed or memory_id in referenced
    followed_reference = config.mode is not ExperimentMode.SEARCH_ONLY and memory_id in referenced
    return allowed, followed_reference


def _append_log(path: Path, entry: ToolLogEntry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry.model_dump_json())
        handle.write("\n")


def execute(
    config: ToolConfig, operation: str, argument: str = ""
) -> tuple[dict[str, Any], ToolLogEntry]:
    log_path = Path(config.log_path)
    sequence = _existing_log_count(log_path) + 1
    if sequence > config.max_tool_calls:
        raise BeadsToolError(f"retrieval tool budget exhausted ({config.max_tool_calls})")

    start_ns = time.monotonic_ns()
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    followed_reference = False
    try:
        if operation in {"search", "continue"}:
            prior_logs = _existing_logs(log_path)
            if operation == "search" and any(
                entry.operation == "search" and entry.error is None for entry in prior_logs
            ):
                raise BeadsToolError(
                    "search was already performed; use its continuation token or stop"
                )
            if operation == "continue":
                continuation = next(
                    (
                        entry.continuation
                        for entry in reversed(prior_logs)
                        if entry.operation in {"search", "continue"}
                        and entry.error is None
                        and entry.continuation
                    ),
                    "",
                )
                if not continuation:
                    raise BeadsToolError("no continuation is available from the prior page")
            else:
                continuation = ""
            raw = _bd(config, _discovery_arguments(config, continuation))
            payload = visible_page(raw, page_size_label=str(config.page_size))
            visible_ids = tuple(
                str(item.get("id", ""))
                for item in payload["items"]
                if isinstance(item, dict) and item.get("id")
            )
            total_matched = int(raw.get("total_matched", 0))
            references: tuple[str, ...] = ()
            memory_id = None
            candidate_ms = float(raw.get("candidate_generation_ms", 0))
            ordering_ms = float(raw.get("ordering_ms", 0))
            next_continuation = str(raw.get("continuation", ""))
        elif operation == "recall":
            if not argument:
                raise BeadsToolError("recall requires a Memory ID")
            allowed, followed_reference = _recall_access(config, log_path, argument)
            if not allowed:
                if config.mode is ExperimentMode.SEARCH_ONLY:
                    raise BeadsToolError(
                        "search-only mode permits recall only for a Memory shown by discovery"
                    )
                raise BeadsToolError(
                    "recall permits only a Memory shown by discovery or referenced by a "
                    "successfully recalled Memory"
                )
            raw = _bd(config, ["recall", argument])
            value = raw.get("value", "")
            if not raw.get("found") or not isinstance(value, str):
                raise BeadsToolError(f"Memory {argument!r} was not found")
            references = memory_references(value)
            payload = {
                "id": str(raw.get("key", argument)),
                "found": True,
                "body": value,
                "references": list(references),
            }
            visible_ids = ()
            total_matched = None
            memory_id = str(raw.get("key", argument))
            candidate_ms = 0.0
            ordering_ms = 0.0
            next_continuation = ""
        else:
            raise BeadsToolError("operation must be search, continue, or recall")
    except Exception as exc:
        elapsed_ms = (time.monotonic_ns() - start_ns) / 1_000_000
        error_payload = {"error": str(exc)}
        encoded, token_estimate = _response_bytes(error_payload)
        entry = ToolLogEntry(
            sequence=sequence,
            operation=operation,
            started_at=started_at,
            elapsed_ms=elapsed_ms,
            since_agent_start_ms=max(
                0.0, (start_ns - config.agent_started_monotonic_ns) / 1_000_000
            ),
            response_bytes=len(encoded),
            response_tokens_estimate=token_estimate,
            error=str(exc),
        )
        _append_log(log_path, entry)
        raise

    elapsed_ms = (time.monotonic_ns() - start_ns) / 1_000_000
    encoded, token_estimate = _response_bytes(payload)
    entry = ToolLogEntry(
        sequence=sequence,
        operation=operation,
        started_at=started_at,
        elapsed_ms=elapsed_ms,
        since_agent_start_ms=max(0.0, (start_ns - config.agent_started_monotonic_ns) / 1_000_000),
        response_bytes=len(encoded),
        response_tokens_estimate=token_estimate,
        visible_ids=visible_ids,
        total_matched=total_matched,
        continuation=next_continuation,
        memory_id=memory_id,
        references=references,
        followed_reference=followed_reference,
        server_candidate_generation_ms=candidate_ms,
        server_ordering_ms=ordering_ms,
    )
    _append_log(log_path, entry)
    return payload, entry


def _load_config() -> ToolConfig:
    path = os.environ.get(TOOL_CONFIG_ENV, "")
    if not path:
        raise BeadsToolError(f"{TOOL_CONFIG_ENV} is not set")
    try:
        return ToolConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BeadsToolError("cannot load the retrieval tool configuration") from exc


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print("usage: memory-tool search | continue | recall MEMORY_ID", file=sys.stderr)
        return 2
    operation = arguments[0]
    if operation == "search":
        argument = " ".join(arguments[1:])
    elif operation == "continue" and len(arguments) in {1, 2}:
        argument = arguments[1] if len(arguments) == 2 else ""
    elif len(arguments) == 2:
        argument = arguments[1]
    else:
        print("usage: memory-tool search | continue | recall MEMORY_ID", file=sys.stderr)
        return 2
    try:
        payload, _ = execute(_load_config(), operation, argument)
    except BeadsToolError as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 1
    sys.stdout.write(_response_bytes(payload)[0].decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
