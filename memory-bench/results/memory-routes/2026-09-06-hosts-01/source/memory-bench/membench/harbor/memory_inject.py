"""Per-rung memory CONTENT injection into an ablation task dir (mem-apg.3d).

mem-apg.2's `WorkRecordLadderAdapter` emits the per-rung information SPEC -- which
memory each rung MAY access -- but writes no memory content (architect-H4 gap). This
module closes it: given a rung's resolved memory payloads, it writes the actual
agent-readable memory file into the task dir.

The payloads themselves are resolved by the driver (`grid.run_grid`), which calls
the `ours` arm under the task's LOO boundary (D6) and supplies the oracle's
ground-truth prior. This module is pure mechanism (ZFC): it writes IO and runs the
leak guards; it makes no retrieval and no semantic judgment.

Two guards run before any write, so a leak aborts with nothing on disk:

- `assert_no_outcome_leak` (the mem-apg.1 task-construction guard) -- no high-entropy
  outcome identifier (pr / commit_sha / base_commit) may reach agent-readable text.
- the `oracle`-only H3 self-leak guard -- the oracle payload must NOT contain the
  held-out bead's OWN `trace_error` signature (full or relaxed), because that
  signature is exactly the answer the deterministic scorer (mem-apg.3a) checks.
  Leaking it would let the agent trivially "avoid" the failure it was handed.

H3 parity for the OURS payloads (mem-tnyo): the same relaxed-signature scan runs
over the retrieval payloads too, but as a recorded COVARIATE
(`signature-overlap.json`), never a hard guard -- see `write_signature_overlap`
for the guard-vs-covariate justification.

`builtin` / `ours+builtin` depend on the agent's opaque built-in memory (the paid
Harbor path owned by mem-whi) and are DEFERRED -- injecting them is not this bead's
job, so they raise `DeferredRungError` rather than silently writing nothing.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from membench.grading import (
    TraceErrorRef,
    assert_no_outcome_leak,
    relaxed_signature,
)

# Where a rung's memory content lands inside its task dir. A single Markdown file
# under a `memory/` area, mirroring the agent's own MEMORY.md convention so the
# injected prior reads the same as a built-in memory would.
MEMORY_FILENAME = "memory/MEMORY.md"

# The fixed first line of every rendered memory file. Distinctive and uniform across
# all injected conditions, so its presence in an agent transcript is a reliable
# consumption signal (`probe_gate.assert_memory_consumed`): a fresh agent never emits
# this verbatim unless a cat/Read/auto-load surfaced the injected file.
MEMORY_HEADER = "# Prior-session memory"

# Rungs whose memory is the agent's opaque built-in store -- owned by mem-whi's
# paid Harbor path, not constructible here.
DEFERRED_RUNGS = ("builtin", "ours+builtin")

# Rungs this module can inject today (the runnable subset of the ladder).
# `vector-rag` is the Sakana recall-ladder rung-2 (mem-do8r): a semantic-arm
# retrieval whose payloads are resolved by the driver (e.g. the `nemo-embed` arm)
# and injected through the SAME leak-guard path as `ours`, so the two retrieval
# rungs differ only in recall policy, never in how their memory reaches the agent.
RUNNABLE_RUNGS = ("none", "vector-rag", "ours", "oracle")

# The full ladder vocabulary (grading/ablation.py's DEFAULT_RUNGS draws from it).
KNOWN_RUNGS = RUNNABLE_RUNGS + DEFERRED_RUNGS

# The two retrieval rungs inject identically -- inject_context + the H3 signature-
# overlap covariate -- and differ ONLY in recall policy: which payloads reach the
# agent, and the `trigger` label recording how the query was formed (`vector-rag`
# retrieves by query text; `ours` replays from the held record, an oracle trigger).
# `oracle` is NOT a peer: it injects one curated payload under a hard self-leak guard.
_RETRIEVAL_TRIGGERS = {"vector-rag": "query_text", "ours": "oracle"}


def validate_rungs(rungs: Sequence[str]) -> tuple[str, ...]:
    """Validate a rung list against the ladder vocabulary BEFORE any execution.

    Raises ValueError naming every unknown rung -- a typo'd ladder must fail at
    config/load time, not mid-sweep after earlier rungs have already burned agent
    runs. Returns the deferred subset (in ladder order) so the caller can surface
    what will be skipped instead of discovering it from a thinner result."""
    unknown = [rung for rung in rungs if rung not in KNOWN_RUNGS]
    if unknown:
        raise ValueError(
            f"unknown ablation rung(s) {unknown!r}; known rungs: {list(KNOWN_RUNGS)!r}"
        )
    return tuple(rung for rung in rungs if rung in DEFERRED_RUNGS)


class DeferredRungError(ValueError):
    """Raised when a rung's memory is owned by another bead (builtin / ours+builtin).

    Distinct from an unknown-rung error so the driver can SKIP these rungs
    deliberately instead of treating them as a config typo."""


class OracleSelfLeakError(AssertionError):
    """Raised when the oracle payload contains the held-out bead's own trace_error
    signature (full or relaxed) -- the answer the scorer checks (architect H3).

    A validity bug that must fail the run loudly, never be silently stripped."""

    def __init__(self, offenders: list[str]) -> None:
        self.offenders = offenders
        detail = ", ".join(repr(sig) for sig in offenders)
        super().__init__(
            f"oracle payload leaks the held bead's own trace_error signature: {detail}"
        )


def held_signatures(held_errors: Sequence[TraceErrorRef]) -> tuple[str, ...]:
    """Every held error's full AND relaxed signature, deduplicated in error
    order. Both keys matter because the scorer's avoid-axis keys on the RELAXED
    signature (`relaxed_signature`), so leaking only the relaxed key still hands
    the agent the answer."""
    out: list[str] = []
    for error in held_errors:
        for signature in (error.signature, relaxed_signature(error)):
            if signature not in out:
                out.append(signature)
    return tuple(out)


def signature_overlap(payload: str, signatures: Iterable[str]) -> tuple[str, ...]:
    """Which of `signatures` appear verbatim in `payload` -- the mechanical,
    case-insensitive scan (mirroring `assert_no_outcome_leak`) shared by the
    oracle H3 guard (which raises on any hit) and the ours-payload covariate
    (which records the hits, mem-tnyo). Deduplicated, first-seen order."""
    haystack = payload.lower()
    matched: list[str] = []
    for signature in signatures:
        if signature not in matched and signature.lower() in haystack:
            matched.append(signature)
    return tuple(matched)


def _assert_no_oracle_self_leak(payload: str, held_errors: Sequence[TraceErrorRef]) -> None:
    """Fail loud if `payload` contains any held error's full or relaxed signature."""
    offenders = list(signature_overlap(payload, held_signatures(held_errors)))
    if offenders:
        raise OracleSelfLeakError(offenders)


