The 48-session checkpoint is complete and admitted to continuation under the
same frozen conditions. Source, executable, and live-profile hashes remain
unchanged. All 48 slots started once, completed, and were assessed; none timed
out, was replaced, or reported an infrastructure fault. The remaining 48 main
slots and 24 normal-native slots are not results of this checkpoint.

| Host | Baseline frozen checks | Memory-arm frozen checks | Initial treatment captures | Accepted memory writes |
| --- | ---: | ---: | ---: | ---: |
| Claude Code / Sonnet 4.6 | 6/6 sessions | 6/6 sessions | 0/2 | 0 |
| Codex / gpt-6-astra | 6/6 | 6/6 | 0/2 | 0 |
| OpenCode / local Qwen3 Coder | 3/6 | 6/6 | 0/2 | 0 |
| zcode / GLM-5.3 | 6/6 | 6/6 | 0/2 | 3 |

Overall, 45/48 session artifacts pass all frozen cases (1553/1568 individual
cases). Two OpenCode baseline failures emitted an XML-like skill invocation as
ordinary text and executed no tools. Another baseline artifact mishandled CSV
quoting. Later sessions sometimes recovered earlier missing functionality from
ordinary source and public examples. These outcomes remain recorded separately.

A source audit found an additional valid offset-ordering case missing from the
frozen reconciliation suite. The same posthoc case was run against all 16 saved
reconciliation stage-2/3 artifacts, using isolated read-only copies and the pinned
runtime and stage-specific independent references. Fourteen passed. OpenCode's
memory-arm stages 2 and 3 failed despite their original 20/20 and 30/30 grades.
Thus 43/48 checkpoint artifacts pass all checks actually applied to them. This is
a finite coverage limitation, not a changed expected answer or reason to rewrite
the original grades. No candidate, reference, or retained artifact was modified.

The generic workflow did not produce an initial keyed capture in any of the
eight treatment opportunities. This is not equivalent to total knowledge loss:
agents preserved and used code, README text, and substantive issue-close reasons.
Codex read the full memory procedure in all six treatment sessions; Claude loaded
the native Beads skill in all six but did not open its memory reference. Other
hosts' observed skill entry and file reads are recorded per session; availability
is not silently treated as a read.

The three zcode writes require different interpretations:

- Renewal stage 3 saved the correct original policy and the new historical
  endpoint's fixed scope. This was a justified new scope/delayed first capture,
  not a duplicate of an existing memory.
- Reconciliation stage 2 saved accurate CSV business facts together with a false
  claim about the pinned Python CSV writer and an unsupported prescription for
  future CSV exports. Readback faithfully preserved that misinformation.
- Reconciliation stage 3 saved the correct frozen incident-replay scope. Its
  absolute no-refactoring advice is stronger engineering guidance than the
  business requirement. The prior CSV note was unchanged and not retrieved.

These queries checked for existing topics and returned no matches. The three
full recalls verified same-session saves. There is no observed fresh-session
direct lookup or search-to-full-lookup handoff at this checkpoint. No confirmed
duplicate control write or historical record mutation occurred; zero writes in
other controls do not establish useful selectivity when captures were absent.
The CSV warning is an observed misleading library-avoidance record. Inherited
reliance on it has not been observed. Do not turn that into a claim that the
practitioner's broader tool-avoidance account is verified.

Claude reports $2.0752089 at list prices, including $0.01152 of auxiliary Haiku
usage. Codex and zcode expose no dollar charge; OpenCode reports zero remote
provider cost and uses unpriced local compute. Checkpoint wall time was 26.26
minutes. These are not invoice or production-cost estimates.

Independent reviews found no condition-invalidating task, delivery, state,
adapter, or expected-answer defect. Continue stages 4–6 with the actual records,
including omissions and the incorrect CSV advice, without repair, task cues,
new keys supplied by the harness, or repeated sessions. The limited adoption and
semantic failures are measured outcomes, not grounds to tune this cohort.

Evidence: [mechanical summary](audits/checkpoint-mechanical-summary.json),
[Claude/Codex review](audits/claude-codex-_jux3wgj/CHECKPOINT.md),
[OpenCode/zcode audits](audits/opencode-zcode-v4vuqra9/),
[uniform offset checks](audits/opencode-zcode-v4vuqra9/offset-supplements/),
[CSV source check](audits/csv-workaround-source-check.md), and
[phase completion](phases/checkpoint/completed.json).
