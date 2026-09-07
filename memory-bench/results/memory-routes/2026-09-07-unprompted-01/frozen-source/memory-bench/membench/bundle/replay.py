"""Trace->diff REPLAY reconstructor -- the bundle's gold-diff `output` leg (mem-75t.7.1).

Plan §9.1 (accepted review revision): the gold diff is produced by REPLAY, not
reconstruction. The caller checks out ``repo@base_commit`` (env_recon's job -- checkout
is explicitly NOT this module's concern), this module replays the transcript's
file-mutation tool calls (``Edit``/``Write``/``MultiEdit``, in transcript order) against
that checkout, and ``git diff`` over the mutated tree IS the gold diff. Two properties
fall out of the replay framing:

- the diff is a real, applyable git diff (near-Option-B exactness for the file-edit
  mutation class), and
- fidelity validation is free: every ``old_string`` that fails to match checkout state
  is a DETECTED drift, classified per call (`ReplayOutcome`) rather than silently
  swallowed. ``replay_success_rate`` = APPLIED / total mutation calls is the bead-level
  fidelity number the P0 acceptance reports.

Replay mirrors Claude Code's own tool semantics: ``Edit`` is exact unique-substring
replacement (ambiguous or missing ``old_string`` fails unless ``replace_all``);
``Write`` is a full-file overwrite that creates the file (and parents); ``MultiEdit``
is a SEQUENTIAL edit list on one file, applied all-or-nothing. Transcript paths are
absolute in the ORIGINAL session's tree, so they are rebased onto the checkout via the
``work_dir`` prefix; a path that does not normalize to inside ``work_dir``
(including ``..`` escapes) is the classified skip `OUTSIDE_WORK_DIR`, never a write
outside the checkout.

The rebase prefix itself is UNRELIABLE on the record (mem-75t.7.1 validation,
.gc/docs/mem-75t.7.1-replay-validation.md): ``record.work_dir`` is the clone root while
sessions ran in nested (``.claude/worktrees/<name>``) or sibling (``<clone>-wt-<id>``)
git worktrees, and per-event ``cwd`` reports the clone root even when edits target a
sibling worktree. `infer_work_dir` is the prescribed majority-prefix inference over
the mutation paths themselves; `effective_work_dir` is the assembler-side contract
that selects the rebase prefix from the majority-prefix chain (record-anchored, the
recovery that lifted 3/8 validation beads from a 0.00 replay rate).

Mutation classes the transcript CANNOT carry (inherent fidelity bounds, surfaced as
drift on any later edit that touches their output rather than hidden):

- shell-mediated mutations (``Bash`` ``mv``/``rm``/``sed``/``git apply``/heredocs) --
  no structured path+content argument to replay (same exclusion as harbor_exec's
  ``_FILE_TOOLS`` harvest);
- codegen / build artifacts (files produced by running tools, not by edit calls);
- ``NotebookEdit`` cell operations (harvested as "written" by harbor_exec, but cell
  surgery is not replayable as text substitution -- excluded here);
- file deletions, renames and permission changes (no deleting tool call exists);
- tool calls that ERRORED in the original session: results are not correlated back to
  calls, so an originally-rejected Edit is replayed as-is and surfaces as a classified
  mismatch, slightly deflating the success rate rather than inflating it.

ZFC: pure mechanism -- IO, structural validation, string replacement and arithmetic.
No model calls, no semantic heuristics. The subprocess runner is injectable (the same
``Runner`` pattern as `membench.harbor.env_recon`) so the git-diff leg is testable
against real temp repos without monkeypatching.
"""

import json
import posixpath
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)

from membench.harbor.harbor_exec import _FILE_TOOLS
from membench.spawn import Runner

# The replayable subset of harbor_exec's file tools: structured path AND structured
# content. (Read carries no mutation; NotebookEdit mutates but not as text substitution.)
MutationTool = Literal["Edit", "Write", "MultiEdit"]
_MUTATION_TOOLS: tuple[MutationTool, ...] = ("Edit", "Write", "MultiEdit")


class ReplayOutcome(StrEnum):
    """Per-call replay classification. Never a bare boolean: a non-APPLIED call is a
    *detected* fidelity failure whose class feeds the P0 acceptance report."""

    APPLIED = "applied"
    OLD_STRING_MISSING = "old_string_missing"
    OLD_STRING_AMBIGUOUS = "old_string_ambiguous"
    FILE_ABSENT = "file_absent"
    OUTSIDE_WORK_DIR = "outside_work_dir"


