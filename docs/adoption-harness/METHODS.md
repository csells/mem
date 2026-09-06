# bd memory comparison methods

> Companion to [README.md](README.md) (how to run the harness) and
> [RESULTS.md](RESULTS.md) (what the reference run found). "R4" is our internal
> label for the task-prompt template all three conditions share.

The question is whether agents choose bd to save useful facts, recover those facts in
a fresh session, and perform the downstream action. Task success alone cannot answer
this: the generic-guidance pilot solved its necessary tasks through native memory.

## Conditions and execution

All three conditions run the same R4 task prompts, tools, isolated store lifecycle,
CLI-default native-memory settings (`{}`), and neutral execution-receipt instrument.
Each pair has an establish session followed by a fresh goal session. They share the
bd store and native-memory directory. The harness clears the working directory
between sessions and restores only condition-specific harness guidance.

- **Generic:** general persistent-memory guidance; no bd deployment context; native
  memory accesses observed.
- **Explicit:** captured bd deployment context plus correct remember/recall/search
  examples; native accesses observed.
- **Redirect:** the explicit condition plus a hook that blocks native-memory accesses
  and directs the agent to bd.

Execution uses Claude Sonnet 4.6 (`claude-sonnet-4-6`), Claude Code 2.1.261, and the
bd executable identified by absolute path, SHA-256, and version in each manifest.
Account1 subscription OAuth supplies authentication. No API key is used. CLI-reported
USD values are estimated token costs, not subscription billing receipts.

The pilot scheduled two task IDs, both necessity variants, three conditions, and
one repeat: 12 pairs / 24 sessions. Confirmation schedules eight task IDs from four
world seeds, both variants, three conditions, and two repeats: 96 pairs / 192 sessions.
These are generated configuration tasks, not independent samples of production
repository work. Two confirmation task IDs also appeared in the pilot. The phases
are analyzed separately; pilot observations are not added to confirmation denominators.

The scheduler randomizes task/variant/repeat blocks and condition order within each
block using the frozen seed. Every scheduled pair remains in the analysis, including
missing, interrupted, or unmeasured pairs. Completed pairs are reused on resume;
an interrupted pair causes a refusal requiring evidence reconciliation before any
new paid work. Source identity is frozen per phase; no harness edits are made during
that phase's live execution.

## What counts

- **Capture:** actual successful bd execution and a valid write acknowledgment whose
  stored content contains the task's authored opaque required value.
- **Observed recall:** successful bd execution returned that value, and the authentic
  bd payload appeared in the matching Bash tool result.
- **Recall before action:** the read's tool-result event preceded submission of the
  successful goal action, including when tools run concurrently.
- **Observed bd handoff:** capture, observed recall, recall before action, and the
  acknowledged goal action all succeeded. This establishes an observed conjunction;
  it does not prove the action depended causally on bd when another channel also
  supplied the value.
- **Recorded goal contract success (historical reference run):** an acknowledged
  Write has argument values containing the required opaque token and excluding
  superseded tokens. That frozen check did not validate the destination filename,
  JSON structure, field placement, or every requested configuration value.
- **Qualifying Write (current scorer and transcript audit):** an acknowledged,
  non-error Write targets the expected `config.json` path and carries valid JSON
  with the required token in string values and no superseded tokens. Both use
  `bd_actions.write_reason`; the audit is not an independent implementation. It
  reads recorded arguments and acknowledgments, not filesystem artifacts, and
  cannot verify later edits, final file state, semantic field placement, or every
  requested setting. Audit results must be distinguished from original saved
  scores; neither endpoint establishes complete task correctness.
- **Unnecessary use:** bd reads in goal sessions where the required value was already
  supplied in the prompt. Establish sessions have the same capture opportunity in
  both variants.

A PreToolUse hook supplies each Bash process with the actual tool-use/session/leg
identifiers. The bd wrapper records start and finish rows with actual argv, exit
status, and per-stream output bytes. The pinned-CLI mechanism check confirmed that
a compound remember/recall call produces two correctly associated receipts, while
the recorded conversation retains the original command without injected metadata.
This check is mechanism evidence, not spontaneous memory-use evidence.

Missing, malformed, unmatched, unfinished, or hidden receipt evidence stays explicit.
The handoff is a three-valued conjunction: a proven false component rules it out;
all proven true components establish it; otherwise it is unknown. Separate measurement
gap counts remain even when the outcome is decidable. Unknown outcomes are included
in scheduled-denominator lower/upper bounds. These missing-data bounds are not
confidence intervals.

Task-level contrasts pair matching work IDs, variants, and repeats. Bootstrap samples
resample work IDs while retaining their twins, repeats, and conditions. Both treatments
are compared with generic guidance, and redirect is compared directly with explicit
guidance. Intervals with few task clusters are descriptive; repeated sessions do not
create additional independent tasks. Results retain per-task rows for inspection.

## Phase differences and limits

The four initial diagnostic sessions had no execution receipts and differing source
manifests; they are excluded from controlled comparisons. One separate pinned-CLI
mechanism session is also excluded.

The pilot exposed a stale redirect sentence that described `bd recall` as a query
operation. Before confirmation, the message was corrected to distinguish
`bd recall <key>` from `bd memories <query>` and to quote the single remember content
argument. A docstring-only lint fix was made at the same phase boundary. The prior
unexecuted confirmation plan remains in `confirmation-plan-before-hook-fix/`.
This means the pilot's redirect condition is not byte-identical to confirmation.

The receipt wrapper preserves bytes within stdout and stderr but buffers and replays
the streams separately; it does not preserve their interleaving when a shell merges
them. Receipt files are an observation mechanism, not protection against an agent
intentionally forging harness files. The harness measures bd CLI use through Bash,
not a separately exposed MCP memory tool. Synthetic opaque values prevent guessing
but can be mistaken for lookup keys; such capture/interpretation failures remain
part of the results rather than being repaired post hoc.
