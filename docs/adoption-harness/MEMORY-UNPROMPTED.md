# Memory Beads during ordinary coding work

Status: **120/120 ordinary-task sessions assessed**, separately from the eight
integration sessions. See the [full setup, results, costs, and recommendations](../../specs/memory-unprompted-results-2026-09-07.md).
Standing guidance produced capture and later search-based use on Codex and zcode,
but initial treatment capture was 0/12 and no known-reference direct lookup
occurred. Frozen artifact checks pass 100/120; a uniform posthoc supplement
reduces the count passing all applied checks to 98/120. One OpenCode session
timed out and was not retried. This did not establish reliable four-profile
memory adoption or validate the new Memory bead type.
The in-scope CLIs are **Claude Code, Codex, OpenCode, and zcode**. The user confirms
all four work. Gemini and Copilot are excluded by request.

## What we want to establish

Agents should independently save useful durable decisions, facts, and lessons
while implementing normal features and fixes. In fresh sessions, they should
recover and correctly apply their actual saved knowledge through both direct
lookup and search with full-record inspection.

The behavior should come from the normal project installation: AGENTS.md, each
host's supported instruction entry point, a shared Beads skill, and available
memory commands. **The coding tasks must contain no instructions to remember,
recall, retain an agreement, create a memory reference, or perform a handoff.**
That includes issue bodies and comments, not just the launch prompt.

Success also requires faithful information, correct permanent revisions,
historical compatibility without changing the standing agreement, and no duplicate
capture merely to reproduce a fully supplied result. Correct code alone does not
prove memory adoption; memory calls alone do not prove correct work.

## The comparison

Compare current issue guidance with the same guidance plus standing memory rules
and a memory skill reference. Both arms get the same real memory-capable tool,
public project checks, and independently authored ordinary tasks. Review the
complete task context before launch. The treatment is the combined rules/skill
package; separate rules-only and skills-only claims require later comparisons.

Two unrelated project families each have six fresh-session tasks: initial feature
or bug fix, a related extension, a fully supplied reproduction, a permanent
business change, an affected extension, and historical product compatibility.
These labels belong to the evaluator, not to the agent's task instructions.

One admitted pair is "Fix reconciliation dropping transactions on the last day
of a selected month," followed by "Add filtered refund CSV export." The first
investigation can uncover exclusive UTC date boundaries useful to the second.
Neither task tells the agent what to save or where to look. The frozen corpus
contains this Northbank family and HarborPass renewal-policy work, with complete
admission and executable grading evidence linked in the results.

Code, issue history, and actual memories carry forward without repair. Other
sources remain legitimate. Direct lookup and search must be observed choices;
we will not insert memory keys to manufacture route coverage. If a route is never
used, that part of the goal remains unvalidated. Agent-created task reminders are
preserved and subsequent instructed reuse is reported separately.

The completed bound is **96 main sessions**: four CLIs × two guidance arms × two
project families × six tasks, with a checkpoint after 48. A separate **24-session
check** uses normal native-memory settings. It tests robustness, not the causal
effect of native memory. Actual models and settings are pinned per CLI.

## Harness qualification comes first

Each CLI must pass a real isolated two-session integration smoke using its actual
authentication and pinned model. Verify instruction and skill delivery, shell/file
operations, Beads capture/search/full lookup, fresh-session state transfer,
completion and error reporting, and model/usage receipts. Verify isolation and
failure handling with local tests before launching those checks. Preserve all
attempts and user data; change no global configuration or existing model server.

These integration smokes explicitly exercise tools and are **not adoption
evidence**. The scored experiment cannot start merely because an executable exists
or a host works interactively. Qualification results will name the exact working
adapter/profile and any remaining limitation.

The [qualification report](../../specs/memory-four-hosts-qualification-2026-09-07.md)
records successful authenticated execution, instruction/skill delivery, capture,
search, full lookup, and fresh-session transfer on all four updated CLIs. Claude,
Codex, and zcode passed both complete smoke checks. OpenCode produced correct
artifacts and retained records but failed marker checks and omitted search and
prime in its second session. Those failures remain failures; tool availability
does not imply that the model reliably follows the workflow. Corpus admission,
the final package, and pre-launch verification are now documented in the
[admission report](../../specs/memory-unprompted-admission-2026-09-07.md).
OpenCode remains included with those failures recorded. The runner freezes the
complete corpus, profiles, and slots before any scored session.

The [full plan](../../specs/plans/0005-unprompted-memory-adoption.md) preserves the
remaining goals and defines task
admission, data preservation, grading, costs, failure classifications, and limits.
The [four-host inventory](../../specs/memory-four-hosts-inventory-2026-09-07.md)
records host interfaces and profiles. Earlier guided experiments and their scope
corrections remain available through the [experiment index](README.md).

A successful screen supports this workflow on the tested tasks, models, and hosts.
Repeatability requires further fresh trials. Legacy keyed-memory results do not
validate the proposed new Memory bead type or establish production reliability.
