"""Offline validation, exclusive evidence writes, and mutation sensitivity."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
OUT = ROOT / ("validation-" + str(time.time_ns()))
OUT.mkdir()


def read(p):
    return json.loads(p.read_text())


def put(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x") as f:
        f.write(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n")


def equal(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


def case_result(home, stage, case):
    try:
        if "artifact_json_path" in case:
            got = read(home / case["artifact_json_path"])
        else:
            result = subprocess.run([sys.executable, str(home / "main.py"), str(stage)],
                                    input=json.dumps(case["stdin"]), capture_output=True,
                                    text=True, timeout=5, cwd=home)
            if result.returncode:
                return {"name":case["name"], "passed":False, "error":result.stderr}
            got = json.loads(result.stdout)
        return {"name":case["name"], "passed":equal(got, case["expected"]), "actual":got}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {"name":case["name"], "passed":False, "error":str(exc)}


worlds = ["account-first", "subscription-first"]
checks = []
public = []
mutations = []
for world in worlds:
    project = ROOT / world
    for stage in range(1, 7):
        cases = read(project / "graders" / f"stage-{stage}.json")
        findings = [case_result(project / "reference", stage, c) for c in cases]
        row = {"world":world, "stage":stage, "passed":all(c["passed"] for c in findings),
               "correct":sum(c["passed"] for c in findings), "total":len(findings), "cases":findings}
        checks.append(row)
        print(world, "stage", stage, row["correct"], "/", row["total"], flush=True)
    tasks = read(project / "tasks.json")["tasks"]
    for stage in range(1, 7):
        for task in tasks[:stage]:
            for case in read(project / task["public_tests"]):
                converted = dict(case)
                if "request" in converted:
                    converted["stdin"] = converted.pop("request")
                row = case_result(project / "reference", stage, converted)
                public.append({"world":world, "stage":stage, "suite":task["public_tests"], **row})
    source = (project / "reference/main.py").read_text()
    variants = [
        ("wrong_initial_scope", 2, source.replace('by_account = WORLD == "account-first"', 'by_account = WORLD != "account-first"')),
        ("wrong_current_scope", 3, source.replace('by_account = WORLD != "account-first"', 'by_account = WORLD == "account-first"')),
        ("wrong_current_default", 3, source.replace('"1.0" if STAGE < 3 else "2.0"', '"1.0"')),
        ("cap_off_one", 1, source.replace('percentage, limit = 10, 2400', 'percentage, limit = 10, 2399')),
        ("round_after_group", 2, source.replace('pools.get(key, 0) + raw[row["line_id"]]', 'pools.get(key, 0) + row["charge_cents"]').replace('min(limit, entitlement)', 'min(limit, entitlement * percentage // 100)')),
        ("old_priority_on_current", 4, source.replace('(lambda row: (-row["charge_cents"], row["line_id"]))', '(lambda row: (row["service_on"], row["line_id"]))')),
        ("current_priority_on_history", 5, source.replace('(lambda row: (row["service_on"], row["line_id"]))', '(lambda row: (-row["charge_cents"], row["line_id"]))')),
        ("sort_output_instead_of_preserve", 4, source.replace('for row in rows]}', 'for row in sorted(rows, key=lambda row: row["line_id"])]}')),
        ("historical_scope_changed", 5, source.replace('by_account = WORLD == "account-first"', 'by_account = WORLD != "account-first"')),
    ]
    for name, stage, code in variants:
        assert code != source, name
        home = OUT / world / name
        put(home / "main.py", code)
        failed = []
        for case in read(project / "graders" / f"stage-{stage}.json"):
            result = case_result(home, stage, case)
            if not result["passed"]:
                failed.append(result)
        mutations.append({"world":world, "mutation":name, "stage":stage, "rejected":bool(failed), "failures":failed})
        print(world, name, "rejected" if failed else "SURVIVED", flush=True)
    for name, value in [("missing_artifact", None), ("wrong_artifact_type", {"request":{}, "response":False})]:
        home = OUT / world / name
        put(home / "main.py", source)
        if value is not None:
            put(home / "support/MC-406.json", value)
        case = read(project / "graders/stage-6.json")[-1]
        result = case_result(home, 6, case)
        mutations.append({"world":world, "mutation":name, "stage":6,
                          "rejected":not result["passed"], "failures":[result]})
    # Exercise the actual delivered checker and starter, without importing model tools.
    for task in tasks:
        proc = subprocess.run([sys.executable, "test_public.py", "--cases", "../"+task["public_tests"]],
                              cwd=project/"reference", capture_output=True, text=True, timeout=10)
        public.append({"world":world, "delivered_checker":task["public_tests"], "passed":proc.returncode==0,
                       "stdout":proc.stdout, "stderr":proc.stderr})
    smoke = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                           cwd=project/"starter", capture_output=True, text=True, timeout=10)
    public.append({"world":world, "starter_smoke":True, "passed":smoke.returncode==0,
                   "stdout":smoke.stdout, "stderr":smoke.stderr})

forks = []
for stage in range(1, 6):
    left = read(ROOT / worlds[0] / "graders" / f"stage-{stage}.json")
    right = read(ROOT / worlds[1] / "graders" / f"stage-{stage}.json")
    assert len(left) == len(right)
    assert all(a["name"] == b["name"] and a.get("stdin") == b.get("stdin") for a,b in zip(left,right))
    different = [a["name"] for a,b in zip(left,right) if not equal(a["expected"],b["expected"])]
    forks.append({"stage":stage, "same_requests":True, "different_expected_cases":different})
assert not forks[0]["different_expected_cases"]
assert forks[1]["different_expected_cases"]

report = {"kind":"offline same-author reference/oracle/public/mutation validation; no models",
          "hidden_correct":sum(c["correct"] for c in checks), "hidden_total":sum(c["total"] for c in checks),
          "all_reference_passed":all(c["passed"] for c in checks),
          "public_correct":sum(c["passed"] for c in public), "public_total":len(public),
          "all_public_passed":all(c["passed"] for c in public),
          "mutations_rejected":sum(c["rejected"] for c in mutations), "mutations_total":len(mutations),
          "all_mutations_rejected":all(c["rejected"] for c in mutations),
          "checks":checks, "public":public, "mutations":mutations, "forks":forks,
          "source_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                           for world in worlds for p in (ROOT/world).rglob("*")
                           if p.is_file() and "__pycache__" not in p.parts}}
put(OUT / "report.json", report)
print(json.dumps({k:v for k,v in report.items() if k not in ["checks","public","mutations","forks","source_sha256"]}, indent=2))
print("Evidence:", OUT)
raise SystemExit(not (report["all_reference_passed"] and report["all_public_passed"] and report["all_mutations_rejected"]))