class EditOp(BaseModel):
    """One exact-substring replacement (a single Edit, or one MultiEdit element)."""

    model_config = ConfigDict(frozen=True)

    old_string: str
    new_string: str
    replace_all: bool = False


class MutationCall(BaseModel):
    """One file-mutation tool call, in transcript order. ``edits`` carries Edit (one op)
    and MultiEdit (n ops); ``content`` carries Write's full-file payload."""

    model_config = ConfigDict(frozen=True)

    tool: MutationTool
    path: str
    edits: tuple[EditOp, ...] = ()
    content: str | None = None

    @model_validator(mode="after")
    def _payload_matches_tool(self) -> "MutationCall":
        if self.tool == "Write" and self.content is None:
            raise ValueError("Write call requires content")
        if self.tool != "Write" and not self.edits:
            raise ValueError(f"{self.tool} call requires at least one edit op")
        return self


class CallReplay(BaseModel):
    """The replay outcome of one `MutationCall`. ``rebased_path`` is None exactly when
    the outcome is `OUTSIDE_WORK_DIR`; ``detail`` localizes the failure (which MultiEdit
    op, how many ambiguous matches)."""

    model_config = ConfigDict(frozen=True)

    index: int
    tool: str
    path: str
    rebased_path: str | None
    outcome: ReplayOutcome
    detail: str = ""


class ReplayResult(BaseModel):
    """The structured replay product: per-call outcomes, the per-file gold diff (paths
    as git reports them, relative to the checkout root), and the fidelity rate.

    ``file_diffs`` is stored as sorted ``(path, diff)`` pairs, not a dict: a dict field
    inside a frozen pydantic model is still mutable in place, which would break the
    frozen-value-object contract. A mapping passed at construction (what `gold_diff`
    produces) is converted; use `diff_by_file` for mapping-shaped access.

    ``replay_success_rate`` for an empty call list is 0.0 by definition: a transcript
    with no file mutations yields no gold diff, and 0.0 marks it non-admittable rather
    than vacuously perfect.

    Two admission signals are DERIVED from ``calls`` (computed, so they can never
    drift from the per-call evidence, and they serialize with the result):

    - ``adjusted_replay_success_rate`` -- APPLIED / (total - OUTSIDE_WORK_DIR).
      OUTSIDE_WORK_DIR calls (dominantly auto-memory writes under a ``.claude*`` home,
      e.g. ``/home/ds/.claude-homes/...``) are out-of-repo BY CONSTRUCTION: they never
      rebase into the checkout, so they cannot affect the gold diff and must not
      deflate fidelity. 0.0 when no in-repo calls remain.
    - ``base_predates_tree`` -- True when some file's FIRST mutation hit `FILE_ABSENT`.
      Only Edit/MultiEdit can yield FILE_ABSENT (Write creates), so a first-touch
      absence means the session's tree already had the file while the
      timestamp-approximate ``base_commit`` does not: the base predates the tree
      (mem-75t.7.1: zg4da/041jz)."""

    model_config = ConfigDict(frozen=True)

    calls: tuple[CallReplay, ...]
    file_diffs: tuple[tuple[str, str], ...]
    replay_success_rate: float

    @field_validator("file_diffs", mode="before")
    @classmethod
    def _file_diffs_as_pairs(cls, value: object) -> object:
        if isinstance(value, Mapping):
            return tuple(sorted(value.items()))
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def adjusted_replay_success_rate(self) -> float:
        applied = sum(1 for c in self.calls if c.outcome is ReplayOutcome.APPLIED)
        in_repo = sum(1 for c in self.calls if c.outcome is not ReplayOutcome.OUTSIDE_WORK_DIR)
        return applied / in_repo if in_repo else 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def base_predates_tree(self) -> bool:
        return bool(self.first_edit_absent_paths())

    def first_edit_absent_paths(self) -> tuple[str, ...]:
        """The (normalized, transcript-order) paths whose FIRST mutation call came back
        `FILE_ABSENT` -- the per-file evidence behind ``base_predates_tree``. ``calls``
        is in transcript order, so the first sighting of a path IS its first mutation."""
        seen: set[str] = set()
        absent: list[str] = []
        for call in self.calls:
            norm = posixpath.normpath(call.path)
            if norm in seen:
                continue
            seen.add(norm)
            if call.outcome is ReplayOutcome.FILE_ABSENT:
                absent.append(norm)
        return tuple(absent)

    def diff_by_file(self) -> dict[str, str]:
        """The per-file diffs as a FRESH mapping -- mutating it never touches the model."""
        return dict(self.file_diffs)


