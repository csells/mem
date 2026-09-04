"""mem-5sht9 — the memory tool surface: reachable, countable, and outliving the cwd wipe.

The invariants that make a zero call-rate MEAN something:

* the shim the agent reaches through ``surface.env()`` execs the REAL bd, not itself. That is
  the one test geometry a52bebd did not have: every one of its shim tests invoked the shim by
  ABSOLUTE path under the ambient ``PATH``, so the suite was green while the shipped surface
  exec'd itself forever and hung every call the evaluated agent made;
* the store survives ``toolreq_builtin.wipe_cwd_contents`` between two legs sharing a sandbox;
* a store inside the sandbox (wiped) or above it (contaminating) is REFUSED by
  ``provision_memory_tool`` itself, not merely by a helper a caller may forget to call;
* the counter keys on the structured tool name plus a shell-word scan of the ``command``
  argument — never prose, never a comment, never a heredoc body, and it does not MISS a call
  behind a space-separated flag value (the miss direction is the one that manufactures the
  near-zero null this series exists to rule out);
* ``--mcp-config`` is emitted alongside ``--strict-mcp-config``, and ``--disallowedTools``
  carries the host-signal deny list;
* the tool surface moves the run identity, so a surface change cannot resume as a cache hit.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

import pytest

from membench.runner import tool_surface
from membench.runner.agent import AgentStepResult
from membench.runner.e1_smoke import (
    SMOKE_KEY,
    SMOKE_TOKEN,
    SMOKE_VALUE,
    halt_reason,
    run_smoke,
)
from membench.runner.e1_smoke import main as smoke_main
from membench.runner.headless_agent import (
    HeadlessClaudeAgent,
    Leg,
    MemoryChannel,
    _render_only_runner,
    assistant_event,
    render_cell_calls,
    result_event,
    serialize_stream,
    tool_calls_from_stream,
    tool_result_event,
)
from membench.runner.metrics import compute_metrics
from membench.runner.tool_surface import (
    HOST_DENIED_TOOLS,
    MEMORY_ALLOWED_TOOLS,
    MEMORY_COMMAND,
    NATIVE_MEMORY_TOOL_NAMES,
    STORE_FORBIDDEN_GUIDANCE,
    MemoryInvocation,
    MemoryToolError,
    NativeMemoryAccess,
    assert_store_outside,
    call_satisfied,
    command_segments,
    endogenous_memory_tool_calls,
    endogenous_memory_verbs,
    harness_call,
    memory_invocations,
    memory_invocations_in_command,
    memory_reaching_calls,
    memory_verbs_in_command,
    native_memory_accesses,
    native_memory_calls,
    native_memory_calls_satisfied,
    partition_memory_calls,
    provision_memory_tool,
    recognizer_policy,
    remember_was_a_recall,
    remember_was_accepted,
    resolve_bd_binary,
    scrub_store_guidance,
    settings_fingerprint,
    surface_fingerprint,
)
from membench.runner.toolreq_builtin import wipe_cwd_contents
from membench.schemas.metrics import EfficiencyMetrics
from membench.schemas.sequence import SequenceStep
from membench.schemas.trace import ToolCall

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

_HAS_BD = shutil.which(MEMORY_COMMAND) is not None
requires_bd = pytest.mark.skipif(_HAS_BD is False, reason="bd is not installed on this host")


def bash(command: str) -> ToolCall:
    return ToolCall(name="Bash", arguments={"command": command})


# --------------------------------------------------------------------------------------
# the counter: shell words of the EXECUTED command, never prose
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command,expected",
    [
        ("bd recall widget-port", ["recall"]),
        ('bd remember "the port is 48317" --key p', ["remember"]),
        ("bd memories", ["memories"]),
        ("bd forget stale-key", ["forget"]),
        ("bd --json recall k", ["recall"]),
        ("/usr/local/bin/bd recall k", ["recall"]),
        ("cd /tmp && bd remember 'x'", ["remember"]),
        ("bd recall a; bd remember b", ["recall", "remember"]),
        # word boundaries, both ends
        ("abd recall k", []),
        ("mybd remember x", []),
        ("bd remembering the port", []),
        ("bd recalls k", []),
        # not a memory verb: `link` is `bd dep add` shorthand, and issue work is not memory work
        ("bd link a b", []),
        ("bd ready", []),
    ],
)
def test_memory_verbs_parse_argv_not_prose(command: str, expected: list[str]) -> None:
    assert memory_verbs_in_command(command) == expected


@pytest.mark.parametrize(
    "command,expected",
    [
        # --- the MISS direction. a52bebd's regex allowed only `--flag` / `--flag=v` between the
        # command and the verb, so every space-separated flag value hid a real memory call. An
        # under-count here manufactures exactly the near-zero result this series must rule out.
        ("bd -C /tmp recall k", ["recall"]),
        ("bd --db /x/y.db recall k", ["recall"]),
        ("bd --directory /tmp remember v --key k", ["remember"]),
        ("bd --actor bot --json memories", ["memories"]),
        ("bd --db=/x/y.db recall k", ["recall"]),
        ("BEADS_ACTOR=bot bd recall k", ["recall"]),
        ("bd \\\n    recall k", ["recall"]),
        ("(bd recall k)", ["recall"]),
        ("bd -q -C /tmp --json forget k", ["forget"]),
        # a value-taking flag must not swallow the verb when it is `=`-joined
        ("bd --actor=bot recall k", ["recall"]),
        # --- the OVER-count direction: prose, comments and heredoc bodies inside an argv
        ("echo bd recall x", []),
        ("echo 'I should probably bd remember this'", []),
        ('echo "bd recall x"', []),
        ("# bd recall k", []),
        ("ls /tmp  # then bd recall k", []),
        ("printf '%s' 'bd remember v'", []),
        ("cat <<EOF\nbd recall k\nEOF", []),
        ("cat <<-'NOTE'\nremember to run bd remember v\nNOTE", []),
        # a real call AFTER a heredoc body still counts — the skip must end at the delimiter
        ("cat <<EOF > f\nbd recall decoy\nEOF\nbd recall real", ["recall"]),
        # a subcommand that merely shares the verb's spelling is not a memory call
        ("bd issue remember", []),
        ("bd dep remember a b", []),
    ],
)
def test_counter_adversarial_argv(command: str, expected: list[str]) -> None:
    assert memory_verbs_in_command(command) == expected


@pytest.mark.parametrize(
    "command,expected",
    [
        # --- shell KEYWORDS in front of the command word. d9809a2's `_verb_of_segment` skipped
        # only NAME=value prefixes, so the keyword BECAME the segment's command word and every one
        # of these counted as no call. E1's primary endpoint IS the call rate, so each of these is
        # a bias toward the near-zero null the series exists to rule out.
        ("if bd recall k; then echo hit; fi", ["recall"]),
        ("if ! bd recall k; then bd remember v --key k; fi", ["recall", "remember"]),
        ("for i in 1 2; do bd recall $i; done", ["recall"]),
        ("while read k; do bd recall $k; done < keys", ["recall"]),
        ("until bd recall k; do sleep 1; done", ["recall"]),
        (
            "if bd recall k > /dev/null 2>&1; then echo yes; else bd memories; fi",
            ["recall", "memories"],
        ),
        ("{ bd recall k; }", ["recall"]),
        # --- COMMAND SUBSTITUTION. `$(...)` broke the segment via its `(`; the backtick form did
        # not appear in _SEGMENT_BREAKS at all.
        ("echo `bd recall k`", ["recall"]),
        ("v=`bd recall k`", ["recall"]),
        ("echo $(bd recall k)", ["recall"]),
        # ...and the same substitution INSIDE a double-quoted run, which 5e45493 copied through
        # without scanning. Capturing a recall into a variable is the canonical agent spelling and
        # quoting it is the habitual one, so this miss ran in the direction of the near-zero null.
        ('v="$(bd recall k)"', ["recall"]),
        ('echo "$(bd recall k)"', ["recall"]),
        ('echo "`bd recall k`"', ["recall"]),
        ('test -n "$(bd recall k)" && echo yes', ["recall"]),
        ('echo "$(bd memories)"', ["memories"]),
        ('echo "prefix $(bd recall a) $(bd remember b c)"', ["recall", "remember"]),
        # A SINGLE-quoted run is literal - the shell expands nothing there - so the same text
        # must not manufacture a call. This is the over-count direction of the same change.
        ("echo '$(bd recall k)'", []),
        ("echo '`bd recall k`'", []),
        ('echo "$(( 1 + 2 ))"', []),
        # --- lesser wrappers named in review alongside the substitution defect
        ("watch bd memories", ["memories"]),
        ("watch -n 5 bd memories", ["memories"]),
        ("script -c 'bd recall k' /dev/null", ["recall"]),
        # NOT widened, and deliberately: an escaped space makes ONE argv word, so bd is handed
        # "recall k" and has no such subcommand. Counting it would invent a call the shell does
        # not make, which is the over-count this table's second half exists to prevent.
        ("bd recall\\ k", []),
        # --- TRANSPARENT WRAPPERS: the process they exec is bd, so the call is a memory call.
        ("sudo bd recall k", ["recall"]),
        ("sudo -u bot bd recall k", ["recall"]),
        ("env bd recall k", ["recall"]),
        ("env FOO=1 bd recall k", ["recall"]),
        ("/usr/bin/env bd recall k", ["recall"]),
        ("timeout 30 bd recall k", ["recall"]),
        ("timeout -k 5 30s bd recall k", ["recall"]),
        ("command bd recall k", ["recall"]),
        ("nohup bd recall k &", ["recall"]),
        ("time bd recall k", ["recall"]),
        ("exec bd recall k", ["recall"]),
        ("stdbuf -oL bd memories", ["memories"]),
        ("cat keys | xargs -n1 bd recall", ["recall"]),
        ("cat keys | xargs -I{} bd recall {}", ["recall"]),
        ("sudo -u bot env FOO=1 timeout 5 bd recall k", ["recall"]),
        # --- an interpreter's `-c` STRING is a command line, not an opaque argument
        ("bash -c 'bd recall k'", ["recall"]),
        ('sh -c "bd recall k"', ["recall"]),
        ("sh -lc 'bd recall a; bd remember b'", ["recall", "remember"]),
        ("sudo bash -c 'bd recall k'", ["recall"]),
        ('eval "bd recall k"', ["recall"]),
        # --- and none of the wrappers may manufacture a call the shell would not make: the scan
        # stops at the first non-option word and it has to BE bd.
        ("timeout 30 echo bd recall k", []),
        ("sudo echo bd recall k", []),
        ("command -v bd", []),
        ("bash -c 'echo bd recall k'", []),
        ("bash --version", []),
        ("for bd in a b; do echo $bd; done", []),
    ],
)
def test_counter_sees_wrapped_and_keyworded_calls(command: str, expected: list[str]) -> None:
    """Every form here returned ``[]`` against d9809a2 (the wrapper/keyword ones) or was invented
    to pin the other direction of the same fix. Reproduced independently by two verifiers before
    it was written."""
    assert memory_verbs_in_command(command) == expected


def test_braces_break_a_segment_only_when_they_stand_alone() -> None:
    """The tokenizer change the ``xargs -I{}`` case rests on: an attached brace is literal text,
    a standalone one is shell grouping. Breaking on every brace split the word and lost the call."""
    assert command_segments("xargs -I{} bd recall {}") == [["xargs", "-I{}", "bd", "recall", "{}"]]
    assert command_segments("{ bd recall k; }") == [["bd", "recall", "k"]]


def test_a_quoted_substitution_is_scanned_but_a_quoted_literal_is_not() -> None:
    """The two halves of the double-quote rule, pinned at the tokenizer rather than the counter.

    The shell RUNS ``$(...)`` inside double quotes and does not inside single quotes, so the
    scanner has to split on exactly that line. Pinning it here as well as in the verb table is
    deliberate: the verb table would still pass if the substitution leaked into the surrounding
    word instead of becoming its own segment."""
    assert command_segments('v="$(bd recall k)"') == [["v="], ["bd", "recall", "k"]]
    assert command_segments("echo '$(bd recall k)'") == [["echo", "$(bd recall k)"]]
    # Nested, because an agent that quotes once tends to quote twice.
    assert ["bd", "recall", "k"] in command_segments('echo "$(echo \\"$(bd recall k)\\")"')
    # Unterminated: the tail is still scanned rather than swallowed whole.
    assert ["bd", "recall", "k"] in command_segments('echo "$(bd recall k')


def test_segments_keep_a_quoted_run_as_one_word() -> None:
    """The property the over-count cases rest on: a quoted blob can never split into a command
    word plus a verb, however much shell-shaped text it contains."""
    assert command_segments('echo "bd recall x"') == [["echo", "bd recall x"]]


def test_counter_ignores_non_bash_tool_names() -> None:
    """A Write whose CONTENT mentions the verb is not a memory call. Keying on the structured name
    first is what keeps the counter off the agent's text."""
    calls = [ToolCall(name="Write", arguments={"content": "run bd remember later"})]
    assert endogenous_memory_tool_calls(calls) == 0
    assert endogenous_memory_verbs(calls) == []


