#!/usr/bin/env python3
"""Check the independent reference, public examples, and defect sensitivity."""
import json
from pathlib import Path
import subprocess
import sys

from grade import cases_for, evaluate, identical


ROOT = Path(__file__).resolve().parents[1]


def main():
    results = {"reference": [], "public_examples": [], "mutations": []}
    ok = True
    for stage in range(1, 7):
        serialized = json.loads((ROOT / "graders" / f"stage-{stage}.json").read_text())
        generated = [{"name": name, "stdin": request, "expected": expected, "argv": []} for name, request, expected in cases_for(stage)]
        if not identical(serialized, generated):
            raise AssertionError(f"Stage {stage} JSON fixtures differ from the authored grader")
        result = evaluate(ROOT / "reference", stage, ["--stage", str(stage)])
        results["reference"].append({key: result[key] for key in ("stage", "total", "passed", "failed")})
        print(f"Reference stage {stage}: {result['passed']}/{result['total']}", flush=True)
        ok = ok and result["failed"] == 0
        for case in json.loads((ROOT / "public_tests" / f"stage_{stage}.json").read_text()):
            process = subprocess.run([sys.executable, str(ROOT / "reference" / "main.py"), "--stage", str(stage)], input=json.dumps(case["request"]), capture_output=True, text=True, timeout=3)
            matched = process.returncode == 0 and identical(json.loads(process.stdout), case["expected"])
            results["public_examples"].append({"stage": stage, "name": case["name"], "passed": matched})
            ok = ok and matched
    for mutation in json.loads((ROOT / "graders" / "mutations.json").read_text()):
        stage = mutation["stage"]
        result = evaluate(ROOT / "graders" / mutation["project"], stage, ["--stage", str(stage)])
        detected = result["failed"] > 0
        results["mutations"].append({"name": mutation["name"], "stage": stage, "detected": detected, "failures": result["failed"], "example_failure": result["failures"][0]["case"] if detected else None})
        print(f"Mutation {mutation['name']}: {'DETECTED' if detected else 'MISSED'} ({result['failed']} failing cases)", flush=True)
        ok = ok and detected
    results["ok"] = ok
    print(json.dumps(results, indent=2))
    return int(not ok)


if __name__ == "__main__":
    raise SystemExit(main())
