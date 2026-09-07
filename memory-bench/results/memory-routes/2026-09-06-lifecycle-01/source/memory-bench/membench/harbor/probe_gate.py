"""Dynamic-range probe runner mechanism (mem-75t.7.6, plan §9.2).

The gate runs each admitted `TaskBundle` under two conditions and measures the gap:

- ``none``  -- the stateless floor: the bundle's issue statement, nothing else.
- ``oracle`` -- the cheap upper-bound rung: the SAME issue statement plus
  `gold_file_list(bundle)` injected as "files likely relevant to this task" through
  the `memory_inject` mechanism (`inject_context`). No curated oracle needed.

Execution MIRRORS the base-rate spike's proven path (`base_rate_spike` 2026-06-10):
a Harbor task dir (``task.toml`` + ``instruction.md`` + ``environment/``), the repo
snapshot baked in via `env_recon.reconstruct_env` -- here at the bundle's EXACT
``env.base_commit``, not a timestamp approximation -- and the run shelled through
``harbor run`` on the Claude OAuth subscription (D16, free path) via
`harbor_exec.run_harbor_job`, harvesting the Claude Code stream-json transcript
(``claude-code.txt``) from the ATIF jobs dir.

The candidate diff is SYMMETRIC with the gold diff: the fresh run's
``Edit``/``Write``/``MultiEdit`` calls are parsed from its transcript
(`bundle.replay.parse_mutation_calls`) and replayed against a fresh detached
checkout of ``repo@base_commit`` (`replay_calls`), rebasing container paths from
``/app`` (the `env_recon` Dockerfile WORKDIR) onto the checkout -- so candidate and
gold per-file diffs share one coordinate space (checkout-relative git paths), which
is exactly what `score_probe_direct` requires. Checkouts are created and removed
per harvest (try/finally); `stale_probe_worktrees` is the CLI's exit-sweep hook.

Leak discipline: the prompt and the injected context must NEVER carry the answer.
`probe_leak_labels` feeds `assert_no_outcome_leak` with the bundle's
``base_commit``, every gold per-file diff text, and the serialized replay-stat /
verification field markers -- so a bundle JSON pasted into a prompt, a planted gold
hunk, or a leaked score field all fail loudly before anything reaches disk.

ZFC: pure mechanism -- IO, subprocess, structural validation, set/percentile
arithmetic. The GO/NO-GO verdict is authored by the orchestrator over this module's
DATA (`summarize_pairs` emits a mechanical ``gap_positive_majority`` flag only).
Everything subprocess- or Harbor-shaped is injectable for tests (no Docker, no
network): the ``Runner`` seam (env_recon's pattern) and the ``StreamExec`` seam.
"""

import json
import shutil
import subprocess
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from statistics import fmean, median
from typing import Any

import toml
from pydantic import BaseModel, ConfigDict, Field

from membench.bundle.replay import ReplayOutcome, ReplayResult, parse_mutation_calls, replay_calls
from membench.grading import assert_no_outcome_leak
from membench.grading.probe_direct import (
    ProbeDirectScore,
    ProbeEfficiency,
    extract_efficiency,
    gold_file_list,
    score_probe_direct,
)
from membench.harbor.agent_memory import (
    AGENT_CONFIG_DIR,
    AGENT_MEMORY_ENV,
    AGENT_NATIVE_MEMORY_PATH,
    DELIVERED_MEMORY_PATHS,
    INSTRUCTION_MEMORY_PATH,
    path_covers_native_memory,
)
from membench.harbor.agent_memory import (
    AGENT_WORKDIR as CONTAINER_WORKDIR,
)
from membench.harbor.control_conditions import (
    FULL_CONTEXT,
    RAW_TRAJECTORY,
    InScopeWork,
    PayloadTruncation,
    full_context_payload,
    raw_trajectory_payload,
)
from membench.harbor.env_recon import DEFAULT_RIG_REPOS, reconstruct_env
from membench.harbor.harbor_exec import _locate_one, project_claude_stream, run_harbor_job
from membench.harbor.memory_inject import (
    MEMORY_FILENAME,
    MEMORY_HEADER,
    inject_context,
    write_signature_overlap,
)
from membench.harbor.shuffled_condition import SHUFFLED, ShuffledSelection
from membench.harbor.task_env import NetworkMode, environment_network
from membench.schemas.bundle import TaskBundle
from membench.spawn import Runner

# The gate's two conditions (plan §9.2): the stateless floor and the cheap ceiling.
CONDITIONS: tuple[str, ...] = ("none", "oracle")

# Clean-room conditions (mem-p3w + mem-hhto + mem-tnyo): the SAME task with the
# agent's native project memory removed from the image, so the only memory variable
# is the injected one. ``none-clean`` is the clean-room floor; ``ours`` additionally
# injects retrieval-v1's citation+lessons payload (D9) through the same
# `memory_inject` path as the oracle — its retrieval query is formed from the held
# record's OWN stored trace errors (an ORACLE trigger: information a fresh agent
# does not have pre-failure), recorded as ``trigger = "oracle"`` in the run
# conditions; ``ours-issue-trigger`` (mem-tnyo) is the separable trigger control —
# the SAME strip, injection, and leak guards, but the retrieval query is formed
# WITHOUT the held record's trace errors (`mem retrieve --no-trace-query`:
# title/task-type text only, the fields available at dispatch time), recorded as
# ``trigger = "issue-text"``; ``shuffled`` (mem-hhto) is the ours arm's
# content-attribution placebo — the SAME rendering and leak guards, but the payload
# is the ours payload retrieved for a DIFFERENT bundle (deterministic other-repo,
# volume-matched donor; `shuffled_condition.select_donor`). If shuffled moves the
# metric like ours does, the win was volume, not content.
OURS_ISSUE_TRIGGER = "ours-issue-trigger"
# The ours-family conditions: identical build path, differing only in how the
# retrieval query was formed (the payload mapping the caller resolves).
OURS_CONDITIONS: tuple[str, ...] = ("ours", OURS_ISSUE_TRIGGER)
CLEAN_CONDITIONS: tuple[str, ...] = ("none-clean", *OURS_CONDITIONS, SHUFFLED)

