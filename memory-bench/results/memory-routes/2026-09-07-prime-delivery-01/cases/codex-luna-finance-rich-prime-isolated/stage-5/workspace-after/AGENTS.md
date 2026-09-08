# Project workflow

Use Beads for issue work. At session start or after compaction, run
`bd prime --no-memories` to restore the project workflow. Read the assigned issue
with `bd show <issue-id>` before implementing. Start it with
`bd update <issue-id> --status in_progress`.

Use the Beads skill in `.agents/skills/beads/SKILL.md` for this workflow. Implement
the issue's requirements, verify the resulting behavior, and close the issue
with `bd close <issue-id>` when its work is complete. Consult command help when
syntax is unclear. Preserve earlier files and task history.


## Project memory

Use Beads memories for approved product policies and exceptions, their scope and
rationale, and verified engineering findings that constrain later work. These
records preserve intent and evidence across sessions; working code alone does not
establish an agreement's full meaning.

Before changing behavior governed by an earlier agreement or investigation,
consult the applicable memory and its sources. Before closing work that introduces
an approved durable decision, a permanent revision, or a verified reusable finding,
preserve that knowledge, including approved details beyond today's implementation.
Read the Beads skill's [memory procedure](.agents/skills/beads/references/memory.md)
at these occasions and for historical work. A fully supplied one-off reproduction
needs no memory activity unless it uncovers new durable knowledge.

## Project reference catalog

At session start, if BEADS_MEMORY_INDEX is set, read the JSON file it names for
the available memory keys. This catalog is a reference index, not the contents
of those records. Use the project memory procedure to decide which records the
work needs. An unset variable means this project uses search without a catalog.
