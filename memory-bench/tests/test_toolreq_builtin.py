"""mem-rk41.3.2 — builtin native-memory persistent-env arm (establish/goal, two calls).

Covers the invariants the bead's PLAN-REVIEW made mandatory:

* H3 — the establish call carries NO tool allowlist (``available_tools=[]``), so
  ``--allowedTools`` never blocks Claude Code's own memory-write path.
* H4 — the establish turn's facts are delivered via ``available_memory`` (like the
  oracle arm), never embedded in the instruction prose, so TRUSTED/RECALLED
  meaningfully varies the establish framing.
* H2 — engagement is CONTENT-based (does the opaque token actually reach native memory),
  not file-existence — an empty scaffolded dir never counts. Native memory is an INDEX
  plus TOPIC FILES, and the fact lands in the topic file, so the check must search both.
* The shared sandbox cwd is FIREWALLED between the two legs: it has to be shared (the
  memory path is keyed on its slug) but its contents are a second continuity channel that
  ``--allowedTools`` cannot close, since an auto-loaded ``CLAUDE.md`` is not a tool call.
* A goal PASS with engaged=False is accounted as a LEAK, not a builtin win.
* The dry-run simulator proves the two-call shared cwd/config-dir wiring end to end for
  zero tokens, persisting in the REAL native-memory layout so the free path guards the
  glob (it does not and cannot prove a real ``claude -p`` session persists at all — that
  is the paid preflight's job, tested at the driver level).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NoReturn

import pytest
from pydantic import ValidationError

from membench.harbor.agent_memory import native_memory_path
from membench.runner import toolreq_builtin_grid as grid
from membench.runner.headless_agent import (
    ENV_MODEL,
    CellCalls,
    CellRecorder,
    HeadlessAgentError,
    Leg,
    MemoryChannel,
    _render_only_runner,
    assistant_event,
    cell_agent,
    render_cell_calls,
    result_event,
    serialize_stream,
)
from membench.runner.realagent_probe import CONFIG_FILE, REAL_TOOL, ArmOutcome
from membench.runner.resume_cache import invocation_digest
from membench.runner.sandbox import SandboxContaminationError
from membench.runner.toolreq_builtin import (
    ARM,
    BUILTIN_SETTINGS,
    SIMULATED_TOPIC_FILE,
    BuiltinDiagnostics,
    _establish_step,
    _memory_engaged,
    cell_calls,
    cell_legs,
    run_builtin_arm,
    simulated_builtin_runner,
    wipe_cwd_contents,
)
from membench.runner.toolreq_realagent import (
    ToolReqRealAgentTask,
    adapt_sequence,
    load_corpus_with_sequences,
    task_fingerprint,
)
from tests.toolreq_helpers import (
    CURRENT,
    STUB_CLI_VERSION,
    corpus,
    noop_cli_runner,
    toolreq_seq,
)


@pytest.fixture(autouse=True)
def _pinned_cli_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Autouse, because the hole this closes is one of OMISSION: a paid test that forgets to stub
    the probe still passes on a dev box and keys its identity on whatever CLI that box has. The
    driver owns its own ``run_corpus`` call and rightly passes no ``version_fn``, so this is the
    only seam that reaches it. An explicit ``version_fn=`` argument still wins over this."""
    monkeypatch.setattr(grid, "resolve_cli_version", lambda: STUB_CLI_VERSION)


def _task(seq_id: str = "w-t0"):
    return adapt_sequence(toolreq_seq(seq_id))


def _corpus(tmp_path: Path, *work_ids: str) -> list[ToolReqRealAgentTask]:
    """This file's grid never uses the source sequences (only the ``ours`` seeder does), so it
    keeps the tasks and drops them here rather than at every call site."""
    _sequences, tasks = corpus(tmp_path, *work_ids)
    return tasks


def _corpus_one(tmp_path: Path, work_id: str = "w-0") -> list[ToolReqRealAgentTask]:
    return _corpus(tmp_path, work_id)


def _legs_by_task(
    per_task: dict[str, int],
) -> Callable[[ToolReqRealAgentTask], tuple[Leg, ...]]:
    """A ``cell_legs`` that BRANCHES on its task, giving ``per_task[work_id]`` legs. The test double
    a uniform patch cannot be: with every task on the same leg count, an exact per-task sum and an
    ``n_tasks x calls_per_repeat(tasks[0])`` model agree, so a test built on it passes under either.
    Only a non-uniform corpus separates them (mem-663ga).

    Annotated ``tuple[Leg, ...]``, not the real ``cell_legs``'s ``tuple[Leg, Leg]``, so the double
    can return a third leg at all. Production's pair is deliberate (its order is a measured input,
    and the cwd firewall runs between the two), so this is a shape the real type rules out — which
    is the point: the disclosure is pinned exact for a corpus the type cannot currently hand it."""

    def _cell_legs(task: ToolReqRealAgentTask) -> tuple[Leg, ...]:
        n_legs = per_task[task.work_id]
        # A double that pads to a count it cannot reach would return the establish+goal pair for
        # any n_legs <= 2 and silently test nothing — the same "the number is a MODEL of the real
        # one" failure this fixture exists to catch, one level up.
        assert n_legs >= 2, f"cell_legs is at least the establish+goal pair; got {n_legs}"
        establish, goal = cell_legs(task)
        extra = [Leg(f"pad{i}", goal.step, {"hint": "x"}) for i in range(n_legs - 2)]
        return (establish, *extra, goal)

    return _cell_legs


def _stream_json_runner(
    *, tool_use_when: Callable[[list[str]], bool], tool_name: str, tool_input: dict[str, object]
):
    """Build a fake `claude -p` runner that emits one `tool_use` event (`tool_name` /
    `tool_input`) iff `tool_use_when(argv)` is true, always followed by a terminal
    `result` event — the shared shape behind this file's per-call-site runner stubs."""

    def run(argv, **kwargs):
        argv_list = list(argv)
        events: list[dict[str, object]] = []
        if tool_use_when(argv_list):
            events.append(assistant_event([(tool_name, tool_input)]))
        events.append(result_event())
        stdout = serialize_stream(events)
        return subprocess.CompletedProcess(argv_list, returncode=0, stdout=stdout, stderr="")

    return run


def _record_plan(
    recorder: CellRecorder, task, channel: MemoryChannel, repeats: int, model: str = ""
):
    """Record the plan's invocations THROUGH the recorder — the real arm records off the CLI seam,
    so a double must too, or ``run_cached_corpus`` (which hashes what the recorder SAW, not a value
    the double returned — mem-9gvej) refuses the cell as a plan/execution mismatch."""
    runner = recorder.cell(noop_cli_runner, arm=ARM, channel=channel, repeats=repeats)
    for _ in range(repeats):
        for argv in cell_calls(task, channel, model=model).calls:
            runner(argv)


def _builtin_arm(
    seen: list[str] | None = None,
    *,
    passes: bool = True,
    engaged: bool,
    leaked: bool = False,
) -> Callable[..., object]:
    """A `run_builtin_arm` double that reports every repeat the same way — HONESTLY: the repeats it
    was asked for, the channel it was given, and the invocations the PLAN says that cell sends, so
    the cells it produces are a real grid the schema will accept. A fake that hardcoded one channel
    would be refused as a duplicated cell, and one that reported invocations the plan does not
    declare would be refused at the cache's write boundary — both are the checks doing their job.

    The three booleans are the only thing this file's callers differ on, and folding them into one
    factory is what keeps the third tuple element (`cell_calls`) written ONCE: it was hand-copied
    into each double before, so every move of `run_builtin_arm`'s return shape was three edits and
    a missed one would leave a double silently disagreeing with the write boundary it must satisfy.
    Mirrors `test_toolreq_realagent._spy_run_arm`, including its optional `seen` recorder."""

    def run(
        task,
        *,
        repeats: int,
        channel: MemoryChannel,
        recorder: CellRecorder,
        model: str = "",
        **_kwargs,
    ):
        if seen is not None:
            seen.append(channel.value)  # a real paid cell would spawn `claude -p` here
        # Record the plan's invocations, honouring the model the grid resolved exactly as the real
        # arm does — else the recorded argv omits `--model` while a pinned identity carries it, and
        # the write boundary rejects the cell as a plan/execution mismatch (mem-bzv2p pins a model
        # on paid runs).
        _record_plan(recorder, task, channel, repeats, model=model)
        return (
            ArmOutcome(
                arm=ARM, channel=channel.value, passes=repeats if passes else 0, runs=repeats
            ),
            BuiltinDiagnostics(
                engaged=repeats if engaged else 0,
                leaked=repeats if leaked else 0,
                runs=repeats,
            ),
        )

    return run


# --- establish step (H3, H4) ----------------------------------------------------------


def test_establish_step_has_no_tool_allowlist() -> None:
    task = _task()
    step = _establish_step(task)
    assert step.available_tools == []


def test_establish_step_does_not_embed_facts_in_prose() -> None:
    # H4: facts flow through `available_memory`, never the instruction text itself.
    task = _task()
    step = _establish_step(task)
    for value in task.current_opaque_values:
        assert value not in step.user_request
    for content in task.oracle_memory.values():
        assert content not in step.user_request


def test_establish_step_instructs_remembering() -> None:
    # Q2 resolved to the usability-ceiling framing: explicitly ask the agent to retain.
    step = _establish_step(_task())
    assert "remember" in step.user_request.lower()


def test_argv_omits_allowed_tools_for_establish_but_not_goal() -> None:
    from membench.runner.headless_agent import HeadlessClaudeAgent

    task = _task()
    agent = HeadlessClaudeAgent(constrain_tools=True, runner=_render_only_runner)
    establish_argv = agent.argv_for(_establish_step(task), {})
    goal_argv = agent.argv_for(task.goal_step, {})
    assert "--allowedTools" not in establish_argv
    assert "--allowedTools" in goal_argv and "Write" in goal_argv


# --- content-based engagement gate (H2, M1) --------------------------------------------


def test_memory_engaged_true_when_token_reaches_memory_md(tmp_path: Path) -> None:
    memory_dir = tmp_path / "projects" / "-tmp-sandbox" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("remembered: toolreq-abc123-CURRENT", encoding="utf-8")
    assert _memory_engaged(tmp_path, ["toolreq-abc123-CURRENT"]) is True


def test_memory_engaged_false_when_absent(tmp_path: Path) -> None:
    assert _memory_engaged(tmp_path, ["toolreq-abc123-CURRENT"]) is False


def test_memory_engaged_false_on_empty_scaffolded_file(tmp_path: Path) -> None:
    # H2: an empty file (CC scaffolds the dir regardless of content) is NOT engagement.
    memory_dir = tmp_path / "projects" / "-tmp-sandbox" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("", encoding="utf-8")
    assert _memory_engaged(tmp_path, ["toolreq-abc123-CURRENT"]) is False


def test_memory_engaged_globs_any_project_slug(tmp_path: Path) -> None:
    # M1: never predict the exact slug — a glob finds it regardless of cwd-derived name.
    memory_dir = tmp_path / "projects" / "-some-other-tempdir-slug" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("value=toolreq-xyz-CURRENT", encoding="utf-8")
    assert _memory_engaged(tmp_path, ["toolreq-xyz-CURRENT"]) is True