# How each ours-family condition's retrieval query was formed — persisted into
# the run conditions (task.toml metadata) so the trigger is explicit in every
# emitted artifact (mem-tnyo relabel; the condition KEY stays stable for
# existing readers, the trigger field is additive).
CONDITION_TRIGGER: dict[str, str] = {"ours": "oracle", OURS_ISSUE_TRIGGER: "issue-text"}

# Brute-force control conditions (M3/M4): the distilled-memory arm's opposites,
# injected on the native (non-clean) base like ``oracle``. ``raw-trajectory`` bakes
# the bundle's RAW transcript; ``full-context`` bakes ALL in-scope prior work,
# LOO-bounded. Both run the SAME leak guard as every other condition — a raw
# transcript / prior-work dump that quotes the gold diff fails loud (a coverage
# exclusion the driver records, never a silent skip).
CONTROL_CONDITIONS: tuple[str, ...] = ("raw-trajectory", "full-context")
ALL_CONDITIONS: tuple[str, ...] = CONDITIONS + CLEAN_CONDITIONS + CONTROL_CONDITIONS

# Char budget for a baked control payload; truncation beyond it is recorded
# (``truncation.json``), never silent (premortem lens 5).
DEFAULT_CONTROL_MAX_CHARS: int = 200_000

# Repo-shipped paths Claude Code auto-loads as project memory (CLAUDE.md/AGENTS.md
# instruction files, the .claude project dir, the .agents migration dir carrying
# copies of both). Removed from /app for clean-room conditions. The user-level
# ~/.claude memory needs no strip: every run is a fresh container, so it is empty.
NATIVE_MEMORY_PATHS: tuple[str, ...] = ("CLAUDE.md", "AGENTS.md", ".claude", ".agents")

# ``CONTAINER_WORKDIR`` (= ``/app``, the env_recon Dockerfile WORKDIR and the rebase
# prefix for candidate replay) is imported from `agent_memory` as its single source of
# truth, since the native-memory sub-path is derived from the same workdir slug.

# Where the injected context file lands for the fixed INSTRUCTION to name. OUTSIDE /app on
# purpose: an agent write to it would rebase outside the checkout (classified
# OUTSIDE_WORK_DIR) instead of polluting the candidate diff. The build ALSO delivers the
# same file to the agent's native-memory path (`agent_memory.NATIVE_MEMORY_PATH`) — the
# path the agent actually reads (trace-explorer audit 2026-07-05: the instruction path
# alone was consumed 0/50 times). This alias keeps the instruction target one source.
ORACLE_MEMORY_CONTAINER_PATH = INSTRUCTION_MEMORY_PATH

# Per-task sidecar (task-dir root, NEVER in the image) carrying the agent env override the
# exec layer applies. Only injected conditions write it; `harbor_stream_exec` reads it.
AGENT_ENV_FILENAME = "agent_env.json"

# Serialized bundle replay-stat / verification field markers that must never reach
# agent-readable text -- their presence means bundle internals leaked into a prompt.
_FORBIDDEN_BUNDLE_MARKERS: tuple[str, ...] = (
    "replay_success_rate",
    "adjusted_replay_success_rate",
    "base_predates_tree",
    "score_direct",
    "score_artifact",
)

# The fixed instruction appended to every probe prompt -- BYTE-IDENTICAL across
# conditions (the oracle condition differs only by the injected file's presence).
_FIXED_INSTRUCTION = (
    f"Implement the change described above in the repository at {CONTAINER_WORKDIR}. "
    "Edit the files in place; do not commit. "
    f"If {ORACLE_MEMORY_CONTAINER_PATH} exists, it contains notes from prior sessions "
    "that may be relevant to this task."
)

# Real probe runs are multi-file feature changes (gold diffs up to ~800 lines), so
# the agent budget is wider than the workrecord adapter's 600s spike default.
AGENT_TIMEOUT_SEC = 2400.0

_WORKTREE_PREFIX = "probe-cand-"

# Executes one prepared task dir and returns the run's RAW Claude Code stream-json
# transcript text -- the source both `harvest_candidate` (mutation calls) and
# `extract_efficiency` (tokens/turns) parse. Injectable; production = `harbor_stream_exec`.
StreamExec = Callable[[Path], str]


# --- leak guard --------------------------------------------------------------------


def probe_leak_labels(bundle: TaskBundle) -> tuple[str, ...]:
    """Every label that must not appear in the probe's agent-readable text: the
    env anchor (``base_commit`` -- the same identifier class `leak_guard` scans on
    records), every non-blank gold per-file diff text (the answer itself), and the
    serialized replay-stat / verification markers (bundle-internals leakage)."""
    labels = [bundle.env.base_commit]
    labels += [diff for _, diff in bundle.output.file_diffs if diff.strip()]
    labels += list(_FORBIDDEN_BUNDLE_MARKERS)
    return tuple(labels)


def assert_probe_task_clean(agent_readable: Mapping[str, str], bundle: TaskBundle) -> None:
    """The probe's explicit task-construction guard: no gold diff, no replay stats,
    no verification fields, no base_commit in anything the agent can read. Raises
    `OutcomeLeakError` (via `assert_no_outcome_leak`) listing every offender."""
    assert_no_outcome_leak(dict(agent_readable), probe_leak_labels(bundle))


# --- task construction ---------------------------------------------------------------


def probe_instruction(bundle: TaskBundle) -> str:
    """The probe prompt: the bundle's issue statement + the fixed instruction.

    Takes no ``condition`` argument BY CONSTRUCTION -- the prompt is byte-identical
    across conditions; only the injected context file differs."""
    parts = [f"# {bundle.work_id}", "", "## Task", "", bundle.issue_title, ""]
    if bundle.issue_body.strip():
        parts += [bundle.issue_body, ""]
    parts += ["## Instructions", "", _FIXED_INSTRUCTION, ""]
    return "\n".join(parts)


def oracle_context_payload(bundle: TaskBundle) -> str:
    """The cheap oracle-rung context: `gold_file_list` presented as "files likely
    relevant" -- file PATHS only, never diff content (plan §9.2's poor-man oracle)."""
    listing = "\n".join(f"- {path}" for path in gold_file_list(bundle))
    return f"Files likely relevant to this task:\n\n{listing}\n"


