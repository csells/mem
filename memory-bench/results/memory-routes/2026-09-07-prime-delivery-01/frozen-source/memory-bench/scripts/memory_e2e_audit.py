"""Write a separate posthoc action audit; no models or real CLI commands run."""

from __future__ import annotations

import argparse
from pathlib import Path

from membench.runner.memory_e2e_audit import write_audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = write_audit(args.run, args.out)
    print(
        f"Wrote {args.out}: {sum(r['recorded_execution_files'] for r in result['runs'])} executions"
    )


if __name__ == "__main__":
    main()
