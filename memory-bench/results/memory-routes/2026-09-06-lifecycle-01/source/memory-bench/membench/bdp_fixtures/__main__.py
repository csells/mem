"""Emit the BDP conformance fixture tree.

    uv run python -m membench.bdp_fixtures --out fixtures/bdp/ordering-families

Re-running over an existing tree is the determinism check: the output is a pure
function of the family names and this package's own seed, so a clean `git diff`
after a re-emit is the evidence, and a dirty one is a defect.

The emitter also deletes documents it could have written at that exact path but
did not, so a removed family cannot leave stale files behind and still show a
clean diff. Ownership is decided on the whole relative path, never on the
basename, and every deletion is printed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from membench.bdp_fixtures.emit import DEFAULT_OUT, emit_all


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="fixture tree to write (default: %(default)s)",
    )
    args = parser.parse_args()

    result = emit_all(out_root=args.out)
    manifest = result["manifest"]
    families = manifest["families"]
    for family in sorted(families):
        entry = families[family]
        print(
            f"{family:45s} {entry['bead_count']:4d} beads  {entry['link_count']:4d} links  "
            f"out {entry['max_outdegree']:3d}  in {entry['max_indegree']:3d}  "
            f"repeats {entry['duplicate_endpoint_tuple_links']:2d}"
        )
    for family, entry in sorted(manifest["collation_family"].items()):
        print(
            f"{family:45s} {entry['bead_count']:4d} beads  {entry['link_count']:4d} links  "
            f"order {entry['reference_order']}"
        )
    for removed in result["pruned"]:
        print(f"pruned {removed}")
    print(
        json.dumps(
            {
                "family_count": manifest["family_count"],
                "pruned": len(result["pruned"]),
                "out": str(args.out),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