def test_memory_engaged_true_when_the_token_lands_in_a_topic_file(tmp_path: Path) -> None:
    # Claude Code native memory is an INDEX plus TOPIC FILES: MEMORY.md carries one-line
    # pointers ("- [Title](topic.md) — hook") and the FACT itself lives in the sibling
    # <topic>.md. Every native-memory dir on this box has that shape, without exception.
    # Globbing only MEMORY.md therefore scores a WORKING builtin as engaged=0 — which on
    # the paid path is a false PREFLIGHT HALT ("native memory may be disabled") or, with
    # --skip-preflight, records the arm's BEST possible result (a clean 3/3 off native
    # memory) as a LEAK. The token must be found wherever native memory actually put it.
    memory_dir = tmp_path / "projects" / "-tmp-sandbox" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text(
        "- [Retention window](retention-window.md) — the window to recall later\n",
        encoding="utf-8",
    )
    (memory_dir / "retention-window.md").write_text(
        "the retention window is toolreq-abc123-CURRENT", encoding="utf-8"
    )
    assert _memory_engaged(tmp_path, ["toolreq-abc123-CURRENT"]) is True


# --- simulated dry-run runner (proves the two-call wiring, no tokens) ------------------


def test_simulated_runner_establish_writes_iff_prompt_carries_every_value(tmp_path: Path) -> None:
    runner = simulated_builtin_runner(["tok-a", "tok-b"])
    argv = ["claude", "-p", "carries tok-a and tok-b", "--output-format", "stream-json"]
    completed = runner(argv, env={"CLAUDE_CONFIG_DIR": str(tmp_path)}, cwd="/sandbox")
    assert completed.returncode == 0
    index_path = Path(native_memory_path(config_dir=str(tmp_path), workdir="/sandbox"))
    assert index_path.is_file()
    # the FACT lands in the topic file, not the index — the real native-memory layout
    topic_path = index_path.parent / SIMULATED_TOPIC_FILE
    assert "tok-a" in topic_path.read_text(encoding="utf-8")


def test_simulated_runner_establish_no_write_when_prompt_missing_a_value(tmp_path: Path) -> None:
    runner = simulated_builtin_runner(["tok-a", "tok-b"])
    argv = ["claude", "-p", "carries only tok-a", "--output-format", "stream-json"]
    runner(argv, env={"CLAUDE_CONFIG_DIR": str(tmp_path)}, cwd="/sandbox")
    memory_path = Path(native_memory_path(config_dir=str(tmp_path), workdir="/sandbox"))
    assert not memory_path.is_file()


def test_simulated_runner_goal_call_passes_iff_marker_present(tmp_path: Path) -> None:
    runner = simulated_builtin_runner(["tok-a"])
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path)}
    # bare goal prompt never carries the value itself
    bare_argv = ["claude", "-p", "## Task\nwrite it", "--output-format", "stream-json"]

    # no establish call happened -> no marker -> goal call makes no tool call
    completed = runner(bare_argv, env=env, cwd="/sandbox")
    events = [json.loads(line) for line in completed.stdout.splitlines()]
    assert all(e["type"] != "assistant" for e in events)

    # now simulate the establish call, then re-run the (identical) bare goal call
    runner(["claude", "-p", "tok-a", "--output-format", "stream-json"], env=env, cwd="/sandbox")
    completed2 = runner(bare_argv, env=env, cwd="/sandbox")
    events2 = [json.loads(line) for line in completed2.stdout.splitlines()]
    (event,) = [e for e in events2 if e["type"] == "assistant"]
    (block,) = event["message"]["content"]
    assert block["name"] == REAL_TOOL
    assert block["input"]["content"] == "tok-a"


# --- run_builtin_arm: dry-run end to end ------------------------------------------------


def test_dry_run_arm_engages_and_passes_every_repeat() -> None:
    task = _task()
    outcome, diag = run_builtin_arm(
        task,
        repeats=3,
        model="",
        dry_run=True,
        channel=MemoryChannel.RECALLED,
        recorder=CellRecorder(),
    )
    assert outcome.arm == ARM
    assert outcome.passes == outcome.runs == 3
    assert diag.engaged == 3
    assert diag.leaked == 0
    # the honest dry-run simulator never claims a tool_use on the establish leg
    assert diag.establish_tool_calls == 0


def test_establish_tool_calls_are_counted_not_discarded() -> None:
    # The establish call's own tool_calls must be captured (the security-review finding:
    # it runs with NO --allowedTools clamp, so its actions need an audit trail).
    task = _task()
    bash_happy_runner = _stream_json_runner(
        tool_use_when=lambda argv: "--allowedTools" not in argv,  # the establish call only
        tool_name="Bash",
        tool_input={"command": "ls"},
    )

    _outcome, diag = run_builtin_arm(
        task,
        repeats=2,
        model="",
        dry_run=False,
        channel=MemoryChannel.RECALLED,
        runner=bash_happy_runner,
        recorder=CellRecorder(),
    )
    assert diag.establish_tool_calls == 2  # one Bash call per repeat's establish leg


def test_dry_run_arm_channel_recorded_on_outcome() -> None:
    task = _task()
    outcome, _diag = run_builtin_arm(
        task,
        repeats=1,
        model="",
        dry_run=True,
        channel=MemoryChannel.TRUSTED,
        recorder=CellRecorder(),
    )
    assert outcome.channel == "trusted"


@pytest.mark.parametrize("channel", [MemoryChannel.RECALLED, MemoryChannel.TRUSTED])
def test_goal_call_is_bare_under_either_channel(channel: MemoryChannel) -> None:
    # ONE HeadlessClaudeAgent drives both legs, carrying the arm's channel. That is only
    # sound because the goal call surfaces memory={} and `build_agent_prompt` emits NO
    # memory block for empty memory under EITHER channel — so the channel's trust framing
    # cannot leak the opaque value into the bare goal prompt. If that ever stops holding,
    # the goal call starts being handed the answer and every builtin "pass" is a leak.
    task = _task()
    value = task.current_opaque_values[0]
    prompts: list[str] = []

    def recording_runner(argv, **kwargs):
        prompts.append(argv[2])
        return subprocess.CompletedProcess(list(argv), returncode=0, stdout="", stderr="")

    run_builtin_arm(
        task,
        repeats=1,
        model="",
        dry_run=False,
        channel=channel,
        runner=recording_runner,
        recorder=CellRecorder(),
    )
    establish_prompt, goal_prompt = prompts
    assert value in establish_prompt  # establish is handed the fact...
    assert value not in goal_prompt  # ...the goal call is not, under either channel
    assert "Established facts" not in goal_prompt
    assert "recalled from" not in goal_prompt.lower()


def test_fresh_sandbox_and_config_dir_per_repeat() -> None:
    # A regression test that would actually FAIL if the two TemporaryDirectory context
    # managers were hoisted out of the per-repeat loop and shared across repeats: record
    # every (cwd, CLAUDE_CONFIG_DIR) pair the runner is invoked with and assert every
    # repeat used a distinct pair. `diag.engaged == runs` alone does not catch this
    # regression class — a shared dir would still show every repeat as "engaged" because
    # the marker file from repeat 1 would still be sitting there for repeat 2 onward.
    task = _task()
    seen: list[tuple[object, object]] = []

    def recording_runner(argv, **kwargs):
        seen.append((kwargs.get("cwd"), (kwargs.get("env") or {}).get("CLAUDE_CONFIG_DIR")))
        return subprocess.CompletedProcess(list(argv), returncode=0, stdout="", stderr="")

    run_builtin_arm(
        task,
        repeats=5,
        model="",
        dry_run=False,
        channel=MemoryChannel.RECALLED,
        runner=recording_runner,
        recorder=CellRecorder(),
    )
    # 2 calls (establish + goal) per repeat, both sharing the SAME pair within a repeat.
    assert len(seen) == 10
    per_repeat_pairs = [seen[i] for i in range(0, 10, 2)]
    assert seen[0] == seen[1]  # establish and goal share one sandbox+config_dir
    assert len(set(per_repeat_pairs)) == 5  # every repeat's pair is distinct from every other


def test_simulated_establish_persists_to_a_topic_file_not_the_index(tmp_path: Path) -> None:
    # The simulator must write where REAL native memory writes: the fact in a <topic>.md,
    # the index holding only a pointer. A simulator that parked the fact in MEMORY.md
    # would be fitted to whatever the engagement check globs — which is exactly how a
    # MEMORY.md-only glob (scoring a working builtin as engaged=0) survived a green
    # dry-run. Pinning the layout here makes the FREE path a real guard on the glob.
    runner = simulated_builtin_runner(["toolreq-abc123-CURRENT"])
    cwd = tmp_path / "sandbox"
    cwd.mkdir()
    config_dir = tmp_path / "config"
    runner(
        ["claude", "-p", "facts: toolreq-abc123-CURRENT"],
        env={"CLAUDE_CONFIG_DIR": str(config_dir)},
        cwd=str(cwd),
    )
    index = Path(native_memory_path(config_dir=str(config_dir), workdir=str(cwd)))
    topic = index.parent / SIMULATED_TOPIC_FILE
    assert "toolreq-abc123-CURRENT" in topic.read_text(encoding="utf-8")  # fact: topic file
    assert "toolreq-abc123-CURRENT" not in index.read_text(encoding="utf-8")  # index: pointer
    assert _memory_engaged(config_dir, ["toolreq-abc123-CURRENT"]) is True


# --- cwd firewall: the shared sandbox is not a second continuity channel ---------------


def _cwd_scavenging_runner(value: str):
    """Establish leg (no ``--allowedTools``): persists the value into a file in the SHARED
    sandbox cwd instead of into native memory — which an unconstrained establish call is
    free to do. Goal leg: passes iff that file is still readable. Claude Code auto-loads
    ``CLAUDE.md``/``AGENTS.md`` from the cwd at session start with NO tool call, so a
    Write-only ``--allowedTools`` clamp does not close this channel; only emptying the cwd
    does."""

    def run(argv, **kwargs):
        argv_list = list(argv)
        cwd = kwargs.get("cwd")
        assert isinstance(cwd, str)
        scavengeable = Path(cwd) / "CLAUDE.md"
        events: list[dict[str, object]] = []
        if "--allowedTools" not in argv_list:  # establish leg
            scavengeable.write_text(f"remember: {value}", encoding="utf-8")
        elif scavengeable.is_file() and value in scavengeable.read_text(encoding="utf-8"):
            events.append(  # goal leg: passes off the leftover file, never touching memory
                assistant_event([(REAL_TOOL, {"file_path": CONFIG_FILE, "content": value})])
            )
        events.append(result_event())
        stdout = serialize_stream(events)
        return subprocess.CompletedProcess(argv_list, returncode=0, stdout=stdout, stderr="")

    return run


def test_goal_leg_cannot_scavenge_a_cwd_file_the_establish_leg_left_behind() -> None:
    # The establish and goal legs MUST share a sandbox cwd (the native-memory path is
    # keyed on the cwd slug), but the cwd's CONTENTS are a second, unfirewalled continuity
    # channel outside the memory channel under test. Left open, an establish call that
    # writes CLAUDE.md and never touches native memory still yields a passing goal leg —
    # and because `engaged` is measured off the establish leg while `leaked` only fires on
    # (pass AND NOT engaged), the accounting would record it as a clean builtin SEPARATES.
    # Wiping the cwd's contents between legs closes the channel structurally: the slug (so
    # the memory path, so continuity) is unchanged, but nothing is left to scavenge.
    task = _task()
    (current_opaque,) = task.current_opaque_values

    outcome, diag = run_builtin_arm(
        task,
        repeats=2,
        model="",
        dry_run=False,
        channel=MemoryChannel.RECALLED,
        runner=_cwd_scavenging_runner(current_opaque),
        recorder=CellRecorder(),
    )
    assert outcome.passes == 0  # the leftover file is gone: nothing to scavenge
    assert diag.engaged == 0  # and this runner never engaged native memory at all
    assert diag.leaked == 0  # so there is no pass to misreport as a builtin win


