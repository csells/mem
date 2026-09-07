# Memory handoffs across installed coding CLIs

Frozen coverage: Claude Code 2.1.263 / Sonnet 4.6 and Codex 0.153.4 /
gpt-6-astra (high reasoning, requested fast tier), **six lifecycles / 48 sessions**.
Gemini reaches a depleted-credit billing gate; Copilot's launcher has no actual CLI.
OpenCode's existing Qwen/Ollama configuration runs, but both real smokes fail and
server logs prove input truncation (7,301 tokens to 2,050). Even the four-tool
diagnostic cannot fit its current context. Preserve these preflight outcomes and
72 blocked candidate slots; do not reinterpret truncated-input trials as a test
of the memory handoff. No model, server, global configuration or account was changed
to make the blocked profiles qualify. Normal mode means feature defaults in fresh
isolated state, not importing the user's personal memory history.

The preceding [96-session experiment](../../specs/memory-lifecycle-experiments-2026-09-06.md)
is complete. Its frozen sources, raw evidence, and verification remain unchanged.
This is a separate authorized extension, not an expansion of that sample.

## Question and bounded comparison

Can the same explicit memory handoff procedure produce correct later work through
the installed Claude Code, Codex, Gemini CLI, OpenCode, and GitHub Copilot CLI?
Installation, local credentials, authenticated execution, and measured memory
performance are distinct coverage states. A blocked host remains in the report.

Before freezing model trials, verify versions, model selection, native-memory
behavior, headless output, and authentication through existing accounts. Exercise
each usable adapter with a short isolated real smoke, retaining failed attempts.
Do not automatically retry interrupted calls or substitute models. Host/model
differences remain confounded unless the actual models match.

The intended bound is two typed domains (cache and image export), eight fresh
sessions each per usable host, with native memory disabled or absent. A separate
eight-session cache lifecycle per host leaves its ordinary native-memory feature
at its installed default in isolated state. This is at most **120 scored sessions**
across five hosts, plus bounded adapter smokes. A host with no native-memory feature,
or with that feature normally disabled, is reported as such; the normal condition
must not silently enable it. Available hosts, exact model IDs, native settings,
timeouts, usage limits and source/binary hashes are frozen before scored calls.

The eight stages reuse the existing corpus: establishment, direct reuse, search
followed by full lookup, permanent revision, revised direct reuse, revised search,
fully supplied reproduction, and historical reproduction. Carry the entire actual
Beads memory map forward, including omissions and mistakes. In the normal condition,
also carry only actual isolated native-memory records; never carry old task files,
session transcripts, approvals, or a manufactured correct note. No source answers
or grader files are readable from the model sandbox.

## Procedure and independent outcomes

Use the selective handoff procedure from the completed experiment, with an explicit
instruction to preserve historical records unchanged and keep unsupported commentary
out of approved source content. This is a newly tested package; do not attribute its
results to one added sentence or pool its results with the previous experiment.
Each mode truthfully describes its native-memory setting. Ordinary reproduction
does not create another memory. Direct references use exact lookup; discovery uses
scoped literal search followed by the complete body.

Reuse the independent artifact and capture graders and the cumulative lifecycle
checks. Separately report capture omission, information loss, retrieval, application,
historical body mutation, source/prose fidelity, and unnecessary reads/writes.
Successful configuration values do not establish semantic truth of all saved prose.
Protect original denominators, unknowns, unsuccessful trials, and costs that a host
cannot report. Session stages share a capture and are not independent reliability
trials. A public consistency check is diagnostic, never a hidden-answer oracle.

## Host plumbing and verification

Keep old frozen runtime sources unchanged. Add small adapters for launch settings
and native event streams. Apply the same isolated Beads wrapper to all new hosts.
Unique execution markers in completed shell output associate raw CLI receipts with
real host tool IDs; missing or ambiguous associations remain unknown. Attribution
alone does not prove that the full memory body reached the agent. Preserve raw
streams, exact CLI stdout/stderr, mapping evidence, actual snapshots and final files.

Unit checks must challenge mismatched identities, truncated output, failed writes,
wrong artifacts, missing captures, accidental answer carryover, and interrupted-run
preservation. Real isolated CLI smokes verify the adapter/authentication boundary
before main calls. Outer filesystem isolation protects the user workspace, global
configuration and data. Existing authentication may be supplied transiently or as
a restricted scratch-only copy; credentials never enter report artifacts.

The final report supplies a CLI/model coverage matrix, measured denominators,
native-memory conditions, known usage/costs, concrete blockers, and the simplest
procedure supported by the evidence. This still tests legacy Beads keyed memory,
not the proposed new Memory type or unrestricted production reliability.

## Execution closed: measured coverage and remaining gaps

The frozen `2026-09-06-hosts-01` run ended with 44 completed model sessions out of
48 planned. Five lifecycles finished; Codex's isolated image-export lifecycle
halted after revision because four Python subprocess readbacks discarded the
receipt markers needed for host attribution. Its four later stages were not
launched or repurchased. Every executed configuration is correct. Two Claude
cache revisions changed historical prose despite the preservation instruction.
The frozen conditions, all prior evidence, and the branch remain preserved.

The [final report](../memory-hosts-experiments-2026-09-06.md) and
[independent analysis](../../memory-bench/results/memory-routes/2026-09-06-hosts-final-analysis-01/report.md)
retain the full denominators and the 72 preflight-blocked candidate slots.
Validation across all five hosts remains incomplete: Gemini billing, the missing
Copilot executable, and OpenCode context delivery need resolution before a new
cohort. Reliable historical preservation and subprocess-safe attribution also
remain open. These are follow-ups, not permission to rerun or alter this cohort.
