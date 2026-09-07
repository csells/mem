"""Pre-run mechanism-fires gate (mem-xe2p): CSB run-validity discipline, first target.

Before a grid burns agent legs, a cheap smoke must show the mechanism under test
actually FIRES — its covariate exceeds zero on at least one anchor. The 69-leg
Option-A grid (mem-lvp.24) returned a null on a mechanism that never engaged once;
this gate would have refused that grid for the cost of one mechanical scan.

Ported from CodeScaleBench's run-validity discipline as a composition (no single
CSB construct is a pre-run mechanism-fires gate):

* the ``harbor_run_guarded`` scaffold (``configs/_common.sh``) — cheap preflight,
  structural refusal at the entrypoint, explicit logged override;
* the ``mcp_never_used`` predicate (``scripts/authoring/validate_task_run.py``) —
  covariate == 0 everywhere is CRITICAL — lifted from post-run audit to pre-run gate.

ZFC: the gate is mechanical (does the covariate exceed zero on any anchor), never a
model judgment. It is mechanism-parameterized — the caller names the mechanism and
covariate and supplies per-anchor observations — so the next grid gates a different
mechanism without touching this module. The gate block rides OUTSIDE
``MetricsBundle`` / ``GridConditionResult.metrics()`` (the safety_gates precedent);
a test enforces that separation. Failure is LOUD: the refusal names the mechanism,
the covariate observed, and every anchor tried. An override never silently skips —
it requires a non-blank reason and is recorded on the gate block itself, which the
grid driver persists in its summary either way.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict


class AnchorObservation(BaseModel):
    """One smoke observation: the covariate's value on one anchor."""

    model_config = ConfigDict(frozen=True)

    anchor_id: str
    value: float
    fired: bool


class MechanismFiresGate(BaseModel):
    """The pre-run verdict. ``fired`` is the gate; ``overridden`` records that a
    failing gate was explicitly waived (with the logged reason) instead of fixed.
    ``reason`` is human-readable provenance for the summary block."""

    model_config = ConfigDict(frozen=True)

    mechanism: str
    covariate: str
    anchors: tuple[AnchorObservation, ...]
    fired_anchor_ids: tuple[str, ...]
    fired: bool
    overridden: bool
    override_reason: str | None
    reason: str


class MechanismNeverFiredError(RuntimeError):
    """The mechanism under test never fired on the smoke — the grid must not run."""

    def __init__(self, gate: MechanismFiresGate) -> None:
        self.gate = gate
        super().__init__(
            f"{gate.reason} — refusing to run the grid: every leg would measure a "
            "mechanism that never engages (the mem-lvp.24 null). Fix the substrate, "
            "or override explicitly with a logged reason."
        )


def compute_mechanism_fires(
    *, mechanism: str, covariate: str, observations: Mapping[str, float]
) -> MechanismFiresGate:
    """The pure readout: fired iff the covariate exceeds zero on at least one
    anchor. Zero anchors fails closed — an empty smoke proves nothing."""
    anchors = tuple(
        AnchorObservation(anchor_id=anchor_id, value=value, fired=value > 0)
        for anchor_id, value in observations.items()
    )
    fired_ids = tuple(anchor.anchor_id for anchor in anchors if anchor.fired)
    if fired_ids:
        reason = (
            f"mechanism {mechanism!r} fired: covariate {covariate!r} > 0 on "
            f"{len(fired_ids)}/{len(anchors)} anchor(s) ({', '.join(fired_ids)})"
        )
    elif anchors:
        tried = ", ".join(anchor.anchor_id for anchor in anchors)
        reason = (
            f"mechanism {mechanism!r} never fired: covariate {covariate!r} == 0 on "
            f"all {len(anchors)} anchor(s) tried ({tried})"
        )
    else:
        reason = (
            f"mechanism {mechanism!r} never fired: no anchors observed for covariate "
            f"{covariate!r} (an empty smoke proves nothing — fail closed)"
        )
    return MechanismFiresGate(
        mechanism=mechanism,
        covariate=covariate,
        anchors=anchors,
        fired_anchor_ids=fired_ids,
        fired=bool(fired_ids),
        overridden=False,
        override_reason=None,
        reason=reason,
    )


def enforce_mechanism_fires(
    *,
    mechanism: str,
    covariate: str,
    observations: Mapping[str, float],
    override_reason: str | None = None,
) -> MechanismFiresGate:
    """The structural seam a grid entrypoint calls BEFORE burning legs. Returns
    the gate block when the mechanism fired; raises `MechanismNeverFiredError`
    when it never fired, unless a non-blank ``override_reason`` waives the
    refusal — then the override is recorded on the returned block. An override
    on a passing gate is not consumed (``overridden`` stays False)."""
    gate = compute_mechanism_fires(
        mechanism=mechanism, covariate=covariate, observations=observations
    )
    if gate.fired:
        return gate
    reason_text = (override_reason or "").strip()
    if not reason_text:
        raise MechanismNeverFiredError(gate)
    return gate.model_copy(
        update={
            "overridden": True,
            "override_reason": reason_text,
            "reason": f"{gate.reason} — OVERRIDDEN: {reason_text}",
        }
    )