def test_cwd_wipe_preserves_the_sandbox_dir_so_the_memory_path_survives() -> None:
    # The wipe must empty the cwd, never replace it: the native-memory path is derived
    # from the cwd SLUG, so a fresh cwd between legs would silently move the memory file
    # out from under the goal call and break the very continuity we are measuring.
    task = _task()
    seen_cwds: list[object] = []

    def recording_runner(argv, **kwargs):
        seen_cwds.append(kwargs.get("cwd"))
        return subprocess.CompletedProcess(list(argv), returncode=0, stdout="", stderr="")

    run_builtin_arm(
        task,
        repeats=1,
        model="",
        dry_run=False,
        channel=MemoryChannel.RECALLED,
        runner=recording_runner,
        recorder=CellRecorder(),
    )
    assert seen_cwds[0] == seen_cwds[1]  # establish and goal still share ONE cwd path


def test_establish_tool_names_are_recorded_not_just_counted() -> None:
    # The audit trail exists so a reviewer gating the PAID fire can see what the
    # unconstrained establish call actually did — a bare count cannot answer "did it write
    # into the shared cwd", which is the question that matters.
    task = _task()
    bash_happy_runner = _stream_json_runner(
        tool_use_when=lambda argv: "--allowedTools" not in argv,  # the establish call only
        tool_name="Bash",
        tool_input={"command": "ls"},
    )
    _outcome, diag = run_builtin_arm(
        task,
        repeats=2,
        model="",
        dry_run=False,
        channel=MemoryChannel.RECALLED,
        runner=bash_happy_runner,
        recorder=CellRecorder(),
    )
    assert diag.establish_tool_calls == 2
    assert diag.establish_tool_names == ("Bash",)


# --- the mechanism knob: a pristine config dir must have native memory ON --------------


def test_fresh_config_dir_turns_native_memory_on() -> None:
    # `autoMemoryEnabled` is a $CLAUDE_CONFIG_DIR/settings.json key — CONFIG-DIR-LOCAL, so
    # this driver fully owns it (account2's settings.json on this box carries it false).
    # Each repeat mints a PRISTINE EMPTY config dir, so without seeding it the mechanism
    # under test would ride on whatever Claude Code's default for that key happens to be —
    # a coin flip on the paid path, and one that would send a halted run chasing an
    # account-level problem that does not exist.
    task = _task()
    seen: list[dict[str, object]] = []

    def settings_recording_runner(argv, **kwargs):
        env = kwargs.get("env") or {}
        config_dir = Path(str(env.get("CLAUDE_CONFIG_DIR")))
        settings = config_dir / "settings.json"
        seen.append(json.loads(settings.read_text(encoding="utf-8")) if settings.is_file() else {})
        return subprocess.CompletedProcess(list(argv), returncode=0, stdout="", stderr="")

    run_builtin_arm(
        task,
        repeats=1,
        model="",
        dry_run=False,
        channel=MemoryChannel.RECALLED,
        runner=settings_recording_runner,
        recorder=CellRecorder(),
    )
    assert seen, "the runner never saw a config dir"
    assert all(s.get("autoMemoryEnabled") is True for s in seen)


def test_builtin_settings_is_frozen() -> None:
    # BUILTIN_SETTINGS is read by reference from both `_seed_config_dir` and
    # `mechanism_fingerprint` — an in-place edit would silently diverge the seeded
    # settings.json from the fingerprint the cache identity carries. Frozen so that edit
    # raises TypeError instead of drifting unnoticed.
    with pytest.raises(TypeError):
        BUILTIN_SETTINGS["autoMemoryEnabled"] = False  # type: ignore[index]


# --- leak accounting (H2): a pass without engagement is NOT a builtin win --------------


def test_leaked_pass_without_engagement_is_flagged_not_counted_as_clean() -> None:
    task = _task()
    (current_opaque,) = task.current_opaque_values
    runner = _leaking_runner_for(current_opaque)
    outcome, diag = run_builtin_arm(
        task,
        repeats=2,
        model="",
        dry_run=False,
        channel=MemoryChannel.RECALLED,
        runner=runner,
        recorder=CellRecorder(),
    )
    assert outcome.passes == 2  # score_goal_action sees a genuine Write of the current value
    assert diag.engaged == 0  # but native memory never actually persisted anything
    assert diag.leaked == 2  # so both passes are flagged as leaks, not a builtin win


def _leaking_runner_for(current_opaque_value: str):
    return _stream_json_runner(
        tool_use_when=lambda argv: "--allowedTools" in argv,  # the goal call only
        tool_name=REAL_TOOL,
        tool_input={"file_path": CONFIG_FILE, "content": current_opaque_value},
    )


def test_diagnostics_is_a_plain_dataclass_not_an_arm_outcome_subtype() -> None:
    # M3: ArmOutcome stays uniform; engagement lives in a SEPARATE sidecar type.
    diag = BuiltinDiagnostics(engaged=1, leaked=0, runs=1)
    assert not hasattr(diag, "arm")
    assert not hasattr(diag, "passes")


# --- the grid (membench/runner/toolreq_builtin_grid.py) ---------------------------------
#
# The arm's cells, its verdict rule, and its cache identity. The RESUME CACHE itself is the
# shared core (`membench.runner.resume_cache`, tested once in `test_resume_cache.py`); what
# is tested here is this grid's ADOPTION of it — that the identity this grid builds actually
# carries the inputs whose absence was the mem-mpxie defect family, and that its cells carry
# bounds the shared schema cannot know about (engagement is a builtin-only concept).


def _cell(
    channel: str = "recalled", *, passes: int = 2, runs: int = 2, engaged: int = 2, leaked: int = 0
) -> grid.BuiltinCell:
    return grid.BuiltinCell(
        arm=ARM,
        channel=channel,
        passes=passes,
        runs=runs,
        engaged=engaged,
        leaked=leaked,
        establish_tool_calls=0,
        establish_tool_names=[],
    )


def test_dry_run_evaluate_task_separates_both_channels() -> None:
    task = _task()
    cells = grid.evaluate_task(task, repeats=2, model="", dry_run=True, recorder=CellRecorder())
    assert {cell.channel for cell in cells} == {"recalled", "trusted"}
    for cell in cells:
        assert cell.passes == cell.runs == 2
        assert cell.engaged == 2 and cell.leaked == 0


def test_verdict_separates_when_engaged_and_passing() -> None:
    assert "SEPARATES" in grid.task_verdict([_cell(passes=3, runs=3, engaged=3)])


def test_verdict_leak_outranks_pass_count() -> None:
    assert "LEAK" in grid.task_verdict([_cell(passes=2, runs=2, engaged=0, leaked=2)])


def test_verdict_not_engaged_when_mechanism_never_fires() -> None:
    assert "NOT-ENGAGED" in grid.task_verdict([_cell(passes=0, runs=3, engaged=0)])


# --- the cell's cross-field bounds: an impossible engagement claim is unconstructible ----


def test_more_engaged_than_runs_is_unconstructible() -> None:
    with pytest.raises(ValidationError):
        _cell(runs=2, engaged=3)


def test_more_leaks_than_passes_is_unconstructible() -> None:
    # A leak IS a pass — one that happened without engagement — so it cannot outnumber the
    # passes it is drawn from.
    with pytest.raises(ValidationError):
        _cell(passes=1, runs=2, engaged=0, leaked=2)


def test_more_leaks_than_non_engaged_repeats_is_unconstructible() -> None:
    # The same impossibility from the other side, and the one a `leaked <= passes` bound alone
    # would miss: a leaked repeat is BY DEFINITION one that did not engage, so 2 leaks cannot
    # coexist with 2 engaged repeats out of 2 runs. Without this a record can claim a clean
    # sweep (engaged 2/2, passes 2/2) AND carry the leaks that deny it.
    with pytest.raises(ValidationError):
        _cell(passes=2, runs=2, engaged=2, leaked=2)


def test_fewer_leaks_than_passes_minus_engaged_is_unconstructible() -> None:
    # The LOWER bound, and the one the three upper bounds cannot stand in for: they only ever say
    # `leaked` is too BIG. `leaked` counts the repeats that PASSED while NOT engaging, so by
    # inclusion-exclusion at least (passes - engaged) of the passing repeats were leaks. A row
    # claiming 2 passes, 0 engaged and 0 leaks is arithmetically impossible.
    with pytest.raises(ValidationError):
        _cell(passes=2, runs=2, engaged=0, leaked=0)


def test_zeroing_leaked_on_a_real_leak_record_cannot_rewrite_the_headline(
    tmp_path: Path, monkeypatch
) -> None:
    # The reason the lower bound matters, end to end. `run_builtin_arm` legitimately writes a LEAK
    # cell (passes=2, engaged=0, leaked=2) when the sandbox hands the agent a pass it never earned
    # through native memory — the most severe verdict the arm produces. Zero `leaked` on disk and
    # the row still satisfies every UPPER bound, while `cell_kind` now reads it as NOT-ENGAGED: the
    # task silently moves out of the summary's `leaked` list into `not_engaged`, on the PAID path,
    # at executed=0.
    #
    # The forged record carries the verdict its forged rows IMPLY, not the original LEAK string.
    # That is what makes this a test of the lower bound rather than of the verdict-derivation check
    # — leave the stale LEAK verdict in place and that other check refuses the file first, and this
    # test would pass with no lower bound at all. A record whose every OTHER field agrees with
    # itself is exactly the one nothing else can refuse.
    tasks = _corpus_one(tmp_path)

    # The verdict a genuinely NOT-ENGAGED grid produces — taken from a real run, never hand-typed,
    # so the forgery is exactly what a self-consistent record would say.
    monkeypatch.setattr(grid, "run_builtin_arm", _builtin_arm(engaged=True))
    engaged_out = tmp_path / "engaged"
    grid.run_corpus(tasks, out_dir=engaged_out, repeats=2, model="", dry_run=True)
    not_engaged_verdict = json.loads((engaged_out / "w-0.json").read_text())["verdict"].replace(
        "SEPARATES: 2/2 (engaged 2/2)", "NOT-ENGAGED: the fact never reached native memory (0/2)"
    )

    out = tmp_path / "out"
    monkeypatch.setattr(grid, "run_builtin_arm", _builtin_arm(engaged=False, leaked=True))
    truth = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert truth["leaked"] == ["w-0"] and truth["not_engaged"] == []

    result_path = out / "w-0.json"
    record = json.loads(result_path.read_text(encoding="utf-8"))
    for row in record["outcomes"]:
        row["leaked"] = 0  # the edit that erases the LEAK...
    record["verdict"] = not_engaged_verdict  # ...and the verdict those rows now imply
    result_path.write_text(json.dumps(record), encoding="utf-8")

    resumed = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert resumed["executed"] == 1 and resumed["reused"] == 0, "served a forged leak-free record"
    assert resumed["leaked"] == ["w-0"], "the LEAK was downgraded to NOT-ENGAGED"


def test_a_cell_whose_diagnostics_disagree_about_runs_is_refused() -> None:
    # The arm reports `runs` on BOTH halves it returns; they are the same measurement, so a
    # disagreement means one of the two is fabricated and the record must not be written.
    outcome = ArmOutcome(arm=ARM, channel="recalled", passes=2, runs=2)
    diagnostics = BuiltinDiagnostics(engaged=2, leaked=0, runs=3)
    with pytest.raises(ValueError, match="diagnostics claim"):
        grid._cell(outcome, diagnostics)


# --- the resume cache, as this grid now inherits it --------------------------------------


def test_run_corpus_persists_and_is_resumable(tmp_path: Path) -> None:
    tasks = _corpus_one(tmp_path)
    out = tmp_path / "out"

    first = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert first["executed"] == 1 and first["reused"] == 0
    assert (out / "w-0.json").is_file()
    assert "SEPARATES" in first["per_task"][0]["verdict"]
    assert first["separates_all_channels"] == 1

    second = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert second["executed"] == 0 and second["reused"] == 1


