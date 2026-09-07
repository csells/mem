"""Print unaudited, completed selected-host evidence for offline review."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
found = 0
for p in sorted((ROOT / "cases").glob("*/stage-*/result.json")):
    if not p.parent.parent.name.startswith(("claude-", "codex-")):
        continue
    d = json.loads(p.read_text())
    if (OUT / f"{d['slot']}.audit.json").exists():
        continue
    found += 1
    s = p.parent
    print("SESSION", d["slot"], "GRADE", d["artifact_correct"], d["artifact_total"], "ACTIONS", d["action_counts"])
    print("DELIVERY", {k: d.get(k) for k in ("native_skill_calls", "skill_file_read_calls", "memory_workflow_read_calls", "host_success", "infrastructure_fault")})
    print("MEMORY BEFORE", (s / "memory-before.json").read_text(), "AFTER", (s / "memory-after.json").read_text())
    for i, c in enumerate(json.loads((s / "tool-calls.json").read_text())):
        args = json.dumps(c.get("arguments", {}))
        print("CALL", i, c.get("tool_name", c.get("name")), args[:1100])
        if any(term in args for term in ("bd remember", "bd memories", "bd recall", "references/memory.md")):
            print("RESULT", str(c.get("result", ""))[:10000])
    print("TASKS", [(t["id"], t.get("close_reason"), t.get("notes"), t.get("comment_count")) for t in json.loads((s / "tasks-after.json").read_text())])
print("UNREVIEWED_COMPLETED", found)
