# E1 guidance ladder: interior fire (R1, R2, R3), 480 legs

**Status: PRELIMINARY.** Design {R1, R2, R3} x {necessary, unnecessary}, T=8 tasks per
variant, R=5 repeats, 48 cells, 240 two-leg cells, 480 legs, all 480 measured (0 timed
out, 0 errored, no quota halt). Model `claude-sonnet-4-6`, Claude Code CLI `2.1.260`,
`corpus_fingerprint` `c5f13bbe8c877a2b`, `surface_fingerprint` `69fa4562ba901a0a`,
`settings_fingerprint` `4848e2882ef184e4`, `execution_protocol` 2, channel `recalled`.
Fired 2026-09-04 in one session. Code at `4d0db67`. Beads: `mem-gj0pc`, `mem-eg850`.

This is the first E1 fire on the two-leg cell. Every earlier E1 number was bought on a
single-leg cell, where the memory store was minted inside the leg and destroyed on the
way out, so a write could not pay off and the published write rate was 0/160 whatever the
agent did. A repeat here is a pair: one sandbox and one store, an establish leg that
states the task's values, the cwd emptied between the legs, then the goal leg.

## Headline

Discrimination lives in the interior, and it peaks at the WEAKEST guidance. Every
interior margin exceeds d(R4) = +0.025 from the ends fire, and all three are separable
from zero, which neither ends margin was.

| rung | guidance words | d (goal leg) | Fisher p | d (pooled) | Fisher p |
| ---- | -------------: | -----------: | -------: | ---------: | -------: |
| R1   |             10 |      +0.4250 |   0.0002 |    +0.2125 |   0.0024 |
| R2   |             23 |      +0.1750 |   0.0117 |    +0.0875 |   0.0136 |
| R3   |             38 |      +0.3000 |   0.0007 |    +0.1500 |   0.0012 |

For reference, from the landed ends fire (`../staged-160`): d(R0) = +0.175 (p = 0.147),
d(R4) = +0.025 (p = 1.000). Those two are the design this fire was authorized to replace:
R4 saturates the instrument at P(call | unnecessary) = 0.975, which bounds d(R4) above by
0.025 no matter the sample size.

Read the GOAL-LEG column as the effect. Both halves of a twin receive a byte-identical
establish leg by construction, so the establish leg's margin is 0.000 at every rung and
pooling the two legs halves the number without adding information. The pooled column is
what `summary.json` publishes; the split is recomputed from `LegRecord.role`, which is on
every leg file for exactly this re-score.

## Pooled table

Pooled means sum of calling legs over sum of measured legs across the eight task cells of
each (rung, variant), never a mean of per-cell rates. Both legs of every pair are in
these counts.

| rung / variant   | measured | calling | P(call) | write legs | writes | reads |
| ---------------- | -------: | ------: | ------: | ---------: | -----: | ----: |
| R1 / necessary   |       80 |      70 |   0.875 |         18 |     36 |    78 |
| R1 / unnecessary |       80 |      53 |   0.662 |         16 |     32 |    58 |
| R2 / necessary   |       80 |      80 |   1.000 |          7 |     14 |    82 |
| R2 / unnecessary |       80 |      73 |   0.912 |          7 |     14 |    79 |
| R3 / necessary   |       80 |      79 |   0.988 |          9 |     18 |    83 |
| R3 / unnecessary |       80 |      67 |   0.838 |         11 |     22 |    77 |

2x2 tables behind the goal-leg margins, reading legs against non-reading legs, necessary
row first: R1 [[32, 8], [15, 25]], R2 [[40, 0], [33, 7]], R3 [[39, 1], [27, 13]].
Fisher exact two-sided, computed here from the leg files with an exact hypergeometric
sum (no scipy in this venv); the same routine reproduces the ends fire's published
p = 0.1471 and p = 1.0000 on its tables.

## The two-leg cell produced writes

136 write calls, against 0 across all 160 legs of the ends fire.

| rung | establish legs writing | establish writes | goal legs writing | goal writes |
| ---- | ---------------------: | ---------------: | ----------------: | ----------: |
| R1   |              34 of 80  |               68 |          0 of 80  |           0 |
| R2   |              14 of 80  |               28 |          0 of 80  |           0 |
| R3   |              20 of 80  |               40 |          0 of 80  |           0 |

