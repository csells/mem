"""Read-only qualification audit; append a new report without rerunning agents.

Keep the original strict smoke result, corrected payload assessment, and evidence
of working transport/tools separate. A model ignoring a diagnostic is not an
adapter failing to deliver that diagnostic. Neither is an adoption result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from membench.runner import memory_unprompted_hosts as hosts
from membench.runner.memory_e2e_audit import classify_operation
from membench.runner.memory_unprompted_grade import grade_record
from scripts.memory_unprompted_smoke import POLICY, grade_files, write_json


def audit(root: Path) -> dict[str, Any]:
    input_hashes = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }
    summaries: dict[str, Any] = {}
    for host in hosts.MODELS:
        path = root / host
        state = json.loads((path / "state.json").read_text())
        stages = []
        for leg in ("capture", "reuse"):
            folder = path / leg
            original = json.loads((folder / "result.json").read_text())
            before = json.loads((folder / "memory-before.json").read_text())
            after = json.loads((folder / "memory-after.json").read_text())
            task = json.loads((folder / "task.json").read_text())
            payload = grade_record(after.get("qualification-identifiers", ""), POLICY)
            observed = hosts.observe(
                host, (folder / "stream.jsonl").read_text(), folder / "host-evidence"
            )
            files = grade_files(folder / "workspace-after", task["id"], state["marks"], leg)
            calls = observed.calls
            outputs = [
                str(c.result or "")
                for c in calls
                if c.tool_result_index is not None and not c.is_error
            ]
            marker_path = folder / "workspace-after" / f"markers-{task['id']}.json"
            marker_data = json.loads(marker_path.read_text()) if marker_path.exists() else {}
            delivery = {
                k: {
                    "copied_correctly": marker_data.get(k) == value,
                    "present_in_tool_result": any(value in text for text in outputs),
                }
                for k, value in state["marks"].items()
            }
            actions = []
            for e in original["memory_operations"]["executions"]:
                classified = classify_operation(
                    e["operation_argv"], e["returncode"], e["stdout"], e["stderr"], before, after
                )
                actions.append({"invocation_id": e["invocation_id"], **classified})
            counts = dict(Counter(e["action"] for e in actions))
            original_checks = original["memory_operations"]
            app_passed = files[f"{leg}.json"] and all(original["behavior"])
            transport_passed = bool(
                original["exit_code"] == 0
                and not original["timed_out"]
                and observed.success
                and observed.models == [hosts.MODELS[host]]
                and not original["credential_redaction_required"]
                and not original_checks["unknown_execution"]
                and original["evidence_export_error"] is None
            )
            strict_corrected = bool(
                transport_passed
                and files["passed"]
                and app_passed
                and payload["passed"] is True
                and original["task_closed"]
                and counts.get("query", 0)
                and counts.get("recall", 0)
                and counts.get("prime", 0)
                and (
                    counts.get("write", 0)
                    if leg == "capture"
                    else before == after and original["missing_key_error_observed"]
                )
            )
            stages.append(
                {
                    "leg": leg,
                    "session_id": observed.session_id,
                    "models_observed": observed.models,
                    "transport_passed": transport_passed,
                    "application_passed": app_passed,
                    "files": files,
                    "delivery": delivery,
                    "payload": payload,
                    "original_strict_smoke_passed": original["passed"],
                    "corrected_strict_smoke_passed": strict_corrected,
                    "record_unchanged": before == after,
                    "missing_key_error_observed": original["missing_key_error_observed"],
                    "actions": counts,
                    "action_audit": actions,
                    "cost_usd": original["cost_usd"],
                    "duration_s": original["duration_s"],
                    "native_skill_calls": original["native_skill_calls"],
                    "skill_file_read_calls": original["skill_file_read_calls"],
                    "memory_reference_reads": original["memory_workflow_read_calls"],
                }
            )
        fresh = len({s["session_id"] for s in stages}) == 2
        delivered = {
            k: any(
                s["delivery"][k]["copied_correctly"] or s["delivery"][k]["present_in_tool_result"]
                for s in stages
            )
            for k in state["marks"]
        }
        totals: Counter[str] = Counter()
        for s in stages:
            totals.update(s["actions"])
        context_ok = None
        if host == "opencode":
            context = json.loads((path / "ollama-context.json").read_text())
            context_ok = bool(
                context["models"]
                and all(m.get("context_length", 0) >= 32768 for m in context["models"])
            )
        wiring = bool(
            fresh
            and context_ok is not False
            and all(delivered.values())
            and all(
                s["transport_passed"] and s["application_passed"] and s["payload"]["passed"] is True
                for s in stages
            )
            and totals["write"]
            and totals["query"]
            and totals["recall"]
            and totals["prime"]
            and stages[1]["actions"].get("recall", 0)
            and stages[1]["record_unchanged"]
            and stages[1]["missing_key_error_observed"]
        )
        summaries[host] = {
            "stages": stages,
            "fresh_sessions": fresh,
            "instruction_delivery_observed": delivered,
            "runtime_context_qualified": context_ok,
            "transport_tools_and_handoff_observed": wiring,
            "all_strict_smoke_checks_passed": all(
                s["corrected_strict_smoke_passed"] for s in stages
            ),
            "actions": dict(totals),
        }
    unchanged = all(
        hashlib.sha256((root / p).read_bytes()).hexdigest() == digest
        for p, digest in input_hashes.items()
    )
    return {
        "schema": "four-cli-qualification-audit.v1",
        "model_calls": 0,
        "scope": "explicit integration; not memory-adoption results",
        "correction": (
            "Original checker required a whole note to be JSON; "
            "exact payloads in readable prose/fences are valid."
        ),
        "measurement_boundary": (
            "Wiring evidence is separate from strict diagnostic adherence; "
            "marker mistakes and omitted calls remain failures of their respective checks."
        ),
        "hosts": summaries,
        "input_sha256": input_hashes,
        "inputs_unchanged": unchanged,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError("Audit reports are append-only")
    result = audit(args.root)
    write_json(args.out, result)
    print(
        json.dumps(
            {h: {k: v for k, v in s.items() if k != "stages"} for h, s in result["hosts"].items()},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