def test_dry_run_cache_never_satisfies_a_paid_run(tmp_path: Path, monkeypatch) -> None:
    tasks = _corpus_one(tmp_path)
    out = tmp_path / "out"
    grid.run_corpus(tasks, out_dir=out, repeats=1, model="", dry_run=True)

    calls = {"n": 0}
    real_eval = grid.evaluate_task

    def _spy(task, **_kwargs):
        calls["n"] += 1
        # dry_run simulates (never spends) but keeps the grid's resolved model, so the recorded
        # argv matches a pinned paid identity's invocation_fingerprint (mem-bzv2p). The recorder is
        # owned by run_cached_corpus and threaded straight through.
        return real_eval(
            task, repeats=1, model=_kwargs["model"], dry_run=True, recorder=_kwargs["recorder"]
        )

    monkeypatch.setattr(grid, "evaluate_task", _spy)
    paid = grid.run_corpus(
        tasks,
        out_dir=out,
        repeats=1,
        model="sonnet",
        dry_run=False,
        version_fn=lambda: STUB_CLI_VERSION,
    )
    assert paid["executed"] == 1 and paid["reused"] == 0
    assert calls["n"] == 1


def test_upgrading_the_cli_between_runs_is_a_miss_not_a_relabel(
    tmp_path: Path, monkeypatch
) -> None:
    """Worth a case here and not only in the 3-arm suite: this grid wires its own `run_corpus`, and
    ours-vs-builtin is a comparison BETWEEN the two grids — a drift that missed one while the other
    reused would corrupt exactly that comparison. Both runs are spied, so neither spends."""
    tasks = _corpus_one(tmp_path)
    out = tmp_path / "out"
    real_eval = grid.evaluate_task

    def _spy(task, **_kwargs):
        # dry_run simulates (never spends) but keeps the grid's resolved model, so the recorded
        # argv matches a pinned paid identity's invocation_fingerprint (mem-bzv2p). The recorder is
        # owned by run_cached_corpus and threaded straight through.
        return real_eval(
            task, repeats=1, model=_kwargs["model"], dry_run=True, recorder=_kwargs["recorder"]
        )

    monkeypatch.setattr(grid, "evaluate_task", _spy)
    first = grid.run_corpus(
        tasks, out_dir=out, repeats=1, model="sonnet", dry_run=False, version_fn=lambda: "2.1.173"
    )
    assert (first["executed"], first["reused"]) == (1, 0)

    second = grid.run_corpus(
        tasks,
        out_dir=out,
        repeats=1,
        model="sonnet",
        dry_run=False,
        version_fn=lambda: STUB_CLI_VERSION,
    )
    assert (second["executed"], second["reused"]) == (1, 0), "old binary's numbers, new instrument"

    # ...and the same binary still resumes: the field must not make every paid run a miss.
    third = grid.run_corpus(
        tasks,
        out_dir=out,
        repeats=1,
        model="sonnet",
        dry_run=False,
        version_fn=lambda: STUB_CLI_VERSION,
    )
    assert (third["executed"], third["reused"]) == (0, 1)


def test_a_dry_run_never_asks_which_binary_is_installed(tmp_path: Path) -> None:
    """A free run spawns no claude, so it must not need one to exist — `--dry-run` has to stay
    runnable on a machine with no CLI installed at all."""

    def _refuse() -> str:
        raise AssertionError("a dry run must not resolve the claude binary — it spawns none")

    summary = grid.run_corpus(
        _corpus_one(tmp_path),
        out_dir=tmp_path / "out",
        repeats=1,
        model="",
        dry_run=True,
        version_fn=_refuse,
    )
    assert summary["executed"] == 1


# THE FOUR LIVE DEFECTS (mem-mpxie). Each was a real hole in this driver's hand-rolled cache on
# 2026-07-14, each is closed by adopting the shared core, and each below is the executable case
# that says so. They are the same shapes the 3-arm grid was already hardened against — which is
# the whole point: the sibling re-earned them because it re-implemented the cache instead of
# adopting it.


def test_a_regenerated_corpus_never_reuses_the_previous_worlds_results(tmp_path: Path) -> None:
    # (a) NO TASK FINGERPRINT. Work ids are POSITIONAL (`w-0`), so regenerating the corpus over the
    # same `--out` reuses them. The old identity was {repeats, dry_run, model} — nothing about the
    # WORLD — so the previous world's numbers were served at executed=0 for a task whose scoring
    # values had changed underneath.
    #
    # The regenerated world here changes ONLY the superseded (stale) value, and that is the point:
    # the stale value is never surfaced (the goal requires the CURRENT memory id) and never named in
    # the request (the leak firewall), so BOTH prompts come out byte-identical while the scorer's
    # `forbidden_values` — what a passing Write must NOT carry — is a different token. It is the one
    # world change the invocation fingerprint structurally cannot see, which is why the identity
    # carries `task_fingerprint` ALONGSIDE it rather than in place of it. A weaker case (changing
    # the current value too) would move the command lines as well, and would pass with no task
    # fingerprint at all.
    out = tmp_path / "out"
    tasks = _corpus_one(tmp_path)
    first = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert first["executed"] == 1

    corpus_dir = tmp_path / "corpus"
    (corpus_dir / "0" / "sequences.json").write_text(
        json.dumps([toolreq_seq("w-0", current=CURRENT, stale="91 days").model_dump()]),
        encoding="utf-8",
    )
    _, regenerated = load_corpus_with_sequences(corpus_dir)
    assert regenerated[0].work_id == tasks[0].work_id  # the id collides, as in the real corpus
    assert invocation_digest(grid.planned_calls(regenerated[0], model="")) == invocation_digest(
        grid.planned_calls(tasks[0], model="")
    )
    assert task_fingerprint(regenerated[0]) != task_fingerprint(tasks[0])

    second = grid.run_corpus(regenerated, out_dir=out, repeats=2, model="", dry_run=True)
    assert second["executed"] == 1 and second["reused"] == 0, "served the previous world's numbers"


def test_repointing_the_env_model_between_runs_is_a_miss_not_a_relabel(
    tmp_path: Path, monkeypatch
) -> None:
    # (b) RAW MODEL IN THE IDENTITY. `--model` defaults to "" and the agent then reads
    # MEMBENCH_AGENT_MODEL, so caching the raw "" made the driver's primary independent variable
    # invisible: run under one model, repoint the env, resume, and every task was served as
    # `reused` with the FIRST model's numbers relabelled as the second's. The identity now stores
    # the RESOLVED model, and `BaseRunIdentity` refuses an unresolved one structurally.
    tasks = _corpus_one(tmp_path)
    out = tmp_path / "out"

    monkeypatch.setenv(ENV_MODEL, "model-one")
    first = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert first["executed"] == 1

    monkeypatch.setenv(ENV_MODEL, "model-two")
    second = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert second["executed"] == 1 and second["reused"] == 0, "relabelled one model as another"


def test_a_newer_writers_extra_identity_field_is_a_miss_not_a_subset_match(tmp_path: Path) -> None:
    # (c) SUBSET IDENTITY COMPARISON. The old check was
    # `any(loaded.get(key) != value for key, value in identity.items())`, so a record carrying a
    # field the reader did not know about — a NEWER writer's file, read by an older binary —
    # matched on the fields they happened to share and was served as `reused`. The identity is now
    # a NESTED strict model with extra="forbid", so acceptance is a whole-object ==.
    tasks = _corpus_one(tmp_path)
    out = tmp_path / "out"
    grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)

    result_path = out / "w-0.json"
    record = json.loads(result_path.read_text(encoding="utf-8"))
    record["identity"]["a_field_a_newer_writer_added"] = "surely harmless"
    result_path.write_text(json.dumps(record), encoding="utf-8")

    resumed = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert resumed["executed"] == 1 and resumed["reused"] == 0


def test_deeply_nested_json_is_a_miss_not_a_recursionerror_killing_the_sweep(
    tmp_path: Path,
) -> None:
    # (d) NARROW PARSE BOUNDARY. The old loader caught (OSError, ValueError) only, and
    # `json.loads` raises RecursionError — NOT a ValueError — on deeply nested input. One such
    # file (disk rot, a truncated write, a hand edit) escaped the loader and killed the whole
    # PAID sweep mid-resume. Every rejection is now a miss.
    tasks = _corpus_one(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "w-0.json").write_bytes(b"[" * 200_000)
    summary = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert summary["executed"] == 1 and summary["reused"] == 0


def test_the_fingerprint_is_the_invocations_the_arm_actually_sends(tmp_path: Path) -> None:
    """THE standing invariant, and it costs ZERO tokens: what the identity hashes must be what the
    arm puts on the wire.

    The arm's invocations are RECORDED off the CLI seam (`RecordingRunner`), so this compares the
    fingerprint against the real command lines, not against a second rendering of them. And
    `dry_run` swaps only the CLI RUNNER — never the prompt builder, never the argv — so the free
    path's invocations ARE the paid path's. Re-introduce a hand-written mirror of the arm's legs
    beside the fingerprint and let it drift by one field, and this goes RED before any money is
    spent."""
    task = _corpus_one(tmp_path)[0]
    sent = []
    for channel in grid.CHANNELS:
        recorder = CellRecorder()
        run_builtin_arm(task, repeats=2, model="", dry_run=True, channel=channel, recorder=recorder)
        (cell,) = recorder.recorded()  # what the CLI seam actually saw, folded to one cycle
        sent.append(cell)
    assert invocation_digest(sent) == invocation_digest(grid.planned_calls(task, model=""))


def test_changing_what_a_leg_surfaces_is_a_miss_not_a_reuse(tmp_path: Path) -> None:
    """THE bead, executable. Surface a hint in the goal leg — memory={} becomes non-empty, the exact
    edit the old hand-written `cell_prompts` did not track — and the identity must MOVE, so a resume
    re-measures instead of serving pre-change numbers as post-change measurements.

    It mutates the PLAN (`cell_legs`), which is what `run_builtin_arm` executes AND what
    `invocation_fingerprint` renders. The test this replaces patched `_ESTABLISH_INSTRUCTION`, which
    feeds both sides through the shared `_establish_step` — so it moved the executor and the hash
    together and would have passed with the mirror fully drifted. It proved the establish leg was
    hashed; it could not prove the hash tracked the arm."""
    tasks = _corpus_one(tmp_path)
    out = tmp_path / "out"
    first = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert first["executed"] == 1

    import membench.runner.toolreq_builtin as tb

    def _hinted_goal(task):
        establish, goal = cell_legs(task)
        return (establish, tb.Leg(goal.name, goal.step, {"hint": "the value you established"}))

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tb, "cell_legs", _hinted_goal)
        second = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert second["executed"] == 1 and second["reused"] == 0, "served the pre-change numbers"


def test_turning_the_mechanism_off_is_a_miss_not_a_reuse(tmp_path: Path, monkeypatch) -> None:
    """`autoMemoryEnabled` IS the mechanism under test, and it reaches the agent through a FILE in
    `CLAUDE_CONFIG_DIR` — not through argv. So flipping it moves NO command line, NO task field and
    (there being no store) no payload: `invocation_fingerprint` structurally cannot see it, which is
    why the identity carries `settings_fingerprint` alongside it (the shared base field this grid
    fills from `mechanism_fingerprint`).

    Without that field a resumed run serves mechanism-ON numbers as mechanism-OFF measurements —
    which is to say, it would report the arm's headline for a setting the arm never ran under."""
    tasks = _corpus_one(tmp_path)
    out = tmp_path / "out"
    first = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert first["executed"] == 1

    import membench.runner.toolreq_builtin as tb

    monkeypatch.setattr(tb, "BUILTIN_SETTINGS", {"autoMemoryEnabled": False})
    second = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert second["executed"] == 1 and second["reused"] == 0, "served the mechanism-ON numbers"


