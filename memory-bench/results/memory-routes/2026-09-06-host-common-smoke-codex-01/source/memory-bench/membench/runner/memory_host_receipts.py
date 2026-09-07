"""Join real bd executions to host tool results without host-specific hooks.

Raw receipts contain a harness session identity, never invented host identities.
A UUID marker is emitted on stderr before forwarding bd's bytes; it is excluded from those
recorded bytes. Only a unique marker in a completed shell result permits a derived
receipt with parser-provided host IDs. This establishes attribution, not delivery:
the existing scorer independently checks that bd stdout reached the tool result.

Use score_correlated, or explicitly retain correlate's unknown diagnostics when
scoring. Missing associations must not silently disappear. Markers are consistent
instrumentation across hosts, but can affect commands that merge stderr into their
data. Writable scratch receipts and visible markers are not a security boundary.
The standalone shim imports only stdlib and the copied bd_receipts append helper.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

from membench.runner import bd_receipts

if TYPE_CHECKING:
    from membench.runner.bd_real_metrics import RealLegEvidence
    from membench.schemas.trace import ToolCall

SCHEMA = "memory-host-receipt.v1"
_UUID = re.compile(r"[0-9a-f]{32}\Z")
_MARKER = re.compile(r"\[MEMBENCH_BD_EXECUTION:([0-9a-f]{32})\]")


def marker(invocation_id: str) -> str:
    if not _UUID.fullmatch(invocation_id):
        raise ValueError("Invalid execution UUID")
    return f"[MEMBENCH_BD_EXECUTION:{invocation_id}]"


def prepare(
    directory: Path,
    store: Path,
    leg_id: str,
    harness_session_id: str,
    *,
    binary: Path,
    python: Path,
) -> tuple[Path, Path]:
    """Create a new standalone shim; return (raw receipt path, shim path)."""
    if not leg_id.strip() or not harness_session_id.strip():
        raise ValueError("Harness session and leg identities are required")
    directory, store, binary, python = (
        path.resolve() for path in (directory, store, binary, python)
    )
    if not store.is_dir() or not binary.is_file() or not python.is_file():
        raise ValueError("Store and executable paths must exist")
    if "\n" in str(python) or " " in str(python):
        raise ValueError("Python shebang path cannot contain whitespace")
    directory.mkdir()
    package = directory / "membench" / "runner"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").touch()
    (package / "__init__.py").touch()
    shutil.copyfile(__file__, package / Path(__file__).name)
    assert bd_receipts.__file__
    shutil.copyfile(bd_receipts.__file__, package / "bd_receipts.py")
    receipts = directory / "receipts.jsonl"
    receipts.touch(exist_ok=False)
    spec = directory / "receipt-policy.json"
    with spec.open("x") as target:
        json.dump(
            {
                "binary": str(binary),
                "store": str(store),
                "leg_id": leg_id,
                "harness_session_id": harness_session_id,
                "receipt_path": str(receipts),
            },
            target,
        )
    shim = directory / "bd"
    with shim.open("x") as target:
        target.write(
            f"#!{python}\nfrom pathlib import Path\n"
            "from membench.runner.memory_host_receipts import shim_main\n"
            f"raise SystemExit(shim_main(Path({str(spec)!r})))\n"
        )
    shim.chmod(0o700)
    return receipts, shim


def shim_main(spec_path: Path) -> int:
    """Execute once and retain exact CLI bytes, including failed-command outcomes."""
    spec = json.loads(spec_path.read_text())
    invocation = uuid.uuid4().hex
    receipt_path = Path(spec["receipt_path"])
    identity = {
        "schema": SCHEMA,
        "invocation_id": invocation,
        "harness_session_id": spec["harness_session_id"],
        "leg_id": spec["leg_id"],
        "argv": [spec["binary"], "-C", spec["store"], *sys.argv[1:]],
        "operation_argv": sys.argv[1:],
        "start_monotonic_ns": time.monotonic_ns(),
    }
    bd_receipts.append_record(receipt_path, {**identity, "event": "start"})
    try:
        result = subprocess.run(identity["argv"], capture_output=True, check=False)
    except OSError as exc:
        bd_receipts.append_record(
            receipt_path, {**identity, "event": "launch_error", "error_type": type(exc).__name__}
        )
        raise
    bd_receipts.append_record(
        receipt_path,
        {
            **identity,
            "event": "finish",
            "returncode": result.returncode,
            "stdout": result.stdout.decode("utf-8", errors="replace"),
            "stderr": result.stderr.decode("utf-8", errors="replace"),
            "stdout_base64": base64.b64encode(result.stdout).decode("ascii"),
            "stderr_base64": base64.b64encode(result.stderr).decode("ascii"),
            "end_monotonic_ns": time.monotonic_ns(),
        },
    )
    # Put attribution before data so ordinary `2>&1 | head` retains the marker.
    # A completed raw pair is still required; neither marker nor truncation proves
    # success or delivery of the omitted stdout payload.
    sys.stderr.buffer.write(marker(invocation).encode() + b"\n")
    sys.stderr.buffer.flush()
    sys.stdout.buffer.write(result.stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(result.stderr)
    sys.stderr.buffer.flush()
    if result.returncode < 0:
        signum = -result.returncode
        if signum not in (signal.SIGKILL, signal.SIGSTOP):
            signal.signal(signum, signal.SIG_DFL)
        signal.raise_signal(signum)
    return int(result.returncode)


def _valid_pair(pair: list[dict[str, Any]]) -> bool:
    if len(pair) != 2 or [row.get("event") for row in pair] != ["start", "finish"]:
        return False
    start, end = pair
    stable = (
        "schema",
        "invocation_id",
        "harness_session_id",
        "leg_id",
        "argv",
        "operation_argv",
        "start_monotonic_ns",
    )
    if any(start.get(key) != end.get(key) for key in stable):
        return False
    if any("session_id" in row or "tool_use_id" in row for row in pair):
        return False
    if end.get("schema") != SCHEMA or any(
        not isinstance(end.get(key), str) or not end[key].strip()
        for key in ("harness_session_id", "leg_id")
    ):
        return False
    argv, operation = end.get("argv"), end.get("operation_argv")
    if (
        not isinstance(argv, list)
        or len(argv) < 4
        or not all(isinstance(arg, str) for arg in argv)
        or argv[1] != "-C"
        or not Path(argv[0]).is_absolute()
        or not Path(argv[2]).is_absolute()
        or not isinstance(operation, list)
        or argv[3:] != operation
    ):
        return False
    begin, stop = end.get("start_monotonic_ns"), end.get("end_monotonic_ns")
    if type(begin) is not int or type(stop) is not int or not 0 <= begin <= stop:
        return False
    if type(end.get("returncode")) is not int:
        return False
    try:
        for field in ("stdout", "stderr"):
            value, encoded = end.get(field), end.get(field + "_base64")
            if not isinstance(value, str) or not isinstance(encoded, str):
                return False
            if base64.b64decode(encoded, validate=True).decode("utf-8", errors="replace") != value:
                return False
    except ValueError:
        return False
    return True


def correlate(
    raw: list[dict[str, Any]], calls: list[ToolCall], host_session_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Derive host attribution only; no timestamps or output similarity join IDs."""
    reasons: list[str] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in raw:
        invocation = row.get("invocation_id")
        if not isinstance(invocation, str) or not _UUID.fullmatch(invocation):
            reasons.append("invalid_raw_invocation_id")
            continue
        grouped.setdefault(invocation, []).append(row)
    matches: dict[str, list[ToolCall]] = {}
    for call in calls:
        for invocation in _MARKER.findall(call.result or ""):
            matches.setdefault(invocation, []).append(call)
    for invocation in matches.keys() - grouped.keys():
        reasons.append(f"marker_without_execution:{invocation}")
    call_ids = Counter(call.tool_use_id for call in calls if call.tool_use_id)
    derived: list[dict[str, Any]] = []
    associations: list[dict[str, Any]] = []
    contexts = {
        (row.get("harness_session_id"), row.get("leg_id"))
        for row in raw
        if isinstance(row.get("harness_session_id"), str) and isinstance(row.get("leg_id"), str)
    }
    global_valid = isinstance(host_session_id, str) and bool(host_session_id.strip())
    if not global_valid:
        reasons.append("missing_host_session_id")
    if len(contexts) > 1:
        reasons.append("mixed_raw_session_contexts")
        global_valid = False
    for invocation, pair in grouped.items():
        if not _valid_pair(pair):
            reasons.append(f"invalid_or_incomplete_raw_pair:{invocation}")
            continue
        matched = matches.get(invocation, [])
        if len(matched) != 1:
            reasons.append(f"missing_or_duplicate_marker:{invocation}")
            continue
        call = matched[0]
        if (
            not global_valid
            or call.name != "Bash"
            or not call.tool_use_id
            or not call.tool_use_id.strip()
            or call_ids[call.tool_use_id] != 1
            or call.tool_result_index is None
            or (call.tool_use_index is not None and call.tool_result_index <= call.tool_use_index)
        ):
            reasons.append(f"unattributable_completed_result:{invocation}")
            continue
        associations.append(
            {
                "invocation_id": invocation,
                "host_session_id": host_session_id,
                "host_tool_use_id": call.tool_use_id,
                "tool_result_index": call.tool_result_index,
                "method": "unique_execution_marker_in_completed_shell_result",
            }
        )
        for row in pair:
            derived.append(
                {
                    **row,
                    "schema": "memory-host-derived-receipt.v1",
                    "session_id": host_session_id,
                    "tool_use_id": call.tool_use_id,
                }
            )
    return derived, {
        "evidence_unknown": bool(reasons),
        "unknown_reasons": sorted(set(reasons)),
        "associations": associations,
    }


def score_correlated(
    raw: list[dict[str, Any]],
    calls: list[ToolCall],
    host_session_id: str,
    *,
    leg_id: str,
    status: str,
    expected_binary: str,
    expected_store: str,
) -> tuple[RealLegEvidence, dict[str, Any]]:
    """Score valid associations while retaining every correlation evidence failure."""
    from membench.runner.bd_real_metrics import score_real_leg

    derived, diagnostics = correlate(raw, calls, host_session_id)
    evidence = score_real_leg(
        calls,
        derived,
        leg_id=leg_id,
        status=status,
        expected_binary=expected_binary,
        expected_store=expected_store,
        expected_session=host_session_id,
    )
    reasons = sorted(set(evidence.unknown_reasons) | set(diagnostics["unknown_reasons"]))
    return evidence.model_copy(
        update={"evidence_unknown": bool(reasons), "unknown_reasons": tuple(reasons)}
    ), {
        **diagnostics,
        "derived_receipts": derived,
    }
