"""Outcome-label leak guard — the task-construction mirror of `validity.assert_no_leak`.

D6 (`validity`) guards what an arm may ingest at *retrieval* time. It does not
cover the *task-construction* path, where an outcome label can reach the agent
through `instruction.md` or verifier markers (`harbor/adapter.py`). This guard
closes that path mechanically: given the files an agent can read and a task's
outcome-label values, assert none of the labels appears in agent-readable text
(architect finding C1).

Only high-entropy *identifiers* (pr, commit_sha, base_commit) are scanned — the
answer-revealing values a held-out bead must not expose. The low-entropy enum states
(pr_state / ci) are excluded by design: a task instruction may legitimately contain
the word "pass" or "merged", so substring-scanning them would be false positives.
`repo` (owner/name) is also excluded deliberately: it is legitimate task *context*
(the agent needs to know where the work lives), not an answer-revealing outcome, and
scanning it would false-positive on any task that names its own repository. Enum and
context leakage are prevented structurally by the design/task manifest split, not by
this scan.
"""

from collections.abc import Iterable, Mapping
from typing import Any

# The high-entropy outcome identifiers a held-out bead must never expose — the
# SINGLE SOURCE OF TRUTH for "which fields are answer-revealing", shared so the
# downstream guards cannot drift from it: the relevance-judge anti-circularity scan
# (mem-lvp.31) and the forward-capture projector's key-routing/scan
# (`forward_capture._OUTCOME_KEYS` imports this; mem-ymxp #5).
IDENTIFYING_KEYS = ("pr", "commit_sha", "base_commit")


class OutcomeLeakError(AssertionError):
    """Raised when an outcome label appears in agent-readable text — a validity bug
    that must fail the run, never be silently stripped."""

    def __init__(self, offenders: list[tuple[str, str]]) -> None:
        # Each offender is (where, label): `where` is the filename (or "<text>"),
        # `label` is the leaked outcome value found in it.
        self.offenders = offenders
        detail = ", ".join(f"{label!r} in {where}" for where, label in offenders)
        super().__init__(f"outcome label leaked into agent-readable text: {detail}")


def outcome_labels(record: Mapping[str, Any]) -> tuple[str, ...]:
    """The high-entropy outcome identifiers of `record` — the values that must not
    appear in any agent-readable file. Missing/empty values are skipped."""
    outcome = record.get("outcome") or {}
    return tuple(str(outcome[key]) for key in IDENTIFYING_KEYS if outcome.get(key))


def find_outcome_leaks(
    agent_readable: str | Mapping[str, str], labels: Iterable[str]
) -> list[tuple[str, str]]:
    """Every ``(where, label)`` outcome-label leak in `agent_readable` (a string, or a
    filename->content mapping). The match is case-insensitive and blank labels are
    ignored so they cannot match every document. Errs toward over-catching — the safe
    direction for a validity scan. Returns an empty list when clean. This is the
    non-raising core both `assert_no_outcome_leak` (raise on any leak) and the
    forward-capture post-close re-scan (quarantine the leaking item) share, so the two
    scan the same way and cannot drift."""
    # Dedupe while preserving order so a caller passing repeated labels does not
    # produce duplicate offenders.
    scan = list(dict.fromkeys(label for label in labels if label.strip()))
    if not scan:
        return []
    docs = (
        list(agent_readable.items())
        if isinstance(agent_readable, Mapping)
        else [("<text>", agent_readable)]
    )
    return [
        (where, label)
        for where, content in docs
        for label in scan
        if label.lower() in content.lower()
    ]


def assert_no_outcome_leak(agent_readable: str | Mapping[str, str], labels: Iterable[str]) -> None:
    """Assert no value in `labels` appears in `agent_readable` (a string, or a
    filename->content mapping). Errs toward over-catching — the safe direction for a
    validity guard: a false positive fails the run loudly, a false negative lets a leak
    through. Raises `OutcomeLeakError` listing every (where, label) offender."""
    offenders = find_outcome_leaks(agent_readable, labels)
    if offenders:
        raise OutcomeLeakError(offenders)
