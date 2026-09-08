"""No-inference checks for future-only operational continuation."""

import importlib.util
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).with_name("continue_untouched.py")
SPEC = importlib.util.spec_from_file_location("prime_operational_continuation", MODULE_PATH)
continuation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(continuation)


def row(stage=1):
    return {"slot": f"example-{stage}", "lifecycle": "example", "stage": stage}


def test_completed_and_claimed_slots_are_never_selected_again(tmp_path):
    evidence = tmp_path / "cases/example/stage-1"
    evidence.mkdir(parents=True)
    (evidence / "process.json").write_text('{"pid":12345}')
    assert continuation.slot_disposition(tmp_path, row()) == "censored_existing_claim"
    (evidence / "result.json").write_text('{"artifact_passed":false}')
    assert continuation.slot_disposition(tmp_path, row()) == "preserved_result"
    assert (evidence / "process.json").read_text() == '{"pid":12345}'


def test_only_absent_destination_with_completed_predecessor_is_launchable(tmp_path):
    assert continuation.slot_disposition(tmp_path, row(1)) == "launch"
    assert continuation.slot_disposition(tmp_path, row(2)) == "censored_missing_predecessor"
    previous = tmp_path / "cases/example/stage-1"
    previous.mkdir(parents=True)
    (previous / "result.json").write_text('{"artifact_passed":false}')
    assert continuation.slot_disposition(tmp_path, row(2)) == "launch"
    assert continuation.slot_disposition(tmp_path, row(3)) == "censored_missing_predecessor"


def test_existing_lifecycle_without_a_session_directory_is_not_recreated(tmp_path):
    (tmp_path / "cases/example").mkdir(parents=True)
    assert continuation.slot_disposition(tmp_path, row()) == "censored_existing_lifecycle"


def test_durable_logging_requires_the_declared_regular_file(tmp_path):
    log = tmp_path / "console.log"
    with log.open("x") as f:
        continuation.assert_durable_output(log, (f.fileno(), f.fileno()))
        other = tmp_path / "different.log"
        other.write_text("existing")
        with pytest.raises(ValueError, match="declared"):
            continuation.assert_durable_output(other, (f.fileno(), f.fileno()))
    readfd, writefd = os.pipe()
    try:
        with pytest.raises(ValueError, match="regular"):
            continuation.assert_durable_output(log, (writefd, writefd))
    finally:
        os.close(readfd)
        os.close(writefd)


def test_exact_recovery_summary_requires_hash_bound_review(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "phase": "phase1",
                "operational_plan_sha256": "plan",
                "blocked_profiles": ["codex-astra"],
            }
        )
    )
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"approved": True, "summary_sha256": "stale"}))
    with pytest.raises(ValueError, match="exact"):
        continuation.prior_phase_gate("phase2", "plan", summary, review)
    review.write_text(json.dumps({"approved": True, "summary_sha256": continuation.sha(summary)}))
    assert continuation.prior_phase_gate("phase2", "plan", summary, review) == {"codex-astra"}


def test_no_original_failure_other_than_exact_broken_pipe_is_overridden(tmp_path):
    markers = tmp_path / "blocked"
    markers.mkdir()
    (markers / "codex-astra.json").write_text(
        json.dumps(
            {"type": "BrokenPipeError", "message": "[Errno 32] Broken pipe", "phase": "phase1"}
        )
    )
    continuation.original_logging_markers(tmp_path, ["codex-astra"])
    (markers / "codex-astra.json").write_text(
        json.dumps({"type": "RuntimeError", "message": "model mismatch", "phase": "phase1"})
    )
    with pytest.raises(ValueError, match="BrokenPipeError"):
        continuation.original_logging_markers(tmp_path, ["codex-astra"])