def _mutation_call_from_block(name: MutationTool, args: Mapping[str, Any]) -> MutationCall:
    """Build the `MutationCall` for one tool_use block, validating structure loudly --
    a mutation call missing its payload is a malformed transcript, never a skip."""
    path_arg = _FILE_TOOLS[name][0]
    try:
        if name == "Write":
            return MutationCall(tool=name, path=args[path_arg], content=args["content"])
        if name == "Edit":
            ops: tuple[Mapping[str, Any], ...] = (args,)
        else:  # MultiEdit
            ops = tuple(args["edits"])
        edits = tuple(
            EditOp(
                old_string=op["old_string"],
                new_string=op["new_string"],
                replace_all=bool(op.get("replace_all", False)),
            )
            for op in ops
        )
        return MutationCall(tool=name, path=args[path_arg], edits=edits)
    except (KeyError, TypeError, ValidationError) as exc:
        raise ValueError(f"malformed {name} tool call (args {dict(args)!r}): {exc}") from exc


def parse_mutation_calls(stream: str) -> tuple[MutationCall, ...]:
    """The transcript's `Edit`/`Write`/`MultiEdit` calls, in order, with full content.

    Same .jsonl event walk as harbor_exec's `project_claude_stream` (``tool_use``
    blocks inside ``message.content``), but ORDERED and content-bearing where that
    harvest only aggregates path sets -- the bundle side needs the payloads to replay.
    Non-JSON lines and non-message events are skipped (matching the documented
    `project_claude_stream` tolerance); a malformed MUTATION call raises."""
    calls: list[MutationCall] = []
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
            if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                continue
            name = block.get("name")
            if name not in _MUTATION_TOOLS:
                continue
            args = block.get("input")
            if not isinstance(args, Mapping):
                raise ValueError(f"malformed {name} tool call: input is not a mapping")
            calls.append(_mutation_call_from_block(name, args))
    return tuple(calls)


def infer_work_dir(calls: Sequence[MutationCall]) -> str | None:
    """The session's work dir inferred from the mutation paths themselves -- the
    mechanical recovery the mem-75t.7.1 validation proved (3/8 beads recovered from a
    0.00 replay rate; ``record.work_dir`` is the clone root, per-event ``cwd`` lies
    under EnterWorktree).

    Exact rule (pure path arithmetic over the set of DISTINCT absolute mutation
    paths -- a hot file edited many times counts once): starting at the filesystem
    root, repeatedly descend into the child directory that contains a STRICT majority
    (count * 2 > total) of the paths; stop when no child qualifies. The result is the
    deepest directory prefix shared by a strict majority of the paths.

    Tiebreaker: two sibling directories cannot both hold a strict majority, so the
    descent chain is unique; an exact split (e.g. 50/50) is not a majority, the
    descent stops, and the shared PARENT wins.

    Returns None when inference has nothing to say: no absolute paths at all, or no
    shared prefix beyond the filesystem root (a caller must then fall back to the
    record's work_dir rather than rebase everything against ``/``).

    Known approximation: when a strict majority of paths sits in one subtree, the
    inferred prefix can be DEEPER than the true session root (observed on the real
    validation traces: mem-us6j infers ``<repo>/src``, 2nbe9 infers
    ``<worktree>/frontend/src``). `effective_work_dir` therefore selects FROM the
    majority chain instead of taking this deepest element blindly; a wrong rebase
    always surfaces as classified drift (FILE_ABSENT) and the admission threshold
    rejects the bundle -- fail-closed, never a silently wrong gold diff."""
    chain = _majority_prefix_chain(_distinct_absolute_paths(calls))
    return str(chain[-1]) if chain else None


def _distinct_absolute_paths(calls: Sequence[MutationCall]) -> tuple[PurePosixPath, ...]:
    paths = {PurePosixPath(posixpath.normpath(call.path)) for call in calls}
    return tuple(p for p in paths if p.is_absolute())


