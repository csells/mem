"""mem-9q8dg — OUTCOME-SIDE necessity verification for the E1 twin corpus.

``SequenceStep.memory_necessary`` is a LABEL. A label asserting necessity is not evidence
of it, and the E1 discrimination endpoint is worthless if the two halves are not what they
say they are. This preflight measures the claim instead of trusting it: it runs the goal
leg ALONE (no establish leg, no store, no surfaced memory — the ``none`` arm) over both
halves and reads the two pass rates.

What a healthy corpus looks like:

* the UNNECESSARY half PASSES with an empty store — its goal states the value in context,
  so a memory-free agent has everything it needs;
* the NECESSARY half FAILS with an empty store — its value is an opaque token that exists
  nowhere in the prompt, so passing would mean a prompt leak (which the adapter's firewall
  forbids) or a hallucination that guessed a 12-hex-digit token.

The thresholds mirror the bead's acceptance criterion: ``unnecessary_pass_rate > 0.8`` and
``necessary_pass_rate < 0.2``.

**A dry run is not the verification.** Without ``--paid`` (the default) the runner is the
stand-in ``realagent_probe.simulated_runner`` rather than a real ``claude -p`` — an honest
memory-copying agent that writes the current values iff they appear in the prompt. It
reproduces the
predicted structure BY CONSTRUCTION and proves only that the corpus geometry and the wiring
are right — never that a real agent behaves this way. Only ``--paid`` produces evidence, and
the emitted JSON says which was run: ``mode`` and ``verified`` are always present, and
``verified`` is false on the dry path no matter how clean the numbers look.

The PAYLOAD carries the same guard, not just the exit code. It reports ``thresholds_cleared``
(the arithmetic) and ``verdict`` (what the run licenses) as separate fields, and ``verdict`` is
``"unverified"`` on the dry path however clean the rates are. The first cut emitted a single
``accepted: true`` computed from the rates alone, so a consumer reading the JSON — the obvious
use of ``--json`` — read an unrun preflight as an acceptance while only the exit status was
guarded.

And the EXIT CODE says it too, because that is the channel a CI gate actually reads. Exit 0 means
"measured and accepted" and nothing else; an unverified run exits 3 however clean its rates are, a
measured rejection exits 1, a refused spend exits 2, and a missing/empty corpus exits 4 — an
infrastructure absence must never arrive as exit 1, the code that means the corpus was MEASURED
and rejected. The first cut returned ``0 if accepted else 1`` and ignored ``verified`` entirely,
so a dry run — whose numbers the simulated runner entails — exited 0 into a gate as ACCEPT.

``empty_store_pass_rate_margin`` is named for what it is. It was ``discrimination_margin``, which
is the name of E1's primary endpoint — a CALL-rate margin, P(call | necessary) - P(call |
unnecessary) — while this field is a PASS-rate margin over an empty store. Two different
quantities under one name is a mislabelled number waiting to be reported as the endpoint.

AS OF THIS COMMIT THE PAID PATH IS UNRUN: no real ``claude -p`` turns have been spent on either
half, so AC2 is not met. The command to meet it, once spend is authorized:

    uv run python -m membench.runner.e1_necessity_preflight --paid --model <id> --repeats 5 --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from membench.runner.headless_agent import (
    ENV_OAUTH,
    REFUSE_API_KEY_SET,
    REFUSE_UNPINNED_MODEL,
    CellRecorder,
    MemoryChannel,
    a_paid_run_carries_the_metered_api_key,
    a_paid_run_needs_a_model,
)
from membench.runner.realagent_probe import run_arm
from membench.runner.toolreq_corpus import load_twin_corpus
from membench.runner.toolreq_realagent import (
    DEFAULT_CORPUS,
    VARIANT_NECESSARY,
    VARIANT_UNNECESSARY,
    ToolReqRealAgentTask,
)

# The arm this preflight runs: empty surfaced memory, i.e. the empty-store floor. Necessity is
# a property measured against NO memory; any other arm answers a different question.
ARM = "none"

UNNECESSARY_PASS_FLOOR = 0.8
NECESSARY_PASS_CEILING = 0.2

# Exit codes, because this command's channel is read by a CI gate and "exit 0" is the only thing a
# gate reads reliably. ``accepted`` alone must NEVER produce EXIT_ACCEPTED: the default run is a dry
# run whose numbers are entailed by the simulated runner, so an unverified accept exiting 0 would
# publish a wiring check as outcome-side evidence — the exact fabrication AC2 exists to prevent.
EXIT_ACCEPTED = 0  # measured, and the rates clear the thresholds
EXIT_REJECTED = 1  # measured, and they do not
EXIT_REFUSED = 2  # refused to spend (no model / metered key / no OAuth token)
EXIT_UNVERIFIED = 3  # no real turns were spent; there is no verdict to report either way
EXIT_NO_CORPUS = 4  # the corpus is absent or empty: an infrastructure fault, never a rejection

# The three verdicts the payload can carry. ``VERDICT_UNVERIFIED`` is the dry path's only possible
# value however clean the rates are, so a consumer reading the JSON rather than the exit status
# cannot read an unrun preflight as an acceptance.
VERDICT_ACCEPTED = "accepted"
VERDICT_REJECTED = "rejected"
VERDICT_UNVERIFIED = "unverified"


@dataclass(frozen=True)
class NecessityPreflight:
    """Both halves' empty-store pass rates and what they imply about the corpus.

    ``verified`` is the load-bearing field: it is true only when real agent turns were spent.

    The first cut carried ``accepted: bool``, computed from the rates alone, and guarded only the
    EXIT CODE with ``verified``. A consumer reading the JSON — the natural thing to do with
    ``--json`` — therefore read an UNRUN preflight as an acceptance. So the payload now separates
    the two questions it was conflating: ``thresholds_cleared`` is the arithmetic (did the rates
    clear the floor and the ceiling), ``verdict`` is what the run actually licenses, and it is
    ``unverified`` on the dry path no matter how clean the arithmetic looks. ``exit_code`` carries
    the process's own answer inside the payload so the two channels cannot disagree."""

    mode: str
    verified: bool
    corpus_dir: str
    repeats: int
    n_necessary: int
    n_unnecessary: int
    necessary_pass_rate: float
    unnecessary_pass_rate: float
    empty_store_pass_rate_margin: float
    thresholds_cleared: bool
    verdict: str
    exit_code: int
    note: str


