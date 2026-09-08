"""Independent no-model admission checks; writes only new audit evidence."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

from membench.runner.memory_routes_runtime import make_profile
from scripts.memory_routes_experiment import PYTHON

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd() / "fixtures/memory-policy-fork-corpus/finance"
WORLDS = ("account-first", "subscription-first")


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
        return {"status": "ok", "product": "Meridian Credits"}
    if command not in ("quote", "total", "statement"):
        return {"error": "unknown_command"}
    version = request.get("release", "1.0" if stage < 3 else "2.0")
    rate, cap = (10, 2400) if version == "1.0" else (15, 3000)
    account = (world == "account-first") == (version == "1.0")
    if reverse_scope:
        account = not account
    rows = [request["line"]] if command == "quote" else request["lines"]
    awards = [0] * len(rows)
    groups = {}
    for i, line in enumerate(rows):
        group = (line["account_id"],) if account else (line["account_id"], line["subscription_id"])
        groups.setdefault(group, []).append(i)
    historical = version == "1.0"
    if wrong_priority:
        historical = not historical
    for members in groups.values():
        # Use stable two-pass ordering within each independently capped group.
        ordered = sorted(members, key=lambda i: rows[i]["line_id"])
        ordered.sort(key=lambda i: rows[i]["service_on"] if historical else rows[i]["charge_cents"],
                     reverse=not historical)
        used = 0
        for i in ordered:
            entitlement = rows[i]["charge_cents"] * rate // 100
            awards[i] = min(entitlement, cap - used)
            used += awards[i]
    total = sum(awards)
    result = {"release": version, "credit_cents": total,
              "amount_due_cents": sum(row["charge_cents"] for row in rows) - total}
    if command == "quote":
        result["line_id"] = rows[0]["line_id"]
    elif command == "statement":
        result["lines"] = [{"line_id": row["line_id"], "credit_cents": awards[i],
                           "amount_due_cents": row["charge_cents"] - awards[i]}
                          for i, row in enumerate(rows)]
    return result


def digest_inputs():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for world in WORLDS for p in sorted((ROOT / world).rglob("*"))
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
                                          str(PYTHON), str(project / "reference/main.py"), str(stage)],
                                         input=json.dumps(request), text=True, capture_output=True,
                                         timeout=5, env=environment, cwd=project / "reference")
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
report = {"scope": "independent no-model finance admission; author-unblinded reviewer",
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