def test_detached_supervisor_log_survives_launcher_exit(tmp_path):
    log = tmp_path / "durable.log"
    child = tmp_path / "child.py"
    child.write_text(
        "import importlib.util, pathlib, sys, time\n"
        f"p=pathlib.Path({str(MODULE_PATH)!r})\n"
        "s=importlib.util.spec_from_file_location('recovery',p)\n"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"
        "m.assert_durable_output(pathlib.Path(sys.argv[1]))\n"
        "time.sleep(.15)\n"
        "print('after-launcher-exit',flush=True)\n"
        "print('COMPLETE',flush=True)\n"
    )
    launcher = tmp_path / "launcher.py"
    launcher.write_text(
        "import pathlib, subprocess, sys\n"
        "with pathlib.Path(sys.argv[2]).open('x') as log:\n"
        " p=subprocess.Popen([sys.executable,sys.argv[1],sys.argv[2]],"
        "stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)\n"
        "print(p.pid,flush=True)\n"
    )
    parent = subprocess.run(
        [sys.executable, str(launcher), str(child), str(log)],
        capture_output=True,
        text=True,
        check=True,
        timeout=2,
    )
    assert int(parent.stdout.strip()) > 0
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and "COMPLETE" not in log.read_text():
        time.sleep(0.02)
    assert log.read_text() == "after-launcher-exit\nCOMPLETE\n"


def test_missing_frozen_input_is_shared_fault_not_profile_failure(tmp_path):
    with pytest.raises(continuation.legacy.FrozenInputsChangedError):
        continuation.checked_hash(tmp_path / "missing")


def test_shared_fault_cannot_be_cleared_by_a_phase2_summary_review(tmp_path):
    summary = tmp_path / "summary.json"
    review = tmp_path / "review.json"
    summary.write_text(
        json.dumps(
            {
                "phase": "phase1",
                "operational_plan_sha256": "plan",
                "blocked_profiles": [],
                "shared_input_fault": {"type": "FrozenInputsChangedError"},
            }
        )
    )
    review.write_text(json.dumps({"approved": True, "summary_sha256": continuation.sha(summary)}))
    with pytest.raises(ValueError, match="shared input fault"):
        continuation.prior_phase_gate("phase2", "plan", summary, review)


@pytest.mark.parametrize("new_infrastructure_fault", [False, True])
def test_worker_only_runs_untouched_slots_and_never_retries_phase(
    tmp_path, monkeypatch, new_infrastructure_fault
):
    def frozen_row(lifecycle, stage):
        return {
            "slot": f"{lifecycle}-{stage}",
            "lifecycle": lifecycle,
            "stage": stage,
            "phase": "phase1",
            "profile_id": "codex-astra",
        }

    rows = [
        frozen_row("complete", 1),
        frozen_row("claimed", 1),
        frozen_row("claimed", 2),
        frozen_row("fresh", 1),
        frozen_row("fresh", 2),
    ]
    manifest = {
        "slots": rows,
        "worker_order": ["codex-astra"],
        "admitted_profile_ids": ["codex-astra"],
    }
    previous = tmp_path / "cases/complete/stage-1/result.json"
    previous.parent.mkdir(parents=True)
    prior_result = {
        "host": "codex",
        "profile_id": "codex-astra",
        "artifact_passed": False,
        "infrastructure_fault": False,
    }
    previous.write_text(json.dumps(prior_result))
    claim = tmp_path / "cases/claimed/stage-1/claimed.json"
    claim.parent.mkdir(parents=True)
    claim.write_text("original claim")
    original_result = previous.read_bytes()
    plan_path = tmp_path / "operational-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema": "prime-operational-continuation.v1",
                "cohort": str(tmp_path),
                "phase_order": ["phase1", "phase2"],
                "manifest_sha256": "fixture",
                "censored_lifecycles": ["claimed"],
            }
        )
    )
    launched = []

    def run_session(cohort, row, endpoint, *, corpus_root, package_installer):
        assert endpoint is None
        assert corpus_root == continuation.policy.CORPUS
        assert package_installer is continuation.package.install
        assert row is next(candidate for candidate in rows if candidate["slot"] == row["slot"])
        launched.append(row["slot"])
        destination = continuation.legacy.session_path(cohort, row)
        destination.mkdir(parents=True, exist_ok=False)
        result = {**prior_result, "infrastructure_fault": new_infrastructure_fault}
        continuation.legacy.write(destination / "result.json", result)
        return result

    # Only external boundaries are replaced. Real selection, immutable writes,
    # worker control flow, stop behavior, summary, and phase claims run below.
    validations = 0

    def validated_manifest(plan, *, condition_observer=None):
        nonlocal validations
        validations += 1
        if condition_observer is not None:
            condition_observer(
                {
                    "observed_sha256": ("a" if validations == 1 else "b") * 64,
                    "effective_effort": "high",
                    "effective_service_tier": "default",
                }
            )
        return manifest

    monkeypatch.setattr(continuation, "assert_durable_output", lambda log: None)
    monkeypatch.setattr(continuation, "validate_plan", validated_manifest)
    monkeypatch.setattr(continuation.delivery, "run_session", run_session)
    output = tmp_path / "attempt-1"
    result = continuation.run_phase(plan_path, "phase1", output, tmp_path / "log")
    assert launched == (["fresh-1"] if new_infrastructure_fault else ["fresh-1", "fresh-2"])
    assert previous.read_bytes() == original_result
    assert claim.read_text() == "original claim"
    assert not (tmp_path / "cases/claimed/stage-2").exists()
    assert result["blocked_profiles"] == (["codex-astra"] if new_infrastructure_fault else [])
    assert len(result["effective_codex_condition_observations"]) == 2
    assert len(list(output.glob("codex-profile-*.json"))) == 2
    ledger = result["profiles"][0]["ledger"]
    assert [entry["status"] for entry in ledger[:3]] == [
        "preserved_result",
        "censored_preexisting_lifecycle",
        "censored_preexisting_lifecycle",
    ]
    with pytest.raises(FileExistsError):
        continuation.run_phase(plan_path, "phase1", tmp_path / "alternate-out", tmp_path / "log")
    assert not (tmp_path / "alternate-out").exists()


