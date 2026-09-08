# From saving notes to preserving decisions that change future work

The practical ambition is a complete handoff during normal coding: one agent
learns or implements an approved agreement; another correctly extends, revises,
or reproduces it without the user remembering to request memory operations.
The evidence does not yet establish that outcome. The [previous report](../memory-unprompted-results-2026-09-07.md)
records partial voluntary capture/search and zero initial keyed treatment captures.
Its four host/model combinations were not a model-strength sweep.

The obvious next step was stronger reminders. The more consequential change is to
test the difference between implemented behavior and approved intent. An agent
can correctly reuse code and legitimately have no missing information under the
old conditional rule. More reminders on those tasks would not establish that
memory supplied knowledge the implementation lacked.

## Material that changed the experiment

The [task sufficiency audit](memory-task-sufficiency-2026-09-07-billing-audit.md)
finds useful initial capture candidates but weak missing-policy follow-ups.
Some later tasks explicitly supplied historical rules or composed existing
functions. Missing memory calls therefore do not all demonstrate rule violations.

The author-written [policy fork](../../memory-bench/results/memory-routes/2026-09-07-policy-fork-probe-01/result.json)
uses the same scalar formula under two approval scopes. Its 72 initial cases agree;
32 of 64 expanded cases differ. Two 30000-cent lines under separate subscriptions
can receive 2400 cents total with an account cap or 4800 with subscription caps.
This proves a distinction in that construction, not adoption or model reliability.
Independent criticism exposed a missing allocation rule in the initial sketch;
the finance corpus now specifies priority and separately tests total versus line
output. Wrong code and a wrong note can agree while violating the approval.

Human implementation-intention research separates holding a goal from linking an
anticipated situation to an action. Its useful transfer is an observable occasion
such as “before closing a newly approved policy change,” instead of an unbounded
judgment that a note might help someday. The human mechanism and measured effects
are not evidence about LLM behavior. [Gollwitzer, 1999](https://bpb-us-e1.wpmucdn.com/wp.nyu.edu/dist/c/6235/files/2019/02/gollwitzer-1999-implementation-intentions.pdf).

Architecture decision records preserve context, decision, status, and consequences;
superseded decisions remain useful when their rationale would otherwise disappear.
This motivates retaining scope, evidence, and historical applicability, without
imposing an ADR template or JSON on every memory. [Nygard's original ADR proposal](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

MemoryArena admits tasks with dependencies across successive interactions and
filters self-contained one-turn work. That suggests checking a real information
dependency before counting a retrieval opportunity. Its retrieval/update loop is
built into the framework, so its results cannot establish voluntary adoption from
standing rules. Our earlier approvals and artifacts remain available; we do not
delete them to force Beads to be the only possible source. [MemoryArena, section 3](https://arxiv.org/html/2602.16313v1).

## Alternatives and selected test

One alternative is to make code/docs the canonical durable memory. It avoids a
second representation when the next task only composes existing behavior. Record
that as legitimate alternative-source success. It leaves cross-session policy,
rationale, and historical knowledge dependent on their discoverability elsewhere.

Another is automatic transcript extraction or compulsory recall at every task.
Those may improve availability but test a different intervention and can create
curation or retrieval overhead. We are not adding a forced read, a save hook, or a
completion guard to this study.

The chosen experiment combines explicit standing workflow occasions with a
declared reference catalog of actual saved keys, alongside a search-only deployment.
It retains generic guidance on the same new tasks as a comparator. Two families
use counterfactual approval scopes and later reveal behavior the initial output
cannot distinguish. Both families end with a fully specified, one-off support
attachment, so merely producing the requested artifact is not a new agreement.

The full [design](../plans/0006-policy-handoff-model-sweep.md) is bounded and frozen
before scoring. Model access is qualified separately. Behavioral failures in
qualification remain visible; they do not justify filtering out working weak
models. Claude and Codex comparisons vary primary model within host, while
OpenCode/Qwen and zcode/GLM extend host coverage with acknowledged confounding.

## Practitioner input and its limits

Atbrace's account advocates designing from observed tool use, shared conventions,
a catalog, readable structured answers, and recurring validated feedback. The user
also noted that Beads adopted commands agents attempted. Those are attributed
practitioner observations; the claimed 150000-plus transcript collection and
adoption claims were not independently verified here.

The useful recommendation is a transcript-and-feedback improvement loop with
separate categories for discovery, omitted capture, information loss, retrieval,
application, and unnecessary work. Attempted syntax is design evidence; it does
not establish unambiguous semantics or justify every permanent alias. Separate
human/agent interfaces should be evaluated by their practical benefit.

Remembered tool avoidance remains a hypothesis to investigate, not a finding from
that account. The previous cohort did contain an unsupported CSV-library rationale
in a saved note, but did not establish inherited downstream reliance on that full
claim. Workaround advice should carry version, circumstances, and evidence, with
an opportunity to recheck it. Correct values do not certify surrounding prose.

All changes above are proposals until scored runs finish. Even a clean synthetic
screen would leave production duration, realistic distractions, concurrency,
native-memory interactions, and the new Memory bead type unvalidated.
