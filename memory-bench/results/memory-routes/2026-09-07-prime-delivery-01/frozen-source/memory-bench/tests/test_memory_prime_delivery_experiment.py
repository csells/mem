from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

import pytest

from membench.runner import memory_prime_delivery_package as package
from scripts import memory_policy_handoff_experiment as policy
from scripts import memory_prime_delivery_experiment as study
from scripts import memory_routes_experiment as base
from scripts import memory_unprompted_experiment as legacy


def test_schedule_matches_world_route_and_counterbalances_delivery_order() -> None:
    rows = study.schedule()
    assert len(rows) == len({r["slot"] for r in rows}) == 216
    assert {p: sum(r["phase"] == p for r in rows) for p in study.PHASES} == {
        "phase1": 72,
        "phase2": 144,
    }
    orders = []
    for profile in study.PROFILE_IDS:
        profile_rows = [r for r in rows if r["profile_id"] == profile]
        assert len(profile_rows) == 36
        starts = [r for r in profile_rows if r["stage"] == 1]
        first_family = starts[0]["family"]
        orders.append(tuple(r["arm"] for r in starts if r["family"] == first_family))
        routes = set()
        for family in policy.WORLDS:
            selected = [r for r in profile_rows if r["family"] == family]
            assert len({r["corpus_family"] for r in selected}) == 1
            assert len({r["catalog_mode"] for r in selected}) == 1
            assert {r["arm"] for r in selected} == set(package.ARMS)
            routes.add(selected[0]["catalog_mode"])
        assert routes == {"indexed", "search-only"}
    assert set(orders) == set(itertools.permutations(package.ARMS))
    assert {r["mode"] for r in rows} == {"isolated"}


def test_freeze_refuses_incomplete_or_stale_qualification(tmp_path: Path) -> None:
    admission = tmp_path / "admission.json"
    admission.write_text(json.dumps({"approved": True, "admitted_profile_ids": []}))
    with pytest.raises(ValueError, match="six declared"):
        study.freeze(tmp_path / "cohort", admission)
    assert not (tmp_path / "cohort").exists()


def test_phase_requires_exact_review_without_creating_or_restarting_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({"slots": [], "require_phase_review": True}))
    prior = tmp_path / "phases/phase1"
    prior.mkdir(parents=True)
    summary = prior / "completed.json"
    summary.write_text('{"assessed":72}')
    (prior / "reviewed.json").write_text('{"approved":true,"summary_sha256":"incorrect"}')
    monkeypatch.setattr(legacy, "assert_frozen", lambda _: None)
    with pytest.raises(ValueError, match="exact final summary"):
        study.run_phase(tmp_path, "phase2")
    assert not (tmp_path / "phases/phase2").exists()


@pytest.mark.parametrize("bad_field", ["briefing_sha256", "actual_prime_equivalence"])
def test_freeze_rejects_changed_briefing_or_unverified_prime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_field: str
) -> None:
    qualification = tmp_path / "qualification.json"
    qualified = {
        "planned": 12,
        "assessed": 12,
        "interface_admitted_profiles": list(study.PROFILE_IDS),
        "briefing_sha256": hashlib.sha256(package.briefing().encode()).hexdigest(),
        "actual_prime_equivalence": True,
    }
    qualified[bad_field] = "stale" if bad_field == "briefing_sha256" else False
    qualification.write_text(json.dumps(qualified))
    admission = tmp_path / "admission.json"
    admission.write_text(
        json.dumps(
            {
                "approved": True,
                "admitted_profile_ids": list(study.PROFILE_IDS),
                "reviewed_sha256": {},
                "qualification_path": str(qualification),
                "qualification_sha256": base.sha(qualification),
            }
        )
    )
    monkeypatch.setattr(study, "review_paths", lambda: set())
    with pytest.raises(ValueError, match=r"briefing differs|actual prime equivalence"):
        study.freeze(tmp_path / "cohort", admission)
    assert not (tmp_path / "cohort").exists()


def test_review_scope_covers_new_delivery_and_existing_guidance() -> None:
    required = study.review_paths()
    assert "memory-bench/scripts/memory_prime_delivery_runtime.py" in required
    assert "memory-bench/membench/runner/memory_prime_delivery_package.py" in required
    assert "memory-bench/fixtures/memory-policy-handoff-package/memory.md" in required
    assert "specs/plans/0007-memory-prime-delivery.md" in required
