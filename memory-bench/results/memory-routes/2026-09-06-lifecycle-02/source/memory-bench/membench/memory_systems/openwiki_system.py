"""``openwiki`` — LangChain OpenWiki as a competitive memory arm.

`langchain-ai/openwiki` is a CLI that ingests raw sources and LLM-synthesises them
into a Markdown wiki (``~/.openwiki/wiki/`` in personal mode, ``openwiki/`` in code
mode). It has no vector store, no top-k/score API, and no Python package — retrieval
is "the agent reads the synthesised wiki." That shape is a **consolidating-filesystem
arm**, NOT an ``AbstractSemanticArm``:

* ``write`` is an O(1) wake-append of a raw source — ZERO model calls on the hot path
  (the ``ConsolidatingMemory`` M6 honesty contract), exactly like the other two-speed
  arm.
* the offline ``consolidate()`` pass shells the OpenWiki CLI to synthesise wiki pages
  from the accumulated raw sources; the LLM cost is metered as ``background_tokens``
  at the harness boundary, never arm-self-reported.
* ``retrieve`` returns the synthesised page(s) (the confirmed retrieval mode — the
  arm surfaces synthesised docs and leaves all model *reasoning* to the
  agent-under-test; it does NOT shell ``openwiki -p`` to answer, which would fold
  answer-synthesis into the arm and muddy the comparison).

The synthesiser is injected behind the ``WikiSynthesizer`` Protocol, mirroring
``ConsolidatingMemory``'s ``ClusterSummarizer`` seam: CI runs a deterministic,
model-free fake (``ConcatWikiSynthesizer``) so the module imports and the whole
suite runs with no Node CLI, no Ollama, and no network. The real
``_CliWikiSynthesizer`` (below) shells ``openwiki`` against a local
OpenAI-compatible endpoint (Ollama), honouring the no-paid-API constraint
(Decision 16) — its model id comes from ``LocalModelStack``, never hardcoded.

Provisioning (downstream of green CI, like Qdrant/Chroma for the vector arms): a real
run needs ``npm i -g openwiki`` plus a running Ollama daemon exposed at its
OpenAI-compatible endpoint (``{OLLAMA}/v1``). The real code-mode wiring was verified
end-to-end against openwiki v0.1.0 + Ollama (mem-nul9j): git-snapshot the sources, run
``openwiki code --init --print`` with env-driven provider/model config, read the nested
``openwiki/`` pages back. The subprocess runner is injected so the shell shape stays
unit-testable without the CLI; the real end-to-end path has a provisioning-gated
integration test (skipped in CI).

Provenance: OpenWiki synthesises pages freely and does not emit per-page
source→page citations, so a page conservatively cites EVERY live source it was
synthesised from (over-declaring provenance keeps M7 citations dereferenceable and
cannot hide a leak — the harness re-audits every payload against the LOO boundary
regardless). Finer per-page provenance is a follow-up if OpenWiki ever surfaces
citations.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from membench.memory_systems.base import MemorySystem, RetrievalRequest, RetrieveResult
from membench.memory_systems.consolidation import ConsolidatedItem, ConsolidationResult
from membench.memory_systems.filesystem_system import _safe_name
from membench.memory_systems.local_stack import LocalModelStack
from membench.runtime import StepContext
from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation
from membench.spawn import run_checked

# Synthesised page ids are namespaced under this prefix so they can NEVER collide with
# a harness-issued raw ``memory_id`` (OpenWiki names wiki files after source paths, which
# can mirror a raw id — an unnamespaced page id would misroute a raw lookup to wiki
# content). Mirrors ``ConsolidatingMemory``'s ``f"{name}-schema-{i}"`` disjointness.
_PAGE_PREFIX = "openwiki-page-"

# OpenWiki provider selector for the local Ollama OpenAI-compatible endpoint.
_OPENWIKI_PROVIDER = "openai-compatible"

# Generous bound on the OpenWiki CLI shell-out (mirrors ``mem_cli.DEFAULT_TIMEOUT_S``):
# the CLI drives a local LLM, so a cold model load can be slow, but a hang past this is
# a wedged process, not a slow run — it must surface as a loud error, never block forever.
DEFAULT_CLI_TIMEOUT_S = 120.0

# The git snapshot is three local plumbing commands over a handful of freshly-written
# files; anything near this bound is a wedged git, not slow work.
_GIT_TIMEOUT_S = 30.0


class OpenWikiCliError(RuntimeError):
    """An ``openwiki`` CLI invocation failed (missing binary, timeout, non-zero exit).
    Carries the command + fix for context, mirroring ``mem_cli.MemCliError`` — a failed
    synthesis is surfaced, never silently degraded to an empty wiki."""


@dataclass(frozen=True)
class WikiPage:
    """One synthesised wiki page: its stable id, the Markdown content the agent reads,
    and the raw source ids it was synthesised from (the M7 provenance a retrieved page
    carries — never empty, or it is a sourceless fabrication)."""

    page_id: str
    content: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class WikiSynthesisResult:
    """What one ``synthesize`` pass returns: the pages built plus the offline LLM cost
    it incurred (``background_tokens`` = 0 for the deterministic CI fake, > 0 for a
    real OpenWiki run — metered at the harness boundary, never arm-self-reported)."""

    pages: tuple[WikiPage, ...]
    background_tokens: int = 0


@runtime_checkable
class WikiSynthesizer(Protocol):
    """The seam ``consolidate()`` synthesises the wiki through. A real synthesiser
    shells the OpenWiki CLI; the CI fake is deterministic and makes no call."""

    def synthesize(self, *, sources: Mapping[str, str]) -> WikiSynthesisResult: ...


class ConcatWikiSynthesizer:
    """Deterministic, model-free synthesiser for CI: merges every source into ONE wiki
    page whose content is the sources concatenated in first-seen order, citing all of
    them. Faithful by construction (every byte of the page comes from a real source, so
    the confabulation proxy scores it 0) and ``background_tokens`` is 0: no model ran.
    Stands in for OpenWiki's LLM synthesis wherever the real CLI is not provisioned."""

    PAGE_ID = "openwiki-page-0"

    def synthesize(self, *, sources: Mapping[str, str]) -> WikiSynthesisResult:
        if not sources:
            return WikiSynthesisResult(pages=(), background_tokens=0)
        ids = tuple(sources.keys())
        content = "\n\n".join(sources[mid] for mid in ids)
        page = WikiPage(page_id=self.PAGE_ID, content=content, source_ids=ids)
        return WikiSynthesisResult(pages=(page,), background_tokens=0)


