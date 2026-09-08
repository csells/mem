"""Read-only exact prime stdout audit; no subprocesses, model, bd, or store calls."""
import base64
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from membench.runner.memory_prime_delivery_package import briefing, thin_prime
from membench.runner.memory_e2e_audit import _parse

AUDIT = Path(__file__).resolve().parent
COHORT = AUDIT.parents[1]
REPO = COHORT.parents[3]
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    return json.loads(path.read_text())

def main():
    manifest_path = COHORT / "manifest.json"
    manifest = read(manifest_path)
    hashes = {str(manifest_path): sha(manifest_path), str(Path(__file__)): sha(Path(__file__))}
    for name in (
        "memory-bench/membench/runner/memory_prime_delivery_package.py",
        "memory-bench/membench/runner/memory_policy_handoff_package.py",
        "memory-bench/membench/runner/memory_e2e_receipts.py",
        "memory-bench/membench/runner/memory_e2e_audit.py",
        "memory-bench/fixtures/memory-e2e-package/issue-rules.md",
        "memory-bench/fixtures/memory-policy-handoff-package/memory.md",
    ):
        path = REPO / name
        assert sha(path) == manifest["source_sha256"][name], name
        hashes[str(path)] = sha(path)
    assert hashlib.sha256(briefing().encode()).hexdigest() == manifest["briefing_sha256"]
    rows = []
    assessed = 0
    raw_prime_count = 0
    for slot in manifest["slots"]:
        folder = COHORT / "cases" / slot["lifecycle"] / f"stage-{slot['stage']}"
        result_path = folder / "result.json"
        if not result_path.is_file():
            continue
        assessed += 1
        raw_path = folder / "raw-receipts.json"
        result, raw = read(result_path), read(raw_path)
        hashes.update({str(p): sha(p) for p in (result_path, raw_path)})
        assert not result["receipt_assessment"]["unknown_execution"]
        raw_finishes = {e["invocation_id"]: (i, e) for i, e in enumerate(raw) if e.get("event") == "finish"}
        raw_prime_ids = {
            e["invocation_id"] for e in raw if e.get("event") == "finish"
            and (parsed := _parse(e.get("operation_argv", []))) is not None and parsed[0] == "prime"
        }
        raw_prime_count += len(raw_prime_ids)
        assessed_ids = set()
        expected = (briefing() if slot["arm"] == "rich-prime" else thin_prime()).encode()
        for i, entry in enumerate(result["receipt_assessment"]["executions"]):
            if entry["command"] != "prime":
                continue
            assessed_ids.add(entry["invocation_id"])
            raw_index, finish = raw_finishes[entry["invocation_id"]]
            for key in ("operation_argv", "stdout", "stderr", "returncode", "stdout_base64"):
                assert entry[key] == finish[key], (slot["slot"], key)
            output = base64.b64decode(finish["stdout_base64"], validate=True)
            assert output.decode("utf-8") == finish["stdout"]
            assert output == expected, slot["slot"]
            assert finish["operation_argv"] == ["prime", "--no-memories"]
            assert finish["returncode"] == 0 and finish["stderr"] == ""
            rows.append({"slot": slot["slot"], "arm": slot["arm"], "receipt_index": i,
                "raw_finish_index": raw_index, "invocation_id": finish["invocation_id"],
                "operation_argv": finish["operation_argv"], "stdout_bytes": len(output),
                "stdout_sha256": hashlib.sha256(output).hexdigest(),
                "entire_stdout_exact_expected_bytes": True,
                "raw_base64_equals_assessed_utf8": True})
        assert assessed_ids == raw_prime_ids, slot["slot"]
    assert assessed == 196 and raw_prime_count == len(rows) == 118
    ns = time.time_ns()
    payload = {"schema": "prime-entire-output-no-extra-memory-body-audit.v1", "created_ns": ns,
        "assessed_sessions": assessed, "actual_prime_executions": len(rows),
        "all_prime_outputs_exact_arm_bytes": True, "all_actual_prime_calls_used_no_memories": True,
        "plain_prime_execution_count": 0, "extra_prefix_or_suffix_bytes_count": 0,
        "arm_execution_counts": dict(Counter(r["arm"] for r in rows)), "rows": rows,
        "source_sha256": hashes, "model_calls": 0, "store_calls": 0,
        "limits": "Execution stdout comparison proves no body was appended by these 118 actual prime calls. Model-visible output may be truncated or combined with separately executed memory commands; those are not automatic prime injection. This does not claim default plain prime behavior suppresses memories."}
    output = AUDIT / f"final-prime-exact-output-{ns}.json"
    with output.open("x") as handle:
        json.dump(payload, handle, indent=2); handle.write("\n")
    print(output)
    print(json.dumps({k: payload[k] for k in ("assessed_sessions", "actual_prime_executions", "arm_execution_counts", "plain_prime_execution_count", "extra_prefix_or_suffix_bytes_count")}))

if __name__ == "__main__":
    main()
