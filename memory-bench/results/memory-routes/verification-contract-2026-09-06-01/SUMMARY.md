# Public contract experiment prelaunch verification

121 targeted tests passed: the 84 existing E2E tests plus 27 checker tests and
10 driver tests. Full Ruff, Black, and strict mypy passed; the new script also
passed explicit strict mypy. Commands, exits, and durations are in results.json;
individual tool output is preserved alongside it. All tests use scratch state.

Offline canonical checks accepted 19/32 prior target interfaces and rejected all
13 incomplete targets. Whole-workspace checks passed 16/32 because three correct
targets had earlier incorrect siblings. All 585 original input hashes matched on
independent recheck; no model calls were made for this proof.

Both previous real CLI smoke profiles were reused only after all their source and
executable hashes matched. Existing authentication status was checked separately;
it is not proof of current inference availability. New source additions and their
tests are pinned in the cohort manifest. No new paid smoke was run.

The previous full Python suite had 4,678 passes, 44 skips, 27 failures and 12 setup
errors, documented in verification-e2e-2026-09-06-02. Those macOS/Linux assumptions
were not modified and the full suite was not repeated. TypeScript is unchanged
from its previous complete passing verification. No full-green suite is claimed.
