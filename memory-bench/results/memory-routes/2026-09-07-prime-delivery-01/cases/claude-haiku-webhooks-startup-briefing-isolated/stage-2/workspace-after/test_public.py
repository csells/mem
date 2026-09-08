"""Run one supplied public case file against the local application/artifacts."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    return left == right


parser = argparse.ArgumentParser()
parser.add_argument("--cases", required=True)
args = parser.parse_args()
failed = 0
for case in json.loads(Path(args.cases).read_text()):
    try:
        if "artifact_json_path" in case:
            got = json.loads(Path(case["artifact_json_path"]).read_text())
        else:
            proc = subprocess.run([sys.executable, "main.py"], input=json.dumps(case["request"]),
                                  capture_output=True, text=True, check=True, timeout=5)
            got = json.loads(proc.stdout)
        ok = equal(got, case["expected"])
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        ok = False
        got = str(exc)
    print(("PASS " if ok else "FAIL ") + case["name"])
    if not ok:
        print(" expected:", case["expected"])
        print(" received:", got)
        failed += 1
raise SystemExit(bool(failed))
