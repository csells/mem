"""Codex 0.153.4 boundary, verified with two isolated authenticated CLI smokes.

The caller must externally sandbox the returned launch. Auth is copied only into
its fresh private scratch config. Rollouts remain session-local for actual model
identity; only native memory paths may cross sessions. Exec JSON supplies tokens,
not a dollar charge. A requested dollar budget is therefore metadata, not a CLI cap.
"""

from __future__ import annotations

import json
import math
import os
import tomllib
from pathlib import Path
from typing import Any

from membench.runner.memory_host_types import HostLaunch, HostObservation
from membench.schemas.trace import ToolCall

BINARY = Path(
    "/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/"
    "codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex"
)


def _source_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()


def prepare(
    local: Path, env: dict[str, str], prompt: str, model: str, mode: str, budget: float
) -> HostLaunch:
    """Prepare a fresh session; the runner owns timeout and subprocess execution."""
    if mode not in {"isolated", "normal"} or not model.strip():
        raise ValueError("Codex requires isolated/normal mode and an explicit model")
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("A finite positive requested budget is required")
    if env.get("OPENAI_API_KEY") or env.get("CODEX_API_KEY"):
        raise ValueError("Refusing API-key override of subscription authentication")
    local = local.resolve()
    source = _source_home()
    source_repo = Path(__file__).resolve().parents[3]
    if (
        local == source
        or source.is_relative_to(local)
        or local.is_relative_to(source)
        or local.is_relative_to(source_repo)
    ):
        raise ValueError("Codex session must use separate scratch state")
    config = local / "config"
    if (config / "auth.json").exists():
        raise FileExistsError("Codex scratch authentication already exists")
    settings = tomllib.loads((source / "config.toml").read_text())
    effort = settings.get("model_reasoning_effort", "high")
    tier = settings.get("service_tier", "default")
    if not isinstance(effort, str) or not isinstance(tier, str):
        raise ValueError("Invalid configured Codex reasoning effort or service tier")
    try:
        auth_bytes = (source / "auth.json").read_bytes()
        auth = json.loads(auth_bytes)
        if (
            not isinstance(auth, dict)
            or auth.get("auth_mode") != "chatgpt"
            or auth.get("OPENAI_API_KEY")
            or not isinstance(auth.get("tokens"), dict)
            or not auth["tokens"].get("access_token")
        ):
            raise ValueError("unsupported auth")
    except (OSError, ValueError):
        raise RuntimeError("File-backed Codex ChatGPT authentication unavailable") from None
    for name in ("work", "config", "tmp", "bin", "native"):
        if not (local / name).is_dir():
            raise ValueError("Codex caller must provision all session directories")
    descriptor = os.open(config / "auth.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(auth_bytes)
    native = local / "native"
    (native / "memories").mkdir(exist_ok=True)
    (config / "memories").symlink_to(native / "memories", target_is_directory=True)
    (config / "memories_1.sqlite").symlink_to(native / "memories_1.sqlite")
    environment = {
        key: value
        for key, value in env.items()
        if not key.startswith(("OPENAI_", "CODEX_", "ANTHROPIC_", "CLAUDE_"))
    }
    environment.update(
        CODEX_HOME=str(config),
        TMPDIR=str(local / "tmp"),
        TMP=str(local / "tmp"),
        TEMP=str(local / "tmp"),
        XDG_CONFIG_HOME=str(config / "xdg"),
        XDG_CACHE_HOME=str(config / "cache"),
    )
    argv = [
        str(BINARY),
        "-a",
        "never",
        "-c",
        'cli_auth_credentials_store="file"',
        "-c",
        "check_for_update_on_startup=false",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox",
        "danger-full-access",
        "--json",
        "--color",
        "never",
        "--model",
        model,
        "-c",
        f"model_reasoning_effort={json.dumps(effort)}",
        "-c",
        "project_doc_max_bytes=0",
        "-c",
        'shell_environment_policy.inherit="all"',
    ]
    for feature in (
        "apps",
        "plugins",
        "browser_use",
        "computer_use",
        "multi_agent",
        "goals",
        "shell_snapshot",
    ):
        argv.extend(["--disable", feature])
    if tier != "default":
        argv.extend(["-c", f"service_tier={json.dumps(tier)}"])
    if mode == "isolated":
        argv.extend(
            [
                "--disable",
                "memories",
                "-c",
                "memories.generate_memories=false",
                "-c",
                "memories.use_memories=false",
            ]
        )
    argv.append(prompt)
    return HostLaunch(
        argv=argv,
        env=environment,
        readable_roots=[BINARY.parent],
        public_settings={
            "host": "codex",
            "mode": mode,
            "requested_model": model,
            "reasoning_effort": effort,
            "service_tier": tier,
            "native_feature_default": False,
            "native_generation_and_use": (
                "explicitly_disabled" if mode == "isolated" else "feature_off_default"
            ),
            "native_path": str(native),
            "fresh_rollouts_retained_for_model_identity": True,
            "requested_budget_usd": budget,
            "dollar_budget_enforced_by_cli": False,
            "auth": "scratch-only copy of existing ChatGPT auth; no API key",
            "known_host_diagnostic": "Host skill discovery may be denied by the outer sandbox",
        },
    )


def _rollout_models(local: Path, session_id: str | None) -> tuple[list[str], list[str]]:
    if session_id is None:
        return [], []
    models: set[str] = set()
    sources: list[str] = []
    root = (local / "config/sessions").resolve()
    if not root.is_relative_to(local.resolve()):
        raise ValueError("Codex session evidence escapes its scratch directory")
    for path in root.rglob("*.jsonl"):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        identities = [
            event.get("payload", {}).get("id")
            for event in events
            if isinstance(event, dict) and event.get("type") == "session_meta"
        ]
        if identities != [session_id]:
            continue
        for event in events:
            if event.get("type") == "turn_context":
                model = event.get("payload", {}).get("model")
                if isinstance(model, str) and model:
                    models.add(model)
                    sources.append(str(path.relative_to(local)))
    return sorted(models), sorted(set(sources))


def export_evidence(local: Path, destination: Path) -> None:
    """Archive only fresh rollout JSONL, preserving the layout used by observe.

    Call after the host process exits. Never copy the auth cache or whole config;
    reject credentials accidentally included in a rollout before writing anything.
    """
    if destination.exists():
        raise FileExistsError("Codex evidence destination already exists")
    local = local.resolve()
    root = local / "config/sessions"
    if root.is_symlink() or not root.resolve().is_relative_to(local):
        raise ValueError("Codex rollout evidence escapes scratch")
    secrets: list[bytes] = []
    auth_path = local / "config/auth.json"
    if auth_path.exists():
        auth = json.loads(auth_path.read_text())
        tokens = auth.get("tokens", {}) if isinstance(auth, dict) else {}
        if isinstance(tokens, dict):
            secrets = [
                value.encode()
                for value in tokens.values()
                if isinstance(value, str) and len(value) >= 12
            ]
    copies: list[tuple[Path, bytes]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Codex rollout evidence contains an external link")
        if not path.is_file() or path.suffix != ".jsonl":
            continue
        payload = path.read_bytes()
        if any(secret in payload for secret in secrets):
            raise ValueError("Codex rollout contains credential material; export refused")
        copies.append((path.relative_to(local), payload))
    destination.mkdir(parents=True, exist_ok=False)
    for relative, payload in copies:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(payload)


def observe(stream: str, local: Path) -> HostObservation:
    """Normalize real exec item IDs and line ordering without inferring missing calls."""
    local = local.resolve()
    errors: list[str] = []
    try:
        events = [json.loads(line) for line in stream.splitlines() if line.strip()]
        if any(not isinstance(event, dict) for event in events):
            raise ValueError("non-object event")
    except ValueError:
        return HostObservation(None, [], [], False, False, errors=["Invalid Codex JSONL stream"])
    identities = [
        event.get("thread_id") for event in events if event.get("type") == "thread.started"
    ]
    session_id = (
        identities[0]
        if len(identities) == 1 and isinstance(identities[0], str) and identities[0]
        else None
    )
    if session_id is None:
        errors.append("Missing or ambiguous Codex thread identity")
    calls: list[ToolCall] = []
    by_id: dict[str, ToolCall] = {}
    host_ids: list[dict[str, Any]] = []
    warnings: list[str] = []
    terminals = []
    for index, event in enumerate(events):
        event_type = event.get("type")
        if event_type in {"turn.completed", "turn.failed"}:
            terminals.append(event)
            if event_type == "turn.failed":
                errors.append("Codex turn failed: " + json.dumps(event.get("error")))
        elif event_type == "error":
            errors.append("Codex error: " + str(event.get("message", "unspecified")))
        if event_type not in {"item.started", "item.completed"}:
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            errors.append("Malformed Codex item")
            continue
        item_id = item.get("id")
        item_id = item_id if isinstance(item_id, str) and item_id else None
        kind = item.get("type")
        host_ids.append(
            {"event_index": index, "event_type": event_type, "item_id": item_id, "item_type": kind}
        )
        if kind == "error":
            warnings.append(str(item.get("message", "unspecified item warning")))
            continue
        if kind not in {"command_execution", "file_change"}:
            continue
        call = by_id.get(item_id) if item_id is not None else None
        if call is None:
            arguments: dict[str, Any]
            if kind == "command_execution":
                command = item.get("command")
                if not isinstance(command, str):
                    errors.append("Missing Codex command text")
                    continue
                name, arguments = "Bash", {"command": command}
            else:
                changes = item.get("changes")
                if (
                    isinstance(changes, list)
                    and len(changes) == 1
                    and isinstance(changes[0], dict)
                    and isinstance(changes[0].get("path"), str)
                ):
                    name, arguments = "Write", {"file_path": changes[0]["path"]}
                else:
                    name, arguments = "codex.file_change", {"changes": changes}
            call = ToolCall(
                name=name,
                arguments=arguments,
                tool_use_id=item_id,
                tool_use_index=index if event_type == "item.started" else None,
            )
            calls.append(call)
            if item_id is not None:
                by_id[item_id] = call
        elif event_type == "item.started" or call.tool_result_index is not None:
            errors.append("Duplicate Codex tool item identity")
        if kind == "command_execution" and call.arguments.get("command") != item.get("command"):
            errors.append("Codex command changed between start and finish")
        if event_type == "item.completed":
            call.tool_result_index = index
            if kind == "command_execution":
                output = item.get("aggregated_output")
                code = item.get("exit_code")
                if not isinstance(output, str) or type(code) is not int:
                    errors.append("Missing Codex completed command output/status")
                else:
                    call.result = output
                call.is_error = code != 0 or item.get("status") != "completed"
            else:
                call.result = json.dumps(item, ensure_ascii=True)
                call.is_error = item.get("status") != "completed"
    if len(terminals) > 1:
        errors.append("Multiple Codex terminal events")
    try:
        models, sources = _rollout_models(local, session_id)
    except (OSError, ValueError, TypeError, AttributeError):
        models, sources = [], []
        errors.append("Invalid Codex rollout model evidence")
    raw_usage = terminals[-1].get("usage", {}) if terminals else {}
    if not isinstance(raw_usage, dict):
        errors.append("Invalid Codex token usage")
        raw_usage = {}
    usage = dict(raw_usage)
    usage.update(host_event_ids=host_ids, host_warnings=warnings, model_evidence_paths=sources)
    return HostObservation(
        session_id=session_id,
        models=models,
        calls=calls,
        completed=bool(terminals),
        success=len(terminals) == 1 and terminals[0].get("type") == "turn.completed" and not errors,
        usage=usage,
        cost_usd=None,
        errors=errors,
        model_evidence="matching_rollout_turn_context" if models else "unobserved",
    )
