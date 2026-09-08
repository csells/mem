"""Combine completed manual audits; never infer fidelity from command counts."""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(item, family, source, root):
    lifecycle = item["lifecycle"]
    finance = family == "finance"
    artifacts = (item["artifacts"] if finance else
                 {str(row["stage"]): row["passed"] for row in item["artifact_results"]})
    if set(artifacts) != {str(stage) for stage in range(1, 7)}:
        raise ValueError(f"Missing stage audits: {lifecycle}")
    for stage, passed in artifacts.items():
        actual = read(root / "cases" / lifecycle / f"stage-{stage}" / "result.json")
        if type(passed) is not bool or passed != actual["artifact_passed"]:
            raise ValueError(f"Audit/artifact disagreement: {lifecycle}/{stage}")
    fidelity = item["current_and_historical_faithful"]
    fidelity = {str(stage): fidelity[f"stage{stage}" if finance else str(stage)]
                for stage in (3, 5, 6)}
    mutation = item["unsupported_standing_or_historical_mutation"]
    if finance:
        mutation = mutation["complete_lifecycle"]
    duplicate = (item["stage6"]["duplicate_curation"] if finance else
                 item["stage6_duplicate_curation"])
    initial = item["initial_capture_faithful"]
    legs = []
    for stage in (2, 4, 5):
        leg = item["retrieval_legs"][str(stage)]
        required = ("applicable_prior_record_at_entry", "full_prior_body_read",
                    "pre_edit_or_informed_use", "artifact_correct")
        if leg["artifact_correct"] != artifacts[str(stage)]:
            raise ValueError(f"Retrieval/artifact disagreement: {lifecycle}/{stage}")
        values = [leg[key] for key in required]
        successful = (False if False in values else
                      True if all(value is True for value in values) else None)
        for field in ("successful_use", "successful_prior_record_use"):
            if field in leg and leg[field] != successful:
                raise ValueError(f"Retrieval score disagreement: {lifecycle}/{stage}/{field}")
        if successful and leg["route"] not in ("direct", "search"):
            raise ValueError(f"Unclassified successful route: {lifecycle}/{stage}")
        legs.append({"stage": stage, **leg, "successful_use_normalized": successful})
    components = [initial, *artifacts.values(), *fidelity.values(),
                  *(leg["successful_use_normalized"] for leg in legs),
                  not mutation if type(mutation) is bool else None,
                  not duplicate if type(duplicate) is bool else None]
    calculated = ("false" if False in components else
                  "true" if all(value is True for value in components) else "unverified")
    reported = item["strict_six_stage_intersection"]
    if isinstance(reported, dict):
        reported = reported["status"]
    elif type(reported) is bool:
        reported = str(reported).lower()
    if calculated != reported:
        raise ValueError(f"Strict intersection disagreement: {lifecycle}: {calculated} != {reported}")
    return {"lifecycle": lifecycle, "profile_id": item["profile_id"],
            "arm": item["arm"], "family": family,
            "mode": "normal" if lifecycle.endswith("-normal") else "isolated",
            "catalog_mode": item["catalog_mode"],
            "initial_capture_faithful": initial,
            "current_and_historical_faithful": fidelity,
            "artifacts": artifacts, "retrieval_legs": legs,
            "unsupported_standing_or_historical_mutation": mutation,
            "stage6_duplicate_curation": duplicate,
            "strict_six_stage_intersection": calculated,
            "audit_source": str(source.relative_to(root)),
            "audit_source_sha256": digest(source)}


def metrics(rows):
    legs = [leg for row in rows for leg in row["retrieval_legs"]]
    successful = [leg for leg in legs if leg["successful_use_normalized"] is True]
    return {"lifecycles": len(rows),
            "initial_faithful": sum(row["initial_capture_faithful"] is True for row in rows),
            "initial_unverified": sum(row["initial_capture_faithful"] is None for row in rows),
            "all_six_artifacts": sum(all(row["artifacts"].values()) for row in rows),
            "current_and_historical_faithful": {
                str(stage): sum(row["current_and_historical_faithful"][str(stage)] is True for row in rows)
                for stage in (3, 5, 6)},
            "current_and_historical_unverified": {
                str(stage): sum(row["current_and_historical_faithful"][str(stage)] is None for row in rows)
                for stage in (3, 5, 6)},
            "eligible_retrieval_legs": len(legs),
            "applicable_record_at_entry": sum(leg["applicable_prior_record_at_entry"] is True for leg in legs),
            "entry_applicability_unverified": sum(leg["applicable_prior_record_at_entry"] is None for leg in legs),
            "full_prior_body_read": sum(leg["full_prior_body_read"] is True for leg in legs),
            "successful_prior_use": len(successful),
            "successful_prior_use_by_route": dict(collections.Counter(leg["route"] for leg in successful)),
            "correct_eligible_artifact_without_verified_prior_use": sum(
                leg["artifact_correct"] is True and leg["successful_use_normalized"] is not True for leg in legs),
            "unsupported_agreement_mutation": sum(row["unsupported_standing_or_historical_mutation"] is True for row in rows),
            "duplicate_curation_stage6": sum(row["stage6_duplicate_curation"] is True for row in rows),
            "strict_intersection": dict(collections.Counter(row["strict_six_stage_intersection"] for row in rows))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--finance", type=Path, action="append", required=True)
    parser.add_argument("--webhooks", type=Path, required=True)
    parser.add_argument("--include-normal", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for source in args.finance:
        for item in read(source)["lifecycle_summaries"]:
            rows.append(normalize(item, "finance", source, args.root))
    for source in sorted(args.webhooks.glob("*.json")):
        rows.append(normalize(read(source), "webhooks", source, args.root))
    wanted = {slot["lifecycle"] for slot in read(args.root / "manifest.json")["slots"]
              if args.include_normal or slot["mode"] == "isolated"}
    if len(rows) != len(wanted) or {row["lifecycle"] for row in rows} != wanted:
        raise ValueError("Completed semantic audits do not exactly cover the frozen lifecycle set")
    output = {"schema": "policy-handoff-semantic-summary.v1", "rows": rows,
              "overall": metrics(rows),
              "limits": ["Manual source/trace audits by unblinded agents involved in corpus development/review; finance reviewer authored its corpus, Courier reviewer cross-reviewed it. Not independent human annotation.",
                         "Useful applicable records may be incomplete; fidelity is a separate outcome.",
                         "Full prior reads can inform validation when earlier work already implemented the requested behavior.",
                         "Strict core success does not certify every surrounding claim or full compliance with all procedure steps."]}
    for field in ("profile_id", "arm", "family", "mode", "catalog_mode"):
        output[field] = {value: metrics([row for row in rows if row[field] == value])
                         for value in dict.fromkeys(row[field] for row in rows)}
    output["main_arm"] = {arm: metrics([row for row in rows if row["arm"] == arm and row["mode"] == "isolated"])
                          for arm in ("generic", "occasions")}
    output["main_profile_arm"] = {f"{profile}/{arm}": metrics([row for row in rows if row["profile_id"] == profile and row["arm"] == arm and row["mode"] == "isolated"])
                                  for profile in dict.fromkeys(row["profile_id"] for row in rows)
                                  for arm in ("generic", "occasions")}
    with args.out.open("x") as handle:
        json.dump(output, handle, indent=2)
        handle.write("\n")
    print(json.dumps(output["overall"], indent=2))