def synthetic_source(tmp_path, config):
    source = tmp_path / "source"
    source.mkdir()
    (source / "config.toml").write_text(config)
    (source / "auth.json").write_text(
        '{"auth_mode":"chatgpt","tokens":{"access_token":"synthetic-not-a-real-credential"}}'
    )
    return source


def local_dirs(tmp_path):
    for name in ("work", "config", "tmp", "bin", "native"):
        (tmp_path / name).mkdir(parents=True)
    return tmp_path


@pytest.mark.parametrize("profile_id", ["codex-astra", "codex-luna"])
def test_full_prepare_erases_ignored_and_overridden_config_fields(
    tmp_path, monkeypatch, profile_id
):
    variants = [
        'model_reasoning_effort="high"\nservice_tier="fast"\nmodel="ignored"\n',
        'model_reasoning_effort="low"\nservice_tier="default"\n'
        'developer_instructions="Unrelated user text"\n[features]\nmemories=true\n',
        'model_reasoning_effort="arbitrary"\nservice_tier="arbitrary"\n'
        'approval_policy="on-request"\n[shell_environment_policy]\ninherit="none"\n',
        '[projects."/ignored/project"]\ntrust_level="trusted"\n',
    ]
    actual = []
    for index, config in enumerate(variants):
        case = tmp_path / f"case-{index}"
        case.mkdir()
        source = synthetic_source(case, config)
        monkeypatch.setattr(
            continuation.memory_host_codex, "_source_home", lambda source=source: source
        )
        local = local_dirs(case / "local")
        launch = continuation.profiles.prepare(
            profile_id, local, {"PATH": "/synthetic/bin"}, "Work on trial-x."
        )
        serialized = json.dumps(asdict(launch), default=str).replace(str(local), "<local>")
        actual.append(serialized)
        assert (source / "config.toml").read_text() == config
        assert (local / "config/auth.json").read_bytes() == (source / "auth.json").read_bytes()
        assert (local / "config/auth.json").stat().st_mode & 0o777 == 0o600
        assert (local / "config/memories").is_symlink()
        assert (local / "config/memories").resolve() == local / "native/memories"
        assert not (local / "config/config.toml").exists()
    assert len(set(actual)) == 1


