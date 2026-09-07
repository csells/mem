"""Run an issue's externally supplied public examples against main.py."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())
    failures = 0
    for case in cases:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("main.py"))], input=json.dumps(case["request"]), text=True, capture_output=True, timeout=3)
        try:
            actual = json.loads(result.stdout)
            success = result.returncode == 0 and actual == case["expected"]
        except ValueError:
            actual = result.stdout
            success = False
        print(("PASS " if success else "FAIL ") + case["name"])
        if not success:
            failures += 1
            print("  expected:", case["expected"])
            print("  actual:", actual)
            if result.stderr:
                print("  stderr:", result.stderr)
    return int(failures != 0)


if __name__ == "__main__":
    raise SystemExit(run())
