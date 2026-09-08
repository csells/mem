"""Read actual evidence compactly for a human/agent auditor; no grading or writes."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

C = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(C.parents[2]))
from membench.runner.memory_prime_delivery_package import briefing
from scripts.memory_e2e_experiment import body_delivered


def strings(value):
    if isinstance(value, str):
        yield value
        if value.startswith(("{", "[")):
            try:
                yield from strings(json.loads(value))
            except (ValueError, RecursionError):
                pass
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


parser = argparse.ArgumentParser()
parser.add_argument("lifecycle")
parser.add_argument("stage", type=int)
args = parser.parse_args()
d = C / "cases" / args.lifecycle / f"stage-{args.stage}"
r = json.loads((d / "result.json").read_text())
before = json.loads((d / "memory-before.json").read_text())
after = json.loads((d / "memory-after.json").read_text())
launch = (d / "launch-prompt.txt").read_text()
print("RESULT", {k: r.get(k) for k in ("slot", "artifact_correct", "artifact_total", "artifact_passed", "support_artifact_passed", "host_success", "errors", "task_id", "record_unchanged", "package_changed_paths")})
print("BEFORE", json.dumps(before, ensure_ascii=False))
print("AFTER CHANGES", json.dumps({k: v for k, v in after.items() if before.get(k) != v}, ensure_ascii=False))
print("REMOVED", sorted(before.keys() - after.keys()))
for i, call in enumerate(json.loads((d / "tool-calls.json").read_text())):
    output = str(call.get("result") or "")
    content = json.dumps(call.get("arguments"), ensure_ascii=False)
    print("CALL", i, call["name"], call.get("tool_use_index"), call.get("tool_result_index"), content[:500], "ERROR", call.get("is_error"), "PRIME_FULL", body_delivered(output, briefing()), "BEFORE_FULL", [k for k, v in before.items() if body_delivered(output, v)], "AFTER_FULL", [k for k, v in after.items() if body_delivered(output, v)], "RESULT", output[:450])
    matches = re.findall(r"(?:Ran \d+ tests?.*|PASS [^\n]+|FAIL [^\n]+)", output)
    if matches:
        print("VALIDATION", matches[:40])
print("AGENT TEXT")
for line in (d / "stream.jsonl").read_text().splitlines():
    event = json.loads(line)
    if event.get("type") == "assistant":
        for item in event.get("message", {}).get("content", []):
            if item.get("type") == "text":
                print(item["text"])
    item = event.get("item", {})
    if event.get("type") == "item.completed" and item.get("type") == "agent_message":
        print(item.get("text"))
    if event.get("type") == "turn.completed":
        print(event.get("payload", {}).get("response"))
for path in d.rglob("rollout-*.jsonl"):
    print("RAW", path.relative_to(d), hashlib.sha256(path.read_bytes()).hexdigest())
    for n, line in enumerate(path.read_text().splitlines(), 1):
        event = json.loads(line)
        kind = event.get("payload", {}).get("type")
        candidates = list(strings(event))
        if launch in candidates:
            print("RAW_LAUNCH", n, kind)
        if kind in ("custom_tool_call_output", "function_call_output"):
            full_before = [k for k, v in before.items() if any(body_delivered(s, v) for s in candidates)]
            full_after = [k for k, v in after.items() if any(body_delivered(s, v) for s in candidates)]
            prime = any(body_delivered(s, briefing()) for s in candidates)
            if full_before or full_after or prime:
                print("RAW_FULL_OUTPUT", n, "PRIME", prime, "BEFORE", full_before, "AFTER", full_after)
            tests = sorted({hit for s in candidates for hit in re.findall(r"Ran \d+ tests?[^\n]*", s)})
            if tests:
                print("RAW_TESTS", n, tests)
