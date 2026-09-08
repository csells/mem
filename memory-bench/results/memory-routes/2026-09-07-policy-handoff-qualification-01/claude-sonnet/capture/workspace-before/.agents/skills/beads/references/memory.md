# Approved project memory

Use Beads to preserve approved knowledge that future project work will reuse.
Memory supplies context within the user's delegation; it does not authorize new
work. Capture a new reusable agreement or a permanent approved change before
completing the issue. Completing a task or reproducing an existing agreement is
not itself a reason to write memory.

## Select the applicable agreement

Inspect the task's references and intended project, scope, and version before
implementing. A complete supplied agreement can be used directly without a memory
lookup. When an earlier agreement is needed and its key is supplied, fully recall
that key. Otherwise search for a distinctive project or topic term, inspect the
matching scope, and fully recall the selected record before applying it.

```text
bd recall '<key>'
bd memories '<query>'
```

Search matches literal substrings in keys and bodies, not semantic similarity.
Try a shorter distinctive term if a search is empty. A search preview is not the
full agreement. If no applicable memory exists, inspect legitimate project files
or earlier tasks and identify that source; report unresolved missing information
instead of inventing an agreement or claiming a memory lookup succeeded.

## Preserve and revise faithfully

Before writing, search for the agreement's project and scope, then recall plausible
matches. Reuse the existing current key for a permanent revision of that agreement;
choose a descriptive project/scope key for genuinely new knowledge. Apply only the
approved change and preserve every unaffected fact. Do not create an alias merely
because the new task describes the same agreement differently.

Give the note a readable preview naming its project, scope, and applicability.
Preserve exact identifiers, values, types, units, field names, and nested structure
when those are part of the agreement. Keep structured agreements as complete
structured data, such as a fenced JSON object, alongside the preview. Use faithful
prose for prose knowledge; every memory does not need JSON. Preserve the supplied
source and rationale without adding an invented approval, date, historical claim,
or validation result. Keep your interpretations distinct from sourced facts.

```text
bd remember '<complete note>' --key '<key>'
bd recall '<key>'
```

Check the write acknowledgment, then recall the exact key and verify the complete
retained note. A failed write or incomplete readback is unfinished preservation.

If the work needs later reproduction of a named historical approval, retain a
separately named snapshot of the actual original agreement before replacing the
current note. Keep that snapshot's entire body unchanged, including its title and
source. Recall the historical snapshot for historical work; leave the current
agreement intact. Reproduction leaves both records unchanged. Do not resave or
duplicate a note just because another task used it.

## Author a usable task reference

When authoring a dependent task, explain why the agreement applies and cite the
actual successfully retained key chosen for that agreement. State whether the task
needs the current agreement or a particular historical snapshot, and cite that
snapshot only when historical reproduction is required. Confirm that the reference
resolves to the intended complete record. If capture failed or the task was not
created, report the missing handoff instead of inventing an identity.

This legacy CLI stores mutable notes by key. A task-body key is a textual reference,
and a separately named snapshot remains editable; neither provides an immutable
revision pin, automatic reference integrity, or concurrent-write protection.

For integration qualification, the reference marker is `93950aa1092740439f3cc7430167bfc7`.
