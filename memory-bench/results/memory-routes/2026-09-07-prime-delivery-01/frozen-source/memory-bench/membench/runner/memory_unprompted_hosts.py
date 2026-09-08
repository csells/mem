"""Project-enabled host adapters for qualification of the four-CLI experiment.

These adapters require the caller's external filesystem sandbox. Authentication
is transient; neither launch.env nor private auth files belong in reports.
Previous experiment adapters and frozen source are deliberately unchanged.
"""

from __future__ import annotations

import json
import math
import shlex
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from membench.runner import memory_e2e_hosts, memory_host_codex, memory_host_other
from membench.runner.memory_host_types import HostLaunch, HostObservation
from membench.schemas.trace import ToolCall

MODELS = {
    "claude": "claude-sonnet-4-6",
    "codex": "gpt-6-astra",
    "opencode": "ollama/qwen3-coder:30b-a3b-q8_0",
    "zcode": "zai/glm-5.3",
}
ZCODE = Path("/opt/homebrew/bin/zcode").resolve()
OPENCODE = Path("/opt/homebrew/bin/opencode").resolve()


def _json(path: Path, value: Any) -> None:
    with path.open("x") as target:
        json.dump(value, target, indent=2)
        target.write("\n")


def _validate(local: Path, mode: str, budget: float) -> None:
    if mode not in {"isolated", "normal"} or not math.isfinite(budget) or budget <= 0:
        raise ValueError("Expected declared native mode and finite positive budget")
    repo = Path(__file__).resolve().parents[3]
    if local.resolve().is_relative_to(repo) or local.resolve() == Path.home():
        raise ValueError("Host state must be in separate scratch storage")
    for name in ("work", "config", "tmp", "bin", "native"):
        if not (local / name).is_dir():
            raise ValueError(f"Missing session directory: {name}")


def prepare(
    host: str,
    local: Path,
    env: dict[str, str],
    prompt: str,
    model: str,
    mode: str = "isolated",
    budget: float = 1.50,
) -> HostLaunch:
    _validate(local, mode, budget)
    if host not in MODELS or model != MODELS[host]:
        raise ValueError("Explicit qualified candidate model required")
    if host in {"claude", "codex"}:
        return memory_e2e_hosts.prepare_host(host, local, env, prompt, model, mode, budget)
    if host == "opencode":
        return _opencode(local, env, prompt, model, mode, budget)
    return _zcode(local, env, prompt, model, mode, budget)


def _opencode(
    local: Path,
    env: dict[str, str],
    prompt: str,
    model: str,
    mode: str,
    budget: float,
) -> HostLaunch:
    provider = memory_host_other._provider()
    endpoint = env.get("MEMBENCH_OLLAMA_BASE_URL", provider["options"]["baseURL"])
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("OpenCode qualification uses only an existing local model")
    provider["options"] = {"baseURL": endpoint}
    provider["models"][model.split("/", 1)[1]]["limit"] = {
        "context": 32768,
        "output": 8192,
    }
    config = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {"ollama": provider},
        "enabled_providers": ["ollama"],
        "model": model,
        "small_model": model,
        "autoupdate": False,
        "share": "disabled",
        "mcp": {},
        "plugin": [],
        "permission": "allow",
        "skills": {"paths": [str((local / "work/.agents/skills").resolve())]},
    }
    settings = local / "config/host-settings.json"
    _json(settings, config)
    prompt_file = local / "config/prompt.txt"
    with prompt_file.open("x") as target:
        target.write(prompt)
    child = dict(env)
    for kind in ("config", "data", "cache", "state"):
        child[f"XDG_{kind.upper()}_HOME"] = str(local / "config" / kind)
    child.update(
        {
            "OPENCODE_CONFIG": str(settings),
            "OPENCODE_CONFIG_DIR": str(local / "config/opencode-dir"),
            "OPENCODE_DISABLE_PROJECT_CONFIG": "false",
            "OPENCODE_DISABLE_CLAUDE_CODE": "true",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
            "OPENCODE_DISABLE_MODELS_FETCH": "true",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
            "OPENCODE_DISABLE_SHARE": "true",
            "npm_config_offline": "true",
            "npm_config_cache": str(local / "config/npm-cache"),
            "NO_COLOR": "1",
        }
    )
    args = [
        str(OPENCODE),
        "run",
        "--model",
        model,
        "--format",
        "json",
        "--pure",
        "--auto",
        "--dir",
        str((local / "work").resolve()),
    ]
    # Positional run arguments are quoted by the host; stdin preserves prompt bytes.
    command = "exec " + shlex.join(args) + " < " + shlex.quote(str(prompt_file))
    return HostLaunch(
        argv=["/bin/sh", "-c", command],
        env=child,
        readable_roots=[OPENCODE.parent],
        public_settings={
            "host": "opencode",
            "model_requested": model,
            "mode": mode,
            "endpoint": endpoint,
            "client_context_limit": 32768,
            "runtime_context": "must be observed independently; client limit is not proof",
            "project_instructions": True,
            "project_skills": "explicit project skill root",
            "native_memory": "no separate automatic extractor configured; repository retained",
            "native_modes_equivalent": True,
            "user_customizations": False,
            "budget_enforced_by_cli": False,
            "requested_budget_usd": budget,
            "auth": "existing local Ollama model; no remote credential",
        },
    )


