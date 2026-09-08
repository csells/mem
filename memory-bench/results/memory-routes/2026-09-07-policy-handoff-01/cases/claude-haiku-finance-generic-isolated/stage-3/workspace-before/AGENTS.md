# Project workflow

Use Beads for issue work. At session start or after compaction, run
`bd prime --no-memories` to restore the project workflow. Read the assigned issue
with `bd show <issue-id>` before implementing. Start it with
`bd update <issue-id> --status in_progress`.

Use the Beads skill in `.agents/skills/beads/SKILL.md` for this workflow. Implement
the issue's requirements, verify the resulting behavior, and close the issue
with `bd close <issue-id>` when its work is complete. Consult command help when
syntax is unclear. Preserve earlier files and task history.


## Project knowledge

Before finishing work that establishes a useful durable decision, fact, or lesson,
preserve it in Beads when it would help later work or be costly to rediscover.
When implementing work that depends on missing project knowledge, retrieve the
applicable record: follow a known reference directly, or search and inspect the
full result. Read the Beads skill's [memory procedure](.agents/skills/beads/references/memory.md)
for capture, lookup, permanent revisions, and historical use. Reproducing an
existing agreement does not by itself justify another save.

## Project reference catalog

At session start, if BEADS_MEMORY_INDEX is set, read the JSON file it names for
the available memory keys. This catalog is a reference index, not the contents
of those records. Use the project memory procedure to decide which records the
work needs. An unset variable means this project uses search without a catalog.
