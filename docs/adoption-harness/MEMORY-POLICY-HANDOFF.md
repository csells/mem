# Memory policy handoffs across coding models

This experiment tests **ordinary issue work with standing rules and a skill**,
not tasks that explicitly request memory use. The [complete design](../../specs/plans/0006-policy-handoff-model-sweep.md)
declares 240 main sessions across ten model profiles and 24 normal-memory sessions
across four CLI hosts. Twenty explicit integration checks qualify the adapters
separately; they do not count as unprompted adoption.

The earlier [120-session screen](../../specs/memory-unprompted-results-2026-09-07.md)
did not establish reliable initial capture or direct lookup. Its follow-up tasks
often reused existing code under rules that required retrieval only for missing
knowledge. The [task audit](../../specs/research/memory-task-sufficiency-2026-09-07-billing-audit.md)
explains why those tasks were insufficient for the stronger claim.

This design makes approved scope matter. For example, identical single-line credit
calculations can implement either an account cap or a subscription cap; a later
multi-subscription statement needs the actual approval. A second project similarly
distinguishes globally unique delivery IDs from IDs unique only within an account.
Later detail output also needs approved allocation or duplicate-selection rules
that aggregate outputs do not reveal.

All original approvals, actual code, issue history, and agent-authored records
survive. An agent can use those legitimate alternatives. The experiment judges
whether the memory workflow is chosen and useful, without making the world
artificially forget everything else.

The comparison keeps the earlier generic guidance and adds an occasions package
on the same tasks. That package states what memories preserve, puts policy review
before implementation, and puts approved-decision capture before issue closure.
Both packages use the same Beads issue skill and legacy memory commands. A declared
indexed deployment exposes only actual saved keys for direct lookup; a search-only
deployment supplies no catalog. No task supplies a memory key or memory command.

All 240 main and 24 normal-memory sessions are complete. The
[final report](../../specs/memory-policy-handoff-results-2026-09-07.md) separates
correct code, faithful knowledge, prior full reads, direct versus search routes,
historical mutation, duplicate capture, costs and host/model failures. The main
strict handoff outcome was 2/20 with generic guidance and 9/20 with occasions
guidance; correct artifacts were 95/120 and 90/120 respectively. These results
support voluntary handoffs on several CLI/model pairs, not reliable behavior
across all tested agents. They do not validate the proposed new Memory bead type.

## What the agent actually receives

The only session request is `Work on <actual issue ID>.` The agent chooses how to
inspect and complete that issue. Its description contains the product request and
ordinary approval information, without memory commands, keys, or reminders.
Later issues do not prescribe memory operations either. All original approvals,
code, public tests, documents, issue history, and actual memories remain available.

The deployment is installed in each fresh synthetic project:

| Surface                         | Installed behavior                                                                                                       |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `AGENTS.md`                     | Shared issue workflow, the assigned memory-guidance arm, and common catalog orientation                                  |
| `CLAUDE.md`, `GEMINI.md`        | `@AGENTS.md` pointer; Gemini is not part of the scored host set                                                          |
| `.agents/skills/beads/SKILL.md` | Shared issue skill plus the arm's link to the memory procedure                                                           |
| `.claude/skills/beads`          | Project alias to that same skill, avoiding a second procedure copy                                                       |
| `references/memory.md`          | Capture, retrieval, source checking, revision, and historical-use procedure                                              |
| `.beads/PRIME.md`               | Directs the agent to `AGENTS.md` and the Beads skill; it supplies no saved memory bodies                                 |
| Isolated `bd` on `PATH`         | Real legacy `remember`, `memories`, and `recall` commands against the lifecycle's scratch store, with execution receipts |

The project rule asks for workflow restoration through `bd prime --no-memories`.
The harness does not force the agent to run it. There is no memory capture hook,
compulsory recall, completion guard, or hidden answer feedback to the agent.
Hidden artifact checks run after the session and never become the next task's
instructions. The [installer](../../memory-bench/membench/runner/memory_policy_handoff_package.py)
and [guidance fixtures](../../memory-bench/fixtures/memory-policy-handoff-package/memory.md)
are the exact implementation of this deployment.

## What changes between guidance arms

Both arms already explain the commands and faithful retention. The occasions arm
changes the decision about _when and why_ to use them:

| Generic guidance                                                                          | Occasions guidance                                                                                                                                                         |
| ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Capture useful durable knowledge when it would help later work or be costly to rediscover | Capture newly approved decisions, permanent revisions, and verified reusable findings before closing the issue, including approved scope beyond the current implementation |
| Retrieve when needed project knowledge is missing                                         | Consult applicable knowledge and its sources before changing behavior governed by an earlier agreement or investigation                                                    |
| Keep evidence and interpretations distinct                                                | Explicitly distinguish approval from inference, resolve conflicts against sources, and state that readback verifies storage rather than truth                              |
| Do not save merely because a record was used                                              | A new consumer or fully supplied reproduction is not a new agreement; save only an actual durable finding or revision                                                      |

The shared skill description names both issue work and durable project knowledge.
This and the common catalog are additions to both arms, so the generic arm is not
a byte-identical rerun of the previous experiment. The comparison does not isolate
rules from skills or one sentence from the complete guidance package.

Indexed deployments expose `BEADS_MEMORY_INDEX`, a fresh JSON catalog containing
only keys actually present before the session. Search-only deployments leave it
unset. The index contains no bodies or perfect seed records. Reading this index,
reading a known record directly, searching, and reading a full search result are
separate observations. Catalog orientation remains work even when no `bd` memory
command follows it.

## Hosts, models, and native-memory conditions

The frozen sweep admits four Codex models (Astra, Sol, Terra, Luna), four Claude
models (Haiku, Sonnet, Opus, Fable), OpenCode with Qwen, and zcode with GLM. Exact
model IDs, CLI binaries, settings, source hashes, and all 264 slots are in the
[manifest](../../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/manifest.json).
Requested model names are checked against actual primary-model receipts. Provider
or execution failures remain visible; an installed executable alone is not
qualification. Existing authentication is used without changing global settings.

| Host        | Main comparison                                         | Bounded normal check                                                              |
| ----------- | ------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Claude Code | Automatic memory disabled                               | Default automatic memory enabled in fresh isolated storage                        |
| Codex       | Memory feature, generation, and use explicitly disabled | Installed feature-off default retained                                            |
| OpenCode    | No separate automatic extractor configured              | Same native behavior; repository state still survives                             |
| zcode       | Memory feature and use disabled                         | Normal headless settings; this runtime still disables extraction in headless mode |

Normal means the supported headless behavior in a fresh project, without the
user's unrelated plugins, instructions, or prior native records. A setting or a
file's existence does not prove native memory participated. The four normal
anchors are Astra, Sonnet, Qwen, and GLM; those 24 sessions are reported separately
from the 240 main sessions.

## Execution and evidence

Twenty real integration checks qualified the interfaces before scoring. All ten
model/host interfaces worked; 16/20 full diagnostic workflows passed. Haiku and
Qwen's behavioral diagnostic failures remain reported rather than being used to
remove weaker models from the experiment. Corpus/oracle validation and adapter
tests are documented in the [verification summary](../../memory-bench/results/memory-routes/2026-09-07-policy-handoff-verification-01/SUMMARY.md).

The cohort runs stages 1–2 first, reviews that exact checkpoint, then runs stages
3–6 and finally the normal-memory check. Four workers, a 420-second session
deadline, and Claude's 30-turn limit and $1.50 CLI stopping threshold bound
execution; the dollar threshold is not a universal invoice cap. Started trials
are never automatically retried.

Read status without launching a session, from `memory-bench/`:

```sh
.venv/bin/python -m scripts.memory_policy_handoff_experiment \
  --out results/memory-routes/2026-09-07-policy-handoff-01 --status
```

The completed [80-session first checkpoint](../../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/phases/phase1/REVIEW.md)
records the initial results and the decision to continue unchanged. The immutable
manifest, per-session results, before/after snapshots, full host evidence,
independent artifact checks, and semantic audit supplements are retained under
that cohort. Source fidelity, model-visible delivery, and surrounding claims are
audited separately from command acknowledgments and passing configuration values.
The [final integrity audit](../../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/final/integrity.json)
checks all 264 sessions and confirms the frozen sources, binaries and profiles
remained unchanged. No scored session was retried or replaced.
