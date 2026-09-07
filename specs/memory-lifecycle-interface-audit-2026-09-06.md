# Available Memory Beads interfaces: bounded build audit

Checked 2026-09-06. No model sessions were launched. Existing Beads checkouts and stores were preserved.

## Finding

**The available feature branch contains executable architecture spikes, not an integrated production Memory Bead type.** Its standalone command builds and passes its four command-contract tests, but it cannot validate the proposed target's lifecycle or shared-history contract. The lifecycle comparison should retain the pinned production `bd` 1.2.1 and describe its result as a legacy-interface protocol/workflow experiment.

The current [proposal, issue #5877](https://github.com/gastownhall/beads/issues/5877), remains open and explicitly defines desired behavior rather than an implementation plan. Its current model requires a first-class Memory kind, shared historical addressing, deletion with retained history, and restoration. The [feature branch's own scope statement](https://github.com/gastownhall/beads/blob/f172284b93dfbd268bf2bbda6f7fe2a79f80fe89/engdocs/spikes/README.md) says the prototypes establish only their named behaviors and providers. Absence of an implementation here does not establish that no other private implementation exists.

## Source identities

| Available artifact | Verified identity | Meaning |
| --- | --- | --- |
| `/Users/csells/Code/gastownhall/beads`, clean `main` | `c0d8da42de5fd15c95adac85e342ba4a121da0fb` | Same SHA returned by the live upstream `main` branch API. Only this working tree is registered. |
| Local and upstream `feat/memory-beads` | `f172284b93dfbd268bf2bbda6f7fe2a79f80fe89` | Same SHA returned by the live feature-branch API; latest commit dated 2026-08-23. Read with `git show`, without checkout changes. |
| Installed `/opt/homebrew/bin/bd` | `bd version 1.2.1 (Homebrew)` | The production legacy interface used by the main experiments. Its experiment manifests carry the binary hash. |
| `gt3code/packages/beads-doltlite/source` | Containing repository HEAD `960e78f2ad0f3e96ae4f7df8b888470ea9a483de` | An older vendored Beads tree requiring Go 1.26.2; no first-class Memory implementation was found in the inspected type/CLI paths. This is the containing repository SHA, not a claimed upstream Beads commit. Its unrelated existing modifications were preserved. |

Live verification used `gh api repos/gastownhall/beads/branches/main`, `gh api repos/gastownhall/beads/branches/feat%2Fmemory-beads`, and `gh issue view 5877`. A title search for Memory Beads PRs returned no matches; that search is corroboration, not exhaustive proof.

The feature branch's [production memory commands](https://github.com/gastownhall/beads/blob/f172284b93dfbd268bf2bbda6f7fe2a79f80fe89/cmd/bd/memory.go) remain the keyed `remember`/`recall`/`memories`/`forget` interface. The branch adds no production CLI implementation change in that file or a production Memory kind in the inspected type definitions. Its [A2 report](https://github.com/gastownhall/beads/blob/f172284b93dfbd268bf2bbda6f7fe2a79f80fe89/engdocs/spikes/memory-beads-a2-revisions.md) describes separate internal provider experiments and explicitly states that their tables and APIs are not a production migration or shared History definition.

## What was built and exercised

Exact copies of four files from the feature SHA were placed under `/private/tmp/beads-memory-spike-audit-ba7p_ddj/source`: the [standalone command](https://github.com/gastownhall/beads/blob/f172284b93dfbd268bf2bbda6f7fe2a79f80fe89/cmd/memory-beads-spike-bd/main.go), its test file, and its two succession fixtures. This command imports only the Go standard library. No full Beads build, dependency download, Dolt server, or installation was needed.

From the copied `cmd/memory-beads-spike-bd` directory, under the experiment's macOS filesystem sandbox:

```text
/opt/homebrew/bin/go build -trimpath -o /private/tmp/beads-memory-spike-audit-ba7p_ddj/bd-spike .
/opt/homebrew/bin/go test -count=1 -v .
```

Environment: `GOENV=off`, `GO111MODULE=off`, `GOTOOLCHAIN=local`, `CGO_ENABLED=0`, `GOPROXY=off`, `GOSUMDB=off`, `GOTELEMETRY=off`; Go cache, GOPATH, build temporary directory, and TMPDIR all pointed inside this new scratch directory. `HOME` was preserved. Toolchain: `go1.26.5 darwin/arm64`.

- Build: exit 0, no stdout/stderr, 1.781 seconds.
- Tests: exit 0; all four passed, including `TestSuccessionWorkflowContract`; 2.971 seconds for the command.
- Built binary SHA-256: `9902e79438845c42c412cda3c9992c138cdd86911357619efe4cd1c820a612bd`.
- Exact `main.go` SHA-256: `009970ad080c922a6ff38695fafb597d150cbd8f2ed479de73eede6318bc6e92`.

Raw receipts and all copied-source hashes remain in `build-evidence.json` and `surface-evidence.json` in that scratch directory. These are deterministic CLI checks, not fresh agent behavior measurements. The [previous succession report](https://github.com/gastownhall/beads/blob/f172284b93dfbd268bf2bbda6f7fe2a79f80fe89/engdocs/spikes/memory-beads-c-agent-succession.md) separately describes one earlier agent run whose exact model and verbatim replies were not retained.

## Actual surface and limits

| Operation | Standalone spike behavior |
| --- | --- |
| Initialize | `init --fixture <JSON>` or `BEADS_MEMORY_SPIKE_FIXTURE`; fixture must define project, memory map, and task map. State is a private JSON file, not a production Beads database. |
| Discover | `memories '<query>' --json --details`: case-insensitive literal substring search across ID, key, title, and current body; ID-sorted summaries with a 96-byte excerpt. No pagination or ranking. |
| Direct read | `recall <ID-or-exact-key> [--revision <revision>] --json`: full selected body and identifying fields. |
| Create/revise | `remember '<body>' --key <key> --author <author>` creates; revision requires `--id <ID> --expected-revision <revision>`. A supplied duplicate key refuses creation. Identical body/key/title is an unchanged result. |
| History | `history <ID> --json` returns the revision array and complete bodies. These fixture revision strings are not the proposed shared Historical Bead Reference format. |
| Task context | `show <fixture-task-ID> --json` returns seeded task references; `prime` supplies guidance without memory bodies. |
| Missing lifecycle/integration | No task create/update/close, forget/delete/restore, link/unlink, generic kind listing, or production storage integration. `close task-1` and `forget mem-storage` both returned exit 1 with “unknown command.” |

A concrete limitation appeared in the manual probe: recalling `mem-storage --revision rev-storage-1` returned title `Storage boundary`; after changing the current title to `Revised storage heading`, the **same historical recall** returned the new title while retaining the old revision ID and body. The command stores body revisions but reads key/title/lifecycle from current state. It therefore does not provide an exact historical snapshot of the complete Memory state. The separate A2 provider fixtures explore a richer state model; they are not wired into this executable.

A wrapper could combine production task commands with this spike's memory commands, but that would introduce two state systems and an experimental interface adapter. It would still be a prototype interaction test. Building and running the **actual proposed type** requires implementation work beyond this bounded audit; substituting the spike must not be presented as that validation.
