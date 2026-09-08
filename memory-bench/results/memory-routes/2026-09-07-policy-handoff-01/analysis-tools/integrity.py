"""Read-only audit of published evidence; never invokes agents or the memory CLI."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(root, repo):
    manifest = read(root / "manifest.json")
    findings, rows = [], []
    hashes = {}
    for field in ("source_sha256", "binary_sha256", "profile_sha256"):
        checks = []
        for name, expected in manifest[field].items():
            path = Path(name)
            if not path.is_absolute():
                path = repo / path
            actual = digest(path) if path.is_file() else None
            checks.append({"path": name, "matches": actual == expected})
            if actual != expected:
                findings.append({"kind": field, "path": name})
        hashes[field] = {"checked": len(checks), "matching": sum(c["matches"] for c in checks)}
    for slot in manifest["slots"]:
        folder = root / "cases" / slot["lifecycle"] / f"stage-{slot['stage']}"
        if not (folder / "result.json").is_file():
            continue
        result = read(folder / "result.json")
        before, after = read(folder / "memory-before.json"), read(folder / "memory-after.json")
        prior = folder.parent / f"stage-{slot['stage']-1}" / "memory-after.json"
        tasks = read(root / "frozen-source/memory-bench/fixtures/memory-policy-fork-corpus" / slot["corpus_family"] / "tasks.json")
        task = read(folder / "task.json")
        spec = tasks["tasks"][slot["stage"] - 1]
        expected_body = (tasks.get("common_contract", "") + "\n\n" + spec["prompt"]).strip()
        expected_catalog = {"keys": sorted(before)}
        catalog = folder / "memory-catalog-before.json"
        checks = {
            "slot_identity": all(result[k] == v for k, v in slot.items()),
            "prompt_only_issue_assignment": (folder / "prompt.txt").read_text() == f"Work on {task['id']}.",
            "issue_matches_frozen_task": task["description"] == expected_body and task["title"] == spec["title"],
            "memory_carryforward_exact": before == (read(prior) if slot["stage"] > 1 else {}),
            "catalog_only_actual_keys": read(catalog) == expected_catalog if slot["catalog_mode"] == "indexed" else not catalog.exists(),
            "reported_requested_model": result["models_observed"] == [manifest["model_profiles"][slot["profile_id"]]["model"]],
            "guidance_unchanged": not result["package_changed_paths"],
            "receipt_ancestry_complete": result["receipt_assessment"]["unknown_execution"] == 0,
            "no_credential_redaction_needed": not result["credential_redaction_required"],
        }
        for name, passed in checks.items():
            if not passed:
                findings.append({"kind": name, "slot": slot["slot"]})
        errors = result.get("errors", [])
        quota = any("usage limit" in str(error).lower() for error in errors)
        rows.append({
            **slot, "checks": checks,
            "quota_error": quota,
            "host_success": result["host_success"],
            "tool_calls": len(read(folder / "tool-calls.json")),
            "artifact_passed": result["artifact_passed"],
            "error_messages": errors,
            "entry_record_count": len(before), "exit_record_count": len(after),
            "native_files": [str(p.relative_to(folder / "native-after")) for p in (folder / "native-after").rglob("*") if p.is_file()],
        })
    return {"schema": "policy-handoff-integrity.v1", "created_ns": time.time_ns(),
            "manifest_sha256": digest(root / "manifest.json"), "hashes": hashes,
            "assessed": len(rows), "findings": findings, "rows": rows,
            "limits": ["Model identity metadata on a quota-only turn does not prove model generation.",
                       "Native file presence alone does not prove automatic extraction or use.",
                       "Frozen task equality does not replace the pre-run semantic cue audit.",
                       "Memory equality verifies carryforward, not truth or completeness."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.root, args.repo)
    with args.out.open("x") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps({k: report[k] for k in ("hashes", "assessed", "findings")}, indent=2))