# The shell seam: ``(argv, cwd, env) -> stdout``. ``env`` overlays the process env for
# that call (OpenWiki takes provider/model/base-url config from env, not flags).
# Injectable so the CLI-shell shape is unit-testable with no ``openwiki`` binary present.
WikiCliRunner = Callable[[list[str], Path, Mapping[str, str]], str]


def _default_cli_runner(argv: list[str], cwd: Path, env: Mapping[str, str]) -> str:
    """Run ``openwiki`` non-interactively and return stdout, with ``env`` overlaid on the
    process environment. Time-bounded and typed: every spawn failure — missing binary, an
    unspawnable one, a timeout, a non-zero exit — raises ``OpenWikiCliError`` with context
    via the shared ``spawn.run_checked`` ladder, so a hang or failure is surfaced, never a
    silent empty wiki."""
    return run_checked(
        argv,
        what=" ".join(argv),
        not_found_hint="install the OpenWiki CLI first (npm i -g openwiki)",
        timeout_s=DEFAULT_CLI_TIMEOUT_S,
        error=OpenWikiCliError,
        cwd=cwd,
        env={**os.environ, **env},
    ).stdout


def _git_snapshot(workdir: Path) -> None:
    """Initialise ``workdir`` as a git repo and commit its current files. OpenWiki's
    ``code`` mode reads git context to decide what to document — verified empirically
    (mem-nul9j): with no commit it writes nothing or a degenerate page, with a commit it
    synthesises structured pages. A pinned identity + no-gpg-sign keeps this hermetic and
    non-interactive; any git failure raises ``OpenWikiCliError`` (never a silent skip) —
    including the missing-git, unspawnable-git and timeout rungs this loop set a bound for
    but never caught until it moved onto the shared ladder (mem-o9plh). Each step keeps its
    own identity in the message: ``what`` is that step's own argv."""
    steps = [
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        # -c flags supply an identity so the commit needs no ambient git config.
        [
            "git",
            "-c",
            "user.email=openwiki-arm@local",
            "-c",
            "user.name=openwiki-arm",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            "sources",
        ],
    ]
    for step in steps:
        run_checked(
            step,
            what=" ".join(step),
            not_found_hint="install git — the OpenWiki code mode reads git context",
            timeout_s=_GIT_TIMEOUT_S,
            error=OpenWikiCliError,
            cwd=workdir,
        )


