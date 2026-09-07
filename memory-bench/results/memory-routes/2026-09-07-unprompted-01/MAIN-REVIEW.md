All 96 main slots started once, completed, and were assessed. The frozen suite
passes 79/96 artifacts and 3965/4488 cases. Baseline passes 39/48 artifacts;
the memory package passes 40/48. No session timed out or reported an
infrastructure fault. All frozen runtime, executable, and profile hashes were
rechecked after completion and remain unchanged.

| Host/model | Baseline | Memory package | Initial treatment captures | Revision treatment captures |
| --- | ---: | ---: | ---: | ---: |
| Claude Code / Sonnet 4.6 | 12/12 | 10/12 | 0/2 | 0/2 |
| Codex / gpt-6-astra | 12/12 | 12/12 | 0/2 | 2/2 |
| OpenCode / local Qwen3 Coder | 3/12 | 6/12 | 0/2 | 0/2 |
| zcode / GLM-5.3 | 12/12 | 12/12 | 0/2 | 2/2 |

Uniform posthoc timestamp-offset checks pass 32/40 applicable saved artifacts.
Five OpenCode treatment artifacts sort offset timestamps incorrectly; three
OpenCode baseline artifacts lack CSV export after an agent rolled back its own
scratch source. Two of those treatment artifacts passed the frozen suite, so
77/96 artifacts pass all checks actually applied. Original grades remain intact.

There are three eligible subsequent-use sessions with search followed by a full
existing-record read: Codex renewal stages 5/6 and zcode reconciliation stage 5.
That is 3/24 treatment reuse slots, or 3/48 across both arms. Two additional
zcode revision sessions retrieve historical notes by search and full lookup.
No known-reference direct lookup occurred. Same-session readback is not reuse.
Naturally authored issue-close key attributions were preserved, but did not
produce an observed direct route. No original task supplies a memory instruction.

Correct code does not certify saved prose: zcode retained a false CSV-library
workaround, overstated verification evidence in two stage-test notes, and
attributed the daily report to the wrong implementation stage. No later session
read the full false CSV rationale or demonstrably relied on it. Historical
business facts survived its one historical-note implementation update. Supplied
reproduction captures recorded new endpoint scope rather than duplicating an
existing memory. The detailed semantic audits retain these distinctions.

One OpenCode session, reconciliation baseline stage 4, has host_success=false
despite exit 0. Its stream contains text after a completed step and a message
missing from the model table. The independent audit identifies that message as
synthetic compaction continuation; adjacent assistant messages have actual
pinned Qwen model rows. This stream validation failure and its provenance limit
remain reported. The artifact failure is independently measurable; no isolation,
delivery, source, or oracle defect was found that invalidates continuation.

Claude's 24 sessions report $5.4149662 at list prices, including $0.0230500 of
auxiliary Haiku usage. Codex/zcode dollar costs are unavailable. OpenCode reports
zero provider cost with local compute unpriced. These are not verified charges.

The independent Claude/Codex and OpenCode/zcode reviews admit the frozen
24-session normal-native phase. Proceed with actual state, unchanged inputs,
no repaired records, no repeated sessions, and no new memory cues. The main
comparison demonstrates some unprompted handoffs, not reliable adoption on all
four host/model profiles or both retrieval routes.

Evidence: [main mechanical summary](audits/main-mechanical-summary.json),
[continuation completion](phases/continuation/completed.json),
[Claude/Codex audit](audits/claude-codex-_jux3wgj/CONTINUATION.md), and
[OpenCode/zcode audits](audits/opencode-zcode-v4vuqra9/).