@pytest.mark.parametrize("field", ["model_reasoning_effort", "service_tier"])
@pytest.mark.parametrize("invalid", ["1", "true", "[]"])
def test_full_prepare_rejects_invalid_consumed_types_before_auth_copy(
    tmp_path, monkeypatch, field, invalid
):
    source = synthetic_source(tmp_path, f"{field}={invalid}\n")
    monkeypatch.setattr(continuation.memory_host_codex, "_source_home", lambda: source)
    local = local_dirs(tmp_path / "local")
    with pytest.raises(ValueError, match="Invalid configured Codex"):
        continuation.profiles.prepare("codex-astra", local, {}, "Work on trial-x.")
    assert not (local / "config/auth.json").exists()


def guarded_fixture(tmp_path, monkeypatch):
    source = synthetic_source(tmp_path, 'model_reasoning_effort="low"\nservice_tier="fast"\n')
    monkeypatch.setattr(continuation, "EXPECTED_SOURCE", source)
    monkeypatch.setattr(continuation.memory_host_codex, "_source_home", lambda: source)
    other = tmp_path / "other-profile.json"
    other.write_text('{"preserve":true}')
    fixture_source = tmp_path / "frozen-input.py"
    fixture_source.write_text("original fixture source\n")
    manifest = {
        "source_sha256": {
            name: continuation.sha(continuation.base.REPO / name)
            for name in continuation.REQUIRED_CONDITION_SOURCES
        }
        | {str(fixture_source): continuation.sha(fixture_source)},
        "binary_sha256": {},
        "profile_sha256": {
            str(source / "config.toml"): "original-frozen-hash",
            str(other): continuation.sha(other),
        },
        "model_profiles": {
            identity: {
                "host": "codex",
                "model": continuation.profiles.get_profile(identity).model,
                "reasoning_effort": "high",
            }
            for identity in ("codex-astra", "codex-luna")
        },
    }
    monkeypatch.setattr(
        continuation.legacy,
        "profile_hashes",
        lambda **kwargs: {
            str(source / "config.toml"): continuation.sha(source / "config.toml"),
            str(other): continuation.sha(other),
        },
    )
    return manifest, source, other, fixture_source


@pytest.mark.parametrize("changed", ["other-profile", "frozen-source"])
def test_effective_exception_never_weakens_other_frozen_checks(tmp_path, monkeypatch, changed):
    manifest, _source, other, fixture_source = guarded_fixture(tmp_path, monkeypatch)
    original = json.dumps(manifest, sort_keys=True)
    evidence = continuation.assert_effective_frozen(manifest)
    assert evidence["raw_profile_drift"]
    assert json.dumps(manifest, sort_keys=True) == original
    target = other if changed == "other-profile" else fixture_source
    target.write_text("changed only in test scratch")
    with pytest.raises(continuation.legacy.FrozenInputsChangedError):
        continuation.assert_effective_frozen(manifest)


def test_effective_exception_rejects_source_home_redirection(tmp_path, monkeypatch):
    manifest, source, _, _ = guarded_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        continuation.memory_host_codex, "_source_home", lambda: source / "different"
    )
    with pytest.raises(continuation.legacy.FrozenInputsChangedError, match="source home"):
        continuation.assert_effective_frozen(manifest)


def test_later_raw_toml_edits_are_allowed_only_with_same_effective_conditions(
    tmp_path, monkeypatch
):
    manifest, source, _, _ = guarded_fixture(tmp_path, monkeypatch)
    before = continuation.assert_effective_frozen(manifest)
    (source / "config.toml").write_text(
        'model_reasoning_effort="xhigh"\nservice_tier="default"\n'
        'developer_instructions="Different unused instructions"\n'
    )
    after = continuation.assert_effective_frozen(manifest)
    assert before["observed_sha256"] != after["observed_sha256"]
    assert before["effective_effort"] == after["effective_effort"] == "high"
    assert before["effective_service_tier"] == after["effective_service_tier"] == "default"
    (source / "config.toml").write_text("model_reasoning_effort=7\n")
    with pytest.raises(continuation.legacy.FrozenInputsChangedError, match="remain strings"):
        continuation.assert_effective_frozen(manifest)
