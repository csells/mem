"""Warm-vs-cold arm metric extraction + unpaired summary (mem-0ut).

The mayor's brain-selection A/B dispatches each bead to one of two arms --
``warm`` (polecat forked from a component brain session) or ``cold`` (current
cold dispatch, same briefing) -- and this module measures the five experiment
axes per bead from the trace substrate, then aggregates per arm:

- **tool_calls_before_first_edit** -- the count of ``tool_use`` blocks emitted
  before the FIRST file-mutation call (``Edit``/``Write``/``MultiEdit``, the
  `bundle.replay` mutation set). ``None`` when the session made no file
  mutation at all (typed absence: "never started editing" is not "edited
  immediately").
- **distractor_read_rate** -- files read OUTSIDE the brain's scope manifest /
  total files read. Reads harvest via `harbor_exec.project_claude_stream`
  (structured ``Read`` calls only -- shell-mediated reads are not attributed,
  same exclusion as everywhere else in membench). A read path matches a scope
  file by component-suffix (scope paths are repo-relative; trace paths are
  absolute in the session's tree -- the harbor scorer's ``_same_file``
  convention). ``None`` when no scope manifest is given OR when the session
  read no files (0/0 is undefined, not 0.0).
- **total_tokens** -- ``input_tokens + output_tokens`` from
  `probe_direct.extract_efficiency` (per-assistant-event usage sums). ``None``
  unless BOTH sides are present -- strict None-propagation, never imputed.
- **wall_clock_seconds** -- last minus first top-level ``timestamp`` in stream
  order over ALL events that carry one (Claude Code stamps message events).
  ``None`` when no event carries a timestamp; ``0.0`` with exactly one.
- **iterations_to_green** -- failing->passing transitions in the record's
  ``trace.tool_outcomes``. Exact rule: outcomes are walked in list order,
  grouped by ``runner``; each time a runner's status changes from the LAST
  observed ``fail`` to ``pass`` counts one iteration; the total is summed
  across runners. A run that never fails counts 0; a fail never followed by a
  pass for that runner counts 0 (it never went green).

Plus ``turns`` and ``tool_calls`` (continuity with the probe's efficiency
metrics) and ``files_read`` (the distractor-rate denominator, kept visible).

UNPAIRED design -- unlike `probe_gate.summarize_pairs` (the same bundle run
under both conditions, per-bundle deltas), the arms here contain DIFFERENT
beads, so there is no per-bead pairing: `summarize_arms` reports per-arm
distributions (mean/median/n per metric, None values excluded) and deltas of
the AGGREGATES (warm mean - cold mean, warm median - cold median), each delta
emitted only when both arms have at least one value -- omitted, never imputed.

Arm assignment is EXPLICIT input (`load_arm_assignment`), never inferred from
the trace: the mayor's dispatch hook will emit it; until then experimenters
hand-author it.

ZFC: pure mechanism -- file IO, structural parsing, set/percentile arithmetic.
No model calls, no semantic heuristics.
"""

import csv
import json
import posixpath
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from statistics import fmean, median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from membench.bundle.replay import _MUTATION_TOOLS
from membench.grading.probe_direct import extract_efficiency
from membench.harbor.harbor_exec import project_claude_stream

# The experiment's two arms (bead mem-0ut): brain-forked vs cold dispatch.
ARMS: tuple[str, ...] = ("warm", "cold")


