"""Frozen confirmation schedules reuse audited independent-session execution."""

from __future__ import annotations

import copy
import json

import pytest

from membench.runner.bd_component_experiment import execute, freeze, validate_manifest
from tests.test_bd_component_experiment import fake_runner, manifest


def confirmation(tmp_path):
    original = manifest(tmp_path)
    source = original["schedule"][0]["sources"]
    prompt = original["schedule"][0]["prompt"]
    seed = original["schedule"][-1]["seed"]
    rows = [
        {
            "row_id": f"{component}-{intervention}-{replicate}",
            "component": component,
            "intervention": intervention,
            "replicate": replicate,
            "condition": "current",
            "initial_store": store,
            "prompt": copy.deepcopy(prompt),
            "sources": copy.deepcopy(source) if component == "capture" else [],
            "seed": copy.deepcopy(seed) if store == "seeded" else None,
        }
        for component, intervention, store in [
            ("capture", "opportunity", "empty"),
            ("capture", "already_known", "seeded"),
            ("retrieval", "seeded", "seeded"),
            ("retrieval", "empty", "empty"),
        ]
        for replicate in (1, 2)
    ]
    return {**original, "schema": "bd-confirmation-experiment.v1", "schedule": rows}


def test_exact_confirmation_eight_no_repurchase(tmp_path):
    m = confirmation(tmp_path)
    calls = []
    out = tmp_path / "out"
    freeze(out, m)
    first = execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    second = execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    assert first["new_sessions"] == 8 and second["new_sessions"] == 0
    assert len(calls) == len(set(calls)) == 8


@pytest.mark.parametrize("replicate", [None, 0, 3, True, False, "1", 1.0, []])
def test_invalid_replicate_rejected(tmp_path, replicate):
    m = confirmation(tmp_path)
    m["schedule"][0]["replicate"] = replicate
    with pytest.raises(ValueError):
        validate_manifest(m)


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate_id",
        "duplicate_slot",
        "adapter",
        "capture_prompt",
        "retrieval_prompt",
        "source_contrast",
        "retrieval_source",
        "empty_seed",
        "seed_contrast",
        "seed_as_source",
        "seed_as_prompt",
    ],
)
def test_confirmation_contrasts_and_leaks_rejected(tmp_path, change):
    m = confirmation(tmp_path)
    rows = m["schedule"]
    alternative = {"path": "binary", "sha256": m["pins"][0]["sha256"]}
    if change == "missing":
        rows.pop()
    elif change == "duplicate_id":
        rows[1]["row_id"] = rows[0]["row_id"]
    elif change == "duplicate_slot":
        rows[1]["replicate"] = 1
    elif change == "adapter":
        rows[0]["condition"] = "focused"
    elif change == "capture_prompt":
        rows[3]["prompt"] = alternative
    elif change == "retrieval_prompt":
        rows[7]["prompt"] = alternative
    elif change == "source_contrast":
        rows[3]["sources"][0] = {**alternative, "target_path": "source.md"}
    elif change == "retrieval_source":
        rows[4]["sources"] = rows[0]["sources"]
    elif change == "empty_seed":
        rows[6]["seed"] = rows[2]["seed"]
    elif change == "seed_contrast":
        rows[5]["seed"] = alternative
    elif change == "seed_as_source":
        for row in rows[:4]:
            row["sources"] = [{**rows[2]["seed"], "target_path": "source.md"}]
    else:
        for row in rows[4:]:
            row["prompt"] = rows[2]["seed"]
    with pytest.raises(ValueError):
        freeze(tmp_path / "out", m)


def test_confirmation_later_partial_blocks_all_new_calls(tmp_path):
    m = confirmation(tmp_path)
    out = tmp_path / "out"
    freeze(out, m)
    late = out / "sessions" / m["schedule"][-1]["row_id"]
    late.mkdir(parents=True)
    (late / "started.json").write_text("{}")
    calls = []
    with pytest.raises(ValueError):
        execute(out, m, session_runner=fake_runner(calls), identity_check=lambda: None)
    assert calls == []


def test_confirmation_replay_rejects_changed_replication_identity(tmp_path):
    m = confirmation(tmp_path)
    out = tmp_path / "out"
    freeze(out, m)
    changed = copy.deepcopy(m)
    changed["schedule"][0]["row_id"] = "replacement-replicate-1"
    with pytest.raises(ValueError, match="Frozen manifest changed"):
        freeze(out, changed)
    assert json.loads((out / "manifest.json").read_text()) == m


def test_confirmation_runs_through_global_campaign(tmp_path):
    from membench.runner.bd_campaign import execute_batch, initialize, register_batch

    m = confirmation(tmp_path)
    campaign = tmp_path / "campaign"
    calls = []
    initialize(campaign)
    register_batch(campaign, "confirmation-01", "replication", m)
    result = execute_batch(
        campaign, "confirmation-01", session_runner=fake_runner(calls), identity_check=lambda: None
    )
    assert result["new_sessions"] == 8
    replay = execute_batch(
        campaign, "confirmation-01", session_runner=fake_runner(calls), identity_check=lambda: None
    )
    assert replay["new_sessions"] == 0
    assert len(calls) == 8
