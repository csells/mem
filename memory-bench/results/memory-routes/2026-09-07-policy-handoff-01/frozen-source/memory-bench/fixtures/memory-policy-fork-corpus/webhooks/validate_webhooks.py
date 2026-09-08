"""Execute reference and counterfactual mutations; preserve each validation run."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(source, request, directory):
    program = directory / "main.py"
    # Validation source is owned throwaway scaffolding, never a model artifact.
    program.write_text(source)
    result = subprocess.run(
        [sys.executable, str(program)], input=json.dumps(request),
        capture_output=True, text=True, timeout=3, check=True, cwd=directory,
    )
    return json.loads(result.stdout)


def main():
    scratch = Path(tempfile.mkdtemp(prefix="courier-oracle-"))
    report = {"scratch": str(scratch), "worlds": {}, "created_ns": time.time_ns()}
    for world in ("global-first", "account-first"):
        folder = ROOT / world
        source = (folder / "reference/main.py").read_text()
        passed = total = public_passed = public_total = 0
        by_stage = {}
        for stage in range(1, 7):
            active = source.replace('CURRENT = "2"', 'CURRENT = "1"') if stage < 3 else source
            cases = json.loads((folder / f"graders/stage-{stage}.json").read_text())
            stage_results = []
            for case in cases:
                if "artifact_json_path" in case:
                    actual = json.loads((folder / "reference" / case["artifact_json_path"]).read_text())
                else:
                    actual = run(active, case["stdin"], scratch)
                ok = actual == case["expected"]
                stage_results.append(ok)
                passed += ok
                total += 1
            by_stage[str(stage)] = {"passed": sum(stage_results), "total": len(stage_results)}
            tasks = json.loads((folder / "tasks.json").read_text())["tasks"]
            for task in tasks[:stage]:
                for case in json.loads((folder / task["public_tests"]).read_text()):
                    if "artifact_json_path" in case:
                        actual = json.loads((folder / "reference" / case["artifact_json_path"]).read_text())
                    else:
                        actual = run(active, case["request"], scratch)
                    public_total += 1
                    public_passed += actual == case["expected"]
        final = json.loads((folder / "graders/stage-6.json").read_text())
        mutants = {
            "wrong_scope": source.replace("global_ids = GLOBAL_FIRST if version == \"1\" else not GLOBAL_FIRST", "global_ids = not GLOBAL_FIRST if version == \"1\" else GLOBAL_FIRST"),
            "wrong_winner": source.replace('stamp if version == "1" else -stamp', '-stamp if version == "1" else stamp'),
            "lexical_timestamp": source.replace('stamp = datetime.fromisoformat(r["occurred_at"].replace("Z", "+00:00")).timestamp()', 'stamp = int(r["occurred_at"][:19].replace("-", "").replace("T", "").replace(":", ""))'),
            "reverse_tie": source.replace('r["record_id"])', 'tuple(-ord(c) for c in r["record_id"]))'),
            "wrong_default": source.replace('CURRENT = "2"', 'CURRENT = "1"'),
            "sorted_output": source.replace('for r in receipts if r["record_id"] in selected_ids', 'for r in sorted(receipts, key=lambda x: x["record_id"]) if r["record_id"] in selected_ids'),
        }
        mutation_results = {}
        for name, mutant in mutants.items():
            failures = []
            for case in final:
                if "stdin" not in case:
                    continue
                try:
                    ok = run(mutant, case["stdin"], scratch) == case["expected"]
                except (ValueError, subprocess.SubprocessError):
                    ok = False
                if not ok:
                    failures.append(case["name"])
            mutation_results[name] = {"rejected": bool(failures), "witnesses": failures}
        report["worlds"][world] = {
            "passed": passed, "total": total, "by_stage": by_stage,
            "public_passed": public_passed, "public_total": public_total,
            "mutations": mutation_results,
        }
        print(world, passed, total, public_passed, public_total, flush=True)
    report["passed"] = all(
        row["passed"] == row["total"] and row["public_passed"] == row["public_total"]
        and all(m["rejected"] for m in row["mutations"].values())
        for row in report["worlds"].values()
    )
    target = ROOT / f"validation-{time.time_ns()}.json"
    with target.open("x") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(target, report["passed"], flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
