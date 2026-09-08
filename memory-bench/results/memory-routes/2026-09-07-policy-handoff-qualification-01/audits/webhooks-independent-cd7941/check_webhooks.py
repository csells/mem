"""Independent no-model admission checks; writes only new audit evidence."""
from datetime import datetime
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
import subprocess

from membench.runner.memory_routes_runtime import make_profile
from scripts.memory_routes_experiment import PYTHON

HERE = Path(__file__).resolve().parent
SOURCE = Path.cwd() / "fixtures/memory-policy-fork-corpus/webhooks"
ROOT = Path(tempfile.mkdtemp(prefix="webhooks-independent-", dir="/tmp"))
WORLDS = ("global-first", "account-first")
for world in WORLDS:
    shutil.copytree(SOURCE / world, ROOT / world, ignore=shutil.ignore_patterns("__pycache__"))
with (HERE / "scratch.json").open("x") as evidence:
    json.dump({"scratch": str(ROOT), "source": str(SOURCE)}, evidence)


def same(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def calculate(request, world, stage, reverse_scope=False, wrong_priority=False):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command not in ("count", "summary", "accepted"):
        return {"error": "unknown_command"}
    version = request.get("protocol", "1" if stage < 3 else "2")
    global_ids = (world == "global-first") == (version == "1")
    if reverse_scope:
        global_ids = not global_ids
    earliest = (version == "1") != wrong_priority
    selected = {}
    receipts = request["receipts"]
    assert len({r["record_id"] for r in receipts}) == len(receipts)
    if command == "count":
        assert len({r["account_id"] for r in receipts}) <= 1
    for row in receipts:
        assert set(row) == {"record_id", "account_id", "delivery_id", "occurred_at", "payload"}
        assert all(type(row[k]) is str and row[k] for k in ["record_id", "account_id", "delivery_id"])
        assert type(row["payload"]) is str
        instant = datetime.fromisoformat(row["occurred_at"].replace("Z", "+00:00"))
        assert instant.tzinfo is not None and 2020 <= instant.year <= 2099
        key = (row["delivery_id"],) if global_ids else (row["account_id"], row["delivery_id"])
        if key not in selected:
            selected[key] = (instant, row)
            continue
        previous_instant, previous_row = selected[key]
        better_time = instant < previous_instant if earliest else instant > previous_instant
        if better_time or instant == previous_instant and row["record_id"] < previous_row["record_id"]:
            selected[key] = (instant, row)
    chosen_ids = {row["record_id"] for _, row in selected.values()}
    result = {"protocol": version, "accepted_count": len(selected),
              "duplicate_count": len(receipts) - len(selected)}
    if command == "accepted":
        result["receipts"] = [row for row in receipts if row["record_id"] in chosen_ids]
    return result


def digest_inputs():
    return {str(p.relative_to(SOURCE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for world in WORLDS for p in sorted((SOURCE / world).rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


before = digest_inputs()
profile = make_profile(HERE / "readonly.sb", [], [ROOT, PYTHON.parent.parent])
environment = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(HERE)}
records = []
public = []
discriminators = []
for world in WORLDS:
    project = ROOT / world
    tasks = json.loads((project / "tasks.json").read_text())["tasks"]
    for stage in range(1, 7):
        stage_reference = project / ("reference-stage-" + str(stage))
        stage_reference.mkdir()
        reference_source = (project / "reference/main.py").read_text()
        if stage < 3:
            reference_source = reference_source.replace('CURRENT = "2"', 'CURRENT = "1"')
        with (stage_reference / "main.py").open("x") as stage_program:
            stage_program.write(reference_source)
        cases = json.loads((project / "graders" / f"stage-{stage}.json").read_text())
        scope_differences = []
        priority_differences = []
        for case in cases:
            if "artifact_json_path" in case:
                actual = json.loads((project / "reference" / case["artifact_json_path"]).read_text())
                req = case["expected"]["request"]
                independent = {"request": req, "response": calculate(req, world, stage)}
                code = 0
            else:
                assert case.get("argv", []) == []
                request = case["stdin"]
                process = subprocess.run(["/usr/bin/sandbox-exec", "-f", str(profile),
                                          str(PYTHON), str(stage_reference / "main.py")],
                                         input=json.dumps(request), text=True, capture_output=True,
                                         timeout=5, env=environment, cwd=stage_reference)
                code = process.returncode
                actual = json.loads(process.stdout) if code == 0 else {"error": process.stderr}
                independent = calculate(request, world, stage)
                if not same(calculate(request, world, stage, reverse_scope=True), independent):
                    scope_differences.append(case["name"])
                if not same(calculate(request, world, stage, wrong_priority=True), independent):
                    priority_differences.append(case["name"])
            records.append({"world": world, "stage": stage, "name": case["name"],
                            "reference_matches": code == 0 and same(actual, case["expected"]),
                            "independent_oracle_matches": same(independent, case["expected"])})
        discriminators.append({"world": world, "stage": stage,
                               "opposite_scope_rejected_by": scope_differences,
                               "wrong_priority_rejected_by": priority_differences})
        for task in tasks[:stage]:
            for case in json.loads((project / task["public_tests"]).read_text()):
                if "artifact_json_path" in case:
                    req = case["expected"]["request"]
                    independent = {"request": req, "response": calculate(req, world, stage)}
                else:
                    independent = calculate(case["request"], world, stage)
                public.append({"world": world, "stage": stage, "name": case["name"],
                               "passed": same(independent, case["expected"])})
        print(world, stage, len(cases), "hidden checked", flush=True)
after = digest_inputs()
report = {"scope": "independent no-model webhooks admission; author-unblinded reviewer",
          "reference_correct": sum(x["reference_matches"] for x in records),
          "independent_oracle_correct": sum(x["independent_oracle_matches"] for x in records),
          "hidden_total": len(records), "public_correct": sum(x["passed"] for x in public),
          "public_total": len(public), "source_unchanged": before == after,
          "source_sha256": before, "python": str(PYTHON),
          "python_sha256": hashlib.sha256(PYTHON.read_bytes()).hexdigest(),
          "records": records, "public": public, "discriminators": discriminators}
report["passed"] = (report["reference_correct"] == report["independent_oracle_correct"] == len(records)
                    and report["public_correct"] == len(public) and before == after)
with (HERE / "validation.json").open("x") as output:
    json.dump(report, output, indent=2)
print(json.dumps({k: v for k, v in report.items() if k not in
                  ["source_sha256", "records", "public", "discriminators"]}), flush=True)
raise SystemExit(not report["passed"])