class BeadMetrics(BaseModel):
    """One bead's five-axis readout (+ probe-continuity counters). ``None``
    fields are typed absences per the module-docstring rules, never zeros."""

    model_config = ConfigDict(frozen=True)

    work_id: str
    tool_calls_before_first_edit: int | None = Field(default=None, ge=0)
    distractor_read_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    files_read: int = Field(ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    wall_clock_seconds: float | None = Field(default=None, ge=0.0)
    iterations_to_green: int = Field(ge=0)
    turns: int = Field(ge=0)
    tool_calls: int = Field(ge=0)

    def metrics(self) -> dict[str, float | None]:
        """The per-bead metric vector `summarize_arms` aggregates (floats for
        uniform arithmetic; ``None`` passes through)."""
        return {
            "tool_calls_before_first_edit": _opt_float(self.tool_calls_before_first_edit),
            "distractor_read_rate": self.distractor_read_rate,
            "files_read": float(self.files_read),
            "total_tokens": _opt_float(self.total_tokens),
            "wall_clock_seconds": self.wall_clock_seconds,
            "iterations_to_green": float(self.iterations_to_green),
            "turns": float(self.turns),
            "tool_calls": float(self.tool_calls),
        }


def _opt_float(value: int | None) -> float | None:
    return None if value is None else float(value)


# --- arm assignment (explicit input, never inferred) ---------------------------------


def _validate_assignment(pairs: Iterable[tuple[str, str]], path: Path) -> dict[str, str]:
    assignment: dict[str, str] = {}
    for work_id, arm in pairs:
        if arm not in ARMS:
            raise ValueError(f"{path}: unknown arm {arm!r} for {work_id!r}; known arms: {ARMS}")
        if work_id in assignment:
            raise ValueError(f"{path}: duplicate work_id {work_id!r}")
        assignment[work_id] = arm
    if not assignment:
        raise ValueError(f"{path}: empty arm assignment")
    return assignment


def load_arm_assignment(path: Path) -> dict[str, str]:
    """The explicit ``work_id -> arm`` map. JSON (object mapping, or a list of
    ``{work_id, arm}`` rows) or CSV (``work_id,arm`` header), by file suffix.
    Unknown arms, duplicate work_ids, and an empty file all raise."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, Mapping):
            pairs = [(str(k), str(v)) for k, v in raw.items()]
        elif isinstance(raw, list):
            pairs = [(str(row["work_id"]), str(row["arm"])) for row in raw]
        else:
            raise ValueError(f"{path}: JSON must be a mapping or a list of rows")
    elif suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            pairs = [(row["work_id"], row["arm"]) for row in csv.DictReader(handle)]
    else:
        raise ValueError(f"{path}: unsupported suffix {suffix!r} (expected .json or .csv)")
    return _validate_assignment(pairs, path)


# --- scope manifest -------------------------------------------------------------------


def load_scope_files(path: Path) -> tuple[str, ...]:
    """The scope's repo-relative file list from a brain manifest JSON.

    Accepts the brains CLI manifest (``fileHashes`` keys -- the per-file
    SHA-256 map pins exactly the resolved in-scope files) or a plain
    ``{"files": [...]}`` listing. Anything else raises -- scope globs alone
    are NOT accepted, the distractor rate needs concrete paths."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path}: manifest must be a JSON object")
    files = raw.get("files")
    if isinstance(files, list):
        return tuple(sorted(str(f) for f in files))
    hashes = raw.get("fileHashes")
    if isinstance(hashes, Mapping):
        return tuple(sorted(str(f) for f in hashes))
    raise ValueError(f"{path}: expected a 'files' list or a brains-manifest 'fileHashes' map")


# --- fork boundary (mem-0ut.1) ----------------------------------------------------------
#
# A ``--fork-session`` warm transcript PHYSICALLY contains the brain session's
# inherited build events. Measured raw, the warm arm's headline metric INVERTS
# (the pilot saw tool_calls_before_first_edit 4.0 vs cold 3.5) because the brain
# prefix's reads are counted as the fork's own pre-edit work. Faithful measurement
# excludes the inherited prefix -- events with ``timestamp <= brain.builtAt`` belong
# to the brain, not the fork -- from the stream-derived axes before the metrics are
# computed. The outcomes-derived axis (``iterations_to_green``) needs no trim: the
# brain is a READ-ONLY exploration, so it fires no test/build runners and contributes
# no ``tool_outcomes`` (which carry no timestamp to trim by in any case).


def _parse_iso_ts(value: str) -> datetime:
    """ISO-8601 to a datetime, tolerating the trailing ``Z`` Claude Code stamps
    (``datetime.fromisoformat`` accepts ``+00:00`` on every supported runtime)."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_brain_built_at(path: Path) -> datetime | None:
    """The brain manifest's ``builtAt`` as the fork boundary every warm transcript
    inherits up to. ``None`` when the manifest carries no ``builtAt`` -- the caller
    then falls back to a per-record stamp or measures the arm raw (and warns). A
    present-but-unparseable ``builtAt`` raises (a corrupt boundary must not pass)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path}: manifest must be a JSON object")
    built_at = raw.get("builtAt")
    if built_at is None:
        return None
    if not isinstance(built_at, str):
        raise ValueError(f"{path}: 'builtAt' must be an ISO-8601 string, got {type(built_at)}")
    return _parse_iso_ts(built_at)


def trim_inherited_events(stream_text: str, boundary: datetime) -> str:
    """The stream with every event whose ``timestamp`` is ``<= boundary`` removed --
    the inherited brain-build prefix of a forked warm transcript (mem-0ut.1).

    A line is KEPT when it is non-JSON, carries no ``timestamp``, or its timestamp
    cannot be parsed/compared to the boundary: the trim only excludes provably-
    inherited events, never guesses one away."""
    kept: list[str] = []
    for line in stream_text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            kept.append(line)
            continue
        stamp = event.get("timestamp") if isinstance(event, Mapping) else None
        if isinstance(stamp, str):
            try:
                if _parse_iso_ts(stamp) <= boundary:
                    continue  # inherited brain-prefix event
            except (ValueError, TypeError):
                pass  # unparseable / naive-vs-aware -> keep (never guess inheritance)
        kept.append(line)
    return "\n".join(kept) + "\n" if kept else ""


