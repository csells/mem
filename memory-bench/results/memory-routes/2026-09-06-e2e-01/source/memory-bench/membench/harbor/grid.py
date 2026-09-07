"""Ablation grid execution driver (mem-apg.3d).

Ties mem-apg.2 (the WorkRecord -> rung task dirs adapter) to mem-apg.3a (the
deterministic trace_error scorer): for one held-out WorkRecord,

    record --adapter--> per-rung task dirs --inject memory--> agent run per rung
        --harvest--> RunTrace --score_run--> RewardRecord(work_id, rung, repeat_idx)

The driver is pure plumbing (ZFC): IO, subprocess, mechanical injection, and the
deterministic scorer call. It makes no semantic judgment.

The agent is driven through an `AgentRunner`:

- `StubRunner` -- deterministic, injectable. Resolves a pre-built RunTrace by the
  task's rung (read from the `task.toml` the adapter wrote). The whole pipeline +
  tests run on it with NO Docker, network, or paid API.
- `HarborRunner` -- thin. Shells `harbor run <task_dir>` on the Claude OAuth
  subscription (NOT a paid-API cost fork, D16) and HARVESTS the result into a
  RunTrace: structured errors via the injected TS extractor
  (`parse/error-extractors.ts`), `files_touched` from the run's files_read /
  files_written. Real exec is not exercised in CI; the harvesting logic
  (`harvest_run_trace`) is tested with a fixture transcript + injected extractor.

DEFERRED to a child of mem-apg.3 (not built here): real harbor exec at scale, the
`builtin` / `ours+builtin` rungs (the agent's opaque memory, mem-whi), and the
C1.3 base-rate go/no-go run over the held-out beads.
"""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import toml

from membench.grading import (
    AblationSource,
    RewardRecord,
    RunTrace,
    TraceErrorRef,
    score_run,
)
from membench.harbor.harbor_exec import harbor_exec
from membench.harbor.memory_inject import (
    DeferredRungError,
    inject_rung_memory,
    validate_rungs,
)
from membench.harbor.task_env import NetworkMode
from membench.harbor.workrecord_adapter import WorkRecordLadderAdapter

# Turns a fresh run's combined build/test/lint output into trace_errors-shaped
# rows (the `TraceErrorRef.from_mapping` shape). The canonical implementation is
# the TS extractor (`parse/error-extractors.ts`); injected so CI needs no TS build.
ErrorExtractor = Callable[[str], list[Mapping[str, Any]]]

# One fresh run's raw result: the combined tool output plus the files the run read
# and wrote. The `harbor run` adapter (and the StubRunner's fixtures) emit this.
RunTranscript = Mapping[str, Any]


class AgentRunner(Protocol):
    """Runs the agent against one prepared task dir and returns its harvested run."""

    def run(self, task_dir: Path) -> RunTrace: ...


def _rung_of(task_dir: Path) -> str:
    """Read the rung the adapter recorded in the task's `task.toml` metadata.

    The rung is authoritative metadata, not inferred from the dir name, so a
    renamed dir cannot silently mis-route the run."""
    config = toml.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
    return str(config["metadata"]["rung"])


def harvest_run_trace(transcript: RunTranscript, *, extractor: ErrorExtractor) -> RunTrace:
    """Harvest a `RunTrace` from one run's raw transcript.

    `errors` come from running the injected extractor over the transcript's
    combined output; `files_touched` is the union of files_read and files_written
    (the evidence the scorer's `path_reached` gate consumes). Missing file keys
    default to empty -- a run that read/wrote nothing is a real (no-op) outcome."""
    rows = extractor(str(transcript.get("output", "")))
    errors = tuple(TraceErrorRef.from_mapping(row) for row in rows)
    touched = frozenset(transcript.get("files_read", ())) | frozenset(
        transcript.get("files_written", ())
    )
    return RunTrace(errors=errors, files_touched=touched)


class StubRunner:
    """Deterministic `AgentRunner` that returns a pre-built RunTrace per rung.

    The injectable test seam for the whole pipeline: no Docker, network, or paid
    API. Resolves by the task's rung (from `task.toml`) so the driver exercises the
    real per-rung wiring while the agent itself is mocked."""

    def __init__(self, traces_by_rung: Mapping[str, RunTrace]) -> None:
        self._traces = dict(traces_by_rung)

    def run(self, task_dir: Path) -> RunTrace:
        rung = _rung_of(task_dir)
        if rung not in self._traces:
            raise KeyError(f"StubRunner has no trace for rung {rung!r} ({task_dir})")
        return self._traces[rung]


