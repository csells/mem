# Worked interaction: a task brings its relevant history

This is a proposed consumer interaction, not a shipped command or an observed agent outcome. The source content is real; task and memory IDs below are illustrative labels, not a proposed historical-address syntax.

## The source we actually have

The [raw-token task's source packet](../memory-bench/data/bd-real-memory-v1/raw_tokens/source_packet.md) identifies parent commit `3a8d18988ea5cdcb6bd3f1032ab22c9bdce4cb2b`, `src/codeprobe/core/executor.py`, lines 807–828. Its code copies an existing diagnostics dictionary, assigns task duration, and assigns token cost when available. The [later task](../memory-bench/data/bd-real-memory-v1/raw_tokens/goal_unbriefed.md) asks for raw input/output token counts while preserving existing diagnostics.

That excerpt establishes the code present in that snapshot. It does not establish a Python-version history, execution results, or a verified fix. A memory that adds those claims would exceed its evidence even if it cites the correct file.

## The proposed trace

1. An earlier worker deliberately records a useful observation or the task retains the source packet. If there is a Memory record, it retains the source identity and exact excerpt; any explanation is separately identifiable as interpretation. This example assumes that capture happened. It does not demonstrate that an agent will choose to do it.
2. A later task references the prior diagnostic-contract observation. Ordinary Beads task display returns the compact reference and its reason: preserving existing diagnostic fields. No body is automatically expanded by core.
3. An external task-loading consumer selects that reference within its own budget and explicitly reads the selected historical Memory version. A plain CLI user could make the same read. The consumer receives the exact body and records the returned identity/version; neither a title match nor a mutable key substitutes for the selected version.
4. The consumer presents the following task-context fragment:

```text
Relevant prior source: diagnostics assembly
Reason selected: this task must preserve existing diagnostics.
Historical source: executor.py 807–828, parent 3a8d189…
Memory identity/version: returned exact reference, recorded in receipt.

Excerpt:
    diagnostics: dict = {}
    existing_diag = completed.scoring_details.get("diagnostics")
    if isinstance(existing_diag, dict):
        diagnostics.update(existing_diag)
    diagnostics["task_time_seconds"] = float(completed.duration_seconds)
    if completed.cost_usd is not None:
        diagnostics["token_cost_usd"] = float(completed.cost_usd)

Evidence limit: historical source excerpt; execution not established.
Current applicability: not checked.
```

5. The working agent inspects the current source, makes the requested change, and performs relevant verification. The consumer logs what was delivered; actual tool results establish what was inspected or tested. Delivery alone is not credited as use.
6. A later revision changes the source. The historical record remains intact. A narrow consumer check can report that tracked source bytes changed, leaving applicability unchecked. Unchanged bytes would still not establish untracked runtime/dependency behavior. An explicitly historical question continues to receive the old version; a current-behavior question requires current evidence.

## What inspecting the fragment reveals

The useful material is already in prior work. The memory's added value is making it easy to find, address, and interpret later. Asking another model to invent a polished general lesson can add risk without adding information. Compare this route with direct source-packet retrieval before requiring a separate Memory record.

The selection is also an assumption: someone supplied the task reference. A comparison that gives only this consumer a perfect link would test privileged relevance information as well as delivery. The first delivery experiment must give equivalent pointers to the native and CLI arms; a subsequent end-to-end experiment must measure who creates the reference and at what cost.

A native-file view could present this same fragment with its provenance. That would test a different front door. It would not establish canonical write-back, synchronization, or concurrent-edit behavior.

## Failure and recovery

- Missing or unavailable selected version: report the unavailable reference; do not substitute latest silently.
- Packet budget exceeded: state which selected material was omitted; do not claim complete delivery.
- Record corrected: preserve the old version and cite the newly read version for current work.
- Consumer interrupted: receipts identify completed deliveries; retry does not create a new semantic memory.
- Missing source/dependency evidence: applicability remains unknown. Provenance is not a truth score.

This stays within the existing core/consumer boundary. It makes no Memory a task, no reference an instruction, and no automatic semantic extraction a core operation.