def _task_toml(
    bundle: TaskBundle,
    condition: str,
    network: NetworkMode,
    donor: ShuffledSelection | None = None,
) -> str:
    metadata = {
        "work_id": bundle.work_id,
        "rig": bundle.rig,
        "condition": condition,
        "source": "task-bundle",
    }
    # The explicit trigger label (mem-tnyo): how an ours-family condition's
    # retrieval query was formed. Additive — the condition key is unchanged.
    trigger = CONDITION_TRIGGER.get(condition)
    if trigger is not None:
        metadata["trigger"] = trigger
    # The donor bundle id travels with the run conditions (mem-hhto) so analysis
    # can verify the injected placebo's irrelevance; a same-repo fallback is
    # flagged here too, never silent.
    if donor is not None:
        metadata["shuffled_donor_work_id"] = donor.donor_work_id
        if donor.fallback_reason is not None:
            metadata["shuffled_fallback_reason"] = donor.fallback_reason
    config = {
        "schema_version": "1.1",
        "task": {
            "name": f"membench-probe/{bundle.work_id}-{condition}",
            "description": f"{bundle.issue_title} [{condition}]",
        },
        "metadata": metadata,
        # Real runs need the network (the installed claude-code agent fetches its
        # CLI + the rig's deps) but never public egress: the landed gold fix is
        # publicly fetchable from the rig's GitHub repo (mem-yeoz), so the caller
        # default is "allowlist" (agent hosts + package registries only).
        "environment": environment_network(network),
        "verifier": {"timeout_sec": 300.0},
        "agent": {"timeout_sec": AGENT_TIMEOUT_SEC},
    }
    return toml.dumps(config)


def _bake_memory_into_env(task_dir: Path, memory_file: Path) -> None:
    """Land the injected memory file in the image at BOTH delivery paths.

    `inject_context` writes ``<task_dir>/memory/MEMORY.md``, but Harbor's Docker
    build context is ``environment/`` only -- without a COPY the injected context
    would never reach the agent. Two targets (`agent_memory`):

    - ``NATIVE_MEMORY_PATH`` -- the path the agent's own native-memory block reads
      (``$CLAUDE_CONFIG_DIR/projects/-app/memory/MEMORY.md`` with the relocated config
      dir). This is the one that actually gets consumed; the instruction path alone was
      read 0/50 times (trace-explorer audit). ``chmod -R 777`` so Harbor's adapter runtime
      ``mkdir -p $CLAUDE_CONFIG_DIR/...`` works whatever user it runs as -- forward
      insurance: the base images set no ``USER`` and the task sets no ``agent.user``, so
      both build and run are root today.
    - ``ORACLE_MEMORY_CONTAINER_PATH`` -- the path the fixed instruction names (fallback
      for an agent that follows the instruction literally).

    DELIVERY invariant (mem-f2vi): the run-side gate cannot witness the auto-load -- CC's
    ``memory_paths`` reports the CONFIGURED native dir independent of its contents (verified
    on CLI 2.1.201: byte-identical whether a MEMORY.md is present, the dir is empty, or
    absent; the loaded content never reaches the stdout stream). So the guarantee that
    NON-EMPTY memory actually lands at the native path is enforced HERE, at build: a
    well-formed (header-bearing) source is required before it is baked. An empty/headerless
    native file would auto-load nothing and silently degenerate the arm to ``none`` -- the
    exact invalidity the consumption gate exists to prevent, on the one axis the transcript
    cannot see."""
    content = memory_file.read_text(encoding="utf-8")
    if MEMORY_HEADER not in content:
        raise ValueError(
            f"refusing to bake malformed memory {memory_file}: missing header "
            f"{MEMORY_HEADER!r} (size={len(content)}) -- an empty/headerless native file "
            "auto-loads nothing, degenerating the memory arm to `none`"
        )
    env_dir = task_dir / "environment"
    shutil.copyfile(memory_file, env_dir / "MEMORY.md")
    dockerfile = env_dir / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8")
        + f"COPY MEMORY.md {AGENT_NATIVE_MEMORY_PATH}\n"
        + f"RUN chmod -R 777 {AGENT_CONFIG_DIR}\n"
        + f"COPY MEMORY.md {ORACLE_MEMORY_CONTAINER_PATH}\n",
        encoding="utf-8",
    )


def touches_native_memory(path: str) -> bool:
    """True when ``path`` is under a repo-ROOT `NATIVE_MEMORY_PATHS` entry -- the
    membership test shared by the strip-disjoint guard and the 3-arm driver's
    builtin-surface evidence. Root-anchored on purpose: the strip removes only
    ``/app/<name>`` (and Claude Code auto-loads only the root copies), so a
    nested ``src/CLAUDE.md`` neither conflicts with the strip nor counts as
    native-memory surface."""
    parts = Path(path).parts
    return bool(parts) and parts[0] in NATIVE_MEMORY_PATHS


def assert_strip_disjoint_from_gold(bundle: TaskBundle) -> None:
    """The clean-room strip must never remove a path the gold diff touches -- the
    stripped image and the (unstripped) scoring checkout would diverge on scored
    paths, corrupting the repro/replay coordinate space."""
    offenders = [path for path, _ in bundle.output.file_diffs if touches_native_memory(path)]
    if offenders:
        raise ValueError(
            f"{bundle.work_id}: gold diff touches the clean-room strip set {offenders} -- "
            "a clean-condition run of this bundle cannot be scored faithfully"
        )


def _strip_native_memory(task_dir: Path) -> None:
    """Remove the repo-shipped native project memory from the image (clean room).

    Appended AFTER `reconstruct_env` writes the base Dockerfile, so the strip runs
    after the repo snapshot lands at /app (the same append pattern as
    `_bake_memory_into_env`)."""
    targets = " ".join(f"{CONTAINER_WORKDIR}/{path}" for path in NATIVE_MEMORY_PATHS)
    dockerfile = task_dir / "environment" / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8") + f"RUN rm -rf {targets}\n",
        encoding="utf-8",
    )