def test_the_seeded_settings_are_the_ones_the_identity_fingerprints(tmp_path: Path) -> None:
    """One definition, not two that agree today: the dict `_seed_config_dir` WRITES to the sandbox
    config dir must be the dict `mechanism_fingerprint` HASHES."""
    import membench.runner.toolreq_builtin as tb

    config_dir = tmp_path / "config"
    tb._seed_config_dir(config_dir)
    seeded = json.loads((config_dir / "settings.json").read_text(encoding="utf-8"))
    assert seeded == tb.BUILTIN_SETTINGS == {"autoMemoryEnabled": True}


def test_a_plan_that_drifts_from_its_arm_refuses_to_publish(tmp_path: Path, monkeypatch) -> None:
    """The other half of the bond. Freeze the fingerprint at a value the arm's invocations do not
    hash to — what a plan left behind by an edit to `run_builtin_arm` produces — and the measurement
    must be REFUSED, not filed.

    Filing it would put a real result under a command line it never sent, and the very next resume
    would serve it. So the result file must not exist: a refused measurement that still wrote itself
    is the failure it exists to prevent, one run later."""
    tasks = _corpus_one(tmp_path)
    out = tmp_path / "out"
    # A plan whose command lines the arm's invocations do not hash to — what an edit to
    # `run_builtin_arm` that moved the argv without moving the plan produces.
    stale_plan = [
        CellCalls(arm=grid.ARM, channel=channel.value, calls=(("claude", "-p", "a-stale-plan"),))
        for channel in grid.CHANNELS
    ]
    monkeypatch.setattr(grid, "planned_calls", lambda task, *, model: stale_plan)
    with pytest.raises(ValueError, match="no longer what its arms execute"):
        grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert not (out / "w-0.json").exists(), "a refused measurement was published anyway"


def _not_engaged_grid(
    task: ToolReqRealAgentTask, *, repeats: int, recorder: CellRecorder, **_kwargs: object
) -> list[grid.BuiltinCell]:
    """An `evaluate_task` stand-in returning a full but NON-separating grid, so a cache HIT and a
    cache MISS yield DIFFERENT headline numbers and the assertion can tell them apart instead of
    accidentally agreeing with the bug. It RECORDS the invocations the PLAN declares through the
    recorder: it stands in for an arm that ran, not for one that drifted (a double that recorded
    anything else is refused at the cache's write boundary, which is that check doing its job)."""
    for channel in grid.CHANNELS:
        _record_plan(recorder, task, channel, repeats)
    return [_cell(channel.value, passes=0, runs=2, engaged=0) for channel in grid.CHANNELS]


def test_a_partial_cell_grid_never_credits_a_both_channel_separation(
    tmp_path: Path, monkeypatch
) -> None:
    # A cache SHORT a channel must be a MISS: a one-channel record would satisfy "separated on BOTH
    # channels" while `trusted` was never evaluated — and on the PAID identity that verdict is
    # credited with zero `claude -p` calls made.
    tasks = _corpus_one(tmp_path)
    out = tmp_path / "out"
    truth = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert truth["separates_all_channels"] == 1  # both channels really do separate

    result_path = out / "w-0.json"
    record = json.loads(result_path.read_text(encoding="utf-8"))
    record["outcomes"] = record["outcomes"][:1]  # drop the `trusted` channel
    result_path.write_text(json.dumps(record), encoding="utf-8")

    monkeypatch.setattr(grid, "evaluate_task", _not_engaged_grid)
    summary = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert summary["executed"] == 1 and summary["reused"] == 0
    assert summary["separates_all_channels"] == 0  # re-measured, not replayed from half a grid
    assert len(json.loads(result_path.read_text())["outcomes"]) == len(grid.CHANNELS)


def test_a_duplicate_channel_cache_never_credits_a_both_channel_separation(
    tmp_path: Path, monkeypatch
) -> None:
    # The dual of the missing-channel case, and NOT caught by an arity check alone: two copies of
    # the `recalled` cell has the right count and the wrong coverage. `trusted` was never measured,
    # yet every kind is SEPARATES, so the both-channel headline would be credited off one channel
    # counted twice.
    tasks = _corpus_one(tmp_path)
    out = tmp_path / "out"
    grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)

    result_path = out / "w-0.json"
    record = json.loads(result_path.read_text(encoding="utf-8"))
    record["outcomes"] = [record["outcomes"][0], record["outcomes"][0]]
    result_path.write_text(json.dumps(record), encoding="utf-8")

    monkeypatch.setattr(grid, "evaluate_task", _not_engaged_grid)
    summary = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert summary["executed"] == 1 and summary["reused"] == 0
    assert summary["separates_all_channels"] == 0


def test_a_forged_leak_free_verdict_is_a_miss(tmp_path: Path, monkeypatch) -> None:
    # The verdict is DERIVED, so a persisted one may only be the one its rows imply. A record whose
    # rows say LEAK and whose verdict says SEPARATES agrees with the run on every other field —
    # identity intact, grid complete — so nothing else in it can refuse it. The summary counts KINDS
    # re-derived from the rows, so a forged verdict cannot reach it even if this check missed; both
    # locks are asserted below.
    tasks = _corpus_one(tmp_path)
    out = tmp_path / "out"
    grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)

    result_path = out / "w-0.json"
    record = json.loads(result_path.read_text(encoding="utf-8"))
    for row in record["outcomes"]:  # the rows now say LEAK...
        row["engaged"] = 0
        row["leaked"] = row["passes"]
    result_path.write_text(json.dumps(record), encoding="utf-8")  # ...but the verdict still says
    assert "SEPARATES" in record["verdict"]  # SEPARATES

    monkeypatch.setattr(grid, "evaluate_task", _not_engaged_grid)
    summary = grid.run_corpus(tasks, out_dir=out, repeats=2, model="", dry_run=True)
    assert summary["executed"] == 1 and summary["reused"] == 0
    assert summary["leaked"] == [] and summary["separates_all_channels"] == 0


# --- driver (scripts/grid_toolreq_builtin.py) -------------------------------------------

