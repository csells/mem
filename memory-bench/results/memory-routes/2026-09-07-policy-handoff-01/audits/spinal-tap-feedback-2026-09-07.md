# Feedback: witness the information dependency before measuring adoption

Date: 2026-09-07
Task/artifact: [Policy handoff experiment](../../../../../specs/plans/0006-policy-handoff-model-sweep.md)
Evidence at capture: untriaged; scored cohort still running

## Comment or observation

The user asked: “were the tasks you assigned sufficient to have learnings that the
agents should save or look up in prep for the task wrt to policy etc?” Earlier the
user objected: “dude. you put instructions to read/write memories into the tasks???”
These are actual user words. Their request to continue is not a quality rating.

Agent observation: a task can produce a correct artifact while leaving an approved
scope unrepresented, or can reuse code without needing the missing agreement.
Neither outcome alone reveals whether memory performed a useful handoff.

## Baseline and result

The earlier ordinary-task screen often allowed function composition to settle the
follow-up. The new construction pairs two approved scopes with identical scalar
behavior and different expanded behavior. The offline probe has 72 identical
initial cases and 32 differing expanded cases out of 64. Independent criticism
also exposed an allocation-priority detail that the first sketch had omitted.

This changed both the task admission test and the fidelity rubric. It did not
justify erasing legitimate source documents, adding memory commands to tasks,
or counting command use as successful knowledge transfer.

## Evidence and limits

See [the probe](../../2026-09-07-policy-fork-probe-01/result.json) and
[research and task analysis](../../../../../specs/research/memory-policy-handoff-spinal-tap-2026-09-07.md).
The probe is author-written, not an agent result. Its mechanical pass establishes
a discriminating construction, not creative quality or adoption reliability.
The scored experiment remains unfinished at capture; no full-lifecycle success
is claimed in this feedback packet.

## Proposed lesson and closure check

For evaluation redesign, attempt a concrete pair of worlds that the existing
artifact cannot distinguish but the intended next task must distinguish. Review
the complete visible context to decide whether the intended trigger actually
occurs. Keep alternative legitimate sources and score them separately.

A later maintenance pass should test whether this step catches evaluations with
uninstantiated triggers without forcing artificial dependency on one tool. Keep
this project-specific packet local; it proposes no change to shared skill rules.