# Where the per-payload H3 signature-overlap covariate lands inside a task dir.
# Task-dir ROOT on purpose (the shuffled-donor.json pattern): Harbor's Docker
# build context is `environment/` only, so the file is run provenance the agent
# can never read -- writing held signatures into agent-readable text would
# itself be a leak.
SIGNATURE_OVERLAP_FILENAME = "signature-overlap.json"


def write_signature_overlap(
    task_dir: str | Path,
    *,
    condition: str,
    trigger: str,
    payloads: Mapping[str, str],
    signatures: Sequence[str],
) -> Path:
    """Persist the per-payload signature-overlap COVARIATE for an ours-family
    condition (mem-tnyo H3 parity).

    Guard-vs-covariate choice, per payload type: the ORACLE payload keeps the
    hard guard (`_assert_no_oracle_self_leak`) -- curated context must never
    carry the held signature. The OURS payloads (both the oracle-triggered and
    the issue-text-triggered condition) get this covariate instead, because a
    retrieved prior that shares the held failure signature is retrieval-v1
    WORKING AS DESIGNED (the D8 tier-1 exact-signature match is the arm's core
    mechanism); a hard guard would delete exactly the items the arm exists to
    return. Persisting the overlap lets analysis condition on it -- and compare
    overlap rates across the two triggers -- instead of silently biasing the
    arm against recurring failures."""
    record = {
        "condition": condition,
        "trigger": trigger,
        "held_signature_count": len(signatures),
        "overlap": {
            source_id: list(signature_overlap(content, signatures))
            for source_id, content in payloads.items()
        },
    }
    target = Path(task_dir) / SIGNATURE_OVERLAP_FILENAME
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return target


