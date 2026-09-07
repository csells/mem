"""C1.3 base-rate go/no-go spike driver (mem-apg.3.1).

Runs the none-rung ablation over a handful of held-out beads end-to-end: reconstruct
each bead's approximate environment, run the agent through real Harbor, score the fresh
run against the bead's held ``trace_errors``, and feed the none-rung reward records to
the base-rate gate. The smallest experiment that says whether the deterministic
avoid-axis has usable dynamic range before investing in the full grid (mem-lvp §11
synthetic fallback is the escalation if the gate returns INSUFFICIENT_POWER / NO_GO).

Store access reads the SQLite store directly via Python ``sqlite3``, NOT the ``mem``
CLI: the landed store is schema v2 while the CLI expects v3 (re-ingest drift), but the
raw ``work_records`` / ``trace_errors`` tables this driver needs are intact and stable.

The orchestration is injectable end-to-end (``runner``, ``load_record``,
``load_held_errors``, ``reconstruct``) so the whole driver runs under the StubRunner
with no Docker, git, or subscription -- only the production `main` wires the real
HarborRunner + ``mem extract-errors`` extractor.
"""

import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from membench.grading import RewardRecord, TraceErrorRef
from membench.grading.base_rate import GateVerdict, base_rate_gate
from membench.grading.trace_score import deterministic_term
from membench.harbor.env_recon import reconstruct_env_for_record
from membench.harbor.grid import AgentRunner, ErrorExtractor, HarborRunner, run_grid
from membench.harbor.harbor_exec import harbor_exec
from membench.harbor.task_env import NetworkMode
from membench.mem_cli import run_mem_json

RecordLoader = Callable[[str], Mapping[str, Any]]
HeldErrorsLoader = Callable[[str], list[TraceErrorRef]]


# --- store loaders (direct sqlite3; CLI is schema-version-incompatible) ----------


def load_record_from_store(store_path: str | Path, work_id: str) -> dict[str, Any]:
    """The held-out bead's canonical WorkRecord (the ``record`` JSON column).

    Loads the full record -- not the flat projection columns -- because the adapter and
    `validity.query_from_record` consume the canonical shape (``lifecycle.started``,
    ``title``, ``metadata``), and `env_recon` reads the same boundary. Raises if the
    bead is absent: a spike over a non-existent work_id is a caller error."""
    con = sqlite3.connect(f"file:{store_path}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT record FROM work_records WHERE work_id = ?", (work_id,)
        ).fetchone()
    finally:
        con.close()
    if row is None:
        raise KeyError(f"work_id {work_id!r} not in store {store_path}")
    record: dict[str, Any] = json.loads(row[0])
    return record


def load_held_errors_from_store(store_path: str | Path, work_id: str) -> list[TraceErrorRef]:
    """The bead's ``trace_errors`` as the scorer's `TraceErrorRef`s, in stable id order.

    Raises on an empty set: the held-out set is 'beads with ≥1 trace_error', so a bead
    with none here is a selection error the caller must see, not score as vacuous."""
    con = sqlite3.connect(f"file:{store_path}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT tool, file, line, error_class, signature "
            "FROM trace_errors WHERE work_id = ? ORDER BY id",
            (work_id,),
        ).fetchall()
    finally:
        con.close()
    if not rows:
        raise ValueError(f"work_id {work_id!r} has no trace_errors in {store_path}")
    return [TraceErrorRef.from_mapping(dict(r)) for r in rows]


# --- the real-run error extractor (canonical TS extractor as a subprocess) -------


def make_cli_extractor(mem_bin: str | Path) -> ErrorExtractor:
    """An `ErrorExtractor` that shells the canonical ``mem extract-errors`` (mem-apg.3.1.1).

    Stateless -- it never touches the store, so the v2/v3 store drift is irrelevant here.
    Delegates to `mem_cli.run_mem_json`, the shared envelope/failure-mode seam, so a
    missing binary, a hang, a non-zero exit, or a malformed envelope all raise
    `MemCliError` instead of a bare subprocess failure."""

    def extract(output: str) -> list[Mapping[str, Any]]:
        data = run_mem_json([str(mem_bin), "extract-errors"], input=output)
        errors: list[Mapping[str, Any]] = data["errors"]
        return errors

    return extract


