"""§11 shape well-formedness gate (mem-rk41.2) — a corpus VALIDITY gate.

Peer of ``memory_necessity_gate``: both are construct-validity preconditions run
over GENERATED tool-requiring tasks, and both flag construction bugs rather than
render an ours-vs-builtin verdict. Necessity asks "does this task need memory at
all?"; this gate asks the narrower "is the generated tool-requiring shape
WELL-FORMED?" — i.e. free of the construction bugs that make its retrieval signal
untrustworthy.

Why this is a well-formedness check and NOT an arm-discrimination claim
----------------------------------------------------------------------
On a well-formed tool-requiring sequence the reward path is pure-Python and
seed-authored (NeMo prose never enters reward), so ``retrieval_discrimination_gate``
is ~100% by construction — the id-exact quality arm always beats the token-overlap
naive arm at the goal. A PASS therefore measures nothing new. A FAILURE, by
contrast, is diagnostic: it means the shape does NOT cleanly separate quality from
naive at the goal, which on a construction that is supposed to separate them can
only be a MALFORMED task. So we aggregate the pass/fail as "shape well-formedness",
never as "discriminates arms" (architect C1). The literal ours-vs-builtin verdict
stays the paid Harbor path (mem-lq2w / rk41.3), out of scope here.

The M1 truncation short-circuit
-------------------------------
One construction bug the discrimination gate CANNOT catch on its own is M1:
``facts_per_task > top_k``. The quality arm (``filesystem``) is id-exact and NOT
top-k bounded, so it surfaces every requested fact regardless; the naive arm
(``lexical``) truncates at ``top_k``. When the task needs more facts than the
retriever can return, the naive arm fails from TRUNCATION, not from surfacing a
stale value — yet the discrimination gate would still read quality>naive and
spuriously ACCEPT the task as discriminating. So M1 is a purely STRUCTURAL
pre-check: if ``facts_per_task > top_k`` we declare the shape malformed WITHOUT
running the arms, because their verdict would be confounded and misleading.

No model is called — ``retrieval_discrimination_gate`` runs the reference
``ScriptedAgent``, so this gate is deterministic and CI-safe.
"""

from __future__ import annotations

from dataclasses import dataclass

from membench.generators.retrieval_discrimination_gate import (
    DiscriminationResult,
    retrieval_discrimination_gate,
)
from membench.memory_systems.lexical_system import DEFAULT_TOP_K
from membench.schemas.sequence import BenchmarkSequence


@dataclass(frozen=True)
class WellformednessResult:
    """One generated sequence's well-formedness verdict.

    ``wellformed`` is the corpus-validity signal: true iff the shape is free of the
    construction bugs this gate detects. ``discrimination`` carries the underlying
    ``retrieval_discrimination_gate`` result when it was run, and is ``None`` when any
    structural pre-check short-circuited the gate — an invalid ``facts_per_task``
    boundary or the M1 truncation check (the arms were deliberately NOT run because
    their verdict would be confounded or meaningless). ``reason`` explains the
    verdict."""

    sequence_id: str
    wellformed: bool
    reason: str
    discrimination: DiscriminationResult | None


def shape_wellformedness_gate(
    seq: BenchmarkSequence,
    *,
    facts_per_task: int,
    top_k: int = DEFAULT_TOP_K,
) -> WellformednessResult:
    """Judge whether a generated tool-requiring ``seq`` is WELL-FORMED (mem-rk41.2).

    Never raises for an invalid ``top_k``/``facts_per_task`` boundary (mem-03acq) — a
    bad boundary is a malformed shape like any other, not an exception. This does NOT
    cover every possible exception: check 2 still runs ``retrieval_discrimination_gate``
    -> ``run_sequence``, whose own fail-fast checks (e.g. a bad supersession ordering
    in ``seq``) deliberately keep raising — those are real construction bugs unrelated
    to this boundary, not something this gate should swallow.

    Three checks, cheapest first:

    0. **``facts_per_task`` validation** — must be >= 1. A ``top_k <= 0`` needs no
       twin check here: M1 below (``facts_per_task > top_k``) already catches it
       for any ``facts_per_task >= 1``, since that trivially holds once ``top_k``
       is non-positive. Declare malformed WITHOUT running the arms.
    1. **M1 structural pre-check** — if ``facts_per_task > top_k`` the naive arm would
       fail from truncation rather than staleness, so the discrimination signal is
       confounded (this is also where an invalid ``top_k <= 0`` surfaces). Declare
       malformed WITHOUT running the arms.
    2. **Discrimination check** — otherwise run ``retrieval_discrimination_gate``,
       threading this same ``top_k`` into the naive arm's construction so the check
       and the arm it is checking never disagree about retrieval width. The shape is
       well-formed iff the quality arm cleanly beats the naive arm at the goal
       (``accepted``). A rejection here flags a construction bug, not an arm verdict.
    """
    if facts_per_task < 1:
        return WellformednessResult(
            sequence_id=seq.sequence_id,
            wellformed=False,
            reason=(
                f"invalid boundary: facts_per_task={facts_per_task} (must be >= 1) "
                "— malformed by construction, arms not run"
            ),
            discrimination=None,
        )

    if facts_per_task > top_k:
        reason = (
            f"M1 truncation: facts_per_task {facts_per_task} > top_k {top_k}; the naive "
            f"arm would fail from retrieval truncation, not staleness, so the "
            f"discrimination signal is confounded — malformed (arms not run)"
        )
        return WellformednessResult(
            sequence_id=seq.sequence_id,
            wellformed=False,
            reason=reason,
            discrimination=None,
        )

    result = retrieval_discrimination_gate(seq, top_k=top_k)
    reason = (
        f"shape separates quality from naive at the goal ({result.reason})"
        if result.accepted
        else (
            f"shape does NOT cleanly separate quality from naive at the goal "
            f"({result.reason}) — on a construction meant to separate them this is a "
            f"MALFORMED task, not an arm verdict"
        )
    )
    return WellformednessResult(
        sequence_id=seq.sequence_id,
        wellformed=result.accepted,
        reason=reason,
        discrimination=result,
    )