_SCRIPTS = str(Path(__file__).resolve().parents[1] / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import grid_toolreq_builtin as driver  # noqa: E402

_engaging_arm = _builtin_arm(engaged=True)


def test_driver_refuses_to_spend_without_token(tmp_path: Path, monkeypatch) -> None:
    _corpus_one(tmp_path)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("must NOT spawn claude when the spend gate fires")

    import membench.runner.toolreq_builtin as tb

    monkeypatch.setattr(tb.subprocess, "run", _boom)
    code = driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")])
    assert code == 2


def test_driver_refuses_to_spend_without_a_named_model(tmp_path: Path, monkeypatch) -> None:
    # mem-bzv2p: the model-side spend guard. A token is present (the OAUTH gate passes) but no model
    # is named — no --model, no MEMBENCH_AGENT_MODEL — so the run would key its cache identity on
    # "" (the CLI's own default) and serve one model's numbers as another's on resume. Exit 2 and
    # never spawn claude, and refuse BEFORE the preflight gate (which would itself spend).
    _corpus_one(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.delenv("MEMBENCH_AGENT_MODEL", raising=False)

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("must NOT spawn claude when the model gate fires")

    import membench.runner.toolreq_builtin as tb

    monkeypatch.setattr(tb.subprocess, "run", _boom)
    code = driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")])
    assert code == 2


def test_driver_refuses_to_spend_with_the_metered_api_key_set(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    # mem-9bh93: the metered-API contamination gate. Both prior gates PASS (a token and a model are
    # present), but ANTHROPIC_API_KEY is exported, and Claude Code prefers the API key, so the run
    # would silently bill the metered API AND cease to be the OAuth config the run claims (env
    # is invisible to the cache identity). Exit 2, never spawn claude, and say which var to unset.
    _corpus_one(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-be-refused")

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("must NOT spawn claude when the api-key gate fires")

    import membench.runner.toolreq_builtin as tb

    monkeypatch.setattr(tb.subprocess, "run", _boom)
    code = driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")])
    assert code == 2
    # Names ANTHROPIC_API_KEY, so this is THIS gate — not the token or model refusal, neither of
    # which mentions it. Absent the assertion, a gate placed after the token gate would still pass.
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_the_api_key_gate_fires_before_the_token_gate(tmp_path: Path, monkeypatch, capsys) -> None:
    # The api-key gate must precede the OAuth-token gate: a set key is a misconfiguration regardless
    # of the token, so refusing for it before the token go-command is printed keeps that disclosure
    # from telling a human to run a command that then refuses for a different reason (the same
    # ordering rationale the model gate is placed first under, mem-u9nu2). Token UNSET + key SET
    # must therefore surface the API-KEY refusal, not the token go-command.
    _corpus_one(tmp_path)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-be-refused")

    code = driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")])
    assert code == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_dry_run_is_unaffected_by_the_metered_api_key(tmp_path: Path, monkeypatch) -> None:
    # The gate is a PAID-path guard (`not args.dry_run and ...`): --dry-run spawns no claude and
    # bills nothing, so a stray ANTHROPIC_API_KEY (common in a CI shell) must not block a free run.
    _corpus_one(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-present-but-harmless-on-dry-run")
    code = driver.main(
        ["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out"), "--dry-run"]
    )
    assert code == 0  # proceeds past the gate and completes the simulated sweep


def test_an_unidentifiable_cli_version_refuses_before_the_preflight_spends(
    tmp_path: Path, monkeypatch
) -> None:
    # mem-84wwq: the third pre-spend refusal gate, alongside no-token and no-model. The live window
    # is a `claude` that serves `-p` fine but whose `--version` is unparseable or times out —
    # `resolve_cli_version` raises `HeadlessAgentError` for exactly that case, and the paid identity
    # stakes an invariant on it ("a paid run that cannot name its instrument must not spend"). The
    # version must therefore be read BEFORE the `before_first_spend` preflight fires its one real
    # establish+check cycle — else that cycle's `claude -p` calls burn before the halt. Locked at
    # the driver level because the driver owns its own `run_corpus` call, and the ordering (probe,
    # then the preflight hook that spends inside `run_cached_corpus`) is a property of that call.
    _corpus_one(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)

    def _unidentifiable() -> str:
        raise HeadlessAgentError("claude --version printed no recognisable version")

    monkeypatch.setattr(grid, "resolve_cli_version", _unidentifiable)

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("must NOT spend a preflight `claude -p` before the version is named")

    monkeypatch.setattr(grid, "run_builtin_arm", _boom)
    code = driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")])
    assert code == 3  # a diagnosed halt, and — via `_boom` — not a single paid call


def test_go_command_refuses_a_factorization_that_misdescribes_its_own_total(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """mem-663ga: the disclosure prints ONE `calls/repeat` factor for the whole corpus. If the leg
    count ever varies by task that factor cannot multiply out to the summed total, so the human
    reads a factorization that disagrees with the number it explains. Refuse to print it rather
    than disclose a spend nobody can check."""
    tasks = [_task("w-0"), _task("w-1")]
    monkeypatch.setattr(grid, "cell_legs", _legs_by_task({"w-0": 2, "w-1": 3}))

    with pytest.raises(ValueError, match="non-uniform calls/repeat"):
        driver._print_go_command(tasks, 1, tmp_path / "out", tmp_path / "corpus", "sonnet")
    assert "real `claude -p` call(s)" not in capsys.readouterr().out  # refused, not printed


def test_go_command_on_an_empty_corpus_says_so(tmp_path: Path) -> None:
    # main() refuses an empty corpus before it ever discloses a cost, so this is a caller-contract
    # violation. It still must not read as "non-uniform calls/repeat []", which describes nothing.
    with pytest.raises(ValueError, match="no tasks"):
        driver._print_go_command([], 1, tmp_path / "out", tmp_path / "corpus", "sonnet")


def test_the_pre_sweep_banner_refuses_a_factorization_that_misdescribes_its_own_total(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """mem-de455: the guard above protects the REFUSE path (``_print_go_command``, reached only when
    the token is unset — the path that spends NOTHING). main()'s pre-sweep banner is on the
    AUTHORIZED path: on a paid run the go-command never fires, so the banner is the FIRST surface to
    disclose the sweep's shape, and it printed at the moment real money starts moving. It modelled
    ``calls/repeat`` off ``tasks[0]`` unguarded, so a non-uniform corpus would misstate the sweep as
    it begins. Drive the banner through ``main(--dry-run)`` (the same banner line, no tokens) with a
    corpus whose leg count branches per task: it must refuse here too, exactly like the disclosure.

    A uniform-corpus test cannot fail on this (the tasks[0] model and the summed total agree when
    every task has the same leg count) — which is how this shape shipped three times under a green
    suite. Only the branching ``_legs_by_task`` double separates them."""
    _corpus(tmp_path, "w-0", "w-1")
    monkeypatch.setattr(grid, "cell_legs", _legs_by_task({"w-0": 2, "w-1": 3}))

    with pytest.raises(ValueError, match="non-uniform calls/repeat"):
        driver.main(
            [
                "--corpus-dir",
                str(tmp_path / "corpus"),
                "--out",
                str(tmp_path / "out"),
                "--dry-run",
            ]
        )
    # Refused before it printed: the lying banner line never reached stdout, and the dry-run sweep
    # that follows it never ran.
    assert "toolreq builtin-arm sweep" not in capsys.readouterr().out


def test_repeats_below_one_is_refused_at_the_flag(tmp_path: Path) -> None:
    # `--repeats 0` runs zero agent turns per cell and would persist 0/0 rows that the verdict rule
    # reads as a confident NOT-ENGAGED for a task that was NEVER EVALUATED. The schema refuses the
    # record (repeats/runs are both >= 1); the flag refuses it first, with a message that says why.
    _corpus_one(tmp_path)
    with pytest.raises(SystemExit) as exit_info:
        driver.main(
            [
                "--corpus-dir",
                str(tmp_path / "corpus"),
                "--out",
                str(tmp_path / "out"),
                "--repeats",
                "0",
                "--dry-run",
            ]
        )
    assert exit_info.value.code == 2


def test_preflight_halts_when_native_memory_never_engages(tmp_path: Path, monkeypatch) -> None:
    _corpus_one(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)

    monkeypatch.setattr(grid, "run_builtin_arm", _builtin_arm(passes=False, engaged=False))
    code = driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")])
    assert code == 3


def test_preflight_agent_error_halts_diagnosed_not_raw_traceback(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    # The most likely REAL preflight failure is an erroring/flaky/timed-out `claude -p` call
    # (HeadlessAgentError), not a clean not-engaged diagnosis. main() must convert it into the
    # documented diagnosed PREFLIGHT HALT (exit 3), never let a raw traceback propagate out.
    _corpus_one(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)

    def _raises(task, **_kwargs):
        raise HeadlessAgentError("claude -p failed: simulated rate-limit")

    monkeypatch.setattr(grid, "run_builtin_arm", _raises)
    code = driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")])
    assert code == 3
    err = capsys.readouterr().err
    assert "PREFLIGHT HALT" in err
    assert "SWEEP HALT" not in err  # the preflight's own counsel, not the mid-sweep one
    assert "simulated rate-limit" in err  # the halt carries the underlying failure


def test_preflight_contaminated_sandbox_halts_diagnosed_not_raw_traceback(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    # A contaminated ancestor chain refuses at the sandbox MINT, which is inside the preflight —
    # so it must arrive as the diagnosed PREFLIGHT HALT, not a raw traceback. It gets its own kind
    # rather than riding AGENT_ERROR: nothing was called, so "the real establish/goal call failed"
    # would name a call that never happened, and the operator's fix is TMPDIR. It must also not
    # borrow the mid-sweep SWEEP HALT counsel, which points at a resume that has nothing to skip.
    _corpus_one(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)

    def _raises(task, **_kwargs):
        raise SandboxContaminationError("/evil/CLAUDE.md sits above the sandbox ... set TMPDIR")

    monkeypatch.setattr(grid, "run_builtin_arm", _raises)
    code = driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")])
    assert code == 3
    err = capsys.readouterr().err
    assert "PREFLIGHT HALT" in err
    assert "SWEEP HALT" not in err  # nothing was measured, so nothing is resumable
    assert "/evil/CLAUDE.md" in err  # carries the offending path through to the operator
    # Routed to its OWN counsel, not the agent-error one: the kind is an internal key, so the
    # counsel it selects is what proves the routing. This halt's fix is TMPDIR, and it must not
    # tell the operator to "retry once the underlying failure is resolved" — nothing failed.
    assert "TMPDIR" in err
    assert "retry once the underlying failure" not in err


def test_sweep_agent_error_halts_diagnosed_with_resume_pointer(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    # The preflight is not the only paid boundary: a HeadlessAgentError mid-sweep (the rate-limit at
    # paid call 50 of 180) must get the same diagnosed-halt treatment — exit 3, pointing at the
    # persisted per-task results for a cheap resume — never a raw traceback during the expensive
    # phase, and never under the PREFLIGHT HALT counsel (which says nothing was measured).
    #
    # Preflight and sweep both spend through `grid.run_builtin_arm` now, so "the preflight passed
    # and the sweep then died" is a double that succeeds ONCE and raises after — not two patches.
    _corpus_one(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)

    def _passes_once_then_raises(task, **kwargs):
        if not calls:
            calls.append("preflight")
            return _engaging_arm(task, **kwargs)
        raise HeadlessAgentError("claude -p failed: simulated mid-sweep rate-limit")

    calls: list[str] = []
    monkeypatch.setattr(grid, "run_builtin_arm", _passes_once_then_raises)
    code = driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")])
    assert code == 3
    err = capsys.readouterr().err
    assert "SWEEP HALT" in err
    assert "PREFLIGHT HALT" not in err  # the preflight passed; this is the mid-sweep boundary
    assert "simulated mid-sweep rate-limit" in err  # carries the underlying failure
    assert "re-run" in err  # and points at the resume path


def test_sweep_contaminated_sandbox_halts_diagnosed_not_raw_traceback(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    # The ancestor guard fires at TWO moments, and only one of them was routed. The mint-time
    # scan is covered by the preflight gate's conversion, but the post-wipe re-check raises
    # MID-SWEEP — the establish leg is unclamped, so it can plant an ancestor CLAUDE.md that
    # no construction-time scan could have seen. SandboxContaminationError is a sibling
    # RuntimeError of PreflightHaltError and HeadlessAgentError, so neither existing arm
    # catches it: without routing, the ONE contamination the post-wipe re-check exists to
    # catch ends as a raw traceback, after real money is spent, with the CONTAMINATED_SANDBOX
    # counsel unreachable on the only path that spends before it can fire.
    _corpus_one(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)

    def _passes_once_then_contaminates(task, **kwargs):
        if not calls:
            calls.append("preflight")
            return _engaging_arm(task, **kwargs)
        raise SandboxContaminationError(
            "/evil/CLAUDE.md sits above the sandbox ... Set TMPDIR to a directory with no ..."
        )

    calls: list[str] = []
    monkeypatch.setattr(grid, "run_builtin_arm", _passes_once_then_contaminates)
    code = driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")])
    assert code == 3  # diagnosed halt, not an uncaught traceback's exit 1
    err = capsys.readouterr().err
    assert "SWEEP HALT" in err
    assert "PREFLIGHT HALT" not in err  # the preflight passed; this is the mid-sweep boundary
    assert "/evil/CLAUDE.md" in err  # carries the offending path
    assert "TMPDIR" in err  # and routes to the operator fix, not a code one


def test_preflight_proceeds_when_engaged(tmp_path: Path, monkeypatch) -> None:
    _corpus_one(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)

    calls: list[str] = []
    monkeypatch.setattr(grid, "run_builtin_arm", _builtin_arm(calls, engaged=True))
    code = driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")])
    assert code == 0
    # once for the preflight + once per (task x channel) cell in the sweep
    assert len(calls) == 1 + len(grid.CHANNELS)


def test_skip_preflight_bypasses_the_real_preflight_call(tmp_path: Path, monkeypatch) -> None:
    _corpus_one(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)

    calls: list[str] = []
    monkeypatch.setattr(grid, "run_builtin_arm", _builtin_arm(calls, engaged=True))
    code = driver.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--out",
            str(tmp_path / "out"),
            "--skip-preflight",
        ]
    )
    assert code == 0
    # no +1 for a preflight call — only the sweep's per-channel cells
    assert len(calls) == len(grid.CHANNELS)


def test_the_driver_writes_the_summary_the_grid_reserves(tmp_path: Path, monkeypatch) -> None:
    # The summary lands in the SAME directory as the per-task results, so its name is one the tasks
    # are not allowed to claim (resume_cache.assert_usable_work_ids). Driver and grid must therefore
    # agree on that name — a second copy of the string is how a task quietly overwrites the summary,
    # or the summary a task's result.
    _corpus_one(tmp_path)
    out = tmp_path / "out"
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)
    monkeypatch.setattr(grid, "run_builtin_arm", _engaging_arm)

    assert driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(out)]) == 0
    assert (out / grid.SUMMARY_NAME).is_file()


def test_a_fully_cache_served_resume_spends_nothing(tmp_path: Path, monkeypatch) -> None:
    """Regression test for mem-dblue: a fully cache-served resume must fire ZERO paid `claude -p`
    calls, preflight included. The driver used to preflight before the cache was ever consulted, so
    every resume attempt re-spent 2 real calls (worst case ~20 min) on a measurement it discarded —
    waste proportional to the resume attempts the cache exists to make free.

    The mem-xe2p mechanism-fires gate still holds: nothing is measured here, so nothing needs it."""
    args = ["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")]
    _corpus(tmp_path, "w-0", "w-1")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)

    first: list[str] = []
    monkeypatch.setattr(grid, "run_builtin_arm", _builtin_arm(first, engaged=True))
    assert driver.main(args) == 0
    assert first, "the cold run must spend — otherwise the resume proves nothing"

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("a fully cache-served resume must not spend a single paid call")

    monkeypatch.setattr(grid, "run_builtin_arm", _boom)
    assert driver.main(args) == 0


def test_a_partial_resume_preflights_exactly_once(tmp_path: Path, monkeypatch) -> None:
    # The other half of the gate: a resume that still has a task to measure DOES spend the preflight
    # — once, not once per remaining task — so the mechanism check keeps protecting every run that
    # actually measures something.
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)
    out = tmp_path / "out"

    _corpus(tmp_path, "w-0")
    monkeypatch.setattr(grid, "run_builtin_arm", _builtin_arm(engaged=True))
    assert driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(out)]) == 0

    # A second task joins the corpus: w-0 is served from the cache, w-1 must be measured.
    resumed = tmp_path / "resumed"
    _corpus(resumed, "w-0", "w-1")
    calls: list[str] = []
    monkeypatch.setattr(grid, "run_builtin_arm", _builtin_arm(calls, engaged=True))
    assert driver.main(["--corpus-dir", str(resumed / "corpus"), "--out", str(out)]) == 0
    # one preflight + w-1's cells only; w-0's cells were reused
    assert len(calls) == 1 + len(grid.CHANNELS)


