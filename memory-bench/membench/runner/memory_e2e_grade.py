"""Grade actual retained records without inventing memory identities or roles.

Literal source/rationale preservation is measured separately from typed policy.
Neither this module nor the reused JSON grader certifies surrounding prose. Map
diffs expose retained changes, not write attempts that leave the same final body;
command receipts must establish those attempts and actual retrieval routes.
"""

from __future__ import annotations

from typing import Any

from membench.runner.memory_e2e_corpus import E2ECase, E2EStage
from membench.runner.memory_routes_grade import grade_capture


def _record(memories: dict[str, str], key: str, case: E2ECase) -> dict[str, Any]:
    body = memories[key]
    result: dict[str, Any] = {}
    for version in ("v1", "v2"):
        policy = case.v1_policy if version == "v1" else case.v2_policy
        source = case.v1_source if version == "v1" else case.v2_source
        rationale = case.v1_rationale if version == "v1" else case.v2_rationale
        typed = grade_capture(memories, key, policy)
        source_present = source in body
        rationale_present = rationale in body
        result[version] = {
            "policy": typed,
            "source": {
                "passed": source_present,
                "scope": "exact_approved_text_presence_only",
            },
            "rationale": {
                "passed": rationale_present,
                "scope": "exact_approved_text_presence_only",
            },
            "complete": typed["passed"] is True and source_present and rationale_present,
        }
    return result


def _history(
    before: dict[str, str], after: dict[str, str], keys: list[str] | None
) -> dict[str, Any]:
    if keys is None:
        return {"passed": None, "reason": "historical_identity_unknown"}
    missing_baseline = sorted(key for key in keys if key not in before)
    missing_after = sorted(key for key in keys if key not in after)
    mutated = sorted(
        key for key in keys if key in before and key in after and before[key] != after[key]
    )
    passed: bool | None = bool(keys) and not missing_after and not mutated
    if passed and missing_baseline:
        passed = None
    return {
        "passed": passed,
        "keys": sorted(keys),
        "mutated": mutated,
        "missing_after": missing_after,
        "missing_baseline": missing_baseline,
    }


def _standing(
    after: dict[str, str], exact_keys: list[str], keys: list[str] | None
) -> dict[str, Any]:
    if keys is None:
        return {"passed": None, "reason": "standing_identity_unknown", "all_match_current": None}
    missing = sorted(key for key in keys if key not in after)
    return {
        "passed": bool(keys) and not missing,
        "keys": sorted(keys),
        "missing": missing,
        "all_match_current": bool(keys) and all(key in exact_keys for key in keys),
    }


def grade_retained(
    before: dict[str, str],
    after: dict[str, str],
    case: E2ECase,
    stage: E2EStage,
    *,
    standing_keys: list[str] | None = None,
    history_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Assess content, retained changes, and externally established record roles.

    Exact-key lists mean content matches, not identified current/history roles.
    Identical v1 bodies may be a legitimate standing record and historical copy.
    Pass roles only when actual author references or observed selection establish
    them; key spelling is not evidence. For historical reproduction, the standing
    agreement is still v2 even though that session's artifact must implement v1.

    Incomplete keys have a supported but incorrect policy representation, or an
    exact policy missing approved source/rationale text. Plain prose outside the
    supported JSON extraction stays unassessed rather than proved information loss.
    Decoy identities are excluded from target grading, but their changes remain
    visible. No records are created, repaired, or selected on the agent's behalf.
    """
    records = {key: _record(after, key, case) for key in sorted(after) if key not in case.decoys}
    exact = {
        version: [key for key, record in records.items() if record[version]["complete"]]
        for version in ("v1", "v2")
    }
    policy_exact = {
        version: [
            key for key, record in records.items() if record[version]["policy"]["passed"] is True
        ]
        for version in ("v1", "v2")
    }
    standing_version = "v1" if stage.name in {"establish", "direct", "search"} else "v2"
    changes = {
        "created": sorted(set(after) - set(before)),
        "updated": sorted(key for key in set(before) & set(after) if before[key] != after[key]),
        "removed": sorted(set(before) - set(after)),
    }
    incomplete = []
    unassessed = []
    for key, record in records.items():
        if any(record[version]["complete"] for version in ("v1", "v2")):
            continue
        if all(record[version]["policy"]["passed"] is None for version in ("v1", "v2")):
            unassessed.append(key)
        else:
            incomplete.append(key)
    return {
        "standing_version": standing_version,
        "records": records,
        "current_exact_keys": exact[standing_version],
        "history_exact_keys": exact["v1"],
        "current_policy_exact_keys": policy_exact[standing_version],
        "history_policy_exact_keys": policy_exact["v1"],
        "v1_exact_keys": exact["v1"],
        "v2_exact_keys": exact["v2"],
        "current_content_available": bool(exact[standing_version]),
        "history_content_available": bool(exact["v1"]),
        "incomplete_keys": incomplete,
        "unassessed_representation_keys": unassessed,
        "excluded_decoy_keys": sorted(set(after) & set(case.decoys)),
        "changes": changes,
        "new_exact_copy_keys": [
            key
            for key in changes["created"]
            if key not in case.decoys and after[key] in before.values()
        ],
        "duplicate_content_groups": {
            version: keys for version, keys in exact.items() if len(keys) > 1
        },
        "duplicate_content_groups_are_definite_duplicates": False,
        "reproduction_changes": changes if stage.name not in {"establish", "revise"} else None,
        "standing_identity": _standing(after, exact[standing_version], standing_keys),
        "historical_bodies": _history(before, after, history_keys),
        "surrounding_prose": "not_assessed",
        "unchanged_write_attempts": "requires_command_receipts",
        "retrieval_route": "requires_command_receipts",
    }
