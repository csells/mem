# Phase 1 workflow and feedback audit

The watcher finished and exited after capturing 68 unique assessed sessions out
of 72 planned phase-1 slots. Every saved audit and underlying source hash was
checked again. There were no duplicate audit files or model calls by the watcher.
This is separate from the family auditors' judgments about duplicate memory
curation. Hidden artifacts passed in 58/68 assessed sessions.

The snapshot retains all 216 planned slots: 67 ordinary assessments, one explicit
posthoc assessment, two censored prelaunch claims, ten dependent censored slots,
and 136 future slots. Four of the twelve censored slots belong to phase 1.

## Actual commands and feedback

Ancestry-checked receipts establish 460 actual `bd` executions: 440 succeeded and
20 failed. No execution has unknown ancestry attribution. Successful operations
include 47 prime calls, 88 issue reads, 58 updates, 57 closes, 78 memory
search/list calls, 30 recalls, 18 saves, and 38 help calls. These are command
counts, not faithful captures or successful memory handoffs. Help is never counted
as its parent operation; in particular, `remember --help` is not a save.

The twenty failures comprise:

- Seven attempts at an unavailable `bd memory` namespace, using `list`, `show`,
  `read` or `--help`.
- Three empty-body save attempts rejected by `bd remember`.
- Three attempts to use issue status `completed`.
- Three invented close flags: `--note`, `--completion-note` and `--context`.
- One each of `show --comments`, `activity`, `ls` and `list --open`.

The per-session records retain each argv, error response, and later command
sequence. Examples show corrections from `ls` to `list`, `completed` to close,
and invalid close flags to `--reason`. This supports an improvement loop using
real attempts and feedback. It does not establish that every attempted alias or
invented semantic should become API surface. No explicit feedback flag was
installed in this experiment.

Forty-six sessions have full prime output linked to an actual prime command.
The remaining successful prime invocation was deliberately piped through
`head -50` in zcode/finance/rich-prime/stage-1: its 4,206-byte receipt became a
2,102-character model-visible prefix. That session does not receive full prime
exposure credit from this audit. Six Haiku sessions instead called native
`Skill(beads, args="prime --no-memories")`; none of those six actually executed
`bd prime`. Loading a skill and invoking a CLI command are separate events.

Three Qwen sessions stopped after emitting pseudo-tool markup as ordinary text.
No actual tools appear in their parent events, process receipts or isolated host
databases. Their identities are retained in the snapshot. This is a tool
invocation failure distinct from choosing not to save a memory.

## Models, auxiliary work, native state and cost

| Profile | Assessed/planned phase-1 sessions | Actual primary model | Reported dollars |
| --- | ---: | --- | ---: |
| Codex Astra | 12/12 | `gpt-6-astra` | Unknown |
| Codex Luna | 10/12 | `gpt-5.6-luna` | Unknown |
| Claude Sonnet | 10/12 | `claude-sonnet-5` | $2.1831296 |
| Claude Haiku | 12/12 | `claude-haiku-4-5-20251001` | $0.9322572 |
| OpenCode Qwen | 12/12 | `ollama/qwen3-coder:30b-a3b-q8_0` | $0 reported; compute unpriced |
| zcode GLM | 12/12 | `zai/glm-5.3` | Unknown |

Known host-reported cost is $3.1153868, with 34 sessions lacking dollar receipts.
Qualification costs are separate. Every Sonnet session's usage receipt also
contains a Haiku entry; these costs are already included in the reported total.
They must not be billed twice or omitted when describing the work performed.

Two Qwen sessions have Explore children omitted from the parent's normalized
tool list: 23 child tools in total. The read-only isolated database exports show
the same pinned Qwen model in both children and retain their separate usage
receipts. A parent-only token total does not account for all child work.

Current-session zcode model-IO logs contain 204 request records identifying
`zai/glm-5.3` with role `main`. No lite-model request appears in those records;
this is not proof that no unrecorded auxiliary request occurred. No native
automatic-memory extraction or use is inferred from filesystem presence.
All 22 assessed Codex native databases have zero rows in both `stage1_outputs`
and `jobs`. zcode's native directories include runtime rollouts, artifacts and
bookkeeping. Claude and OpenCode native snapshots contain no files.

The three other global profile hashes remain unchanged. Codex TOML has the
documented raw-hash drift under the separately reviewed effective-condition
guard. Neither this audit nor either continuation restored or edited user
configuration.

Evidence: `phase1-1788827108816097000.json`,
`phase1-workflow-review-1788827275837194000.json`,
`phase1-native-auxiliary-1788827275833679000.json`, and the referenced immutable
session audit files. Semantic correctness, information loss, applicable memory
use, historical mutation and duplicate curation remain the independent family
auditors' responsibility.
