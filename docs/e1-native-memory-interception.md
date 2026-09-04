# Intercepting the harness's own memory tooling

## The question

Can the rig tell, at the moment it happens, that the agent is about to use Claude Code's native
memory files, and answer that reach with the `bd` verbs instead?

## What was built

A `PreToolUse` hook, seeded into each leg's own `CLAUDE_CONFIG_DIR`, so it lives and dies with the
leg and touches nothing on the operator's machine.

- `membench/runner/native_memory_hook.py` installs the hook and decides each pending call.
- The policy constants (`NATIVE_MEMORY_HOOK_*`) live in `tool_surface.py`, so `recognizer_policy`
  folds them into `surface_fingerprint` automatically and a resume cannot serve one mode's legs for
  another's.

It decides with `tool_surface.native_memory_accesses` — the same recognizer the stream scorer uses.
There is no second grammar to drift.

## Two modes, and the difference matters

| mode | what happens | what it is |
| --- | --- | --- |
| `observe` (default) | one JSON line appended, exit 0, the call proceeds, the agent is told nothing | an instrument |
| `redirect` | exit 2 with `bd remember` / `bd recall` named on stderr; the CLI blocks the call and shows the model the reason | a treatment |

`redirect` is guidance delivered at the moment of the reach, which is stronger than R4's prompt
block: it arrives when it is acted on rather than at the top of the turn. Folding it into a ladder
rung would publish an intervention as a disposition, so it is opt-in and never the default.

E1 installs `observe` on every rung. It is byte-identical across the ladder, so it cancels in every
contrast, and it buys a record of the reach made AT the reach — which a leg whose stream was cut by
the timeout bound would otherwise not leave behind. Each leg record now carries `hook_reaches`.

## Failure posture

A hook fault is never a block. A malformed event, an unreadable log, an import that fails: all exit
0 and leave a `hook_error` line. Exiting 2 for the hook's own reasons would refuse a tool call the
agent was entitled to make and publish it as a redirect that never happened.

Installation MERGES into whatever `settings.json` the rung already seeded. R0's whole job is to run
with `autoMemoryEnabled: false`; an install that rewrote the file would turn the native prompt back
on for exactly the rung that must not have it. An unreadable settings file refuses rather than
dropping the pin.

## What this does NOT settle

`redirect` mode has never been fired against a real agent. What is verified is the mechanism: the
script the CLI would run, driven with the payload the CLI would send, blocks the call and puts the
bd verbs in front of the model. Whether an agent so redirected then calls `bd` is the experiment,
and it costs a slice of grid.