def fork_boundary_for(
    record: Mapping[str, Any], arm: str, manifest_built_at: datetime | None
) -> datetime | None:
    """The fork boundary to trim a record's stream by, or ``None`` (no trim).

    Cold records are never trimmed. A warm record prefers a per-record stamp
    (``record['fork']['fork_ts']`` -- the dispatch-hook fork-boundary stamp, option
    2, the deterministic source) over the shared manifest ``builtAt`` (option 1,
    inferred). A warm record with neither source returns ``None`` -- the caller
    measures it raw and must warn, since the headline metric then inverts."""
    if arm != "warm":
        return None
    fork = record.get("fork")
    if isinstance(fork, Mapping):
        stamped = fork.get("fork_ts")
        if isinstance(stamped, str):
            return _parse_iso_ts(stamped)
    return manifest_built_at


# --- per-axis extraction ----------------------------------------------------------------


def _iter_content_blocks(stream: str, block_type: str) -> Iterable[Mapping[str, Any]]:
    """Every message content block of ``block_type`` in stream order -- the same tolerant
    event walk as `project_claude_stream` (non-JSON lines and shapeless events skipped)."""
    for line in stream.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = event.get("message") if isinstance(event, Mapping) else None
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, Mapping) and block.get("type") == block_type:
                yield block


def _iter_tool_use_blocks(stream: str) -> Iterable[Mapping[str, Any]]:
    """Every ``tool_use`` block in stream order."""
    return _iter_content_blocks(stream, "tool_use")


def _iter_tool_result_blocks(stream: str) -> Iterable[Mapping[str, Any]]:
    """Every ``tool_result`` block in stream order -- the ``user`` events Claude Code prints
    when a tool returns, each keyed to its call by ``tool_use_id``."""
    return _iter_content_blocks(stream, "tool_result")


def tool_calls_before_first_edit(stream: str) -> int | None:
    """Count of ``tool_use`` blocks before the first ``Edit``/``Write``/
    ``MultiEdit`` call; ``None`` when the stream contains no mutation call."""
    for count, block in enumerate(_iter_tool_use_blocks(stream)):
        if block.get("name") in _MUTATION_TOOLS:
            return count
    return None


def distractor_read_rate(
    files_read: Sequence[str], scope_files: Sequence[str] | None
) -> float | None:
    """Out-of-scope reads / total reads. ``None`` without a scope manifest or
    without any reads. Matching rule: a (normalized) read path is in scope when
    it equals a scope path or ends with ``"/" + scope_path`` -- whole-component
    suffix match, so ``xsrc/a.ts`` never matches scope file ``src/a.ts``."""
    if scope_files is None or not files_read:
        return None
    scope = {posixpath.normpath(f) for f in scope_files}

    def in_scope(path: str) -> bool:
        norm = posixpath.normpath(path)
        return any(norm == s or norm.endswith("/" + s) for s in scope)

    outside = sum(1 for path in files_read if not in_scope(path))
    return outside / len(files_read)


def wall_clock_seconds(stream: str) -> float | None:
    """Last minus first top-level ``timestamp`` in STREAM ORDER (the documented
    first->last rule, not min/max). ``None`` when no event carries a timestamp."""
    first: datetime | None = None
    last: datetime | None = None
    for line in stream.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        stamp = event.get("timestamp") if isinstance(event, Mapping) else None
        if not isinstance(stamp, str):
            continue
        try:
            parsed = datetime.fromisoformat(stamp)
        except ValueError:
            continue
        if first is None:
            first = parsed
        last = parsed
    if first is None or last is None:
        return None
    return (last - first).total_seconds()


def iterations_to_green(tool_outcomes: Sequence[Mapping[str, Any]]) -> int:
    """Failing->passing transitions in ``trace.tool_outcomes`` (exact rule in
    the module docstring: per-runner last-status tracking, summed). A malformed
    entry raises -- the outcomes are our own store projection, so a shapeless
    one is an ingest bug, never a silent skip."""
    last_status: dict[str, str] = {}
    transitions = 0
    for i, outcome in enumerate(tool_outcomes):
        if not isinstance(outcome, Mapping):
            raise ValueError(f"tool_outcome[{i}] is not a mapping: {outcome!r}")
        runner, status = outcome.get("runner"), outcome.get("status")
        if not isinstance(runner, str) or not isinstance(status, str):
            raise ValueError(f"tool_outcome[{i}] missing runner/status: {dict(outcome)!r}")
        if status == "pass" and last_status.get(runner) == "fail":
            transitions += 1
        last_status[runner] = status
    return transitions


