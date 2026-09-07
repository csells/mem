# Installed memory workflow trace audit

Status: all four lifecycle audits are complete. All 32 planned sessions ran and
have completed assessments; none are missing or skipped. This audit supplements
the per-session assessments and the offline action audit without replacing or
altering frozen evidence. The two integration smokes remain separate observations.

Evidence root: [2026-09-06-e2e-01](../memory-bench/results/memory-routes/2026-09-06-e2e-01/).
The manifest fixes 32 session slots in four correlated eight-stage lifecycles.
The two integration smokes are separate. Gemini, OpenCode, and Copilot retain
their previous coverage blockers and have no scheduled slots in this screen.

## Claude explicit: eight completed stages

All eight components implement the tested cache behavior and preserve the exact
named SOURCE and RATIONALE fields. All eight fail the exported POLICY contract:
they export the inner cache settings and omit the outer project identifier and
cache nesting. The public README requires that complete nested structure. The
first agent's tests assert its flattened interface, and subsequent agents read
that code before implementing siblings. These are correlated application errors
following one initial implementation, not eight independent capture failures.

Both retained original notes contain the complete nested agreement. Revision
updates the existing standing key to the exact revised agreement. The separately
named original note stays byte-identical throughout the lifecycle. Both actual
agent-authored successor tasks cite the real standing key and explicitly require
a complete nested POLICY. Faithful memory and correct task references did not
prevent incomplete subsequent work.

The initial author skipped the procedure's search-before-write step. The revision
did search, full lookup, an existing-key update, and readback. Both search stages
initially used a long literal phrase that matched nothing, then shortened the
query and obtained the right full record. Historical reproduction searched by
the original approval identifier and fully recalled the historical record.

There were 19 agent memory reads and four accepted writes: two initial captures,
one permanent revision, and one unnecessary identical resave in revised search.
That resave changed no memory-body bytes and was followed by readback. Five of
six reproduction stages made no writes; the sixth added no new record identity
but did unnecessary work. The fully supplied task searched and recalled the
current agreement before writing its component, despite having the complete
agreement in its task. It made no memory writes.

The CLI usage estimate was $1.6446794. All eight sessions ended successfully and
closed their tasks; those statuses do not turn the failed artifact checks into
passes.

The retained approval/source/rationale claims were supported by the supplied
facts. Surrounding narration was less reliable: the initial final answer called
the mutable legacy snapshot "immutable"; search claimed exact reproduction
despite the flattened POLICY; revised search described its identical resave as
updating the agreement to v2; supplied reproduction described 50 tests as existing
tests although that total included its new tests. Exact field checks do not
certify these statements.

Evidence: each stage's `assessment.json`, `tool-calls.json`, `raw-receipts.json`,
`memory-before.json`, `memory-after.json`, `workspace-after/`, and `stream.jsonl`
under `cases/claude-explicit/`; actual successor bodies are in
`direct/task-before.json` and `revised_direct/task-before.json`. Root and an
independent agent reviewed these artifacts without changing them or rerunning
model sessions.

## Claude installed: eight completed stages

All eight components pass the tested runtime behavior and exact named SOURCE and
RATIONALE checks. Three also preserve the complete exported POLICY: revised
direct, revised search, and fully supplied reproduction. The first four stages
and historical reproduction flatten POLICY and omit the outer project identifier
and cache nesting. Those five remain artifact failures despite correct runtime
behavior and faithful retained memories.

| Stage          | Complete artifact | Native Beads skill | Full memory-reference read | Agent memory reads | Accepted writes |
| -------------- | ----------------- | ------------------ | -------------------------- | ------------------ | --------------- |
| Establish      | Fail: flat POLICY | Yes                | Yes                        | 4                  | 2               |
| Direct         | Fail: flat POLICY | Yes                | No                         | 1                  | 0               |
| Search         | Fail: flat POLICY | Yes                | Yes                        | 3                  | 0               |
| Revise         | Fail: flat POLICY | Yes                | Yes                        | 4                  | 1               |
| Revised direct | Pass              | Yes                | No                         | 1                  | 0               |
| Revised search | Pass              | Yes                | Yes                        | 3                  | 0               |
| Fully supplied | Pass              | Yes                | No                         | 0                  | 0               |
| Historical     | Fail: flat POLICY | Yes                | Yes                        | 3                  | 0               |

