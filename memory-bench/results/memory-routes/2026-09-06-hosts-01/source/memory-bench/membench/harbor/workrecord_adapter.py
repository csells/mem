"""Emit a held-out WorkRecord as an ablation information-ladder of Harbor tasks.

One task dir per ablation rung (none / ours / builtin / ours+builtin / oracle). The
task the agent attempts is built ONLY from the record's label-free `title` — never
its `metadata` (which carries outcome signals like `evidence.commit_sha`) and never
its `outcome`. Every agent-readable file is checked with `assert_no_outcome_leak`
before write, so the D6 / leak invariant holds mechanically on the task-construction
path (mem-apg.1 finding C1).

This bead (mem-apg.2) emits the task skeleton + the per-rung information spec; the
per-rung memory CONTENT injection and the scoring are mem-apg.3. Env reconstruction
(merged-diff) is demoted to opportunistic and is not built here (ARCHITECTURE D17).
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import toml

from membench.grading import AblationSource, assert_no_outcome_leak, outcome_labels
from membench.harbor.task_env import NetworkMode, environment_network
from membench.schemas.work_record import WorkRecord
from membench.validity import query_from_record

# The stateless baseline rung surfaces no prior-session memory; every other rung
# does. This must stay in sync with `ablation.DEFAULT_RUNGS[0]` — if that rung is
# renamed, update this too (the test `test_memory_enabled_rungs_*` is the safety net).
_STATELESS_RUNG = "none"


def _safe(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-" else "-" for c in value.lower())


def _instruction_md(record: WorkRecord, rung: str) -> str:
    parts = [
        f"# {record.work_id}",
        "",
        record.title,
        "",
        "Complete the work described above.",
        "",
    ]
    if rung != _STATELESS_RUNG:
        parts += [
            "## Memory",
            "",
            f"Prior-session memory is available (information rung: `{rung}`). "
            "Consult relevant prior lessons before acting.",
            "",
        ]
    return "\n".join(parts)


class WorkRecordLadderAdapter:
    """Generate Harbor task dirs for one WorkRecord, one per ablation rung."""

    def __init__(
        self,
        record: Mapping[str, Any] | WorkRecord,
        output_dir: str | Path,
        *,
        source: AblationSource | None = None,
        overwrite: bool = False,
        network: NetworkMode = "no-network",
    ) -> None:
        # Snapshot (via validation or a deep copy) so a caller mutating its input
        # between construction and run() cannot change what the leak guard sees vs
        # what gets written.
        self.record: WorkRecord = (
            record.model_copy(deep=True)
            if isinstance(record, WorkRecord)
            else WorkRecord.model_validate(record)
        )
        self.output_dir = Path(output_dir)
        self.source = source or AblationSource()
        self.overwrite = overwrite
        # Offline by default (deterministic, leak-safe scoring). The real-exec spike
        # must set "allowlist": Harbor's installed `claude-code` agent fetches its CLI
        # over the network (native installer on Debian) and most rigs' build/test step
        # needs its package registry — but the landed gold fix is publicly fetchable
        # from the rig's GitHub repo, so full egress would leak the answer into every
        # arm (mem-yeoz). "public" stays available only as an explicit escape hatch.
        self.network: NetworkMode = network

    def _task_toml(self, name: str, rung: str, loo_boundary: str) -> str:
        config = {
            "schema_version": "1.1",
            "task": {
                "name": name,
                "description": f"{self.record.title} [{rung}]",
            },
            "metadata": {
                "work_id": self.record.work_id,
                "rig": self.record.rig,
                "rung": rung,
                # The D6 LOO boundary (the record's own `started`) — a timestamp,
                # not an outcome, so it is label-free and rides into the task.
                "loo_boundary": loo_boundary,
                "source": "workrecord",
            },
            "environment": environment_network(self.network),
            "verifier": {"timeout_sec": 300.0},
            "agent": {"timeout_sec": 600.0},
        }
        return toml.dumps(config)

    def run(self) -> list[Path]:
        """Write one task dir per rung; returns the dirs created.

        Every rung's files are built and leak-checked BEFORE any are written, so a
        leak (or a pre-existing dir) in any rung aborts the whole emission with no
        partial output on disk."""
        # These three contracts still take Mapping[str, Any] (validity.py's LOO
        # module and grading's leak guard are unchanged) — dumped once and reused.
        record_dict = self.record.model_dump()
        design = self.source.design(record_dict)
        # The boundary is the record's own `started` (falls back to `created`);
        # raises if neither exists, rather than inventing a leak-unsafe default.
        loo_boundary = query_from_record(record_dict).started
        labels = outcome_labels(record_dict)

        planned: list[tuple[Path, str, str]] = []  # (task_dir, instruction, task_toml)
        for rung in design.rungs:
            slug = f"{_safe(self.record.work_id)}-{_safe(rung)}"
            task_dir = self.output_dir / slug
            if task_dir.exists() and not self.overwrite:
                raise FileExistsError(f"Task dir already exists: {task_dir} (pass overwrite=True)")
            instruction = _instruction_md(self.record, rung)
            task_toml = self._task_toml(f"membench-wr/{slug}", rung, loo_boundary)
            # Mechanical leak guard over every agent-readable file BEFORE any write.
            assert_no_outcome_leak({"instruction.md": instruction, "task.toml": task_toml}, labels)
            planned.append((task_dir, instruction, task_toml))

        created: list[Path] = []
        for task_dir, instruction, task_toml in planned:
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "task.toml").write_text(task_toml, encoding="utf-8")
            (task_dir / "instruction.md").write_text(instruction, encoding="utf-8")
            created.append(task_dir)
        return created
