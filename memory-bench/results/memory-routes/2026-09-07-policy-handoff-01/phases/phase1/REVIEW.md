# Initial capture and first reuse checkpoint

All 80 frozen phase-1 slots were started and assessed once. The runner exited 0.
The [mechanical summary](mechanical.json) records 59/80 correct artifacts and
1882/2340 passing hidden cases. This is not a complete-lifecycle result.

| Phase-1 outcome | Generic | Occasions |
| --- | ---: | ---: |
| Correct artifacts | 30/40 | 29/40 |
| Passing hidden cases | 962/1170 | 920/1170 |
| Faithful initial policy captures | 2/20 | 9/20 |
| Correct first reuse with full prior governing record read before editing | 2/20 | 9/20 |
| Faithful late first captures at stage 2 | 4/20 | 0/20 |

The 11 successful governing-record reads cover five direct catalog lookups and
six search-then-full-lookup routes. All 11 entries with a complete governing
agreement were read before editing and followed by correct work. GLM also saved
useful test-invocation knowledge in finance and a dispatch note in Courier; these
are distinct from complete policy capture. Its later full dispatch-note read was
after implementation. Incomplete or unrelated records do not become complete
governing agreements merely because they were saved or read.

Fourteen Codex sessions reported quota errors: 12 before tool work and two after
work began. Both guidance arms have seven such sessions. These remain in the
planned denominator and are classified as availability failures, not memory
adherence judgments. Two interrupted sessions left passing artifacts. Later
scheduled Codex sessions succeeded, contradicting the provisional assumption of
a stable shared account block. The superseded block markers and correction are
preserved under `audits/provider-quota-observations-1788807651726095000/`.
No failed session was retried or replaced and no credits were purchased.

The reported cost is $11.0525124: Claude's 32 sessions report provider list-price
usage; Qwen reports zero remote charges, with local compute unpriced. Codex and
GLM dollar costs are unavailable for 40 sessions. No session timed out. The sum
of session durations is 5935.24 seconds; that is not elapsed wall time.

The [integrity audit](integrity.json) finds no discrepancy across all 80 published
slots: 442 source hashes, seven binary hashes, and four existing-profile hashes
match; prompts only assign an issue; issue bodies match frozen tasks; memory
carryforward and actual-key catalogs are exact; receipt ancestry is complete;
the guidance files are unchanged. Host session IDs are unique. The runner's
narrow `infrastructure_fault=0` does not negate the quota failures.

Both family reviewers independently checked saved artifact outputs against
frozen expected results and manually audited actual retained bodies and traces.
They are unblinded corpus-author agents, not independent human annotators.
Finance's final evidence is in
`audits/finance-phase1-lxa0y1o5/phase1-final-1788808529862145000.json`;
Courier's 40 per-slot audits are in `audits/webhooks-phase1-8w6n9zwg/`.
These paths are relative to the cohort root.

There is a substantive failure to carry forward unchanged: Sonnet's occasions
Courier stage 2 invented account-local identity although the available provider
contract required global identity. It saved and read back the wrong rule, cited
an issue that did not approve that change, and passed only 37/51 hidden cases.
The procedure explicitly required source verification; storage agreement did
not establish truth. Several other sessions overclaimed validation of ordering
from aggregate-only tests. Core facts, saved provenance, and final prose are
therefore separate audit fields.

Codex's normalized aggregate tool output sometimes omits leading chunks. Its
retained model-facing rollout contains them. Append-only audit supplements use
that actual delivery evidence; frozen visibility counters remain lower bounds.
Conversely, a full raw memory receipt does not prove a full model-visible read
when the agent pipes its output through `head` or `grep`.

The checkpoint supports continuing the unchanged design. Capture omission,
wrong policy, tool-format failure, and alternate-source success are results;
none justify changing conditions. Release stages 3–6 with the actual retained
records, including errors, then assess revision, historical fidelity, and
fully supplied reproduction. No full-lifecycle success is awarded here.