def _zcode(
    local: Path,
    env: dict[str, str],
    prompt: str,
    model: str,
    mode: str,
    budget: float,
) -> HostLaunch:
    source = json.loads((Path.home() / ".zcode/cli/config.json").read_text())
    provider = source["provider"]["zai"]
    key = provider.get("options", {}).get("apiKey")
    if provider.get("kind") != "anthropic" or not isinstance(key, str) or not key.strip():
        raise RuntimeError("Existing zcode Z.AI API-key profile unavailable")
    if source.get("model", {}).get("main") != model:
        raise RuntimeError("Configured zcode primary model differs from the candidate")
    safe_provider = json.loads(json.dumps(provider))
    safe_provider["options"].pop("apiKey", None)
    if safe_provider.get("headers"):
        raise ValueError("Custom provider headers require separate secret handling")
    # A credential-free project config is the public CLI's supported override.
    # Storage paths are per-session environment overrides, not edits to this file.
    project_config = {
        "provider": {"zai": safe_provider},
        "model": {"main": model, "lite": source["model"]["lite"]},
        "features": {
            "memory": mode == "normal",
            "skill": True,
            "mcp": False,
            "subagent": False,
            "rewind": False,
            "compact": True,
        },
        "memory": {"use": mode == "normal"},
        "plugins": {"enabled": False, "dirs": [], "enabledPlugins": {}},
        "skills": {
            "enabled": True,
            "includeInstructions": True,
            "roots": [str((local / "work/.agents/skills").resolve())],
        },
        "mcp": {"servers": {}},
        "hooks": {"enabled": False},
        "logging": {"level": "warn", "format": "json"},
    }
    config = local / "work/zcode.json"
    if config.exists():
        if json.loads(config.read_text()) != project_config:
            raise ValueError("Existing project host settings differ; preserve and inspect")
    else:
        _json(config, project_config)
    child = dict(env)
    child.update(
        {
            "ZCODE_API_KEY": key,
            "ZCODE_STORAGE_DIR": str(local / "native"),
            "ZCODE_SESSION_DB_PATH": str(local / "config/session.sqlite"),
            "ZCODE_DATA_BASE_DIR": str(local / "config/shared-data"),
            "ZCODE_LOG_DIR": str(local / "config/logs"),
            "ZCODE_MODEL_TELEMETRY_ENABLED": "false",
            "ZCODE_DISABLE_UPDATE_CHECK": "1",
            "NO_UPDATE_NOTIFIER": "1",
            "ZCODE_MODEL_RETRY_MAX_RETRIES": "0",
            "NO_COLOR": "1",
        }
    )
    return HostLaunch(
        argv=[
            str(ZCODE),
            "--prompt",
            prompt,
            "--output-format",
            "stream-json",
            "--mode",
            "yolo",
            "--cwd",
            str((local / "work").resolve()),
            "--no-color",
        ],
        env=child,
        readable_roots=[ZCODE.parent.parent],
        public_settings={
            "host": "zcode",
            "model_requested": model,
            "lite_model": source["model"]["lite"],
            "mode": mode,
            "project_instructions": "native AGENTS.md",
            "project_skills": "explicit project root",
            "auth": "existing Z.AI key, transient child environment only",
            "native_memory": "feature/use disabled" if mode == "isolated" else "headless defaults",
            "headless_extraction_enabled": False,
            "native_limit": "runtime headless entry disables extraction even under normal settings",
            "native_records": str(local / "native"),
            "user_customizations": False,
            "budget_enforced_by_cli": False,
            "requested_budget_usd": budget,
        },
    )