def build_probe_task(
    bundle: TaskBundle,
    condition: str,
    task_dir: Path,
    *,
    rig_repos: Mapping[str, Path] = DEFAULT_RIG_REPOS,
    runner: Runner = subprocess.run,
    ours_payloads: Mapping[str, str] | None = None,
    held_signatures: Sequence[str] = (),
    shuffled_payloads: Mapping[str, str] | None = None,
    shuffled_donor: ShuffledSelection | None = None,
    raw_transcript: str | None = None,
    in_scope_payloads: Mapping[str, InScopeWork] | None = None,
    control_max_chars: int = DEFAULT_CONTROL_MAX_CHARS,
    network: NetworkMode = "allowlist",
) -> Path:
    """Write one (bundle, condition) Harbor task dir; return it.

    Environment = the rig clone snapshot at the bundle's EXACT ``env.base_commit``
    with ``env.base_image`` (via `env_recon.reconstruct_env` -- the bundle carries
    the exact anchor, so no timestamp approximation). The prompt is byte-identical
    across ALL conditions; only the image differs:

    - ``none``       -- the snapshot as-is (native project memory present);
    - ``oracle``     -- + `oracle_context_payload` baked in via `memory_inject`;
    - ``none-clean`` -- native project memory stripped (`NATIVE_MEMORY_PATHS`);
    - ``ours``       -- stripped + the caller-resolved retrieval payloads
      (``ours_payloads``, source-id -> rendered citation+lessons) baked in. An
      empty payload is a caller bug: the empty-retrieval case reuses the
      ``none-clean`` run instead of burning an agent run on an identical task.
      The retrieval query behind these payloads is ORACLE-triggered (the held
      record's own stored trace errors) and labeled so in task.toml (mem-tnyo).
    - ``ours-issue-trigger`` -- the mem-tnyo trigger control: byte-identical
      build path to ``ours``, but the caller resolved ``ours_payloads`` from an
      issue-text query (`mem retrieve --no-trace-query` -- no trace errors);
      labeled ``trigger = "issue-text"`` in task.toml.
    - ``shuffled``   -- stripped + a DIFFERENT bundle's ours payload
      (``shuffled_payloads``) baked through the same path; ``shuffled_donor``
      (`shuffled_condition.select_donor`'s record) is persisted as provenance
      (``shuffled-donor.json`` + task.toml metadata).

    ``held_signatures`` (ours-family conditions only): the held record's full +
    relaxed trace-error signatures (canonical TS-computed strings, read from the
    retrieval result's ``query_signatures`` fields). When supplied, the
    per-payload H3 signature-overlap COVARIATE is persisted to the task dir
    (`memory_inject.write_signature_overlap` -- covariate, not guard: overlap is
    the D8 exact-signature retrieval working as designed).

    Every agent-readable text is leak-checked BEFORE any write."""
    if condition not in ALL_CONDITIONS:
        raise ValueError(f"unknown probe condition {condition!r}; known: {list(ALL_CONDITIONS)}")
    if condition in OURS_CONDITIONS and not ours_payloads:
        raise ValueError(
            f"the {condition} condition needs non-empty ours_payloads; an empty retrieval "
            "reuses the none-clean run instead of executing an identical task"
        )
    if condition not in OURS_CONDITIONS and ours_payloads:
        raise ValueError(f"condition {condition!r} takes no ours_payloads")
    if condition not in OURS_CONDITIONS and held_signatures:
        raise ValueError(f"condition {condition!r} takes no held_signatures")
    if condition == SHUFFLED and not shuffled_payloads:
        raise ValueError(
            "the shuffled condition needs non-empty shuffled_payloads (the donor "
            "bundle's ours payload, picked by shuffled_condition.select_donor)"
        )
    if condition == SHUFFLED and shuffled_donor is None:
        raise ValueError(
            "the shuffled condition needs shuffled_donor (the selection provenance "
            "record) so analysis can verify the placebo's irrelevance"
        )
    if shuffled_donor is not None and shuffled_donor.work_id != bundle.work_id:
        raise ValueError(
            f"shuffled_donor records recipient {shuffled_donor.work_id!r}, "
            f"but the bundle is {bundle.work_id!r}"
        )
    if condition != SHUFFLED and (shuffled_payloads or shuffled_donor is not None):
        raise ValueError(f"condition {condition!r} takes no shuffled donor payload")
    if condition == RAW_TRAJECTORY and raw_transcript is None:
        raise ValueError(
            f"the {RAW_TRAJECTORY!r} condition needs raw_transcript (the bundle's raw trace)"
        )
    if condition == FULL_CONTEXT and not in_scope_payloads:
        raise ValueError(
            f"the {FULL_CONTEXT!r} condition needs non-empty in_scope_payloads "
            "(the LOO-bounded in-scope prior work to inject)"
        )
    if condition != RAW_TRAJECTORY and raw_transcript is not None:
        raise ValueError(f"condition {condition!r} takes no raw_transcript")
    if condition != FULL_CONTEXT and in_scope_payloads:
        raise ValueError(f"condition {condition!r} takes no in_scope_payloads")
    if condition in CLEAN_CONDITIONS:
        assert_strip_disjoint_from_gold(bundle)
    clone = rig_repos.get(bundle.rig)
    if clone is None:
        raise RuntimeError(
            f"no local clone mapped for rig {bundle.rig!r} (known rigs: {sorted(rig_repos)})"
        )

    instruction = probe_instruction(bundle)
    task_toml = _task_toml(bundle, condition, network, donor=shuffled_donor)
    injected: dict[str, str] | None = None
    control_truncation: PayloadTruncation | None = None
    if condition == "oracle":
        injected = {"oracle-files": oracle_context_payload(bundle)}
    elif condition in OURS_CONDITIONS:
        injected = dict(ours_payloads or ())  # non-empty: guarded above
    elif condition == SHUFFLED:
        injected = dict(shuffled_payloads or ())  # non-empty: guarded above
    elif condition == RAW_TRAJECTORY:
        payload = raw_trajectory_payload(bundle, raw_transcript or "", max_chars=control_max_chars)
        injected = {RAW_TRAJECTORY: payload.text}
        control_truncation = payload.truncation
    elif condition == FULL_CONTEXT:
        payload = full_context_payload(bundle, in_scope_payloads or {}, max_chars=control_max_chars)
        injected = {FULL_CONTEXT: payload.text}
        control_truncation = payload.truncation
    agent_readable = {"instruction.md": instruction, "task.toml": task_toml}
    if injected:
        agent_readable["memory/MEMORY.md"] = "\n".join(injected.values())
    assert_probe_task_clean(agent_readable, bundle)

    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text(task_toml, encoding="utf-8")
    (task_dir / "instruction.md").write_text(instruction, encoding="utf-8")
    reconstruct_env(
        task_dir,
        repo=clone,
        commit=bundle.env.base_commit,
        base_image=bundle.env.base_image,
        runner=runner,
    )
    if condition in CLEAN_CONDITIONS:
        _strip_native_memory(task_dir)
    if injected:
        memory_file = inject_context(task_dir, injected, outcome_labels=probe_leak_labels(bundle))
        _bake_memory_into_env(task_dir, memory_file)
        # Relocate CLAUDE_CONFIG_DIR so the agent's native-memory block reads the file baked
        # at NATIVE_MEMORY_PATH. Carried beside the task (never in the image), applied by
        # `harbor_stream_exec`; injected conditions only, so none/none-clean/builtin keep
        # Harbor's default config dir unchanged (`agent_memory`).
        (task_dir / AGENT_ENV_FILENAME).write_text(
            json.dumps(dict(AGENT_MEMORY_ENV), indent=2) + "\n", encoding="utf-8"
        )
    # Truncation of a control payload is persisted, never silent (premortem lens 5):
    # a reader of the task dir sees exactly how much of the source was dropped.
    if control_truncation is not None and control_truncation.truncated:
        (task_dir / "truncation.json").write_text(
            control_truncation.model_dump_json(indent=2), encoding="utf-8"
        )
    # The donor selection is the shuffled run's irrelevance provenance (mem-hhto):
    # which bundle's payload was injected, its repo, and the volume-match accounting.
    if shuffled_donor is not None:
        (task_dir / "shuffled-donor.json").write_text(
            shuffled_donor.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    # H3 parity covariate for the ours-family payloads (mem-tnyo): recorded run
    # provenance (task-dir root, never in the image), not a guard -- see
    # `write_signature_overlap` for why a hard guard is wrong for these payloads.
    if condition in OURS_CONDITIONS and held_signatures:
        write_signature_overlap(
            task_dir,
            condition=condition,
            trigger=CONDITION_TRIGGER[condition],
            payloads=dict(ours_payloads or ()),
            signatures=list(held_signatures),
        )
    return task_dir


# --- execution (mirrors base_rate_spike's harbor path) -------------------------------


def load_stream(job_dir: Path) -> str:
    """The run's raw Claude Code stream-json transcript from a finished job dir.

    The probe needs the RAW stream (mutation calls + usage events), not
    `harvest_job_dir`'s projected transcript -- so it reads ``claude-code.txt``
    directly (the reliable source: Harbor skips the ATIF conversion on a normal
    completed run, see `harbor_exec.harvest_job_dir`)."""
    stream = _locate_one(job_dir, "*/agent/claude-code.txt")
    if stream is None:
        raise RuntimeError(
            f"no */agent/claude-code.txt under {job_dir} -- the run left no stream transcript"
        )
    return stream.read_text(encoding="utf-8")


class EmptyRunError(RuntimeError):
    """A probe run that never did real work. An auth / usage-limit failure returns a
    one-turn transcript with all-zero usage (and an ``is_error`` result event), which
    `score_probe_direct` would otherwise persist as a legitimate ``0.0`` -- silently,
    and resumability would then skip it forever. The gate must treat it as a FAILURE:
    write NO result file (so a rerun re-executes it) and log loudly, never a score of
    zero (mem-75t.7.6 run incident, 2026-06-11)."""


class MemoryNotConsumedError(RuntimeError):
    """A memory-injected run whose agent never READ the injected memory -- the arm
    silently degenerated to ``none`` on the input side (trace-explorer audit 2026-07-05:
    0/50 memory-bearing runs consumed the injected file; the agent checked its own empty
    native-memory dir and proceeded). Scoring such a run as a memory-arm data point is
    the exact invalidity the audit found, so the gate writes NO result and logs loudly.
    Unlike `EmptyRunError` this does NOT cascade -- it re-runs on resume (the agent gets
    another chance), so the batch skips the leg rather than aborting."""

    def __init__(self, work_id: str, condition: str, files_read: Sequence[str]) -> None:
        self.work_id = work_id
        self.condition = condition
        self.files_read = tuple(files_read)
        # Surface only WRONG memory paths (e.g. the empty native dir the agent used to
        # check) -- listing every source file it opened would just be noise.
        wrong_memory = [
            p for p in files_read if p not in DELIVERED_MEMORY_PATHS and "MEMORY.md" in p
        ]
        detail = f"; agent instead read memory at {wrong_memory}" if wrong_memory else ""
        super().__init__(
            f"{work_id} [{condition}]: injected memory never consumed -- the memory header "
            f"{MEMORY_HEADER!r} never appeared in the transcript and no delivered path "
            f"{list(DELIVERED_MEMORY_PATHS)} was read{detail}"
        )


def _init_memory_paths(stream: str) -> list[str]:
    """The paths Claude Code auto-loaded native memory from, read off the stream's
    ``system``/``init`` event ``memory_paths`` field -- a ``{label: path}`` map, e.g.
    ``{"auto": "/agent-memory/projects/-app/memory/"}``. Empty when there is no init event
    or it reports no memory paths. Mirrors `assert_run_pins`' init-event scan (skips
    non-init system events like ``thinking_tokens``)."""
    for line in stream.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, Mapping) or event.get("type") != "system":
            continue
        if event.get("subtype") != "init":
            continue
        paths = event.get("memory_paths")
        return (
            [v for v in paths.values() if isinstance(v, str)] if isinstance(paths, Mapping) else []
        )
    return []


