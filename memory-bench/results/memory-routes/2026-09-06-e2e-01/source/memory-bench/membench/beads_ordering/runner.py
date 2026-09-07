from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from membench.beads_ordering.client import BeadsExperimentClient, candidate_parity
from membench.beads_ordering.models import (
    BM25FConfig,
    ExperimentMode,
    FrozenCorpus,
    OrderingArm,
    OrderingRunResult,
    OrderingTask,
    ToolLogEntry,
)
from membench.beads_ordering.scoring import score_agent_run
from membench.beads_ordering.tool import TOOL_CONFIG_ENV, ToolConfig
from membench.runner.headless_agent import (
    HeadlessAgentError,
    HeadlessClaudeAgent,
    RecordingRunner,
    a_paid_run_carries_the_metered_api_key,
    a_paid_run_needs_a_model,
    resolve_cli_version,
    resolve_model,
    seed_config_dir,
)
from membench.runner.realagent_probe import PROBE_SETTINGS
from membench.runner.sandbox import paid_sandbox
from membench.runtime import StepContext
from membench.schemas.sequence import SequenceStep

PAGE_SIZES: tuple[int | str, ...] = (3, 5, 10, 20, 50, "all")
STRUCTURAL_ARMS: tuple[OrderingArm, ...] = (
    OrderingArm.INDEGREE,
    OrderingArm.OUTDEGREE,
    OrderingArm.PAGERANK,
    OrderingArm.REVERSE_PAGERANK,
    OrderingArm.HITS_AUTHORITY,
    OrderingArm.HITS_HUB,
)
ARMS: tuple[OrderingArm, ...] = (OrderingArm.KEY, *STRUCTURAL_ARMS, OrderingArm.BM25F)
CONTROL_ARMS: tuple[OrderingArm, ...] = (
    OrderingArm.CONTROL_AUTOMATIC,
    OrderingArm.CONTROL_SEMANTIC,
    OrderingArm.CONTROL_STRATEGY,
    OrderingArm.CONTROL_RAW,
)


class OrderingExperimentError(RuntimeError):
    pass


@dataclass(frozen=True)
class RankTruth:
    total_matched: int
    candidate_digest: str
    ranks: Mapping[OrderingArm, Mapping[str, int]]


