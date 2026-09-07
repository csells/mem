# Proposed agent integration experiment for Memory Beads

Status: proposal, not a launched cohort or an implemented integration. Existing
branches, runtime sources, frozen conditions, sessions, and verification remain
unchanged. This document answers how to make the next experiment resemble the
planned experience; its candidate instructions have not been behaviorally tested.

## What the next experiment should establish

Can a fresh agent start with an ordinary task assignment, discover the installed
Beads workflow, preserve an approved durable decision, and use the actual retained
information correctly in later work? Measure installation/discovery as well as
capture, retrieval, application, and unnecessary work.

The [completed host experiment](memory-hosts-experiments-2026-09-06.md) supplied
roughly 500 words of procedure directly in every initial prompt. Its 44 completed
sessions produced correct configurations, but two historical notes were rewritten.
These results establish neither instruction discovery nor production Memory-type
behavior. The [interface audit](memory-lifecycle-interface-audit-2026-09-06.md)
distinguishes the available legacy CLI and architecture spikes from that product.

## One project instruction package

Use this layout in new disposable project fixtures, not in the user's global
configuration or this investigation's operating instructions:

```text
AGENTS.md                              # short workflow occasions and skill pointer
CLAUDE.md                              # @AGENTS.md
GEMINI.md                              # @./AGENTS.md
.agents/skills/beads/SKILL.md            # one canonical Beads skill
.agents/skills/beads/references/memory.md # detailed memory branch
.claude/skills/beads                    # directory symlink to the canonical skill
.beads/PRIME.md                        # compact orientation and skill routing
```

Codex, OpenCode, and Copilot document direct AGENTS.md support. Gemini, Codex,
OpenCode, and Copilot document `.agents/skills` discovery; Claude documents skill
directory symlinks. Verify those mechanisms against the exact installed versions
in isolated smokes. File existence or a Markdown link is not evidence of loading.
Distinguish native skill activation from an agent explicitly reading its file.

Host documentation checked for this proposal:

| Host | Instruction entry | Skill discovery reference |
| --- | --- | --- |
| Claude Code | [`CLAUDE.md` imports](https://code.claude.com/docs/en/memory) | [Project skills and symlinks](https://code.claude.com/docs/en/skills) |
| Codex | [`AGENTS.md`](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | [`.agents/skills`](https://learn.chatgpt.com/docs/build-skills) |
| Gemini CLI | [`GEMINI.md` imports](https://geminicli.com/docs/cli/gemini-md/) | [Workspace skill discovery and activation](https://geminicli.com/docs/cli/tutorials/skills-getting-started/) |
| OpenCode | [`AGENTS.md`; links are not automatic imports](https://opencode.ai/docs/rules/) | [Shared and host-specific skill paths](https://opencode.ai/docs/skills/) |
| Copilot CLI | [`AGENTS.md`](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions) | [Shared and host-specific skill paths](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills) |

These are documented capabilities, not successful isolated integration smokes on
all five installed hosts. Gemini's workspace trust/skill activation and each host's
project configuration permissions must be exercised without changing user globals.

The canonical skill covers ordinary issue work and routes to the memory branch at
the relevant occasions. Memory remains durable knowledge with its own lifecycle;
issue claiming, completion, and closure apply to the work, not to the memory.
Generate host aliases and prime routing from one package; do not maintain five
independent versions of the procedure.

Candidate AGENTS.md addition, for the legacy packaging test:

> Use Beads for issue work and approved durable project knowledge. Follow the
> project Beads skill at `.agents/skills/beads/SKILL.md`. At session start or after
> compaction, run `bd prime --no-memories` if a project hook has not restored the
> workflow. Read the skill's memory workflow when a task depends on an earlier
> agreement, or when work establishes or permanently changes an approved durable
> decision. Retrieve missing agreements before implementing. Preserve newly
> approved reusable knowledge before completing its issue. Reproducing an existing
> agreement leaves its memory unchanged; a complete supplied agreement can be used
> directly. Memory records supply context within the user's delegation.

The memory branch contains the detailed sequence: inspect references and scope;
search and fully recall plausible records; preserve exact identifiers, types,
units, structure, and source when needed; search before writing; revise an existing
identity when appropriate; verify the write; and distinguish current, historical,
and fully supplied reproduction. Use faithful prose for prose knowledge and
structured data for structured agreements. Include a readable preview. Do not
turn every memory into JSON or every completed task into a new memory.

## Prime and hooks must teach selection

Installed `bd prime --help` and the v1.2.1 source confirm that `.beads/PRIME.md`
overrides workflow text but **does not suppress appended memory bodies**. The
existing `--no-memories` option does. `--memories-only` takes precedence over it.
Use the real `bd prime --no-memories` command for this legacy packaging test, and
ensure every configured startup/compaction hook follows the same policy. Verify
with sentinel records that unrelated bodies never appear in prime output.

Use supported project startup/context-restoration hooks where available; the
AGENTS rule supplies the explicit command path elsewhere. Trace the difference.
Start without an automatic capture or completion-blocking hook. Such enforcement
would be another intervention and could recreate duplicate capture. Public checks
may report missing references or failed writes, but cannot supply hidden answers,
repair records, or certify the truth of an artifact merely because memory agrees.

## Put the work in the task

The user message becomes approximately `Work on <task-id>`. Detailed requirements,
approval evidence, and intended use of references belong in the task body. Keep
capture keys and memory coaching out of ordinary task requests. The project policy
authorizes preservation of approved reusable knowledge; the agent still must
recognize the occasion and select the appropriate record.

Use a small runnable service or CLI with independently testable behavior. For
example, implement a cache adapter, then a second component governed by the same
approved policy. Preserve the eight existing occasions: initial approval, direct
reuse, search reuse, permanent revision, revised direct and search reuse, fully
supplied reproduction, and historical reproduction. Include structured settings
and a short source/rationale statement whose fidelity is assessed separately.

Have the producing agent also author a real follow-up task, explaining the policy's
relevance and linking the actual memory it created. Grade task authoring and the
returned identity separately. If it omits the capture, task, or reference, retain
that omission; never synthesize the missing handoff to let the next stage pass.
Search work should include plausibly overlapping notes and a different wording of
the same agreement, so selecting and updating an existing identity matters.
The permanent-revision task is the explicit search-before-write test: it supplies
the project/scope and approved change, but no memory ID, key, or link. The agent
must find the record actually created earlier, fully recall it, and revise that
identity without duplicating it. Grade selection, retained identity, complete
revised content, and historical preservation independently.

Carry actual project files, task history, Beads records, and condition-appropriate
native memory forward in isolated state. Never erase source evidence just to make
memory indispensable. A fresh sibling component may need knowledge absent from
its own code, but earlier tasks or specifications can still be legitimate sources.
Correct work through such an alternative is a task success and a different
retrieval route, not a memory handoff success. Report memory necessity explicitly.

## Small matched screen before broader claims

Propose two delivery arms with identical tasks, public workflow semantics, tool
surface, memory-body exclusion, and grading:

1. Explicit delivery: the complete candidate procedure is in the initial prompt.
2. Installed delivery: only the task assignment is in the prompt; rules, prime,
   skill discovery, and task inspection deliver the procedure.

The explicit arm retains ordinary issue guidance and tool help, but does not also
auto-load or register the candidate memory procedure through prime and skills.
Each arm gets one intended delivery path; otherwise duplicate exposure would
confound the comparison. This compares the integration package as a whole, not
the individual effects of AGENTS wording, a hook, or skill discovery.

One eight-stage lifecycle per arm on each of the two previously usable hosts is
**32 planned session slots**, plus at most one bounded integration smoke per host.
This is a screening design, not a reliability estimate. Compare within each
CLI/model; do not attribute Claude/Sonnet versus Codex/GPT differences to the host
alone. The old cohort remains historical evidence, not a matched control.

Recheck actual availability before freezing. The last cohort's Gemini billing,
Copilot executable, and OpenCode context blockers remain visible until resolved;
do not silently exclude them or spend to repair them as part of this proposal.
Use existing authentication, exact models/CLI hashes, and fresh scratch state.
Keep each host's normal native-memory setting identical across the two arms and
carry only records actually generated there. Default-off is still default-off;
an empty native store does not establish competition with a mature memory system.
Freeze session/time/token limits, supported cost caps, ordering, and interruption
handling before calls. An unavailable slot remains unrun, with its reason.

Static checks precede real smokes: host imports and symlink resolution; source
hash equality; no answer values in instructions; prime body exclusion; real task
bodies; store isolation; subprocess-safe receipt attribution; and grader rejection
of wrong-but-mutually-consistent artifact/memory pairs. Smokes must demonstrate
project rule delivery and actual skill use without prompt-injected instructions.
The current Claude adapter disables slash commands and excludes the Skill tool;
the Codex adapter ignores rules and sets project-document capacity to zero. Add
separate adapters or modes that enable the frozen project package while preserving
user/global isolation. Leave the old adapters and frozen copies unchanged.
OpenCode also needs project settings and external skills enabled; its old normal
mode uses AGENTS.md as a native-memory file, which cannot stand in for the new
instruction entry. Gemini and Copilot still need real adapters after availability
blockers are resolved; the common other-host adapter currently implements OpenCode.

## Outcomes and improvement loop

Grade the resulting feature behavior against hidden independent expectations.
Separately assess faithful retained content, source/provenance, record identity,
and historical immutability. Trace these boundaries: guidance delivered, skill
reached, task inspected, capture attempted and retained, discovery results seen,
full record delivered, information applied, and historical/current state changed.
Unknown delivery or attribution remains unknown. Agent narration is not a receipt.

Classify capture omission, information loss, retrieval, application, historical
mutation, unnecessary reads/writes, and incomplete task handoffs separately.
Record automatic/harness reads separately from agent reads. Report denominators
for attempts, completed sessions, complete lifecycles, and blocked/unrun stages;
eight stages sharing one capture are not eight independent reliability samples.
Report known costs, unknown costs, and instruction/tool overhead.

Use transcripts and optional feedback to explain departures before changing the
package. Preserve recurring attempted commands as design evidence, not automatic
API commitments. Version any remembered workaround with circumstances and evidence;
tool avoidance remains a hypothesis unless the new traces actually show it.
Retest a changed package as a new cohort rather than editing frozen conditions.

## What requires the actual Memory type

The packaging screen can use legacy `bd` now. Its task-body key links remain text,
and its history remains mutable notes. It cannot validate structured Bead References,
canonical optional-key identity, immutable revisions, pinned history, conditional
updates, or production provenance. Do not present a shim or seeded spike as that
implementation.

The smallest subsequent production slice needs create/search/full recall, revision
with immutable history and stale-write protection, task reference authoring and
reading including a revision pin, and the generated instruction package. Run the
same author-to-executor sequence against that real surface, then use deterministic
CLI tests for reference integrity and concurrent-write failure. Broader lifecycle,
provider, migration, and archive acceptance remains outside this agent screen.

The proposed end-to-end acceptance moment is concrete: the user assigns a task;
one agent captures its approved reusable decision and authors a useful reference;
a fresh agent follows the shipped guidance, selects the actual record, implements
correct behavior, and leaves an accurate current agreement and unchanged history.
