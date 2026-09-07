# Memory lifecycles: correct work, mutable history

**All 96 configuration artifacts passed. The selective instructions and completion
guard did not improve task correctness over the existing successful procedure in
this sample.** They also did not eliminate unnecessary historical-note rewrites or
unsupported explanatory prose. We have stronger evidence for an explicit handoff
workflow, and concrete remaining weaknesses in preserving the memory itself.

This is a new experiment following the [earlier 80-session investigation](memory-routes-experiments-2026-09-06.md).
Those results remain unchanged and are not pooled with these 96 sessions. The
[frozen design](plans/archive/0001-memory-lifecycle-comparison.md),
[independent measured report](../memory-bench/results/memory-routes/2026-09-06-lifecycle-final-analysis-02/report.md),
and [trace audit](memory-lifecycle-trace-audit-2026-09-06.md) retain the distinction
between actual work, procedural compliance, and memory fidelity.

## What ran

Four domains—cache, CSV export, image export, and logging—each ran under three
procedures: the previous successful protocol unchanged; that protocol plus
selective-capture guidance; and selective capture plus workflow-check guidance,
a task-closure wrapper, and a real Claude Code Stop hook.

Each lifecycle contained eight fresh sessions: establish an agreement, reuse it by
direct lookup, reuse it by search, permanently revise one field, reuse the revision
by direct lookup, reuse it by search, reproduce a fully supplied agreement, and
reproduce the original historical agreement. Revisions covered integers, a boolean,
and a fractional value. Every later session received the entire actual saved memory
map, including any mistakes. Earlier task history and configuration files were
excluded; neither target records nor missing information were repaired by the harness.

This was **12 lifecycles and 96 unique real sessions**, primary model Sonnet 4.6,
Claude Code 2.1.263, `bd` 1.2.1, macOS, seed 20260907. Native automatic memory was
disabled. Five other-project memories competed with each target. Current and `.v1`
historical references were publicly specified, and agents had to create both.
That is an explicitly requested manual snapshot, not native version-history support.