def test_counter_counts_blocks_and_verbs_separately() -> None:
    calls = [
        bash("ls"),
        bash("bd recall k && bd remember 'v'"),
        ToolCall(name="Read", arguments={"file_path": "/x"}),
    ]
    assert endogenous_memory_tool_calls(calls) == 1
    assert endogenous_memory_verbs(calls) == ["recall", "remember"]


def test_counter_tolerates_a_bash_call_with_no_command_argument() -> None:
    assert endogenous_memory_tool_calls([ToolCall(name="Bash", arguments={})]) == 0


# --------------------------------------------------------------------------------------
# the shim: it must exec the REAL bd, under the env the AGENT gets
# --------------------------------------------------------------------------------------


def test_resolve_bd_binary_returns_an_absolute_path() -> None:
    resolved = resolve_bd_binary("/bin/sh")
    assert Path(resolved).is_absolute()
    assert os.path.isfile(resolved)


def test_resolve_bd_binary_refuses_a_binary_inside_the_shim_dir(tmp_path: Path) -> None:
    """The fatal defect, as a unit: a `bd` that resolves into the shim directory is a shim that
    execs itself. Refused at provision time rather than discovered as a hang."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / MEMORY_COMMAND
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    with pytest.raises(MemoryToolError, match="inside the shim directory"):
        resolve_bd_binary(str(fake), refuse_under=bin_dir)


def test_resolve_bd_binary_raises_when_bd_is_absent(tmp_path: Path) -> None:
    with pytest.raises(MemoryToolError, match="no executable"):
        resolve_bd_binary(str(tmp_path / "nope" / "bd"))


@requires_bd
def test_shim_does_not_self_exec_under_surface_env(tmp_path: Path) -> None:
    """THE regression guard for the defect that rejected a52bebd, and the only geometry that can
    see it: run the shim the way the AGENT does — by bare name, with ``surface.env()`` applied, so
    the shim directory is FIRST on PATH.

    Against the old shim (``exec "bd" ...`` with a bare-name resolution) this re-execs itself,
    prepending another ``-C <store>`` each pass until the argv is unusable; the call never
    returns a clean `bd version`. Every a52bebd test invoked the shim by absolute path under the
    ambient PATH and so passed whether the surface worked or not."""
    surface = provision_memory_tool(tmp_path, sandbox=None)
    assert Path(surface.bd_binary).is_absolute()
    assert surface.bin_dir.resolve() not in Path(surface.bd_binary).parents

    env = {**os.environ, **surface.env()}
    assert env["PATH"].split(os.pathsep)[0] == str(surface.bin_dir)
    completed = subprocess.run(
        [MEMORY_COMMAND, "version"],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    # and the recursion signature is absent: one `-C` was injected, not hundreds
    assert "-C" not in completed.stdout


@requires_bd
def test_the_old_bare_name_shim_really_does_self_exec(tmp_path: Path) -> None:
    """The isolated revert, kept as a test so the guard above can never be vacuous.

    This writes a52bebd's shim body verbatim — ``exec "bd" ...``, the bare name — into the shim
    directory and runs it with the shim directory first on PATH, the geometry ``surface.env()``
    creates. It must NOT succeed. Measured on this host: exit 124, the call never returns.

    A guard test whose fixture geometry lets it pass either way is the failure that shipped the
    defect; this asserts the geometry itself is discriminating."""
    bin_dir = tmp_path / "bin"
    store = tmp_path / "store"
    bin_dir.mkdir()
    store.mkdir()
    shim = bin_dir / MEMORY_COMMAND
    shim.write_text(f'#!/bin/sh\nexec "bd" -C "{store}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    env = {**os.environ, "PATH": os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])}
    try:
        completed = subprocess.run(
            [MEMORY_COMMAND, "version"],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return  # the observed behaviour: it never returns
    assert completed.returncode != 0, "the bare-name shim must not resolve to the real bd"


@requires_bd
def test_memory_round_trip_through_the_agent_path(tmp_path: Path) -> None:
    """A write and a read spelled the way the agent spells them — bare `bd`, resolved through
    ``surface.env()`` — not through ``harness_call``'s absolute path."""
    surface = provision_memory_tool(tmp_path, sandbox=None)
    env = {**os.environ, **surface.env()}
    write = subprocess.run(
        [MEMORY_COMMAND, "remember", SMOKE_VALUE, "--key", SMOKE_KEY],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert write.returncode == 0, write.stderr[-2000:]
    read = subprocess.run(
        [MEMORY_COMMAND, "recall", SMOKE_KEY],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert read.returncode == 0, read.stderr[-2000:]
    assert SMOKE_VALUE in read.stdout


# --------------------------------------------------------------------------------------
# the store: outside the cwd, refused at provision time, and it survives the wipe
# --------------------------------------------------------------------------------------


def test_assert_store_outside_refuses_a_store_inside_the_sandbox(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    with pytest.raises(MemoryToolError, match="inside the sandbox"):
        assert_store_outside(sandbox, sandbox / ".beads")


def test_assert_store_outside_refuses_a_store_above_the_sandbox(tmp_path: Path) -> None:
    sandbox = tmp_path / "store" / "sandbox"
    sandbox.mkdir(parents=True)
    with pytest.raises(MemoryToolError, match="ABOVE the sandbox"):
        assert_store_outside(sandbox, tmp_path / "store")


def test_assert_store_outside_accepts_sibling_directories(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    store = tmp_path / "store"
    sandbox.mkdir()
    store.mkdir()
    assert_store_outside(sandbox, store)  # does not raise


def test_provision_refuses_a_store_the_sandbox_would_eat(tmp_path: Path) -> None:
    """``assert_store_outside`` is CALLED by the provisioner, not left as a helper a caller may
    forget — and it fires before ``bd init`` writes CLAUDE.md/AGENTS.md/.claude anywhere."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    def never(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("bd init must not run once the store placement is refused")

    with pytest.raises(MemoryToolError, match="inside the sandbox"):
        provision_memory_tool(sandbox / "root", sandbox=sandbox, runner=never)


@requires_bd
def test_store_survives_wipe(tmp_path: Path) -> None:
    """THE bead's acceptance test: write through the tool in leg 1, wipe the shared sandbox cwd
    the way ``toolreq_builtin`` does between legs, read it back through the tool in leg 2.

    The shim is invoked with ``cwd=sandbox`` on both legs — exactly where the agent's Bash tool
    would run it — so this fails if the store is ever allowed back into the cwd."""
    root = tmp_path / "surface"
    root.mkdir()
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    surface = provision_memory_tool(root, sandbox=sandbox)

    # leg 1 — the agent writes
    harness_call(surface, ["remember", SMOKE_VALUE, "--key", SMOKE_KEY], cwd=sandbox)
    (sandbox / "scratch.txt").write_text("leg-1 residue", encoding="utf-8")

    wipe_cwd_contents(sandbox)
    assert list(sandbox.iterdir()) == []

    # leg 2 — the agent reads, in the same (now empty) cwd
    assert SMOKE_VALUE in harness_call(surface, ["recall", SMOKE_KEY], cwd=sandbox)


@requires_bd
def test_a_mint_survives_an_initialized_beads_workspace_in_an_ancestor(tmp_path: Path) -> None:
    """The store is minted under a temp root, so its ancestors include `/tmp` -- and bd discovers
    its workspace by walking UP from cwd. A stray `bd init` rooted at any ancestor therefore
    captures every store minted afterwards: init aborts with "This workspace is already
    initialized" and creates nothing, and the rig has no memory tool at all.

    Not hypothetical. mem-pkglb: a real `bd init` landed at `/tmp` on 2026-09-03 and reddened 57
    tests until it was removed. It fails closed, so it costs CI time rather than validity -- but a
    fire that cannot mint a store is a fire that measures wiring.

    The ancestor here is planted INSIDE tmp_path so the test owns it: `tmp_path/.beads` is a real
    initialized workspace, and the mint root sits under it.

    Survives an isolated revert of the `git init` boundary in `provision_memory_tool`: without it,
    this raises MemoryToolError and no `.beads` is created under the store."""
    subprocess.run(
        [resolve_bd_binary(None), "init", "--prefix", "anc", "--quiet"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert (tmp_path / ".beads").is_dir(), "the planted ancestor workspace did not initialize"

    root = tmp_path / "nested" / "surface"
    root.mkdir(parents=True)
    surface = provision_memory_tool(root, sandbox=None)

    # The store exists AND is functional -- a `.beads` directory alone would pass while pointing at
    # the ancestor's database, which is the capture this boundary exists to prevent.
    assert (surface.store_dir / ".beads").is_dir()
    harness_call(surface, ["remember", SMOKE_VALUE, "--key", SMOKE_KEY])
    assert SMOKE_VALUE in harness_call(surface, ["recall", SMOKE_KEY])


@requires_bd
def test_a_minted_store_carries_no_guidance_about_the_memory_tool(tmp_path: Path) -> None:
    """`bd init` writes `CLAUDE.md`, `AGENTS.md` and a beads skill beside the store, and two of
    them say "Use `bd remember` for persistent knowledge". That text is the ladder's TOP rung,
    authored by the tooling, sitting inside an artifact an R0 leg is supposed to reach with no
    guidance at all -- and the agent holds Read, Bash, and a shim whose body spells the store path.

    Asserts on the store as it actually lands, not on the removal list: a drop-in bd adds in a
    later release is the case that matters, and only a scan of what survived can see it.

    Survives an isolated revert of the `scrub_store_guidance` call in `provision_memory_tool`."""
    surface = provision_memory_tool(tmp_path, sandbox=None)

    survivors = [
        path
        for path in sorted(surface.store_dir.rglob("*"))
        if path.is_file() and path.relative_to(surface.store_dir).parts[0] not in {".beads", ".git"}
    ]
    assert survivors, "the scrub emptied the store of everything, including its own boundary"
    for path in survivors:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for token in STORE_FORBIDDEN_GUIDANCE:
            assert token not in text, f"{path.relative_to(surface.store_dir)} still names {token}"

    # The store is still a store: neutrality that broke the memory tool would pass the scan above.
    harness_call(surface, ["remember", SMOKE_VALUE, "--key", SMOKE_KEY])
    assert SMOKE_VALUE in harness_call(surface, ["recall", SMOKE_KEY])


def test_a_guidance_file_the_drop_in_list_does_not_name_is_refused(tmp_path: Path) -> None:
    """The removal list is a snapshot of what bd wrote on the day it was read. The scan is what
    makes the guarantee hold across a bd upgrade: a NEW file naming the verbs must stop the run,
    not be silently provisioned into every leg.

    Refuses rather than removes, deliberately. Deleting an unrecognized file would let the surface
    drift under the rig without anyone deciding it should.

    Survives an isolated revert of the `rglob` scan in `scrub_store_guidance` (the plant would be
    provisioned), and of the `STORE_FORBIDDEN_GUIDANCE` loop."""
    store = tmp_path / "store"
    (store / ".beads").mkdir(parents=True)
    (store / ".beads" / "notes.md").write_text("recall whatever", encoding="utf-8")
    (store / "ONBOARDING.md").write_text(
        "Keep project memory in beads: use bd remember.", encoding="utf-8"
    )

    with pytest.raises(MemoryToolError) as raised:
        scrub_store_guidance(store)
    assert "ONBOARDING.md" in str(raised.value)


def test_an_undecodable_file_in_the_store_is_refused_rather_than_assumed_neutral(
    tmp_path: Path,
) -> None:
    """Fails CLOSED. A file whose bytes will not decode cannot be shown not to instruct the agent,
    and `UnicodeDecodeError` is not an `OSError`, so an `except OSError` here would let it through
    as a raw crash rather than a refusal.

    Survives an isolated revert of `UnicodeDecodeError` out of the except clause."""
    store = tmp_path / "store"
    store.mkdir(parents=True)
    (store / "notes.bin").write_bytes(b"\xff\xfe\x00remember\x80")

    with pytest.raises(MemoryToolError) as raised:
        scrub_store_guidance(store)
    assert "notes.bin" in str(raised.value)


@requires_bd
def test_provisioned_shim_is_executable_and_pins_the_store(tmp_path: Path) -> None:
    surface = provision_memory_tool(tmp_path, sandbox=None)
    shim = surface.bin_dir / MEMORY_COMMAND
    assert shim.exists()
    assert shim.stat().st_mode & 0o111
    body = shim.read_text(encoding="utf-8")
    assert str(surface.store_dir) in body
    assert f'exec "{surface.bd_binary}"' in body  # an absolute path, never the bare name
    assert not (tmp_path / ".beads").exists()  # nothing landed in the caller's cwd
    assert surface.env()["PATH"].split(os.pathsep)[0] == str(surface.bin_dir)


def test_provision_raises_when_bd_init_fails(tmp_path: Path) -> None:
    def failing(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(argv), 1, "", "no beads database found")

    with pytest.raises(MemoryToolError, match="init"):
        provision_memory_tool(tmp_path, sandbox=None, bd_binary="/bin/sh", runner=failing)


# --------------------------------------------------------------------------------------
# the argv: the tool is reachable, the host-signal verbs are not, and the plan agrees
# --------------------------------------------------------------------------------------


def _step() -> SequenceStep:
    return SequenceStep(
        step_id="s", user_request="do it", available_tools=list(MEMORY_ALLOWED_TOOLS)
    )


def test_argv_allows_bash_so_the_memory_tool_is_reachable() -> None:
    """Both affordances must be reachable: `Bash` for the bd shim, `Read`/`Edit` for the native
    memory files (mem-gj0pc). The expectation is spelled out rather than read off the constant, so
    a tool silently dropped from the clamp fails here instead of agreeing with itself."""
    agent = HeadlessClaudeAgent(model="m", runner=_render_only_runner)
    argv = agent.argv_for(_step(), {})
    allowed = argv[argv.index("--allowedTools") + 1].split(",")
    assert allowed == ["Bash", "Write", "Read", "Edit"]


def test_argv_emits_the_host_signal_deny_list() -> None:
    """Host safety, such as it is: the sandbox bounds the cwd, not the process table, and a hung
    surface once drove the evaluated agent to a host-wide `pkill -9 bd`."""
    agent = HeadlessClaudeAgent(
        model="m", runner=_render_only_runner, disallowed_tools=HOST_DENIED_TOOLS
    )
    argv = agent.argv_for(_step(), {})
    denied = argv[argv.index("--disallowedTools") + 1].split(",")
    assert "Bash(pkill:*)" in denied
    assert "Bash(kill:*)" in denied


def test_argv_omits_disallowed_tools_when_none_are_denied() -> None:
    agent = HeadlessClaudeAgent(model="m", runner=_render_only_runner)
    assert "--disallowedTools" not in agent.argv_for(_step(), {})


def test_argv_emits_mcp_config_alongside_strict_mcp_config(tmp_path: Path) -> None:
    config = str(tmp_path / "mcp.json")
    agent = HeadlessClaudeAgent(model="m", runner=_render_only_runner, mcp_config=config)
    argv = agent.argv_for(_step(), {})
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--mcp-config") + 1] == config


def test_argv_omits_mcp_config_when_no_server_is_declared() -> None:
    agent = HeadlessClaudeAgent(model="m", runner=_render_only_runner)
    assert "--mcp-config" not in agent.argv_for(_step(), {})


def test_rendered_plan_carries_the_mcp_config_the_cell_would_send(tmp_path: Path) -> None:
    """The plan and the wire must agree on every argv element, or the resume cache's write
    boundary refuses the measurement."""
    config = str(tmp_path / "mcp.json")
    legs = [Leg(name="goal", step=_step(), memory={})]
    planned = render_cell_calls(
        arm="ours", channel=MemoryChannel.RECALLED, legs=legs, model="m", mcp_config=config
    )
    sent = HeadlessClaudeAgent(model="m", runner=_render_only_runner, mcp_config=config).argv_for(
        _step(), {}
    )
    assert planned.calls == (tuple(sent),)


# --------------------------------------------------------------------------------------
# the identity: a surface change is not a cache hit; a tempdir path is not a cache miss
# --------------------------------------------------------------------------------------


def test_settings_fingerprint_moves_when_the_tool_surface_changes(tmp_path: Path) -> None:
    settings = {"autoMemoryEnabled": True}
    bare = settings_fingerprint(settings)
    with_mcp = settings_fingerprint(settings, mcp_config=str(tmp_path / "mcp.json"))
    assert bare != with_mcp
    # and it still moves on the settings alone, so folding the surface in did not swallow them
    assert bare != settings_fingerprint({"autoMemoryEnabled": False})


@requires_bd
def test_surface_fingerprint_ignores_the_realised_store_path(tmp_path: Path) -> None:
    """Two runs differ only in which tempdir their store landed in. Hashing that path would force
    a permanent MISS and re-spend real money on a difference that moves no measurement."""
    a = provision_memory_tool(tmp_path / "a", sandbox=None)
    b = provision_memory_tool(tmp_path / "b", sandbox=None)
    assert a.store_dir != b.store_dir
    assert a.fingerprint() == b.fingerprint() == surface_fingerprint()


# --------------------------------------------------------------------------------------
# the smoke, free path
# --------------------------------------------------------------------------------------


def answering_runner(final_answer: str) -> object:
    """A ``claude -p`` stand-in that makes the memory call and then answers IN ITS OWN WORDS.

    This is the geometry ``simulated_runner`` cannot produce. That simulator sets ``final_answer``
    to raw shim stdout, so the seeded sentence is present by construction and every assertion about
    recovery passes whether the estimator is right or wrong — which is exactly how d9809a2 shipped
    a gate that HALTS on a correctly recalling agent. Here the answer is supplied by the test, so
    the estimator is the only thing under test."""

    def run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        stream = serialize_stream(
            [
                assistant_event([("Bash", {"command": f"bd recall {SMOKE_KEY}"})]),
                result_event(final_answer),
            ]
        )
        return subprocess.CompletedProcess(list(argv), 0, stream, "")

    return run


@requires_bd
def test_dry_run_smoke_reports_a_memory_tool_call() -> None:
    result = run_smoke(model="m", dry_run=True, timeout_s=30.0)
    assert result["endogenous_memory_tool_calls"] == 1
    assert result["endogenous_memory_verbs"] == ["recall"]
    assert result["tool_names"] == ["Bash"]
    assert result["recovered_token"] is True
    # and it says out loud that it is not a paid reachability result
    assert result["paid"] is False


def test_emitted_keys_do_not_collide_with_efficiency_metrics() -> None:
    """FIX 4 as a property, not a spelling. ``EfficiencyMetrics.memory_tool_calls`` counts
    harness-performed memory EVENTS; the smoke row counts calls the AGENT chose to make. A consumer
    joining the two on a shared key would compare different quantities silently, so the bare names
    must not appear on the JSON surface at all.

    The property is DIFFERENT quantities under one name, not any shared name. E3b gave
    ``EfficiencyMetrics`` its own ``endogenous_memory_*`` fields carrying the agent-chosen count
    this row already reports, and there the shared key is the correct join rather than the silent
    mismatch: both sides are counted by ``tool_surface`` from observed argv. So those names are
    exempted BY NAME and the bare ones stay banned — an exemption list that a future bare
    ``memory_tool_calls`` cannot slip into."""
    row = run_smoke(
        model="m",
        dry_run=False,
        timeout_s=30.0,
        runner=answering_runner(f"the handle is {SMOKE_TOKEN}"),
    )
    assert "memory_tool_calls" not in row
    assert "memory_verbs" not in row
    deliberately_shared = {
        "endogenous_memory_tool_calls",
        "endogenous_memory_reads",
        "endogenous_memory_writes",
    }
    assert set(EfficiencyMetrics.model_fields) & set(row) <= deliberately_shared


@requires_bd
def test_a_paraphrasing_agent_passes_the_gate() -> None:
    """The defect FIX 2 removes. The prompt asks the agent to REPORT THE HANDLE, so a correctly
    recalling agent answers with the handle, not with the seeded sentence. d9809a2 required the
    sentence verbatim and would have HALTED the whole series on a working surface."""
    row = run_smoke(
        model="m",
        dry_run=False,
        timeout_s=30.0,
        runner=answering_runner(f"I looked it up: the handle is {SMOKE_TOKEN}."),
    )
    assert row["endogenous_memory_tool_calls"] == 1
    assert row["recovered_token"] is True
    # the paraphrase does NOT contain the seeded sentence — which is the whole point
    assert row["recovered_sentence"] is False
    assert halt_reason({**row, "paid": True}) is None


@requires_bd
def test_an_answer_without_the_token_halts() -> None:
    """The other side: a plausible answer the agent could have written without reading the store
    recovers nothing, and must HALT. The token is unguessable precisely so this case is decidable.
    """
    row = run_smoke(
        model="m",
        dry_run=False,
        timeout_s=30.0,
        runner=answering_runner("The staging widget service handle is stored in the memory."),
    )
    assert row["recovered_token"] is False
    reason = halt_reason({**row, "paid": True})
    assert reason is not None
    assert "never recovered the seeded token" in reason


@requires_bd
def test_the_token_is_not_recovered_as_a_fragment() -> None:
    row = run_smoke(
        model="m",
        dry_run=False,
        timeout_s=30.0,
        runner=answering_runner(f"the handle is x{SMOKE_TOKEN}9"),
    )
    assert row["recovered_token"] is False


def test_halt_gate_passes_only_when_the_surface_both_answers_and_is_called() -> None:
    assert (
        halt_reason(
            {"endogenous_memory_tool_calls": 1, "recovered_token": True, "paid": True},
        )
        is None
    )


def test_halt_gate_halts_on_zero_calls() -> None:
    reason = halt_reason(
        {"endogenous_memory_tool_calls": 0, "recovered_token": False, "paid": True}
    )
    assert reason is not None
    assert "no memory tool call" in reason


def test_halt_gate_halts_when_calls_were_made_but_nothing_came_back() -> None:
    """The observed live failure, as a unit: 7 calls against a self-exec'ing shim, every one of
    them hung, no value recovered — and a52bebd's count-only gate exited 0 on it."""
    reason = halt_reason(
        {"endogenous_memory_tool_calls": 7, "recovered_token": False, "paid": True}
    )
    assert reason is not None
    assert "never recovered the seeded token" in reason


def test_halt_gate_refuses_to_bless_an_unpaid_row() -> None:
    """FIX 3. ``paid`` was added to say a simulated row proves nothing and then read by nobody, so
    ``--dry-run`` exited 0 whenever the simulator recovered the value. The exit code is the channel
    a CI gate reads; an advisory JSON field is not one."""
    reason = halt_reason(
        {"endogenous_memory_tool_calls": 1, "recovered_token": True, "paid": False}
    )
    assert reason is not None
    assert "not a paid run" in reason


@requires_bd
def test_dry_run_main_exits_nonzero() -> None:
    """The same refusal at the process boundary, which is where a gate actually observes it."""
    assert smoke_main(["--dry-run", "--json"]) == 1


# --------------------------------------------------------------------------------------
# the store check is not optional, and a memory call is not a non-memory call
# --------------------------------------------------------------------------------------


def test_provision_requires_the_sandbox_to_be_named() -> None:
    """FIX 5. ``sandbox`` defaulted to ``None``, so ``assert_store_outside`` fired only by caller
    discipline: a cell that forgot the argument got a store the wipe eats and a silent miss in the
    second leg. Keyword-only with NO default means every call site has to state what it is doing."""
    with pytest.raises(TypeError):
        provision_memory_tool(Path("/tmp"))  # type: ignore[call-arg]


def test_partition_splits_a_bash_wrapped_memory_call_out() -> None:
    calls = [bash("ls -la"), bash("bd recall k"), ToolCall(name="Read", arguments={})]
    memory, other = partition_memory_calls(calls)
    assert [c.arguments.get("command") for c in memory] == ["bd recall k"]
    assert len(other) == 2


def test_metrics_do_not_score_a_memory_call_as_a_non_memory_call() -> None:
    """FIX 6. ``runner/metrics.py`` passed ``len(agent_result.tool_calls)`` straight through as
    ``non_memory_tool_calls``, so the moment a grid hands the agent this surface every endogenous
    memory call inflates the non-memory cost and the latency that goes with it — the arm that calls
    the tool itself would look like the arm doing the most non-memory work. A docstring was the
    only guard.

    The assertions below also carry the round-3 correction to that fix: FIX 6 as shipped moved the
    bias instead of removing it. It stopped counting the memory call as non-memory and then routed
    it nowhere, so this very test asserted a two-call step reports ``tool_calls_total == 1`` and a
    410ms step reports 10. A published cost metric that drops exactly the calls the agent chose to
    make rewards the arm that uses memory most with the cheapest-looking total, which is the one
    direction the series cannot afford to be wrong in. Total now means total."""
    result = AgentStepResult(
        final_answer="done",
        tool_calls=[
            ToolCall(name="Bash", arguments={"command": "ls"}, latency_ms=10),
            ToolCall(name="Bash", arguments={"command": "bd recall k"}, latency_ms=400),
        ],
        check_results={"c1": True},
        writes_performed={},
    )
    bundle = compute_metrics(
        SequenceStep(step_id="s", user_request="go"),
        result,
        None,
        [],
        reads_enabled=False,
    )
    # The split still holds: the memory call is not non-memory work...
    assert bundle.efficiency.non_memory_tool_calls == 1
    # ...and the harness performed no memory event of its own here...
    assert bundle.efficiency.memory_tool_calls == 0
    # ...but the agent made TWO tool calls costing 410ms, and the totals say so.
    assert bundle.efficiency.tool_calls_total == 2
    assert bundle.efficiency.tool_latency_ms == 410


def test_tempdir_prefix_stays_out_of_the_repo() -> None:
    """The provisioning root is the caller's tempdir, never the worktree — a store written into
    the repo would be both a leak and a contaminated ancestor."""
    with tempfile.TemporaryDirectory(prefix="membench-memory-") as root:
        assert Path(root).is_absolute()


def test_env_pins_claude_config_dir_under_the_surface_root(tmp_path: Path) -> None:
    """The native memory path must resolve inside the surface, never in the operator's home.

    mem-gj0pc: the first paid E1 cycle handed the agent PATH only, and it reached for Claude
    Code's native MEMORY.md under the real account home. Only the allowedTools clamp stopped the
    read."""
    surface = provision_memory_tool(tmp_path / "root", sandbox=tmp_path / "sandbox")
    env = surface.env()
    pinned = Path(env["CLAUDE_CONFIG_DIR"])
    assert pinned.is_dir()
    assert pinned.is_relative_to(tmp_path / "root")
    assert not pinned.is_relative_to(Path.home() / ".claude")


def test_env_pin_survives_the_sandbox_wipe_boundary(tmp_path: Path) -> None:
    """The config dir lives beside the store, OUTSIDE the sandbox cwd — the same wipe boundary the
    store gets, and for the same reason: a native memory write the wipe eats is invisible."""
    sandbox = tmp_path / "sandbox"
    surface = provision_memory_tool(tmp_path / "root", sandbox=sandbox)
    assert not Path(surface.env()["CLAUDE_CONFIG_DIR"]).is_relative_to(sandbox)


def _read_call(path: str, tool: str = "Read") -> ToolCall:
    return ToolCall(name=tool, arguments={"file_path": path})


def test_native_memory_access_is_recognized_under_the_pinned_config_dir(tmp_path: Path) -> None:
    """mem-gj0pc's exact shape: a Read of MEMORY.md under the pinned config dir counts."""
    config = tmp_path / "config"
    memory = config / "projects" / "-tmp" / "memory"
    memory.mkdir(parents=True)
    calls = [_read_call(str(memory / "MEMORY.md"))]
    accesses = native_memory_accesses(calls, config_dir=config)
    assert [a.verb for a in accesses] == ["native_read"]
    assert native_memory_calls(calls, config_dir=config) == 1


def test_a_read_the_harness_answered_with_an_error_reached_but_obtained_nothing(
    tmp_path: Path,
) -> None:
    """The staged fire's read endpoint, exactly: 59 of 59 native reads were answered "File does
    not exist" and every one was published as `native_read`. The reach is real and must stay
    counted -- the agent DID turn to memory, which is the behaviour the ladder moves -- but it is
    not evidence memory was used, and one number cannot carry both facts.

    Survives an isolated revert of `satisfied=call_satisfied(call)` in `native_memory_accesses`
    (the errored read would count as obtained), and of `call_satisfied` returning `not
    call.is_error`."""
    config = tmp_path / "config"
    memory = config / "projects" / "-tmp" / "memory"
    memory.mkdir(parents=True)
    missed = ToolCall(
        name="Read",
        arguments={"file_path": str(memory / "MEMORY.md")},
        result="File does not exist.",
        is_error=True,
    )
    got = ToolCall(
        name="Read",
        arguments={"file_path": str(memory / "notes.md")},
        result="the deploy port is 48317",
    )

    assert [a.satisfied for a in native_memory_accesses([missed], config_dir=config)] == [False]
    assert native_memory_calls([missed], config_dir=config) == 1
    assert native_memory_calls_satisfied([missed], config_dir=config) == 0

    both = [missed, got]
    assert native_memory_calls(both, config_dir=config) == 2
    assert native_memory_calls_satisfied(both, config_dir=config) == 1


def test_a_call_the_stream_never_answered_is_unobserved_not_failed(tmp_path: Path) -> None:
    """A stream truncated before the tool returned carries no answer. That is a different fact
    from an error, and collapsing it to "not satisfied" would report a definite failure the run
    never observed.

    Survives an isolated revert of the `call.result is None` branch in `call_satisfied` to
    `return not call.is_error`."""
    config = tmp_path / "config"
    memory = config / "projects" / "-tmp" / "memory"
    memory.mkdir(parents=True)
    unanswered = _read_call(str(memory / "MEMORY.md"))
    assert unanswered.result is None

    assert [a.satisfied for a in native_memory_accesses([unanswered], config_dir=config)] == [None]
    assert native_memory_calls([unanswered], config_dir=config) == 1
    assert native_memory_calls_satisfied([unanswered], config_dir=config) == 0


def test_the_stream_parser_carries_the_tool_results_error_flag() -> None:
    """`satisfied` is only as good as the flag it reads, and that flag was being dropped on the
    floor: `tool_calls_from_stream` joined the result TEXT and discarded `is_error`.

    Survives an isolated revert of `is_error=` in `tool_calls_from_stream`'s `ToolCall(...)`."""
    stream = serialize_stream(
        [
            assistant_event(
                [
                    ("Read", {"file_path": "a"}, "t1"),
                    ("Read", {"file_path": "b"}, "t2"),
                ]
            ),
            tool_result_event("t1", "File does not exist.", is_error=True),
            tool_result_event("t2", "the port is 48317"),
            result_event(),
        ]
    )
    calls = tool_calls_from_stream(stream)
    assert [(c.is_error, call_satisfied(c)) for c in calls] == [(True, False), (False, True)]


def test_a_settings_read_under_the_config_dir_is_not_a_memory_call(tmp_path: Path) -> None:
    """Containment is necessary and NOT sufficient — the `memory` segment is required too, or the
    agent reading its own settings would be scored as recalling."""
    config = tmp_path / "config"
    config.mkdir()
    assert native_memory_calls([_read_call(str(config / "settings.json"))], config_dir=config) == 0


def test_a_memory_path_outside_the_pinned_config_dir_is_not_attributed(tmp_path: Path) -> None:
    """The operator's own memory index is not the agent's reach. A path that merely LOOKS like a
    memory file, outside the surface, counts for nothing."""
    config = tmp_path / "config"
    config.mkdir()
    outsider = tmp_path / "elsewhere" / "memory" / "MEMORY.md"
    outsider.parent.mkdir(parents=True)
    assert native_memory_calls([_read_call(str(outsider))], config_dir=config) == 0


def test_native_reads_and_writes_are_told_apart(tmp_path: Path) -> None:
    """Distinct counts per direction, and neither equals the total: two reads, one write."""
    config = tmp_path / "config"
    memory = config / "projects" / "-tmp" / "memory"
    memory.mkdir(parents=True)
    calls = [
        _read_call(str(memory / "MEMORY.md")),
        _read_call(str(memory / "a-topic.md")),
        _read_call(str(memory / "b-topic.md"), tool="Write"),
    ]
    accesses = native_memory_accesses(calls, config_dir=config)
    assert sum(1 for a in accesses if a.is_read) == 2
    assert sum(1 for a in accesses if a.is_write) == 1
    assert [a.verb for a in accesses] == ["native_read", "native_read", "native_write"]


def test_an_unpinned_surface_attributes_nothing(tmp_path: Path) -> None:
    """No pinned config dir means no path the harness owns, so the recognizer reports nothing
    rather than falling back to the operator's home."""
    assert (
        native_memory_calls([_read_call("/home/someone/.claude/memory/MEMORY.md")], config_dir=None)
        == 0
    )


def test_the_native_tools_are_actually_allowed(tmp_path: Path) -> None:
    """A recognizer for a tool the step forbids measures nothing. `Read` was denied on the first
    paid cycle, which is why the reach came back permission_denied."""
    assert "Read" in MEMORY_ALLOWED_TOOLS
    assert set(NATIVE_MEMORY_TOOL_NAMES) - {"NotebookEdit"} <= set(MEMORY_ALLOWED_TOOLS)


# --------------------------------------------------------------------------- #
# mem-8fv4t: a write is bd's acknowledgement, not the verb token
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("command", "key", "operands"),
    [
        ("bd remember 'a value' --key k", "k", ("a value",)),
        ("bd remember --key=k 'a value'", "k", ("a value",)),
        ("bd remember --key k 'a value'", "k", ("a value",)),
        ("bd remember list", "", ("list",)),
        ("bd remember", "", ()),
        ("bd remember 'a value' --json", "", ("a value",)),
    ],
)
def test_remember_argv_splits_key_from_content(
    command: str, key: str, operands: tuple[str, ...]
) -> None:
    (invocation,) = memory_invocations_in_command(command)
    assert (invocation.verb, invocation.key, invocation.operands) == ("remember", key, operands)


@pytest.mark.parametrize(
    ("result", "accepted", "recalled"),
    [
        ("Remembered [k]: a value", True, False),
        ("Updated [k]: a value", True, False),
        ('{"action":"remembered","key":"k"}', True, False),
        ('{"action":"updated","key":"k"}', True, False),
        ('(recalled "k" -- a bare existing key READS. To overwrite: ...)\na value', False, True),
        ('{"action":"recalled","found":true,"key":"k"}', False, True),
        ('Error: "list" looks like a command, not something to remember', False, False),
        ("", False, False),
        (None, False, False),
        # An echo of the acknowledgement mid-line is not the acknowledgement: bd prints it at
        # column 0.
        ("note: Remembered [k]: a value", False, False),
    ],
)
def test_bd_remember_acknowledgement_is_format_anchored(
    result: str | None, accepted: bool, recalled: bool
) -> None:
    assert remember_was_accepted(result) is accepted
    assert remember_was_a_recall(result) is recalled


def test_an_accepted_write_needs_both_an_operand_and_an_acknowledgement() -> None:
    ack = "Remembered [k]: a value"
    assert MemoryInvocation("remember", ("a value",), "k", ack).is_accepted_write
    assert MemoryInvocation("remember", ("a value",), "", ack).is_accepted_write
    assert not MemoryInvocation("remember", ("list",), "", None).is_accepted_write
    assert not MemoryInvocation("remember", (), "", ack).is_accepted_write
    assert not MemoryInvocation("recall", ("k",), "", ack).is_accepted_write
    # Verb-level `is_write` is untouched: E3b's endogenous-write metric still keys on the verb.
    assert MemoryInvocation("remember", ("list",), "", None).is_write


def test_memory_invocations_carry_each_calls_own_result() -> None:
    """The result is joined per CALL, so two remembers in one leg score independently."""
    calls = [
        ToolCall(
            name="Bash",
            arguments={"command": "bd remember list 2>&1 | head -100"},
            result='Error: "list" looks like a command, not something to remember',
        ),
        ToolCall(
            name="Bash",
            arguments={"command": "bd remember 'a value' --key k"},
            result="Remembered [k]: a value",
        ),
        ToolCall(name="Bash", arguments={"command": "bd remember k"}, result='(recalled "k" -- x)'),
    ]
    invocations = memory_invocations(calls)
    assert [inv.is_accepted_write for inv in invocations] == [False, True, False]
    assert [inv.is_recall_by_result for inv in invocations] == [False, False, True]


_REFUSAL = 'Error: "list" looks like a command, not something to remember'


@pytest.mark.parametrize(
    ("command", "result", "accepted", "recalled"),
    [
        # The review's shape: one refusal and one ack for two invocations in ONE Bash call.
        # The whole-result join scored write_calls=2 here.
        (
            "bd remember list; bd remember 'ok' --key k",
            f"{_REFUSAL}\nRemembered [k]: ok",
            [False, True],
            [False, False],
        ),
        # A keyed invocation takes the line carrying ITS key, not the first line.
        (
            "bd remember 'a' --key j && bd remember 'b' --key k",
            "Remembered [k]: b",
            [False, True],
            [False, False],
        ),
        # Unkeyed invocations consume unmatched ack lines in stream order: one line, one write.
        ("bd remember 'a'; bd remember 'b'", "Remembered [x]: a", [True, False], [False, False]),
        # Both acknowledged: two lines, two writes.
        (
            "bd remember 'a' --key j; bd remember 'b' --key k",
            "Remembered [j]: a\nUpdated [k]: b",
            [True, True],
            [False, False],
        ),
        # The recalled marker is attributed the same way and is never an acceptance.
        (
            "bd remember k; bd remember 'v' --key j",
            '(recalled "k" -- a bare existing key READS)\nRemembered [j]: v',
            [False, True],
            [True, False],
        ),
        ("bd remember k; bd remember k", '(recalled "k" -- x)', [False, False], [True, False]),
        # A refusal is never an ack: neither invocation stored anything.
        (
            "bd remember list; bd remember foo",
            f"{_REFUSAL}\n{_REFUSAL}",
            [False, False],
            [False, False],
        ),
        # --json: one object per invocation, matched by key where the object carries one.
        (
            "bd remember 'a' --key j --json; bd remember 'b' --key k --json",
            '{"action": "remembered", "key": "k"}',
            [False, True],
            [False, False],
        ),
    ],
    ids=[
        "refusal-then-ack",
        "keyed-takes-its-own-line",
        "unkeyed-stream-order",
        "two-lines-two-writes",
        "recalled-and-ack",
        "recalled-once",
        "two-refusals",
        "json-keyed",
    ],
)
def test_one_acknowledgement_line_acknowledges_at_most_one_invocation(
    command: str, result: str, accepted: list[bool], recalled: list[bool]
) -> None:
    """Review F1: a Bash call chaining two bd invocations has ONE tool_result. Riding the whole
    result on every invocation let one ``Remembered`` line acknowledge both, so a refused
    ``bd remember list`` next to a real write scored as two writes."""
    invocations = memory_invocations([_bash_call(command, result)])
    assert [inv.is_accepted_write for inv in invocations] == accepted
    assert [inv.is_recall_by_result for inv in invocations] == recalled


def test_a_single_invocation_keeps_the_whole_result() -> None:
    """The exact join for one invocation is unchanged: whatever bd printed is its result."""
    (invocation,) = memory_invocations(
        [_bash_call("bd remember 'ok' --key k", "noise\nRemembered [k]: ok")]
    )
    assert invocation.result == "noise\nRemembered [k]: ok"
    truncated = memory_invocations([_bash_call("bd remember 'ok' --key k; bd recall k", None)])
    assert [inv.result for inv in truncated] == [None, None]


def test_score_leg_counts_one_write_for_a_refusal_and_an_ack_in_one_call() -> None:
    from membench.runner.e1_grid import score_leg

    call = _bash_call(
        "bd remember list; bd remember 'ok' --key k", f"{_REFUSAL}\nRemembered [k]: ok"
    )
    assert score_leg([call], config_dir=None).write_calls == 1


def _bash_call(command: str, result: str | None) -> ToolCall:
    return ToolCall(name="Bash", arguments={"command": command}, result=result)


# --------------------------------------------------------------------------- #
# mem-zfm0m item 3: a Bash command that touches the pinned memory dir is a native access
# --------------------------------------------------------------------------- #


def _bash(command: str) -> ToolCall:
    return ToolCall(name="Bash", arguments={"command": command})


def _pinned(tmp_path: Path) -> tuple[Path, Path]:
    config = tmp_path / "config"
    memory = config / "projects" / "-tmp" / "memory"
    memory.mkdir(parents=True)
    return config, memory


@pytest.mark.parametrize(
    "template",
    [
        "cat {m}/MEMORY.md",
        "head -50 {m}/MEMORY.md",
        "tail -n 20 {m}/MEMORY.md",
        "sed -n 1,40p {m}/MEMORY.md",
        "grep -n retention {m}/MEMORY.md",
        "less {m}/MEMORY.md",
        "more {m}/MEMORY.md",
        "cat < {m}/MEMORY.md",
        "cat {m}/MEMORY.md 2>&1 | head -20",
        "cd /tmp && cat {m}/MEMORY.md",
        "/bin/cat {m}/MEMORY.md",
        'cat "$CLAUDE_CONFIG_DIR/projects/-tmp/memory/MEMORY.md"',
        "cat ${{CLAUDE_CONFIG_DIR}}/projects/-tmp/memory/MEMORY.md",
        "cd {m} && cat MEMORY.md",
        "cp {m}/MEMORY.md /tmp/copy.md",
    ],
)
def test_a_bash_read_of_the_pinned_memory_dir_is_a_native_read(
    tmp_path: Path, template: str
) -> None:
    """The recognizer keys on the ARGV SHAPE and the pinned path — the command word, its operands,
    a `<` redirect, the `$CLAUDE_CONFIG_DIR` the harness itself pinned, or a `cd` earlier in the
    same command — never on prose about memory."""
    config, memory = _pinned(tmp_path)
    accesses = native_memory_accesses([_bash(template.format(m=memory))], config_dir=config)
    assert [a.verb for a in accesses] == ["native_read"], template
    assert accesses[0].tool == "Bash"
    assert Path(accesses[0].path) == memory / "MEMORY.md"


@pytest.mark.parametrize(
    "template",
    [
        "echo '- note' > {m}/MEMORY.md",
        "echo '- note' >> {m}/MEMORY.md",
        "printf 'x' >| {m}/MEMORY.md",
        "printf 'x' &> {m}/MEMORY.md",
        "printf 'x' | tee {m}/MEMORY.md",
        "printf 'x' | tee -a {m}/MEMORY.md",
        "cp /tmp/notes.md {m}/MEMORY.md",
        "mv /tmp/notes.md {m}/MEMORY.md",
        "sed -i 's/a/b/' {m}/MEMORY.md",
        "sed -i.bak 's/a/b/' {m}/MEMORY.md",
        "sed --in-place 's/a/b/' {m}/MEMORY.md",
        "cd {m} && echo x >> MEMORY.md",
        'echo x >> "$CLAUDE_CONFIG_DIR/projects/-tmp/memory/MEMORY.md"',
    ],
)
def test_a_bash_write_into_the_pinned_memory_dir_is_a_native_write(
    tmp_path: Path, template: str
) -> None:
    config, memory = _pinned(tmp_path)
    accesses = native_memory_accesses([_bash(template.format(m=memory))], config_dir=config)
    assert [a.verb for a in accesses] == ["native_write"], template
    assert Path(accesses[0].path) == memory / "MEMORY.md"


@pytest.mark.parametrize(
    "template",
    [
        # Prose about memory is not a path: the word appears and no pinned path is touched.
        "echo 'let me check memory first'  # memory",
        "grep -rn memory /tmp/notes",
        "cat /tmp/notes/memory.md",
        # Under the config dir but not under a `memory` segment.
        "cat {c}/settings.json",
        "echo x >> {c}/settings.json",
        # A memory-looking path OUTSIDE the pinned config dir is the operator's, not the agent's.
        "cat /home/someone/.claude/projects/-tmp/memory/MEMORY.md",
        "echo x > /tmp/memory/MEMORY.md",
        # A relative path with no `cd` to anchor it names nothing the harness owns.
        "cat projects/-tmp/memory/MEMORY.md",
        # A redirect to /dev/null beside a non-memory read.
        "cat /etc/hostname 2>/dev/null",
    ],
)
def test_bash_commands_that_touch_no_pinned_memory_path_are_not_native_accesses(
    tmp_path: Path, template: str
) -> None:
    config, memory = _pinned(tmp_path)
    command = template.format(c=config, m=memory)
    assert native_memory_accesses([_bash(command)], config_dir=config) == []


@pytest.mark.parametrize(
    "template",
    [
        "rg retention {m}/MEMORY.md",
        "awk '{{print}}' {m}/MEMORY.md",
        "wc -l {m}/MEMORY.md",
        "find {m}/MEMORY.md -newer /tmp/x",
        "od -c {m}/MEMORY.md",
        "dd if={m}/MEMORY.md bs=1 count=100",
        "cut -c1-80 {m}/MEMORY.md",
        "jq . {m}/MEMORY.md",
        "stat {m}/MEMORY.md",
        "command cat {m}/MEMORY.md",
        "sudo -u me cat {m}/MEMORY.md",
        "env FOO=bar cat {m}/MEMORY.md",
        "time cat {m}/MEMORY.md",
        "nice cat {m}/MEMORY.md",
        "exec cat {m}/MEMORY.md",
        "python3 -c \"print(open('{m}/MEMORY.md').read())\"",
        "perl -ne 'print' {m}/MEMORY.md",
        "node -e \"console.log(require('fs').readFileSync('{m}/MEMORY.md','utf8'))\"",
        "bash -c 'cat {m}/MEMORY.md'",
        "cat ${{CLAUDE_CONFIG_DIR:?}}/projects/-tmp/memory/MEMORY.md",
        "cat ${{CLAUDE_CONFIG_DIR:-/nowhere}}/projects/-tmp/memory/MEMORY.md",
        "cat --show-all {m}/MEMORY.md",
        "some-tool --file={m}/MEMORY.md",
    ],
)
def test_a_bash_read_is_decided_by_the_path_not_the_command_name(
    tmp_path: Path, template: str
) -> None:
    """Review F2: the ACCESS is decided by any token resolving under the pinned memory path,
    whatever the command word (the 7-name allowlist scored `rg`, `wc`, `jq`, an inline
    interpreter, ... as zero); the command word and the redirect shape decide read vs write
    only. Wrapper words are skipped; `${VAR:?}` and `${VAR:-x}` expand like `$VAR`."""
    config, memory = _pinned(tmp_path)
    accesses = native_memory_accesses([_bash(template.format(m=memory))], config_dir=config)
    assert [a.verb for a in accesses] == ["native_read"], template
    assert Path(accesses[0].path) == memory / "MEMORY.md"
    assert accesses[0].tokenizer_failed is False


@pytest.mark.parametrize(
    "template",
    [
        "sudo tee {m}/MEMORY.md",
        "command cp /tmp/notes.md {m}/MEMORY.md",
        "env -i sed -i 's/a/b/' {m}/MEMORY.md",
        "printf x >> ${{CLAUDE_CONFIG_DIR:?}}/projects/-tmp/memory/MEMORY.md",
    ],
)
def test_direction_is_read_from_the_unwrapped_command_word(tmp_path: Path, template: str) -> None:
    config, memory = _pinned(tmp_path)
    accesses = native_memory_accesses([_bash(template.format(m=memory))], config_dir=config)
    assert [a.verb for a in accesses] == ["native_write"], template
    assert Path(accesses[0].path) == memory / "MEMORY.md"


@pytest.mark.parametrize(
    "template",
    [
        "cat 'unterminated {m}/MEMORY.md",
        'grep "x {m}/MEMORY.md; echo done',
    ],
)
def test_a_command_the_tokenizer_refuses_is_still_scanned_for_the_path(
    tmp_path: Path, template: str
) -> None:
    """Review F2: an unterminated quote used to return [] — a miss on the exact kind of
    command a model writes by accident. The path scan falls back to a whitespace split and the
    access is flagged so a reader knows the tokenizer did not vouch for it."""
    config, memory = _pinned(tmp_path)
    accesses = native_memory_accesses([_bash(template.format(m=memory))], config_dir=config)
    assert [a.verb for a in accesses] == ["native_read"], template
    assert Path(accesses[0].path) == memory / "MEMORY.md"
    assert accesses[0].tokenizer_failed is True


@pytest.mark.parametrize(
    ("template", "name"),
    [
        ("rm {m}/MEMORY.md", "MEMORY.md"),
        ("rm -rf {m}", "memory"),
        ("touch {m}/MEMORY.md", "MEMORY.md"),
        ("chmod 600 {m}/MEMORY.md", "MEMORY.md"),
        ("chown me {m}/MEMORY.md", "MEMORY.md"),
        ("truncate -s 0 {m}/MEMORY.md", "MEMORY.md"),
        ("ln -s /tmp/notes.md {m}/MEMORY.md", "MEMORY.md"),
        ("mkdir -p {m}/topics", "topics"),
        ("rmdir {m}/topics", "topics"),
    ],
)
def test_a_command_that_mutates_the_memory_file_is_a_native_write(
    tmp_path: Path, template: str, name: str
) -> None:
    """Review G1: every command word outside the write list defaulted to READ, so deleting,
    re-moding, truncating or creating a memory path scored as the agent reading it. A mutation
    is a write; it never lands beside the reads."""
    config, memory = _pinned(tmp_path)
    accesses = native_memory_accesses([_bash(template.format(m=memory))], config_dir=config)
    assert [(a.verb, Path(a.path).name) for a in accesses] == [("native_write", name)], template


def test_a_link_out_of_the_memory_dir_reads_it(tmp_path: Path) -> None:
    config, memory = _pinned(tmp_path)
    accesses = native_memory_accesses(
        [_bash(f"ln -s {memory}/MEMORY.md /tmp/link.md")], config_dir=config
    )
    assert [a.verb for a in accesses] == ["native_read"]


@pytest.mark.parametrize(
    ("template", "verb"),
    [
        ("sudo -u me tee {m}/MEMORY.md", "native_write"),
        ("sudo -u me -g us tee {m}/MEMORY.md", "native_write"),
        ("sudo -u me cat {m}/MEMORY.md", "native_read"),
        ("sudo --user=me tee {m}/MEMORY.md", "native_write"),
        ("env -i FOO=bar tee {m}/MEMORY.md", "native_write"),
        ("env -u FOO tee {m}/MEMORY.md", "native_write"),
        ("nice -n 5 tee {m}/MEMORY.md", "native_write"),
        ("nice -n 5 rm {m}/MEMORY.md", "native_write"),
        ("time -f '%e' tee {m}/MEMORY.md", "native_write"),
        ("time -o /tmp/t.log cat {m}/MEMORY.md", "native_read"),
    ],
)
def test_a_wrapper_option_value_is_not_read_as_the_command_word(
    tmp_path: Path, template: str, verb: str
) -> None:
    """Review G1: `sudo -u me tee <path>` left `me` as the command word, and `me` reads. The
    separate value of a wrapper option is consumed with the option."""
    config, memory = _pinned(tmp_path)
    accesses = native_memory_accesses([_bash(template.format(m=memory))], config_dir=config)
    assert [(a.verb, Path(a.path).name) for a in accesses] == [(verb, "MEMORY.md")], template


@pytest.mark.parametrize(
    "template",
    [
        "echo '$CLAUDE_CONFIG_DIR/projects/-tmp/memory/MEMORY.md'",
        'echo "$CLAUDE_CONFIG_DIR/projects/-tmp/memory/MEMORY.md"',
        "echo {m}/MEMORY.md",
        "printf '%s\\n' {m}/MEMORY.md",
        "echo reading {m}/MEMORY.md now",
    ],
)
def test_an_echoed_path_is_not_an_access(tmp_path: Path, template: str) -> None:
    """Review G3: `echo <path>` prints the path and opens nothing, quoted or not. The operands
    of a non-accessing command attribute nothing; only a redirect beside them does."""
    config, memory = _pinned(tmp_path)
    assert native_memory_accesses([_bash(template.format(m=memory))], config_dir=config) == []


def test_a_redirect_beside_a_non_accessing_command_still_counts(tmp_path: Path) -> None:
    config, memory = _pinned(tmp_path)
    accesses = native_memory_accesses(
        [_bash(f"echo {memory}/topic.md >> {memory}/MEMORY.md")], config_dir=config
    )
    assert [(a.verb, Path(a.path).name) for a in accesses] == [("native_write", "MEMORY.md")]


@pytest.mark.parametrize(
    ("template", "verb", "name"),
    [
        ('cd "$CLAUDE_CONFIG_DIR/projects/-tmp/memory" && cat MEMORY', "native_read", "MEMORY"),
        ("cd {m} && cat MEMORY", "native_read", "MEMORY"),
        ("cd {m}; rm MEMORY", "native_write", "MEMORY"),
        ("cd {m} && cat < MEMORY", "native_read", "MEMORY"),
        ("cd {c} && cd projects/-tmp/memory && cat MEMORY", "native_read", "MEMORY"),
    ],
)
def test_inside_the_pinned_memory_dir_every_operand_is_a_path(
    tmp_path: Path, template: str, verb: str, name: str
) -> None:
    """Review G2: the relative-path shape rule (a `/` or a `.`) kept `cd /tmp && grep x
    memory/f` from scoring `x`, and also kept `cd <memory dir> && cat MEMORY` from scoring the
    memory file. When the cd anchor resolves under the pin, every operand resolves against it."""
    config, memory = _pinned(tmp_path)
    command = template.format(m=memory, c=config)
    accesses = native_memory_accesses([_bash(command)], config_dir=config)
    assert [(a.verb, Path(a.path).name) for a in accesses] == [(verb, name)], command
    assert Path(accesses[0].path) == memory / name


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("cd {m} && chmod 600 MEMORY.md", [("native_write", "MEMORY.md")]),
        ("cd {m} && chown me MEMORY.md", [("native_write", "MEMORY.md")]),
        ("cd {m} && grep pattern", []),
        ("cd {m} && grep pattern MEMORY.md", [("native_read", "MEMORY.md")]),
        ("cd {m} && grep -e pat MEMORY.md", [("native_read", "MEMORY.md")]),
        ("cd {m} && grep --regexp=pat MEMORY.md", [("native_read", "MEMORY.md")]),
        ("cd {m} && grep -A 3 pat MEMORY.md", [("native_read", "MEMORY.md")]),
        ("cd {m} && sed -n 1,40p MEMORY.md", [("native_read", "MEMORY.md")]),
        ("cd {m} && sed -e 1,40p MEMORY.md", [("native_read", "MEMORY.md")]),
        ("cd {m} && head -n 50 MEMORY.md", [("native_read", "MEMORY.md")]),
        ("cd {m} && tail -n 20", []),
        ("cd {m} && awk '{{print}}' MEMORY.md", [("native_read", "MEMORY.md")]),
        ("cd {m} && find . -name MEMORY.md", [("native_read", "memory")]),
        ("cd {m} && truncate -s 0 MEMORY.md", [("native_write", "MEMORY.md")]),
        ("cd {m} && cut -d : -f 1 MEMORY.md", [("native_read", "MEMORY.md")]),
        (
            "cd {m} && ln -s MEMORY.md link",
            [("native_read", "MEMORY.md"), ("native_write", "link")],
        ),
    ],
)
def test_inside_the_pinned_memory_dir_only_path_operands_anchor(
    tmp_path: Path, template: str, expected: list[tuple[str, str]]
) -> None:
    """Review H1: the in-pin widening made EVERY non-flag word a path, so `chmod 600 MEMORY.md`
    was two writes and `grep pattern` a read of `<memory>/pattern` — counters inflated per call
    and a reading leg manufactured. A value word (a mode, a pattern, a script, a flag's value)
    is policy-enumerated and never anchored; a command left with no path operand attributes
    nothing."""
    config, memory = _pinned(tmp_path)
    accesses = native_memory_accesses([_bash(template.format(m=memory))], config_dir=config)
    assert [(a.verb, Path(a.path).name) for a in accesses] == expected, template
    for access in accesses:
        assert Path(access.path).is_relative_to(memory)


def test_in_pin_value_words_do_not_inflate_the_per_call_counters(tmp_path: Path) -> None:
    from membench.runner.e1_grid import score_leg

    config, memory = _pinned(tmp_path)
    chmod = _bash(f"cd {memory} && chmod 600 MEMORY.md")
    assert score_leg([chmod], config_dir=config).write_calls == 1
    grep = _bash(f"cd {memory} && grep pattern")
    assert score_leg([grep], config_dir=config).read_calls == 0
    sed = _bash(f"cd {memory} && sed -n 1,40p MEMORY.md")
    assert score_leg([sed], config_dir=config).read_calls == 1


def test_outside_the_pinned_memory_dir_a_bare_operand_is_still_not_a_path(tmp_path: Path) -> None:
    config, memory = _pinned(tmp_path)
    parent = memory.parent
    accesses = native_memory_accesses(
        [_bash(f"cd {parent} && cat memory/MEMORY")], config_dir=config
    )
    assert [Path(a.path).name for a in accesses] == ["MEMORY"]
    assert native_memory_accesses([_bash(f"cd {parent} && cat memory")], config_dir=config) == []


def test_a_pinned_path_is_reported_once_per_token(tmp_path: Path) -> None:
    config, memory = _pinned(tmp_path)
    accesses = native_memory_accesses([_bash(f"cat {memory}/MEMORY.md")], config_dir=config)
    assert len(accesses) == 1


def test_one_bash_command_can_read_one_memory_file_and_write_another(tmp_path: Path) -> None:
    """Direction is per PATH, so a copy from one memory file into another is one read and one
    write — and it is ONE call, matching the block-not-verb rule for bd."""
    config, memory = _pinned(tmp_path)
    calls = [_bash(f"cat {memory}/MEMORY.md >> {memory}/topic.md")]
    accesses = native_memory_accesses(calls, config_dir=config)
    assert [(a.verb, Path(a.path).name) for a in accesses] == [
        ("native_read", "MEMORY.md"),
        ("native_write", "topic.md"),
    ]
    assert native_memory_calls(calls, config_dir=config) == 1


def test_memory_reaching_calls_counts_a_call_once_across_both_affordances(tmp_path: Path) -> None:
    """A Bash command that runs `bd recall` AND cats the native memory file reached memory ONCE
    (one tool call), while a bd-only call and a native-only call each count on their own."""
    config, memory = _pinned(tmp_path)
    both = _bash(f"bd recall k; cat {memory}/MEMORY.md")
    bd_only = _bash("bd recall k")
    native_only = _read_call(str(memory / "MEMORY.md"))
    neither = _bash("ls /tmp")
    assert memory_reaching_calls([both], config_dir=config) == 1
    assert memory_reaching_calls([both, bd_only, native_only, neither], config_dir=config) == 3
    assert memory_reaching_calls([native_only], config_dir=None) == 0


def test_a_bash_call_and_a_read_tool_call_carry_their_own_call_index(tmp_path: Path) -> None:
    config, memory = _pinned(tmp_path)
    calls = [
        _bash("ls /tmp"),
        _read_call(str(memory / "MEMORY.md")),
        _bash(f"cat {memory}/MEMORY.md; cat {memory}/topic.md"),
    ]
    accesses = native_memory_accesses(calls, config_dir=config)
    assert [a.call_index for a in accesses] == [1, 2, 2]
    assert native_memory_calls(calls, config_dir=config) == 2
    assert isinstance(accesses[0], NativeMemoryAccess)


# --------------------------------------------------------------------------- #
# mem-zfm0m item 6: the recognizer's constants are part of the surface policy
# --------------------------------------------------------------------------- #


def _mutated(value: object) -> object:
    """A value of the same kind that differs from ``value``, so the mutation is one the constant's
    readers could see rather than a type change."""
    if isinstance(value, re.Pattern):
        return re.compile(value.pattern + "x", value.flags)
    if isinstance(value, bool):
        return not value
    if isinstance(value, int | float):
        return value + 1
    if isinstance(value, str):
        return value + "x"
    if isinstance(value, tuple):
        return (*value, "x")
    if isinstance(value, frozenset):
        return value | {"x"}
    raise TypeError(f"no mutation for a {type(value).__name__}")


@pytest.mark.parametrize("name", sorted(recognizer_policy()))
def test_surface_fingerprint_moves_when_any_recognizer_constant_changes(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """mem-zfm0m item 6, review F4. The recognizers decide what a leg SCORES, so every constant
    they read is surface policy: a resume against an artifact counted under a different recognizer
    would pool two measurements under one identity. The list is ENUMERATED from the module (every
    name under a stated prefix), not hand-written, so a constant added later cannot be left out."""
    before = surface_fingerprint()
    monkeypatch.setattr(tool_surface, name, _mutated(getattr(tool_surface, name)))
    assert surface_fingerprint() != before


def test_the_recognizer_implementation_version_is_policy() -> None:
    """Review G5: the shape rule and the rest of the recognizer's logic live in code, outside
    any constant, so a version number stands in for them in the fingerprint. It is an int, in
    the policy, and at least 2 (G1-G3 changed the logic after the version-1 recognizer)."""
    version = tool_surface.RECOGNIZER_IMPLEMENTATION_VERSION
    assert isinstance(version, int) and version >= 3
    assert recognizer_policy()["RECOGNIZER_IMPLEMENTATION_VERSION"] == version


def test_the_recognizers_read_their_command_names_from_the_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review G5: `cd`, `sed` and the assignment-taking wrapper were literals in the matcher,
    fingerprinted by nothing. Each is a policy constant the matcher READS: renaming it in the
    policy renames what the matcher recognizes."""
    config, memory = _pinned(tmp_path)

    def verbs(command: str) -> list[tuple[str, str]]:
        accesses = native_memory_accesses([_bash(command)], config_dir=config)
        return [(a.verb, Path(a.path).name) for a in accesses]

    assert verbs(f"cd {memory} && cat MEMORY.md") == [("native_read", "MEMORY.md")]
    monkeypatch.setattr(tool_surface, "NATIVE_MEMORY_BASH_CD", "chdir")
    assert verbs(f"chdir {memory} && cat MEMORY.md") == [("native_read", "MEMORY.md")]
    # `cd` is now an ordinary command whose operand is the memory dir itself.
    assert verbs(f"cd {memory} && cat MEMORY.md") == [("native_read", "memory")]

    assert verbs(f"sed -i s/a/b/ {memory}/MEMORY.md") == [("native_write", "MEMORY.md")]
    monkeypatch.setattr(tool_surface, "NATIVE_MEMORY_BASH_SED", "ssed")
    assert verbs(f"ssed -i s/a/b/ {memory}/MEMORY.md") == [("native_write", "MEMORY.md")]
    assert verbs(f"sed -i s/a/b/ {memory}/MEMORY.md") == [("native_read", "MEMORY.md")]

    assert verbs(f"env FOO=bar tee {memory}/MEMORY.md") == [("native_write", "MEMORY.md")]
    monkeypatch.setattr(tool_surface, "NATIVE_MEMORY_BASH_ASSIGNMENT_WRAPPERS", ())
    assert verbs(f"env FOO=bar tee {memory}/MEMORY.md") == [("native_read", "MEMORY.md")]


def test_the_recognizer_policy_covers_every_constant_the_recognizers_read() -> None:
    """Review F4: the ack/recall grammar, the argv grammar and the native Bash recognizer's tables
    are all in; the only module-level constants outside the policy are the ones that do not
    change what a leg scores, named here so a new constant must be placed on one side or the
    other."""
    policy = set(recognizer_policy())
    assert {
        "_BD_REMEMBER_ACK",
        "_BD_REMEMBER_RECALLED",
        "_BD_REMEMBER_ACK_ACTIONS",
        "_GRAMMAR_SEGMENT_BREAKS",
        "_GRAMMAR_SHELL_KEYWORDS",
        "_GRAMMAR_CONFIG_DIR_SPELLINGS",
        "BD_KEY_FLAG",
        "BD_VALUE_FLAGS",
        "MEMORY_VERBS",
        "MEMORY_COMMAND",
        "HOST_DENIED_TOOLS",
        "NATIVE_MEMORY_BASH_WRAPPERS",
        "NATIVE_MEMORY_BASH_WRAPPER_VALUE_FLAGS",
        "NATIVE_MEMORY_BASH_WRITE_ALL_OPERANDS",
        "NATIVE_MEMORY_BASH_WRITE_LAST_OPERAND",
        "NATIVE_MEMORY_BASH_NON_ACCESSING_COMMANDS",
        "NATIVE_MEMORY_BASH_CD",
        "NATIVE_MEMORY_BASH_SED",
        "NATIVE_MEMORY_BASH_ASSIGNMENT_WRAPPERS",
        "NATIVE_MEMORY_BASH_LEADING_VALUE_OPERANDS",
        "NATIVE_MEMORY_BASH_COMMAND_VALUE_FLAGS",
        "RECOGNIZER_IMPLEMENTATION_VERSION",
        "NATIVE_MEMORY_BASH_PATH_TERMINATORS",
        "CONFIG_DIR_ENV",
    } <= policy
    uppercase = {
        name
        for name, value in vars(tool_surface).items()
        if re.fullmatch(r"_?[A-Z][A-Z0-9_]*", name) and not callable(value)
    }
    assert uppercase - policy == {
        "PROVISION_TIMEOUT_S",
        "CALL_TIMEOUT_S",
        "ENV_BD_BINARY",
        "_POLICY_PREFIXES",
    }
