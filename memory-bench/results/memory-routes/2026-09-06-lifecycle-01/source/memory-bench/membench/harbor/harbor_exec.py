"""Real Harbor execution + ATIF trajectory harvest for HarborRunner (mem-apg.3.1).

`grid.py`'s harvesting boundary is a `RunTranscript` -- a mapping of
``{output, files_read, files_written}`` that `harvest_run_trace` turns into a
`RunTrace`. This module is the PRODUCTION source of that transcript: it runs one
local task through ``harbor run`` on the Claude OAuth subscription (D16, not a
paid-API cost fork) and PROJECTS the resulting ATIF trajectory (RFC-0001,
``harbor.models.trajectories``) onto that shape.

The projection is needed because Harbor emits an ATIF `Trajectory`, NOT the
transcript shape grid.py consumes, and carries no ``files_read``/``files_written``
keys (the original ``_default_exec`` assumed both -- it was documented-but-wrong, see
mem-apg.3.1):

- ``files_read`` / ``files_written`` are DERIVED from the agent's structured
  file-tool calls (``Read`` -> read; ``Write``/``Edit``/``MultiEdit``/``NotebookEdit``
  -> written). ``Bash``/``Grep``/``Glob`` also touch files but not via a structured
  path argument, so attributing them would mean guessing from shell text -- out of
  scope, kept deterministic rather than lenient.
- ``output`` (what the trace_error extractor parses) is the union of tool OBSERVATION
  contents -- the build/test/lint stdout the agent actually saw -- in step order, NOT
  the agent's prose.

Container file paths are absolute (``/app/...``); the scorer's ``_same_file`` does a
path-suffix match, so they align with repo-relative held paths WITHOUT normalization
here. ``test_projected_files_suffix_match_repo_relative_held_path`` pins that contract.

The pure projection (`project_trajectory`) is unit-tested against a synthesized ATIF
fixture that is first validated by Harbor's own model. A SUCCESSFUL `run_harbor_job`
needs Docker + a real subscription run and is not exercised in CI; its spawn-FAILURE
ladder is, against a stubbed `subprocess.run` (a spawn that never happens needs neither).
"""

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from membench.spawn import Runner, run_checked

# The transcript shape `grid.harvest_run_trace` consumes. A plain dict; defined as the
# return contract here so harbor_exec does not import from grid (grid imports this).
RunTranscript = dict[str, Any]

# Claude Code structured file tools -> (path-bearing argument, "read" | "written").
# Only tools whose file target is an explicit argument are counted; see module docstring
# for why Bash/Grep/Glob are excluded.
_FILE_TOOLS: Mapping[str, tuple[str, str]] = {
    "Read": ("file_path", "read"),
    "Write": ("file_path", "written"),
    "Edit": ("file_path", "written"),
    "MultiEdit": ("file_path", "written"),
    "NotebookEdit": ("notebook_path", "written"),
}

# The agent that drives Claude Code under the OAuth subscription (harbor adapter name).
DEFAULT_AGENT = "claude-code"


def _as_trajectory_dict(trajectory: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a raw trajectory against Harbor's strict ATIF model and return it as a
    plain dict. A malformed trajectory (extra keys, non-sequential step_id, missing
    required fields) raises here -- a bad harvest is never silently a clean trace.

    Validation is REQUIRED, not optional: if Harbor is not importable the harvest
    cannot be trusted, so we fail rather than parse a best-effort shape."""
    from harbor.models.trajectories import Trajectory

    validated = Trajectory.model_validate(dict(trajectory)).to_json_dict(exclude_none=True)
    return cast(dict[str, Any], validated)


def _content_text(content: Any) -> str:
    """Flatten an ATIF content value (str | list[ContentPart] | None) to text.

    A ``ContentPart`` array (multimodal, ATIF-v1.6) contributes only its ``text``
    parts; image parts carry no parseable build output and are dropped."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = [
        part.get("text", "")
        for part in content
        if isinstance(part, Mapping) and part.get("type") == "text"
    ]
    return "\n".join(p for p in parts if p)


