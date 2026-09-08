"""Harbor integration — emit benchmark sequences as Harbor tasks (§14).

Follows Harbor's REAL extension shape (verified against harbor==0.3): a task dir of
`task.toml` + `instruction.md` + `environment/Dockerfile` + `tests/test.sh`
(+ optional `solution/solve.sh`), with the verifier writing a reward in [0,1] to
`/logs/verifier/reward.txt`. (NOT the spec §14 hypothesized
task_adapter.py/dataset_adapter.py/scorer.py names — plan §A, DIV-7.)
"""

from membench.harbor.adapter import REWARD_TEXT_PATH, SequenceAdapter
from membench.harbor.grid import (
    AgentRunner,
    ErrorExtractor,
    HarborRunner,
    StubRunner,
    harvest_run_trace,
    run_grid,
)
from membench.harbor.memory_inject import (
    MEMORY_FILENAME,
    DeferredRungError,
    OracleSelfLeakError,
    inject_rung_memory,
)
from membench.harbor.workrecord_adapter import WorkRecordLadderAdapter

__all__ = [
    "MEMORY_FILENAME",
    "REWARD_TEXT_PATH",
    "AgentRunner",
    "DeferredRungError",
    "ErrorExtractor",
    "HarborRunner",
    "OracleSelfLeakError",
    "SequenceAdapter",
    "StubRunner",
    "WorkRecordLadderAdapter",
    "harvest_run_trace",
    "inject_rung_memory",
    "run_grid",
]