def observe(host: str, stream: str, local: Path) -> HostObservation:
    if host in {"claude", "codex"}:
        return memory_e2e_hosts.observe_host(host, stream, local)
    if host == "opencode":
        return memory_host_other.observe(host, stream, local)
    if host != "zcode":
        raise ValueError("Unknown host")
    return observe_zcode(stream)


def observe_zcode(stream: str) -> HostObservation:
    events, errors = memory_host_other._events(stream)
    ends = [e for e in events if e.get("type") == "result"]
    end = ends[0] if len(ends) == 1 else {}
    session = end.get("sessionId")
    if not isinstance(session, str) or not session:
        session = None
        errors.append("Missing actual zcode terminal session identity")
    if len(ends) != 1 or not events or events[-1] is not end:
        errors.append("Expected one final zcode result")
    starts: dict[str, tuple[int, dict[str, Any]]] = {}
    calls: list[ToolCall] = []
    models: set[str] = set()
    complete_turns = 0
    for i, event in enumerate(events):
        if event.get("sessionId") != session:
            errors.append("zcode event session differs from terminal identity")
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        if event.get("type") == "turn.completed":
            complete_turns += 1
        if event.get("type") in {"turn.failed", "permission.requested"}:
            errors.append("zcode turn failed or required interactive permission")
        # Sanitized model_request payloads expose the actual requested model ref.
        ref = payload.get("modelRef")
        if isinstance(ref, dict):
            provider, model = ref.get("providerId", ref.get("provider")), ref.get(
                "modelId", ref.get("model")
            )
            if isinstance(provider, str) and isinstance(model, str):
                models.add(provider + "/" + model)
        if event.get("type") != "tool.updated":
            continue
        identity = payload.get("toolCallId")
        if not isinstance(identity, str):
            continue
        kind = payload.get("kind")
        if kind == "scheduled":
            if identity in starts:
                errors.append("Repeated zcode tool identity")
            starts[identity] = (i, payload)
        elif kind == "started":
            old = starts.get(identity, (i, {}))
            starts[identity] = (old[0], {**old[1], **payload})
        elif kind in {"result", "error"}:
            start = starts.pop(identity, None)
            if not start:
                errors.append("zcode tool result lacks a start")
                continue
            args = start[1].get("input", start[1].get("arguments", {}))
            result = payload.get("result", {})
            output = result.get("content") if isinstance(result, dict) else None
            if kind == "error":
                output = json.dumps(payload.get("error"), ensure_ascii=False)
            if not isinstance(output, str) or not isinstance(args, dict):
                errors.append("zcode tool output or arguments unavailable")
                continue
            name = start[1].get("toolName")
            if not isinstance(name, str):
                errors.append("zcode tool name unavailable")
                continue
            calls.append(
                ToolCall(
                    name=name,
                    tool_use_id=identity,
                    tool_use_index=start[0],
                    tool_result_index=i,
                    arguments=args,
                    result=output,
                    is_error=kind == "error",
                    latency_ms=0,
                )
            )
    if starts:
        errors.append("zcode has unfinished tool calls")
    if not models:
        errors.append("Actual zcode model identity unavailable")
    completed = complete_turns == 1 and len(ends) == 1
    if not completed:
        errors.append("Expected one completed fresh zcode turn")
    usage = end.get("usage", {})
    return HostObservation(
        session_id=session,
        models=sorted(models),
        calls=calls,
        completed=completed,
        success=completed and not errors,
        usage=usage if isinstance(usage, dict) else {},
        cost_usd=None,
        errors=errors,
        model_evidence="actual model_request modelRef events",
    )


def export_evidence(host: str, local: Path, destination: Path) -> None:
    if host == "codex":
        memory_host_codex.export_evidence(local, destination)
    elif host == "opencode":
        memory_host_other.export_evidence(local, destination)
    else:
        destination.mkdir(exist_ok=False)
        _json(destination / "source.json", {"source": "archived CLI event stream"})
