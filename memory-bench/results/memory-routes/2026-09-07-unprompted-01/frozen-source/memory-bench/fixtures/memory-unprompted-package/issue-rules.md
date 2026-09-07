# Project workflow

Use Beads for issue work. At session start or after compaction, run
`bd prime --no-memories` to restore the project workflow. Read the assigned issue
with `bd show <issue-id>` before implementing. Start it with
`bd update <issue-id> --status in_progress`.

Use the Beads skill in `.agents/skills/beads/SKILL.md` for this workflow. Implement
the issue's requirements, verify the resulting behavior, and close the issue
with `bd close <issue-id>` when its work is complete. Consult command help when
syntax is unclear. Preserve earlier files and task history.