def assert_memory_consumed(stream: str, *, work_id: str, condition: str) -> None:
    """Raise `MemoryNotConsumedError` unless the run's ``stream`` shows the injected memory
    reached the agent's context. Three mechanical signals, any sufficient:

    - Claude Code's ``system``/``init`` event lists a ``memory_paths`` auto-load whose dir is
      the relocated native path (`path_covers_native_memory`) -- CC's native-memory is
      pointed at our baked dir, so it auto-loads whatever is there. This is the PRIMARY
      signal for the real relocated-config run, whose auto-load is otherwise SILENT (content
      never reaches the stdout stream -- no header echo, no ``Read`` tool call; confirmed on
      CLI 2.1.201). It proves the RELOCATION took effect (the ``extra_env`` override reached
      the agent), NOT that content was present: ``memory_paths`` is content-independent (same
      field whether the dir holds a file or is empty). Content is guaranteed on the other
      side of the delivery -- `_bake_memory_into_env` refuses to bake an empty/headerless
      native file -- so relocation-active + non-empty-bake together put the memory in
      context; or
    - the render header `MEMORY_HEADER` appears anywhere in the raw transcript -- it heads
      every injected file, so a visible ``cat``/``Read`` observation surfaces it (the header
      carries no JSON-special chars, so it matches verbatim inside the escaped stream); or
    - a structured `Read` tool call targeted a delivered memory path -- covers a read whose
      observation the transcript elided.

    The failure mode (relocation did NOT take effect -> ``memory_paths`` points at CC's
    default /logs dir, which the runtime mount leaves empty -> the agent gets nothing and
    reads no delivered path) produces none of these, so it correctly fails. Uniform across
    conditions (no per-payload fingerprint, so oracle's file-path payloads cannot
    false-pass). ZFC-clean: init-event path membership + substring presence + a path-set
    membership test, no semantic judgment."""
    if any(path_covers_native_memory(p) for p in _init_memory_paths(stream)):
        return
    if MEMORY_HEADER in stream:
        return
    files_read = project_claude_stream(stream)["files_read"]
    if set(files_read) & set(DELIVERED_MEMORY_PATHS):
        return
    raise MemoryNotConsumedError(work_id, condition, files_read)