def _half_pass_rate(
    tasks: Sequence[ToolReqRealAgentTask],
    *,
    repeats: int,
    model: str,
    dry_run: bool,
    channel: MemoryChannel,
) -> float:
    """The fraction of runs across ``tasks`` whose goal action passed with NO surfaced memory.

    Empty ``tasks`` is a caller error rather than a 0.0 rate: a rate over nothing would read as
    "the half failed" and could satisfy the necessary-half threshold with an empty corpus."""
    if not tasks:
        raise ValueError("necessity preflight: no tasks in this half")
    passes = 0
    runs = 0
    for task in tasks:
        outcome = run_arm(
            arm=ARM,
            step=task.goal_step,
            memory={},
            channel=channel,
            repeats=repeats,
            model=model,
            dry_run=dry_run,
            current_values=task.current_opaque_values,
            recorder=CellRecorder(),
        )
        passes += outcome.passes
        runs += outcome.runs
    return passes / runs


def necessity_preflight(
    tasks: Sequence[ToolReqRealAgentTask],
    *,
    corpus_dir: Path,
    repeats: int = 1,
    model: str = "",
    dry_run: bool = True,
    channel: MemoryChannel = MemoryChannel.RECALLED,
) -> NecessityPreflight:
    """Run the empty-store leg over both halves and summarize. The validity verdict rides
    THIS summary — the object the driver emits — never a per-cell metric vector, where it
    would flatten into a paired mean."""
    halves = {
        VARIANT_NECESSARY: [t for t in tasks if t.variant == VARIANT_NECESSARY],
        VARIANT_UNNECESSARY: [t for t in tasks if t.variant == VARIANT_UNNECESSARY],
    }
    rates = {
        name: _half_pass_rate(half, repeats=repeats, model=model, dry_run=dry_run, channel=channel)
        for name, half in halves.items()
    }
    necessary = rates[VARIANT_NECESSARY]
    unnecessary = rates[VARIANT_UNNECESSARY]
    cleared = unnecessary > UNNECESSARY_PASS_FLOOR and necessary < NECESSARY_PASS_CEILING
    # An unverified run has no verdict to give, so it reports none — the payload cannot say
    # "accepted" about turns nobody spent, whatever the arithmetic came out to.
    if not dry_run:
        verdict = VERDICT_ACCEPTED if cleared else VERDICT_REJECTED
        exit_code = EXIT_ACCEPTED if cleared else EXIT_REJECTED
    else:
        verdict = VERDICT_UNVERIFIED
        exit_code = EXIT_UNVERIFIED
    note = (
        "PAID: real claude -p turns; these rates are outcome-side evidence."
        if not dry_run
        else (
            "DRY RUN — UNRUN, NOT VERIFICATION. simulated_runner writes the current values iff "
            "they appear in the prompt, so this structure is reproduced by construction and says "
            "nothing about a real agent. AC2 is UNMET until this is re-run with --paid; the "
            f"command exits {EXIT_UNVERIFIED}, never {EXIT_ACCEPTED}, so no gate can read it as "
            "acceptance."
        )
    )
    return NecessityPreflight(
        mode="paid" if not dry_run else "dry_run",
        verified=not dry_run,
        corpus_dir=str(corpus_dir),
        repeats=repeats,
        n_necessary=len(halves[VARIANT_NECESSARY]),
        n_unnecessary=len(halves[VARIANT_UNNECESSARY]),
        necessary_pass_rate=necessary,
        unnecessary_pass_rate=unnecessary,
        empty_store_pass_rate_margin=unnecessary - necessary,
        thresholds_cleared=cleared,
        verdict=verdict,
        exit_code=exit_code,
        note=note,
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--model", default="")
    ap.add_argument(
        "--paid",
        action="store_true",
        help="spend real claude -p turns; without it the run is a wiring dry run, not evidence",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    # The refusals run BEFORE the corpus is loaded: a refused run must cost nothing at all, and a
    # gate that trips on the missing corpus first would hide the reason it was actually refused.
    if a_paid_run_carries_the_metered_api_key(dry_run=not args.paid):
        print(REFUSE_API_KEY_SET)
        return EXIT_REFUSED
    if args.paid and not os.environ.get(ENV_OAUTH):
        print(
            f"REFUSING to spend: {ENV_OAUTH} is unset. Source it from an account home\n"
            "  (~/.claude-homes/accountN/.claude/.credentials.json) and re-run, or drop --paid\n"
            "  to prove the wiring for free."
        )
        return EXIT_REFUSED
    # --model defaults to "", so this is the gate the whole --paid path used to walk straight past:
    # an unpinned paid run executes under whichever model the CLI defaults to, and a necessity
    # verdict that cannot name the model it was measured under is not evidence about any agent.
    if a_paid_run_needs_a_model(args.model, dry_run=not args.paid):
        print(REFUSE_UNPINNED_MODEL)
        return EXIT_REFUSED

    _, tasks = load_twin_corpus(args.corpus_dir)
    # An ABSENT corpus is an infrastructure fault, not a scientific result. Without this it fell
    # through to ``_half_pass_rate``'s ValueError, or (worse, had that guard been laxer) to an
    # exit 1 — the code that means "measured, and the corpus was REJECTED". No missing directory
    # may ever be readable as a rejection.
    if not tasks:
        print(
            f"no tool-requiring tasks under {args.corpus_dir}: the corpus is missing or empty, "
            "so there is nothing to measure (this is NOT a rejection)",
            file=sys.stderr,
        )
        return EXIT_NO_CORPUS
    result = necessity_preflight(
        tasks,
        corpus_dir=args.corpus_dir,
        repeats=args.repeats,
        model=args.model,
        dry_run=not args.paid,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        print(
            f"[{result.mode}] necessary {result.necessary_pass_rate:.3f} "
            f"unnecessary {result.unnecessary_pass_rate:.3f} "
            f"pass-rate margin {result.empty_store_pass_rate_margin:.3f} "
            f"-> {result.verdict.upper()} "
            f"(thresholds_cleared={result.thresholds_cleared}, verified={result.verified})"
        )
        print(result.note)
    return result.exit_code


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
