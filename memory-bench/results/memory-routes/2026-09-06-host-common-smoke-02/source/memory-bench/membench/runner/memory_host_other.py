"""Installed OpenCode boundary; Gemini and Copilot retain explicit blockers.

OpenCode JSON events omit model identity, so actual assistant rows from its own
scratch database supply it. The evidence export selects identity fields only;
credentials, prompts, conversation text and database state never cross sessions.
Transport completion is independent of the experiment's artifact oracle.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from membench.runner.memory_host_types import HostLaunch, HostObservation
from membench.schemas.trace import ToolCall

EXECUTABLE = Path("/opt/homebrew/bin/opencode").resolve()
MODEL = "ollama/qwen3-coder:30b-a3b-q8_0"
MODEL_ID = MODEL.split("/", 1)[1]
BLOCKERS = {
    "gemini": "Gemini existing API key returned HTTP 429: prepayment credits depleted",
    "copilot": "Installed VS Code launcher cannot find the actual GitHub Copilot CLI",
}
_EVIDENCE = "opencode-models.json"
_SCHEMA = "memory-host-opencode-models.v1"


def _check_host(host: str) -> None:
    if host in BLOCKERS:
        raise RuntimeError(BLOCKERS[host])
    if host != "opencode":
        raise ValueError("Unknown other CLI host")


def _provider() -> dict[str, Any]:
    """Read only the configured local route, refusing new providers or secrets."""
    source = Path.home() / ".config/opencode/opencode.json"
    configured = json.loads(source.read_text())["provider"]["ollama"]
    options = configured.get("options", {})
    if (
        configured.get("npm") != "@ai-sdk/openai-compatible"
        or options != {"baseURL": "http://localhost:11434/v1"}
        or MODEL_ID not in configured.get("models", {})
    ):
        raise RuntimeError("Existing local OpenCode provider configuration has changed")
    return {
        "npm": configured["npm"],
        "name": "Ollama (existing local route)",
        "options": options,
        "models": {MODEL_ID: {"name": MODEL_ID}},
    }


def prepare(
    host: str,
    local: Path,
    env: dict[str, str],
    prompt: str,
    model: str,
    mode: str,
    budget: float,
) -> HostLaunch:
    _check_host(host)
    if mode not in {"isolated", "normal"}:
        raise ValueError("Unknown native-memory condition")
    if model != MODEL:
        raise ValueError("OpenCode must use the existing configured local model")
    child_env = dict(env)
    for kind in ("config", "data", "cache", "state"):
        child_env[f"XDG_{kind.upper()}_HOME"] = str(local / "config" / kind)
    child_env.update(
        {
            "OPENCODE_CONFIG": str(local / "config/host-settings.json"),
            "OPENCODE_CONFIG_DIR": str(local / "config/opencode-dir"),
            "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE": "true",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
            "OPENCODE_DISABLE_MODELS_FETCH": "true",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
            "OPENCODE_DISABLE_SHARE": "true",
            # The CLI attempts a background plugin dependency setup even --pure.
            # Keep that attempt offline and unable to touch the user's npm cache.
            "npm_config_offline": "true",
            "npm_config_cache": str(local / "config/npm-cache"),
            "NO_COLOR": "1",
        }
    )
    native_links = {
        local / "work/AGENTS.md": local / "native/project/AGENTS.md",
        local / "config/config/opencode/AGENTS.md": local / "native/global/AGENTS.md",
    }
    if mode == "normal":
        for link, target in native_links.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.touch(exist_ok=False)
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target)
    config = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {"ollama": _provider()},
        "enabled_providers": ["ollama"],
        "model": model,
        "autoupdate": False,
        "share": "disabled",
        "mcp": {},
        "plugin": [],
        "permission": "allow",
    }
    with (local / "config/host-settings.json").open("x") as target:
        json.dump(config, target)
    return HostLaunch(
        argv=[
            str(EXECUTABLE),
            "run",
            prompt,
            "--model",
            model,
            "--format",
            "json",
            "--pure",
            "--auto",
            "--dir",
            str(local / "work"),
        ],
        env=child_env,
        readable_roots=[EXECUTABLE.parent],
        public_settings={
            "model_requested": model,
            "auth": "existing local Ollama endpoint; no remote credential",
            "native_default": "AGENTS.md instruction discovery; no automatic extractor verified",
            "native_records": "native/project/AGENTS.md and native/global/AGENTS.md",
            "native_enabled": mode == "normal",
            "native_empty_scaffolds": 2 if mode == "normal" else 0,
            "user_customizations": False,
            "runtime_context_observed_in_smoke": 4096,
            "context_override": None,
            "max_budget_usd_requested": budget,
            "budget_enforced_by_cli": False,
            "cost_scope": "CLI provider cost; local compute cost is unmeasured",
        },
    )


def _database_projection(local: Path) -> dict[str, Any]:
    path = local / "config/data/opencode/opencode.db"
    rows: list[dict[str, Any]] = []
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as connection:
        for identity, session, raw in connection.execute(
            "SELECT id, session_id, data FROM message ORDER BY time_created, id"
        ):
            data = json.loads(raw)
            if data.get("role") != "assistant":
                continue
            rows.append(
                {
                    "id": identity,
                    "session_id": session,
                    "role": "assistant",
                    "provider_id": data.get("providerID"),
                    "model_id": data.get("modelID"),
                    "finish": data.get("finish"),
                }
            )
    return {"schema": _SCHEMA, "source": "OpenCode message table assistant rows", "rows": rows}


def export_evidence(local: Path, destination: Path) -> None:
    """Archive a new identity-only projection, never an auth-bearing raw database."""
    projection = _database_projection(local)
    destination.mkdir(parents=True, exist_ok=False)
    with (destination / _EVIDENCE).open("x") as target:
        json.dump(projection, target, indent=2)


def _model_rows(local: Path) -> list[dict[str, Any]]:
    archived = local / _EVIDENCE
    data = json.loads(archived.read_text()) if archived.exists() else _database_projection(local)
    if not isinstance(data, dict) or data.get("schema") != _SCHEMA:
        raise ValueError("Invalid OpenCode model evidence schema")
    rows = data.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Invalid OpenCode model evidence rows")
    return rows


def _events(stream: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, line in enumerate(stream.splitlines()):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            errors.append(f"Non-JSON event at line {index + 1}")
            continue
        if not isinstance(row, dict):
            errors.append(f"Non-object event at line {index + 1}")
            continue
        rows.append(row)
    return rows, errors


def _call(event: dict[str, Any], index: int) -> ToolCall:
    part = event["part"]
    state = part["state"]
    identity, name, arguments = part["callID"], part["tool"], state["input"]
    if (
        not isinstance(identity, str)
        or not identity.strip()
        or not isinstance(name, str)
        or not isinstance(arguments, dict)
        or state.get("status") not in {"completed", "error"}
    ):
        raise ValueError("Invalid completed OpenCode tool event")
    output = state.get("output") if state["status"] == "completed" else state.get("error")
    if not isinstance(output, str):
        raise ValueError("Missing actual OpenCode tool output")
    arguments = dict(arguments)
    if "filePath" in arguments:
        arguments["file_path"] = arguments.pop("filePath")
    clock = state.get("time", {})
    start, end = clock.get("start"), clock.get("end")
    elapsed = end - start if type(start) is int and type(end) is int and end >= start else 0
    return ToolCall(
        name={"bash": "Bash", "write": "Write", "read": "Read", "edit": "Edit"}.get(name, name),
        tool_use_id=identity,
        # The combined event provides no independently observed start position.
        tool_use_index=None,
        tool_result_index=index,
        arguments=arguments,
        result=output,
        is_error=state["status"] == "error",
        latency_ms=elapsed,
    )


def observe(host: str, stream: str, local: Path) -> HostObservation:
    _check_host(host)
    events, errors = _events(stream)
    sessions = {
        event.get("sessionID") for event in events if isinstance(event.get("sessionID"), str)
    }
    session = next(iter(sessions)) if len(sessions) == 1 else None
    if not session or not session.strip():
        session = None
        errors.append("Expected one actual OpenCode session identity")
    calls: list[ToolCall] = []
    steps: list[dict[str, Any]] = []
    message_ids: set[str] = set()
    step_ids: set[str] = set()
    for index, event in enumerate(events):
        if event.get("type") == "error":
            errors.append("OpenCode emitted a session error")
        part = event.get("part")
        if not isinstance(part, dict):
            if event.get("type") != "error":
                errors.append("OpenCode event lacks a part")
            continue
        if part.get("sessionID") != session or event.get("sessionID") != session:
            errors.append("OpenCode event session identity mismatch")
        message = part.get("messageID")
        if not isinstance(message, str) or not message.strip():
            errors.append("OpenCode event lacks an actual message identity")
        else:
            message_ids.add(message)
        if event.get("type") == "tool_use":
            try:
                calls.append(_call(event, index))
            except (KeyError, TypeError, ValueError):
                errors.append("Malformed OpenCode tool event")
        if event.get("type") == "step_finish":
            identity = part.get("id")
            if not isinstance(identity, str) or identity in step_ids:
                errors.append("Missing or repeated OpenCode step identity")
            else:
                step_ids.add(identity)
            steps.append(part)
    if len({call.tool_use_id for call in calls}) != len(calls):
        errors.append("Repeated OpenCode tool identity")
    completed = bool(steps and steps[-1].get("reason") == "stop")
    if not completed:
        errors.append("OpenCode has no final stop result")
    if any(step.get("reason") == "stop" for step in steps[:-1]):
        errors.append("OpenCode emitted events after a completed step")
    models: list[str] = []
    try:
        rows = _model_rows(local)
        selected = [row for row in rows if row.get("session_id") == session]
        observed_ids = {row.get("id") for row in selected}
        if not message_ids or not message_ids.issubset(observed_ids):
            errors.append("Stream message identity missing from actual model evidence")
        for row in selected:
            if row.get("id") not in message_ids:
                continue
            provider, model = row.get("provider_id"), row.get("model_id")
            if (
                not isinstance(provider, str)
                or not provider
                or not isinstance(model, str)
                or not model
            ):
                errors.append("Actual OpenCode model identity unavailable")
                continue
            models.append(f"{provider}/{model}")
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
        errors.append("Actual OpenCode model evidence unavailable")
    if not models:
        errors.append("No actual OpenCode assistant model observed")
    costs = [part.get("cost") for part in steps]
    cost = (
        sum(float(value) for value in costs)
        if costs and all(type(v) in (int, float) for v in costs)
        else None
    )
    usage = {
        "steps": [
            {
                "message_id": part.get("messageID"),
                "tokens": part.get("tokens"),
                "cost": part.get("cost"),
            }
            for part in steps
        ],
        "scope": "Every emitted step; automatic title-helper usage is not emitted",
        "auxiliary_usage_known": False,
    }
    return HostObservation(
        session_id=session,
        models=sorted(set(models)),
        calls=calls,
        completed=completed,
        success=completed and not errors,
        usage=usage,
        cost_usd=cost,
        errors=errors,
        model_evidence="Actual OpenCode assistant message rows crossmatched to stream message IDs",
    )
