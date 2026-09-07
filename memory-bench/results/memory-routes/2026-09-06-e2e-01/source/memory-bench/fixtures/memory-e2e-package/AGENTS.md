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

{{MEMORY_ROUTING}}
