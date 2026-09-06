# bd adoption harness

A harness for one question: **will a coding agent choose a memory tool on its own,
recover what it stored in a later session, and act on it?**

Task success cannot answer that question by itself. In our first run, the agents that
were given only general "you have persistent memory" guidance solved their tasks
without touching bd at all. They wrote the facts to Claude Code's own memory files
instead. The task passed; bd was never used. The harness therefore measures the
pathway as well as the outcome, and it reads that pathway from execution receipts
rather than from what the agent reports doing.

Everything below runs against the real `claude` CLI and a real `bd` binary. There is no
simulation mode. A run costs money on whatever account supplies the credentials.

## What one trial looks like

A trial is a **pair** of agent sessions against the same synthetic project.

1. **Establish session.** The agent works a task and encounters several facts, one of
   which is an opaque token it cannot guess or re-derive. Nothing tells it to save
   anything specific.
2. The harness clears the working directory. The bd store and the native memory
   directory survive.
3. **Goal session.** A fresh agent, with no conversation history, gets a task that
   needs that token.

Every task ships as twins:

| Variant | Goal prompt | What a bd read means |
|---|---|---|
| `necessary` | omits the token | the agent had to recover it from memory |
| `unnecessary` | supplies the token | reading memory was avoidable work |

The `unnecessary` twin is the control. Without it, a condition could score well on
adoption purely by making the agent read memory constantly.

## The three conditions

All three run the same tasks, the same tools, the same isolated store lifecycle, and
the same default native-memory settings. Only the guidance differs.

| Condition | What the agent is told | Native memory |
|---|---|---|
| `generic` | general persistent-memory guidance, bd never named | observed |
| `explicit` | bd deployment context plus working `remember` / `recall` / `memories` examples | observed |
| `redirect` | the explicit context, plus a hook that blocks a native-memory access and answers it by naming the bd commands | intercepted |

"Observed" means a `PreToolUse` hook records the reach and lets it through.
"Intercepted" means the same hook refuses the call and returns a message pointing at
bd. The recognizer that decides what counts as a native-memory access is shared with
the scoring path, so the hook and the scorer cannot drift apart.

## What we measured with it

96 pairs, 192 sessions, `claude-sonnet-4-6` on Claude Code 2.1.261, 8 generated task
clusters, $13.47 of estimated spend.

| Condition | Captured the token | Recalled it | Recalled it *before* acting | Full bd handoff | Completed the task |
|---|---:|---:|---:|---:|---:|
| `generic` | 0/16 | 0/16 | 0/16 | **0/16** | 16/16 |
| `explicit` | 10/16 | 9/16 | 8/16 | **8/16** | 14/16 |
| `redirect` | 15/16 | 15/16 | 12/16 | **12/16** | 12/16 |

Two details in that table matter as much as the headline. The `generic` row is an
agent that never discovers the tool and passes every task anyway. And task completion
falls as adoption rises, because several agents that did recall the token then misread
what it was for. Adoption and correctness are separate outcomes.

Full write-up: [RESULTS.md](RESULTS.md). Definitions and known limits:
[METHODS.md](METHODS.md).

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/). Run everything from `memory-bench/`.
- The `claude` CLI on `PATH`. Pin the version you intend to run with; the harness
  refuses to start if the installed version differs from what you pass.
- A `bd` binary on `PATH`, or an absolute path in `MEMBENCH_BD_BINARY`. The harness
  records its path, SHA-256 and version into the run manifest and refuses to resume a
  run if the binary underneath it changed.
- `CLAUDE_CODE_OAUTH_TOKEN` set. Generate one with `claude setup-token`.
- `ANTHROPIC_API_KEY` **unset**. A set key silently reroutes every child session onto
  the metered API, which is both a surprise bill and a different measurement from the
  one the manifest claims. The harness refuses to spend while it is set.

```bash
cd memory-bench
uv sync
```

## Build the task corpus

The corpus is generated deterministically from seeds, so it is not committed. Eight
seeds reproduce the exact corpus our published numbers were measured on:

```bash
for s in 0 1 2 3 4 5 6 7; do
  PYTHONPATH=. uv run python scripts/generate_worlds.py \
    --seed "$s" --personas 4 --tasks 2 --offline --tool-requiring \
    --out fixtures/worlds-tool
done

PYTHONPATH=. uv run python scripts/verify_worlds.py fixtures/worlds-tool
# 8/8 worlds reproduce deterministically
```

`--offline` means the persona rows are authored by seeded code, with no model call and
no network. Each world is admitted only if a memory-necessity gate confirms the task
genuinely cannot be solved without the retained facts.