def git_sha(repo: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise OrderingExperimentError(f"cannot resolve git SHA for {repo}: {completed.stderr}")
    return completed.stdout.strip()


def git_dirty(repo: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise OrderingExperimentError(f"cannot inspect git state for {repo}: {completed.stderr}")
    return bool(completed.stdout.strip())


def git_diff_sha256(repo: Path) -> str:
    completed = subprocess.run(
        ["git", "diff", "--binary", "HEAD", "--", "."],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode(errors="replace")
        raise OrderingExperimentError(f"cannot hash git diff for {repo}: {stderr}")
    return hashlib.sha256(completed.stdout).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def corpus_digest(corpus: FrozenCorpus) -> str:
    return hashlib.sha256(corpus.model_dump_json().encode()).hexdigest()


def seed_beads_workspace(
    *,
    corpus: FrozenCorpus,
    corpus_size: int,
    beads_bin: str,
    workspace: Path,
    control_task_id: str | None = None,
) -> None:
    """Materialize one nested corpus using Beads' memory import surface."""

    stored_values = tuple(
        (memory.key, memory.stored_value(corpus_size, control_task_id=control_task_id))
        for memory in corpus.memories[:corpus_size]
    )
    expected = hashlib.sha256(
        "\n".join(f"{key}\0{value}" for key, value in stored_values).encode()
    ).hexdigest()
    legacy_expected = hashlib.sha256(
        "\n".join(
            memory.model_dump_json(exclude={"control_ranks_by_task"})
            for memory in corpus.memories[:corpus_size]
        ).encode()
    ).hexdigest()
    marker = workspace / ".membench-corpus.json"
    if marker.exists():
        raw = json.loads(marker.read_text(encoding="utf-8"))
        if raw == {
            "corpus_size": corpus_size,
            "fixture_digest": expected,
            "control_task_id": control_task_id,
        }:
            return
        if control_task_id is None and raw == {
            "corpus_size": corpus_size,
            "fixture_digest": legacy_expected,
        }:
            return
        raise OrderingExperimentError(
            f"{workspace} contains a different frozen corpus; choose a new workspace root"
        )
    if workspace.exists() and any(workspace.iterdir()):
        raise OrderingExperimentError(f"refusing to seed non-empty workspace {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)
    commands = (
        ["git", "init", "-q"],
        [
            beads_bin,
            "init",
            "--non-interactive",
            "--skip-agents",
            "--skip-hooks",
            "--quiet",
        ],
    )
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        if completed.returncode != 0:
            raise OrderingExperimentError(
                f"seed command failed ({' '.join(command)}): {completed.stderr.strip()}"
            )
    jsonl = "\n".join(
        json.dumps(
            {
                "_type": "memory",
                "key": memory.key,
                "value": stored_value,
            }
        )
        for memory, (_, stored_value) in zip(
            corpus.memories[:corpus_size], stored_values, strict=True
        )
    )
    completed = subprocess.run(
        [beads_bin, "import", "-", "--quiet"],
        cwd=workspace,
        input=jsonl + "\n",
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0:
        raise OrderingExperimentError(f"bd import failed: {completed.stderr.strip()}")
    marker.write_text(
        json.dumps(
            {
                "corpus_size": corpus_size,
                "fixture_digest": expected,
                "control_task_id": control_task_id,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def task_workspace(root: Path, task: OrderingTask, *, task_scoped: bool) -> Path:
    """Choose a stable workspace; control ranks require one corpus image per task."""

    if task_scoped:
        return root / "tasks" / task.task_id
    return root / f"corpus-{task.corpus_size}"


def validate_rank_truth(
    *,
    task: OrderingTask,
    workspace: Path,
    beads_bin: str,
    bm25f: BM25FConfig,
    arms: Sequence[OrderingArm] = ARMS,
) -> RankTruth:
    pages: dict[OrderingArm, dict[str, Any]] = {}
    ranks: dict[OrderingArm, dict[str, int]] = {}
    selected_arms = tuple(dict.fromkeys((OrderingArm.KEY, *arms)))
    for arm in selected_arms:
        discovery = BeadsExperimentClient(
            beads_bin=beads_bin,
            workspace=str(workspace),
            page_size="all",
            bm25f=bm25f,
        ).exhaust(task.query, arm)
        payload = discovery.pages[0].model_dump(mode="json")
        pages[arm] = payload
        ranks[arm] = {item.id: item.rank for item in discovery.items}
    parity = candidate_parity(pages)
    labelled = {
        task.primary_relevant,
        *task.acceptable_entry_points,
        *task.distractors,
    }
    if set(parity["candidate_ids"]) != labelled:
        raise OrderingExperimentError(f"frozen labels do not equal matches for {task.task_id}")
    return RankTruth(
        total_matched=int(parity["total_matched"]),
        candidate_digest=str(parity["candidate_digest"]),
        ranks=ranks,
    )


def agent_request(task: OrderingTask, mode: ExperimentMode, *, max_tool_calls: int) -> str:
    if mode is ExperimentMode.SEARCH_ONLY:
        navigation = (
            " Reference traversal is disabled in this run; recall only Memories already shown "
            "in discovery results."
        )
    elif mode is ExperimentMode.DEPTH_FIRST:
        navigation = (
            " When a recalled Memory lists references, follow those references depth-first "
            "before answering, within the same budget."
        )
    else:
        navigation = (
            " You may follow references from recalled Memories naturally when they look useful."
        )
    return (
        f"{task.instruction}\n\n"
        "Memory discovery is available only through these commands:\n"
        "  ./memory-tool search\n"
        "  ./memory-tool continue\n"
        "  ./memory-tool recall '<Memory ID>'\n"
        "Search exactly once, inspect the compact results, and naturally decide whether to "
        "recall a Memory, request the continuation, or stop. Do not paginate after you believe "
        "you have a "
        f"useful result. You have at most {max_tool_calls} retrieval-tool calls.{navigation} "
        "Do not inspect the wrapper or its configuration. You may explain the decision briefly, "
        "but end with exactly one line in the form `DECISION: <exact configuration token>`. Put "
        "only the selected current token on that line."
    )


def _write_launcher(sandbox: Path) -> Path:
    launcher = sandbox / "memory-tool"
    launcher.write_text(
        "#!/usr/bin/env python3\n"
        "from membench.beads_ordering.tool import main\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    return launcher


def _load_tool_logs(path: Path) -> list[ToolLogEntry]:
    if not path.exists():
        return []
    return [
        ToolLogEntry.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _first_acceptable_rank(task: OrderingTask, ranks: Mapping[str, int]) -> int | None:
    values = [ranks[memory_id] for memory_id in task.acceptable_entry_points if memory_id in ranks]
    return min(values) if values else None


def run_agent_cell(
    *,
    task: OrderingTask,
    arm: OrderingArm,
    page_size: int | str,
    mode: ExperimentMode,
    repeat: int,
    workspace: Path,
    beads_bin: str,
    bm25f: BM25FConfig,
    rank_truth: RankTruth,
    model: str,
    cli_version: str,
    mem_sha: str,
    mem_dirty: bool,
    mem_git_diff_sha256: str,
    beads_sha: str,
    beads_dirty: bool,
    beads_git_diff_sha256: str,
    beads_bin_sha256: str,
    structural_order_source_git_sha: str,
    artifacts_dir: Path,
    claude_credentials: Path | None = None,
    max_tool_calls: int = 12,
) -> OrderingRunResult:
    resolved_model = resolve_model(model)
    if not resolved_model:
        raise OrderingExperimentError("a real run requires an explicitly pinned agent model")
    run_id = f"{task.task_id}:{mode.value}:{arm.value}:p{page_size}:r{repeat}"
    run_dir = artifacts_dir / "runs" / run_id.replace(":", "__")
    run_dir.mkdir(parents=True, exist_ok=False)
    raw_stream = ""
    final_answer = ""
    input_tokens = 0
    output_tokens = 0
    failure: str | None = None
    start_ns = time.monotonic_ns()
    with (
        paid_sandbox("beads-ordering-") as sandbox,
        tempfile.TemporaryDirectory(prefix="beads-ordering-config-") as config_raw,
        tempfile.TemporaryDirectory(prefix="beads-ordering-tool-") as tool_raw,
    ):
        _write_launcher(sandbox)
        config_dir = Path(config_raw)
        seed_config_dir(config_dir, PROBE_SETTINGS)
        if claude_credentials is not None:
            destination = config_dir / ".credentials.json"
            shutil.copyfile(claude_credentials, destination)
            destination.chmod(0o600)
        tool_dir = Path(tool_raw)
        tool_log = run_dir / "retrieval.jsonl"
        tool_config = ToolConfig(
            beads_bin=beads_bin,
            workspace=str(workspace),
            query=task.query,
            arm=arm,
            page_size=page_size,
            bm25f=bm25f,
            log_path=str(tool_log),
            agent_started_monotonic_ns=start_ns,
            max_tool_calls=max_tool_calls,
            mode=mode,
        )
        config_path = tool_dir / "config.json"
        config_path.write_text(tool_config.model_dump_json(indent=2), encoding="utf-8")
        python_root = str(Path(__file__).resolve().parents[2])
        inherited_pythonpath = os.environ.get("PYTHONPATH", "")
        env = {
            "CLAUDE_CONFIG_DIR": str(config_dir),
            TOOL_CONFIG_ENV: str(config_path),
            "PYTHONPATH": (
                python_root
                if not inherited_pythonpath
                else f"{python_root}{os.pathsep}{inherited_pythonpath}"
            ),
        }
        step = SequenceStep(
            step_id=task.task_id,
            user_request=agent_request(task, mode, max_tool_calls=max_tool_calls),
            available_tools=["Bash"],
        )
        recorder = RecordingRunner(subprocess.run)
        agent = HeadlessClaudeAgent(
            model=resolved_model,
            runner=recorder,
            cwd=str(sandbox),
            env=env,
        )
        try:
            result = agent.run_step(
                step,
                {},
                StepContext(trial_id=run_id, session_id=run_id, step_id=task.task_id),
            )
            raw_stream = result.raw_stream
            final_answer = result.final_answer
            input_tokens = result.input_tokens
            output_tokens = result.output_tokens
        except HeadlessAgentError as exc:
            failure = str(exc)
            raw_stream = recorder.streams[-1] if recorder.streams else ""
    end_to_end_ms = (time.monotonic_ns() - start_ns) / 1_000_000
    (run_dir / "agent.stream.jsonl").write_text(raw_stream, encoding="utf-8")
    logs = _load_tool_logs(run_dir / "retrieval.jsonl")
    arm_ranks = rank_truth.ranks[arm]
    effective_page_size = rank_truth.total_matched if page_size == "all" else int(page_size)
    scored = score_agent_run(
        task_id=task.task_id,
        query=task.query,
        corpus_size=task.corpus_size,
        arm=arm,
        mode=mode,
        repeat=repeat,
        page_size_label=str(page_size),
        primary_id=task.primary_relevant,
        acceptable_ids=set(task.acceptable_entry_points),
        expected_facts=list(task.expected_facts),
        forbidden_facts=list(task.forbidden_facts),
        final_answer=final_answer,
        logs=logs,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        end_to_end_ms=end_to_end_ms,
        primary_rank=arm_ranks[task.primary_relevant],
        acceptable_rank=_first_acceptable_rank(task, arm_ranks),
        page_size=max(1, effective_page_size),
        total_matched=rank_truth.total_matched,
        failure=failure,
        mem_git_sha=mem_sha,
        mem_git_dirty=mem_dirty,
        mem_git_diff_sha256=mem_git_diff_sha256,
        beads_git_sha=beads_sha,
        beads_git_dirty=beads_dirty,
        beads_git_diff_sha256=beads_git_diff_sha256,
        beads_bin_sha256=beads_bin_sha256,
        structural_order_source_git_sha=structural_order_source_git_sha,
        agent_model=resolved_model,
        agent_cli_version=cli_version,
    )
    (run_dir / "result.json").write_text(scored.model_dump_json(indent=2) + "\n", "utf-8")
    return scored


def validate_paid_run(model: str, *, claude_credentials: Path | None = None) -> tuple[str, str]:
    if a_paid_run_needs_a_model(model, dry_run=False):
        raise OrderingExperimentError("refusing an unpinned paid run; pass --model")
    if a_paid_run_carries_the_metered_api_key(dry_run=False):
        raise OrderingExperimentError(
            "refusing a paid run while ANTHROPIC_API_KEY is set; use OAuth subscription auth"
        )
    if claude_credentials is not None and not claude_credentials.is_file():
        raise OrderingExperimentError(
            f"Claude credentials file does not exist: {claude_credentials}"
        )
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") and claude_credentials is None:
        raise OrderingExperimentError(
            "a real run needs CLAUDE_CODE_OAUTH_TOKEN or --claude-credentials; refusing before "
            "creating unauthenticated run artifacts"
        )
    return resolve_model(model), resolve_cli_version()


def write_raw_results(path: Path, rows: Sequence[OrderingRunResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8")
