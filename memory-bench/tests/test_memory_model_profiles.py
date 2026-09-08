"""Exact model requests and observed receipts are separate qualification facts."""

import json
from pathlib import Path

import pytest

from membench.runner import memory_host_claude, memory_host_codex, memory_model_profiles
from membench.runner import memory_unprompted_hosts as legacy
from membench.runner.memory_host_types import HostObservation


def local_dirs(tmp_path: Path) -> Path:
    local = tmp_path / "session"
    for name in ("work", "config", "tmp", "bin", "native"):
        (local / name).mkdir(parents=True)
    return local


def test_registry_is_explicit_immutable_and_preserves_archived_anchor() -> None:
    assert len(memory_model_profiles.PROFILES) == 10
    assert legacy.MODELS["claude"] == "claude-sonnet-4-6"
    assert memory_model_profiles.get_profile("claude-sonnet").model == "claude-sonnet-5"
    with pytest.raises(TypeError):
        memory_model_profiles.PROFILES["new"] = object()
    with pytest.raises(ValueError, match="Unknown explicit"):
        memory_model_profiles.get_profile("sonnet")


@pytest.mark.parametrize("profile_id", ["codex-astra", "codex-sol", "codex-terra", "codex-luna"])
def test_codex_pins_model_and_effort_without_mutating_user_config(
    profile_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    config = 'model="other"\nmodel_reasoning_effort="low"\nservice_tier="fast"\n'
    (source / "config.toml").write_text(config)
    auth = '{"auth_mode":"chatgpt","tokens":{"access_token":"private-test-token"}}'
    (source / "auth.json").write_text(auth)
    monkeypatch.setattr(memory_host_codex, "_source_home", lambda: source)
    local = local_dirs(tmp_path)
    prompt = "literal prompt; preserve `quotes` and $variables"
    launch = memory_model_profiles.prepare(profile_id, local, {}, prompt)
    profile = memory_model_profiles.get_profile(profile_id)
    assert launch.argv[launch.argv.index("--model") + 1] == profile.model
    assert [arg for arg in launch.argv if arg.startswith("model_reasoning_effort=")] == [
        'model_reasoning_effort="high"'
    ]
    assert not any(arg.startswith("service_tier=") for arg in launch.argv)
    assert launch.argv[-1] == prompt
    assert "--ignore-user-config" in launch.argv
    assert "project_doc_max_bytes=32768" in launch.argv
    assert "memories.generate_memories=false" in launch.argv
    assert launch.public_settings["service_tier"] == "default"
    assert (source / "config.toml").read_text() == config
    assert (source / "auth.json").read_text() == auth
    assert (local / "config/auth.json").stat().st_mode & 0o777 == 0o600
    assert "private-test-token" not in json.dumps(launch.public_settings)


@pytest.mark.parametrize(
    "profile_id", ["claude-haiku", "claude-sonnet", "claude-opus", "claude-fable"]
)
def test_claude_requests_exact_model_without_fallback_or_stale_anchor_label(
    profile_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(memory_host_claude, "subscription_token", lambda: "private-test-token")
    launch = memory_model_profiles.prepare(profile_id, local_dirs(tmp_path), {}, "task")
    assert (
        launch.argv[launch.argv.index("--model") + 1]
        == memory_model_profiles.get_profile(profile_id).model
    )
    assert "--fallback-model" not in launch.argv
    assert launch.argv[launch.argv.index("--max-budget-usd") + 1] == "1.5"
    assert launch.argv[launch.argv.index("--setting-sources") + 1] == "project"
    assert "Sonnet 4.6" not in json.dumps(launch.public_settings)
    assert "configured_user_model" not in launch.public_settings
    assert "private-test-token" not in json.dumps(launch.public_settings)


@pytest.mark.parametrize("models", [[], ["claude-sonnet-4-6"], ["claude-sonnet-5", "other"]])
def test_wrong_or_missing_primary_never_qualifies(
    models: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = HostObservation("session", models, [], True, True, errors=["existing error"])
    monkeypatch.setattr(legacy, "observe", lambda *_: original)
    stream = json.dumps({"type": "assistant", "message": {"model": "claude-sonnet-5"}})
    observed = memory_model_profiles.observe("claude-sonnet", stream, tmp_path)
    assert not observed.success
    assert observed.models == models
    assert observed.errors[0] == "existing error"
    assert len(observed.errors) == 2
    assert original.success  # Observation inputs are not changed in place.


def test_matching_primary_preserves_protocol_failure_and_auxiliary_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = HostObservation(
        "session",
        ["claude-sonnet-5"],
        [],
        True,
        False,
        usage={"claude-haiku-4-5-20251001": {"inputTokens": 123}},
        errors=["protocol failure"],
    )
    monkeypatch.setattr(legacy, "observe", lambda *_: original)
    stream = json.dumps({"type": "assistant", "message": {"model": "claude-sonnet-5"}})
    assert memory_model_profiles.observe("claude-sonnet", stream, tmp_path) is original


@pytest.mark.parametrize("actual", [None, "claude-opus-5", "claude-sonnet-5"])
def test_claude_init_model_alone_is_not_an_actual_assistant_receipt(
    actual: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = HostObservation("session", ["claude-sonnet-5"], [], True, True)
    monkeypatch.setattr(legacy, "observe", lambda *_: original)
    stream = json.dumps({"type": "assistant", "message": {"model": actual}})
    observed = memory_model_profiles.observe("claude-sonnet", stream, tmp_path)
    assert observed.success is (actual == "claude-sonnet-5")
    if actual != "claude-sonnet-5":
        assert observed.models == ([] if actual is None else [actual])
        assert observed.models != [memory_model_profiles.get_profile("claude-sonnet").model]


def test_mixed_actual_claude_primaries_trigger_model_identity_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = HostObservation("session", ["claude-sonnet-5"], [], True, True)
    monkeypatch.setattr(legacy, "observe", lambda *_: original)
    models = ["claude-sonnet-5", "claude-opus-5"]
    stream = "\n".join(
        json.dumps({"type": "assistant", "message": {"model": model}}) for model in models
    )
    observed = memory_model_profiles.observe("claude-sonnet", stream, tmp_path)
    assert not observed.success
    assert observed.models == sorted(models)
    assert observed.models != [memory_model_profiles.get_profile("claude-sonnet").model]


def test_failed_claude_host_does_not_hide_actual_model_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = HostObservation(
        "session", ["claude-sonnet-5"], [], True, False, errors=["terminal failure"]
    )
    monkeypatch.setattr(legacy, "observe", lambda *_: original)
    stream = "malformed line\n[]\n" + json.dumps(
        {"type": "assistant", "message": {"model": "claude-opus-5"}}
    )
    observed = memory_model_profiles.observe("claude-sonnet", stream, tmp_path)
    assert not observed.success
    assert observed.models == ["claude-opus-5"]
    assert observed.errors[0] == "terminal failure"
