"""Claude Code launch and observation for the common memory experiment.

The normal condition retains automatic memory's default enabled state in a new
isolated directory. User plugins, instructions and hooks are excluded in both
conditions. The model remains explicit rather than following an evolving alias.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from membench.runner.headless_agent import tool_calls_from_stream
from membench.runner.memory_host_types import HostLaunch, HostObservation
from membench.runner.memory_routes_runtime import subscription_token

EXECUTABLE = Path("/Users/csells/.local/bin/claude").resolve()
MODEL = "claude-sonnet-4-6"


def prepare(
    local: Path,
    env: dict[str, str],
    prompt: str,
    model: str,
    mode: str,
    budget: float,
) -> HostLaunch:
    if mode not in {"isolated", "normal"}:
        raise ValueError("Unknown native-memory condition")
    settings = {
        "autoMemoryEnabled": mode == "normal",
        "autoMemoryDirectory": str(local / "native"),
    }
    path = local / "config/host-settings.json"
    with path.open("x") as target:
        json.dump(settings, target)
    child_env = {**env, "CLAUDE_CODE_OAUTH_TOKEN": subscription_token()}
    return HostLaunch(
        argv=[
            str(EXECUTABLE),
            "-p",
            prompt,
            "--model",
            model,
            "--output-format",
            "stream-json",
            "--verbose",
            "--no-session-persistence",
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--setting-sources",
            "",
            "--settings",
            str(path),
            "--tools",
            "Bash,Read,Write,Edit",
            "--allowedTools",
            "Bash,Read,Write,Edit",
            "--permission-mode",
            "dontAsk",
            "--permission-prompts",
            "none",
            "--disable-slash-commands",
            "--no-chrome",
            "--max-turns",
            "18",
            "--max-budget-usd",
            str(budget),
        ],
        env=child_env,
        readable_roots=[EXECUTABLE.parent],
        public_settings={
            **settings,
            "native_default_enabled": True,
            "native_records": "native/",
            "auth": "existing subscription token, transient child environment",
            "user_customizations": False,
            "model_requested": model,
            "configured_user_model": "claude-fable-5-1[1m]",
            "model_choice": "Sonnet 4.6 retained as the preceding experiment's anchor",
            "max_turns": 18,
            "max_budget_usd": budget,
        },
    )


def observe(stream: str, local: Path) -> HostObservation:
    del local
    events: list[dict[str, Any]] = []
    errors = []
    for index, line in enumerate(stream.splitlines()):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            errors.append(f"Non-JSON event at line {index + 1}")
            continue
        if not isinstance(event, dict):
            errors.append(f"Non-object event at line {index + 1}")
            continue
        events.append(event)
    starts = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
    ends = [e for e in events if e.get("type") == "result"]
    if len(starts) != 1:
        errors.append("Expected one actual Claude initialization")
    if len(ends) != 1:
        errors.append("Expected one terminal Claude result")
    start = starts[0] if len(starts) == 1 else {}
    end = ends[0] if len(ends) == 1 else {}
    session = start.get("session_id")
    model = start.get("model")
    if not isinstance(session, str) or not session:
        session = None
        errors.append("Actual session identity unavailable")
    models = [model] if isinstance(model, str) and model else []
    if not models:
        errors.append("Actual primary model unavailable")
    cost = end.get("total_cost_usd")
    usage = end.get("modelUsage", {})
    return HostObservation(
        session_id=session,
        models=models,
        calls=tool_calls_from_stream(stream),
        completed=len(ends) == 1,
        success=bool(len(ends) == 1 and not end.get("is_error") and not errors),
        cost_usd=(
            float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None
        ),
        usage=usage if isinstance(usage, dict) else {},
        errors=errors + ([str(end.get("subtype"))] if end.get("is_error") else []),
        model_evidence="actual system/init model; helper usage retained separately",
    )