def _openwiki_env(stack: LocalModelStack) -> dict[str, str]:
    """The env OpenWiki needs to run against the local Ollama OpenAI-compatible endpoint
    (no-paid-API, Decision 16). Model + base-url come from ``LocalModelStack`` (never
    hardcoded); the api key is a non-empty placeholder Ollama ignores but the OpenAI SDK
    requires. Verified against openwiki v0.1.0 (mem-nul9j)."""
    base_url = f"{stack.ollama_base_url.rstrip('/')}/v1"
    return {
        "OPENWIKI_PROVIDER": _OPENWIKI_PROVIDER,
        "OPENAI_COMPATIBLE_BASE_URL": base_url,
        "OPENAI_COMPATIBLE_API_KEY": os.environ.get("OPENAI_COMPATIBLE_API_KEY") or "ollama",
        "OPENWIKI_MODEL_ID": stack.chat_model,
    }


class _CliWikiSynthesizer:
    """Adapts the OpenWiki CLI to ``WikiSynthesizer``. Each ``synthesize`` call runs in
    a FRESH throwaway workdir: it writes the live raw sources as Markdown files,
    git-snapshots them, shells ``openwiki code --init --print`` against the local
    OpenAI-compatible (Ollama) endpoint, reads the synthesised ``openwiki/`` pages back
    (recursively — OpenWiki nests them under ``architecture/``, ``workflows/``, …), then
    removes the workdir.

    A per-call hermetic dir is load-bearing — a workdir shared across trials would let
    OpenWiki build one trial's wiki off another's stale sources, leaking the answer
    across the temporal-LOO boundary (and a fixed relative default would make the
    location cwd-dependent and racy under concurrent sequences).

    Contract verified against openwiki v0.1.0 (mem-nul9j): provider/model/base-url are
    ENV-driven (``_openwiki_env`` from ``LocalModelStack`` — no-paid-API, Decision 16),
    ``code`` mode needs a git commit to have anything to document (``_git_snapshot``),
    ``--init`` is the fresh-build command, and pages land nested under ``openwiki/``. The
    subprocess runner is injected so this class stays unit-testable with no ``openwiki``
    binary and no Ollama; the real end-to-end path is exercised by a provisioning-gated
    integration test (skipped in CI)."""

    _WIKI_SUBDIR = "openwiki"

    def __init__(
        self,
        parent_dir: str | Path | None = None,
        *,
        stack: LocalModelStack | None = None,
        runner: WikiCliRunner | None = None,
    ) -> None:
        # Parent for the per-call throwaway workdirs; ``None`` -> the system temp dir.
        self._parent_dir = str(parent_dir) if parent_dir is not None else None
        self._stack = stack or LocalModelStack.from_env()
        self._runner = runner or _default_cli_runner

    def synthesize(self, *, sources: Mapping[str, str]) -> WikiSynthesisResult:
        if not sources:
            return WikiSynthesisResult(pages=(), background_tokens=0)
        # A source id is a filename here; an unsafe id (``/``, ``..``) would escape the
        # workdir on write, so reject it loudly — same guard the sibling filesystem arm
        # enforces (``filesystem_system._safe_name``), never a silent mangle/overwrite.
        for mid in sources:
            if _safe_name(mid) != mid:
                raise ValueError(
                    f"{self.__class__.__name__}: source id {mid!r} is not filesystem-safe "
                    "(use only alphanumerics, '-', '_', '.'); it would escape the workdir."
                )
        if self._parent_dir is not None:
            Path(self._parent_dir).mkdir(parents=True, exist_ok=True)
        workdir = Path(tempfile.mkdtemp(prefix="openwiki-arm-", dir=self._parent_dir))
        try:
            source_ids = tuple(sources.keys())
            for mid, content in sources.items():
                (workdir / f"{mid}.md").write_text(content, encoding="utf-8")
            _git_snapshot(workdir)
            argv = [
                "openwiki",
                "code",
                "--init",
                "--print",
                "--modelId",
                self._stack.chat_model,
                "Document every source file as wiki pages.",
            ]
            stdout = self._runner(argv, workdir, _openwiki_env(self._stack))
            background_tokens = _parse_background_tokens(stdout)
            wiki_dir = workdir / self._WIKI_SUBDIR
            pages = tuple(
                # No per-page citations from OpenWiki: conservatively cite every source.
                # Page id = the namespaced, filesystem-safe relative path (e.g.
                # ``openwiki-page-architecture_overview``) so it cannot collide with a raw
                # ``memory_id``. rglob so nested pages are not dropped.
                WikiPage(
                    page_id=f"{_PAGE_PREFIX}{_safe_name(str(md.relative_to(wiki_dir).with_suffix('')))}",
                    content=md.read_text(encoding="utf-8"),
                    source_ids=source_ids,
                )
                for md in sorted(wiki_dir.rglob("*.md"))
            )
            return WikiSynthesisResult(pages=pages, background_tokens=background_tokens)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


