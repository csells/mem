# Selective memory capture and completion checks

Completed 6 September 2026: all 96 planned sessions and independent verification
finished. See the [results and recommendations](../../memory-lifecycle-experiments-2026-09-06.md).
The original bounded design follows; its later validation items remain outside this run.

Frozen design before model calls, 6 September 2026. This is the next authorized
experiment after the [memory-route investigation](../../memory-routes-experiments-2026-09-06.md).
Previous results and verification are preserved. New code extends the local
experiment driver; no production memory implementation or live store changes.

## Decision

Can the successful handoff procedure preserve correct subsequent work while
avoiding duplicate curation, and can a small completion check catch incomplete
handoffs without being given the hidden answer?

Three arms receive identical tasks and the same ordinary bead workflow:

1. Existing: the previous command examples and complete successful procedure,
   unchanged.
2. Selective: existing plus an explicit distinction between new durable decisions,
   permanent revisions, and reproduction of an existing agreement.
3. Checked: selective plus workflow-check guidance, a wrapper around task closure,
   and a Stop hook checking public requirements against actual files, memories,
   and this session's execution receipts.

The third arm tests a bundle of guidance and enforcement, not the isolated causal
effect of a hook. All arms receive explicit public version/reproduction cues.
These clearer tasks may improve the existing arm too; a null difference is valid.

## Schedule and limits

Four domains (cache, CSV export, image export, logging), seed 20260907, three arms,
eight sequential fresh sessions per lifecycle: **12 lifecycles, 96 sessions**.
Stages are establish, direct reuse, search reuse, permanent revision, revised direct
reuse, revised search reuse, fully supplied reproduction, and historical reproduction.
Revisions exercise integers, a boolean, and a fractional value. Domain/arm order is
randomized reproducibly. Two lifecycles run concurrently at most; the first batch
is inspected before purchasing the rest. Each session retains the previous
$0.75 CLI budget and 180-second timeout. Usage estimates are subscription telemetry,
not an assertion of additional billing charges.

Model/CLI/binary are pinned by version and SHA-256 when freezing the manifest.
The expected environment is Sonnet 4.6, Claude Code 2.1.263, production bd 1.2.1,
on the same Mac. Native automatic memory remains disabled to isolate the procedure.
An interrupted lifecycle is never silently rerun; its evidence remains recorded.

The [interface audit](../../memory-lifecycle-interface-audit-2026-09-06.md) found the
new Memory type still proposed, with only an architecture spike. Thus this run
uses real production legacy keyed memory and **cannot validate the new type**.
Both current and historical `.v1` references are openly specified in the initial
task. The agent must save them; the harness does not manufacture a history record.
This is manual snapshot retention, not native version-history testing.

## Carryover and grading

Only the entire actual saved memory map crosses each session boundary, including
bad records, mutations, and unwanted aliases. No target memory or perfect reference
is inserted by the harness. Initial stores contain five unrelated-project decoys.
Earlier task records and workspace artifacts do not cross. Later direct references
come from the public agreed naming convention; search prompts omit the key. No
hidden expected configuration is put into the sandbox or completion-check policy.

The primary endpoint is a complete lifecycle: correct final artifacts at every
stage, complete current and historical contracts retained, correct retrieved
payload delivered when needed, task closure, and no unwanted memory curation during
reproduction. Primary outcomes are four paired lifecycles per arm; the stage counts
share captures and are not independent reliability trials.

Report separately: exact capture, missing/incomplete records, retrieval and ordering,
actual application, permanent revisions, historical preservation, extra keys,
same-key rewrites, correct fully supplied work, pre-action reads, and post-action
curation. Procedural gate compliance is diagnostic, not a substitute for correct
work. Count actual gate denials, administrative bd queries and latency separately
from agent memory calls. Preserve unknown outcomes and denominators.

The guard checks configuration well-formedness and equality with actual surviving
memory; required accepted writes followed by exact CLI readback; and, when needed,
prior recalls. On search legs it may match any surviving recalled record to the
artifact rather than receive a hidden target key. Revision requires recalling the
public current key before its update. It cannot determine arbitrary factual truth,
autonomously recognize durable decisions, guarantee model attention, prevent every
side effect before retrieval, enforce history immutability, or suppress duplicates.
Writable instrumentation is not a security boundary. Stop hooks can be overridden
by host loop/termination behavior, so only a recorded successful check establishes
an enforced completion; missing hook evidence is not a pass.

## Checks before trusting the run

Unit tests cover actual carryover, withheld answers, gate receipt integrity, and
adversarial capture. Mechanical controls use a real isolated bd store and wrapper
to show missing capture, malformed content, and absent readback cannot close a
designated task, then demonstrate successful completion after repair. A wrong but
internally consistent artifact/memory must pass the procedural check while failing
the independent approved-contract oracle. These are tool checks, not agent trials.
An independent report recomputes final artifact and snapshot grades from frozen
expected values, checks cumulative transfer, and audits actual receipts/transcripts.

Broader models/hosts, normal native-memory competition, automatic decision
recognition, realistic large stores, and the actual new Memory type remain later
validation. This experiment is designed to answer a bounded next question, not
establish unrestricted production reliability.
