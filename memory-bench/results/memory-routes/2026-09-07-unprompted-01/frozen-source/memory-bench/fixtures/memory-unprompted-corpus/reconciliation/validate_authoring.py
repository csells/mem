"""Revalidate cases and bad implementations in a fresh, self-contained scratch run."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("grader", ROOT / "graders/grade.py")
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)
run_dir = Path(tempfile.mkdtemp(prefix="validation-run-", dir=ROOT))
report = {"run_dir": str(run_dir), "references": [], "public_examples": [], "mutations": []}

public = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                        cwd=ROOT / "starter", capture_output=True, text=True)
report["public_tests"] = {"exit_code": public.returncode, "stdout": public.stdout, "stderr": public.stderr}
assert public.returncode == 0, public.stderr
print("Public starter tests passed.", flush=True)

baseline = grader.grade(1, ROOT / "starter")
report["starter_stage1"] = baseline
assert not baseline["ok"]
print(f"Starter correctly fails stage 1: {baseline['passed']}/{baseline['total']} passed.", flush=True)

for stage in range(1, 7):
    authored = [{"name": name, "input": request, "expected": expected, "argv": []}
                for name, request, expected in grader.cases(stage)]
    loaded = json.loads((ROOT / "graders" / f"stage-{stage}.json").read_text())
    assert authored == loaded, f"Serialized cases disagree at stage {stage}"
    result = grader.grade(stage, ROOT / "reference" / f"stage_{stage}")
    report["references"].append(result)
    assert result["ok"], result
    print(f"[{stage}/6] Reference: {result['passed']}/{result['total']} passed.", flush=True)
    for case in json.loads((ROOT / "public_tests" / f"stage_{stage}.json").read_text()):
        proc = subprocess.run([sys.executable, str(ROOT / "reference" / f"stage_{stage}" / "cli.py")],
                              input=json.dumps(case["input"]), text=True, capture_output=True, timeout=5)
        passed = proc.returncode == 0 and json.dumps(json.loads(proc.stdout), sort_keys=True) == json.dumps(case["expected"], sort_keys=True)
        report["public_examples"].append({"stage": stage, "name": case["name"], "passed": passed})
        assert passed, case

source = (ROOT / "reference/engine.py").read_text()
cr_buggy_csv = r'''def csv_record(values):
    def quote_field(value):
        text = str(value)
        if any(character in text for character in (",", '"', "\n")):
            return '"' + text.replace('"', '""') + '"'
        return text
    return ",".join(quote_field(value) for value in values) + "\n"


'''
mutations = [
    ("current-reports-still-UTC", 4, [
        ('shifted = stage >= 4 and op in', 'shifted = False and op in'),
    ]),
    ("incident-follows-current", 4, [
        ('op in {"reconcile", "refunds_csv", "daily_net"}', 'op in {"reconcile", "refunds_csv", "daily_net", "incident_replay"}'),
    ]),
    ("release1-follows-current", 6, [
        ('op in {"reconcile", "refunds_csv", "daily_net"}', 'op in {"reconcile", "refunds_csv", "daily_net", "release1_reconcile"}'),
    ]),
    ("replay-recreates-original-omission", 3, [
        ('        rows.append(row)', '        if op == "incident_replay" and (date + timedelta(days=1)).day == 1:\n            continue\n        rows.append(row)'),
    ]),
    ("release1-recreates-original-omission", 6, [
        ('        rows.append(row)', '        if op == "release1_reconcile" and (date + timedelta(days=1)).day == 1:\n            continue\n        rows.append(row)'),
    ]),
    ("timestamp-offsets-ignored", 1, [
        ('.astimezone(timezone.utc)', '.replace(tzinfo=timezone.utc)'),
    ]),
    ("ordered-by-id", 1, [
        ('key=lambda row: (posting(row), row["id"])', 'key=lambda row: row["id"]'),
    ]),
    ("daily-calendar-dates", 5, [
        ('date = (posting(row) - shift).date().isoformat()', 'date = posting(row).date().isoformat()'),
    ]),
    ("upper-bound-included", 1, [
        ('date = (posting(row) - shift).date()', 'date = (posting(row) - shift - timedelta(milliseconds=1)).date()'),
    ]),
    ("csv-bare-CR-not-quoted", 2, [
        (source[source.index("def csv_record"):source.index("def process")], cr_buggy_csv),
    ]),
]
for index, (name, stage, replacements) in enumerate(mutations, 1):
    target = run_dir / name
    target.mkdir()
    mutated = source
    for old, new in replacements:
        assert old in mutated, (name, old)
        mutated = mutated.replace(old, new)
    (target / "engine.py").write_text(mutated)
    (target / "cli.py").write_text(f"from engine import run\nrun({stage})\n")
    shutil.copyfile(ROOT / "reference/ledgerlake_snapshot.json", target / "ledgerlake_snapshot.json")
    result = grader.grade(stage, target)
    report["mutations"].append({"name": name, **result})
    assert not result["ok"], f"Grader failed to reject {name}"
    print(f"[{index}/{len(mutations)}] Rejected {name}: {result['total'] - result['passed']} failing cases.", flush=True)

(run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print("Validation evidence: " + str(run_dir / "report.json"), flush=True)
