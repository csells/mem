"""Scratch-only regression checks; never invoke a host, bd, or candidate code."""

import json
from pathlib import Path

import final_dispositions as audit
import pytest


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as output:
        json.dump(value, output)


def stream(tmp_path, events, host):
    path = tmp_path / "stream.jsonl"
    path.write_text("\n".join(json.dumps(event) for event in events))
    return audit.stream_evidence(path, host)


@pytest.mark.parametrize(
    ("host", "event"),
    [
        ("codex", {"type": "item.completed", "item": {"type": "agent_message", "text": "Done"}}),
        (
            "claude",
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read"}]}},
        ),
        ("opencode", {"type": "text", "part": {"type": "text", "text": "<function=skill>"}}),
        ("zcode", {"type": "model.streaming", "payload": {"kind": "text", "delta": "A"}}),
    ],
)
def test_actual_output_is_generation_even_when_pseudo_tool(tmp_path, host, event):
    evidence = stream(tmp_path, [event], host)
    assert evidence["generation"] == [{"line": 1, "type": event["type"]}]
    assert evidence["provider_denials"] == []


def test_model_metadata_and_completed_token_counters_are_not_generation(tmp_path):
    evidence = stream(
        tmp_path,
        [
            {"type": "thread.started", "model": "gpt-6-astra"},
            {"type": "turn.completed", "usage": {"output_tokens": 4}},
        ],
        "codex",
    )
    assert not evidence["generation"]


def test_actual_codex_quota_denial_differs_from_quoted_text(tmp_path):
    message = audit.QUOTA_PREFIX + " Try later."
    evidence = stream(
        tmp_path,
        [
            {"type": "error", "message": message},
            {"type": "turn.failed", "error": {"message": message}},
        ],
        "codex",
    )
    assert not evidence["generation"]
    assert len(evidence["provider_denials"]) == 2
    other = tmp_path / "other"
    other.mkdir()
    quoted = stream(
        other,
        [{"type": "item.completed", "item": {"type": "agent_message", "text": message}}],
        "codex",
    )
    assert quoted["generation"] and not quoted["provider_denials"]


def test_malformed_input_does_not_become_fake_denial_or_generation(tmp_path):
    path = tmp_path / "stream.jsonl"
    path.write_text('broken usage limit\n{"type":"system","model":"haiku"}\n')
    evidence = audit.stream_evidence(path, "claude")
    assert evidence == {"generation": [], "provider_denials": [], "malformed_lines": [1]}


def test_actual_auth_denial_is_typed_but_quoted_auth_message_is_not(tmp_path):
    message = (
        "Your access token could not be refreshed because your refresh token was revoked. "
        "Please log out and sign in again."
    )
    evidence = stream(tmp_path, [{"type": "error", "message": message}], "codex")
    assert evidence["provider_denials"][0]["kind"] == "authentication_rejected"
    assert not evidence["generation"]
    other = tmp_path / "quoted"
    other.mkdir()
    quoted = stream(
        other,
        [
            {"type": "user", "text": message},
            {"type": "item.completed", "item": {"type": "agent_message", "text": message}},
        ],
        "codex",
    )
    assert not quoted["provider_denials"]


def classify(**changes):
    values = {
        "assessed": False,
        "generated": False,
        "denied": False,
        "original_claim": False,
        "original_lifecycle": False,
        "directory_exists": False,
        "process_exists": False,
        "auth_failure": False,
        "profile_blocked": False,
        "predecessor_missing": False,
    }
    return audit.disposition(**(values | changes))


def test_dispositions_distinguish_original_claim_auth_claim_dependency_and_profile_stop():
    assert (
        classify(
            original_claim=True, original_lifecycle=True, directory_exists=True, auth_failure=True
        )
        == "original_prelaunch_censor"
    )
    assert (
        classify(original_lifecycle=True, predecessor_missing=True)
        == "original_downstream_missing_predecessor"
    )
    assert (
        classify(directory_exists=True, auth_failure=True, profile_blocked=True)
        == "new_auth_setup_claim"
    )
    assert (
        classify(predecessor_missing=True, profile_blocked=True) == "downstream_missing_predecessor"
    )
    assert classify(profile_blocked=True) == "later_profile_blocked_untouched"
    assert (
        classify(directory_exists=True, process_exists=True, auth_failure=True)
        == "started_unassessed"
    )
    assert classify() == "untouched_no_recorded_blocker"


