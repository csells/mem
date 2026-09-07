"""Project-enabled profiles; the previous experiment's adapters remain unchanged."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from membench.runner import memory_host_claude, memory_host_codex
from membench.runner.memory_host_types import HostLaunch, HostObservation


def enable_project(host: str, launch: HostLaunch) -> HostLaunch:
    argv = list(launch.argv)
    if host == "claude":
        argv.remove("--disable-slash-commands")
        argv[argv.index("--setting-sources") + 1] = "project"
        for flag in ("--tools", "--allowedTools"):
            argv[argv.index(flag) + 1] = "Bash,Read,Write,Edit,Glob,Grep,Skill"
        # More room for actual feature work, still bounded by time and USD limits.
        if "--max-turns" in argv:
            argv[argv.index("--max-turns") + 1] = "30"
    elif host == "codex":
        argv.remove("--ignore-rules")
        argv[argv.index("project_doc_max_bytes=0")] = "project_doc_max_bytes=32768"
    else:
        raise ValueError(f"No qualified E2E adapter for {host}")
    settings = {
        **launch.public_settings,
        "project_instructions": True,
        "project_skills": True,
        "user_customizations": False,
        "workflow_restoration": "project rule invokes prime; no automatic capture hook",
    }
    if host == "claude":
        settings["max_turns"] = 30
    return replace(launch, argv=argv, env=dict(launch.env), public_settings=settings)


def prepare_host(
    host: str,
    local: Path,
    env: dict[str, str],
    prompt: str,
    model: str,
    mode: str,
    budget: float,
) -> HostLaunch:
    if host == "claude":
        launch = memory_host_claude.prepare(local, env, prompt, model, mode, budget)
    elif host == "codex":
        launch = memory_host_codex.prepare(local, env, prompt, model, mode, budget)
    else:
        raise ValueError(f"No qualified E2E adapter for {host}")
    return enable_project(host, launch)


def observe_host(host: str, stream: str, local: Path) -> HostObservation:
    if host == "claude":
        return memory_host_claude.observe(stream, local)
    if host == "codex":
        return memory_host_codex.observe(stream, local)
    raise ValueError(f"No qualified E2E adapter for {host}")
