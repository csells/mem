"""CSB-style oracle validity gate (mem-g6a / mem-r5y): the per-bundle sanity check
that PRECEDES every graded signal.

Before any candidate is scored, the bundle's own oracle must behave: the gold diff
applied as the candidate must REPRODUCE (repro_pass=True, test_ratio=1.0) and the
empty diff must FAIL (repro_pass=False, test_ratio=0.0). This mirrors CSB's
``docs/ORG_CALIBRATION.md`` validity gate -- "the gold answer must score 1.0 and the
empty answer 0.0 on every task, or the oracle itself is broken". A bundle that fails
the gate has a broken oracle (a non-reproducing gold diff, or a test that passes
without the fix), and must be excluded from the graded comparison rather than
silently scored: a gold diff that does not reproduce would drag every arm's
``test_ratio`` toward noise, and an empty diff that partially passes means the gold
tests are not actually fail-to-pass.

The gate runs the SAME `ReproRunner` the direct leg uses, so its judgment is the
test runner's (delegated), and this module only interprets two outcomes against the
invariant -- pure mechanism (ZFC).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from membench.grading.dual_verifier import ReproRunner
from membench.schemas.bundle import TaskBundle


class ValidityResult(BaseModel):
    """One bundle's oracle-validity readout. ``valid`` is the CSB invariant: gold
    reproduces (and, when per-file counts ran, scores 1.0) and empty fails (scores
    0.0). ``reason`` records WHY a bundle failed the gate so the exclusion is never
    silent. Test ratios are None when the runner is a stub / errored before the test
    loop -- a typed absence, not a misleading 0.0."""

    model_config = ConfigDict(frozen=True)

    work_id: str
    gold_repro_passed: bool
    gold_test_ratio: float | None
    empty_repro_passed: bool
    empty_test_ratio: float | None
    valid: bool
    reason: str


def validity_gate(bundle: TaskBundle, *, test_runner: ReproRunner) -> ValidityResult:
    """Run the CSB validity gate for ``bundle``: apply the gold diff as the candidate
    (must reproduce) and the empty diff (must fail). Returns the readout with
    ``valid`` set per the invariant and ``reason`` naming the first breach."""
    gold_candidate = bundle.output.diff_by_file()
    gold = test_runner.run(bundle=bundle, candidate_diff=gold_candidate)
    empty = test_runner.run(bundle=bundle, candidate_diff={})

    reasons: list[str] = []
    if gold.error is not None:
        reasons.append(f"gold diff did not score (runner error: {gold.error})")
    elif not gold.passed:
        reasons.append("gold diff did not reproduce (expected repro_pass=True)")
    elif gold.test_ratio is not None and gold.test_ratio != 1.0:
        reasons.append(f"gold diff scored test_ratio {gold.test_ratio} (expected 1.0)")

    if empty.error is not None:
        reasons.append(f"empty diff did not score (runner error: {empty.error})")
    elif empty.passed:
        reasons.append("empty diff reproduced (expected repro_pass=False)")
    elif empty.test_ratio is not None and empty.test_ratio != 0.0:
        reasons.append(
            f"empty diff scored test_ratio {empty.test_ratio} (expected 0.0; a gold "
            "test passes without the fix)"
        )

    return ValidityResult(
        work_id=bundle.work_id,
        gold_repro_passed=gold.passed and gold.error is None,
        gold_test_ratio=gold.test_ratio,
        empty_repro_passed=empty.passed,
        empty_test_ratio=empty.test_ratio,
        valid=not reasons,
        reason="; ".join(reasons) if reasons else "gold reproduces, empty fails",
    )
