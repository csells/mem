"""mem-rk41.3.2 — builtin native-memory persistent-env arm for the tool-requiring real-agent grid.

Completes the ours-vs-builtin verdict's third leg (none/oracle staged in mem-rk41.3;
``ours`` in mem-rk41.3.1): does the agent's OWN native-memory feature carry a fact
across two sequential ``claude -p`` calls with no external memory system at all?

Two calls per repeat, sharing ONE sandbox cwd + ONE ``CLAUDE_CONFIG_DIR`` (so Claude
Code's own native memory is the sole continuity channel):

0. **mint** — the shared cwd comes from ``sandbox.paid_sandbox``, which fail-closes before
   any call if the ancestor chain is not neutral. The wipe below is the cwd's firewall and
   structurally cannot substitute for it; see ``sandbox`` for why (mem-rx11w).
1. **establish** — the id-exact facts (``task.oracle_memory``, opaque-valued like the
   oracle arm) are surfaced via ``available_memory`` under the TRUSTED/RECALLED channel,
   with an explicit instruction to retain them for later. That instruction makes this the
   usability CEILING, so a null reads as "the mechanism doesn't work" rather than "the
   agent wasn't told to" (unprompted uptake is a separate experiment). No tool allowlist
   (``available_tools=[]``), so Claude Code's own memory-write path is never blocked by
   ``--allowedTools``.
2. **cwd wipe** — the shared sandbox cwd's CONTENTS are emptied between the legs. The
   two legs must share a cwd (native memory is keyed on the cwd slug), but the cwd is
   itself a continuity channel: Claude Code auto-loads ``CLAUDE.md``/``AGENTS.md`` from
   it at session start with NO tool call, so a Write-only ``--allowedTools`` clamp does
   NOT close the scavenge vector — an unconstrained establish leg can leave the fact in a
   file the goal leg reads for free. Emptying the directory (rather than replacing it)
   keeps the slug, hence the memory path, hence the continuity under test, while leaving
   nothing to scavenge. This is a firewall, not a detector: the accounting cannot see
   this channel, since ``engaged`` is measured off the establish leg's write and
   ``leaked`` only fires on (pass AND NOT engaged) — a scavenged pass would otherwise
   score as a clean SEPARATES. The ancestor guard re-runs HERE too, not just at the mint:
   the establish leg is unclamped by design, so the same window the wipe covers for the cwd
   is open one directory up, where the wipe cannot reach.
3. **goal** — ``task.goal_step`` run BARE (``memory={}``): with the cwd emptied, the only
   way the current opaque value can reach the ``Write`` call is if call 1 actually
   persisted it and Claude Code's native-memory system re-surfaced it unprompted.

Engagement is graded on CONTENT, not file existence: after call 1, every native-memory
``.md`` under the config dir — the ``MEMORY.md`` index AND its topic files, which is
where the fact actually lands — is checked for the current opaque token. A goal PASS with
engaged=False is a LEAK, not a builtin win — same severity class as the ``none``-arm leak
branch in ``realagent_probe``.

The mechanism's own knob is set here too: each repeat mints a pristine
``CLAUDE_CONFIG_DIR``, so ``settings.json`` is seeded with ``autoMemoryEnabled: true``
rather than riding on whatever the CLI's default happens to be. The key is config-dir
local, so this driver owns it outright — it is not an account/pool-level flag.

ZFC: plumbing + a mechanical token-presence check (``states_value``, the same
word-boundary match ``toolreq_realagent``'s leak firewall uses). No model call, no
semantic judgment.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import types
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from membench.harbor.agent_memory import NATIVE_MEMORY_GLOB, native_memory_path
from membench.metrics.scorers import states_value
from membench.runner.headless_agent import (
    CellCalls,
    CellRecorder,
    Leg,
    MemoryChannel,
    assistant_event,
    cell_agent,
    render_cell_calls,
    result_event,
    seed_config_dir,
    serialize_stream,
)
from membench.runner.realagent_probe import CONFIG_FILE, REAL_TOOL, ArmOutcome, score_goal_action
from membench.runner.resume_cache import digest
from membench.runner.sandbox import assert_neutral_ancestry, paid_sandbox
from membench.runner.toolreq_realagent import ToolReqRealAgentTask
from membench.runtime import StepContext
from membench.schemas.sequence import SequenceStep
from membench.spawn import Runner

ARM = "builtin"

# Where the dry-run simulator parks the fact: a TOPIC file beside the MEMORY.md index,
# which is the layout real native memory uses (the index holds pointers, not content).
SIMULATED_TOPIC_FILE = "established-facts.md"

_ESTABLISH_INSTRUCTION = (
    "Take note of the established fact(s) above and remember them: you will need to "
    "recall and use them later in this same session, without being reminded again."
)


def _establish_step(task: ToolReqRealAgentTask) -> SequenceStep:
    """The establish turn's bare instruction. The facts themselves are NOT embedded in
    this prose — they are delivered via ``available_memory`` (like the oracle arm), which
    is what lets the TRUSTED/RECALLED channel framing actually vary how they present."""
    return SequenceStep(
        step_id=f"{task.work_id}-establish",
        user_request=_ESTABLISH_INSTRUCTION,
        available_tools=[],  # H3: no --allowedTools clamp on CC's own memory-write path
    )


def cell_legs(task: ToolReqRealAgentTask) -> tuple[Leg, Leg]:
    """The two calls one ``(builtin, channel)`` cell makes, in order.

    THE definition, and the only one. ``run_builtin_arm`` EXECUTES these legs and
    ``toolreq_builtin_grid.planned_calls`` RENDERS them into the plan ``CachePlan.lookup`` hashes,
    so neither can describe a call the other does not make: change what a leg surfaces and both the
    sent command line and the cache identity move together, by construction.

    What this replaces was two hand-written copies of the same argument triples — a ``cell_prompts``
    that "lives beside ``run_builtin_arm`` and mirrors its two ``run_step`` calls". Adjacency is not
    structure. Surface a hint in the goal leg, edit only the arm, and the fingerprint stayed put:
    every persisted cell then matched, a resumed PAID run reported ``reused``, and pre-change
    numbers were published as post-change measurements, with nothing crashing and the suite green.

    They are returned as a PAIR, not a list to loop: the two legs are not interchangeable. The cwd
    firewall and the engagement read both happen BETWEEN them (``run_builtin_arm``), and their ORDER
    is a measured input — swap them and the arm establishes the fact into a directory it then wipes.
    """
    return (
        Leg("establish", _establish_step(task), dict(task.oracle_memory)),
        # BARE (memory={}): with the cwd emptied, native memory is the only channel left that can
        # carry the current value into the Write call. That empty dict IS the arm's hypothesis.
        Leg("goal", task.goal_step, {}),
    )


def cell_calls(task: ToolReqRealAgentTask, channel: MemoryChannel, *, model: str) -> CellCalls:
    """The two command lines one ``(builtin, channel)`` cell WILL spawn — the plan, rendered from
    the same legs the arm executes, through the same agent that executes them
    (``headless_agent.render_cell_calls``)."""
    return render_cell_calls(arm=ARM, channel=channel, legs=cell_legs(task), model=model)


# The mechanism under test, as the literal settings dict `_seed_config_dir` writes. Named, and
# EXPORTED, because it is a measured input the command line cannot carry: it reaches the agent
# through a file in `CLAUDE_CONFIG_DIR`, not through argv. `toolreq_builtin_grid` hashes THIS
# object into the cache identity (`BaseRunIdentity.settings_fingerprint`) — flip the flag and
# every other fingerprint is unmoved (same prompts, same task, no payload), so a resumed run would
# serve mechanism-ON numbers as mechanism-OFF measurements. A value outside the identity is not
# defended by the checks around it.
#
# Frozen (`MappingProxyType`) so an in-place edit (`BUILTIN_SETTINGS["autoMemoryEnabled"] = False`)
# raises TypeError instead of silently diverging the seeded settings.json from this fingerprint.
BUILTIN_SETTINGS: Mapping[str, object] = types.MappingProxyType({"autoMemoryEnabled": True})


def _seed_config_dir(config_dir: Path) -> None:
    """Turn the mechanism under test ON in a freshly-minted ``CLAUDE_CONFIG_DIR``.

    ``autoMemoryEnabled`` is a ``$CLAUDE_CONFIG_DIR/settings.json`` key — config-dir
    LOCAL, so this driver owns it outright (it is NOT an account/pool-level flag; one
    account home on this box carries it ``false``). Each repeat mints a pristine empty
    config dir, so without this seed the paid run would measure native memory riding on
    whatever the CLI's default for that key happens to be.

    Delegates to the shared ``headless_agent.seed_config_dir`` (the config-surface owner both grids
    seed through), binding this arm's frozen ``BUILTIN_SETTINGS`` — so the dict the cache
    fingerprints is the same object this seeds, one definition, not two that agree today. Unlike
    that seed path, ``mechanism_fingerprint`` needs no ``MappingProxyType`` unwrap — ``digest``'s
    ``canonicalize`` already branches on ``Mapping``."""
    seed_config_dir(config_dir, BUILTIN_SETTINGS)


def mechanism_fingerprint() -> str:
    """The digest of the settings this arm SEEDS into every repeat's ``CLAUDE_CONFIG_DIR``.

    It lives HERE, beside ``_seed_config_dir``, and reads the module global at CALL time — so the
    grid cannot hold a stale by-value copy of the dict from import, and the value hashed is by
    construction the value written. A fingerprint computed from a second reference to a mutable
    module-level dict is the defect family in miniature, at the one input the command line cannot
    carry."""
    return digest(BUILTIN_SETTINGS)


def wipe_cwd_contents(cwd: Path) -> None:
    """Empty the shared sandbox cwd between the establish and goal legs, closing the
    scavenge channel that ``--allowedTools`` cannot (an auto-loaded ``CLAUDE.md`` is not a
    Read tool call). The DIRECTORY survives: native memory is keyed on the cwd slug, so
    replacing it would move the memory file out from under the goal call and destroy the
    continuity being measured."""
    for entry in cwd.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def _memory_engaged(config_dir: Path, tokens: Collection[str]) -> bool:
    """True iff any current opaque ``tokens`` reached native memory under ``config_dir``.

    Matches on CONTENT, not file existence — Claude Code scaffolds an empty ``memory/``
    dir regardless of whether anything meaningful was written, so existence alone would
    read as engagement. Searches every native-memory ``.md`` (``NATIVE_MEMORY_GLOB``), not
    just the ``MEMORY.md`` index: native memory is an index plus TOPIC FILES, and the fact
    lands in the topic file."""
    for memory_file in config_dir.glob(NATIVE_MEMORY_GLOB):
        try:
            content = memory_file.read_text(encoding="utf-8")
        except OSError:
            continue
        if any(states_value(content, token) for token in tokens):
            return True
    return False


@dataclass(frozen=True)
class BuiltinDiagnostics:
    """Sidecar engagement diagnostics for one (arm=builtin, channel) cell — kept OFF
    ``ArmOutcome`` (M3: no ``BuiltinArmOutcome`` subtype) so the eventual
    none/oracle/ours/builtin report merge stays a uniform ``ArmOutcome`` list; the
    driver persists this alongside it. ``leaked`` is the count of repeats that scored a
    PASS despite ``engaged=False`` — an invalid result, not a builtin win."""

    engaged: int
    leaked: int
    runs: int
    # Audit trail for the establish call, which runs with NO --allowedTools clamp (so CC's
    # memory-write path is never blocked) and can therefore genuinely invoke Bash/Read/etc,
    # not just the intended memory write. Summed across repeats so a reviewer gating the
    # paid fire can see what the unconstrained call actually did before authorizing spend.
    # The NAMES, not just the count: "it made 6 tool calls" cannot answer the question the
    # trail exists for — which tools the unconstrained leg actually reached for.
    establish_tool_calls: int = 0
    establish_tool_names: tuple[str, ...] = ()


def simulated_builtin_runner(current_values: Collection[str]) -> Runner:
    """Dry-run stand-in for BOTH builtin calls: the establish call honestly persists the
    values in Claude Code's REAL native-memory layout (an ``MEMORY.md`` index pointing at
    a ``<topic>.md`` that carries the fact) iff its prompt carried every current value
    (i.e. iff the arm surfaced them via ``available_memory``); the goal call — always
    bare, so its own prompt never carries the values — reads that topic file back and
    Writes the current value(s) iff present.

    It persists to the real layout ON PURPOSE. A simulator that wrote the fact into the
    index instead would be fitted to whatever the engagement check happens to glob, so a
    green dry-run would prove nothing about the on-disk shape — precisely how a
    MEMORY.md-only glob (which scores a working builtin as engaged=0) survived a green
    dry-run before. Writing where native memory really writes makes the free path a
    genuine regression guard on the glob.

    Proves the two-call shared cwd/config-dir wiring, the layout, and the scoring path for
    zero tokens; it still CANNOT exercise the one link that actually matters — whether a
    real ``claude -p`` session persists at all when asked. That is the paid preflight's
    job, not this simulator's."""
    values = list(current_values)

    def run(argv: Collection[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        argv_list = list(argv)
        assert argv_list[:2] == ["claude", "-p"], f"unexpected argv layout: {argv_list[:3]}"
        prompt = argv_list[2] if len(argv_list) > 2 else ""
        env = kwargs.get("env")
        cwd = kwargs.get("cwd")
        config_dir = env.get("CLAUDE_CONFIG_DIR") if isinstance(env, Mapping) else None
        events: list[dict[str, object]] = []
        if config_dir and isinstance(cwd, str):
            index_path = Path(native_memory_path(config_dir=str(config_dir), workdir=cwd))
            # The fact goes in a TOPIC file beside the index — the real layout. The index
            # gets only a pointer, exactly as Claude Code writes it.
            topic_path = index_path.parent / SIMULATED_TOPIC_FILE
            if values and all(value in prompt for value in values):
                # establish call: honestly persist iff the arm surfaced every value
                index_path.parent.mkdir(parents=True, exist_ok=True)
                index_path.write_text(
                    f"- [Established facts]({SIMULATED_TOPIC_FILE}) — recall these later\n",
                    encoding="utf-8",
                )
                topic_path.write_text(" ".join(values), encoding="utf-8")
            elif topic_path.is_file():
                persisted = topic_path.read_text(encoding="utf-8")  # once, not per value
                if all(value in persisted for value in values):
                    # goal call: re-surface iff the establish call actually persisted it
                    events.append(
                        assistant_event(
                            [(REAL_TOOL, {"file_path": CONFIG_FILE, "content": " ".join(values)})]
                        )
                    )
        events.append(result_event())
        stdout = serialize_stream(events)
        return subprocess.CompletedProcess(argv_list, returncode=0, stdout=stdout, stderr="")

    return run


def run_builtin_arm(
    task: ToolReqRealAgentTask,
    *,
    repeats: int,
    model: str,
    dry_run: bool,
    channel: MemoryChannel,
    recorder: CellRecorder,
    runner: Runner | None = None,
) -> tuple[ArmOutcome, BuiltinDiagnostics]:
    """Run ``repeats`` independent establish/goal pairs, each in a fresh sandbox cwd +
    fresh ``CLAUDE_CONFIG_DIR``, score the goal call externally, and return the score plus
    engagement diagnostics. ``dry_run`` swaps the real ``claude -p`` for
    ``simulated_builtin_runner`` (no token).

    Two runner seams, not to be confused: ``runner`` is the INNER CLI runner to wrap (overriding the
    dry_run selection — mainly for tests exercising accounting edge cases, like a pass without
    engagement, that the honest dry-run simulator cannot itself produce); ``recorder`` is the
    seam that RECORDS it. This function opens its per-cell ``RecordingRunner`` through
    ``recorder.cell(...)`` and returns NO invocations — ``run_cached_corpus`` owns the recorder and
    reads ``recorded()`` itself, so a cell's argv can never be a value this function handed back.

    The two legs come from ``cell_legs`` and the agent from ``cell_agent``, so what this
    executes and what ``toolreq_builtin_grid.planned_calls`` renders (for ``CachePlan.lookup`` to
    hash into the identity) are ONE definition. A leg added here and forgotten in the plan is still
    seen, because the recorder sees the call whether or not anyone declared it."""
    if runner is None:
        runner = simulated_builtin_runner(task.current_opaque_values) if dry_run else subprocess.run
    cell_runner = recorder.cell(runner, arm=ARM, channel=channel, repeats=repeats)
    establish_leg, goal_leg = cell_legs(task)
    passes = 0
    engaged = 0
    leaked = 0
    establish_tool_calls = 0
    establish_tool_names: set[str] = set()

    for i in range(repeats):
        with (
            paid_sandbox(f"toolreq-{ARM}-sandbox-") as sandbox,
            tempfile.TemporaryDirectory(prefix=f"toolreq-{ARM}-config-") as config_dir_str,
        ):
            config_dir = Path(config_dir_str)
            _seed_config_dir(config_dir)
            agent = cell_agent(
                model=model,
                channel=channel,
                runner=cell_runner,
                cwd=str(sandbox),
                env={"CLAUDE_CONFIG_DIR": str(config_dir)},
            )

            # Takes the `Leg` WHOLE rather than two of its fields: nothing at a call site can pair
            # one leg's label with another leg's step, and a third leg needs no third hand-copied
            # unpack. `i` is pinned as a default — the legs are run inside this loop (B023).
            def _ctx(leg: Leg, i: int = i) -> StepContext:
                return StepContext(
                    trial_id=f"{ARM}-{channel.value}-{i}-{leg.name}",
                    session_id=f"{ARM}-{channel.value}-{i}",
                    step_id=leg.step.step_id,
                )

            establish_result = agent.run_step(
                establish_leg.step, dict(establish_leg.memory), _ctx(establish_leg)
            )
            establish_tool_calls += len(establish_result.tool_calls)
            establish_tool_names.update(call.name for call in establish_result.tool_calls)
            repeat_engaged = _memory_engaged(config_dir, task.current_opaque_values)

            # Close the cwd channel BEFORE the goal leg: native memory (in the config dir)
            # survives, anything the unconstrained establish leg dropped in the shared cwd
            # does not. Engagement is read above, off the config dir, so the wipe cannot
            # affect it. This is why the legs are a PAIR and not a loop, and why their order
            # is a measured input (`cell_legs`).
            wipe_cwd_contents(sandbox)

            # The wipe's blind spot, one directory up (docstring step 2). Re-scanned rather
            # than trusted from the mint: refusing here costs the establish call, already
            # spent and never written, which beats publishing a fabricated SEPARATES.
            assert_neutral_ancestry(sandbox)

            result = agent.run_step(goal_leg.step, dict(goal_leg.memory), _ctx(goal_leg))

        passed = score_goal_action(
            task.goal_step, tool_calls=result.tool_calls, final_answer=result.final_answer
        )
        if passed:
            passes += 1
        if repeat_engaged:
            engaged += 1
        if passed and not repeat_engaged:
            leaked += 1

    outcome = ArmOutcome(arm=ARM, channel=channel.value, passes=passes, runs=repeats)
    diagnostics = BuiltinDiagnostics(
        engaged=engaged,
        leaked=leaked,
        runs=repeats,
        establish_tool_calls=establish_tool_calls,
        establish_tool_names=tuple(sorted(establish_tool_names)),
    )
    return outcome, diagnostics