def detect_run_failure(stream: str) -> str | None:
    """Return a human-readable reason when ``stream`` is a dead run, else ``None``.

    Two independent marks, either sufficient (the 2026-06-11 incident carried both):
    the terminal ``result`` event flags ``is_error`` / carries an ``api_error_status``
    (the agent never reached the model -- e.g. a 401 on an expired OAuth token), or the
    transcript bills ZERO output tokens (a genuine run always bills output for its
    attempt; zero means nothing ran). Turn count alone is NOT the test -- a short but
    real run can be a single turn -- so a billed one-turn run is never falsely failed."""
    for line in stream.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, Mapping) or event.get("type") != "result":
            continue
        if event.get("is_error"):
            status = event.get("api_error_status")
            detail = f" (api_error_status={status})" if status else ""
            reason = str(event.get("result") or "agent reported is_error").strip()
            return f"agent run errored{detail}: {reason[:200]}"
    efficiency = extract_efficiency(stream)
    if (efficiency.output_tokens or 0) == 0:
        return (
            f"agent run billed zero output tokens (turns={efficiency.turns}, "
            f"input_tokens={efficiency.input_tokens}) -- no work performed"
        )
    return None


class PinMismatchError(RuntimeError):
    """A run executed on a different model or claude-code CLI version than the
    arm it must stay comparable with (mem-p3w: the cached builtin runs) -- a
    silent instrument confound. The caller must persist NO result for such a run
    (the `EmptyRunError` discipline). The stale job dir is NOT removed on this
    path -- the driver's startup scrub (`scrub_unfinished_jobs`) removes it on
    the next invocation, so harbor re-runs instead of re-harvesting the drifted
    transcript."""


def assert_run_pins(stream: str, *, model: str, cli_version: str) -> None:
    """Assert the run's stream init event matches the pinned model + CLI version.

    Harbor installs the claude CLI fresh in every container, so an unpinned run
    silently drifts to latest -- across days that is a different instrument than
    the cached arm it is paired against. Raises `PinMismatchError` on drift or
    when the stream carries no init event to verify."""
    for line in stream.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, Mapping) or event.get("type") != "system":
            continue
        # Only the init event carries model/version; other system events (e.g.
        # thinking_tokens) would otherwise read as None != pinned and false-fail.
        if event.get("subtype") != "init":
            continue
        mismatches = []
        if event.get("model") != model:
            mismatches.append(f"model {event.get('model')!r} != pinned {model!r}")
        if event.get("claude_code_version") != cli_version:
            mismatches.append(
                f"cli version {event.get('claude_code_version')!r} != pinned {cli_version!r}"
            )
        if mismatches:
            raise PinMismatchError("; ".join(mismatches))
        return
    raise PinMismatchError("no system init event in stream -- cannot verify run pins")


def _resolve_agent_env(task_dir: Path) -> dict[str, str] | None:
    """The agent env override a build wrote beside the task (`AGENT_ENV_FILENAME`), or
    None. Injected conditions carry the ``CLAUDE_CONFIG_DIR`` relocation here; other
    conditions have no sidecar and run with Harbor's default. A malformed sidecar raises
    -- a corrupt override must not silently fall back to the wrong config dir."""
    sidecar = task_dir / AGENT_ENV_FILENAME
    if not sidecar.exists():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"malformed {AGENT_ENV_FILENAME} at {sidecar}: invalid JSON ({exc})"
        ) from exc
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise ValueError(f"malformed {AGENT_ENV_FILENAME} at {sidecar}: expected str->str map")
    return data


def harbor_stream_exec(
    task_dir: Path,
    *,
    jobs_dir: Path | None = None,
    job_name: str | None = None,
    model: str | None = None,
    harbor_bin: str = "harbor",
    timeout_sec: float | None = None,
    agent_version: str | None = None,
) -> str:
    """Production `StreamExec`: ``harbor run`` one task (the spike's exact invocation
    path -- OAuth token from the Harbor process env, jobs-dir layout, ``-q -y``),
    then return the raw stream transcript. Requires Docker + the subscription.
    ``agent_version`` pins the in-container claude CLI install (mem-p3w parity).

    A per-task `AGENT_ENV_FILENAME` sidecar (injected conditions) relocates
    ``CLAUDE_CONFIG_DIR`` so the agent's native-memory block reads the injected file."""
    jobs_dir = jobs_dir or (task_dir.parent / "_harbor_jobs")
    job_name = job_name or task_dir.name
    job_dir = run_harbor_job(
        task_dir,
        jobs_dir=jobs_dir,
        job_name=job_name,
        model=model,
        harbor_bin=harbor_bin,
        timeout_sec=timeout_sec,
        agent_version=agent_version,
        agent_env=_resolve_agent_env(task_dir),
    )
    return load_stream(job_dir)