def test_a_preflight_leak_is_not_reported_as_a_mechanism_that_never_fired(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """``engaged == 0`` is one bit short, and the two bits want opposite responses from a human.

    A bool gate read BOTH `engaged=0, leaked=1` — the goal leg PASSED without native memory, so the
    sandbox cwd firewall handed the answer over, the most severe thing this arm can find — and
    `engaged=0, leaked=0` as "the mechanism genuinely did not fire". For the leak that is FALSE, and
    the driver's counsel told the operator to accept it as the arm's own finding rather than go fix
    the isolation that invalidates every cell the sweep would measure."""
    _corpus_one(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token-for-test")
    monkeypatch.setenv("MEMBENCH_AGENT_MODEL", "sonnet")  # paid path must name a model (mem-bzv2p)
    monkeypatch.setattr(grid, "run_builtin_arm", _builtin_arm(engaged=False, leaked=True))

    assert (
        driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")]) == 3
    )
    err = capsys.readouterr().err
    assert "PASSED without engaging native memory" in err
    assert "ISOLATION" in err  # the leak's counsel: fix the firewall
    assert "genuinely did not fire" not in err  # NOT the never-fired counsel


# --- the recorder is structure, not caller discipline (mem-swp43 review reject) --------


def test_cell_agent_requires_an_explicit_runner() -> None:
    """The reject: the recording seam was caller discipline. ``cell_agent`` defaulted ``runner`` to
    ``subprocess.run``, so a new execution leg built the idiomatic way — ``cell_agent(model=...,
    channel=...)`` — spawned a REAL, unrecorded ``claude -p``: never folded by ``one_cycle``, never
    checked at the write boundary, published under the wrong fingerprint with a green suite.

    With ``runner`` required, that reflex path is a construction-time error, not a silent real
    spawn. An executing caller must hand in its ``RecordingRunner``; the only other caller (the
    non-executing render path) passes an explicit sentinel."""
    with pytest.raises(TypeError):
        cell_agent(model="", channel=MemoryChannel.TRUSTED)  # type: ignore[call-arg]


def test_headless_claude_agent_requires_a_runner() -> None:
    """The reject, one construction site DOWN: ``cell_agent`` is a wrapper, and guarding only it
    still left ``HeadlessClaudeAgent(...)`` — the class that actually spawns — defaulting ``runner``
    to ``subprocess.run``. Constructing it directly (already precedented at
    ``scripts/smoke_realrun_trajectory.py``) reproduced the unrecorded-execution defeat verbatim.
    The default is gone from the executing class itself, so no construction path — wrapper or direct
    — can run a leg through an unrecorded agent by omission."""
    from membench.runner.headless_agent import HeadlessClaudeAgent

    with pytest.raises(TypeError):
        HeadlessClaudeAgent(model="")  # type: ignore[call-arg]


def test_render_only_runner_refuses_to_execute() -> None:
    """The render path builds an agent only to call ``argv_for`` (pure — no spawn). Its sentinel
    runner makes that explicit: if a future edit ever drives the render agent to actually execute,
    it crashes loudly instead of issuing an untracked real call."""
    with pytest.raises(RuntimeError, match="render argv only"):
        _render_only_runner(["claude", "-p", "x"])


def test_render_cell_calls_never_spawns() -> None:
    """``render_cell_calls`` renders the plan for the fingerprint and must stay side-effect free
    even though it now holds a real-looking agent: it only reads ``argv_for``, never runs the
    sentinel."""
    task = _task()
    establish, goal = cell_legs(task)
    rendered = render_cell_calls(
        arm=ARM, channel=MemoryChannel.TRUSTED, legs=[establish, goal], model=""
    )
    assert len(rendered.calls) == 2  # establish + goal argv, no execution


def test_a_leg_is_hashable_despite_unhashable_fields() -> None:
    """``Leg`` carries a non-frozen pydantic ``step`` and a dict ``memory`` — both unhashable —
    under ``frozen=True``. ``hash=False`` on those fields keeps the auto ``__hash__`` from raising
    the first time a ``Leg`` lands in a set, while value ``__eq__`` still spans all three fields."""
    establish, goal = cell_legs(_task())
    assert len({establish, goal, establish}) == 2  # hashing works; the dup collapses


# --- the disclosed paid cost is derived from the legs, not a hand-written constant -----


def test_calls_per_repeat_is_the_leg_count() -> None:
    task = _task()
    assert grid.calls_per_repeat(task) == len(cell_legs(task)) == 2


def test_paid_call_count_scales_with_the_legs(monkeypatch) -> None:
    """The reject's second half: ``CALLS_PER_REPEAT = 2`` was a hand-written model of the leg count
    driving the refuse-to-spend money disclosure. Add a leg — which now correctly moves the argv and
    the fingerprint — and a literal ``2`` under-reports the spend the human authorizes. Derived from
    ``cell_legs``, the disclosed count tracks it."""
    tasks = [_task("w-0"), _task("w-1")]
    two_legs = grid.paid_call_count(tasks, repeats=3)
    assert two_legs == len(grid.CHANNELS) * 3 * 2 * len(tasks)

    # `calls_per_repeat` resolves `cell_legs` in the grid module's namespace, so patch it there.
    monkeypatch.setattr(grid, "cell_legs", _legs_by_task({"w-0": 3, "w-1": 3}))
    three_legs = grid.paid_call_count(tasks, repeats=3)
    assert three_legs == len(grid.CHANNELS) * 3 * 3 * len(tasks)
    assert three_legs > two_legs  # the disclosure moved with the leg, not stuck at 2


def test_paid_call_count_is_exact_when_the_leg_count_varies_by_task(monkeypatch) -> None:
    """mem-663ga: ``n_tasks x len(CHANNELS) x repeats x calls_per_repeat(tasks[0])`` reads the FIRST
    task's leg count and bills every other task at it. The disclosed number is what the human
    authorizes the spend against, so it must be the exact sum, not a model of it that happens to be
    right while the corpus is uniform."""
    tasks = [_task("w-0"), _task("w-1")]
    monkeypatch.setattr(grid, "cell_legs", _legs_by_task({"w-0": 2, "w-1": 3}))

    exact = len(grid.CHANNELS) * 1 * sum(grid.calls_per_repeat(task) for task in tasks)
    assert exact == 10  # 2 channels x 1 repeat x (2 + 3) legs
    # The regression form returns 8 here — a silent 20% under-report of real money.
    assert grid.paid_call_count(tasks, repeats=1) == exact


def test_paid_call_count_of_an_empty_corpus_is_zero() -> None:
    assert grid.paid_call_count([], repeats=3) == 0


# --- the permission gate on the unconstrained establish leg (mem-5yobo) -------------------
#
# H3 is INTENTIONAL and load-bearing: the establish leg passes `available_tools=[]`, so no
# `--allowedTools` clamp is put on Claude Code's own memory-write path. That is the hypothesis
# the builtin arm exists to test and it is NOT what these pin.
#
# What they pin is the thing actually holding the blast radius, which today is held by nothing
# executable: corpus-authored text flows verbatim into that unconstrained prompt under a header
# telling the agent to treat it as fact, and `headless_agent.run_step` hands the child
# `{**os.environ, **self.env}` — the OAuth token included. The default permission gate is what
# stands between that and a hostile `sequences.json`, and it is one flag away.
#
# NOTE ON WHAT THESE ARE WORTH: no bypass flag appears anywhere in this repo today, so these are
# green by construction. They are regression pins against a FUTURE edit, not evidence of a hole
# that was open. Both routes to the same blast radius are covered, because only one goes through
# argv: a `permissions` key in the seeded settings.json would never touch a command line.

_BYPASS_FLAGS = (
    "--dangerously-skip-permissions",
    "--permission-mode",
    "bypassPermissions",
    "acceptEdits",
)


@pytest.mark.parametrize("channel", [MemoryChannel.RECALLED, MemoryChannel.TRUSTED])
def test_no_bypass_flag_reaches_the_argv_of_any_leg(channel) -> None:
    # Rendered through `cell_calls` -> `render_cell_calls` -> the same `cell_agent`/`argv_for` the
    # arm executes through, so this reads the real command lines and not a model of them.
    for argv in cell_calls(_task(), channel, model="sonnet").calls:
        flat = " ".join(argv)
        for flag in _BYPASS_FLAGS:
            assert flag not in flat, f"{flag} reached the argv: {argv}"


def test_the_establish_leg_is_unconstrained_but_not_permission_bypassed() -> None:
    """The two halves of H3, pinned together so neither can drift into the other.

    Unconstrained (no `--allowedTools`) is the hypothesis and must STAY. Permission-bypassed is
    not part of it and must never arrive — the absence of the clamp is exactly why the gate below
    it has to hold."""
    establish = cell_calls(_task(), MemoryChannel.RECALLED, model="sonnet").calls[0]
    assert "--allowedTools" not in establish  # H3 intact
    for flag in _BYPASS_FLAGS:
        assert flag not in " ".join(establish)


def test_the_seeded_settings_carry_no_permissions_key() -> None:
    """The route to the same blast radius that never touches argv: `_seed_config_dir` writes
    BUILTIN_SETTINGS into the establish leg's CLAUDE_CONFIG_DIR, so a permissions block added
    there would widen the unconstrained leg without any command line moving."""
    assert set(BUILTIN_SETTINGS) == {"autoMemoryEnabled"}


# --- the go-command prices THIS fire, not the whole corpus (mem-u9nu2) -------------------


def test_the_go_command_prices_the_work_that_remains_not_the_whole_corpus(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """THE bead, end to end. The refuse-to-spend gate fires BEFORE the sweep, so it used to name the
    only cost it could see — the whole corpus — while a resume re-measures only what is not cached.
    On a mostly-served `--out` that number describes work that will not be done, and it is the
    number a human authorizes real money against.

    Two of three tasks are pre-measured under the SAME paid identity the driver will price, so the
    disclosure must name the ONE that remains and keep the cold cost visible as what it is."""
    tasks = _corpus(tmp_path, "w-0", "w-1", "w-2")
    out = tmp_path / "out"
    monkeypatch.setattr(grid, "run_builtin_arm", _engaging_arm)
    seeded = grid.run_corpus(tasks[:2], out_dir=out, repeats=1, model="sonnet", dry_run=False)
    assert seeded["executed"] == 2

    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    code = driver.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--out",
            str(out),
            "--repeats",
            "1",
            "--model",
            "sonnet",
        ]
    )
    assert code == 2  # refused to spend — the gate that prints the disclosure
    printed = capsys.readouterr().out

    remaining = grid.paid_call_count(tasks[2:], repeats=1)
    cold = grid.paid_call_count(tasks, repeats=1)
    assert (
        remaining < cold
    ), "the fixture must actually have work left to skip, or this proves nothing"
    assert (
        f"COST OF THIS FIRE: {remaining} real `claude -p` call(s) over the 1 of 3 task(s)"
        in printed
    )
    assert "2 task(s) are already cached" in printed
    # The cold number stays, labeled as the whole corpus — it is what a fresh --out costs, and
    # dropping it would hide the ceiling the remaining count is conditional on.
    assert f"A COLD --out is {cold} real" in printed
    # ...and the command that spends pins the model the count was priced under (else the disclosure
    # prices one identity and the fire runs another: `model` is an identity field).
    assert "--model sonnet" in printed
    assert "WHAT THAT COUNT ASSUMES" in printed


def test_the_go_command_says_a_fully_cached_resume_spends_nothing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """The bead's scenario at its limit. Its own branch rather than a `0 calls` line, because zero
    is also what the PREFLIGHT costs here — `before_first_spend` fires before the first task
    actually measured, and there is none (mem-dblue) — and a human deciding whether to re-fire
    needs that said, not inferred."""
    tasks = _corpus(tmp_path, "w-0", "w-1")
    out = tmp_path / "out"
    monkeypatch.setattr(grid, "run_builtin_arm", _engaging_arm)
    grid.run_corpus(tasks, out_dir=out, repeats=1, model="sonnet", dry_run=False)

    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    driver.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--out",
            str(out),
            "--repeats",
            "1",
            "--model",
            "sonnet",
        ]
    )
    printed = capsys.readouterr().out
    assert "THIS FIRE SPENDS NOTHING: all 2 task(s) are already cached" in printed
    assert "The PREFLIGHT does not fire either" in printed
    # "spends nothing" is a COUNT, and the largest under-report available here if the identity
    # moves: every cell called cached is re-measured, so the fire spends the whole corpus.
    assert "WHAT THAT COUNT ASSUMES" in printed


