# Memory guidance through prime or startup

This experiment asks whether the same memory procedure works better when agents
receive it directly through `bd prime` or at startup. The preceding
[policy-handoff experiment](MEMORY-POLICY-HANDOFF.md) put the detailed procedure
behind project rules and a skill; prime merely pointed back to those files.

The [frozen design](../../specs/plans/0007-memory-prime-delivery.md) specifies
216 ordinary coding sessions across six models and four CLIs, preceded by twelve
explicit delivery checks. The conditions are:

| Condition        | What changes                                                                                            |
| ---------------- | ------------------------------------------------------------------------------------------------------- |
| Thin prime       | Existing project rules, skill and memory reference; prime points to them                                |
| Rich prime       | The same deployment, with the complete procedure also returned by prime                                 |
| Startup briefing | The same deployment and thin prime, with that complete procedure supplied in a separate startup section |

The rich briefing is assembled from the existing instructions, including exact
commands, source checking, permanent revisions, historical reproduction and
duplicate avoidance. It adds no new policy facts. Actual CLI checks establish
that the rich prime output and startup briefing contain identical text.

Every task component remains `Work on <actual issue ID>.` The startup condition's
whole launch message is intentionally longer: common briefing, then task. The
briefing is identical for every task and supplies no specific memory key or
instruction that this particular task requires remembering or recalling.

## What this tests

The thin/rich comparison tests presenting the full procedure at an existing
command. The rich/startup comparison tests command-mediated delivery versus
initial availability. They compare delivery packages; message position, role,
repetition, output truncation and extra context can also affect behavior. A
successful injected briefing does not establish that agents will discover prime.

`bd prime` supplies workflow guidance. `bd ready` finds work and `bd show` reads
a selected task. The experiment does not make prime select tasks or memory bodies.
It uses real legacy Beads commands with `--no-memories`, a project override and
the same actual-key catalog or search-only deployment as the earlier experiment.
The proposed canonical Memory type and its shared-history semantics remain
untested.

## Tasks, agents and scoring

The two unchanged projects require later work to recover approved scope and
allocation/selection rules that early narrow outputs do not reveal. Each has six
fresh sessions: initial capability, multi-entity use, permanent revision, detailed
current output, historical output and fully supplied support reproduction.

All actual code, issues, documents and saved memories carry forward, including
mistakes and missing captures. Original approvals remain legitimate alternative
sources. No perfect memories are seeded and no failed trial is restarted.

The model profiles are Codex Astra and Luna, Claude Sonnet and Haiku, OpenCode
with local Qwen, and zcode with GLM. This covers all four CLIs plus weaker-model
contrasts within two hosts. Exact model IDs, versions, native-memory settings,
source hashes and the ordered schedule are pinned before scoring. All scored
sessions use the previously qualified isolated native-memory configuration;
there is no additional normal-memory sweep.

Independent checks judge correct accumulated behavior, faithful retained
agreements, actual full reads through direct lookup or search, history integrity
and unnecessary work. The primary use score requires retrieval before changed
behavior or subsequent testing/validation. A later confirmation after tests gets
a separate score, as do unsupported verification claims. Receiving instructions
or calling commands is not itself success.

The run has four workers, 420-second session deadlines and Claude's existing
30-turn limit and $1.50 stopping threshold. Costs are reported where available;
unknown subscription/provider charges and local compute remain explicit. First
run and review the 72 initial/reuse sessions, then continue the remaining 144
sessions unchanged. Qualification and its deliberately explicit instructions
never count as adoption evidence.

The [delivery qualifications](../../memory-bench/results/memory-routes/2026-09-07-prime-delivery-qualification-01/result.json)
passed 12/12 explicit diagnostics across all six profiles. Actual scratch prime
outputs matched the intended text and excluded sentinel memory bodies; global
configuration hashes were unchanged. Those checks establish working delivery,
not voluntary memory adoption. Reported qualification usage was $0.2510, with six
sessions lacking dollar receipts and local compute unpriced.

The [scored manifest](../../memory-bench/results/memory-routes/2026-09-07-prime-delivery-01/manifest.json)
freezes 216 slots, 450 source inputs, seven executable hashes and four profile
hashes. The [verification log](../../memory-bench/results/memory-routes/2026-09-07-prime-delivery-verification-01/targeted-checks-01.log)
records 76 passing targeted and shared tests, plus Ruff, Black and strict mypy.
The completed earlier runs remain untouched.

The reusable entry points are
[qualification](../../memory-bench/scripts/memory_prime_delivery_qualification.py)
and [scored execution](../../memory-bench/scripts/memory_prime_delivery_experiment.py),
run as Python modules from `memory-bench/`. Qualification requires `--run` and a
new `--out` directory. Scoring first requires `--freeze --admission <review.json>`,
then `--run phase1`, an exact-summary internal review, and `--run phase2`.
Started or completed evidence is never replaced. The durable launch and console
records under the verification directory and cohort's `recovery-02/` directory
record the actual invocations.

A supervisor output-pipe failure interrupted phase 1. The
[operational recovery record](../../memory-bench/results/memory-routes/2026-09-07-prime-delivery-01/OPERATIONAL-RECOVERY.md)
preserves that failure and specifies continuation of untouched slots only. One
completed model turn was assessed from its original transcript, with OS exit
unknown. Two prelaunch claims leave twelve planned sessions unassessed; there
are no replacements. Later provider/authentication and deadline failures remain
separate from this original incident; the final report retains all 216 slots.

The first continuation stopped at 28 assessed sessions after a byte change to
the live Codex configuration triggered its original hash guard. A
[separate effective-settings review](../../memory-bench/results/memory-routes/2026-09-07-prime-delivery-01/CONFIG-GUARD-REVIEW.md)
found that the frozen adapter replaces both settings it reads from that file and
launches Codex with isolated configuration and `--ignore-user-config`. The raw
mismatch remains documented; no user configuration is restored or changed.
A second reviewed continuation preserves those 28 results and runs only
untouched eligible slots under the same effective conditions.

Execution and independent semantic auditing are finished. The
[results report](../../specs/memory-prime-delivery-results-2026-09-07.md) records
**196/216 sessions assessed, 120 correct artifacts, and one strict handoff across
36 planned lifecycles**. Twenty assessed turns had provider denials without model
generation. Twenty slots remained unassessed: twelve from the original incident,
two after an authentication setup failure, and six after a zcode timeout triggered
the frozen profile stop rule. No affected slot was retried or replaced.

Each arm produced three complete initial captures: nine complete, two incomplete
and 23 absent among 34 assessed initial opportunities. Thirty-three preparatory
uses led to correct work, including sixteen direct lookups and seventeen searches
followed by full lookup. Twenty-three had complete faithful entries; ten used
partial knowledge with other sources filling gaps. There were no duplicate
captures in 26 controls with model work, but six still performed unnecessary
memory discovery or reads.

The sole strict success was GLM's startup-briefing Finance lifecycle. Its other
Finance conditions did not finish, so this cannot establish a startup advantage.
More prominent procedure delivery did not establish reliable handoffs. The
smallest proposed improvements clarify the capture occasion, improve failed
search handling, check record content against approval sources, and limit
unnecessary curation. These are proposals, not validated fixes.

The [evidence index](../../memory-bench/results/memory-routes/2026-09-07-prime-delivery-01/README.md)
links the frozen manifest, raw transcripts, actual retained records, independent
grades, semantic audits and recovery history. The report preserves the known raw
Codex configuration mismatch, provider failures, incomplete matched coverage,
partial-record usefulness and exact limits of the evidence. This study does not
test prime selecting relevant project memory headers or the new Memory bead type.
