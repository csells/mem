# Four-host integration qualification — 2026-09-07

All four selected coding-agent CLIs can run the isolated harness with working
authentication, project instructions, skills, file/shell tools, and real Beads
storage. Eight sessions completed, with correct application artifacts in 8/8,
faithful payloads in 4/4 captured records, and unchanged records after 4/4 fresh
consumer sessions. **This establishes integration capability, not unprompted
memory adoption.** The integration tasks explicitly requested memory operations.
The proposed ordinary-task cohort has not started.

Claude, Codex, and zcode passed both complete smoke checks after correcting a
representation error in the grader. OpenCode completed useful work but failed
specific diagnostic instructions. Its failures remain in the results.

## Coverage and updates

| CLI           | Current version           | Observed primary model            | Completed sessions | Correct artifacts | Complete smoke checks |
| ------------- | ------------------------- | --------------------------------- | ------------------ | ----------------- | --------------------- |
| Claude Code   | 2.1.263                   | `claude-sonnet-4-6`               | 2/2                | 2/2               | 2/2                   |
| Codex         | 0.153.4                   | `gpt-6-astra`                     | 2/2                | 2/2               | 2/2                   |
| OpenCode      | 1.18.20                   | `ollama/qwen3-coder:30b-a3b-q8_0` | 2/2                | 2/2               | 0/2                   |
| zcode-app-cli | 3.11.2-21; runtime 0.16.5 | `zai/glm-5.3`                     | 2/2                | 2/2               | 2/2                   |

Only zcode required an update, from 3.10.2-18. The other three matched their
current stable update sources. Existing authentication was exercised successfully,
not inferred from installed executables. Configuration hashes remained unchanged
after updates; rollback material was retained. Gemini and Copilot are excluded
by user request. Paths, update commands, and supported headless profiles are in
the [inventory](memory-four-hosts-inventory-2026-09-07.md).

These are four **host plus model** profiles, not a controlled host comparison.
Claude's usage also records a Haiku helper. OpenCode's emitted usage excludes
its automatic title helper. zcode pins its configured lite helper separately.
An observed primary model does not establish that every internal request used it.

## What the integration tasks did

Each host received a new scratch Git project, real legacy `bd` 1.2.1 store,
project AGENTS and supported host entry points, and the Beads skill/reference.
The first issue asked for a small identifier-formatting utility: trim whitespace
while preserving leading zeros and case. It explicitly requested saving the
complete typed policy, searching, and reading the full record. A second fresh
session explicitly requested lookup, correct reproduction, no additional save,
and handling a deliberately missing key. Unique rule, skill, and reference
markers diagnosed instruction delivery. They are integration instrumentation,
not proposed ordinary-task prompts.

The harness retained actual code and memory between sessions. It never repaired
a capture. Hidden checks independently compared the JSON artifact's complete
structure and types with the expected policy and executed the formatter on two
inputs. Public tool receipts were correlated with the CLI process tree. Native
transcripts established session/model identity, completion, and tool results.
The marker check distinguishes receiving instructions from copying them correctly.

The stored payload was:

```json
{
  "project": "qualification",
  "identifiers": { "kind": "opaque-string", "trim": true },
  "examples": ["000417", "AC-019"]
}
```

Correct surrounding commentary or provenance is **not** certified by this exact
payload check. Existing code and task information also remained available, so
successful reproduction does not show that memory caused correctness.

## Measured outcomes and failures

- Scheduled, started, completed, and assessed: **8/8 sessions**, four paired
  integrations. No interrupted sessions, retries, or replacement trials.
- Successful CLI exit and observed completion with the requested primary model:
  **8/8**. Eight distinct sessions, including a fresh consumer for each host.
- Correct full application artifact and independent formatter checks: **8/8**.
- Faithful captured policy: **4/4**. Capture omission and literal information
  loss: **0/4** under explicit capture instructions.
- Successful real capture, search, and full lookup: **4/4 hosts** across each pair.
  Successful full lookup in fresh consumers: **4/4**; search in consumers: **3/4**.
  Keys were supplied for these integration checks; this is not independent route choice.
- Consumer record unchanged: **4/4**; duplicate consumer writes: **0/4**.
- Expected missing-key nonzero response observed and handled: **4/4 consumers**.
- Rule, skill, and reference delivery observed: **4/4 hosts**. Complete marker
  reproduction: **6/8 sessions**. Codex opened skill files; Claude and zcode used
  native skill tools. OpenCode's native skill result contained the actual marker.
- Corrected complete smoke checks: **6/8 sessions**, **3/4 host pairs**.
- Permanent revision, historical mutation, autonomous capture, and ordinary-work
  retrieval: **not tested by this qualification**.

OpenCode's capture session wrote `beads` instead of the skill's unique marker,
despite receiving the full skill containing that marker. Its consumer marker file
was also wrong, and it omitted search and `bd prime`. It nevertheless read the
saved record, handled the missing key, wrote correct artifacts, and left the
record unchanged. This is evidence of incomplete adherence to the diagnostic
instructions; we did not observe a failure to deliver the skill or execute the
memory tools. It remains a strict smoke failure, not a discarded trial.

