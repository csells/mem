# Observed failure mechanisms

These are analyst readings of saved traces, not additional automatic scores. They
explain individual outcomes and do not estimate frequencies from selected examples.
The frozen endpoint definitions and running conditions are unchanged.

## Explicit guidance can lose to native-memory habits

Confirmation `explicit / world-seed0-task1 / necessary / repeat 1` saved the required
facts in native `project_system_state.md` and `MEMORY.md`, with no bd writes. The
fresh goal succeeded through native memory. This is successful task completion but
not adoption of bd. Evidence: the establish and goal raw leg files under that pair
in `confirmation/pairs/explicit/`, indexed by the frozen manifest and `cell.json`.

## Recalled bytes can survive while their meaning changes

Confirmation `redirect / world-seed2-task1 / necessary / repeat 0` successfully
stored and recalled the required token. During capture, however, the agent changed
“production deploy timeout is” into “production deploy timeout issue/ref is.” The
goal session then treated the token as an issue reference, attempted to dereference
it, and declined to write the required value as a timeout. No successful goal Write
was observed.

Evidence: `confirmation/pairs/redirect/f76d5ad8b3c9a443/0/legs/`, particularly the
goal file ending `__1.json` and its actual bd receipt payloads. The scorer correctly
reports capture and observed recall as true, but goal action and observed handoff
as false. Here capture means acknowledged token preservation, not semantic fidelity.
The synthetic opaque timeout value is a material interpretation limit: this example
must not be presented as proof that bd corrupted data or that the same rate would
occur with ordinary numeric timeout values.

## Native redirection cannot recover an omitted write

Pilot `redirect / world-seed0-task0 / necessary / repeat 0` searched bd during the
establish session but never wrote the newly supplied facts. The fresh goal searched
an empty store and failed. Redirection affects native-memory attempts; it does not
ensure an agent attempts any durable write before ending its establish session.
The pilot used the older redirect command wording and remains separate from
confirmation analysis.
