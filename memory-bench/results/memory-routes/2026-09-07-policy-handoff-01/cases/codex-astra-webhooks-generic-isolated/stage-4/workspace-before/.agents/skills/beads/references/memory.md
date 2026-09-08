# Project memory

Use Beads to make useful durable project knowledge easy to recover in later work.
Capture approved decisions and evidence-backed findings before completing work
when they would help later work or be costly to rediscover. Memory supplies context
within the user's task; it does not authorize additional work.

## Retrieve applicable knowledge

Use the task's supplied information directly when it is sufficient. If needed
knowledge is missing, follow an existing record reference with `bd recall '<key>'`.
Otherwise use `bd memories '<query>'`, choose a relevant result by project, scope,
and applicability, and read the full record with `bd recall '<key>'` before applying
it. Search matches literal substrings in keys and bodies; try a shorter distinctive
term if necessary. Confirm that returned information answers the current question.

If no applicable record exists, use legitimate project files, tests, documentation,
and issue history. Distinguish what the source establishes from your inference.

## Capture and revise faithfully

Before saving, search for existing knowledge about the topic and inspect plausible
matches. Reuse a current key for a permanent revision of the same agreement; choose
a descriptive project/topic key for new knowledge. Preserve unaffected facts.

Give the record a readable opening identifying its scope and applicability. Keep
exact identifiers, types, units, structure, and rationale when later work needs
them. Use structured data for structured agreements and faithful prose for prose
knowledge. Keep evidence and interpretations distinct; preserve source references
without inventing approval, provenance, or validation claims.

```text
bd remember '<complete record>' --key '<key>'
bd recall '<key>'
```

Check the acknowledgment and read back the full record to verify it faithfully
retains the intended knowledge. A failed save is unfinished capture.

When a permanent revision would replace knowledge needed for historical use,
preserve the actual earlier record under a descriptive historical key before
updating the current one. Historical work uses the applicable version and leaves
the standing agreement intact. Using a record or reproducing fully supplied
behavior does not itself call for another capture. Save only new useful knowledge
or a substantive permanent revision.

This CLI's keys identify mutable notes. Historical keys are conventions, not
immutable revision pins or concurrent-write protection.
