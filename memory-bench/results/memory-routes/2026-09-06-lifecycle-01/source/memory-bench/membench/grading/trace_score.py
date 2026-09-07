"""Deterministic trace_error scorer — the deterministic half of the D17 per-rung reward.

The held-out set is closed beads carrying ≥1 build/test/lint `trace_error` with a
canonical failure signature `tool:file:line:error_class` (TS-side
`failureSignature`, persisted into the `trace_errors` store columns). The agent is
re-run fresh per ablation rung; this module asks the *deterministic* question: did
the held-out task's known failure class recur in the fresh run, or was it avoided?

Two validity defenses make the answer interpretable (architect review of mem-apg.3):

- **Relaxed signature for the avoid axis.** The canonical signature encodes the
  *original* agent's exact path; a fresh agent that touches the same file at a
  shifted line would otherwise score a trivial "resolved". `relaxed_signature`
  drops the line and basenames the file, so recurrence keys on *which failure class
  in which file*, not the original line. This relaxation is a deliberate
  calibrated-threshold mechanism (ZFC exception — the same justification
  `parse/recurrence.ts` uses for its `errorClass` fallback), not a semantic
  judgment; the full signature is kept verbatim for `exact_recurrence` reporting.

- **`path_reached` gate.** A run that never touched the file the held-out error
  lives in cannot claim to have resolved it: its deterministic term is *not
  applicable* (`None`), not a free `1.0`. This closes the "did nothing → trivially
  avoided the error" confound: a no-op falls through to the (absent or low) judge
  term in `combined_reward` instead of winning by default.

The fresh-run errors this module consumes MUST be produced by the canonical TS
extractor (`parse/error-extractors.ts`) so the signatures it compares are
byte-identical to the held-out side; the harvesting + extraction live at the grid
driver boundary (mem-apg.3d), not here. This module is pure: given structured held
errors and a harvested `RunTrace`, it computes the reward components and never runs
an agent. The semantic `rubric_score` term is the OSS judge's (mem-apg.3b); this
module only carries the slot and the composition rule the curve builder (mem-apg.3c)
consumes.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from posixpath import basename
from typing import Any


@dataclass(frozen=True)
class TraceErrorRef:
    """The minimal projection of a `trace_errors` row the scorer needs. The row
    also carries `work_id`/`col`/`severity`/`message`; those are irrelevant to
    recurrence and deliberately not retained (carrying them would be speculative)."""

    tool: str
    file: str
    line: int
    error_class: str
    # The canonical TS-computed signature `tool:file:line:error_class`, used
    # verbatim for exact-recurrence reporting (never recomputed in Python).
    signature: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "TraceErrorRef":
        """Project a raw `trace_errors` row onto the fields the scorer uses; extra
        columns are ignored rather than required-then-dropped."""
        return cls(
            tool=row["tool"],
            file=row["file"],
            line=int(row["line"]),
            error_class=row["error_class"],
            signature=row["signature"],
        )


def relaxed_signature(error: TraceErrorRef) -> str:
    """The line-invariant, basename-scoped failure key: `tool:basename:error_class`.

    Counters path-divergence (a fresh recurrence at a shifted line, or under a
    different cwd prefix, is still the same failure). A calibrated-threshold ZFC
    exception, not a semantic match — it collapses exactly the line + directory
    components and nothing else."""
    return f"{error.tool}:{basename(error.file)}:{error.error_class}"


@dataclass(frozen=True)
class RunTrace:
    """The harvested result of one fresh agent run (mem-apg.3d produces this).

    `errors` are the structured build/test/lint errors the fresh run emitted (via
    the canonical TS extractor). `files_touched` are the paths the run read or
    wrote — the evidence for `path_reached`."""

    errors: tuple[TraceErrorRef, ...]
    files_touched: frozenset[str]


@dataclass(frozen=True)
class RewardComponents:
    """The deterministic reward terms for one (held-out task x rung) run.

    `path_reached` — did the fresh run engage the file the held-out error lives in.
    `trace_error_resolved` — did the held-out failure class stay absent from the
    fresh run (only meaningful when `path_reached`; pinned False otherwise, since a
    failure you never reached cannot be resolved).
    `rubric_score` — the OSS judge's semantic-completion term in [0, 1] (mem-apg.3b);
    None until the judge runs."""

    # A plain value object, NOT self-validating beyond the rubric range: the
    # contradictory (path_reached=False, trace_error_resolved=True) state is
    # constructible directly, but it is harmless — `deterministic_term` gates on
    # `path_reached` and ignores `resolved` when the path was never reached, and
    # `score_run` never emits that combination. Callers building components by hand
    # should rely on that gate rather than on a constructor invariant.
    path_reached: bool
    trace_error_resolved: bool
    rubric_score: float | None = None

    def __post_init__(self) -> None:
        if self.rubric_score is not None and not 0.0 <= self.rubric_score <= 1.0:
            raise ValueError(f"rubric_score must be in [0, 1], got {self.rubric_score}")


def _same_file(held_file: str, touched: str) -> bool:
    """Whether `touched` (a fresh-run path) is the same logical file as `held_file`
    (a repo-relative trace path). Matches on path *suffix* so a different cwd prefix
    in the fresh run still aligns, while a same-basename file in a different
    directory (`utils/index.ts` vs `components/index.ts`) does NOT — basename-only
    matching would conflate them. Case-sensitive (Harbor runs on Linux)."""
    return (
        held_file == touched
        or touched.endswith("/" + held_file)
        or held_file.endswith("/" + touched)
    )


def _path_reached(held: list[TraceErrorRef], touched: frozenset[str]) -> bool:
    return any(_same_file(e.file, t) for e in held for t in touched)


def score_run(
    held_out_errors: Iterable[TraceErrorRef],
    run: RunTrace,
    *,
    rubric_score: float | None = None,
) -> RewardComponents:
    """Score one fresh run against the held-out task's known trace errors.

    `path_reached` keys on path-suffix match (cwd-prefix tolerant; basename
    collisions across directories rejected). Resolution keys on the *relaxed*
    signature and is whole-set: ANY known failure class recurring anywhere in the
    fresh run marks not-resolved. Completeness across multiple held files (the run
    engaged one held file but skipped another) is deliberately NOT the deterministic
    axis's job — that is the judge's semantic-completion term (architect C2: the
    deterministic axis answers "did the known failure recur", the judge answers "was
    the work done"). An empty held set is a caller error — the held-out set is
    "beads with ≥1 trace_error" by construction, so an empty set would otherwise
    score a vacuous "resolved"."""
    held = list(held_out_errors)
    if not held:
        raise ValueError("score_run needs at least one held-out error to score against")

    path_reached = _path_reached(held, run.files_touched)

    if path_reached:
        held_relaxed = {relaxed_signature(e) for e in held}
        run_relaxed = {relaxed_signature(e) for e in run.errors}
        trace_error_resolved = held_relaxed.isdisjoint(run_relaxed)
    else:
        # Cannot resolve a failure the run never reached — pin False rather than
        # emit the contradictory (path_reached=False, resolved=True) state.
        trace_error_resolved = False

    return RewardComponents(
        path_reached=path_reached,
        trace_error_resolved=trace_error_resolved,
        rubric_score=rubric_score,
    )


def exact_recurrence(held_out_errors: Iterable[TraceErrorRef], run: RunTrace) -> tuple[str, ...]:
    """The held-out *full* signatures that recur exactly in the fresh run, in held
    order, de-duplicated. Reporting only — the avoid axis uses the relaxed key."""
    run_signatures = {e.signature for e in run.errors}
    seen: set[str] = set()
    out: list[str] = []
    for error in held_out_errors:
        if error.signature in run_signatures and error.signature not in seen:
            seen.add(error.signature)
            out.append(error.signature)
    return tuple(out)


def deterministic_term(components: RewardComponents) -> float | None:
    """The deterministic reward term, or None when it does not apply.

    None ⇔ the run never reached the relevant code path, so the avoid is
    *unmeasurable* (the no-op guard) — it must not collapse to 0.0 or 1.0 here;
    `combined_reward` then defers to the judge term."""
    if not components.path_reached:
        return None
    return 1.0 if components.trace_error_resolved else 0.0


def combined_reward(components: RewardComponents, *, det_weight: float = 0.5) -> float:
    """Compose the available reward terms into a scalar in [0, 1] — the contract the
    curve builder (mem-apg.3c) consumes and may re-weight.

    - both terms present → `det_weight*deterministic + (1 - det_weight)*rubric`.
    - deterministic only → the deterministic term (no judge yet).
    - rubric only → the judge term (a genuine different-path solve: the run never
      hit the original file, so the deterministic axis is N/A, but the judge can
      still credit completion).
    - neither → 0.0 (a no-op the judge also declined to credit)."""
    if not 0.0 <= det_weight <= 1.0:
        raise ValueError(f"det_weight must be in [0, 1], got {det_weight}")

    det = deterministic_term(components)
    rubric = components.rubric_score

    if det is not None and rubric is not None:
        return det_weight * det + (1.0 - det_weight) * rubric
    if det is not None:
        return det
    if rubric is not None:
        return rubric
    return 0.0


@dataclass(frozen=True)
class RewardRecord:
    """One reward observation, keyed by (work_id, rung, repeat_idx) so the curve
    builder can aggregate per rung and so flaky-rung reruns never double-count."""

    work_id: str
    rung: str
    repeat_idx: int
    components: RewardComponents

    @property
    def reward(self) -> float:
        return combined_reward(self.components)
