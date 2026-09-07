"""Independent saved-artifact recheck; no model calls or original-state writes.

Run with the resolved venv interpreter and memory-bench/site-packages on PYTHONPATH.
Only new scratch copies and an exclusive output file are written.
"""

import hashlib
import json
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile

from scripts import memory_contract_experiment as contract
from scripts import memory_e2e_experiment as e2e
from membench.runner.memory_e2e_corpus import build_e2e_case

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(path):
    result = {}
    if not path.exists():
        return result
    for directory, dirs, files in os.walk(path, followlinks=False):
        for name in list(dirs):
            item = Path(directory) / name
            if item.is_symlink():
                result[str(item.relative_to(path))] = {"link": os.readlink(item)}
                dirs.remove(name)
        for name in files:
            item = Path(directory) / name
            result[str(item.relative_to(path))] = (
                {"link": os.readlink(item)} if item.is_symlink() else sha(item)
            )
    return result


manifest = json.loads((OUT / "manifest.json").read_text())
contract.assert_frozen(manifest)
case = build_e2e_case()
scratch = Path(tempfile.mkdtemp(prefix="mem-contract-regrade-")).resolve()
rows, transfers, native = [], [], []
inputs = {}
for group in manifest["cases"]:
    previous = None
    for stage in case.stages:
        evidence = OUT / "cases" / group["id"] / stage.name
        assessment = evidence / "assessment.json"
        if not assessment.is_file():
            continue
        original = json.loads(assessment.read_text())
        for relative in (
            "assessment.json",
            "execution.json",
            "memory-before.json",
            "memory-after.json",
            "task-before.json",
            "tasks-after.json",
        ):
            path = evidence / relative
            inputs[str(path)] = sha(path)
        for name in ("workspace-before", "workspace-after", "native-after"):
            for relative, digest in tree(evidence / name).items():
                if isinstance(digest, str):
                    inputs[str(evidence / name / relative)] = digest
        local = scratch / group["id"] / stage.name
        local.mkdir(parents=True)
        work = local / "work"
        e2e.snapshot(evidence / "workspace-after", work)
        grade = e2e.assess_feature(work, stage, case, local)
        public = contract.assess_checker(work, stage.component, local)
        fields = ("passed", "policy", "source", "rationale", "behavior", "observations")
        row = {
            "case": group["id"],
            "stage": stage.name,
            "artifact_grade_matches": all(
                grade.get(k) == original["artifact"].get(k) for k in fields
            ),
            "artifact": grade,
            "canonical_public_check_completed": public["completed"],
            "canonical_public_verdicts_match": all(
                public.get(k, {}).get("passed")
                == original["canonical_public_check"].get(k, {}).get("passed")
                for k in ("component", "whole_workspace")
            ),
        }
        rows.append(row)
        if previous is not None:
            transfers.append(
                {
                    "case": group["id"],
                    "from": previous.name,
                    "to": stage.name,
                    "memory_equal": json.loads((previous / "memory-after.json").read_text())
                    == json.loads((evidence / "memory-before.json").read_text()),
                    "workspace_equal": tree(previous / "workspace-after")
                    == tree(evidence / "workspace-before"),
                }
            )
        saved_native = evidence / "native-after"
        native_row = {
            "case": group["id"],
            "stage": stage.name,
            "files": tree(saved_native),
            "matches_original": tree(saved_native)
            == tree(Path(original["execution"]["scratch"]) / "native"),
            "sqlite": [],
            "nonempty_wal_paths": [
                str(path.relative_to(saved_native))
                for path in saved_native.rglob("*-wal")
                if path.stat().st_size
            ],
        }
        for db in saved_native.rglob("*.sqlite"):
            with closing(sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)) as conn:
                tables = {
                    r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                counts = {
                    name: conn.execute('SELECT COUNT(*) FROM "' + name + '"').fetchone()[0]
                    for name in ("stage1_outputs", "jobs")
                    if name in tables
                }
            native_row["sqlite"].append(
                {"path": str(db.relative_to(saved_native)), "counts": counts}
            )
        native.append(native_row)
        previous = evidence
        print(
            f"Regraded {len(rows)}/32 {group['id']}/{stage.name}: match={row['artifact_grade_matches']}",
            flush=True,
        )

changed = [name for name, digest in inputs.items() if sha(Path(name)) != digest]
expected = {(group["id"], stage.name) for group in manifest["cases"] for stage in case.stages}
observed = {(row["case"], row["stage"]) for row in rows}
result = {
    "schema": "memory-contract-independent-recheck.v1",
    "model_calls": 0,
    "script_sha256": sha(Path(__file__)),
    "scratch": str(scratch),
    "frozen_source_files_verified": len(manifest["source_sha256"]),
    "frozen_executables_verified": len(manifest["binary_sha256"]),
    "rows": rows,
    "transfers": transfers,
    "native": native,
    "expected_assessments": len(expected),
    "missing_assessments": sorted(expected - observed),
    "complete_cohort_rechecked": observed == expected and len(transfers) == 28,
    "inputs_sha256": inputs,
    "changed_inputs": changed,
    "all_present_checks_passed": bool(rows)
    and not changed
    and all(
        row["artifact_grade_matches"]
        and row["canonical_public_check_completed"]
        and row["canonical_public_verdicts_match"]
        for row in rows
    )
    and all(row["memory_equal"] and row["workspace_equal"] for row in transfers)
    and all(row["matches_original"] for row in native),
}
with (OUT / "final-evidence-audit-01.json").open("x") as output:
    json.dump(result, output, indent=2)
    output.write("\n")
print(
    json.dumps(
        {
            "regraded": len(rows),
            "transfers": len(transfers),
            "preserved_inputs": len(inputs),
            "all_present_checks_passed": result["all_present_checks_passed"],
            "complete_cohort_rechecked": result["complete_cohort_rechecked"],
        }
    )
)