def pinned_stream_exec(
    *, jobs_dir: Path, model: str, cli_version: str, timeout_sec: float | None = None
) -> StreamExec:
    """A `StreamExec` pinned to one instrument (model + in-container CLI version),
    shared by the grid/probe drivers so every arm and rep stays comparable. Dead
    runs (401 / usage-limit / zero-output) are classified FIRST -- their streams
    carry an init event without model fields, which would otherwise raise a
    misleading `PinMismatchError` instead of the batch-handled `EmptyRunError` --
    and pin drift raises before the batch can persist a result."""

    def exec_stream(task_dir: Path) -> str:
        stream = harbor_stream_exec(
            task_dir,
            jobs_dir=jobs_dir,
            model=model,
            timeout_sec=timeout_sec,
            agent_version=cli_version,
        )
        failure = detect_run_failure(stream)
        if failure is not None:
            raise EmptyRunError(f"{task_dir.name}: {failure}")
        assert_run_pins(stream, model=model, cli_version=cli_version)
        return stream

    return exec_stream


# --- candidate harvest ----------------------------------------------------------------


def _run_git(
    clone: Path, args: Sequence[str], runner: Runner
) -> "subprocess.CompletedProcess[str]":
    return runner(["git", "-C", str(clone), *args], capture_output=True, text=True, check=False)


def _add_worktree(clone: Path, commit: str, dest: Path, runner: Runner) -> None:
    completed = _run_git(clone, ["worktree", "add", "--detach", str(dest), commit], runner)
    if completed.returncode != 0:
        raise RuntimeError(
            f"git worktree add {commit[:12]} in {clone} failed "
            f"(exit {completed.returncode}): {completed.stderr.strip()}"
        )


def _remove_worktree(clone: Path, dest: Path, runner: Runner) -> None:
    """Force-remove + prune, with an rmtree backstop for a dir git no longer tracks
    (the assemble_batch cleanup pattern)."""
    _run_git(clone, ["worktree", "remove", "--force", str(dest)], runner)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    _run_git(clone, ["worktree", "prune"], runner)


def stale_probe_worktrees(
    clone: Path, *, runner: Runner = subprocess.run, prefix: str = _WORKTREE_PREFIX
) -> tuple[str, ...]:
    """Any ``prefix``-named worktree paths the clone still lists -- the CLI's
    exit-sweep input (must be empty after a run). Defaults to the probe's own
    prefix; the grid sweeps its repro worktrees through the same mechanism."""
    completed = _run_git(clone, ["worktree", "list", "--porcelain"], runner)
    if completed.returncode != 0:
        raise RuntimeError(f"git worktree list in {clone} failed: {completed.stderr.strip()}")
    return tuple(
        line.removeprefix("worktree ")
        for line in completed.stdout.splitlines()
        # Match on the path's BASENAME -- a clone whose own path merely contains
        # the prefix must never be swept (it would force-remove a real checkout).
        if line.startswith("worktree ")
        and Path(line.removeprefix("worktree ")).name.startswith(prefix)
    )


def sweep_probe_worktrees(
    clone: Path, *, runner: Runner = subprocess.run, prefix: str = _WORKTREE_PREFIX
) -> None:
    """Remove every leftover ``prefix`` worktree in ``clone``; raise if any survives."""
    for stale in stale_probe_worktrees(clone, runner=runner, prefix=prefix):
        _remove_worktree(clone, Path(stale), runner)
    remaining = stale_probe_worktrees(clone, runner=runner, prefix=prefix)
    if remaining:
        raise RuntimeError(f"{prefix} worktrees left in {clone} after sweep: {remaining}")


def harvest_candidate(
    run_transcript: str,
    bundle: TaskBundle,
    *,
    clone: Path,
    runner: Runner = subprocess.run,
    worktree_root: Path = Path("/tmp"),
) -> ReplayResult:
    """The fresh run's candidate diff, in the gold diff's coordinate space.

    Parses the run's mutation calls and replays them against a FRESH detached
    checkout of ``repo@base_commit`` (the same machinery as the gold diff),
    rebasing from the container workspace root (`CONTAINER_WORKDIR`) onto the
    checkout. The checkout is created and removed per call (try/finally) -- no
    path leaves it behind. Returns the full `ReplayResult` (per-file diffs + the
    classified replay outcome stats)."""
    calls = parse_mutation_calls(run_transcript)
    worktree = worktree_root / f"{_WORKTREE_PREFIX}{bundle.work_id}-{uuid.uuid4().hex[:8]}"
    _add_worktree(clone, bundle.env.base_commit, worktree, runner)
    try:
        return replay_calls(calls, checkout_dir=worktree, work_dir=CONTAINER_WORKDIR, runner=runner)
    finally:
        _remove_worktree(clone, worktree, runner)


# --- scoring ---------------------------------------------------------------------------


class ProbeConditionResult(BaseModel):
    """One (bundle, condition) run's full readout: the direct score vs gold, the
    efficiency axis, and the candidate-replay outcome stats."""

    model_config = ConfigDict(frozen=True)

    work_id: str
    condition: str
    score: ProbeDirectScore
    efficiency: ProbeEfficiency
    candidate_files: tuple[str, ...]
    replay_applied: int = Field(ge=0)
    replay_total: int = Field(ge=0)
    replay_outside_work_dir: int = Field(ge=0)

    def metrics(self) -> dict[str, float | None]:
        """The gate's per-condition metric vector (summary + gap arithmetic input).
        Token metrics are None when the transcript carried no usage data."""
        return {
            "combined": self.score.combined,
            "file_f1": self.score.file_f1,
            "hunk_overlap": self.score.hunk_overlap,
            "input_tokens": (
                None
                if self.efficiency.input_tokens is None
                else float(self.efficiency.input_tokens)
            ),
            "output_tokens": (
                None
                if self.efficiency.output_tokens is None
                else float(self.efficiency.output_tokens)
            ),
            "turns": float(self.efficiency.turns),
            "tool_calls": float(self.efficiency.tool_calls),
        }