def _parse_background_tokens(stdout: str) -> int:
    """Best-effort read of OpenWiki's ``--print`` token accounting. OpenWiki prints a
    trailing JSON summary line; a run that omits it reports 0 (an honest absence, never
    a fabricated cost). Never raises — a malformed line means no metered cost, not a
    crashed consolidation."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        total = obj.get("total_tokens")
        # ``bool`` is an ``int`` subclass — exclude it so ``{"total_tokens": true}`` reads
        # as malformed (skip), not a token count of 1.
        if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
            return total
    return 0


def default_openwiki_synthesizer(parent_dir: str | Path | None = None) -> WikiSynthesizer:
    """Build the real CLI-backed synthesiser. Construction does NO shelling and needs no
    ``openwiki`` binary — the CLI is invoked only when ``consolidate()`` calls
    ``synthesize``, so a bare ``build_memory_system('openwiki')`` constructs cleanly and
    only a real consolidation touches the CLI. ``parent_dir`` (``None`` -> system temp)
    is the parent for the per-consolidation throwaway workdirs."""
    return _CliWikiSynthesizer(parent_dir)


class OpenWikiMemory(MemorySystem):
    """LangChain OpenWiki arm. Two-speed consolidating-filesystem: O(1) raw ``write``,
    offline LLM ``consolidate()`` that synthesises wiki pages, ``retrieve`` returns the
    synthesised pages. Satisfies ``ConsolidationCapable`` structurally (``consolidate``
    + ``tombstone``) without widening the ``MemorySystem`` ABC."""

    name = "openwiki"
    backend = MemoryBackend.FILESYSTEM
    supports_write = True

    def __init__(self, synthesizer: WikiSynthesizer | None = None) -> None:
        self._synthesizer = (
            synthesizer if synthesizer is not None else default_openwiki_synthesizer()
        )
        self._reset_state()

    def _reset_state(self) -> None:
        # Raw sources (the hot-write log), the pages consolidation produced, each page's
        # provenance, and the soft-delete set. Nothing is ever hard-deleted (M7).
        self._store: dict[str, str] = {}
        self._order: list[str] = []
        self._tombstoned: set[str] = set()
        self._pages: dict[str, str] = {}
        self._provenance: dict[str, tuple[str, ...]] = {}

    def reset(self, trial_id: str) -> None:
        self._reset_state()

    # -- hot path: O(1) wake-append, no model call ------------------------- #
    def write(self, memory_id: str, content: str, ctx: StepContext) -> MemoryEvent:
        if memory_id not in self._store:
            self._order.append(memory_id)
        self._store[memory_id] = content
        return MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool=f"{self.name}.ingest_source",
            normalized_operation=MemoryOperation.WRITE,
            backend=self.backend,
            written_ids=[memory_id],
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )

    # -- offline consolidation: shell OpenWiki to synthesise the wiki ------ #
    def _live_sources(self) -> dict[str, str]:
        return {mid: self._store[mid] for mid in self._order if mid not in self._tombstoned}

    def consolidate(self, ctx: StepContext) -> ConsolidationResult:
        live = self._live_sources()
        if not live:
            return ConsolidationResult(notes={"pages": "0"})
        result = self._synthesizer.synthesize(sources=live)
        # Validate the WHOLE batch before committing any page: a later sourceless page
        # must not leave an earlier one half-committed into _pages/_provenance (atomicity).
        for page in result.pages:
            if not page.source_ids:
                # A page citing nothing is a sourceless fabrication — fail loud rather
                # than record a page the provenance gate can never dereference.
                raise ValueError(
                    f"{self.name!r}: synthesised page {page.page_id!r} has no source_ids; "
                    "a wiki page must cite the sources it was synthesised from (M7)."
                )
        items: list[ConsolidatedItem] = []
        for page in result.pages:
            self._pages[page.page_id] = page.content
            self._provenance[page.page_id] = page.source_ids
            items.append(
                ConsolidatedItem(
                    memory_id=page.page_id,
                    content=page.content,
                    source_trace_ids=page.source_ids,
                )
            )
        # Every source folded into a page is subsumed (soft-deleted, still re-derivable).
        # Ordered dedup (not a set) so tombstoned_ids is deterministic run-to-run.
        subsumed = list(dict.fromkeys(mid for page in result.pages for mid in page.source_ids))
        for mid in subsumed:
            self.tombstone(mid)
        return ConsolidationResult(
            items=tuple(items),
            tombstoned_ids=tuple(subsumed),
            background_tokens=result.background_tokens,
            notes={"pages": str(len(result.pages))},
        )

    def tombstone(self, memory_id: str) -> None:
        # Soft delete: the raw source stays in _store and is_live keeps reporting True,
        # so a subsumed source is still re-derivable (the M7 reversibility invariant).
        self._tombstoned.add(memory_id)

    def is_live(self, trace_id: str) -> bool:
        """Reachability oracle for the provenance gate: a source is live iff its raw
        content is still present (tombstoned-but-present counts; only a real GC reap
        would make it dead — and this arm has no hard delete)."""
        return trace_id in self._store

    # -- retrieval: return the synthesised pages --------------------------- #
    def retrieve(self, request: RetrievalRequest, ctx: StepContext) -> RetrieveResult:
        """Return the synthesised wiki page(s) for the requested ids. A subsumed raw id
        redirects to every page it fed; because OpenWiki synthesises cross-source and
        emits no per-page citations, that page set is effectively the whole wiki — the
        honest model of "the agent reads the wiki," and the harness's precision/coverage
        guard is what measures that injected volume (this is NOT a precision-ranked arm)."""
        payloads: dict[str, str] = {}
        provenance: dict[str, tuple[str, ...]] = {}
        for rid in request.requested_ids:
            if rid in self._pages:  # a synthesised page asked for directly
                payloads[rid] = self._pages[rid]
                provenance[rid] = self._provenance[rid]
            elif rid in self._store and rid not in self._tombstoned:  # raw, not yet consolidated
                payloads[rid] = self._store[rid]
                provenance[rid] = (rid,)
            elif rid in self._tombstoned:  # subsumed → redirect to the synthesised page
                for pid, sources in self._provenance.items():
                    if rid in sources:
                        payloads[pid] = self._pages[pid]
                        provenance[pid] = sources
        event = MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool=f"{self.name}.read_wiki",
            normalized_operation=MemoryOperation.SEARCH,
            backend=self.backend,
            query=request.query_text,
            retrieved_ids=list(payloads),
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )
        return RetrieveResult(payloads=payloads, event=event, source_trace_ids=provenance)


# Re-exported for callers that annotate against the seam types.
__all__ = [
    "ConcatWikiSynthesizer",
    "OpenWikiMemory",
    "WikiPage",
    "WikiSynthesisResult",
    "WikiSynthesizer",
    "default_openwiki_synthesizer",
]