Native `Skill(beads)` calls succeeded in all eight sessions, and each native
stream contains the complete canonical skill body in a delivered user message.
Five sessions also successfully read the complete detailed memory reference,
through either its canonical `.agents/skills` path or the `.claude/skills` alias.
None read the main SKILL.md through an ordinary file-reading tool; native
activation delivered that entry point. These are different observations from automatic AGENTS.md loading,
which is not directly certified. All eight sessions ran `bd prime --no-memories`.

The initial author searched before writing, saved the complete nested agreement
under its chosen current key `catalog-api.response-cache` and historical key
`catalog-api.response-cache.v1`, then read both back. The revision searched, fully
recalled the current and original records, updated the same current key, and
verified the write. All required settings, types, source, and rationale were
retained. The original note's entire body stayed byte-identical across all eight
stages, and no earlier project files changed. No unsupported approval or
provenance claims were found in the retained bodies reviewed here.

The actual author-created direct task `trial-6ki` cites the current key, explains
its relevance, and explicitly requires a complete nested POLICY. It also repeats
the five configuration values in prose, creating another legitimate information
source. The revised direct task `trial-o56` cites the same actual current key,
requests the current v2 agreement, and again explicitly requires nesting. Neither
task or reference was supplied or repaired by the harness. Their bodies are
preserved in [direct/task-before.json](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/claude-installed/direct/task-before.json)
and [revised_direct/task-before.json](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/claude-installed/revised_direct/task-before.json).

There were 19 successful agent memory reads: nine `bd memories` list/search calls
and ten full recalls. The three accepted writes were precisely the two initial
captures and the permanent current-key revision. All six reproduction stages made
zero memory writes; fully supplied reproduction also made zero memory reads.
Historical reproduction searched by CACHE-17 and recalled the actual original
note before implementing, while leaving the standing v2 record unchanged. Its
later second search was additional verification rather than a necessary source
of the already retrieved original settings. The CLI usage estimate was $1.8740751.

Command ergonomics caused recoverable detours. Search and revision each attempted
the unsupported `bd memory list`, received an error, and recovered with documented
commands. Revised search attempted `bd memories list`, which is valid syntax for
searching the literal word `list` and returned no matches. It then listed memories
without a query and fully recalled the correct current record. That success is a
list-and-recall route, not a successful filtered query. These attempts are design
evidence, not justification to silently change the frozen CLI or permanently add
every guessed spelling. See the [revised search tool calls](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/claude-installed/revised_search/tool-calls.json).

### Where the artifact shape first changed

Revised direct is the first complete POLICY success. It recalled the current
record before reading the README and the earlier, still-flat `catalog_cache.py`
and `catalog_detail_cache.py`. It then exported the complete nested policy and
passed `POLICY["cache"]` to the engine. No earlier correct component was available
for it to copy. The author-created task emphasized nesting, but the earlier
failed direct task had also done so; this is not evidence of a newly effective
instruction treatment. See its [tool calls](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/claude-installed/revised_direct/tool-calls.json)
and [actual component](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/claude-installed/revised_direct/workspace-after/catalog_preview_cache.py).

Revised search subsequently read that correct preview component before recalling
the current agreement and producing another correct nested component. Fully
supplied reproduction read an older flat component, but still used the supplied
nested contract correctly without memory calls. Historical reproduction read old
flat v1 components and fully recalled the correct nested historical record, yet
returned to the flat export. Code-pattern influence is a plausible explanation
worth testing, but these traces do not isolate it causally. They show that correct
retrieval, a successful native skill call, and reading the full procedure are
each insufficient to certify correct application.

The three passes are correlated outcomes within one lifecycle, not three
independent confirmations that installed instructions outperform explicit
delivery. Stored facts remained accurate; final narration still needs its own
checks. For example, revised search reported adding eight tests, while its saved
test file defines nine and the executed suite grew from 40 to 49. No unsupported
stored immutability or approval claim was found in this arm.

Evidence for all eight stages is under [cases/claude-installed](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/claude-installed/),
including each `assessment.json`, `execution.json`, `tool-calls.json`, before/after
memory maps, preserved workspaces, and native stream. This independent audit read
the completed artifacts without modifying frozen inputs or rerunning sessions.

## Codex installed: eight completed stages

All eight components pass the independent runtime behavior, complete nested
POLICY, exact SOURCE, and exact RATIONALE checks. The first implementation already
exports the outer project identifier and nested cache settings, then passes only
`POLICY["cache"]` to the engine. Later agents read those correct sibling components
and the retained agreements. This is one complete lifecycle with a correct
initial example, not eight independent reliability trials or an isolated measure
of host effects relative to Claude's different model.