If your corpus is right, the plan you freeze in the next step will carry
`"corpus_fingerprint": "24c77b5bc5c10e5d"`, the same fingerprint as our run.

## Freeze a plan (spends nothing)

Without `--fire`, the entry point only writes a manifest. No agent starts.

```bash
PYTHONPATH=. uv run python -m membench.runner.bd_experiment \
  --out runs/my-first-run \
  --model claude-sonnet-4-6 \
  --expect-cli-version "$(claude --version | cut -d' ' -f1)" \
  --tasks 8 --repeats 2
```

The manifest holds the full randomized schedule, the model, the CLI version, the bd
identity, a hash of every harness source file, and the corpus fingerprint. Read it
before spending anything. `--tasks 8 --repeats 2` is the shape of our published run:
96 pairs, 192 sessions.

## Run it

```bash
PYTHONPATH=. uv run python -m membench.runner.bd_experiment \
  --out runs/my-first-run \
  --model claude-sonnet-4-6 \
  --expect-cli-version "$(claude --version | cut -d' ' -f1)" \
  --tasks 8 --repeats 2 \
  --fire --max-pairs 1
```

`--max-pairs` bounds how many *new* pairs this invocation may buy. It defaults to 1, so
the obvious first command buys one pair and stops. Re-run with a larger `--max-pairs` to
continue; already-completed pairs are reused, never repurchased. Budget roughly **$0.14
per pair** at the rates our run saw, so a full 96-pair replication is around $13.

Start with one pair and read its output before scaling up.

### If a run is interrupted

A pair whose directory exists without a `cell.json` is treated as a **purchased but
unreconciled** trial. The next invocation refuses to start rather than silently buying
a replacement, because that process may have spent money before it wrote anything.
Inspect `runs/<name>/pairs/<condition>/<hash>/<repeat>/` (it will hold `started.json`
and any completed `legs/`, plus a `halt.json` recording what went wrong), decide what
happened, then move or delete that directory deliberately.

## Read the results

```bash
PYTHONPATH=. uv run python scripts/analyze_bd_experiment.py runs/my-first-run \
  --out runs/my-first-run-analysis
```

That writes `analysis.json` and a human-readable `report.md`; the pair from our own run
is in [`reference-run/`](reference-run/report.md) if you want to see the shape before you
spend anything. Denominators come from the *schedule*, not from whatever completed, so a
missing or unmeasured pair stays visible in the counts instead of quietly shrinking the
sample.

A second, independent check re-derives the task outcome from the actual file the agent
wrote rather than from the frozen scorer:

```bash
PYTHONPATH=. uv run python scripts/audit_bd_actions.py runs/my-first-run \
  --out runs/my-first-run-audit
```

On our 96 pairs the two agreed everywhere. Running both is how you find out whether
that holds for you.

### Layout of a run directory

```
runs/my-first-run/
  manifest.json                      frozen identity and schedule
  pairs/<condition>/<task-hash>/<repeat>/
    started.json                     pair identity, written before any spend
    legs/                            one row per session: argv, exit status, receipts
    cell.json                        scored outcome, written last
    halt.json                        present only if the pair failed
```

Every bd invocation inside a session is wrapped so that its actual argv, exit status
and per-stream output are recorded. A verb on a command line is not an operation: in
an earlier run the only apparent "memory write" was a `bd remember list` that bd
*refused*, and only the recorded result could say so.

## Refusals you may hit

The harness stops before spending, with the reason, when:

- `ANTHROPIC_API_KEY` is set
- `CLAUDE_CODE_OAUTH_TOKEN` is unset
- the model is not pinned
- the installed `claude` version differs from `--expect-cli-version`
- the resolved `bd` binary differs from the one in the frozen manifest
- the output directory holds a plan that disagrees with the one about to run
- a previously started pair has no recorded outcome

These are ordered so that no refusal message sends you into a different refusal.

## What this does not tell you

Eight generated task clusters, one model, repeats inside a single episode. The result
is a bounded adoption comparison, not a production reliability estimate. The tasks use
opaque synthetic tokens, which agents sometimes reject as suspicious or mistake for
lookup keys; those failures are part of the numbers rather than repaired after the
fact. The harness measures bd used as a CLI through Bash, not a memory tool exposed
over MCP. And a full handoff is an observed conjunction, not proof the action depended
on bd when another channel could also have supplied the value.

[METHODS.md](METHODS.md) states these limits in full, along with the phase differences
between the pilot and the confirmation run.