def _render(payloads: dict[str, str]) -> str:
    """Render id -> payload as the agent-readable memory file. One section per
    prior, keyed by its source id so the agent can cite it. An empty mapping
    yields an explicit 'no relevant prior memory' body -- the rung was tried."""
    if not payloads:
        return f"{MEMORY_HEADER}\n\nNo relevant prior memory was retrieved.\n"
    parts = [MEMORY_HEADER, ""]
    for source_id, content in payloads.items():
        parts += [f"## {source_id}", "", content, ""]
    return "\n".join(parts)


def _write(task_dir: Path, text: str) -> Path:
    target = task_dir / MEMORY_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def inject_context(
    task_dir: str | Path,
    payloads: dict[str, str],
    *,
    outcome_labels: Iterable[str] = (),
) -> Path:
    """Render + leak-check + write context payloads as the task's memory file.

    The injection MECHANISM shared by `inject_rung_memory`'s content-bearing rungs
    and the mem-75t.7.6 probe gate (`harbor.probe_gate`), which injects the cheap
    oracle-rung context (the gold-diff file list) through the same render + guard +
    write path. The leak guard runs over the RENDERED text, so a label smuggled in
    via a payload key fails just like one in a payload body."""
    text = _render(payloads)
    assert_no_outcome_leak(text, list(outcome_labels))
    return _write(Path(task_dir), text)


def inject_rung_memory(
    task_dir: str | Path,
    rung: str,
    *,
    held_errors: Sequence[TraceErrorRef],
    vector_payloads: dict[str, str] | None = None,
    ours_payloads: dict[str, str] | None = None,
    oracle_payload: str | None = None,
    outcome_labels: Iterable[str] = (),
) -> Path | None:
    """Write `rung`'s memory content into `task_dir`; return the file written.

    - `none` -> writes nothing, returns None (the stateless control).
    - `vector-rag` -> writes the semantic-arm retrieval payloads (`vector_payloads`,
      resolved by the driver from a dense-embedding arm) and records the same H3
      signature-overlap covariate as `ours` -- both are retrieval rungs, so a
      cosine-nearest prior may legitimately share the held failure signature
      (mem-tnyo): a covariate, never a guard.
    - `ours` -> writes the distilled retrieval payloads (`ours_payloads`) and
      records the H3 signature-overlap covariate (`write_signature_overlap`,
      mem-tnyo -- a covariate, not a guard: see that function's rationale).
    - `oracle` -> writes `oracle_payload`, guarded by the H3 self-leak check.
    - `builtin` / `ours+builtin` -> `DeferredRungError` (owned by mem-whi).

    Both `vector_payloads` and `ours_payloads` MUST already be bounded to the task's
    LOO boundary by the caller (retrieval-v1 excludes the held item; the semantic arm
    scopes its candidate set per trial) -- this module injects them verbatim and does
    not re-filter.

    All payloads are leak-checked for outcome labels before any write; the oracle
    rung additionally runs the self-leak guard. `held_errors` is required and must
    be non-empty (the held-out set is 'beads with >=1 trace_error' by
    construction) so the oracle guard always has the answer to protect."""
    held = list(held_errors)
    if not held:
        raise ValueError("inject_rung_memory needs at least one held error (oracle guard input)")

    task_path = Path(task_dir)
    labels = list(outcome_labels)

    if rung == "none":
        return None

    if rung in _RETRIEVAL_TRIGGERS:
        # One injection path for both retrieval rungs (H3 parity, mem-tnyo): write the
        # payloads, then record the signature-overlap COVARIATE -- a retrieved prior
        # may legitimately share the held failure signature, so overlap is recorded for
        # analysis (comparable across recall policies), never used as a guard. Recall
        # policy is the only thing that varies: the payload source and the trigger label.
        payloads = {"vector-rag": vector_payloads, "ours": ours_payloads}[rung] or {}
        target = inject_context(task_path, payloads, outcome_labels=labels)
        write_signature_overlap(
            task_path,
            condition=rung,
            trigger=_RETRIEVAL_TRIGGERS[rung],
            payloads=payloads,
            signatures=held_signatures(held),
        )
        return target

    if rung == "oracle":
        if oracle_payload is None:
            raise ValueError("oracle rung needs an oracle_payload")
        _assert_no_oracle_self_leak(oracle_payload, held)
        return inject_context(task_path, {"oracle": oracle_payload}, outcome_labels=labels)

    if rung in DEFERRED_RUNGS:
        raise DeferredRungError(
            f"rung {rung!r} depends on the agent's built-in memory (paid Harbor path, "
            "mem-whi) and is not injected here"
        )

    raise ValueError(f"unknown ablation rung {rung!r}")