def collect_output(trajectory: Mapping[str, Any]) -> str:
    """The combined tool-observation output the trace_error extractor parses.

    Joins every observation result's content across all steps in step order. Agent
    prose messages are excluded -- the parseable compiler/test output lives in the
    tool observations, and including the prose would risk double-counting errors the
    agent quotes back."""
    traj = _as_trajectory_dict(trajectory)
    chunks: list[str] = []
    for step in traj["steps"]:
        observation = step.get("observation")
        if not observation:
            continue
        for result in observation.get("results", ()):
            text = _content_text(result.get("content"))
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _accumulate_file(tool_name: Any, args: Any, read: set[str], written: set[str]) -> None:
    """Bucket one file-tool call into read/written by `_FILE_TOOLS`. Shared by the ATIF
    and Claude-stream projections so the tool->bucket policy lives in one place."""
    spec = _FILE_TOOLS.get(tool_name if isinstance(tool_name, str) else "")
    if spec is None:
        return
    arg_name, bucket = spec
    path = args.get(arg_name) if isinstance(args, Mapping) else None
    if isinstance(path, str) and path:
        (read if bucket == "read" else written).add(path)


def derive_files_touched(
    trajectory: Mapping[str, Any],
) -> tuple[frozenset[str], frozenset[str]]:
    """(files_read, files_written) derived from the agent's structured file-tool calls.

    See module docstring for the tool->bucket mapping and why shell-driven file access
    is not attributed."""
    traj = _as_trajectory_dict(trajectory)
    read: set[str] = set()
    written: set[str] = set()
    for step in traj["steps"]:
        for call in step.get("tool_calls") or ():
            _accumulate_file(call.get("function_name"), call.get("arguments"), read, written)
    return frozenset(read), frozenset(written)


def project_trajectory(trajectory: Mapping[str, Any]) -> RunTranscript:
    """Project one ATIF trajectory onto the `RunTranscript` grid.py harvests.

    ``files_read``/``files_written`` are sorted for a deterministic transcript."""
    read, written = derive_files_touched(trajectory)
    return {
        "output": collect_output(trajectory),
        "files_read": sorted(read),
        "files_written": sorted(written),
    }


def project_claude_stream(stdout: str) -> RunTranscript:
    """Project a Claude Code stream-json transcript (the agent's stdout, ``claude-code.txt``)
    onto a `RunTranscript`. The robust harvest source when Harbor SKIPS its ATIF
    conversion -- it only writes ``trajectory.json`` when ``agent_result.is_empty()``
    (trial.py ``_maybe_populate_agent_context``), so a normal completed run leaves no
    trajectory but always leaves this stdout.

    Same projection as ATIF, different source shape: ``tool_use`` blocks in ``assistant``
    messages give files_read/written (same `_FILE_TOOLS` mapping); ``tool_result`` blocks
    in ``user`` messages give the observation output the trace_error extractor parses.
    Lines that are not JSON (or carry no message content) are skipped, not fatal."""
    read: set[str] = set()
    written: set[str] = set()
    chunks: list[str] = []
    for line in stdout.splitlines():
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
            if not isinstance(block, Mapping):
                continue
            if block.get("type") == "tool_use":
                _accumulate_file(block.get("name"), block.get("input"), read, written)
            elif block.get("type") == "tool_result":
                text = _content_text(block.get("content"))
                if text:
                    chunks.append(text)
    return {
        "output": "\n".join(chunks),
        "files_read": sorted(read),
        "files_written": sorted(written),
    }


