# Proposed end-to-end Memory Beads experiment

**Status: planned, not implemented or run.** This is a separate experiment from
the [paired adoption harness](README.md). There is no public runner or command
recipe for this cohort yet. The existing README's run commands execute the paired
experiment, not this proposal.

The question is whether an agent receiving an ordinary task assignment can
discover the installed Beads workflow, preserve an approved durable decision,
author a useful reference to it, and use the actual retained knowledge correctly
in later work. The test covers delivery and discovery as well as storage,
retrieval, application, and unnecessary curation.

## A small matched screen

The proposed screen has **32 session slots**: one eight-stage lifecycle in each of
two delivery arms on each of the two previously usable hosts, Claude Code and
Codex. At most one bounded integration smoke per host precedes the screen.

| Arm                | How the procedure reaches the agent                                                                                            |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| Explicit delivery  | The complete candidate procedure appears in the initial prompt.                                                                |
| Installed delivery | The prompt supplies only the task assignment; project rules, prime, the Beads skill, and task inspection deliver the workflow. |

Both arms use the same tasks, procedure semantics, tools, memory-body exclusion,
native-memory setting, and grading. The explicit arm keeps ordinary issue guidance
and tool help but does not also register or automatically load the candidate
memory procedure through skills or prime. This compares two delivery packages;
it cannot isolate the effect of one rule, hook, or skill description. Earlier
cohorts remain historical evidence, not a matched control.

Availability, models, CLI and source hashes, ordering, resource limits, and
interruption handling must be frozen before calls. Gemini's billing blocker,
Copilot's missing CLI, and OpenCode's context-delivery blocker remain visible until
resolved. Blocked or interrupted slots stay in the accounting. The screen does
not authorize changing user credentials, global configuration, models, or servers
to repair those blockers.

## One shared project package

Install one package in each disposable project fixture:

```text
AGENTS.md                               # short workflow occasions and skill pointer
CLAUDE.md                               # @AGENTS.md
GEMINI.md                               # @./AGENTS.md
.agents/skills/beads/SKILL.md             # canonical Beads workflow
.agents/skills/beads/references/memory.md # detailed memory branch
.claude/skills/beads                     # symlink to the canonical skill
.beads/PRIME.md                          # compact orientation and skill routing
```

Host entries share the same instructions; they are not five separately maintained
procedures. Verify imports, discovery, and actual content delivery against the
installed versions. A file's presence or an ordinary Markdown link does not prove
that it was loaded. Record native skill activation separately from an agent
explicitly reading the skill file.

The skill covers ordinary issue work and explains when to enter its memory
workflow: an absent prior agreement, a newly approved reusable decision, or a
permanent correction. Preserve exact identifiers, scope, values, types, units,
structure, and source where relevant. Keep a readable preview and distinguish
approved facts from interpretation. Use faithful prose for prose knowledge and
structured data for structured agreements. Not every memory needs JSON, and
completing a task does not by itself justify another memory.

Issue claiming and closure apply to the work. Memory records provide durable
knowledge with a separate lifecycle. Start without automatic capture or a
completion-blocking hook; those would be additional interventions.

### Prime must not supply the answers

For the legacy packaging test, use the real **`bd prime --no-memories`** command.
In installed `bd` v1.2.1, a custom `.beads/PRIME.md` replaces workflow text but does
not suppress appended memory bodies. `--no-memories` suppresses them;
`--memories-only` takes precedence over that flag and must not be combined with it
here.

Every configured startup or compaction hook must preserve this exclusion. Where
the host has no suitable project hook, the project rule supplies the explicit
command path. Check prime output with unrelated sentinel records before any model
calls. Injecting stored bodies automatically would bypass the retrieval routes
the experiment is intended to measure.

## Put the requirements in real tasks

The ordinary user request is approximately `Work on <task-id>`. Detailed feature
requirements, approval evidence, and the intended use of references belong in
the actual task body. Routine task requests do not supply capture keys or memory
coaching.

Use a small runnable service or CLI with independently testable behavior, such as
a cache adapter followed by another component governed by the same policy. Its
eight fresh agent sessions cover:

1. Initial approval and implementation.
2. Reuse through an agent-authored task reference.
3. Reuse by searching for the agreement.
4. A permanent revision.
5. Direct reuse of the revised agreement.
6. Search-based reuse of the revised agreement.
7. Reproduction with the complete agreement supplied.
8. Historical reproduction.

The producing agent must author a real follow-up task that explains the policy's
relevance and refers to the memory it actually created. Grade that task, the
returned identity, and the later handoff separately. An omitted memory, task, or
reference remains omitted; the harness must not manufacture it for the next
session.

Search tasks include plausibly overlapping notes and different wording of the
same agreement. The permanent-revision task supplies the project, scope, and
approved change, but **no memory key, ID, or link**. It tests whether the agent
searches, fully recalls the existing record, and updates that identity without
creating a duplicate. Grade the revised content and historical preservation
independently of record selection.

Carry actual project files, task history, Beads records, and condition-appropriate
native memory forward. Do not erase source evidence to force memory use. A later
agent may correctly recover an agreement from an earlier task, specification, or
code. That is a task success through an alternative source, not a demonstrated
memory handoff. Report whether memory was necessary for each task.

## What will be measured

Independent hidden expectations grade the resulting feature behavior. Separate
checks assess retained information, source fidelity, record identity, historical
immutability, and the quality of agent-authored references.

Traces must distinguish rules delivered, skill reached, task inspected, capture
attempted and retained, search results seen, full record delivered, information
applied, and current or historical state changed. Agent narration is not a receipt;
unknown attribution stays unknown. Automatic and harness reads are counted
separately from agent reads. Additional reads may be legitimate verification and
are not automatically waste.

Static checks and bounded integration smokes must establish project isolation,
rule and skill delivery, prime body exclusion, real task bodies, subprocess-safe
receipts, and rejection of wrong-but-mutually-consistent memory/artifact pairs.
The previous adapters deliberately suppressed project rules or skills; new modes
or adapters are needed without changing frozen experiments.

Report attempts, recorded sessions, complete lifecycles, blocked or unrun stages,
known and unknown costs, and instruction/tool overhead. Eight stages sharing one
capture are correlated observations, not eight independent reliability trials.
Use transcripts to explain failures before changing the package; retest a changed
package as a new cohort.

## What this cannot establish

This screen can exercise legacy keyed memory in `bd`. Its task references remain
text, and its historical notes remain mutable. It cannot validate the proposed
production Memory type's structured Bead References, canonical identity,
immutable revisions, revision pins, stale-write protection, or production
provenance. A shim is not that implementation.

The later production test must run the same author-to-executor handoff against
the actual Memory interface. This small screen first asks whether the shipped
workflow can be discovered and used through ordinary issue work. It is not a
claim of production reliability or spontaneous recognition of every useful
lesson.

The [design proposal](../../specs/memory-e2e-experiment-proposal-2026-09-06.md)
records the host documentation, candidate instructions, and remaining production
requirements.