def _default_exec(task_dir: Path) -> RunTranscript:
    """Run the task through real Harbor and project its ATIF trajectory.

    The real exec path -- NOT exercised in CI (HarborRunner is tested with an
    injected `exec_task`). Delegates to `harbor_exec`: `harbor run --config` on the
    Claude OAuth subscription (D16, not a paid-API cost fork) -> ATIF trajectory ->
    `{output, files_read, files_written}` transcript. A non-zero exit, missing task
    dir, or absent trajectory raises -- a failed run is never silently a clean trace."""
    return harbor_exec(task_dir)


class HarborRunner:
    """Thin `AgentRunner` over `harbor run`: exec the task, harvest a RunTrace.

    The exec is injectable (`exec_task`) so the harvesting logic is testable with a
    fixture transcript and no Harbor present; the default shells `harbor run`. The
    `extractor` turns the run's output into structured errors (the injected TS
    extractor). All semantic work lives in the agent + the extractor; this class is
    pure harvesting glue."""

    def __init__(
        self,
        *,
        extractor: ErrorExtractor,
        exec_task: Callable[[Path], RunTranscript] = _default_exec,
    ) -> None:
        self._extractor = extractor
        self._exec_task = exec_task

    def run(self, task_dir: Path) -> RunTrace:
        transcript = self._exec_task(task_dir)
        return harvest_run_trace(transcript, extractor=self._extractor)


def run_grid(
    record: Mapping[str, Any],
    output_dir: str | Path,
    *,
    held_errors: Sequence[TraceErrorRef],
    runner: AgentRunner,
    rungs: tuple[str, ...] = ("none", "ours", "oracle"),
    vector_payloads: dict[str, str] | None = None,
    ours_payloads: dict[str, str] | None = None,
    oracle_payload: str | None = None,
    outcome_labels: Sequence[str] = (),
    repeat_idx: int = 0,
    overwrite: bool = False,
    env_reconstructor: Callable[[Path], object] | None = None,
    network: NetworkMode = "no-network",
) -> list[RewardRecord]:
    """Run the ablation grid for one held-out WorkRecord and score every rung.

    Emits the rung task dirs (mem-apg.2 adapter), injects each rung's memory,
    runs the agent, harvests a RunTrace, and scores it against `held_errors`
    (mem-apg.3a). Returns one `RewardRecord` per non-deferred rung, keyed by
    (work_id, rung, repeat_idx).

    `builtin` / `ours+builtin` rungs are SKIPPED (owned by mem-whi); requesting
    them is not an error. `held_errors` must be non-empty -- the held-out set is
    'beads with >=1 trace_error', and the scorer rejects an empty held set.

    Two caller preconditions (this driver does not enforce them):
    - `ours_payloads` (and `vector_payloads`, the recall-ladder rung-2 semantic-arm
      retrieval) MUST already be bounded to the task's D6 LOO boundary by the caller
      (e.g. via `validity.loo_bounded`, or the semantic arm's per-trial scope);
      `run_grid` injects them verbatim and does not re-filter by `loo_boundary`.
    - the returned `RewardComponents.rubric_score` is always `None` -- the judge
      (mem-apg.3b) is a separate post-harvest step; a caller wanting the combined
      semantic reward must run the judge over each rung's run output and set
      `rubric_score` before calling `combined_reward`.

    `env_reconstructor`, when given, is called once per emitted task dir (after the
    adapter writes it, before any agent run) to bake in the task's environment --
    e.g. `env_recon.reconstruct_env_for_record` partial-applied to this record. It
    is optional so the StubRunner pipeline (and CI) need no Docker or git checkout."""
    held = list(held_errors)
    if not held:
        raise ValueError("run_grid needs at least one held error to score against")
    # A typo'd rung must fail HERE, before any task dir is emitted or agent run
    # spent -- not mid-sweep when the loop first reaches it.
    validate_rungs(rungs)

    source = AblationSource(rungs=rungs)
    adapter = WorkRecordLadderAdapter(
        record, output_dir, source=source, overwrite=overwrite, network=network
    )
    # The adapter returns the task dirs in rung order, so the driver locates them
    # by the adapter's own naming rather than re-deriving the slug (no coupling to
    # its private `_safe`).
    task_dirs = adapter.run()
    if env_reconstructor is not None:
        for task_dir in task_dirs:
            env_reconstructor(task_dir)

    work_id = str(record["work_id"])
    records: list[RewardRecord] = []
    for rung, task_dir in zip(rungs, task_dirs, strict=True):
        try:
            inject_rung_memory(
                task_dir,
                rung,
                held_errors=held,
                vector_payloads=vector_payloads,
                ours_payloads=ours_payloads,
                oracle_payload=oracle_payload,
                outcome_labels=outcome_labels,
            )
        except DeferredRungError:
            # builtin / ours+builtin are owned by mem-whi -- skip, do not score.
            continue

        run_trace = runner.run(task_dir)
        components = score_run(held, run_trace)
        records.append(
            RewardRecord(
                work_id=work_id,
                rung=rung,
                repeat_idx=repeat_idx,
                components=components,
            )
        )
    return records
