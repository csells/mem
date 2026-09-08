"""Explicit model profiles for new experiments, independent of archived defaults.

The registry declares candidates, not authentication or qualification. A successful
launch must still produce the requested primary model's actual host receipt.
Prepare never launches inference and requires the caller's external sandbox.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

from membench.runner import memory_e2e_hosts, memory_unprompted_hosts
from membench.runner.memory_host_types import HostLaunch, HostObservation


@dataclass(frozen=True)
class ModelProfile:
    """A stable experiment identifier and an exact provider model identifier."""

    id: str
    host: str
    model: str
    reasoning_effort: str | None = None


PROFILES = MappingProxyType(
    {
        profile.id: profile
        for profile in (
            ModelProfile("codex-astra", "codex", "gpt-6-astra", "high"),
            ModelProfile("codex-sol", "codex", "gpt-5.6-sol", "high"),
            ModelProfile("codex-terra", "codex", "gpt-5.6-terra", "high"),
            ModelProfile("codex-luna", "codex", "gpt-5.6-luna", "high"),
            ModelProfile("claude-haiku", "claude", "claude-haiku-4-5-20251001"),
            ModelProfile("claude-sonnet", "claude", "claude-sonnet-5"),
            ModelProfile("claude-opus", "claude", "claude-opus-5"),
            ModelProfile("claude-fable", "claude", "claude-fable-5-1"),
            ModelProfile("opencode-qwen", "opencode", "ollama/qwen3-coder:30b-a3b-q8_0"),
            ModelProfile("zcode-glm", "zcode", "zai/glm-5.3"),
        )
    }
)


def get_profile(profile_id: str) -> ModelProfile:
    try:
        return PROFILES[profile_id]
    except KeyError:
        raise ValueError(f"Unknown explicit model profile: {profile_id}") from None


def _codex_options(argv: list[str], effort: str) -> list[str]:
    """Replace source-user effort/tier overrides without touching the source file."""
    result: list[str] = []
    index = 0
    while index < len(argv):
        if (
            argv[index] == "-c"
            and index + 1 < len(argv)
            and argv[index + 1].split("=", 1)[0] in {"model_reasoning_effort", "service_tier"}
        ):
            index += 2
        else:
            result.append(argv[index])
            index += 1
    # The final positional argument is the prompt. Default service tier is the
    # absence of an override under --ignore-user-config, not a provider alias.
    result[-1:-1] = ["-c", f"model_reasoning_effort={json.dumps(effort)}"]
    return result


def prepare(
    profile_id: str,
    local: Path,
    env: dict[str, str],
    prompt: str,
    mode: str = "isolated",
    budget: float = 1.50,
) -> HostLaunch:
    """Prepare one pinned candidate with unchanged host isolation guarantees."""
    profile = get_profile(profile_id)
    memory_unprompted_hosts._validate(local, mode, budget)
    if profile.host in {"claude", "codex"}:
        launch = memory_e2e_hosts.prepare_host(
            profile.host, local, env, prompt, profile.model, mode, budget
        )
    else:
        launch = memory_unprompted_hosts.prepare(
            profile.host, local, env, prompt, profile.model, mode, budget
        )
    settings = {
        **launch.public_settings,
        "model_profile": profile.id,
        "model_requested": profile.model,
        "model_choice": "Explicit candidate; actual primary receipt required",
        "qualification": "not implied by registry membership",
        "automatic_model_fallback_requested": False,
    }
    argv = list(launch.argv)
    if profile.host == "codex":
        if profile.reasoning_effort is None:
            raise ValueError("Codex profile must explicitly declare reasoning effort")
        argv = _codex_options(argv, profile.reasoning_effort)
        settings.update(
            reasoning_effort=profile.reasoning_effort,
            service_tier="default",
            reasoning_policy="fixed high across the four Codex candidates",
            helper_model_policy="multi_agent explicitly disabled",
        )
    elif profile.host == "claude":
        # The old adapter's static user-model label is unrelated to this request.
        settings.pop("configured_user_model", None)
        settings.update(
            reasoning_effort="host/model default; no effort override requested",
            helper_model_policy="host auxiliary models retained; inspect result.modelUsage",
        )
    else:
        settings["helper_model_policy"] = (
            "small_model pinned to primary"
            if profile.host == "opencode"
            else "existing GLM lite profile retained; inspect actual model-io evidence"
        )
    return replace(launch, argv=argv, env=dict(launch.env), public_settings=settings)


def observe(profile_id: str, stream: str, local: Path) -> HostObservation:
    """Keep protocol errors and reject missing, substituted, or mixed primaries."""
    profile = get_profile(profile_id)
    observed = memory_unprompted_hosts.observe(profile.host, stream, local)
    if profile.host == "claude":
        # Init includes a model selection; actual assistant messages also carry
        # model IDs. Auxiliary entries in result.modelUsage remain separate.
        assistant_models: set[str] = set()
        for line in stream.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue  # The underlying observer retains malformed-stream errors.
            if not isinstance(event, dict) or event.get("type") != "assistant":
                continue
            message = event.get("message")
            if isinstance(message, dict):
                model = message.get("model")
                if isinstance(model, str) and model:
                    assistant_models.add(model)
        if assistant_models != {profile.model}:
            return replace(
                observed,
                models=sorted(assistant_models),
                success=False,
                model_evidence="Claude assistant.message.model missing or mismatched",
                errors=[*observed.errors, "Claude assistant model receipt missing or mismatched"],
            )
        if observed.success:
            observed = replace(observed, model_evidence="Claude init and assistant.message.model")
    if observed.models == [profile.model]:
        return observed
    return replace(
        observed,
        success=False,
        errors=[*observed.errors, f"Actual primary model does not match profile {profile.id}"],
    )


def export_evidence(profile_id: str, local: Path, destination: Path) -> None:
    memory_unprompted_hosts.export_evidence(get_profile(profile_id).host, local, destination)