class ProbePair(BaseModel):
    """One bundle's paired readout. ``deltas`` is oracle - none per metric (sorted
    pairs; a metric absent from either side is omitted, never imputed as 0)."""

    model_config = ConfigDict(frozen=True)

    work_id: str
    none: ProbeConditionResult
    oracle: ProbeConditionResult
    deltas: tuple[tuple[str, float], ...]


def score_condition(
    bundle: TaskBundle, condition: str, candidate: ReplayResult, run_transcript: str
) -> ProbeConditionResult:
    """Score one condition's harvested candidate against the bundle's gold diff,
    plus the transcript's efficiency axis."""
    return ProbeConditionResult(
        work_id=bundle.work_id,
        condition=condition,
        score=score_probe_direct(candidate.diff_by_file(), bundle.output.diff_by_file()),
        efficiency=extract_efficiency(run_transcript),
        candidate_files=tuple(sorted(candidate.diff_by_file())),
        replay_applied=sum(1 for c in candidate.calls if c.outcome is ReplayOutcome.APPLIED),
        replay_total=len(candidate.calls),
        replay_outside_work_dir=sum(
            1 for c in candidate.calls if c.outcome is ReplayOutcome.OUTSIDE_WORK_DIR
        ),
    )


def paired_deltas(
    none_metrics: Mapping[str, float | None], oracle_metrics: Mapping[str, float | None]
) -> tuple[tuple[str, float], ...]:
    """Per-metric (oracle - none) deltas; a metric absent (None) on either side is
    omitted, never imputed. Shared by the gate's `score_pair` and the ablation
    grid's `pair_grid`."""
    deltas: list[tuple[str, float]] = []
    for metric, none_value in sorted(none_metrics.items()):
        oracle_value = oracle_metrics.get(metric)
        if none_value is None or oracle_value is None:
            continue
        deltas.append((metric, oracle_value - none_value))
    return tuple(deltas)


def score_pair(none: ProbeConditionResult, oracle: ProbeConditionResult) -> ProbePair:
    """Pair one bundle's two condition results and compute the per-metric deltas
    (oracle - none). Mismatched work_ids or conditions are caller bugs -- raise."""
    if none.work_id != oracle.work_id:
        raise ValueError(f"work_id mismatch: {none.work_id!r} vs {oracle.work_id!r}")
    if none.condition != "none" or oracle.condition != "oracle":
        raise ValueError(
            f"score_pair needs (none, oracle), got ({none.condition!r}, {oracle.condition!r})"
        )
    deltas = paired_deltas(none.metrics(), oracle.metrics())
    return ProbePair(work_id=none.work_id, none=none, oracle=oracle, deltas=deltas)


def run_probe(
    bundle: TaskBundle,
    condition: str,
    task_dir: Path,
    *,
    clone: Path,
    exec_stream: StreamExec = harbor_stream_exec,
    runner: Runner = subprocess.run,
    worktree_root: Path = Path("/tmp"),
) -> ProbeConditionResult:
    """Execute ONE prepared (bundle, condition) task and score it: run the agent
    (`exec_stream` -- production `harbor_stream_exec`, injectable for tests),
    harvest the candidate diff symmetrically with the gold, score the pair leg.

    A dead run (`detect_run_failure` -- auth/limit error or zero-output transcript)
    raises `EmptyRunError` BEFORE the candidate harvest, so the caller writes no
    result file and the run re-executes on resume rather than scoring a silent 0.

    A memory-injected condition additionally passes the consumption gate
    (`assert_memory_consumed`): the injected file (``<task_dir>/memory/MEMORY.md``,
    present iff memory was injected) must show up as read in the transcript, else
    `MemoryNotConsumedError` -- the arm degenerated to ``none`` and must not be scored."""
    stream = exec_stream(task_dir)
    failure = detect_run_failure(stream)
    if failure is not None:
        raise EmptyRunError(f"{bundle.work_id} [{condition}]: {failure}")
    # The injected file is present iff this condition injected memory (build_probe_task
    # writes it only then), so its existence is the exact gate trigger.
    if (task_dir / MEMORY_FILENAME).exists():
        assert_memory_consumed(stream, work_id=bundle.work_id, condition=condition)
    candidate = harvest_candidate(
        stream, bundle, clone=clone, runner=runner, worktree_root=worktree_root
    )
    return score_condition(bundle, condition, candidate, stream)


# --- summary / gap arithmetic ------------------------------------------------------------


def metric_gap_stats(delta_maps: Sequence[Mapping[str, float]]) -> dict[str, Any]:
    """Per-metric gap stats over per-bundle delta maps: raw deltas, mean/median,
    and the count where oracle beat none. Shared by the gate's `summarize_pairs`
    and the ablation grid's `summarize_grid`."""
    gaps: dict[str, Any] = {}
    for metric in sorted({metric for deltas in delta_maps for metric in deltas}):
        deltas = [d[metric] for d in delta_maps if metric in d]
        gaps[metric] = {
            "deltas": deltas,
            "mean_delta": fmean(deltas),
            "median_delta": median(deltas),
            "n_oracle_gt_none": sum(1 for d in deltas if d > 0),
            "n_pairs": len(deltas),
        }
    return gaps


def summarize_pairs(pairs: Sequence[ProbePair]) -> dict[str, Any]:
    """The gate's DATA product: per-bundle paired scores + per-metric gap stats
    (deltas, mean/median, count where oracle > none) and the mechanical
    ``gap_positive_majority`` provisional flag (strict majority of bundles with a
    positive ``combined`` delta). The authored GO/NO-GO verdict is the
    orchestrator's, written elsewhere -- never computed here."""
    if not pairs:
        raise ValueError("summarize_pairs needs at least one (none, oracle) pair")
    delta_maps = [dict(pair.deltas) for pair in pairs]
    per_bundle = [
        {
            "work_id": pair.work_id,
            "none": pair.none.metrics(),
            "oracle": pair.oracle.metrics(),
            "deltas": deltas,
        }
        for pair, deltas in zip(pairs, delta_maps, strict=True)
    ]
    combined_positive = sum(1 for deltas in delta_maps if deltas.get("combined", 0.0) > 0)
    return {
        "n_pairs": len(pairs),
        "per_bundle": per_bundle,
        "gaps": metric_gap_stats(delta_maps),
        "gap_positive_majority": combined_positive * 2 > len(pairs),
    }