def build_job_config(
    task_dir: Path,
    *,
    job_name: str,
    jobs_dir: Path,
    model: str | None = None,
    agent: str = DEFAULT_AGENT,
    agent_version: str | None = None,
    agent_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """The minimal Harbor `JobConfig` to run one local task with the OAuth agent.

    The OAuth token is NOT set in ``agent.env``: Harbor does not expand ``${VAR}`` and
    merges ``agent.env`` OVER the claude-code adapter's own env (base.py ``_exec`` does
    ``merged_env.update(extra_env)``), so a ``${CLAUDE_CODE_OAUTH_TOKEN}`` reference here
    would overwrite the real token with the literal string -> '401 Invalid bearer token'.
    Instead the adapter reads ``CLAUDE_CODE_OAUTH_TOKEN`` from the HARBOR PROCESS env
    (claude_code.py ``run``), so the caller MUST export it before invoking `harbor_exec`
    (e.g. `run_real_spike` sets ``os.environ`` from the account's credentials). Leaving
    ``agent.env`` unset keeps no secret on disk and lets the real token through unmodified.
    ``ANTHROPIC_API_KEY`` stays unset so Claude Code uses subscription auth (D16).

    ``agent_env`` is the ONE sanctioned use of ``agent.env``: LITERAL, non-secret vars the
    probe path relocates ``CLAUDE_CONFIG_DIR`` with, so the agent's native-memory block
    reads the injected file (`agent_memory`). It is merged over the adapter env exactly
    like the token warning above, so the OAuth token key is REFUSED here — it must keep
    flowing from the process env. Absent ``agent_env``, ``agent.env`` stays unset.

    ``agent_version`` pins the in-container CLI install (harbor's installed-agent
    ``version`` constructor kwarg, reached via ``AgentConfig.kwargs``); without it
    every container installs whatever is latest — a silent instrument drift across
    runs executed on different days (mem-p3w)."""
    agent_cfg: dict[str, Any] = {"name": agent}
    if model is not None:
        agent_cfg["model_name"] = model
    if agent_version is not None:
        agent_cfg["kwargs"] = {"version": agent_version}
    if agent_env:
        if "CLAUDE_CODE_OAUTH_TOKEN" in agent_env:
            raise ValueError(
                "agent_env must not carry CLAUDE_CODE_OAUTH_TOKEN: agent.env is merged OVER "
                "the adapter's real token, so setting it here clobbers auth -> 401. The token "
                "flows from the harbor process env; keep it out of agent.env."
            )
        agent_cfg["env"] = dict(agent_env)
    return {
        "job_name": job_name,
        "jobs_dir": str(jobs_dir),
        "tasks": [{"path": str(task_dir)}],
        "agents": [agent_cfg],
        "environment": {"type": "docker"},
        # The reconstructed tasks carry no `tests/` -- and we score via trace_error
        # recurrence, not Harbor's reward -- so the verifier is disabled. The agent still
        # runs and the ATIF trajectory is still written (the only output we harvest).
        "verifier": {"disable": True},
    }


def _locate_one(job_dir: Path, pattern: str) -> Path | None:
    """The single file under a one-task/one-attempt job dir matching `pattern`, or None.

    Trial dir names are ``<task>__<shortuuid>`` (unpredictable), so the artifact is
    globbed. More than one is a harvest error (ambiguous); zero returns None so the
    caller can fall back to another source."""
    matches = sorted(job_dir.glob(pattern))
    if len(matches) > 1:
        raise RuntimeError(
            f"expected at most one {pattern} under {job_dir}, found {len(matches)}: "
            f"{[str(m) for m in matches]}"
        )
    return matches[0] if matches else None


def harvest_job_dir(job_dir: Path) -> RunTranscript:
    """Harvest a `RunTranscript` from a finished job dir, preferring Harbor's ATIF
    ``trajectory.json`` and falling back to the Claude Code stream-json stdout.

    Harbor only writes ``trajectory.json`` when ``agent_result.is_empty()`` (it skips the
    ATIF conversion on a normal completed run -- trial.py ``_maybe_populate_agent_context``),
    so the stream-json ``claude-code.txt`` is the reliable source. Neither present is a
    harvest failure, surfaced loudly rather than scored as a clean (no-op) trace."""
    trajectory = _locate_one(job_dir, "*/agent/trajectory.json")
    if trajectory is not None:
        return project_trajectory(json.loads(trajectory.read_text(encoding="utf-8")))
    stream = _locate_one(job_dir, "*/agent/claude-code.txt")
    if stream is not None:
        return project_claude_stream(stream.read_text(encoding="utf-8"))
    raise RuntimeError(
        f"no harvest source under {job_dir}: neither */agent/trajectory.json nor "
        "*/agent/claude-code.txt -- the agent run produced no transcript"
    )


def run_harbor_job(
    task_dir: Path,
    *,
    jobs_dir: Path,
    job_name: str,
    model: str | None = None,
    harbor_bin: str = "harbor",
    timeout_sec: float | None = None,
    agent_version: str | None = None,
    agent_env: Mapping[str, str] | None = None,
    runner: Runner = subprocess.run,
) -> Path:
    """Run one local task through ``harbor run`` and return its job dir.

    Writes the job config under ``jobs_dir``, then shells
    ``harbor run --config <cfg> -q -y``. ``-y`` auto-confirms the host-env-var prompt
    (the OAuth token) that would otherwise block on stdin; ``-q`` suppresses the live
    UI. A non-zero exit raises -- a failed run is never silently a clean trace.

    Every way the spawn itself can fail raises a DIAGNOSED `RuntimeError` too -- a missing
    binary, any other spawn OSError (permissions, ENOEXEC), and a timeout -- via the shared
    `spawn.run_checked` ladder. `HarborRunner` (grid.py) catches nothing on this path, so an
    undiagnosed spawn failure would kill a whole sweep with a raw traceback that says
    nothing about which of the three it was.

    ``agent_env`` relocates ``CLAUDE_CONFIG_DIR`` for the probe path (`build_job_config`)."""
    jobs_dir.mkdir(parents=True, exist_ok=True)
    config = build_job_config(
        task_dir,
        job_name=job_name,
        jobs_dir=jobs_dir,
        model=model,
        agent_version=agent_version,
        agent_env=agent_env,
    )
    config_path = jobs_dir / f"{job_name}.job.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    # Only the SPAWN is guarded. The mkdir/write_text above stay outside, so their
    # OSErrors keep their own identity instead of being misreported as a bad binary --
    # and `harbor_exec`'s "task dir does not exist" guard sits a frame above, untouched.
    run_checked(
        [harbor_bin, "run", "--config", str(config_path), "-q", "-y"],
        what=f"harbor run for {task_dir}",
        not_found_hint="install harbor or pass harbor_bin",
        timeout_s=timeout_sec,
        runner=runner,
    )
    return jobs_dir / job_name


def harbor_exec(
    task_dir: Path,
    *,
    jobs_dir: Path | None = None,
    job_name: str | None = None,
    model: str | None = None,
    harbor_bin: str = "harbor",
    timeout_sec: float | None = None,
) -> RunTranscript:
    """Run the agent on one task dir and harvest its transcript (ATIF, else stream-json).

    The production ``exec_task`` for `HarborRunner`. ``jobs_dir`` defaults to a
    ``_harbor_jobs`` sibling of the task dir; ``job_name`` to the task dir name."""
    if not task_dir.exists():
        raise FileNotFoundError(f"task dir does not exist: {task_dir}")
    jobs_dir = jobs_dir or (task_dir.parent / "_harbor_jobs")
    job_name = job_name or task_dir.name

    job_dir = run_harbor_job(
        task_dir,
        jobs_dir=jobs_dir,
        job_name=job_name,
        model=model,
        harbor_bin=harbor_bin,
        timeout_sec=timeout_sec,
    )
    return harvest_job_dir(job_dir)