def _majority_prefix_chain(paths: Sequence[PurePosixPath]) -> tuple[PurePosixPath, ...]:
    """Every directory prefix that covers a strict majority of ``paths``, shallowest
    first, excluding the filesystem root. Strict-majority prefixes always form a
    single root-to-leaf chain (two of them must share a covered path, so one contains
    the other), which is what makes "the deepest" well-defined."""
    if not paths:
        return ()
    total = len(paths)
    prefix = PurePosixPath("/")
    chain: list[PurePosixPath] = []
    while True:
        children = Counter(
            path.relative_to(prefix).parts[0]
            for path in paths
            # >= 2 parts: a directory component below prefix, then at least the file.
            if path.is_relative_to(prefix) and len(path.relative_to(prefix).parts) >= 2
        )
        if not children:
            break
        child, count = children.most_common(1)[0]
        if count * 2 <= total:
            break
        prefix = prefix / child
        chain.append(prefix)
    return tuple(chain)


# The Claude Code NESTED-worktree layout (validation shape: the 4bol-health session
# rooted at <clone>/.claude/worktrees/<name>). A harness-layout convention like
# harbor_exec's _FILE_TOOLS tool names -- structural, not a semantic guess.
_NESTED_WORKTREE_SEGMENTS: tuple[str, str] = (".claude", "worktrees")


def effective_work_dir(record_work_dir: str, calls: Sequence[MutationCall]) -> str:
    """The rebase prefix the bundle assembler's replay must use -- the mem-75t.7.1
    recovery, formalized. ``record.work_dir`` zeroed out 3/8 validation beads (the
    sessions ran in git worktrees, not the clone root the record names), and the
    recovered roots all sit ON the majority-prefix chain; this selects the chain
    element the validation picked, with ``record_work_dir`` as the structural anchor:

    1. No chain (no absolute mutation paths / no shared prefix beyond ``/``):
       ``record_work_dir`` -- inference has nothing to say.
    2. Record COVERS a strict majority of the paths (it lies on the chain, i.e. it is
       consistent with the trace): keep ``record_work_dir``; any deeper chain element
       is subtree concentration, not a different root (mem-us6j: a perfect 1.00
       replay that a blind deepest-prefix rebase would destroy). One exception -- the
       chain continuing through ``<record>/.claude/worktrees/<name>`` is Claude
       Code's NESTED-worktree root (usu9f shape, recovered 0.00 -> 0.69): use it.
    3. Record covers NO majority (the validated 0.00 failure mode): the session ran
       somewhere else entirely. Use the chain element at the record's own depth --
       the SIBLING-worktree shape (``<clone>-wt-<id>`` lives at the clone's
       filesystem level; recovered 2nbe9/52kv3 from 0.00 to 0.63-0.76) -- else the
       deepest majority prefix.

    Inference wins over the record exactly when the record is inconsistent with the
    trace's own paths; a wrongly-deep choice is still caught downstream by the
    admission threshold (see `infer_work_dir`)."""
    chain = _majority_prefix_chain(_distinct_absolute_paths(calls))
    if not chain:
        return record_work_dir
    record = PurePosixPath(posixpath.normpath(record_work_dir))
    if record in chain:
        nested_len = len(record.parts) + len(_NESTED_WORKTREE_SEGMENTS) + 1
        for element in chain:
            inside = element.is_relative_to(record) and len(element.parts) == nested_len
            if inside and element.relative_to(record).parts[:-1] == _NESTED_WORKTREE_SEGMENTS:
                return str(element)
        return record_work_dir
    for element in chain:
        if len(element.parts) == len(record.parts):
            return str(element)
    return str(chain[-1])


def _rebase_path(path: str, work_dir: str, checkout_dir: Path) -> Path | None:
    """Map an original-session absolute path onto the checkout, or None when it does
    not normalize to inside ``work_dir`` (relative paths and ``..`` escapes included --
    a replay must never write outside the checkout)."""
    norm = PurePosixPath(posixpath.normpath(path))
    work = PurePosixPath(posixpath.normpath(work_dir))
    if not norm.is_absolute() or not norm.is_relative_to(work):
        return None
    return checkout_dir / norm.relative_to(work)


def _apply_edits(text: str, edits: tuple[EditOp, ...]) -> tuple[str, ReplayOutcome, str]:
    """Apply a sequential edit list to ``text`` (Claude Code Edit/MultiEdit semantics).

    Returns the resulting text only on full success -- the caller writes all-or-nothing,
    so a mid-sequence failure leaves the file untouched (MultiEdit atomicity)."""
    for i, op in enumerate(edits):
        occurrences = text.count(op.old_string)
        if occurrences == 0:
            return text, ReplayOutcome.OLD_STRING_MISSING, f"edit {i}: old_string not found"
        if occurrences > 1 and not op.replace_all:
            return (
                text,
                ReplayOutcome.OLD_STRING_AMBIGUOUS,
                f"edit {i}: old_string matches {occurrences} times without replace_all",
            )
        count = -1 if op.replace_all else 1
        text = text.replace(op.old_string, op.new_string, count)
    return text, ReplayOutcome.APPLIED, ""