def test_assessed_denial_and_partial_generation_are_separate():
    assert (
        classify(assessed=True, denied=True)
        == "assessed_provider_denial_without_observed_generation"
    )
    assert (
        classify(assessed=True, denied=True, generated=True)
        == "assessed_generation_with_provider_denial"
    )
    assert classify(assessed=True) == "assessed_generation_unverified"


def corpus(tmp_path, *, summary_count=1, result_slot="life-0-3"):
    cohort = tmp_path / "cohort"
    slots = [
        {
            "slot": f"life-{i}-{stage}",
            "lifecycle": f"life-{i}",
            "profile_id": "codex-astra",
            "host": "codex",
            "family": "finance",
            "arm": "thin-prime",
            "stage": stage,
            "phase": "phase1" if stage < 3 else "phase2",
        }
        for i in range(36)
        for stage in range(1, 7)
    ]
    save(cohort / "manifest.json", {"slots": slots, "admitted_profile_ids": ["codex-astra"]})
    save(
        cohort / "recovery-01/operational-plan.json",
        {
            "manifest_sha256": audit.sha(cohort / "manifest.json"),
            "preexisting_claims_without_result": ["life-1-1"],
            "censored_lifecycles": ["life-1"],
        },
    )
    summary = cohort / "recovery-02/phase2/summary.json"
    save(
        summary,
        {
            "phase": "phase2",
            "manifest_sha256": audit.sha(cohort / "manifest.json"),
            "phase_assessed": summary_count,
            "blocked_profiles": ["codex-astra"],
        },
    )
    save(
        summary.parent / "codex-astra-failure.json",
        {"profile": "codex-astra", "message": audit.AUTH_FAILURE},
    )
    row = slots[2]
    folder = cohort / "cases/life-0/stage-3"
    save(
        folder / "result.json",
        row | {"slot": result_slot, "exit_code": 1, "artifact_passed": False},
    )
    stream(folder, [{"type": "turn.failed", "error": {"message": audit.QUOTA_PREFIX}}], "codex")
    return cohort, summary


def test_full_export_hashes_all_216_slots_and_preserves_source_bytes(tmp_path):
    cohort, summary = corpus(tmp_path)
    before = {str(p): audit.sha(p) for p in cohort.rglob("*") if p.is_file()}
    result = audit.export(cohort, summary)
    assert result["planned"] == 216 and result["assessed"] == 1
    assert sum(result["status_counts"].values()) == 216
    assert result["status_counts"]["original_prelaunch_censor"] == 1
    assert result["status_counts"]["original_downstream_missing_predecessor"] == 5
    assert result["status_counts"]["assessed_provider_denial_without_observed_generation"] == 1
    assert all(audit.sha(Path(p)) == h for p, h in before.items())
    assert result["source_sha256"][str(cohort / "cases/life-0/stage-3/result.json")]


def test_foreign_results_are_refused(tmp_path):
    cohort, summary = corpus(tmp_path)
    save(cohort / "cases/foreign/stage-3/result.json", {"unplanned": True})
    with pytest.raises(ValueError, match="outside manifest"):
        audit.export(cohort, summary)


def test_result_identity_mismatch_is_refused_without_write(tmp_path):
    cohort, summary = corpus(tmp_path, result_slot="foreign")
    with pytest.raises(ValueError, match="identity mismatch"):
        audit.export(cohort, summary)
    assert not (cohort / "report.json").exists()


def test_summary_result_count_mismatch_is_refused(tmp_path):
    cohort, summary = corpus(tmp_path, summary_count=2)
    with pytest.raises(ValueError, match="terminal summary"):
        audit.export(cohort, summary)


def test_mixed_generation_and_denial_does_not_invent_their_order():
    assert (
        classify(assessed=True, denied=True, generated=True)
        == "assessed_generation_with_provider_denial"
    )