def test_the_go_command_falls_back_to_the_cold_ceiling_when_the_binary_cannot_be_named(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """A paid cell's identity NAMES the binary it was measured on, so without one there is no
    identity to ask the cache what a resume would reuse — and no honest remaining count.

    The fallback is the cold cost, labeled UNKNOWN and explained: strictly SAFE (it over-discloses,
    the direction this disclosure had for every resume before mem-u9nu2) and never silent. What it
    must NOT do is drop the go-command: the operator came here for it, and the probe is an
    improvement to the disclosure, not a precondition of it."""
    _corpus(tmp_path, "w-0")

    def _unidentifiable() -> str:
        raise HeadlessAgentError("claude --version printed no recognisable version")

    monkeypatch.setattr(grid, "resolve_cli_version", _unidentifiable)  # beats the autouse stub
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    code = driver.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--out",
            str(tmp_path / "out"),
            "--repeats",
            "1",
            "--model",
            "sonnet",
        ]
    )
    assert code == 2
    printed = capsys.readouterr().out
    assert "COST OF THIS FIRE: UNKNOWN" in printed
    assert "UPPER BOUND" in printed
    assert "A COLD --out is" in printed
    assert "scix-batch -- env CLAUDE_CODE_OAUTH_TOKEN=..." in printed  # the go-command survives
    # ...and the count's caveat does NOT ride along: it caveats a count, and this branch printed
    # none. A paragraph explaining what "the count above" assumes, under a branch with no count
    # above, asserts something its own output does not hold.
    assert "WHAT THAT COUNT ASSUMES" not in printed


def test_an_unpinned_paid_run_is_refused_before_a_go_command_it_could_not_price(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """The model gate fires BEFORE the token gate (mem-u9nu2), and both halves of that matter.

    It is true regardless of the token, so the old order printed a go-command telling the human to
    fire a command that would immediately refuse for a DIFFERENT reason. And `model` is an identity
    field: with none resolved there is no paid identity, so the disclosure could not have priced the
    fire even if it wanted to — refusing here is what lets the go-command below always pin one."""
    _corpus(tmp_path, "w-0")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv(ENV_MODEL, raising=False)

    code = driver.main(["--corpus-dir", str(tmp_path / "corpus"), "--out", str(tmp_path / "out")])

    assert code == 2
    printed = capsys.readouterr().out
    assert "REFUSING to spend: no model named" in printed
    assert "scix-batch" not in printed, "priced nothing, so it must not print a go-command"


# --- ancestor firewall: the sandbox's PARENT CHAIN is not a third continuity channel ----


def _never_spent_runner(argv: Sequence[str], **kwargs: object) -> NoReturn:
    """For the refuse-at-MINT cases, where the guard fires before any leg runs. Asserting the
    refusal alone would leave "refuses to SPEND" an implication; this makes it a claim the test
    can fail on, and keeps a scavenging runner from implying legs that never execute."""
    raise AssertionError(
        f"the guard refused at the mint, so no `claude -p` should have been spawned — got {argv}"
    )


def _ancestor_scavenging_runner(value: str, *, plant: bool):
    """The SILENT shape, which is the one that matters. The establish leg genuinely engages
    native memory (the real index+topic layout), so ``engaged`` is True and honest; the goal
    leg then passes off an ancestor ``CLAUDE.md`` WITHOUT native memory re-surfacing
    anything. Claude Code walks UP from cwd at launch, so an ancestor file is auto-loaded
    exactly like an in-cwd one, with no tool call to clamp.

    The arm's own honest verdict for this runner is a builtin NULL — memory was written and
    did not carry — but pass+engaged scores as SEPARATES, a fabricated builtin win, because
    ``leaked`` only fires on (pass AND NOT engaged). An establish leg that merely scavenged
    without engaging would show up as leaked, loud and correct; this is the shape the
    accounting is blind to, and the reason the guard is fail-closed rather than recorded.

    ``plant`` makes the unclamped establish leg write that ancestor file itself (the
    between-legs window ``wipe_cwd_contents`` covers for the cwd but structurally cannot
    cover for a parent); otherwise the ancestor is the operator's, via ``TMPDIR``."""

    def run(argv, **kwargs):
        argv_list = list(argv)
        cwd = kwargs.get("cwd")
        env = kwargs.get("env")
        assert isinstance(cwd, str)
        scavengeable = Path(cwd).parent / "CLAUDE.md"
        events: list[dict[str, object]] = []
        if "--allowedTools" not in argv_list:  # establish leg
            config_dir = env.get("CLAUDE_CONFIG_DIR") if isinstance(env, dict) else None
            assert isinstance(config_dir, str)
            # Engage native memory for real, in the real layout: this is what makes the
            # scavenged pass below score as a clean win instead of a leak.
            index_path = Path(native_memory_path(config_dir=config_dir, workdir=cwd))
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(f"- [Established]({SIMULATED_TOPIC_FILE})\n", encoding="utf-8")
            (index_path.parent / SIMULATED_TOPIC_FILE).write_text(value, encoding="utf-8")
            if plant:
                scavengeable.write_text(f"remember: {value}", encoding="utf-8")
        elif scavengeable.is_file() and value in scavengeable.read_text(encoding="utf-8"):
            events.append(  # goal leg: passes off the ancestor file, never touching memory
                assistant_event([(REAL_TOOL, {"file_path": CONFIG_FILE, "content": value})])
            )
        events.append(result_event())
        stdout = serialize_stream(events)
        return subprocess.CompletedProcess(argv_list, returncode=0, stdout=stdout, stderr="")

    return run


def test_wipe_cannot_reach_an_ancestor_claude_md(tmp_path: Path) -> None:
    # Locks the STRUCTURAL claim that makes the ancestor guard a separate defense rather
    # than a wider wipe: `wipe_cwd_contents` iterates cwd.iterdir(), which by construction
    # never ascends. Emptying the cwd is still right (the slug, hence the memory path, must
    # survive) — it just cannot be where the parent chain is handled.
    ancestor = tmp_path / "CLAUDE.md"
    ancestor.write_text("scavenge me", encoding="utf-8")
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "CLAUDE.md").write_text("in the cwd", encoding="utf-8")

    wipe_cwd_contents(sandbox)

    assert list(sandbox.iterdir()) == []  # the cwd channel: closed
    assert ancestor.is_file()  # the ancestor channel: untouched, and unreachable from here


def test_a_contaminated_ancestor_chain_refuses_to_spend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The bead's own case: TMPDIR points somewhere with a CLAUDE.md above it (pointing
    # TMPDIR at a workspace for disk space is routine, and this box has a CLAUDE.md at both
    # /home/ds/projects/mem and /home/ds/projects). Claude Code auto-loads it into EVERY
    # "neutral" sandbox at launch, so the arm's whole premise — that native memory is the
    # SOLE continuity channel — is silently false, and the accounting cannot see it:
    # `engaged` is read off the establish leg and `leaked` only fires on (pass AND NOT
    # engaged), so a scavenged pass publishes as a clean builtin SEPARATES. Refuse to
    # spend rather than measure something the harness cannot describe.
    (tmp_path / "CLAUDE.md").write_text("remember: toolreq-w-t0-CURRENT", encoding="utf-8")
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    task = _task()

    with pytest.raises(SandboxContaminationError) as exc:
        run_builtin_arm(
            task,
            repeats=2,
            model="",
            dry_run=False,
            channel=MemoryChannel.RECALLED,
            runner=_never_spent_runner,
            recorder=CellRecorder(),
        )
    assert str(tmp_path / "CLAUDE.md") in str(exc.value)  # names the offending path
    assert "TMPDIR" in str(exc.value)  # and the knob that fixes it


def test_an_establish_leg_that_plants_an_ancestor_claude_md_cannot_reach_the_goal_leg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The construction-time scan is not enough on its own. The establish leg is
    # deliberately unclamped (available_tools=[], so no --allowedTools), which is why
    # `wipe_cwd_contents` runs BETWEEN the legs rather than at construction — and the same
    # window is open one directory up, where the wipe cannot reach. A leg that writes an
    # ancestor CLAUDE.md *and* engages native memory would otherwise publish as SEPARATES
    # (engaged=True, pass), the exact silent inflation this arm exists to avoid. So the
    # guard runs again after the wipe: refuse to PUBLISH, the calls already being spent.
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    task = _task()
    (current_opaque,) = task.current_opaque_values

    # repeats=1 is load-bearing, not incidental: with a second repeat, repeat 1's plant is
    # still sitting above the sandbox when repeat 2 MINTS, so the construction-time guard
    # catches it and this test passes even with the post-wipe call deleted — locking the
    # wrong guard. One repeat leaves the post-wipe call as the only thing that can raise.
    with pytest.raises(SandboxContaminationError):
        run_builtin_arm(
            task,
            repeats=1,
            model="",
            dry_run=False,
            channel=MemoryChannel.RECALLED,
            runner=_ancestor_scavenging_runner(current_opaque, plant=True),
            recorder=CellRecorder(),
        )


def test_a_clean_ancestor_chain_under_a_relocated_tmpdir_still_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The guard is on CONTAMINATION, never on WHERE the sandbox lives: pointing TMPDIR at a
    # roomier disk is a legitimate thing the bead itself names, and it moves nothing that is
    # measured (argv carries no cwd, and the scored artifact is a cwd-relative path). Pinning
    # a harness-owned root instead would break this case to defend an input that, once the
    # chain is guaranteed clean, cannot vary the measurement at all.
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    task = _task()
    (current_opaque,) = task.current_opaque_values

    outcome, diag = run_builtin_arm(
        task,
        repeats=2,
        model="",
        dry_run=False,
        channel=MemoryChannel.RECALLED,
        runner=_ancestor_scavenging_runner(current_opaque, plant=False),
        recorder=CellRecorder(),
    )
    # The arm's honest verdict for this runner, now that there is nothing to scavenge: the
    # builtin engaged and did not carry. A null, not a fabricated win.
    assert outcome.passes == 0
    assert diag.engaged == 2
    assert diag.leaked == 0


def test_the_guard_walks_the_real_chain_of_a_symlinked_tmpdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # TMPDIR resolving THROUGH a symlink is the case a naive walk misses: `tempfile` hands
    # back a path under the link, whose lexical parents are clean, while the kernel's cwd is
    # the real inode — so Claude Code walks the REAL chain and loads the CLAUDE.md the guard
    # just declared absent. The scan must resolve() first, or it is green precisely when it
    # is wrong.
    #
    # The GEOMETRY is the whole test. Planting CLAUDE.md inside the symlink TARGET proves
    # nothing: `<link>/CLAUDE.md` stats straight through the link, so an unresolved walk
    # finds it too and the test passes with resolve() deleted — green exactly when it is
    # wrong, the very failure it is named for. The file must sit where the REAL chain and
    # the LEXICAL chain DISAGREE: in the target's PARENT, which only resolve() reaches.
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    (hidden / "CLAUDE.md").write_text("remember: toolreq-w-t0-CURRENT", encoding="utf-8")
    real = hidden / "real"
    real.mkdir()
    link = tmp_path / "link"  # lexical parents: tmp_path/link, tmp_path — both clean
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setattr(tempfile, "tempdir", str(link))
    task = _task()

    with pytest.raises(SandboxContaminationError):
        run_builtin_arm(
            task,
            repeats=2,
            model="",
            dry_run=False,
            channel=MemoryChannel.RECALLED,
            runner=_never_spent_runner,
            recorder=CellRecorder(),
        )
