# Project workflow

Use Beads for issue work. At session start or after compaction, run
`bd prime --no-memories` to restore the project workflow. Read the assigned issue
with `bd show <issue-id>` before implementing. Start it with
`bd update <issue-id> --status in_progress`. Consult command help when syntax is
unclear.

Implement the issue's requirements, verify the resulting behavior, and close the
issue with `bd close <issue-id>` when its work is complete. Preserve earlier files
and task history. When asked to author follow-up work, create a real issue with an
actionable body and explain which earlier work it depends on. Report the actual
issue ID; never substitute a proposed task for a successfully created one.

Use the project Beads skill at `.agents/skills/beads/SKILL.md` for issue work and
approved durable project knowledge. Activate it through the host's skill facility;
if that facility is unavailable, read the file explicitly. Follow its memory
reference when work depends on an earlier agreement, establishes reusable approved
knowledge, or permanently changes an approved decision.

## Integration qualification only
For each qualification task, also write `markers-<issue-id>.json` with keys rule, skill, reference. Read the Beads skill and its memory reference for their marker values. The rule marker is `f67e8d1be74d482f80dccb869206c6cd`. These diagnostics are excluded from the adoption experiment.
