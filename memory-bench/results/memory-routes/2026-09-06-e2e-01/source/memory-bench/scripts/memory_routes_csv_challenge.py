"""Behavioral CSV challenges branching an actual, completed memory capture.

Run with ``python -m scripts.memory_routes_csv_challenge --out PATH`` to freeze a
plan. Add --fire only after reviewing it. The existing driver owns subscriptions,
sandboxing, task workflow and receipts. This script never repairs captured memory.
"""

from __future__ import annotations

import argparse
import codecs
import copy
import csv
import hashlib
import io
import json
import math
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from membench.runner.headless_agent import tool_calls_from_stream
from membench.runner.memory_routes_corpus import Task, build_tasks
from membench.runner.memory_routes_grade import grade_capture
from membench.runner.memory_routes_runtime import experiment_env
from scripts import memory_routes_experiment as driver

SEED = 20260906
LEGS = ("search", "supplied", "current", "historical")
DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "results/memory-routes/2026-09-06-main-02"
ROWS = (
    {"client": 'Café "North", LLC;\tWest', "amount": "12.34565"},
    {"client": "South & Sons", "amount": "-0.01005"},
    {"client": "East", "amount": "0"},
)


def expected_rows(config: dict[str, Any]) -> list[list[str]]:
    settings = config["csv_export"]
    places = settings["decimal_places"]
    quantum = Decimal(1).scaleb(-places)
    rows = [["client", "amount"]]
    for row in ROWS:
        amount = Decimal(row["amount"]).quantize(quantum, rounding=ROUND_HALF_UP)
        rendered = format(amount, f".{places}f").replace(".", settings["decimal_separator"])
        rows.append([row["client"], rendered])
    return rows


def canonical_csv(config: dict[str, Any]) -> bytes:
    """Provide inspectable expected bytes; grading permits equivalent CSV quoting."""
    settings = config["csv_export"]
    out = io.StringIO(newline="")
    csv.writer(
        out,
        delimiter=settings["delimiter"],
        lineterminator="\r\n" if settings["line_ending"] == "CRLF" else "\n",
    ).writerows(expected_rows(config))
    if settings["encoding"] == "utf-16":
        return codecs.BOM_UTF16_LE + out.getvalue().encode("utf-16-le")
    return out.getvalue().encode(settings["encoding"])