| Stage          | Complete artifact | Full skill file read | Full memory-reference read | Agent memory reads | Accepted memory writes |
| -------------- | ----------------- | -------------------- | -------------------------- | ------------------ | ---------------------- |
| Establish      | Pass              | Yes                  | Yes                        | 4                  | 2                      |
| Direct         | Pass              | Yes                  | Yes                        | 2                  | 0                      |
| Search         | Pass              | Yes                  | Yes                        | 2                  | 0                      |
| Revise         | Pass              | Yes                  | Yes                        | 9                  | 1                      |
| Revised direct | Pass              | Yes                  | Yes                        | 1                  | 0                      |
| Revised search | Pass              | Yes                  | Yes                        | 2                  | 0                      |
| Fully supplied | Pass              | Yes                  | Yes                        | 0                  | 0                      |
| Historical     | Pass              | Yes                  | Yes                        | 2                  | 0                      |

Each session explicitly read `.agents/skills/beads/SKILL.md` and the detailed
`references/memory.md` using shell `cat` calls. The complete canonical contents of
both files appear in successful tool outputs in all eight sessions. There are no
native Skill-tool calls in this arm. All eight ran `bd prime --no-memories`.
File-reading delivery therefore worked here; this does not establish native
skill activation or automatic rule loading by itself.

There were 22 successful agent memory reads: six filtered `bd memories` queries
and sixteen full recalls. The initial author searched before capture. Original
search and historical reproduction queried the project/approval identifier, then
fully recalled `catalog-api.response-cache.v1` before writing their components.
Revised search queried `catalog-api` and recalled the actual current key before
writing. Both direct tasks also recalled their referenced standing agreement
before writing. Fully supplied reproduction read the procedure and project files,
but performed zero memory reads or writes. All six reproduction stages made zero
memory writes.

The three actual accepted memory writes were two initial captures and one
permanent update to `catalog-api.response-cache`. The raw frozen counters show
five because they also count two successful `bd remember --help` calls, one in
establish and one in revise. Those calls display usage and do not write memory.
The table excludes them based on their actual recorded arguments and output;
the frozen evidence remains unchanged. Conversely, a genuine identical resave
must still count as a write even when the before/after maps match, as observed in
Claude explicit. See [establish/raw-receipts.json](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/codex-installed/establish/raw-receipts.json)
and [revise/raw-receipts.json](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/codex-installed/revise/raw-receipts.json).

Revision's nine reads include explicit verification work. It searched, recalled
both original records, read them again inside a script, updated only the current
key, verified that current body and the unchanged historical body, read the current
record for display, then recalled it again to compare against the actual exported
component before authoring the successor. Direct reproduction also performed a
second recall for a programmatic comparison of the exported policy and approval
fields. These reads have observed purposes; they are not all necessary discovery,
nor should their count alone establish waste. The final independent artifact
oracle remains necessary because agreement between an artifact and its remembered
source cannot establish that either matches the approved source.

The actual successor tasks `trial-rcp` and `trial-nn8` refer to the chosen current
key, explain its scope and version, and require full lookup and exact structure.
Each includes a real issue dependency on its producing task. These dependencies
relate work to work; the memory key remains a textual reference rather than a
production Memory Bead relationship. The revised successor repeats the approved
configuration values in prose, while directing its executor to recall the full
record for structure, types, source, and rationale. Earlier tasks and code also
remain legitimate alternative sources, so observed recall is not proof that
memory was the only possible route to correct work. The authored bodies are in
[direct/task-before.json](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/codex-installed/direct/task-before.json)
and [revised_direct/task-before.json](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/codex-installed/revised_direct/task-before.json).

Both initial notes contain the exact complete v1 agreement and are initially
byte-identical. The historical note's complete body stays unchanged across all
eight stages; the current note becomes the exact v2 agreement, including the
revised preview, source, and rationale. No earlier project files changed. The
review found no unsupported stored approval/provenance claim or unsupported
immutability assertion. Completion narration and recorded test totals checked
here are consistent with the saved artifacts and tool output.

Three shell commands failed before their intended work ran: initial successor
creation, direct's extra verification script, and the first revision script used
here-documents that zsh could not create inside the sandbox. Each reported
`can't create temp file for here document: operation not permitted`; the agent
recovered using a project-local temporary file or `python3 -c` and completed the
work. These are host/environment detours, not rejected Beads captures. They do
not appear in the Beads-only `failed_commands` count because the shell failed
before invoking those commands. See each affected stage's `tool-calls.json`.

