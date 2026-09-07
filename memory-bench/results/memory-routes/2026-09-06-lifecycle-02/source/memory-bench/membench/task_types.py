"""Model task-type classification for free-form beads (mem-75t.11).

The store's task typing has three sources (see src/ingest/task-type.ts):
`formula` and `structural` are mechanical projections done at ingest; this
module supplies the third — a MODEL classifies the free-form residue into a
closed taxonomy, and every entry records which model said so and when
(`task_type_source='model'` in the store; never silently mixed with the
mechanical sources).

ZFC boundary: the semantic judgment is the model call (injected as a runner
callable so tests use a stub). Everything here is orchestration — batching,
prompt assembly, structural validation of the response (label must be in the
taxonomy, work_id must be one we asked about), and cache merging. Invalid
model output is dropped AND counted, never silently accepted or retried into
the cache.

The mechanical predicate is a deliberate mirror of the TS rules: it only
decides which beads to SKIP (already typed at ingest). If it drifts from the
TS side the failure is benign — a bead gets a model label the ingest then
ignores, because mechanical rules take precedence there.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from membench.judge_config import IsolatedJudgeConfig, run_isolated_claude
from membench.spawn import Runner

# Mirror of MODEL_TASK_TAXONOMY in src/ingest/task-type.ts — keep in sync.
TAXONOMY = frozenset(
    {
        "feature",
        "bugfix",
        "refactor",
        "testing",
        "docs",
        "research",
        "review",
        "triage",
        "infra",
        "release",
        "coordination",
        "report",
        "other",
    }
)

# Runner seam: prompt in, raw model text out (production shells `claude -p`).
ModelRunner = Callable[[str], str]

# A classification batch is bounded (batch_size items of one title line each); a
# multi-minute bound means a wedged subprocess, not slow inference.
DEFAULT_CLASSIFIER_TIMEOUT_S = 300.0


def claude_model_runner(
    model: str,
    isolation: IsolatedJudgeConfig,
    *,
    timeout_s: float = DEFAULT_CLASSIFIER_TIMEOUT_S,
    runner: Runner = subprocess.run,
) -> ModelRunner:
    """The production `ModelRunner`: headless ``claude -p`` through the shared
    mem-9ld4 isolation choke point (`run_isolated_claude`, mem-hv9l). ``isolation``
    is REQUIRED — there is deliberately no un-isolated variant of this runner, so a
    classifier can never shell the host config surface (where a host/project agent
    could hijack the reply). Raw stdout comes back unparsed
    (`parse_classification`'s job), so no ``--output-format json``. ``runner`` is
    injectable so tests drive the seam without spawning a real claude."""

    def run(prompt: str) -> str:
        return run_isolated_claude(
            prompt,
            isolation=isolation,
            runner=runner,
            timeout_s=timeout_s,
            model=model,
            callsite="task-type classifier",
            output_format_json=False,
        )

    return run


_FORMULA_TITLE = re.compile(r"^mol-[a-z0-9-]+$")
_COPILOT_ITERATE = re.compile(r"^Iterate copilot review \d+ on ")


def mechanical_task_type(title: str, metadata: Mapping[str, Any]) -> str | None:
    """The mechanical (formula/structural) type the TS ingest will assign, or
    None when only a model can type the bead. Mirror of deriveMechanicalType
    in src/ingest/task-type.ts — used here only to pick the classification
    population."""
    if _FORMULA_TITLE.match(title):
        return title
    step_ref = metadata.get("gc.step_ref")
    if isinstance(step_ref, str) and step_ref:
        return step_ref
    if title.startswith("Rollup("):
        return "rollup"
    if title.startswith("input convoy for ") or metadata.get("gc.synthetic") == "true":
        return "convoy"
    if _COPILOT_ITERATE.match(title):
        return "pr-review-iterate"
    if title == "Human review checkpoint":
        return "review-checkpoint"
    if title.startswith("sling-"):
        return "sling-dispatch"
    return None


@dataclass(frozen=True)
class BeadItem:
    work_id: str
    rig: str
    title: str


_PROMPT_HEADER = """You are classifying software-work items into a fixed taxonomy.

Labels (choose EXACTLY one per item):
- feature: implement new functionality
- bugfix: fix a defect or regression
- refactor: restructure code without changing behavior
- testing: write/fix/extend tests or test infrastructure
- docs: documentation, guides, README/AGENTS files
- research: investigation, analysis, literature/codebase exploration, spikes
- review: code/PR review work
- triage: diagnose/prioritize incoming issues or failures
- infra: CI, build, tooling, deployment, environment work
- release: shipping, versioning, publishing, merging release branches
- coordination: dispatching, scheduling, mail/messaging, agent orchestration
- report: status summaries, digests, rollups
- other: none of the above fits

Items (one per line, "work_id | rig | title"):
"""

_PROMPT_FOOTER = """
Respond with ONLY a JSON object mapping every work_id to its label, e.g.
{"mem-1": "bugfix", "gc-2": "coordination"}. No other text."""


def classification_prompt(items: Sequence[BeadItem]) -> str:
    lines = "\n".join(f"{i.work_id} | {i.rig} | {i.title}" for i in items)
    return _PROMPT_HEADER + lines + _PROMPT_FOOTER


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class ParseResult:
    labels: dict[str, str]
    n_invalid_label: int
    n_unknown_id: int
    n_missing: int


def parse_classification(text: str, expected_ids: Iterable[str]) -> ParseResult:
    """Validate one model response: extract the JSON object, keep only labels
    in the taxonomy for ids we actually asked about. Everything else is
    counted, not silently kept."""
    expected = set(expected_ids)
    match = _JSON_OBJECT.search(text)
    if match is None:
        return ParseResult({}, 0, 0, len(expected))
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return ParseResult({}, 0, 0, len(expected))
    if not isinstance(payload, Mapping):
        return ParseResult({}, 0, 0, len(expected))

    labels: dict[str, str] = {}
    invalid = unknown = 0
    for work_id, label in payload.items():
        if work_id not in expected:
            unknown += 1
            continue
        if not isinstance(label, str) or label not in TAXONOMY:
            invalid += 1
            continue
        labels[work_id] = label
    return ParseResult(
        labels=labels,
        n_invalid_label=invalid,
        n_unknown_id=unknown,
        n_missing=len(expected - labels.keys()),
    )


def classify(
    items: Sequence[BeadItem],
    runner: ModelRunner,
    *,
    model: str,
    classified_at: str,
    batch_size: int = 40,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[dict[str, dict[str, str]], dict[str, int]]:
    """Classify items in batches. Returns (entries, counters). Entries carry
    the model id + timestamp so the store's `model` provenance is auditable.
    A batch whose response fails structural validation contributes its valid
    subset; the rest is counted under the failure counters."""
    entries: dict[str, dict[str, str]] = {}
    counters = {"batches": 0, "invalid_label": 0, "unknown_id": 0, "missing": 0}
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        counters["batches"] += 1
        text = runner(classification_prompt(batch))
        result = parse_classification(text, [i.work_id for i in batch])
        counters["invalid_label"] += result.n_invalid_label
        counters["unknown_id"] += result.n_unknown_id
        counters["missing"] += result.n_missing
        for work_id, label in result.labels.items():
            entries[work_id] = {
                "task_type": label,
                "model": model,
                "classified_at": classified_at,
            }
        if on_progress is not None:
            on_progress(f"{min(start + batch_size, len(items))}/{len(items)} classified")
    return entries, counters