def grade_csv(path: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Validate the actual regular file, independently of config.json and tool prose."""
    if path.is_symlink():
        return {"passed": False, "reason": "artifact_symlink"}
    if not path.is_file():
        return {"passed": False, "reason": "artifact_missing_or_not_file"}
    try:
        raw = path.read_bytes()
    except OSError:
        return {"passed": False, "reason": "artifact_unreadable"}
    settings = config["csv_export"]
    encoding = settings["encoding"]
    has_bom = raw.startswith((codecs.BOM_UTF8, codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE))
    if (
        (encoding == "utf-8" and has_bom)
        or (encoding == "utf-8-sig" and not raw.startswith(codecs.BOM_UTF8))
        or (encoding == "utf-16" and not raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)))
    ):
        return {"passed": False, "reason": "bom_mismatch"}
    try:
        text = raw.decode(encoding)
    except UnicodeError:
        return {"passed": False, "reason": "encoding_mismatch"}
    ending = "\r\n" if settings["line_ending"] == "CRLF" else "\n"
    remainder = text.replace(ending, "")
    if not text.endswith(ending) or "\r" in remainder or "\n" in remainder:
        return {"passed": False, "reason": "line_ending_mismatch"}
    try:
        actual = list(
            csv.reader(io.StringIO(text, newline=""), delimiter=settings["delimiter"], strict=True)
        )
    except csv.Error:
        return {"passed": False, "reason": "malformed_csv"}
    if actual != expected_rows(config):
        return {"passed": False, "reason": "header_rows_or_format_mismatch"}
    return {
        "passed": True,
        "reason": "csv_contract_satisfied",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "canonical_bytes_match": raw == canonical_csv(config),
    }


def challenge_legs(task: Task) -> dict[str, dict[str, Any]]:
    original = task.expected_config
    current = copy.deepcopy(original)
    delimiter = ";" if original["csv_export"]["delimiter"] != ";" else "|"
    current["csv_export"]["delimiter"] = delimiter
    change = f"The current delimiter is now {json.dumps(delimiter)}."
    common = (
        "Create both config.json and invoices.csv for the Acme finance invoice export before "
        "finishing. config.json must contain the complete effective project configuration, "
        "using the original field names and JSON types. invoices.csv must be an actual CSV "
        "export, not JSON or a description. Its header is client,amount, in that order. "
        "Export the following rows in their supplied order; input amounts are decimal "
        "strings. Round amounts to the approved number of decimal places using decimal "
        "ROUND_HALF_UP, preserve trailing zeroes, and use the approved decimal separator. "
        "Use the approved delimiter, encoding (utf-8 means no BOM; utf-8-sig means a UTF-8 "
        "BOM; utf-16 means a UTF-16 BOM), and line ending, including a final line ending. "
        "Use double-quote CSV escaping where needed; preserve client text exactly. Validate "
        "both actual files. This fresh checkout contains no earlier agreement or output.\n\n"
        "Input rows:\n" + json.dumps(ROWS, ensure_ascii=False, indent=2) + "\n\n"
    )
    requests = {
        "search": (
            "Use the configuration we agreed in the earlier work session. Its settings "
            "are not supplied here."
        ),
        "supplied": (
            "All approved settings are supplied below. Use this complete contract; it "
            "takes precedence over prior settings.\n\n"
            + json.dumps(original, ensure_ascii=False, indent=2)
        ),
        "current": (
            "For today's export, apply this change to the earlier agreement: "
            + change
            + " All other settings remain exactly as agreed in the earlier work session. "
            "Recover the earlier agreement and apply only this one setting change."
        ),
        "historical": (
            "There has been a change since the earlier agreement: "
            + change
            + " This request is a historical reproduction of the export BEFORE that change. "
            "Use every original setting, including the original delimiter, for both output "
            "files. Today's delimiter must not replace the historical one."
        ),
    }
    return {
        leg: {
            "prompt": common + request,
            "expected_config": current if leg == "current" else copy.deepcopy(original),
        }
        for leg, request in requests.items()
    }


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Required regular evidence file is unavailable: {path}")
    return json.loads(path.read_text())


def load_capture(source: Path) -> tuple[Task, dict[str, str], dict[str, str]]:
    """Require completed source evidence and verified literal capture, never reseed."""
    task = next(task for task in build_tasks(SEED) if task.domain == "csv_export")
    relative = Path("cases") / f"{task.id}-protocol"
    files = [
        Path("manifest.json"),
        relative / "result.json",
        relative / "establish/result.json",
        relative / "establish/memory.json",
    ]
    manifest, completed, establish, captured = [_read_json(source / path) for path in files]
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "memory-routes-macos.v1"
        or manifest.get("seed") != SEED
        or not any(
            item.get("id") == task.id and item.get("expected_config") == task.expected_config
            for item in manifest.get("tasks", [])
            if isinstance(item, dict)
        )
    ):
        raise ValueError("Source manifest does not match the frozen CSV task")
    if (
        not isinstance(completed, dict)
        or completed.get("task") != task.id
        or completed.get("policy") != "protocol"
        or not isinstance(completed.get("legs"), dict)
        or set(completed["legs"]) != {"establish", "direct", "search", "unnecessary"}
        or completed["legs"]["establish"] != establish
        or not isinstance(establish, dict)
        or establish.get("exit_code") != 0
        or establish.get("is_error")
    ):
        raise ValueError("Source CSV protocol case is not completed consistently")
    if not isinstance(captured, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in captured.items()
    ):
        raise ValueError("Source capture must contain only string keys and memory bodies")
    capture = grade_capture(captured, task.key, task.expected_config)
    if capture["passed"] is not True:
        raise ValueError(f"Source capture is blocked: {capture['reason']}; no repair is permitted")
    if not set(task.decoys).issubset(captured):
        raise ValueError("Source capture is missing one of the five original decoy records")
    return task, captured, {str(path): driver.sha(source / path) for path in files}


def make_plan(
    source: Path, legs: list[str], budget: float
) -> tuple[dict[str, Any], dict[str, str]]:
    if not legs or len(legs) != len(set(legs)) or not set(legs) <= set(LEGS):
        raise ValueError("Legs must be unique members of search,supplied,current,historical")
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("Session budget must be finite and positive")
    task, captured, source_hashes = load_capture(source)
    challenges = challenge_legs(task)
    selected = {}
    for leg in legs:
        challenge = challenges[leg]
        raw = canonical_csv(challenge["expected_config"])
        selected[leg] = {
            **challenge,
            "expected_csv_rows": expected_rows(challenge["expected_config"]),
            "canonical_csv_hex": raw.hex(),
            "canonical_csv_sha256": hashlib.sha256(raw).hexdigest(),
        }
    sources = [
        Path(__file__).resolve(),
        Path(driver.__file__).resolve(),
        *sorted((driver.REPO / "memory-bench/membench").rglob("*.py")),
    ]
    return {
        "schema": "memory-routes-csv-challenge.v1",
        "source_run": str(source.resolve()),
        "source_evidence_sha256": source_hashes,
        "source_sha256": {str(p.relative_to(driver.REPO)): driver.sha(p) for p in sources},
        "binary_sha256": {str(p): driver.sha(p) for p in (driver.BD, driver.CLAUDE, driver.PYTHON)},
        "model": driver.MODEL,
        "policy": "protocol",
        "policy_prompt": driver.BASE + driver.EXAMPLES + driver.PROCEDURE,
        "original_config": task.expected_config,
        "input_rows": list(ROWS),
        "schedule": legs,
        "session_budget_usd": budget,
        "planned_sessions": len(legs),
        "legs": selected,
        "oracle": (
            "Final regular files only. Exact effective JSON contract; CSV semantic rows, "
            "fixed decimal formatting, encoding/BOM and line endings. Equivalent double-quote "
            "escaping and UTF-16 endianness are allowed; canonical bytes are inspectable, "
            "not an exact-byte pass requirement. Original-contract delivery is scored "
            "separately from the current leg's intentionally modified effective contract."
        ),
        "interpretation": (
            "Four goal-only diagnostic branches from one actual protocol capture. No "
            "new capture test, seeded repair, spontaneous-adoption estimate, or reliability "
            "claim. Supplied/current/historical differ in task information intentionally. "
            "Temporal prompts test current applicability and historical intent, not "
            "selection among stored versions or canonical Beads history. Literal JSON "
            "capture verification does not certify surrounding memory prose."
        ),
    }, captured


def run_challenge(out: Path, leg: str, plan: dict[str, Any], captured: dict[str, str]) -> None:
    directory = out / "cases" / leg
    directory.mkdir(parents=True)
    scratch = Path(tempfile.mkdtemp(prefix="mem-csv-", dir="/tmp")).resolve()
    driver.new_json(directory / "started.json", {"leg": leg, "scratch": str(scratch)})
    try:
        setup = scratch / "setup"
        setup.mkdir()
        for name in ("config", "tmp", "bin"):
            (setup / name).mkdir()
        env = experiment_env(setup / "config", setup / "tmp", setup / "bin")
        store = scratch / "store"
        driver.initialize_store(store, env, directory / "initialization.json")
        for key, body in captured.items():
            driver.checked_bd(["remember", body, "--key", key], store, env)
        transferred = driver.memories(store, env)
        if transferred != captured:
            raise RuntimeError("Transferred memory differs from the immutable source capture")
        driver.new_json(directory / "transferred-memory.json", transferred)
        challenge = plan["legs"][leg]
        session = directory / "session"
        result, _ = driver.run_leg(
            case=scratch,
            evidence=session,
            leg=leg,
            policy="protocol",
            prompt=challenge["prompt"],
            store=store,
            native_from=None,
            expected=challenge["expected_config"],
            budget=plan["session_budget_usd"],
        )
        work = scratch / leg / "work"
        csv_grade = grade_csv(work / "invoices.csv", challenge["expected_config"])
        calls = tool_calls_from_stream((session / "stream.jsonl").read_text())
        original_route = driver.route_summary(
            result["memory_evidence"], calls, work / "config.json", plan["original_config"]
        )
        driver.new_json(
            directory / "result.json",
            {
                "leg": leg,
                "config_artifact": result["artifact"],
                "csv_artifact": csv_grade,
                "passed": result["artifact"]["passed"] and csv_grade["passed"],
                "original_contract_route": original_route,
                "session_result_sha256": driver.sha(session / "result.json"),
                "session_result": result,
            },
        )
        print(f"CSV {leg}: passed={csv_grade['passed']} reason={csv_grade['reason']}", flush=True)
    except Exception as exc:
        driver.new_json(directory / "halt.json", {"type": type(exc).__name__, "message": str(exc)})
        raise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--legs", default=",".join(LEGS))
    parser.add_argument("--session-budget", type=float, default=0.75)
    parser.add_argument("--fire", action="store_true")
    args = parser.parse_args(argv)
    plan, captured = make_plan(args.source_run, args.legs.split(","), args.session_budget)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = args.out / "manifest.json"
    snapshot = args.out / "source-memory.json"
    if manifest.exists():
        if _read_json(manifest) != plan or _read_json(snapshot) != captured:
            raise ValueError("Frozen challenge plan/source capture differs; use a new output")
    else:
        if any(args.out.iterdir()):
            raise ValueError("Nonempty challenge output has no manifest")
        driver.new_json(manifest, plan)
        driver.new_json(snapshot, captured)
    print(f"PLAN {len(plan['schedule'])} CSV sessions at {args.out}", flush=True)
    if not args.fire:
        return
    pending = []
    for leg in plan["schedule"]:
        directory = args.out / "cases" / leg
        if not directory.exists():
            pending.append(leg)
            continue
        if not (directory / "result.json").exists():
            raise ValueError(f"Interrupted challenge cannot be repurchased: {directory}")
        result = _read_json(directory / "result.json")
        if (
            result.get("leg") != leg
            or result.get("session_result_sha256") != driver.sha(directory / "session/result.json")
            or result.get("session_result") != _read_json(directory / "session/result.json")
        ):
            raise ValueError(f"Completed challenge evidence differs: {directory}")
    for leg in pending:
        run_challenge(args.out, leg, plan, captured)


if __name__ == "__main__":
    main()
