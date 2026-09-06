# bd memory reliability experiment

> Results from the reference run of the harness in [README.md](README.md). Read that
> first for what a trial is, what the three conditions change, and how to run one
> yourself. "R4" below is our internal label for the task-prompt template all three
> conditions share.

**All 96 confirmation pairs / 192 sessions completed.** Explicit bd guidance plus
native-memory redirection produced the most bd handoffs, but no tested condition
made the complete bd workflow reliable across all necessary tasks.

**Bd adoption, successful action, and preservation of meaning are separate outcomes.**
Native memory can solve tasks without bd; a recalled token can still be misunderstood.

## Recommendation

For a workflow specifically requiring bd, use **explicit command guidance plus
native-memory redirection as the best tested starting configuration**: necessary-task
capture rose from 10/16 with explicit guidance to 15/16, and handoff from 8/16 to
12/16. Its incremental handoff advantage remains uncertain with eight task clusters.
Necessary action success was lower: 12/16 versus 14/16 with explicit guidance and
16/16 with generic guidance. This is an adoption recommendation, not evidence of
improved overall task completion. No untested protocol improvement is credited.

## Comparison and scope

All conditions share R4 prompts, tools, isolated stores, receipt instrumentation,
and CLI-default native-memory settings (`{}`). An establish session precedes a fresh
goal session; their working directory is cleared while memory stores survive.

| Condition | Environment |
|---|---|
| Generic | General persistent-memory guidance; native accesses observed |
| Explicit | Captured bd context plus correct remember/recall/search examples |
| Redirect | Explicit context plus a hook blocking native-memory accesses and naming bd commands |

Confirmation covered eight generated task IDs from four world seeds, two necessity
variants, three conditions, and two repeats: **96 pairs / 192 sessions**. The model
is `claude-sonnet-4-6`, Claude Code `2.1.261`, and bd is pinned by path, version, and
SHA-256. This measures bd CLI use through Bash, not a separately exposed MCP tool.

The two-task pilot's 12 pairs remain separate: its ambiguous `recall <query>` redirect
was corrected before confirmation to `recall <key>`, `memories <query>`, and quoted
remember content. Four diagnostic sessions and one instrumentation session are
excluded. Two confirmation task IDs appeared in the pilot. See [methods](METHODS.md).

## Necessary-memory results

Each condition completed 16 necessary pairs. Counts below use the full denominator.

| Condition | Capture | Observed recall | Recall before qualifying action | Strict bd handoff | Qualifying action |
|---|---:|---:|---:|---:|---:|
| Generic | 0/16 | 0/16 | 0/16 | 0/16 | 16/16 |
| Explicit | 10/16 | 9/16 | 8/16 | 8/16 | 14/16 |
| Redirect | 15/16 | 15/16, 1 unknown | 12/16 | 12/16 | 12/16 |

Capture and observed recall use frozen scores; ordering, handoff, and action use
the strict audit. Frozen redirect timing has one unknown; the strict audit rules
that case false because there was no qualifying Write.

Capture requires acknowledged token storage; recall requires actual bd output in
the matching tool result. Handoff adds delivery before successful action. This is
an observed conjunction, not causal dependence when another channel supplies the value.

| Necessary-task contrast | Handoff difference | Task-cluster 95% interval | Action difference | Task-cluster 95% interval |
|---|---:|---|---:|---|
| Explicit minus generic | +50 pp | [+18.75, +81.25] | −12.5 pp | [−25, 0] |
| Redirect minus generic | +75 pp | [+37.5, +100] | −25 pp | [−62.5, 0] |
| Redirect minus explicit | +25 pp | [−6.25, +62.5] | −12.5 pp | [−43.75, +12.5] |

Contrasts pair work ID, variant, and repeat. Bootstrap sampling resamples work IDs,
retaining twins and repeats. There are eight task clusters, not 192 independent
tasks; intervals are descriptive. Missing-data bounds are separate from confidence
intervals. Original and strict action/handoff outcomes agree for all 96 pairs,
so these paired outcome contrasts also describe the strict audit.

