"""The resumable per-task result cache, shared by every paid toolreq grid.

THE CACHE INVARIANT — stated once here, for every consumer, not re-argued at each check. A resumed
paid run may reuse a persisted cell only when that cell's identity is a total function of what was
measured: the invocations sent, the inputs the scorer grades against, and the run knobs. Every cache
defect this codebase has shipped had ONE shape — the identity hashed a MODEL of the executed input,
the model was one field short, and the task then reported ``reused``, spent nothing, did NOT crash,
and printed a stale or fabricated number as a real measurement. A green suite is not evidence
against that; each such shape is an executable case in ``tests/test_resume_cache.py``.

So the identity does not model the executed input, it CARRIES it: ``invocation_fingerprint`` hashes
the exact ``claude -p`` command lines the task's cells spawn, and ``run_cached_corpus`` refuses to
publish a measurement whose RECORDED invocations do not hash to it. The two halves are what make it
structural rather than a convention — hash the artifact, and check the artifact against the hash.

And the fingerprint is not a value a grid supplies at all: ``CachePlan.lookup`` computes it ITSELF
from the grid's ``plan_of`` (``invocation_digest``) and refuses any ``identity_of`` that returns a
different one — before the cache is consulted, so a fully cache-served resume, which never reaches
the write boundary, is checked too. A grid can no longer author the field by a route of its own.

The same invariant one level out, because a COST is authorized the way a measurement is read. Two
callers need the hit/miss decision: ``run_cached_corpus``, which answers "what will this run
measure" by measuring it, and ``pending_tasks``, which answers it for a driver's refuse-to-spend
disclosure BEFORE anything runs (mem-u9nu2). They read one ``CachePlan``, through one
``CachePlan.lookup``. A probe that modelled the decision instead — the crudest being "does
``<work_id>.json`` exist" — is this module's defect family displaced from the measurement to the
price: a FREE dry-run's file exists and cannot satisfy a PAID identity, so the probe reports cached,
the fire spends anyway, and the human authorized a fraction of what moved. That direction is the one
a probe ADDS, since the sweep's own over-report was fail-safe; it is why the decision is shared
rather than re-derived, and why ``CachePlan`` is a value rather than a convention.

Every defense below is STRUCTURAL — a property of the schema, not of the caller — and each is
stated at its own definition. A consumer subclasses ``BaseRunIdentity`` / ``BaseCellOutcome`` /
``BaseCachedResult`` to add its own measured inputs and cell fields, and supplies ``expected_cells``
+ ``classify``. All of it then stays in force by construction: a grid that does not cover its cells
exactly, or whose stored verdict is not the one its own rows imply, cannot be constructed, let
alone loaded.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Protocol, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from membench.bbon.models import deterministic_id
from membench.runner.headless_agent import (
    CellCalls,
    CellRecorder,
    resolve_model,
    stream_cli_version,
)


def digest(payload: object) -> str:
    """The one hash used by every fingerprint in every grid — same encoding, same width.

    Canonical (``deterministic_id`` -> RFC8785-style: object keys SORTED, list order KEPT). Sorting
    keys is what makes a field REORDER — which moves nothing executed and nothing scored — a cache
    hit rather than a full re-spend, and it is safe only because every input whose ORDER IS a
    measured input (surfaced memory, a retrieval payload, a cell's legs) is passed as a LIST."""
    return deterministic_id(payload)[:16]


def invocation_digest(cells: Iterable[CellCalls]) -> str:
    """The value ``BaseRunIdentity.invocation_fingerprint`` carries: every ``claude -p`` a task's
    cells will spawn — argv and all, prompt included.

    Its two halves pull in OPPOSITE directions and both are load-bearing.

    The CELLS sort. Each is an independent run in its own sandbox carrying its own ``(arm,
    channel)`` label, so the order a grid's loop happens to visit them in moves nothing executed and
    nothing scored — sorting keeps a reordered loop a cache HIT rather than a full paid re-spend.

    A cell's CALLS do not. Its legs share a cwd and a config dir and run in SEQUENCE, so their order
    IS a measured input: swap the builtin arm's establish and goal legs and it establishes the fact
    into a directory it then wipes, measuring a guaranteed 0/N. A digest that read that as the same
    run as the un-swapped one would serve the pre-swap numbers as post-swap measurements — this
    module's whole defect family, so the list stays a list. (Same two halves, same reasons, as
    ``digest``'s canonical-JSON contract.)

    Two records for one cell is refused, never merged: a cell runs ONE cycle, so they cannot both
    describe what it did, and merging would let a fabricated record overwrite the measured one."""
    by_cell: dict[tuple[str, str], list[list[str]]] = {}
    for cell in cells:
        key = (cell.arm, cell.channel)
        if key in by_cell:
            raise ValueError(f"two invocation records for cell {key} — a cell runs ONE cycle")
        by_cell[key] = [list(argv) for argv in cell.calls]
    return digest([[arm, channel, by_cell[(arm, channel)]] for arm, channel in sorted(by_cell)])


class CacheableTask(Protocol):
    """What the cache needs of a task: an id that keys both its identity and its result file.

    Structural, so this module never imports a task type and no consumer must inherit anything to
    be cacheable."""

    @property
    def work_id(self) -> str: ...


TaskT = TypeVar("TaskT", bound=CacheableTask)


class Cell(Protocol):
    """The four fields every grid's verdict rule reads.

    Structural, so one rule applies both to a persisted row (``BaseCellOutcome``) and to a raw
    in-memory measurement (``ArmOutcome``) — including a DEGENERATE one the schema refuses to
    persist (``runs=0``), which is how the rules that refuse it stay testable at all."""

    @property
    def arm(self) -> str: ...

    @property
    def channel(self) -> str: ...

    @property
    def passes(self) -> int: ...

    @property
    def runs(self) -> int: ...


def render_verdict(classified: Sequence[tuple[str, str, str]]) -> str:
    """The one renderer, so every grid's verdict string is built from its kind ladder rather than
    authored beside it."""
    return " | ".join(f"[{channel}] {line}" for channel, _kind, line in classified)


# The verdict kinds shared by every grid that reports through ``corpus_summary``: SEPARATES and LEAK
# are the two the summary COUNTS across all of them, WEAK the shared "partial, add repeats" rung.
# Declared HERE — beside the renderer that lays a ladder out and the summary keyed on them — rather
# than re-declared per grid: two copies of ``"SEPARATES"`` is exactly the drift a resume cache
# exists to refuse, and it would sit one import from the key that counts it. Each grid EXTENDS this
# with the kind only it has (``toolreq_grid``: KILL; the builtin grid: NOT-ENGAGED).
LEAK = "LEAK"
SEPARATES = "SEPARATES"
WEAK = "WEAK"


class BaseRunIdentity(BaseModel):
    """What a persisted cell was measured under: the run's knobs, and every measured input a grid
    has in common. A consumer subclasses this to add the inputs only it has.

    ``repeats`` is bounded at 1: ``--repeats 0`` evaluates nothing and persists 0/0 rows that a
    verdict rule reads as a confident "no separation" for a task that was never run. The drivers
    reject it at the flag too; this is the structural backstop, and both are deliberate.

    ``protocol`` covers what the fingerprints structurally CANNOT: the executing and scoring CODE. A
    change to the stream-json parser, the scorer, the engagement check or the sandbox firewall moves
    a result without touching any task field, so every fingerprint stays identical across it and a
    resumed sweep would serve pre-change answers as if they measured the new protocol. Each grid
    owns its own constant and BUMPS it on such a change. It is a MANUAL gate and that is its
    weakness: the alternative (hashing those modules' source) would invalidate the whole paid grid
    on any comment edit and re-spend real money. It still does not reach the ``claude`` binary's
    PATH or account config — those remain uncovered, and honestly so.

    ``model`` is the model a paid cell RAN UNDER, and is defended twice: it must be a fixed point of
    ``resolve_model`` (``_model_is_the_one_the_agent_will_actually_run_under``, so a repointed
    ``MEMBENCH_AGENT_MODEL`` is a miss not a relabel) AND, on the paid path, it must NAME a model
    (``_a_paid_run_names_the_model_it_executed_under``, so ``""`` — a deferral to the CLI's own
    default nothing here records — cannot be persisted as a measurement). A dry run may leave it
    empty. Like ``cli_version`` it is asserted here, not observed off the run's stream; mem-bzv2p.

    ``cli_version`` is the binary a paid cell was measured ON, resolved off the instrument itself
    (``headless_agent.resolve_cli_version``) rather than left to ``protocol``'s manual bump. The
    two gaps are not the same kind: a scorer change is made BY the person who would bump the
    constant, but the CLI drifts under an ``npm -g`` upgrade nobody connects to a benchmark — so
    upgrade the CLI between a staging run and a paid resume over the same ``--out``, and every task
    would be served as ``reused``, publishing old-binary numbers as measurements of the new
    instrument, at ``executed=0``, with no error. A manual gate cannot close a drift nobody
    performs on purpose. Bounded to the runs it can describe: a dry run spawns no binary (its whole
    measurement is the simulated runner, which ``protocol`` covers) and so names none, and a paid
    run must name one or it cannot say what it measured.

    It covers drift BETWEEN runs, not WITHIN one: the version is resolved once per sweep, so a CLI
    upgraded mid-sweep still tags later cells with the pre-sweep version. That is the narrower and
    louder residue — it mislabels a REAL measurement rather than silently serving a stale one as a
    cache hit — and closing it means checking each run's own stream instead of a pre-flight claim
    (``harbor.probe_gate.assert_run_pins``; mem-z32zu).

    ``invocation_fingerprint`` hashes the COMMAND LINES THEMSELVES — every ``claude -p`` argv every
    cell will spawn, prompt included — rather than a model of what goes into them, and so it cannot
    be incomplete *about the invocation*, because it IS the invocation. It is not authored here
    either: ``CachePlan.lookup`` derives it from the grid's ``plan_of`` and refuses any identity
    that carries a different value, before the cache is consulted. Its other half is the write
    boundary: ``run_cached_corpus`` refuses to publish a measurement whose RECORDED invocations do
    not hash to it (``invocation_digest``), so the two cannot be things that merely agree today —
    and between the two checks, one fires on a cache HIT and the other on a MISS, so neither path is
    served under a fingerprint that is not the plan's. Hashing the whole argv rather than just the
    prompt is what keeps ``--allowedTools``, ``--model`` and ``--strict-mcp-config`` out of
    ``protocol``'s manual surface: unclamping ``--allowedTools`` frees the scored goal leg while
    moving no task field, no payload and no prompt.

    It does NOT subsume ``task_fingerprint`` and is carried ALONGSIDE it, never in place of it: the
    scorer grades fields no command line mentions.

    ``settings_fingerprint`` hashes the ``settings.json`` a grid seeds into every cell's fresh
    ``CLAUDE_CONFIG_DIR`` (``headless_agent.seed_config_dir``) — the config surface the real
    ``claude -p`` reads its ``~/.claude`` from. It is the counterpart of ``invocation_fingerprint``
    for a measured input the argv CANNOT carry: the settings reach the agent through a FILE, not the
    command line, so ``autoMemoryEnabled`` (and, generalizing, any seeded config) moves a result
    while every other fingerprint stays identical — same prompts, same task, same (or absent)
    payload. Without it a resumed sweep serves numbers measured under one config surface as
    measurements of another; the builtin grid shipped this field first as ``mechanism_fingerprint``
    and it is generalized here so every grid that seeds a config dir declares what it seeded by
    construction. Each grid supplies the digest of the dict IT seeds; a grid that seeds nothing has
    no honest value to carry and this field would not apply to it (every current grid seeds one)."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    repeats: int = Field(ge=1)
    dry_run: bool
    model: str
    cli_version: str
    protocol: int
    task_fingerprint: str
    invocation_fingerprint: str
    settings_fingerprint: str

    @model_validator(mode="after")
    def _a_paid_measurement_names_the_binary_it_was_made_on(self) -> Self:
        """``cli_version`` is bounded to exactly the runs it can describe — structural, so a grid
        that forgets to resolve it gets a ValidationError rather than an identity spanning two
        binaries (see ``cli_version`` above)."""
        if self.dry_run and self.cli_version:
            raise ValueError(
                f"a dry run spawns no claude binary, so it cannot have been measured on "
                f"{self.cli_version!r} — dry-run identities must leave cli_version empty"
            )
        if not self.dry_run and not self.cli_version:
            raise ValueError(
                "a paid identity must name the claude binary it was measured on "
                "(headless_agent.resolve_cli_version), or a CLI upgrade between a staging run and "
                "a paid resume serves the old binary's numbers as the new instrument's"
            )
        return self

    @model_validator(mode="after")
    def _model_is_the_one_the_agent_will_actually_run_under(self) -> Self:
        """``model`` must be a FIXED POINT of ``resolve_model`` — the rule made structural rather
        than left to caller discipline (see this module's docstring)."""
        resolved = resolve_model(self.model)
        if self.model != resolved:
            raise ValueError(
                f"model {self.model!r} is not the one the agent would run under ({resolved!r}): a "
                "cache identity must store the RESOLVED model (headless_agent.resolve_model), or a "
                "repointed MEMBENCH_AGENT_MODEL serves one model's numbers as another's"
            )
        return self

    @model_validator(mode="after")
    def _a_paid_run_names_the_model_it_executed_under(self) -> Self:
        """The paid side of ``model``, bounded like ``cli_version`` — structural, so a driver that
        fires the sweep unpinned gets a ValidationError rather than an identity that names no model.

        The fixed-point check above keeps ``model`` honest ABOUT ``resolve_model``, but ``""`` is a
        fixed point of that rule (an unpinned run, no ``MEMBENCH_AGENT_MODEL``) and ``""`` is not a
        model: it defers to the CLI's OWN default, a rule the CLI evaluates against inputs this
        codebase never sees (``ANTHROPIC_MODEL``, ``settings.json``, the
        ``ANTHROPIC_DEFAULT_*_MODEL`` aliases). So two paid sweeps on genuinely different models
        both store ``""``, match on every field, and the resume serves one model's numbers as the
        other's at ``executed=0`` with nothing raised — this module's whole defect family, at the
        input the identity most loudly claims to cover. A paid identity must therefore NAME a model;
        a dry run spawns none to
        misname and may leave it empty (its plan for the CLI default is a legitimate free
        fingerprint — the asymmetry with ``cli_version``, which a dry run is REFUSED, is that a
        version stamped on a process that never started is a false claim while an empty model is
        merely a deferral).

        Only a backstop: the ``model`` that reaches the identity is ASSERTED, not OBSERVED off the
        run's own stream the way ``harbor.probe_gate.assert_run_pins`` reads a fresh run's init
        event. The drivers refuse the unpinned spend first; this refuses to PERSIST it (mem-bzv2p).
        """
        if not self.dry_run and not self.model:
            raise ValueError(
                "a paid identity cannot name the model it ran under: an unpinned paid run defers "
                "to the CLI's own default (ANTHROPIC_MODEL, settings.json, alias remaps), which "
                "this codebase never records, so its identity matches every later resume on any "
                "model — pin --model, or set MEMBENCH_AGENT_MODEL, so the executed model is named"
            )
        return self


class BaseCellOutcome(BaseModel):
    """One persisted ``(arm, channel)`` row — the schema the in-memory measurement dataclasses
    cannot enforce.

    ``ArmOutcome`` and friends are plain frozen dataclasses that type-check nothing, so a
    hand-edited ``{"passes": "0"}`` constructs happily and only detonates LATER inside a verdict
    rule
    (``passes > 0`` -> TypeError), an unhandled exception escaping mid-resume and killing a paid
    sweep. Strict mode rejects the string, the float, and the bool (an ``int`` subclass that would
    otherwise sail straight through an ``isinstance`` check) structurally, at the parse boundary,
    where a bad row is still just a cache miss.

    ``runs`` is bounded at 1 for the reason ``BaseRunIdentity.repeats`` is; ``passes`` is bounded
    above by ``runs`` because a row claiming more passes than runs is a fabricated ceiling."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    arm: str
    channel: str
    passes: int = Field(ge=0)
    runs: int = Field(ge=1)

    @model_validator(mode="after")
    def _passes_cannot_exceed_runs(self) -> Self:
        if self.passes > self.runs:
            raise ValueError(f"{self.arm}/{self.channel}: passes {self.passes} > runs {self.runs}")
        return self


IdentityT = TypeVar("IdentityT", bound=BaseRunIdentity)
CellT = TypeVar("CellT", bound=BaseCellOutcome)


class BaseCachedResult(BaseModel, Generic[IdentityT, CellT]):
    """One task's persisted result — the ONLY shape ``<work_id>.json`` may take, on write and on
    read alike, so a writer cannot emit a record its reader would have to reject.

    The identity is NESTED, not spread across the top level: nesting is what makes acceptance a
    whole-object ``==`` against this run's identity instead of a field-by-field walk that can only
    check the fields the reader thought to enumerate.

    The two cross-row invariants below are schema, not caller discipline. A subclass adds its own by
    declaring another ``model_validator``; it does not re-implement these."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    work_id: str
    identity: IdentityT
    outcomes: list[CellT]
    verdict: str

    @classmethod
    def expected_cells(cls) -> set[tuple[str, str]]:
        """The full ``(arm, channel)`` grid one task must cover to be scored as complete."""
        raise NotImplementedError

    @classmethod
    def classify(cls, outcomes: Sequence[CellT]) -> list[tuple[str, str, str]]:
        """This grid's verdict rule as ONE ladder: ``(channel, kind, line)``, one entry per channel.

        The kind a summary COUNTS and the line a human READS come out of the same branch, so they
        cannot desync. Deriving the counts the other way — substring-matching the rendered line, as
        ``"LEAK" in verdict`` — is what this shape refuses: reword a line and the headline silently
        changes, with no schema change and nothing failing."""
        raise NotImplementedError

    @classmethod
    def implied_verdict(cls, outcomes: Sequence[CellT]) -> str:
        """The verdict these rows produce — rendered from ``classify``, never authored beside it.
        The stored one may only ever be this one."""
        return render_verdict(cls.classify(outcomes))

    @property
    def kinds(self) -> list[str]:
        """This record's per-channel verdict kinds — what a summary counts, taken from the same
        ladder that produced its ``verdict`` string."""
        return [kind for _channel, kind, _line in type(self).classify(self.outcomes)]

    @model_validator(mode="after")
    def _rows_are_a_complete_grid_measured_at_this_identity(self) -> Self:
        for cell in self.outcomes:
            if cell.runs != self.identity.repeats:
                raise ValueError(
                    f"{cell.arm}/{cell.channel}: measured at {cell.runs} run(s), identity says "
                    f"{self.identity.repeats}"
                )
        # The cells must cover the grid EXACTLY — one row per (arm, channel), no dupes, no strays.
        # BOTH halves are load-bearing and each alone has already shipped a bug: N copies of one
        # cell has the right ARITY but wrong coverage (a channel no `claude -p` call ever ran,
        # credited as full coverage); the correct rows PLUS a duplicate cover the grid as a SET but
        # a verdict rule keys by (arm, channel), so the last duplicate overwrites the real
        # measurement — a genuine SEPARATES rewritten into a fabricated KILL.
        cells = [(cell.arm, cell.channel) for cell in self.outcomes]
        expected = type(self).expected_cells()
        if len(cells) != len(expected) or set(cells) != expected:
            raise ValueError(f"cells {sorted(cells)} are not the grid {sorted(expected)}")
        return self

    @model_validator(mode="after")
    def _verdict_is_the_one_its_own_rows_imply(self) -> Self:
        """The verdict is DERIVED, so a persisted one may only be the one its rows produce.

        Without this the field is the single unchecked value in the record: a hand-edited
        ``"verdict": "SEPARATES: ..."`` over KILL rows passes every other check (identity intact,
        rows intact) and the summary a human reads is built from ``verdict`` strings. It was
        harmless only by accident, because a caller happened to recompute the verdict from the
        loaded rows and overwrite it. That is a redundancy standing in for a missing invariant,
        which is the shape this module exists to refuse: a value outside the checks is not defended
        by the checks around it."""
        implied = type(self).implied_verdict(self.outcomes)
        if self.verdict != implied:
            raise ValueError(f"verdict {self.verdict!r} is not the one its rows imply: {implied!r}")
        return self

    @classmethod
    def of(cls, work_id: str, identity: IdentityT, outcomes: Sequence[CellT]) -> Self:
        """Build the record a run publishes, verdict included — through the same validators a loaded
        file passes, so an invalid record cannot reach disk in the first place."""
        return cls(
            work_id=work_id,
            identity=identity,
            outcomes=list(outcomes),
            verdict=cls.implied_verdict(outcomes),
        )


ResultT = TypeVar("ResultT", bound=BaseCachedResult[Any, Any])


def load_cached(
    result_path: Path, identity: BaseRunIdentity, result_cls: type[ResultT]
) -> ResultT | None:
    """The persisted RECORD of a task whose identity matches this run, or ``None`` meaning MISS.

    Returned whole, and reused as-is: every field it carries — rows, flags, and verdict alike — is
    checked by the schema, so there is nothing left for a caller to recompute and no reason to
    rewrite the file it came from.

    Every rejection is a miss, never a crash and never a partial acceptance. These files are written
    by a sweep that can be killed mid-run and re-read by a PAID resume, so the two failure modes to
    design against are an exception escaping and killing the whole sweep on one bad file, and a
    degenerate or FOREIGN file being scored as a complete task."""
    try:
        raw = json.loads(result_path.read_text(encoding="utf-8"))
    except (ValueError, OSError, RecursionError):
        # A PARSE BOUNDARY over an untrusted file: catch by blast radius, not by enumerating what
        # json.loads is known to raise. ValueError covers JSONDecodeError, UnicodeDecodeError and
        # the >4300-digit int-literal limit; RecursionError covers deeply nested JSON; OSError
        # covers unreadable/directory/permission.
        return None
    try:
        loaded = result_cls.model_validate(raw)
    except ValidationError:
        return None  # wrong shape, drifted type, degenerate row, or an incomplete/forged grid
    if loaded.identity != identity:
        return None  # another run's measurement (dry-run vs paid, model, repeats, world...)
    return loaded


def assert_usable_work_ids(tasks: Sequence[CacheableTask], summary_name: str) -> None:
    """A work_id must be unique and a safe, unclaimed filename — it keys both the identity map and
    the ``<work_id>.json`` result path.

    A DUPLICATE silently aliases two different tasks onto one cache file: the second overwrites the
    first and, on resume, that single record is served for both. An UNSAFE id is corpus data used to
    build a filesystem path before being checked as one — it either claims the summary's name (the
    driver writes the summary into the same directory AFTERWARDS, overwriting that task's result,
    which then misses forever) or carries a separator/traversal that writes outside ``--out``.
    Corpus ids are sequence-derived and a regenerated or hand-assembled corpus can produce either,
    so refuse rather than measure."""
    duplicates = sorted(id_ for id_, n in Counter(t.work_id for t in tasks).items() if n > 1)
    if duplicates:
        raise ValueError(
            f"duplicate work_id(s) in the corpus: {duplicates} — each task must map to exactly "
            "one <work_id>.json, or a resumed run serves one task's measurement for another"
        )
    unsafe = sorted(
        t.work_id
        for t in tasks
        if f"{t.work_id}.json" == summary_name or Path(t.work_id).name != t.work_id or not t.work_id
    )
    if unsafe:
        raise ValueError(
            f"unsafe work_id(s) for a result filename: {unsafe} — a work_id must be a plain "
            f"filename component and must not claim the summary's name ({summary_name})"
        )


@dataclass(frozen=True)
class CacheLookup(Generic[IdentityT, CellT]):
    """What consulting the cache for ONE task answered: where its result lives, the identity this
    run would measure it under, and the persisted record if one may be REUSED (else ``None`` — a
    MISS, meaning this task will be measured and will spend).

    Returned whole rather than as a bare bool because ``run_cached_corpus`` needs the ``identity``
    again to publish under (``result_cls.of``) and the ``result_path`` to publish to, while
    ``pending_tasks`` needs only ``cached``. One decision, two readers, no second derivation."""

    result_path: Path
    identity: IdentityT
    cached: BaseCachedResult[IdentityT, CellT] | None


# `eq=False`: `plan_of` / `identity_of` are functions, so the structural `__eq__` `frozen=True`
# would synthesize compares two identical plans UNEQUAL — a check that fails open on the exact
# question this class exists to settle. No meaningful structural equality exists here, so none is
# offered.
@dataclass(frozen=True, eq=False)
class CachePlan(Generic[TaskT, IdentityT, CellT]):
    """Everything that decides WHETHER a persisted result may be reused — the miss decision's
    inputs, as one value: a thing PASSED WHOLE, not a thing compared (see `eq=False` above).

    Passed whole rather than as loose keyword arguments so the probe and the run cannot be asked
    about DIFFERENT runs — the module docstring argues why.

    ``resume`` is a field for the same reason and not a convenience default: it is the knob a driver
    is most likely to model rather than share (``--no-resume`` re-measures everything, so a probe
    that assumed ``True`` would disclose a cached-and-cheap resume for a fire that re-spends the
    whole corpus — the UNDER-report direction). Neither driver exposes the flag today, which makes
    the drift unobservable rather than absent, and unobservable-but-absent is the condition under
    which every defect this module documents shipped.

    ``IdentityT`` is a parameter of this class and not a convenience: it BINDS ``identity_of`` to
    ``result_cls``, so a grid cannot pair one grid's identity with another's result type. Typed as
    the base ``BaseRunIdentity``, that pairing was a matter of each ``cache_plan`` factory being
    careful by hand, and a crossed pair type-checked clean and failed as a pydantic
    ``ValidationError`` raised INSIDE the write boundary below — i.e. after ``evaluate`` had already
    made that task's real ``claude -p`` calls. Paid, then crashed, then published nothing: the
    expensive end of this module's failure modes, reachable by a copy-paste between two sibling
    grids. Now it is an ``arg-type`` error at the ``CachePlan(...)`` call."""

    out_dir: Path
    result_cls: type[BaseCachedResult[IdentityT, CellT]]
    plan_of: Callable[[TaskT], Sequence[CellCalls]]
    identity_of: Callable[[TaskT, str], IdentityT]
    summary_name: str
    resume: bool = True

    def lookup(self, task: TaskT) -> CacheLookup[IdentityT, CellT]:
        """Consult the cache for ONE task: the hit/miss decision, in ONE place, for every reader.

        A method and not two copies, so the model that could drift never exists — the module
        docstring argues why.

        The fingerprint is derived HERE from ``plan_of`` and the identity is checked to carry
        exactly it — before the cache is consulted, so a probe and a fully cache-served resume are
        both checked, and a grid cannot author the field by a route its plan does not own."""
        result_path = self.out_dir / f"{task.work_id}.json"
        plan_fingerprint = invocation_digest(self.plan_of(task))
        identity = self.identity_of(task, plan_fingerprint)
        if identity.invocation_fingerprint != plan_fingerprint:
            raise ValueError(
                f"{task.work_id}: the identity carries invocation_fingerprint "
                f"{identity.invocation_fingerprint}, but this run's plan hashes to "
                f"{plan_fingerprint} — the fingerprint is computed by the CachePlan from "
                "plan_of and handed to identity_of, so an identity carrying any other value "
                "authored the field by a route the plan does not own. Pass through the fingerprint "
                "you were given; do not recompute it."
            )
        # No is_file() probe first: load_cached is TOTAL over its path — a missing file raises
        # OSError inside it and is a miss like every other rejection.
        cached = load_cached(result_path, identity, self.result_cls) if self.resume else None
        return CacheLookup(result_path=result_path, identity=identity, cached=cached)


def pending_tasks(plan: CachePlan[TaskT, IdentityT, CellT], tasks: Sequence[TaskT]) -> list[TaskT]:
    """The tasks ``run_cached_corpus`` WOULD measure under this same ``plan`` — the work that
    REMAINS, in corpus order. A pure READ: it publishes nothing, rewrites nothing, and spawns no
    agent.

    What it is for: a paid driver's refuse-to-spend disclosure fires INSTEAD of the sweep, so the
    whole corpus is the only cost it can name — and on a mostly-cached resume that describes work
    which will not be done (mem-u9nu2). Price this subset with the grid's own cost function instead.

    Deliberately NOT free of preconditions, and callers must not read it as advisory: the answer is
    only true for a fire that runs under the identity this ``plan`` names. ``model``,
    ``cli_version`` and each grid's own measured inputs are identity fields, so a fire under a
    repointed ``MEMBENCH_AGENT_MODEL``, an upgraded ``claude``, or a moved payload misses every cell
    this probe called cached — and spends the WHOLE corpus against a number that disclosed a
    fraction of it. That direction is the one this probe adds and the sweep never had, so a driver
    that prints the number must pin what it can into the command it prints, and name what it
    cannot.

    ``assert_usable_work_ids`` first, exactly as the run does: a duplicate work_id aliases two tasks
    onto one file, and the probe would answer for the wrong one. The run refuses such a corpus
    outright, so a disclosure that priced it would be pricing a fire that cannot start."""
    assert_usable_work_ids(tasks, plan.summary_name)
    return [task for task in tasks if plan.lookup(task).cached is None]


@dataclass(frozen=True)
class CorpusRun(Generic[ResultT]):
    """What one sweep over the corpus produced, and what it COST to produce it.

    ``executed`` / ``reused`` are the accounting a paid run is read through: they say how many tasks
    this invocation actually spent ``claude -p`` calls on. Each grid shapes its own headline summary
    from ``results``; the split between what was measured and what was replayed is common to all of
    them."""

    results: list[ResultT]
    executed: int
    reused: int


def run_cached_corpus(
    plan: CachePlan[TaskT, IdentityT, CellT],
    tasks: Sequence[TaskT],
    *,
    evaluate: Callable[[TaskT, CellRecorder], Sequence[CellT]],
    before_first_spend: Callable[[], None] | None = None,
) -> CorpusRun[BaseCachedResult[IdentityT, CellT]]:
    """Evaluate every task, persisting one ``<work_id>.json`` each, and reuse a persisted result
    only when its identity matches this run's — so a FREE dry-run's simulated result can never
    satisfy a PAID run over the same ``--out``, and a corrupt or partial file is a miss rather than
    a crash.

    ``plan`` carries the miss decision's inputs and ``evaluate`` is injected beside it: they are the
    only things that differ between the grids that share this cache, and injecting them is what
    keeps the arms, the invocations and the verdict rule of one experiment out of the other's.

    ``plan.plan_of`` returns the ``claude -p`` cycles a task's cells WILL spawn, and the PLAN — not
    the grid — hashes them into ``invocation_fingerprint`` (``CachePlan.lookup``) and hands the
    value to ``identity_of``. So ``invocation_fingerprint`` is no longer a field any grid can author
    by a route of its own: whatever ``identity_of`` returns must carry exactly the digest computed
    there (checked for EVERY task, before any spend), and the write boundary below then checks the
    RECORDED invocations against that SAME value. The grid supplies one plan; the fingerprint the
    identity is compared under and the fingerprint the arms are held to are one thing, owned by that
    seam rather than two call sites that happen to agree today.

    ``before_first_spend`` is a driver's paid warm-up — a preflight cycle, a mechanism check — and
    is injected for the same reason: it must fire once if this run will measure anything and NOT AT
    ALL if it will not, and only this loop knows which. A driver that MODELLED the miss set — an
    ``is_file`` probe, a hand-rolled identity — would drift from this loop the moment the two
    disagreed about a knob such as ``resume``, and a warm-up is a paid call: it must not fire for a
    corpus this loop will serve entirely from cache.

    A driver that must know the miss set WITHOUT running asks ``pending_tasks``, which reads this
    same ``plan``: the decision has one home, not one asker. The hook stays the right shape for its
    own case, which is not "what remains" but "fire once, if anything remains, at the moment it
    does".

    It fires immediately before the first task that reaches ``evaluate``, so
    ``assert_usable_work_ids`` and every cache hit speak FIRST and a fully-served corpus costs zero
    paid calls. Raising from it aborts the run before anything is measured — how a driver halts a
    sweep it has diagnosed as not worth spending on.

    ``plan_of`` (what the arms WILL send) and the run's RECORDING (what they DID) are still
    independent measurements — which is why the write boundary below exists. But ``evaluate``
    no longer HANDS BACK the recording: this loop creates the ``CellRecorder``, passes it in, and
    reads ``recorded()`` itself. So the value hashed at the write boundary is the argv the CLI seam
    SAW, never a ``calls`` an ``evaluate`` returned — the last route by which a caller could make
    the check tautological (return the plan's rendering, or spawn a leg through a bare runner the
    recorder never saw) is closed structurally, not by caller discipline (mem-9gvej). A plan left
    resting on its agreement with the executor is still one edit from a command line the
    arms no longer send: change what a leg surfaces, forget to move the plan, and the recording no
    longer matches, so a resumed PAID run refuses rather than publishing pre-change numbers as
    post-change measurements. A refused measurement is expensive — the ``claude -p`` calls are
    already made and are NOT written — and that is the cheap end of this failure.

    What this seam closed on the PLAN side is the third route: the fingerprint is derived from
    ``plan_of`` in ``CachePlan.lookup``, not authored inside ``identity_of``, so a grid can no
    longer carry a fingerprint computed by any route other than its plan — and that check fires on a
    cache HIT too, not only on the miss the write boundary sees."""
    # `mode=0o700` because this dir holds PAID results and the publish below treats it as a
    # trust boundary. A bare `mkdir` takes 0o777 & ~umask -- 0o755 under the usual umask, and
    # 0o775 (GROUP-WRITABLE) under the 0o002 that this rig's own sessions run with, which is
    # exactly the "someone else can plant a file at the predictable temp name" precondition.
    # `mode` is applied only on CREATE, and umask still subtracts from it, so this narrows the
    # common case rather than guaranteeing a mode: an out_dir the operator already created
    # keeps whatever it had. The publish is what actually refuses; this stops handing it the
    # problem for free.
    plan.out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    assert_usable_work_ids(tasks, plan.summary_name)

    results: list[BaseCachedResult[IdentityT, CellT]] = []
    executed = 0
    reused = 0
    warmed_up = False
    for task in tasks:
        found = plan.lookup(task)
        if found.cached is not None:
            # Reused whole. Nothing is recomputed and the file is NOT rewritten: it already passed
            # every validator, so a rewrite could only reproduce it — and a fully cache-served
            # resume then does zero writes, leaving the results' mtimes an honest record of which
            # tasks this run actually measured.
            results.append(found.cached)
            reused += 1
            continue
        if before_first_spend is not None and not warmed_up:
            # Not `executed == 0`: that is equivalent only while the write boundary below raises on
            # every miss after the first. Soften that raise to a skip and `executed == 0` silently
            # re-fires a PAID warm-up on the next miss.
            warmed_up = True
            before_first_spend()
        recorder = CellRecorder()
        outcomes = evaluate(task, recorder)
        sent = invocation_digest(recorder.recorded())
        if sent != found.identity.invocation_fingerprint:
            raise ValueError(
                f"{task.work_id}: the `claude -p` invocations this task actually made hash to "
                f"{sent}, but the identity it was measured under fingerprints "
                f"{found.identity.invocation_fingerprint} — the grid's plan is no longer what its "
                "arms execute. This measurement is NOT written: publishing it would file a real "
                "result under a fingerprint describing a command line it never sent, and every "
                "cell a later resume serves on that fingerprint would answer for a different run. "
                "Fix the plan (or the arm) so the two are one thing again, then re-measure."
            )
        # The ARTIFACT check, one input over from the fingerprint refusal above (mem-z32zu). That
        # one holds the argv the cells SENT to the plan; this holds the version the cells' own
        # streams REPORTED to the identity's pinned `cli_version`. `cli_version` is resolved ONCE at
        # the top of a sweep off a pre-flight `claude --version` (a claim about a DIFFERENT
        # process), so a CLI upgraded mid-sweep — an `npm -g`, an auto-update — tags every later
        # cell with the pre-sweep version, filing a real measurement under the wrong instrument's
        # name. Each cell's own `claude -p` stream carries a `type=system`/`subtype=init` event
        # announcing the version the binary that ran it actually was; checking it here refuses that
        # mislabel before it is published. Skipped for a dry run (`cli_version == ""` names no
        # binary — the identity validator refuses a dry run that claims one). A stream that carries
        # no init event names no instrument and is left unchecked: a drifted REAL run always prints
        # the new version's init event, so the threat is covered without importing dead-run
        # detection into the grids.
        if found.identity.cli_version:
            for stream in recorder.recorded_streams():
                ran_on = stream_cli_version(stream)
                if ran_on is not None and ran_on != found.identity.cli_version:
                    raise ValueError(
                        f"{task.work_id}: a `claude -p` cell ran on CLI version {ran_on} (its own "
                        f"init event), but the identity it was measured under pins "
                        f"{found.identity.cli_version} — the binary was upgraded mid-sweep. This "
                        "measurement is NOT written: publishing it would file a real result under "
                        "the pre-upgrade instrument's name, which a later resume would then match "
                        "and serve. Re-run the sweep on one CLI version."
                    )
        executed += 1
        result = plan.result_cls.of(task.work_id, found.identity, outcomes)
        # Atomic publish: write a sibling temp file then rename, so a kill mid-write leaves either
        # the old result or the new one, never a half-written JSON the next resume trips on.
        _publish_atomically(found.result_path, result.model_dump_json(indent=2) + "\n")
        results.append(result)
    return CorpusRun(results=results, executed=executed, reused=reused)


def _publish_atomically(result_path: Path, payload: str) -> None:
    """Write ``payload`` to ``<result_path>.tmp`` and rename it over ``result_path``.

    Not ``Path.write_text``: the temp path has a PREDICTABLE name, so anyone who can write
    to out_dir can plant something there ahead of the run and have the publish write
    through it -- after which the rename leaves the result itself pointing wherever they
    chose. The write is a trust boundary and this module refuses at boundaries.

    UNLINK THEN ``O_EXCL``, and the pair is the point. ``O_EXCL`` alone cannot be used: a
    leftover regular ``.json.tmp`` is designed-for residue (the agent is OOM-killed by
    design, so a kill can land between the write and the rename) and must still be
    replaced; ``O_EXCL`` would raise on it -- on a cache MISS, i.e. AFTER the re-spend --
    wedging the resume path permanently. The unlink is what makes ``O_EXCL`` affordable:
    it clears the residue first, so the create that follows is always a FRESH inode.

    Why not ``O_TRUNC|O_NOFOLLOW``, which also preserves the residue contract: it opens
    whatever object already sits at the name, and ``O_NOFOLLOW`` only refuses a SYMLINK.
    A hard link to a victim file is opened and truncated exactly like a regular file
    (reproduced: the victim's contents are replaced with benchmark JSON), and a planted
    FIFO blocks the publish forever on ``O_WRONLY`` -- after the paid calls are already
    made. Creating a new inode refuses all three shapes by construction rather than
    enumerating them. ``os.unlink`` removes the directory ENTRY, so it drops a planted
    symlink or hard link without touching whatever it pointed at.

    A ``FileExistsError`` here therefore means something raced the unlink, which no
    legitimate path does -- refusing is correct, and it is not the wedge ``O_EXCL`` alone
    would have been.

    KNOWN LIMIT, deliberately not closed here: ``replace`` renames by PATH, not by the fd
    just written, so an attacker who wins the sub-millisecond window between close and
    rename can still swap the temp entry and have the rename publish THEIR symlink as the
    result. The payload is never written through it (the fd is already an unlinked inode
    by then), and closing it needs a different publish shape than rename-by-name. Recorded
    rather than papered over.
    """
    tmp_path = result_path.with_suffix(".json.tmp")
    # The clear and the create are diagnosed SEPARATELY because they have different remedies.
    # Nothing there is the normal case (suppressed); a directory at the name or a read-only
    # out_dir fails the unlink itself, and calling that a race would send the operator hunting
    # an attacker for a stale directory.
    try:
        with contextlib.suppress(FileNotFoundError):
            tmp_path.unlink()
    except OSError as exc:
        raise OSError(
            f"refusing to publish {result_path.name} through {tmp_path}: {exc.strerror}. "
            "The temp path could not be cleared, so this publish never reached the create. "
            "Treated as an anomaly rather than written through."
        ) from exc
    try:
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        raise OSError(
            f"refusing to publish {result_path.name} through {tmp_path}: {exc.strerror}. "
            "The temp path was cleared immediately before this create, so anything already at "
            "it raced that unlink -- which no legitimate path does. Treated as an anomaly "
            "rather than written through."
        ) from exc
    # `os.fdopen` ADOPTS the fd -- on success the `with` owns it. But if the wrapper
    # construction itself raises, nothing owns the raw fd yet and it is orphaned. This runs
    # once per task inside a paid sweep, so a systematic trigger exhausts the table mid-sweep.
    try:
        handle = os.fdopen(fd, "w", encoding="utf-8")
    except BaseException:
        os.close(fd)
        raise
    with handle:
        handle.write(payload)
    tmp_path.replace(result_path)


def corpus_summary(
    tasks: Sequence[CacheableTask],
    run: CorpusRun[ResultT],
    *,
    dry_run: bool,
    repeats: int,
    n_channels: int,
) -> dict[str, Any]:
    """The summary keys EVERY grid emits: what the run covered, what it cost, the two verdict counts
    every grid shares, and the rows behind them all. Each grid spreads this and adds only its OWN
    headline (``toolreq_grid``: ``ours_empty_retrieval``; the builtin grid: ``not_engaged``), so the
    accounting a paid run is read through — the two shared counts included — has one owner rather
    than a copy per grid that can drift apart. That is why they live HERE and not inline in each
    ``run_corpus``: they were computed identically in both, one rename from meaning two things.

    ``separates_all_channels`` counts the tasks whose EVERY channel separated, against
    ``n_channels`` and never ``all(...)`` over the kinds a result happens to hold: ``all([])`` is
    vacuously True, so an empty or short grid would be credited "separates on every channel" off a
    measurement that covered none. ``leaked`` is the tasks any of whose channels leaked. Both read
    ``r.kinds`` — the per-channel kinds off the same ladder that produced each result's ``verdict``
    — so a headline is never recovered by substring-matching a rendered line."""
    # Memoized positionally, not by work_id: each result's kinds is read only for that same
    # result, so a work_id-keyed dict would buy nothing over a list while quietly depending on
    # work_id uniqueness (a value outside the checks is not defended by the checks) — and this
    # function is public, callable on a hand-built CorpusRun that never ran assert_usable_work_ids.
    kinds = [(r.work_id, r.kinds) for r in run.results]
    return {
        "n_tasks": len(tasks),
        "executed": run.executed,
        "reused": run.reused,
        "dry_run": dry_run,
        "repeats": repeats,
        "separates_all_channels": sum(1 for _w, k in kinds if k.count(SEPARATES) == n_channels),
        "leaked": [w for w, k in kinds if LEAK in k],
        "per_task": [r.model_dump(mode="json") for r in run.results],
    }