def replay_call(call: MutationCall, index: int, *, checkout_dir: Path, work_dir: str) -> CallReplay:
    """Replay one mutation call against the checkout and classify the outcome."""
    rebased = _rebase_path(call.path, work_dir, checkout_dir)
    if rebased is None:
        return CallReplay(
            index=index,
            tool=call.tool,
            path=call.path,
            rebased_path=None,
            outcome=ReplayOutcome.OUTSIDE_WORK_DIR,
            detail=f"path does not normalize to inside work_dir {work_dir!r}",
        )
    if call.tool == "Write":
        if call.content is None:  # _payload_matches_tool forbids this; keep the failure loud
            raise ValueError(f"Write call {index} for {call.path!r} carries no content")
        rebased.parent.mkdir(parents=True, exist_ok=True)
        rebased.write_text(call.content, encoding="utf-8")
        outcome, detail = ReplayOutcome.APPLIED, ""
    elif not rebased.is_file():
        outcome, detail = ReplayOutcome.FILE_ABSENT, "file absent in checkout"
    else:
        new_text, outcome, detail = _apply_edits(rebased.read_text(encoding="utf-8"), call.edits)
        if outcome is ReplayOutcome.APPLIED:
            rebased.write_text(new_text, encoding="utf-8")
    return CallReplay(
        index=index,
        tool=call.tool,
        path=call.path,
        rebased_path=str(rebased),
        outcome=outcome,
        detail=detail,
    )


def _run_git(args: list[str], checkout_dir: Path, runner: Runner) -> str:
    completed = runner(
        ["git", "-C", str(checkout_dir), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"git {args[0]} in {checkout_dir} failed (exit {completed.returncode}): "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout


def gold_diff(checkout_dir: Path, *, runner: Runner = subprocess.run) -> dict[str, str]:
    """The per-file gold diff of the replayed checkout vs its base commit.

    ``git add -N`` (intent-to-add) first, so files the replay CREATED appear in
    ``git diff`` alongside modifications. File names come from ``--name-only -z``
    (NUL-delimited -- robust to spaces), then one ``git diff -- <path>`` per file keeps
    the per-file split unambiguous instead of parsing combined-diff headers."""
    _run_git(["add", "-N", "."], checkout_dir, runner)
    names = _run_git(["diff", "--no-color", "--name-only", "-z"], checkout_dir, runner)
    return {
        name: _run_git(["diff", "--no-color", "--", name], checkout_dir, runner)
        for name in names.split("\0")
        if name
    }


def replay_calls(
    calls: Sequence[MutationCall],
    *,
    checkout_dir: Path,
    work_dir: str,
    runner: Runner = subprocess.run,
) -> ReplayResult:
    """Replay PRE-PARSED mutation calls in transcript order, then diff -- the P0 core.

    Split out of `replay_transcript` for callers that already hold the parsed calls
    (the batch assembler parses once to feed `effective_work_dir`, then replays the
    same calls) -- a multi-MB transcript must not be parsed twice."""
    replays = tuple(
        replay_call(call, index, checkout_dir=checkout_dir, work_dir=work_dir)
        for index, call in enumerate(calls)
    )
    applied = sum(1 for r in replays if r.outcome is ReplayOutcome.APPLIED)
    return ReplayResult(
        calls=replays,
        file_diffs=tuple(sorted(gold_diff(checkout_dir, runner=runner).items())),
        replay_success_rate=applied / len(replays) if replays else 0.0,
    )


def replay_transcript(
    stream: str,
    *,
    checkout_dir: Path,
    work_dir: str,
    runner: Runner = subprocess.run,
) -> ReplayResult:
    """Parse, replay in order, then diff: the P0 entry point.

    ``stream`` is the resolved transcript text (.jsonl); ``checkout_dir`` is the repo
    already checked out at ``base_commit``; ``work_dir`` is the original record's
    working directory (the rebase prefix)."""
    return replay_calls(
        parse_mutation_calls(stream),
        checkout_dir=checkout_dir,
        work_dir=work_dir,
        runner=runner,
    )
