"""Read-only scheduled component observations; no semantic memory quality inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from membench.runner.bd_component_experiment import _audit, validate_manifest
from membench.runner.e1_grid import out_lock

COUNTS = (
    "syntactic_read_attempts",
    "syntactic_write_attempts",
    "executed_reads",
    "executed_writes",
    "accepted_writes",
    "observed_reads",
    "observed_content_reads",
    "empty_reads",
    "exposure_commands",
)


def _memory(agent: Mapping[str, Any]) -> dict[str, Any]:
    raw = agent.get("memory")
    raw = raw if isinstance(raw, dict) else {}
    counts = {key: raw.get(key) for key in COUNTS}
    for key, value in counts.items():
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"Invalid memory count: {key}")
    unknown = raw.get("evidence_unknown")
    if unknown is not None and type(unknown) is not bool:
        raise ValueError("Invalid evidence_unknown flag")
    return {
        **counts,
        "evidence_unknown": unknown is not False or any(value is None for value in counts.values()),
        "unknown_reasons": raw.get("unknown_reasons", []),
    }


def _row(run: Path, row: Mapping[str, Any], state: str) -> dict[str, Any]:
    terminal = run / "sessions" / row["row_id"] / "terminal.json"
    result = json.loads(terminal.read_text())["result"] if state != "missing" else {}
    agent = result.get("agent") or {}
    cost = agent.get("total_cost_usd")
    if cost is not None and (
        isinstance(cost, bool)
        or not isinstance(cost, (int, float))
        or not math.isfinite(cost)
        or cost < 0
    ):
        raise ValueError("Invalid session cost")
    check = result.get("task_check") or {}
    return {
        **{key: row[key] for key in ("row_id", "component", "intervention", "condition")},
        "session_status": state,
        "session_id": agent.get("session_id"),
        "agent_status": agent.get("status"),
        "integrity_errors": agent.get("integrity_errors"),
        "memory": _memory(agent),
        "task_check_status": check.get("status", "unknown"),
        "total_cost_usd": cost,
    }


def analyze(run: Path) -> dict[str, Any]:
    """Require authentic terminal journals; partial starts and changed raw evidence fail closed."""
    with out_lock(run):
        manifest_path = run / "manifest.json"
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
        validate_manifest(manifest)
        states = _audit(run, manifest)
        rows = [
            _row(run, row, states.get(row["row_id"], "missing")) for row in manifest["schedule"]
        ]
        totals = {
            key: {
                "observed_total": sum(
                    row["memory"][key] for row in rows if row["memory"][key] is not None
                ),
                "known_rows": sum(row["memory"][key] is not None for row in rows),
            }
            for key in COUNTS
        }
        costs = [row["total_cost_usd"] for row in rows if row["total_cost_usd"] is not None]
        return {
            "schema": "bd-component-analysis.v1",
            "planned_sessions": len(rows),
            "manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "session_status_counts": dict(Counter(row["session_status"] for row in rows)),
            "evidence_unknown_sessions": sum(row["memory"]["evidence_unknown"] for row in rows),
            "memory_totals": totals,
            "observed_cost_usd": sum(costs),
            "cost_known_sessions": len(costs),
            "cost_unknown_sessions": len(rows) - len(costs),
            "rows": rows,
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out_json.resolve().is_relative_to(args.run.resolve()):
        raise ValueError("Analysis output must stay outside immutable run evidence")
    result = analyze(args.run)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