The audited operations total four writes, ten memory queries, eight full recalls,
seven prime calls, two help calls, and five failed commands. Four failures are
intentional missing-key checks. These counts diagnose paths; they are not the
success metric. Sixteen administrative memory snapshots and eight administrative
task reads are separate from agent actions. Help is not counted as a write.

## Grader correction and preserved evidence

The original driver reported 0/8 strict passes. It incorrectly required the whole
memory body to parse as JSON. Claude, Codex, and zcode retained the complete JSON
inside readable prose or a code fence, which is a valid representation. The
corrected grader accepts a single complete outer JSON payload, rejects duplicate
keys, type coercion, and conflicting payloads, and leaves prose-only records for
semantic review. It does not certify surrounding prose.

A read-only audit corrects those six false negatives without changing original
grades or rerunning any model. OpenCode's two failures remain. A separate,
retrospective assessment records demonstrated transport, instruction delivery,
tool capability, and state transfer on all four hosts; it does **not** replace
the original strict admission criterion with an easier pass.

Evidence:

- [Original sessions, tasks, streams, receipts, outputs, initial grades, and first audit](../memory-bench/results/memory-routes/2026-09-07-four-cli-smoke-01/)
- [Current read-only audit](../memory-bench/results/memory-routes/verification-four-cli-2026-09-07-01/audit-02.json),
  with input hashes and an unchanged-input check. Its non-OpenCode runtime-context
  field is null: those hosts' effective server allocations were not measured.
- [Verification](../memory-bench/results/memory-routes/verification-four-cli-2026-09-07-01/SUMMARY.md)
  and [preflight evidence](../memory-bench/results/memory-routes/2026-09-07-four-cli-preflight-01/).
- [Host adapters](../memory-bench/membench/runner/memory_unprompted_hosts.py),
  [integration driver](../memory-bench/scripts/memory_unprompted_smoke.py), and
  [offline auditor](../memory-bench/scripts/memory_unprompted_audit.py).

The source was under development during qualification; per-host source/binary
hashes and original assessments are retained. The grader correction and owned
server startup cleanup are subsequent code changes. This is not a claim that
all eight sessions ran the final source tree of a frozen adoption cohort.

## Cost and isolation limits

| Host     | Two-session elapsed total | Reported cost                                  | Recorded token usage across the pair                                          |
| -------- | ------------------------- | ---------------------------------------------- | ----------------------------------------------------------------------------- |
| Claude   | 106.04 s                  | $0.35065 list-price estimate, including helper | 1,834 uncached input; 423,280 cache read; 26,135 cache creation; 4,346 output |
| Codex    | 93.84 s                   | Not emitted; existing subscription usage       | 198,931 input, including 183,680 cached; 2,859 output                         |
| OpenCode | 106.72 s                  | $0 provider charge; local compute not priced   | 360,377 step input; 2,808 output; title-helper usage excluded                 |
| zcode    | 180.52 s                  | Not emitted; existing provider authentication  | 272,403 input, including 248,192 cache read; 6,491 output                     |

Token fields follow each host's conventions; they are not directly comparable
cost units. There is no verified combined invoice total. Each CLI session had a
420-second wall limit. The ordinary-task cohort's enforceable limits and cost
estimate still need to be frozen before launch.

All checks used new scratch state and an external filesystem sandbox. Claude's
automatic memory and Codex's native memory were disabled in their isolated
profiles. OpenCode has no separate configured automatic extractor. zcode's
headless entry disables extraction even under normal defaults; this cannot stand
in for its desktop application's full memory behavior. The separate normal-native
cohort has not run. Global settings and personal memories were not reset.

OpenCode used a separate task-owned Ollama endpoint with the existing model bytes
read-only. `/api/ps` and the server log confirm an effective **32,768-token context**;
all logged completion entries report `truncated = 0`. The existing user server
was not reconfigured or restarted. The task-owned server was stopped afterward.

## Smallest next steps

1. Admit two independently authored ordinary task families and their executable
   graders. Review every agent-visible surface for task-specific memory cues,
   including issue comments and agent-created follow-ups. Preserve alternatives
   such as code and issue history.
2. Freeze the generic rules/skill package, exact host/model profiles, resource
   limits, and all cohort slots. Resolve OpenCode's outstanding strict diagnostic
   outcome explicitly at admission; do not label it a full pass or insert forced
   memory prompts to improve its score.
3. Run the proposed comparison with a 48-session checkpoint, retaining those
   sessions in the 96-session bound. Measure faithful capture and correct later
   work through independently chosen search and direct lookup. An unobserved
   route stays unvalidated. Keep the 24 normal-native sessions separate.

The intended procedure remains simple: generic standing guidance explains when
useful knowledge deserves capture, when missing knowledge deserves retrieval,
and when reproducing an agreement does not justify a new save. Syntax lives in
the shared skill and tool help. Whether that procedure works during ordinary
coding is the next experiment's question, not a finding of these explicit checks.
No result here validates the proposed new Memory bead type or production reliability.
