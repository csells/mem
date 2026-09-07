"""Load benchmark sequences from JSON fixtures.

The TS work-audit graph builder is a *data source* (plan §A, DIV-8): it exports
sequences/fixtures as JSON, which this loader validates into typed
`BenchmarkSequence` objects. The skeleton ships one hand-authored fixture; mining
≥10 real sequences is Phase 2 (not this bead).
"""

import json
from pathlib import Path

from membench.schemas.sequence import BenchmarkSequence


def load_sequence(path: str | Path) -> BenchmarkSequence:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return BenchmarkSequence.model_validate(data)