The split is the mechanism working, not a defect: the establish leg is where the agent is
handed state, and the goal leg is where it is asked to act. An agent that records on being
told something and does not record while executing is behaving sensibly. It also means the
write rate the single-leg design measured was structurally zero, not behaviorally zero:
that cell had no leg in which recording was the rational move.

## Every call was native memory — but bd was never named to the agent

Verb census over all 480 legs: `native_read` 457, `native_write` 136, and **zero `bd`
verbs of any kind**. R1 through R3 do not pin native memory off (only R0 does), so
`native_memory_pinned_off` is false on all 480 legs, and the interception hook observed
931 reaches into the native path.

**This zero means NEVER DISCOVERED, not discovered and declined.** Read it carefully
before quoting it.

bd was genuinely reachable. Every pair got a real store (`bd init` under a temp root
outside the sandbox, so the cwd wipe cannot eat it) and a `bd` shim placed FIRST on PATH,
pinned to that store with `-C`; `Bash` is in `MEMORY_ALLOWED_TOOLS`; and the argv counter
catches the verb through roughly twenty spellings (backticks, `xargs`, `bash -c`, env
prefixes). A leg that typed `bd remember k v` would have worked and would have been
counted.

The agent was never told bd existed. The ladder's strongest clause says "a persistent
memory tool available in this session" and never names it, and `scrub_store_guidance`
deliberately DELETES the `CLAUDE.md` / `AGENTS.md` that `bd init` drops beside the store,
the files that say "use `bd remember` for persistent knowledge". That deletion is right
for its own purpose (those files are the ladder's top rung smuggled into the artifact, and
leaving them in means R0 was never silent), but its side effect is that the only thing
naming the tool was removed. Discovering bd required reading PATH unprompted. Zero of 480
streams contain the token `bd` anywhere; 47 legs did probe the environment (`which`, `ls`,
`PATH`) and still did not surface it.

So what this fire supports: the agent reaches for memory constantly (931 observed
reaches), it takes the NATIVE path by default, and guidance strength moves how
discriminatingly it reaches. What it does NOT support, and must not be quoted as: that the
agent preferred native memory OVER bd. It was choosing between native memory and a tool it
had no way to know about.

The 931 reaches remain the quantified target for a redirect treatment. But a cheaper prior
question now comes first, and the ladder never asked it: does simply NAMING the tool move
anything? That is a rung this design does not contain.

## Gate: monotonicity FAILS

`call_rate_gates.monotonicity.monotone` is **false**. The pooled call rate on the
necessary half falls from R2 1.000 to R3 0.988 as the guidance gets strictly stronger, a
drop of 0.0125, which is one leg of eighty. The tolerance is 0.0, so one leg reds the gate.

Reported as failed rather than waved off. The gate exists because a ladder whose rates do
not order with its treatment is not measuring the treatment, and a one-leg drop at a
ceiling of 1.000 is the shape a real violation would also take at this sample size. What
it does not do is disturb the headline: the discrimination margin, not the call rate, is
the primary endpoint, and d does not order with rung strength either (R1 > R3 > R2), which
is the more interesting non-monotonicity and the one worth a follow-up.

## Limits

- **n = 80 legs per arm, 40 per arm on the goal-leg split.** The margins separate from
  zero; the differences BETWEEN interior rungs do not, and are not claimed.
- **Not version-identical to the ends fire.** CLI 2.1.260 here against 2.1.258 there, and
  a different corpus fingerprint and surface fingerprint. The ends numbers are quoted
  above for reference and the two tables must not be merged into one grid.
- **`execution_protocol` 2.** The staged-160 artifact was bought under protocol 1 and is
  not resumable by this rig; that is the intended consequence of the cell changing shape.
- **d is over READS.** Writes are excluded from the margin by design: recording what you
  learned is the same act on both halves of the twin, so it moves both rates together.
  `any_call_margin_by_rung` in `summary.json` carries the diluted number.
- **One model, one session.** No cross-model or cross-account replication.
- **The bd zero is an affordance-discovery result, not a preference result.** See the verb
  section: bd was on PATH and callable, and was never named to the agent in any prompt or
  any file. No conclusion about bd-versus-native preference is available from this fire.

## Files

- `summary.json` — cells, per-cell metrics, gate block, rig identity
- `summary.json.legs/` — 480 leg files, each with its stream, `role`, verbs, and the
  pin-precedence fingerprint it ran under