# --- per-bead extraction -----------------------------------------------------------------


def extract_bead_metrics(
    record: Mapping[str, Any],
    stream_text: str,
    scope_files: Sequence[str] | None = None,
    *,
    fork_boundary: datetime | None = None,
) -> BeadMetrics:
    """One bead's full metric vector from its canonical record + raw trace stream.

    ``record`` is the store's ``record`` JSON (``work_id`` required;
    ``trace.tool_outcomes`` defaults to none-recorded); ``stream_text`` is the
    resolved trace .jsonl; ``scope_files`` is the brain scope (None -> no
    distractor rate).

    ``fork_boundary`` (mem-0ut.1): when set, the inherited brain-build prefix
    (events with ``timestamp <= fork_boundary``) is trimmed from the stream before
    the stream-derived axes are computed, so a forked warm transcript is measured
    from its OWN work and the headline metric does not invert. Cold arms pass
    ``None`` (no trim). ``iterations_to_green`` is unaffected -- a read-only brain
    contributes no ``tool_outcomes``."""
    work_id = record.get("work_id")
    if not isinstance(work_id, str) or not work_id:
        raise ValueError(f"record carries no work_id: keys {sorted(record)}")
    if fork_boundary is not None:
        stream_text = trim_inherited_events(stream_text, fork_boundary)
    trace = record.get("trace")
    outcomes = trace.get("tool_outcomes", []) if isinstance(trace, Mapping) else []
    if not isinstance(outcomes, list):
        raise ValueError(f"{work_id}: trace.tool_outcomes is not a list: {type(outcomes)}")

    efficiency = extract_efficiency(stream_text)
    if efficiency.input_tokens is None or efficiency.output_tokens is None:
        total_tokens = None  # strict None-propagation: never impute a missing side as 0
    else:
        total_tokens = efficiency.input_tokens + efficiency.output_tokens
    files_read = project_claude_stream(stream_text)["files_read"]

    return BeadMetrics(
        work_id=work_id,
        tool_calls_before_first_edit=tool_calls_before_first_edit(stream_text),
        distractor_read_rate=distractor_read_rate(files_read, scope_files),
        files_read=len(files_read),
        total_tokens=total_tokens,
        wall_clock_seconds=wall_clock_seconds(stream_text),
        iterations_to_green=iterations_to_green(outcomes),
        turns=efficiency.turns,
        tool_calls=efficiency.tool_calls,
    )


# --- unpaired arm summary --------------------------------------------------------------


def _metric_stats(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {"mean": None, "median": None, "n": 0}
    return {"mean": fmean(values), "median": median(values), "n": len(values)}


def summarize_arms(per_arm: Mapping[str, Sequence[BeadMetrics]]) -> dict[str, Any]:
    """Per-arm distributions + warm-cold deltas of the aggregates.

    UNPAIRED (module docstring): different beads per arm, so no per-bead
    deltas -- only per-arm mean/median/n per metric (None values excluded)
    and ``warm aggregate - cold aggregate`` deltas, each emitted only when
    both arms carry at least one value for that metric."""
    unknown = set(per_arm) - set(ARMS)
    if unknown:
        raise ValueError(f"unknown arm(s) {sorted(unknown)}; known arms: {ARMS}")
    if not any(per_arm.get(arm) for arm in ARMS):
        raise ValueError("no per-bead results in either arm")

    metric_names = list(BeadMetrics.model_fields)
    metric_names.remove("work_id")
    arm_values: dict[str, dict[str, list[float]]] = {}
    arms_out: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        vectors = [bead.metrics() for bead in per_arm.get(arm, ())]
        arm_values[arm] = {
            metric: [value for v in vectors if (value := v[metric]) is not None]
            for metric in metric_names
        }
        arms_out[arm] = {m: _metric_stats(arm_values[arm][m]) for m in metric_names}

    deltas: dict[str, Any] = {}
    for metric in metric_names:
        warm, cold = arm_values["warm"][metric], arm_values["cold"][metric]
        if not warm or not cold:
            continue  # omitted, never imputed
        deltas[metric] = {
            "mean_delta": fmean(warm) - fmean(cold),
            "median_delta": median(warm) - median(cold),
            "n_warm": len(warm),
            "n_cold": len(cold),
        }

    return {
        "design": "unpaired",
        "n_per_arm": {arm: len(per_arm.get(arm, ())) for arm in ARMS},
        "arms": arms_out,
        "deltas": deltas,
    }
