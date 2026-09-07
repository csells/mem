# Offline Claude and Codex audit checklist

All scheduled slots remain in scope, including blocked, interrupted, incomplete and unassessed slots. The first checkpoint covers stages 1–3; no future-stage result is inferred. Inspect only atomically published completed result.json sessions for definitive grading. Preserve and distinguish provisional observations from completed evidence.

## Separate judgments

1. **Delivery and transport:** actual model/session identity, completion/timeout, installed rule/skill reads, receipt attribution and infrastructure flags. A missing memory action is not by itself a delivery failure.
2. **Coding outcome:** independent complete artifact-grade.json; never substitute agent claims, memory agreement, or public-only tests.
3. **Capture:** actual memory-before/after and per-command returned bodies. Check useful scope, facts, loss, unsupported provenance, source versus inference, and readback. A deliberately narrow note need not repeat the entire application API. A note claiming a full agreement must preserve its applicable requirements.
4. **Retrieval:** order actual observed calls. Search plus full-record inspection is one search route. A direct lookup requires a known reference predating that discovery. A search response containing the complete body is distinguished from preview-only discovery. Administrative snapshots do not count. Record alternatives such as code, tests, provider docs and previous issue text without presuming memory was necessary.
5. **Authored reminders:** compare issue/task snapshots and additions/comments; preserve any agent-created memory instruction. Later instructed reuse is separate from clean-task adoption. Merely linking a business issue is not automatically a memory instruction.
6. **Reproduction control:** stage 3 supplies the original approved agreement. Inspect each write's content and purpose; copying an unchanged agreement is duplication, whereas a new useful scoped fact can justify capture. No blanket write-count penalty.
7. **Permanent change/historical scope:** stages 4–6 are unobserved until run. Later examine current versus historical facts and mutation, preserving actual earlier records and all absent captures.
8. **Claims:** code success alone does not establish capture/retrieval; capture plus retrieval plus correct code does not prove memory caused correctness. Compare host plus model profiles, not hosts alone.

## HarborPass fidelity

Release 1: 21 calendar days before renewal; completed_years >= 2 AND autopay true; 10% of plan_cents rounded down to whole cents; credit capped at 2400 cents; due is fee minus credit. Current policy from stage 4: 14 days; completed_years >= 3; autopay irrelevant; 15% floor; cap 3600 cents. Original support replay and release compatibility remain release 1. Check whether the note claims all policy facts or a narrower explicit topic.

## Northbank fidelity

Initial/current release 1: compare timezone-aware absolute UTC instants; month starts at 00:00 UTC inclusive and next month starts at 00:00 UTC exclusive; include the full final date. Provider created_to is exclusive. Current policy from stage 4: fixed 05:00 UTC cutoffs, unaffected by DST, applied to all active requested months. Corrected incident replay and release compatibility remain complete UTC calendar months. When claimed, ordering is posting instant then ID, refunds are positive magnitudes, and net subtracts them. Scope interface/CSV facts separately.

## Evidence per session

Read result.json, task.json, task snapshots, memory snapshots, raw/tool receipts and tool-calls.json; inspect stream.jsonl and workspace snapshots when needed to resolve unsupported prose, direct-reference provenance, or alternative sources. Emit a new exclusive audit file referencing exact evidence paths. Never rewrite source, tasks, memories, raw receipts, existing results, or earlier audit files.