# --- spike result + driver -------------------------------------------------------


@dataclass(frozen=True)
class BeadOutcome:
    """One bead's none-rung readout: did the run reach the held path, and (if so) did
    the known failure recur? ``deterministic`` is the tri-state avoid term (None when
    the path was never reached -- the no-op guard)."""

    work_id: str
    path_reached: bool
    deterministic: float | None


@dataclass(frozen=True)
class SpikeResult:
    """The base-rate spike's full readout: per-bead outcomes, the raw reward records,
    and the gate verdict computed over them."""

    outcomes: tuple[BeadOutcome, ...]
    records: tuple[RewardRecord, ...]
    verdict: GateVerdict


def run_base_rate_spike(
    work_ids: Sequence[str],
    *,
    output_dir: str | Path,
    runner: AgentRunner,
    load_record: RecordLoader,
    load_held_errors: HeldErrorsLoader,
    reconstruct: bool = True,
    repeats: int = 1,
    rung: str = "none",
    base_ref: str = "origin/main",
    network: NetworkMode = "no-network",
) -> SpikeResult:
    """Run the none-rung base-rate spike over ``work_ids`` and gate the result.

    Each bead is run ``repeats`` times (within-task repeats the gate collapses by
    majority vote). ``reconstruct`` bakes each bead's environment in before the run; set
    False under the StubRunner (no Docker/git). ``network`` must be "allowlist" for real
    Harbor runs (the installed agent fetches its CLI + deps, but public egress would let
    it fetch the landed gold fix from the rig's GitHub repo -- mem-yeoz); "public" is
    the explicit escape hatch. Raises if ``work_ids`` is empty -- the gate cannot speak
    to a rung it never saw."""
    if not work_ids:
        raise ValueError("run_base_rate_spike needs at least one work_id")
    output_dir = Path(output_dir)

    records: list[RewardRecord] = []
    outcomes: list[BeadOutcome] = []
    for work_id in work_ids:
        record = load_record(work_id)
        held = load_held_errors(work_id)
        reconstructor: Callable[[Path], object] | None = (
            partial(reconstruct_env_for_record, record=record, base_ref=base_ref)
            if reconstruct
            else None
        )
        bead_records: list[RewardRecord] = []
        for repeat_idx in range(repeats):
            bead_records.extend(
                run_grid(
                    record,
                    output_dir / work_id,
                    held_errors=held,
                    runner=runner,
                    rungs=(rung,),
                    repeat_idx=repeat_idx,
                    overwrite=True,
                    env_reconstructor=reconstructor,
                    network=network,
                )
            )
        records.extend(bead_records)
        dets = [deterministic_term(r.components) for r in bead_records]
        outcomes.append(
            BeadOutcome(
                work_id=work_id,
                path_reached=any(r.components.path_reached for r in bead_records),
                deterministic=next((d for d in dets if d is not None), None),
            )
        )

    verdict = base_rate_gate(records, rung=rung)
    return SpikeResult(outcomes=tuple(outcomes), records=tuple(records), verdict=verdict)


def run_real_spike(
    work_ids: Sequence[str],
    *,
    store_path: str | Path,
    mem_bin: str | Path,
    output_dir: str | Path,
    model: str | None = None,
    repeats: int = 1,
    network: NetworkMode = "allowlist",
) -> SpikeResult:
    """Production entry: wire the real HarborRunner + CLI extractor + store loaders.

    Requires Docker up and ``CLAUDE_CODE_OAUTH_TOKEN`` in the environment (Harbor reads
    it from the host). Reconstructs each bead's environment and runs the agent for real.
    ``network`` defaults to "allowlist" (agent hosts + package registries only -- the
    landed gold fix is publicly fetchable, mem-yeoz); pass "public" as the explicit
    escape hatch for unrestricted egress."""
    runner = HarborRunner(
        extractor=make_cli_extractor(mem_bin),
        exec_task=partial(harbor_exec, model=model),
    )
    return run_base_rate_spike(
        work_ids,
        output_dir=output_dir,
        runner=runner,
        load_record=partial(load_record_from_store, store_path),
        load_held_errors=partial(load_held_errors_from_store, store_path),
        reconstruct=True,
        repeats=repeats,
        network=network,
    )
