# Operational recovery after progress-pipe failure

The original phase-1 supervisor stopped after its stdout reader disappeared.
Progress and heartbeat writes raised `BrokenPipeError`; all six worker failure
records and the failed phase summary were preserved. The outer tee did not write
an exit record. The exact reason its reader disappeared is not independently
established. This is investigator orchestration failure, not model behavior.

At inspection, six session results existed, one further session had an original
process record without a result, and two slots had been claimed before process
launch. No supervisor or recorded model process remained running. The six saved
results and original failure records are hashed in
`infrastructure-preservation-before.json`. Original sources, manifest, blocked
markers, output logs and scratch stores remain untouched.

The unassessed Codex Astra turn has a complete preserved transcript ending in
`turn.completed` within the original deadline. A separately reviewed assessment
may append its missing receipt exports, snapshots, unchanged hidden grading and
result from those actual artifacts. It must not launch a model, change code or
memories, fabricate an OS exit status, or claim the supervisor observed process
completion. Its result is explicitly posthoc, with unknown OS exit, approximate
stream-based duration and the logging infrastructure fault retained. Report a
sensitivity excluding this recovered lifecycle.

The two slots claimed before launch are not restarted. Their later stages remain
unassessed because a completed predecessor is missing. These are infrastructure
censoring, not negative capture or retrieval observations.

Continuation is a documented operational deviation from the original phase
runner's permanent per-profile blocking. Once the shared logging fault has been
resolved, independent untouched lifecycles can continue with the original frozen
rows, conditions and order. No claim, started trial, completed trial or missing
capture is recreated. Existing results are skipped, and a new stage starts only
when its destination has never existed and its actual predecessor has a result.
The original blocked markers remain; a new reviewed continuation ledger records
the narrowly authorized override of this shared `BrokenPipeError` cause.

The continuation supervisor writes directly to an exclusive durable file and
runs in a separate process session, so losing a terminal reader cannot turn a
progress write into a broken pipe. New infrastructure failures still stop the
affected profile, and frozen-input changes stop all work. Four-worker concurrency,
420-second deadlines, Claude limits, owned Qwen runtime, native-memory isolation,
model pins, actual retained state and independent hidden checks remain unchanged.
No additional model slots or retries are authorized by this recovery.

Complete and review the remaining eligible phase-1 slots before beginning
phase 2. A new exact-summary review records the continuation checkpoint alongside
the original failed summary. Keep all 216 planned slots and 36 lifecycles in the
report, with started, assessed, censored and recovered counts separated. Missing
observations weaken the matched comparison and must not be silently excluded or
replaced with perfect records.

The censored cells are Sonnet/finance/rich-prime and Luna/Courier/thin-prime.
Their other arms remain useful observed outcomes, but those two profile/family
cells cannot supply a complete three-arm comparison. Before continuation, declare
a separate sensitivity using the remaining ten complete profile/family cells
(30 lifecycles, 180 sessions), contingent on their completion. An additional
matched sensitivity excluding the recovered Astra/finance cell has nine cells.
The primary report retains every planned slot; these sensitivities must not hide
the unbalanced infrastructure censoring.
