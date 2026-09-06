"""Global campaign reservations and no-repurchase checks, without provider calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from membench.runner.bd_campaign import audit_campaign, execute_batch, initialize, register_batch
from tests.test_bd_component_experiment import fake_runner, manifest


def batch_manifest(tmp_path: Path, number: int) -> dict:
    directory = tmp_path / f"inputs-{number}"
    directory.mkdir()
    return {**manifest(directory), "replicate_id": str(number)}


def test_initialize_fixed_budget_and_readonly_audit(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    before = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
    result = audit_campaign(out)
    assert result["limits"] == {"total": 96, "development": 24, "replication": 24, "transfer": 48}
    assert result["started"] == 0 and result["reserved"] == 0 and not result["issues"]
    assert before == {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}


def test_reservations_enforce_all_phase_and_total_caps(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    n = 0
    for stage, count in [("development", 3), ("replication", 3), ("transfer", 6)]:
        for _ in range(count):
            n += 1
            register_batch(out, f"batch-{n}", stage, batch_manifest(tmp_path, n))
        with pytest.raises(ValueError):
            register_batch(out, f"extra-{stage}", stage, batch_manifest(tmp_path, 100 + n))
    report = audit_campaign(out)
    assert report["reserved"] == 96 and report["started"] == 0
    assert {stage: v["reserved"] for stage, v in report["stages"].items()} == {
        "development": 24,
        "replication": 24,
        "transfer": 48,
    }


def test_execute_resume_never_rebuys(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    calls = []
    register_batch(out, "first", "development", m)
    assert (
        execute_batch(out, "first", session_runner=fake_runner(calls), identity_check=lambda: None)[
            "new_sessions"
        ]
        == 8
    )
    assert (
        execute_batch(out, "first", session_runner=fake_runner(calls), identity_check=lambda: None)[
            "new_sessions"
        ]
        == 0
    )
    assert audit_campaign(out)["started"] == 8 and len(calls) == 8


def test_duplicate_registration_and_alias_manifest_refused(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    register_batch(out, "first", "development", m)
    with pytest.raises(ValueError):
        register_batch(out, "first", "development", m)
    with pytest.raises(ValueError):
        register_batch(out, "alias", "replication", m)


def test_later_partial_counts_slot_and_prevents_any_call(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    for n in [1, 2]:
        register_batch(out, f"batch-{n}", "development", batch_manifest(tmp_path, n))
    late = out / "batches/batch-2/run/sessions/opportunity-current"
    late.mkdir(parents=True)
    (late / "started.json").write_text("{}")
    calls = []
    report = audit_campaign(out)
    assert report["started"] == 1 and report["issues"]
    with pytest.raises(ValueError):
        execute_batch(
            out, "batch-1", session_runner=fake_runner(calls), identity_check=lambda: None
        )
    assert not calls


def test_future_corruption_between_rows_stops_second_call(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    for n in [1, 2]:
        register_batch(out, f"batch-{n}", "development", batch_manifest(tmp_path, n))
    calls = []

    def run(row, config, path):
        result = fake_runner(calls)(row, config, path)
        (out / "batches/batch-2/run/manifest.json").write_text("{}")
        return result

    with pytest.raises(ValueError):
        execute_batch(out, "batch-1", session_runner=run, identity_check=lambda: None)
    assert len(calls) == 1


def test_timeout_in_one_batch_blocks_other_batch(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    calls = []
    for n in [1, 2]:
        register_batch(out, f"batch-{n}", "development", batch_manifest(tmp_path, n))
    assert execute_batch(
        out,
        "batch-1",
        session_runner=fake_runner(calls, "terminal_timeout"),
        identity_check=lambda: None,
    )["halted"]
    assert audit_campaign(out)["started"] == 1
    with pytest.raises(ValueError):
        execute_batch(
            out, "batch-2", session_runner=fake_runner(calls), identity_check=lambda: None
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "damage", ["foreign_batch", "missing_manifest", "registration", "symlink", "foreign_row"]
)
def test_global_corruption_rejected(tmp_path, damage):
    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    register_batch(out, "first", "development", m)
    batch = out / "batches/first"
    calls = []
    if damage == "foreign_batch":
        (out / "batches/foreign").mkdir()
    elif damage == "missing_manifest":
        (batch / "run/manifest.json").unlink()
    elif damage == "registration":
        p = batch / "registration.json"
        r = json.loads(p.read_text())
        r["stage"] = "transfer"
        p.write_text(json.dumps(r))
    elif damage == "symlink":
        (out / "batches/alias").symlink_to(batch, target_is_directory=True)
    else:
        (batch / "run/sessions/foreign").mkdir(parents=True)
    assert audit_campaign(out)["issues"]
    with pytest.raises(ValueError):
        execute_batch(out, "first", session_runner=fake_runner(calls), identity_check=lambda: None)
    assert not calls


def test_shared_campaign_lock_prevents_registration_and_execution(tmp_path):
    from membench.runner.e1_grid import ResumeMismatchError, out_lock

    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    register_batch(out, "first", "development", m)
    with out_lock(out):
        with pytest.raises(ResumeMismatchError):
            register_batch(out, "second", "development", m)
        with pytest.raises(ResumeMismatchError):
            execute_batch(out, "first", session_runner=fake_runner([]), identity_check=lambda: None)


def test_missing_batch_cannot_erase_reservation_or_release_id(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    register_batch(out, "first", "development", m)
    (out / "batches/first").rename(tmp_path / "moved-first")
    report = audit_campaign(out)
    assert report["reserved"] == 8 and report["issues"]
    with pytest.raises(ValueError):
        register_batch(out, "first", "development", batch_manifest(tmp_path, 2))


def test_registry_receipt_missing_or_modified_blocks_calls(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    calls = []
    register_batch(out, "first", "development", m)
    (out / "registrations/first.json").unlink()
    assert audit_campaign(out)["issues"]
    with pytest.raises(ValueError):
        execute_batch(out, "first", session_runner=fake_runner(calls), identity_check=lambda: None)
    assert not calls


def test_deleted_consumed_row_stays_counted_and_cannot_be_repurchased(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    calls = []
    register_batch(out, "first", "development", m)
    execute_batch(
        out, "first", session_runner=fake_runner(calls), identity_check=lambda: None, max_sessions=1
    )
    row = out / "batches/first/run/sessions" / m["schedule"][0]["row_id"]
    row.rename(tmp_path / "removed-row")
    report = audit_campaign(out)
    assert report["started"] == 1 and report["issues"]
    with pytest.raises(ValueError):
        execute_batch(out, "first", session_runner=fake_runner(calls), identity_check=lambda: None)
    assert len(calls) == 1


def test_campaign_start_receipt_precedes_runner_and_survives_exception(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    register_batch(out, "first", "development", m)

    def broken(row, config, path):
        receipt = out / "invocations/first" / f"{row['row_id']}.json"
        assert receipt.is_file()
        raise RuntimeError("preserve the consumed invocation")

    with pytest.raises(RuntimeError):
        execute_batch(out, "first", session_runner=broken, identity_check=lambda: None)
    assert audit_campaign(out)["started"] == 1 and audit_campaign(out)["issues"]


def test_lost_independent_start_receipt_keeps_observed_start_count(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    calls = []
    register_batch(out, "first", "development", m)
    execute_batch(
        out, "first", session_runner=fake_runner(calls), identity_check=lambda: None, max_sessions=1
    )
    (out / "invocations/first" / f"{m['schedule'][0]['row_id']}.json").unlink()
    report = audit_campaign(out)
    assert report["started"] == 1 and report["issues"]
    with pytest.raises(ValueError):
        execute_batch(out, "first", session_runner=fake_runner(calls), identity_check=lambda: None)
    assert len(calls) == 1


def test_crash_after_component_start_before_campaign_receipt_is_not_retried(tmp_path):
    from membench.runner.bd_component_experiment import _identity

    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    calls = []
    register_batch(out, "first", "development", m)
    path = out / "batches/first/run/sessions" / m["schedule"][0]["row_id"]
    path.mkdir(parents=True)
    (path / "started.json").write_text(json.dumps(_identity(m["schedule"][0], m)))
    report = audit_campaign(out)
    assert report["started"] == 1 and report["issues"]
    with pytest.raises(ValueError):
        execute_batch(out, "first", session_runner=fake_runner(calls), identity_check=lambda: None)
    assert not calls


def test_new_batch_does_not_verify_old_live_runtime(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    calls = []
    for n in [1, 2]:
        m = {**batch_manifest(tmp_path, n), "source_fingerprint": f"old-frozen-source-{n}"}
        register_batch(out, f"batch-{n}", "development", m)
    verified = []
    execute_batch(
        out,
        "batch-2",
        session_runner=fake_runner(calls),
        identity_check=lambda: verified.append("batch-2"),
        max_sessions=1,
    )
    assert verified == ["batch-2"]


def test_initialize_or_register_invalid_identity(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    for batch_id, stage in [("../bad", "development"), ("ok", "other")]:
        with pytest.raises(ValueError):
            register_batch(out, batch_id, stage, m)
    with pytest.raises(ValueError):
        execute_batch(out, "unknown", session_runner=fake_runner([]), identity_check=lambda: None)
    other = tmp_path / "nonempty"
    other.mkdir()
    (other / "file").touch()
    with pytest.raises(ValueError):
        initialize(other)


def test_orphaned_started_batch_still_counted_globally(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    calls = []
    register_batch(out, "first", "development", m)
    execute_batch(
        out, "first", session_runner=fake_runner(calls), identity_check=lambda: None, max_sessions=1
    )
    (out / "registrations/first.json").unlink()
    report = audit_campaign(out)
    assert report["started"] == 1 and report["issues"]


def test_duplicate_stem_unrecognized_receipt_never_disappears(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    calls = []
    register_batch(out, "first", "development", m)
    execute_batch(
        out, "first", session_runner=fake_runner(calls), identity_check=lambda: None, max_sessions=1
    )
    directory = out / "invocations/first"
    original = directory / f"{m['schedule'][0]['row_id']}.json"
    payload = original.read_text()
    original.unlink()
    original.with_suffix(".txt").write_text(payload)
    original.write_text(payload)
    assert audit_campaign(out)["issues"]
    with pytest.raises(ValueError):
        execute_batch(out, "first", session_runner=fake_runner(calls), identity_check=lambda: None)
    assert len(calls) == 1


def test_corrupt_registration_retains_known_starts_and_marks_reservation_unknown(tmp_path):
    out = tmp_path / "campaign"
    initialize(out)
    m = batch_manifest(tmp_path, 1)
    calls = []
    register_batch(out, "first", "development", m)
    execute_batch(
        out, "first", session_runner=fake_runner(calls), identity_check=lambda: None, max_sessions=2
    )
    (out / "registrations/first.json").write_text("{}")
    report = audit_campaign(out)
    assert report["started"] == 2 and report["issues"]
    assert report["reservation_unknown_batches"] == ["first"]