All arms received the same explicit version and reproduction cues. The checked arm
added both instructions and enforcement, so its results cannot isolate the effect
of the hook. The [interface audit](memory-lifecycle-interface-audit-2026-09-06.md)
found a buildable architecture spike, not the proposed production Memory type;
these trials therefore retain the real legacy memory interface. They do not validate
the implementation of the [new Memory type proposal](https://github.com/gastownhall/beads/issues/5877).

## Measured outcomes

| Outcome                                               | Existing protocol | Selective capture | Selective + checks |
| ----------------------------------------------------- | ----------------: | ----------------: | -----------------: |
| Lifecycles meeting the predefined checks              |               4/4 |               4/4 |                4/4 |
| Exact final configurations                            |             32/32 |             32/32 |              32/32 |
| Complete initial current and historical captures      |               4/4 |               4/4 |                4/4 |
| Direct reuse, initial and revised                     |               8/8 |               8/8 |                8/8 |
| Search reuse, initial and revised                     |               8/8 |               8/8 |                8/8 |
| Correct permanent revision                            |               4/4 |               4/4 |                4/4 |
| Correct historical reproduction, current v2 retained  |               4/4 |               4/4 |                4/4 |
| Fully supplied tasks with zero agent memory calls     |               4/4 |               4/4 |                4/4 |
| Unrequested historical-body rewrites during revision  |           **4/4** |           **3/4** |            **2/4** |
| Agent memory writes / reads during the four revisions |            8 / 12 |            7 / 12 |             6 / 14 |
| Estimated CLI usage cost                              |           $1.8342 |           $1.8179 |            $1.8831 |
| Median session duration                               |           22.84 s |           23.41 s |            24.14 s |

All 72 reproduction sessions, including the 12 fully supplied controls, made zero
agent memory writes. No extra aliases or missing captures appeared. Necessary
reuse read the appropriate agreement before constructing the file. All 12 revisions
recovered the old agreement before applying the supplied field change. Search used
literal discovery followed by exact recall, including choosing between original and
revised records. No session reached a turn/budget limit or had unknown receipt evidence.

Total CLI usage estimate was **$5.5352622**, including usage attributed to Haiku 4.5
by the CLI. This used the existing subscription; it is not an additional billing
charge. Timing and cost differences are descriptive, not demonstrated efficiency gains.
The eight stages share one lifecycle; the sample is four paired lifecycles per arm,
not 32 independent reliability trials per arm.

The earlier protocol controls saved duplicates after acting. Here, even the existing
protocol's controls performed no memory work. Clearer shared reproduction cues are
a plausible explanation, but the tasks and lifecycles also changed. This comparison
does **not** establish that the added selective paragraph caused that improvement.

## What the artifact scores missed

**Historical values survived, but historical prose was often rewritten.** In nine
of twelve revisions, the agent wrote the `.v1` note again while updating the current
agreement. All nine kept its original JSON and source label; all changed its prose.
None read the existing historical note before replacing it. They reconstructed it
from the still-original current agreement. The predefined literal-history check
passes these cases; it did not claim to enforce byte-for-byte historical preservation.

The checked arm reduced this write count descriptively, but its four revisions made
20 memory calls, the same as the existing arm; selective made 19. The guard accepted
the history rewrites because historical immutability was outside its checks. No
procedure eliminated them.

**Readable commentary can introduce claims the approval never supplied.** The
selective image note added a claim that quality 72 was not a conventional default.
During revision that remark was copied into the historical record, where it had
not previously existed. Selective logging included an unsupported comparison to an
`info` default under a supplied-facts label; its later history rewrite removed that
commentary. Existing image notes added a quality-scale assumption absent from the
contract. These may include reasonable domain assumptions; they are not established
by the supplied approval. None changed the graded configuration values. The problem
is unrequested historical mutation and unmarked interpretation, not a claim that
every rewrite made the content worse. Exact examples and before/after evidence are
in the [trace audit](memory-lifecycle-trace-audit-2026-09-06.md).

## What the guard established

The guard used public task requirements, actual files and memory, and this session's
CLI receipts. It received no hidden expected configuration. For designated captures
it required an accepted write, later exact readback, and a surviving record matching
the actual artifact. For reuse it checked a recalled matching record; revision
required a prior recall of the public current key. It checked closure and stopping,
not every possible side effect. Successful CLI readback alone is not proof of model
attention or correct application.

The separate [real-CLI mechanical controls](../memory-bench/results/memory-routes/2026-09-06-lifecycle-gate-smoke-01/result.json)
showed that missing capture, malformed saved content, and absent readback each
prevented task closure. Correct write/readback permitted closure. Direct Stop-hook
checks blocked incomplete/unclosed work and accepted completed work. These controls
used synthetic attribution and **zero model calls**; they establish tool behavior,
not agents recovering from injected failures.

The decisive counterexample also behaved correctly: a wrong but internally
consistent configuration and memory passed the guard, while the independent
approved-contract grader failed the configuration. **Consistency is not truth.**
All 32 natural checked sessions passed closure and Stop on their first attempts;
there were no live guard denials. Thus the experiment shows the guard can run with
successful work, but provides no measured incremental correctness or recovery benefit.

The guard added **64 administrative memory snapshots and 32 task queries**, taking
25.82 seconds across its checks. Its four fully supplied controls alone added eight
memory snapshots and four task queries despite zero agent memory calls. The snapshots
were consumed by the guard after acting, not delivered as agent recall evidence.
This overhead must remain visible when judging selective use. Host termination and
Stop-loop limits also bound enforcement; a hook declaration is not a guarantee that
every session must finish successfully. [Claude hook behavior](https://code.claude.com/docs/en/hooks).

## Smallest useful next changes

1. **Keep the successful handoff procedure and make the task occasion explicit.**
   State whether work establishes a durable agreement, permanently revises it, or
   reproduces it, and whether current or historical behavior is required. Preserve
   the information later context cannot supply. Use exact lookup when the reference
   is known, otherwise scoped search followed by the complete body. The current
   results support this workflow; they do not show that more instructions improve it.

2. **Protect approved source content and historical records mechanically.** Store a
   faithful approved record and keep interpretations distinct. Make an old version
   immutable, or reject an unapproved change against its actual prior content/hash.
   Updating the current agreement should not rewrite its historical snapshot.
   For new capture, comparing memory only to the agent's own artifact is insufficient:
   where the approved source is available, use that source as the fidelity reference.
   These are proposed changes, not capabilities validated by this run. Preserve
   readable previews; do not impose JSON on unrelated kinds of memory.

3. **Make completion checks conditional and judge their benefit separately.** Apply
   them where a memory handoff is explicitly required. Avoid querying memory on a
   fully supplied reproduction merely to run a generic guard. If protected history
   is part of the requirement, validate its preservation explicitly. Test missing
   and incomplete captures plus actual agent recovery, while continuing to grade
   subsequent work independently. Do not turn successful receipts into a semantic
   truth certificate.

4. **Validate normal work and the real type before claiming general reliability.**
   These trials did not test automatic recognition of useful lessons, ordinary
   native-memory competition, another primary model/host, large ambiguous stores,
   or the production Memory type. Those are distinct next validation steps. Keep
   the transcript-and-feedback loop recommended after Atbrace's attributed account:
   these traces exposed curation and prose defects that adoption counts missed.
   His transcript volume/adoption claims remain unverified here; remembered tool
   avoidance remains an unobserved hypothesis.

## Artifacts and verification

The [driver](../memory-bench/scripts/memory_lifecycle_experiment.py),
[corpus](../memory-bench/membench/runner/memory_lifecycle_corpus.py),
[public-input gate](../memory-bench/membench/runner/memory_lifecycle_gate.py), and
[independent reporter](../memory-bench/scripts/memory_lifecycle_report.py) are
experimental additions. The earlier driver gained optional guidance, hook, and
terminal-budget handling; its existing behavior remains the default. Known budget
limits are retained as failed trials, not silently censored as infrastructure errors.
All stores and model workspaces were isolated scratch state. No production memory
feature was installed, and earlier result artifacts were preserved.

[Verification](../memory-bench/results/memory-routes/verification-lifecycle-2026-09-06-01/SUMMARY.md)
passed 287 targeted tests, full Ruff/Black/strict mypy, and explicit checks on the
four affected experiment scripts. Earlier unrelated Python platform failures on
this Mac remain documented; the full unrelated suite and unchanged TypeScript
suite were not rerun. The previous TypeScript 908-test result remains prior evidence.
The first new plan refused a tuple/list serialization mismatch before any model call;
that plan was retained, corrected code received a regression test, and the actual
96 sessions ran under a new frozen manifest. No interrupted paid session was repurchased.

Reproduction uses a new output directory from `memory-bench/`:

```bash
.venv/bin/python -m scripts.memory_lifecycle_experiment --out results/memory-routes/new-lifecycle
.venv/bin/python -m scripts.memory_lifecycle_experiment --out results/memory-routes/new-lifecycle --fire --max-cases 12 --workers 2
.venv/bin/python -m scripts.memory_lifecycle_report --run results/memory-routes/new-lifecycle --out results/memory-routes/new-lifecycle-analysis
```

The first command freezes without invoking a model. The driver remains configured
for this local Mac, not a portable replacement for the shared adoption harness.
