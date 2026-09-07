"""Real reference corpus: work-audit records -> transcripts -> §8 ``Trace`` (mem-ovi.1).

The gated RUN leg of the mem-ovi realism metric's real side. ``real_loader.py``
is pure — it reduces already-loaded ``Trace`` objects — so THIS module owns the
two IO steps that produce them: querying the live ``.mem`` work-audit graph for
candidate ``WorkRecord``\\ s, and parsing each one's transcript JSONL into a
``Trace``.

Querying reuses ``corpus.py``'s injectable-runner seam directly (``CorpusRunner``,
``_resolve``): the runner-resolution plumbing has no reason to diverge between
the two callers. What stays separate is the record PROJECTION —
``corpus.py`` loads the LOO-relevant ``WorkRef`` for retrieval, this module loads
the RAW record (it needs ``trace.jsonl_path``, which ``WorkRef`` deliberately
drops) — same query seam, different projection.

Fork A — the corpus SUBSET (which real records enter the reference corpus, e.g.
by rig/status/date-range) — is PENDING Stephanie #mem sign-off (mem-ovi §1). This
loader hardcodes no default: ``load_work_records`` takes ``filters`` as an
explicit caller-supplied mapping onto ``mem query`` CLI flags, so resolving fork A
is entirely the caller's call, never a change to this module.

Fork B — SESSION -> STEP segmentation — is defaulted (user-turn) and independently
injectable (``segmenter``) inside ``real_loader.py``, not here; this module only
supplies the ``Trace``.

Fork C — ``task_text`` gc-prime boilerplate handling — is surfaced, not resolved,
by ``default_message_filter``'s docstring: for autonomous worker-pool sessions the
non-meta non-tool_result "user" turn set is typically just the orchestrator
kickoff line (e.g. "Run gc prime..."), so ``n_steps`` / ``task_text_length`` on
these real sessions measure something structurally different from a synthetic
task's authored ``user_request``. ``message_filter`` is injectable specifically so
Stephanie's eventual call on this does not require touching the loader.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from membench.corpus import CorpusRunner
from membench.corpus import _resolve as _resolve_runner
from membench.schemas.trace import ToolCall, Trace, TraceMessage

logger = logging.getLogger(__name__)

# One raw transcript entry (a parsed JSONL line). Only a `Mapping` is assumed —
# the transcript format's other entry types (`mode`, `attachment`, `system`, ...)
# are read defensively via `.get`, never indexed.
TranscriptEntry = Mapping[str, Any]

# Decides whether one non-sidechain user/assistant transcript entry becomes a
# session `TraceMessage`. Injectable so a caller can resolve fork C (or any other
# corpus-shape judgment call) without editing this module.
MessageFilter = Callable[[TranscriptEntry], bool]

# Reads the transcript text at a `trace.jsonl_path`. Injectable so tests exercise
# `load_real_corpus` against hand-built fixtures with no filesystem access.
TranscriptReader = Callable[[str], str]


def load_work_records(
    store_path: str,
    *,
    mem_bin: str | None = None,
    runner: CorpusRunner | None = None,
    filters: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Query the work-audit graph for the raw ``WorkRecord`` dicts a real
    reference corpus is built from.

    ``filters`` maps ``mem query`` CLI flag names (without the leading ``--``,
    e.g. ``"rig"``, ``"status"``, ``"agent"``) straight onto argv — see
    ``src/cli/commands/query.ts`` for the accepted set. Which records qualify
    (fork A: corpus subset) is entirely the caller's call; this loader applies
    no rig/status default of its own."""
    args = ["query", "--store", store_path]
    for flag, value in (filters or {}).items():
        args.extend([f"--{flag}", value])
    data = _resolve_runner(runner, mem_bin)(args)
    return list(data["records"])


def _message_content(entry: TranscriptEntry) -> Any:
    """The raw `entry.message.content` value (`str`, `list`, or `None` when the
    entry carries no `message`, or an entry type — e.g. `system` — that has none).
    Every other message-shape helper derives from this single lookup."""
    message = entry.get("message")
    return message.get("content") if isinstance(message, Mapping) else None


def _content_blocks(entry: TranscriptEntry) -> list[Any]:
    """The entry's `message.content[]` blocks, or `[]` when absent/not a list
    (a bare string content, or an entry type that carries no `message` at all)."""
    content = _message_content(entry)
    return content if isinstance(content, list) else []


def _is_tool_result_shaped(entry: TranscriptEntry) -> bool:
    """True when every content block is a `tool_result` — Claude Code's own
    marker for a tool invocation's echoed-back output, never authored
    conversation. An entry with no blocks (e.g. bare string content) is not
    tool_result-shaped by this definition."""
    blocks = _content_blocks(entry)
    return bool(blocks) and all(
        isinstance(block, Mapping) and block.get("type") == "tool_result" for block in blocks
    )


def default_message_filter(entry: TranscriptEntry) -> bool:
    """Keep a non-sidechain user/assistant transcript entry as a session message
    unless it is tool_result-shaped (``_is_tool_result_shaped``) or ``isMeta`` is
    truthy.

    Both are the transcript FORMAT's own flags — not an invented heuristic:
    ``isMeta`` marks Claude Code's own injected context (base skill / slash-
    command boilerplate), and a tool_result block is the harness's own echo of a
    tool call's output, not something the session author said. For an autonomous
    worker-pool session the surviving non-meta, non-tool_result "user" turn set is
    typically just the orchestrator kickoff line (fork C, see the module
    docstring) — this filter does not resolve that, only avoids conflating it with
    injected boilerplate."""
    if entry.get("isMeta"):
        return False
    return not _is_tool_result_shaped(entry)