Codex reported token usage but no dollar charge; cost remains unknown, not zero.
Evidence for all eight stages is under [cases/codex-installed](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/codex-installed/).
The audit read saved assessments, native streams, tool results, task references,
memory bodies, and workspace snapshots without changing frozen inputs or running
additional model sessions.

## Codex explicit: eight completed stages

All eight components pass the complete nested POLICY, exact SOURCE and RATIONALE,
and independent runtime checks. Both actual retained versions also remain exact.
Like Codex installed, this lifecycle begins with a correct nested implementation
that later agents can inspect. Neither Codex arm exhibited the application-shape
failures observed in Claude. This does not separate host effects from their
different models or establish a population success rate.

| Stage          | Complete artifact | Agent memory reads | Accepted memory writes |
| -------------- | ----------------- | ------------------ | ---------------------- |
| Establish      | Pass              | 5                  | 2                      |
| Direct         | Pass              | 1                  | 0                      |
| Search         | Pass              | 3                  | 0                      |
| Revise         | Pass              | 7                  | 1                      |
| Revised direct | Pass              | 1                  | 0                      |
| Revised search | Pass              | 2                  | 0                      |
| Fully supplied | Pass              | 0                  | 0                      |
| Historical     | Pass              | 3                  | 0                      |

The control package contains ordinary issue rules in AGENTS.md and ordinary
issue orientation in prime, with no registered memory skill or detailed memory
reference. The memory procedure arrives in each initial user prompt. There are
zero native Skill calls and zero skill/reference file reads, as intended; all
eight sessions run `bd prime --no-memories`. Those counts are not failures to
discover an installed skill, because this arm intentionally has none. See the
[control rules](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/codex-explicit/establish/workspace-before/AGENTS.md)
and [actual initial prompt](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/codex-explicit/establish/prompt.txt).

There were 22 successful memory reads: five filtered queries and seventeen full
recalls. Establish searched `catalog` and fully inspected two existing notes in
other cache scopes before retaining its new agreement. It chose
`catalog-api.response-cache` for the standing record and
`catalog-api.response-cache.CACHE-17-v1` for the original snapshot, then fully read
back both. Search queried `catalog` and recalled both current and historical v1
records before implementing. Revised search queried `catalog` and recalled the
current v2 record. Historical also queried `catalog`, then recalled the historical
v1 record and current v2 record before writing: its three reads are one query and
two full lookups, not three searches. Both direct stages followed their actual
task's standing reference before implementation. Fully supplied reproduction
explicitly recognized that its complete agreement required no memory lookup or
capture and made neither.

Three actual memory writes occurred: two initial captures and one permanent
revision of the same current key. Two `bd remember --help` calls account for the
raw counter's five writes; the [offline action audit](../memory-bench/results/memory-routes/2026-09-06-e2e-01/action-audit-01.json)
corrects these classifications without changing the frozen receipts. All six
reproduction stages made zero writes. Revision's seven reads include comparing
the original records and verifying both the updated current body and unchanged
historical body; they are not seven discovery steps. The initial notes are
byte-identical, and the complete historical body remains unchanged through the
entire lifecycle. Current memory becomes the exact revised approval, including
the preview, source, and rationale. No earlier project files changed.

The author-created follow-ups `trial-ulw` and `trial-l78` have real dependencies on
their producing issues, respectively `trial-b2t` and `trial-03x`. Their descriptions
cite the successfully retained current key, distinguish standing from historical
use, require full recall, and explain the shared project/scope. The revised task
also supplies the v2 configuration values as handoff context. These are actual
author decisions and additional legitimate information sources; the harness did
not synthesize them. See [direct/task-before.json](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/codex-explicit/direct/task-before.json)
and [revised_direct/task-before.json](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/codex-explicit/revised_direct/task-before.json).

Shell and filesystem restrictions again caused recoverable work. Five
here-document commands failed across establish, search, revise, and revised
search. Initial follow-up drafting also failed at a path outside the writable
project, and search attempted to read a test file that its failed script had not
created. The agent recovered using allowed project paths, direct file edits, or
`python3 -c`. Several interim test runs consequently exercised only the existing
tests; later runs included the newly created component tests. The final artifacts
and final reported test totals match the completed evidence. These seven failed
host-tool calls are separate from the Beads-only failure counter, which is zero
for this arm. They should not be described as failed memory writes.

No unsupported stored approval, provenance, or immutability claim was found in
the records reviewed. The final completion claims checked here are supported by
the actual artifacts and final tool results. Dollar cost remains unknown. All
eight sessions completed and closed their actual tasks; evidence is under
[cases/codex-explicit](../memory-bench/results/memory-routes/2026-09-06-e2e-01/cases/codex-explicit/).

