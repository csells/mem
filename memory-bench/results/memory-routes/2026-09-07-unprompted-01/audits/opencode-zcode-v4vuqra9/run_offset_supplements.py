"""Append uniform post-hoc offset-order checks for completed reconciliation snapshots.
No models, no original evidence or source writes. Each saved candidate runs from
its own scratch copy under the frozen pinned interpreter in a readonly sandbox.
"""
from pathlib import Path
import datetime, hashlib, importlib.util, json, shutil, subprocess, tempfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
DEST = OUT / "offset-supplements"
DEST.mkdir(exist_ok=True)
PYTHON = Path("/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/bin/python3.14")
PYTHON_HASH = "87d4df53fd91304be5bac391fb204643c36b7df2023c04a0953bcbc7d4fdf634"
RUNTIME = ROOT / "frozen-source/memory-bench/membench/runner/memory_routes_runtime.py"
REFERENCE = ROOT / "frozen-source/memory-bench/fixtures/memory-unprompted-corpus/reconciliation/reference"
SPEC = importlib.util.spec_from_file_location("offset_audit_runtime", RUNTIME)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
REQUEST = {
    "op": "refunds_csv", "month": "2025-02", "transactions": [
        {"id": "a", "kind": "refund", "posted_at": "2025-02-15T01:00:00Z", "amount_cents": 1},
        {"id": "b", "kind": "refund", "posted_at": "2025-02-15T02:00:00+02:00", "amount_cents": 2},
    ],
}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def tree(path):
    return {str(p.relative_to(path)): digest(p) for p in path.rglob("*") if p.is_file() and not p.is_symlink()}

def exclusive(path, value):
    with path.open("x") as file:
        json.dump(value, file, indent=2)
        file.write("\n")

assert digest(PYTHON) == PYTHON_HASH
selected = []
for path in sorted((ROOT / "cases").glob("*/stage-*/result.json")):
    result = json.loads(path.read_text())
    if result["family"] == "reconciliation" and result["stage"] >= 2 and not (DEST / (result["slot"] + ".json")).exists():
        selected.append((path, result))
if not selected:
    print("No untested completed reconciliation snapshots", flush=True)
    raise SystemExit(0)

scratch = Path(tempfile.mkdtemp(prefix="opencode-zcode-uniform-offset-", dir="/tmp")).resolve()
shutil.copytree(REFERENCE, scratch / "reference")
reference_profile = MODULE.make_profile(scratch / "reference-readonly.sb", [], [scratch / "reference", PYTHON.parent.parent])
reference_hashes = tree(REFERENCE)
summary = []
for result_path, result in selected:
    slot = result["slot"]
    source = result_path.parent / "workspace-after"
    source_hashes = tree(source)
    candidate = scratch / slot
    shutil.copytree(source, candidate)
    profile = MODULE.make_profile(scratch / (slot + ".sb"), [], [candidate, PYTHON.parent.parent])
    observations = {}
    for name, entry, sandbox in [
        ("reference", scratch / "reference" / ("stage_" + str(result["stage"])) / "cli.py", reference_profile),
        ("candidate", candidate / "cli.py", profile),
    ]:
        argv = ["/usr/bin/sandbox-exec", "-f", str(sandbox), str(PYTHON), str(entry)]
        try:
            proc = subprocess.run(argv, cwd=entry.parent, input=json.dumps(REQUEST), capture_output=True, text=True, timeout=3, env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})
            try:
                value = json.loads(proc.stdout)
            except json.JSONDecodeError:
                value = None
            observations[name] = {"argv": argv, "exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "json": value}
        except subprocess.TimeoutExpired as error:
            observations[name] = {"argv": argv, "timeout": True, "error": str(error)}
    unchanged = source_hashes == tree(source) and reference_hashes == tree(REFERENCE) and source_hashes == tree(candidate)
    assert unchanged
    ref, actual = observations["reference"], observations["candidate"]
    if ref.get("exit") != 0 or ref.get("json") is None:
        raise RuntimeError("Supplemental reference execution failed: " + slot)
    passed = actual.get("exit") == 0 and actual.get("json") == ref["json"]
    item = {
        "schema": "uniform-posthoc-offset-check.v1", "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "slot": slot, "host": result["host"], "arm": result["arm"], "stage": result["stage"], "family": result["family"],
        "posthoc": True, "request": REQUEST, "frozen_grade_unchanged": {"correct": result["artifact_correct"], "total": result["artifact_total"]},
        "supplemental_passed": passed, "observations": observations,
        "candidate_source": str(source), "source_hashes": source_hashes, "original_result_sha256": digest(result_path),
        "reference_source": str(REFERENCE), "reference_hashes": reference_hashes,
        "python": str(PYTHON), "python_sha256": PYTHON_HASH,
        "runtime_helper_sha256": digest(RUNTIME), "sandbox_profile": profile.read_text(), "reference_sandbox_profile": reference_profile.read_text(),
        "original_and_copy_unchanged": unchanged, "scratch": str(scratch), "model_calls": 0,
        "scope": "Supplemental valid offset-order contract check only. Never replaces or augments frozen cohort score. Same midmonth input applies under current UTC and 05:00 UTC month boundaries; reference selected separately for current stage.",
    }
    exclusive(DEST / (slot + ".json"), item)
    summary.append({"slot": slot, "supplemental_passed": passed, "frozen_grade": item["frozen_grade_unchanged"]})
    print(json.dumps(summary[-1]), flush=True)
exclusive(DEST / ("batch-" + scratch.name + ".json"), {"scratch": str(scratch), "tested": summary, "posthoc": True, "model_calls": 0})