## Unnecessary reads and costs

Unnecessary goal prompts already contain the required value. Completing the action
without reading memory is desirable; a low handoff rate here is not a failure.

| Condition | Qualifying action / 16 | Goal bd read attempts | Goal sessions reading bd / 16 | Estimated USD, all confirmation sessions |
|---|---:|---:|---:|---:|
| Generic | 16/16 | 0 | 0/16 | $3.922 |
| Explicit | 14/16 | 16 | 5/16 | $4.802 |
| Redirect | 15/16 | 11 | 6/16 | $4.748 |

Confirmation cost estimates total **$13.471**, with complete final-session cost fields.
Mean CLI duration was 13.23/19.23/19.15 seconds for generic/explicit/redirect; these
are session durations, not end-to-end wall time. USD values are CLI estimates, not
subscription billing receipts. Native hook counts are differenced between legs.
The [complete analysis](reference-run/analysis.json) retains token/cache totals.

## Mechanisms visible in the traces

**Native substitution:** explicit `world-seed0-task1 / necessary / repeat 1` wrote
native memory files, made no bd writes, then read native memory and completed its
action. Task completion alone would conceal the absence of bd adoption.

**Meaning changed despite token preservation:** redirect `world-seed2-task1 /
necessary / repeat 0` stored a timeout token as an “issue/ref,” recalled it, attempted
to dereference it with `bd show`, and made no goal Write. Other inspected failures
rejected opaque configuration tokens as suspicious or inappropriate types, including
when the value was already in the unnecessary prompt. These are material limits
of synthetic opaque values, not evidence that bd corrupts facts.

**Omitted capture:** pilot redirect `world-seed0-task0 / necessary` searched but never
wrote the supplied facts; its fresh goal found an empty store and failed. Redirection
does not force a write. These are explanatory examples, not frequency estimates.
See [trace notes](reference-run/FAILURE_NOTES.md).

## Measurement safeguards and limits

The frozen goal contract is weak: an acknowledged Write's arguments must contain
the required token and exclude superseded tokens. It does not check the destination,
JSON structure, field placement, or every requested fact. A separate mechanical
audit requires a Write to lexical `cwd/config.json`, valid JSON, required tokens
in decoded string values rather than keys/filenames, and no superseded token. It
recomputes ordering using qualifying Writes only and preserves original scores.

The [audit using the frozen scorer](reference-run/action-audit.json) found
**zero contradictory action, ordering, or handoff verdicts**. After execution ended,
the scorer's qualifying-action predicate was corrected; a [separate v3 audit](reference-run/action-audit-v3.json)
again found zero discrepancies across all 96 pairs. Both retain their distinct source
provenance. The audit witnesses a qualifying Write event, not final filesystem state.
Neither endpoint judges full semantic fidelity. Receipt files are not an adversarial
security boundary; the wrapper preserves each output stream's bytes but not merged
stdout/stderr interleaving.

One receipt-coverage warning remains explicit: an untaken `||` branch in redirect
`world-seed1-task1 / necessary / repeat 0` was counted statically as a second bd
attempt. Its actual executed call has a receipt. The frozen recall/timing endpoints
remain unknown there; failed capture and action nevertheless establish failed handoff.
There are **no unknown primary action/handoff outcomes**, missing sessions, or timeouts.

The [manifest](reference-run/manifest.json), raw streams, receipts, analyses, and audits
retain reproducibility identities and source/input hashes. The [independent integrity check](reference-run/integrity-audit.json)
passed with the coverage warning documented. Completed pairs were not repurchased;
post-run scorer changes do not rewrite these saved scores.

These eight generated tasks support a bounded bd-adoption decision, not general
memory reliability. Broader claims need fresh repository tasks with ordinary typed
values and meaningful action checks.