def _entry_text(entry: TranscriptEntry) -> str:
    """Flatten one entry's `message.content` to plain text: a bare string passes
    through unchanged; a block list joins only `text`-typed blocks (`thinking`,
    `tool_use`, and `tool_result` blocks carry no conversational text)."""
    content = _message_content(entry)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, Mapping) and block.get("type") == "text"
        )
    return ""


def _is_textual(entry: TranscriptEntry) -> bool:
    """True when the entry carries conversational text: a bare string content, or
    at least one `text`-typed block. An assistant turn made up ENTIRELY of
    `tool_use`/`thinking` blocks has nothing to contribute as a session message
    (its tool_use blocks are already captured as `tool_calls`) — including it
    anyway would add a phantom zero-length turn."""
    content = _message_content(entry)
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return any(isinstance(block, Mapping) and block.get("type") == "text" for block in content)
    return False


def parse_transcript(
    jsonl_text: str,
    *,
    message_filter: MessageFilter = default_message_filter,
) -> tuple[list[TraceMessage], list[ToolCall]]:
    """Parse a raw Claude Code transcript JSONL into ``(messages, tool_calls)``.

    Only non-sidechain ``user``/``assistant`` entries are considered:
    ``isSidechain`` marks a sub-agent's own conversation, Claude Code's own flag
    for "not the main session thread", which is out of scope for a session-level
    structural trace. Tool calls are every ``tool_use`` content block on a
    non-sidechain ``assistant`` entry. Messages are every non-sidechain
    ``user``/``assistant`` entry that survives ``message_filter`` (default:
    ``default_message_filter``) AND carries conversational text (``_is_textual``
    — a tool_use/thinking-only assistant turn is not a message, only a tool
    call), reduced to ``(role, flattened text)``.

    Malformed lines (a truncated append-only write, exactly as the trace index
    tolerates) are skipped, never raised."""
    messages: list[TraceMessage] = []
    tool_calls: list[ToolCall] = []
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or entry.get("isSidechain"):
            continue
        entry_type = entry.get("type")
        if entry_type not in ("user", "assistant"):
            continue
        if entry_type == "assistant":
            for block in _content_blocks(entry):
                if isinstance(block, Mapping) and block.get("type") == "tool_use":
                    name = block.get("name")
                    if isinstance(name, str) and name:
                        tool_calls.append(ToolCall(name=name))
        if message_filter(entry) and _is_textual(entry):
            message = entry.get("message")
            role = message.get("role") if isinstance(message, Mapping) else None
            messages.append(TraceMessage(role=str(role or entry_type), content=_entry_text(entry)))
    return messages, tool_calls


def _read_transcript_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _trace_from_record(
    record: Mapping[str, Any], messages: list[TraceMessage], tool_calls: list[ToolCall]
) -> Trace:
    """Map a WorkRecord's own identity/lifecycle fields onto a `Trace`'s required
    §8 identity fields. These identifiers are opaque to `real_loader.py` (it only
    reads `messages` / `tool_calls` / `memory_events`); they are populated from
    the record's real fields rather than placeholders so the `Trace` stays
    traceable back to its source `work_id`. `memory_events` is always `[]`,
    consistent with `perfeature_reference.py`'s documented finding that real
    coding sessions emit zero memory ops pre-forward-capture."""
    lifecycle = record.get("lifecycle") or {}
    agents = record.get("agents") or []
    started = lifecycle.get("started") or lifecycle.get("created") or ""
    return Trace(
        trial_id=str(record["work_id"]),
        experiment_id=str(record.get("rig", "")),
        dataset_id="mem-corpus",
        task_id=str(record["work_id"]),
        step_id=str(record["work_id"]),
        agent_config_id=str(agents[0].get("agent_id", "unknown")) if agents else "unknown",
        memory_config_id="real",
        start_time=str(started),
        end_time=str(lifecycle.get("closed") or started),
        messages=messages,
        tool_calls=tool_calls,
        memory_events=[],
    )


def load_real_corpus(
    store_path: str,
    *,
    mem_bin: str | None = None,
    runner: CorpusRunner | None = None,
    filters: Mapping[str, str] | None = None,
    message_filter: MessageFilter = default_message_filter,
    transcript_reader: TranscriptReader = _read_transcript_file,
) -> list[Trace]:
    """Query the work-audit graph (``load_work_records``) and parse each
    qualifying record's transcript (``parse_transcript``) into a ``Trace``.

    A record with no ``trace.jsonl_path``, or whose transcript cannot be read,
    is logged and skipped rather than raised — real corpora routinely include
    unresolved or archived-away transcripts (mem-h3di), and one bad record must
    not abort the whole reference-corpus load."""
    records = load_work_records(store_path, mem_bin=mem_bin, runner=runner, filters=filters)
    traces: list[Trace] = []
    for record in records:
        trace_ref = record.get("trace") or {}
        jsonl_path = trace_ref.get("jsonl_path")
        if not jsonl_path:
            logger.warning("work_id %s has no trace.jsonl_path; skipping", record.get("work_id"))
            continue
        try:
            text = transcript_reader(jsonl_path)
        except (OSError, UnicodeDecodeError) as exc:
            # UnicodeDecodeError (raised by the default _read_transcript_file on
            # invalid-UTF-8 bytes, e.g. a corrupted/archived transcript) is a
            # ValueError subclass, not an OSError — it must be caught alongside
            # the missing-file/permission case or it propagates and aborts the
            # whole corpus load, breaking this function's own skip-not-raise
            # contract (mem-ovi.1 rejection).
            logger.warning(
                "work_id %s transcript unreadable at %s: %s", record.get("work_id"), jsonl_path, exc
            )
            continue
        messages, tool_calls = parse_transcript(text, message_filter=message_filter)
        traces.append(_trace_from_record(record, messages, tool_calls))
    return traces
