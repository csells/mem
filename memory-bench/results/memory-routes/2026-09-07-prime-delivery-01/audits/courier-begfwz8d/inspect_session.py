"""Read-only evidence index for manual semantic review; never runs an agent."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parents[2]))
from membench.runner.memory_prime_delivery_package import briefing
from scripts.memory_e2e_experiment import body_delivered


def read(path):
    return json.loads(path.read_text())


def clip(value, size=900):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= size else text[:size] + f" [CLIPPED {len(text)} chars]"


parser = argparse.ArgumentParser()
parser.add_argument("lifecycle", nargs="?")
parser.add_argument("stage", nargs="?", type=int)
parser.add_argument("--call", type=int)
args = parser.parse_args()
manifest = read(ROOT / "manifest.json")
if args.lifecycle is None:
    for row in manifest["slots"]:
        path = ROOT / "cases" / row["lifecycle"] / f"stage-{row['stage']}" / "result.json"
        if row["family"] == "webhooks" and path.exists():
            r = read(path)
            print(r["slot"], r["artifact_correct"], r["artifact_total"],
                  "memories", r["memory_before_count"], r["memory_after_count"])
    raise SystemExit()
folder = ROOT / "cases" / args.lifecycle / f"stage-{args.stage}"
result = read(folder / "result.json")
calls = read(folder / "tool-calls.json")
if args.call is not None:
    print(json.dumps(calls[args.call], indent=2, ensure_ascii=False))
    raise SystemExit()
print("IDENTITY", json.dumps({k: result[k] for k in (
    "slot", "host", "profile_id", "arm", "corpus_family", "catalog_mode",
    "artifact_passed", "artifact_correct", "artifact_total", "host_success", "errors",
    "task_id", "memory_before_count", "memory_after_count", "record_unchanged",
    "package_changed_paths")}, ensure_ascii=False))
print("TASK", json.dumps(read(folder / "task.json"), ensure_ascii=False))
for name in ("memory-before.json", "memory-after.json"):
    print(name, json.dumps(read(folder / name), indent=2, ensure_ascii=False))
print("RECEIPTS")
for idx, event in enumerate(result["receipt_assessment"]["executions"]):
    print(json.dumps({"receipt": idx, "command": event.get("command"),
        "argv": clip(event["operation_argv"], 750), "returncode": event["returncode"],
        "wall_ns": event.get("wall_ns"),
        "stdout_visible": event.get("stdout_visible_somewhere_in_session"),
        "exact_rich_prime_stdout": event.get("command") == "prime" and event["stdout"] == briefing(),
    }, ensure_ascii=False))
print("CALLS; zero-based index is --call selector")
for idx, call in enumerate(calls):
    output = call.get("result") or ""
    print(json.dumps({"call": idx, "name": call["name"],
        "use": call.get("tool_use_index"), "response": call.get("tool_result_index"),
        "arguments": clip(call.get("arguments")), "error": call.get("is_error"),
        "rich_briefing_complete": isinstance(output, str) and body_delivered(output, briefing()),
        "result": clip(output, 1200)}, ensure_ascii=False))
print("FILES", [(str(p.relative_to(folder / "workspace-after")), p.stat().st_size)
                for p in (folder / "workspace-after").rglob("*") if p.is_file()])
print("HASHES", json.dumps({name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
    for name in ("result.json", "tool-calls.json", "memory-before.json", "memory-after.json",
                 "artifact-grade.json", "task.json", "stream.jsonl")}))
