"""Emit a benchmark sequence as Harbor tasks, one task per (step x condition).

The condition is materialized into the task the way a real agent would experience
it:
  - no_memory       → instruction only; no memory tooling.
  - oracle_memory   → the exact relevant memory injected inline in instruction.md.
  - memory_enabled  → memory-tool instructions + a mounted ~/memory dir that
                      persists across the sequence's steps.

The verifier (`tests/test.sh`) writes a reward in [0,1] to
`/logs/verifier/reward.txt` (Harbor's canonical reward path).
"""

from pathlib import Path

import toml

from membench.harbor.task_env import environment_network
from membench.schemas.conditions import Condition
from membench.schemas.sequence import BenchmarkSequence, SequenceStep

REWARD_TEXT_PATH = "/logs/verifier/reward.txt"

_DOCKERFILE = """\
FROM python:3.12-slim
WORKDIR /app
RUN mkdir -p /root/memory
"""


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-" else "-" for c in s.lower())


def _task_name(seq_id: str, condition: Condition, step_id: str) -> str:
    return f"membench/{_safe(seq_id)}-{condition.value.replace('_', '-')}-{_safe(step_id)}"


def _instruction_md(step: SequenceStep, condition: Condition, oracle_pool: dict[str, str]) -> str:
    parts = [f"# {step.step_id}", "", step.user_request, ""]
    if condition is Condition.ORACLE_MEMORY and step.expected_memory_reads:
        parts += ["## Provided context (oracle memory)", ""]
        for mid in step.expected_memory_reads:
            if mid in oracle_pool:
                parts += [f"- **{mid}**: {oracle_pool[mid]}"]
        parts.append("")
    if condition is Condition.MEMORY_ENABLED:
        parts += [
            "## Memory",
            "",
            "Prior-session memory persists under `~/memory/`. Read relevant notes "
            "with `grep`/`cat` before acting, and record durable lessons by writing "
            "`~/memory/<id>.md`.",
            "",
        ]
    return "\n".join(parts)


def _test_sh(step: SequenceStep) -> str:
    """A minimal real verifier: reward = fraction of outcome checks whose marker is
    present in /app/answer.txt; written to the canonical reward path."""
    check_ids = [c.check_id for c in step.outcome_checks] or ["_present"]
    checks_literal = " ".join(check_ids)
    return f"""\
#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$(dirname {REWARD_TEXT_PATH})"
answer="/app/answer.txt"
checks=({checks_literal})
total=${{#checks[@]}}
passed=0
if [[ -f "$answer" ]]; then
  for c in "${{checks[@]}}"; do
    if grep -q "$c" "$answer"; then passed=$((passed+1)); fi
  done
fi
awk -v p="$passed" -v t="$total" \
  'BEGIN {{ if (t == 0) print "0.0"; else printf "%.4f\\n", p / t }}' \
  > {REWARD_TEXT_PATH}
"""


def _solve_sh(step: SequenceStep) -> str:
    """Oracle solution: emit every check marker so the verifier scores 1.0."""
    markers = " ".join(c.check_id for c in step.outcome_checks) or "_present"
    return f"""\
#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' {markers} > /app/answer.txt
"""


class SequenceAdapter:
    """Generate Harbor task dirs from a `BenchmarkSequence`."""

    def __init__(
        self,
        sequence: BenchmarkSequence,
        output_dir: str | Path,
        conditions: list[Condition] | None = None,
        overwrite: bool = False,
    ) -> None:
        self.sequence = sequence
        self.output_dir = Path(output_dir)
        self.conditions = conditions or list(Condition)
        self.overwrite = overwrite

    def _oracle_pool(self) -> dict[str, str]:
        pool: dict[str, str] = {}
        for step in self.sequence.steps:
            pool.update(step.expected_memory_writes)
        return pool

    def _task_toml(self, name: str, step: SequenceStep, condition: Condition) -> str:
        config = {
            "schema_version": "1.1",
            "task": {
                "name": name,
                "description": f"{self.sequence.title} — {step.step_id} [{condition.value}]",
            },
            "metadata": {
                "sequence_id": self.sequence.sequence_id,
                "step_id": step.step_id,
                "condition": condition.value,
                "expected_memory_reads": step.expected_memory_reads,
                "expected_memory_writes": sorted(step.expected_memory_writes),
            },
            # Internet is a task-level property, not a condition-level one: the only
            # thing that may vary across conditions is memory, else the oracle ceiling
            # is contaminated by web lookups. Off by default in the skeleton (tools are
            # local fs/git; memory persists via a mount).
            "environment": environment_network("no-network"),
            "verifier": {"timeout_sec": 300.0},
            "agent": {"timeout_sec": 600.0},
        }
        return toml.dumps(config)

    def run(self) -> list[Path]:
        """Write all task dirs; returns the list of task dirs created."""
        oracle_pool = self._oracle_pool()
        created: list[Path] = []
        for condition in self.conditions:
            for step in self.sequence.steps:
                name = _task_name(self.sequence.sequence_id, condition, step.step_id)
                task_dir = self.output_dir / name.split("/", 1)[1]
                if task_dir.exists() and not self.overwrite:
                    raise FileExistsError(
                        f"Task dir already exists: {task_dir} (pass overwrite=True)"
                    )
                (task_dir / "environment").mkdir(parents=True, exist_ok=True)
                (task_dir / "tests").mkdir(parents=True, exist_ok=True)
                (task_dir / "solution").mkdir(parents=True, exist_ok=True)

                (task_dir / "task.toml").write_text(
                    self._task_toml(name, step, condition), encoding="utf-8"
                )
                (task_dir / "instruction.md").write_text(
                    _instruction_md(step, condition, oracle_pool), encoding="utf-8"
                )
                (task_dir / "environment" / "Dockerfile").write_text(_DOCKERFILE, encoding="utf-8")
                (task_dir / "tests" / "test.sh").write_text(_test_sh(step), encoding="utf-8")
                (task_dir / "solution" / "solve.sh").write_text(_solve_sh(step), encoding="utf-8")
                created.append(task_dir)
        return created
