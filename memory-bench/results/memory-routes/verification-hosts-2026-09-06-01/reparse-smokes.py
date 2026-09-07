"""Regrade saved successful common smokes without subprocesses or model calls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from membench.runner.memory_host_receipts import score_correlated
from membench.runner.memory_routes_grade import grade_artifact
from scripts import memory_hosts_experiment as driver
from scripts import memory_routes_experiment as base

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    results = []
    inventory = {}
    for host, name in (
        ("claude", "2026-09-06-host-common-smoke-02"),
        ("codex", "2026-09-06-host-common-smoke-codex-02"),
    ):
        root = ROOT / "results/memory-routes" / name
        session = root / "session"
        paths = [
            session / name
            for name in (
                "stream.jsonl", "result.json", "started.json", "raw-receipts.json",
                "tool-calls.json", "workspace/config.json",
            )
        ]
        paths.extend(path for path in (session / "host-evidence").rglob("*") if path.is_file())
        for path in paths:
            inventory[str(path.relative_to(ROOT))] = sha(path)
        original = json.loads((session / "result.json").read_text())
        started = json.loads((session / "started.json").read_text())
        observed = driver.observe_host(
            host, (session / "stream.jsonl").read_text(), session / "host-evidence"
        )
        scored, mapping = score_correlated(
            json.loads((session / "raw-receipts.json").read_text()),
            observed.calls,
            observed.session_id or "",
            leg_id=original["leg"],
            status="ok" if observed.completed else "error",
            expected_binary=str(base.BD),
            expected_store=started["store"],
        )
        artifact = grade_artifact(session / "workspace/config.json", {"smoke": True})
        routes = base.route_summary(
            scored.model_dump(mode="json"), observed.calls,
            Path(started["scratch"]) / "work/config.json", {"smoke": True},
        )
        admitted = bool(
            observed.completed and observed.success and original["exit_code"] == 0
            and original["timed_out"] is False
            and observed.models == [original["model_requested"]]
            and not scored.evidence_unknown and scored.accepted_writes == 1
            and scored.observed_reads == 2 and routes["bd_correct_payload_via_direct"]
            and routes["bd_search"] and artifact["passed"]
        )
        results.append({
            "host": host, "source_run": name, "final_parser_admits_smoke": admitted,
            "completed": observed.completed, "success": observed.success,
            "errors": observed.errors, "models": observed.models,
            "session_id": observed.session_id,
            "actual_identity_unchanged": (
                observed.session_id == original["session_id"]
                and observed.models == original["models_observed"]
            ),
            "tool_calls_unchanged": (
                [call.model_dump(mode="json") for call in observed.calls]
                == json.loads((session / "tool-calls.json").read_text())
            ),
            "memory_evidence": scored.model_dump(mode="json"),
            "associations": mapping["associations"], "artifact": artifact,
            "routes": routes, "cost_usd": observed.cost_usd, "usage": observed.usage,
        })
    source_pins = {
        str(path.relative_to(ROOT)): sha(path)
        for directory in (ROOT / "membench", ROOT / "scripts")
        for path in sorted(directory.rglob("*.py"))
    }
    unchanged = all(sha(ROOT / name) == digest for name, digest in inventory.items())
    proof = {
        "no_model_calls": True, "source_sha256": source_pins,
        "input_sha256": inventory, "input_unchanged": unchanged, "results": results,
    }
    with (OUT / "offline-smokes-final-parser.json").open("x") as target:
        json.dump(proof, target, indent=2)
        target.write("\n")
    print(json.dumps({
        "input_unchanged": unchanged,
        "smokes": [
            {name: row[name] for name in (
                "host", "final_parser_admits_smoke", "actual_identity_unchanged", "tool_calls_unchanged"
            )}
            for row in results
        ],
    }))
    if not unchanged or not all(row["final_parser_admits_smoke"] for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
