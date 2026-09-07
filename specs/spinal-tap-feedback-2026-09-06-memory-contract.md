# Feedback: measure the information available across a handoff

Date: 2026-09-06
Task/artifact: [Memory-route experiments](memory-routes-experiments-2026-09-06.md)
Evidence at capture: untriaged; kept with the project because the evidence contains project-specific material.

## Comment or observation

User request: “run your experiments and report back about how to get agents to reliably store and use memories via search and direct lookup”. This is a task request, not feedback about output quality.

Agent observation: a memory can be successfully written and retrieved while still omitting information needed for the later artifact. Conversely, a prose note may contain usable decisions even when a literal-JSON grader cannot certify it.

## Baseline and result

The main comparison found four omitted captures and four prose captures that lost required structure. The explicit procedure preserved complete contracts and passed all eight tasks through both lookup routes. A targeted repair supplied only output schema while retaining an actual prose capture. Direct lookup then produced the correct artifact; search still substituted a display name for the required identifier. This narrowed the tempting conclusion that memories must always contain JSON: the operative requirement is sufficient exact information across retained memory and current context.

An earlier exploratory run also omitted an important disclosure: generated files would not survive. We retained that run separately and disclosed the reset equally before the full comparison. Otherwise an agent's decision to keep facts in an ordinary output file could be mistaken for refusing memory.

## Evidence and limits

The [schema manifest](../memory-bench/results/memory-routes/2026-09-06-schema-01/manifest.json), [observation correction](../memory-bench/results/memory-routes/2026-09-06-schema-01/measurement-correction.json), and [trace audit](memory-routes-trace-audit-2026-09-06.md) retain the construction and its limits. The schema control is one capture with two goal sessions. It does not estimate a general treatment effect. Oracle checks establish artifact correctness, not creative value or user satisfaction.

## Proposed lesson and closure check

A later skill-maintenance pass should consider asking what information the current task supplies before interpreting a memory experiment. An intervention that restores a missing part of the task contract can distinguish insufficient retained content from inability to retrieve or apply it. Require the revealing fragment to change a claim or expose a limit; additional experiment count alone is not a breakthrough.

Support this lesson with fresh tasks where present-day schemas or identifiers differ in availability. Narrow or reject it if those controls do not change the failure classification. This packet is evidence for later maintenance, not an active global instruction.
