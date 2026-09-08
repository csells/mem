"""Extract real rejected command attempts for interface review, not API expansion."""
import argparse
import collections
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
manifest = json.loads((args.root / "manifest.json").read_text())
attempts = []
for slot in manifest["slots"]:
    path = args.root / "cases" / slot["lifecycle"] / f"stage-{slot['stage']}" / "result.json"
    if not path.is_file():
        continue
    result = json.loads(path.read_text())
    for index, event in enumerate(result["receipt_assessment"]["executions"]):
        if event.get("returncode") in (0, None):
            continue
        argv = event.get("operation_argv", [])
        lines = (event.get("stderr") or event.get("stdout") or "").strip().splitlines()
        attempts.append({**slot, "receipt_index": index,
                         "source": str(path.relative_to(args.root)),
                         "argv_preview": [str(arg)[:120] for arg in argv[:5]],
                         "first_argument": argv[0] if argv else None,
                         "returncode": event["returncode"],
                         "error_first_line": lines[0][:300] if lines else ""})
report = {"schema": "policy-handoff-command-feedback.v1", "attempts": attempts,
          "failed_invocations": len(attempts),
          "by_first_argument": dict(collections.Counter(a["first_argument"] for a in attempts)),
          "limits": ["Counts are executed rejected invocations, not unique agents or failed tasks.",
                     "Attempted syntax is design evidence; ambiguous semantics do not automatically justify permanent aliases.",
                     "No command behavior was changed during the frozen experiment."]}
with args.out.open("x") as output:
    json.dump(report, output, indent=2)
    output.write("\n")
print(json.dumps({k: report[k] for k in ("failed_invocations", "by_first_argument")}, indent=2))