## Completed screen and next useful changes

The final screen has four complete lifecycles and 32 completed sessions, with
the requested model observed and task closed in every session. All 32 implement
the tested runtime behavior and exact named approval fields. Nineteen satisfy the
full exported interface: Claude explicit 0/8, Claude installed 3/8, Codex installed
8/8, and Codex explicit 8/8. All thirteen remaining failures omit the outer policy
structure despite retaining complete memories. These failures remain failures.
The [frozen report](../memory-bench/results/memory-routes/2026-09-06-e2e-01/report-01.md)
and per-stage assessments preserve those denominators.

Across the 32 cohort sessions, the offline action audit identifies 82 actual
memory reads, thirteen actual writes, 26 filtered queries, one unfiltered list,
and 55 full recalls. Twelve writes are intentional: two initial records and one
permanent revision in each lifecycle. The thirteenth is Claude explicit's
redundant identical resave. All four historical bodies remain unchanged. The
action audit covers 34 executions because it also includes the two separate
integration smokes; their activity is not included in these cohort totals.

The smallest useful improvements, in order, are:

1. Add a public component-interface check that verifies required structure and
   field presence without supplying hidden approved values. The currently public
   tests and agent-authored tests allowed correct runtime behavior with a wrong
   exported interface. This would be a new tested condition, not a retroactive
   pass for this cohort.
2. Retain the demonstrated issue-to-memory procedure and its verified delivery
   paths: read relevant guidance, inspect the task, select and fully recall missing
   agreements, preserve approved changes faithfully, verify writes, and leave
   reproduction records unchanged. Keep instruction delivery and correct work as
   separate checks. Installed delivery worked on both admitted hosts, but did not
   establish universal compliance or an advantage over explicit prompting.
3. Keep transcript-driven action classification: separate help, queries, lists,
   full recalls, real writes, identical resaves, and pre-command shell failures.
   Address the sandbox's here-document detour before another cohort; the successful
   recoveries do not make that avoidable overhead disappear.
4. Validate the same author-to-executor handoff against the actual Memory type,
   including real task references, immutable revisions, and historical pins.
   Legacy keyed notes and textual references cannot establish those guarantees.

Reliability remains bounded by one small cache fixture, one lifecycle per
host/model/delivery combination, fresh scratch native-memory state, and access to
earlier correct or incorrect code and task history. The producing tasks explicitly
identify durable approvals and ask for successor authoring; spontaneous recognition
of useful knowledge during ordinary feature work is not established. The three
other installed CLIs remain blocked and untested in this screen. Compaction
recovery, mature native-memory competition, production concurrency, and broad
Memory-type lifecycle behavior are also untested. These are concrete limits on
what the measured success supports.

## Reporting boundaries

- Repeated complete-memory checks measure availability at successive stages;
  they are not independent captures. Count initial capture and permanent revision
  occasions separately.
- Retrospective v1/v2 content roles do not certify canonical-reference identity.
  Inspect the actual authored task, resolved record, and retained key history.
- A successful native skill call is different from a full reference read.
  Installed files and observed behavior do not directly certify automatic rule
  loading or actual compaction recovery.
- Command execution, visible output, and correct application are separate facts.
  Final artifact modification time is only an ordering diagnostic. Source and
  earlier tasks remain legitimate alternative information sources.
- A final memory map can miss an identical accepted resave. Receipts identify
  that work. Harness snapshots are administrative reads, not agent retrieval.
- The frozen report function reads completed lifecycle results. Until a lifecycle
  result exists, its saved stage assessments are omitted from its aggregate and
  appear unrun. Monitor actual assessment files during execution. A lifecycle
  marked `finished` can include skipped, missing authored-task stages; inspect
  individual statuses and retain the original 32-slot denominator.

## Proposed follow-ups, not tested treatments

The observed application error motivates a public interface-conformance check
that verifies required nesting and field presence independently of hidden approved
values. This cohort's artifact failures remain failures; adding that check would
require a new frozen condition. Earlier historical rewrites also motivate
mechanically protected versions in the actual Memory type. Neither improvement
is validated by this legacy-keyed-memory experiment.

Atbrace's transcript volume and adoption claims remain attributed practitioner
observations. They support a transcript-and-feedback improvement loop, not a
causal explanation of these failures. Remembered tool avoidance remains an
unobserved hypothesis. Workaround advice should carry version, circumstances,
and evidence; attempted commands should inform interface design without granting
ambiguous semantics a permanent API.
