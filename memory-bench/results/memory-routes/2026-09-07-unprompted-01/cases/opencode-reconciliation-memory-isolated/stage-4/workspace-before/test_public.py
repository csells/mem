"""Run the public examples supplied with a product issue."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args()
    failures = 0
    for case in json.loads(args.cases.read_text()):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("cli.py"))],
                                input=json.dumps(case["input"]), text=True,
                                capture_output=True, timeout=5)
        try:
            actual = json.loads(result.stdout)
            passed = result.returncode == 0 and json.dumps(actual, sort_keys=True) == json.dumps(case["expected"], sort_keys=True)
        except ValueError:
            passed = False
        print(("PASS " if passed else "FAIL ") + case["name"])
        if not passed:
            failures += 1
            print("Expected:", case["expected"])
            print("Received:", result.stdout)
            print("stderr:", result.stderr)
    return int(failures != 0)


if __name__ == "__main__":
    raise SystemExit(main())
