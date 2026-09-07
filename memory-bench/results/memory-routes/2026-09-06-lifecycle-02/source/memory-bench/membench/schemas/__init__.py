"""Pydantic schemas mirroring the eval-harness spec.

Each module maps to a spec section:
  - conditions      → §4 evaluation conditions
  - config          → §3 system model (experiment / agent / memory)
  - sequence        → §9.2 benchmark sequence + step
  - memory_event    → §6.2 normalized memory operations + memory_event
  - candidate_memory→ §8 extractor output (schema only; extractor is a later phase)
  - trace           → §8 trace capture
  - metrics         → §12 metric groups (task/efficiency/retrieval/retention/
                      synthesis/action-impact + privacy/interruption per plan §A DIV-4)
"""

from membench.schemas.candidate_memory import CandidateMemory, MemoryType, RetentionPolicy
from membench.schemas.conditions import Condition
from membench.schemas.config import AgentConfig, ExperimentConfig, MemoryConfig
from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation
from membench.schemas.metrics import (
    ActionImpactMetrics,
    EfficiencyMetrics,
    InterruptionMetrics,
    MetricsBundle,
    PrivacyMetrics,
    RetentionMetrics,
    RetrievalMetrics,
    SynthesisMetrics,
    TaskMetrics,
)
from membench.schemas.sequence import BenchmarkSequence, SequenceStep
from membench.schemas.trace import ToolCall, Trace, TraceMessage
from membench.schemas.work_record import (
    AgentRef,
    Execution,
    Landed,
    Lifecycle,
    Links,
    Outcome,
    PrLink,
    Provenance,
    RepoSource,
    SessionCommits,
    Signal,
    TraceRef,
    TraceRun,
    WorkRecord,
)
from membench.schemas.work_record import TraceError as WorkRecordTraceError

__all__ = [
    "ActionImpactMetrics",
    "AgentConfig",
    "AgentRef",
    "BenchmarkSequence",
    "CandidateMemory",
    "Condition",
    "EfficiencyMetrics",
    "Execution",
    "ExperimentConfig",
    "InterruptionMetrics",
    "Landed",
    "Lifecycle",
    "Links",
    "MemoryBackend",
    "MemoryConfig",
    "MemoryEvent",
    "MemoryOperation",
    "MemoryType",
    "MetricsBundle",
    "Outcome",
    "PrLink",
    "PrivacyMetrics",
    "Provenance",
    "RepoSource",
    "RetentionMetrics",
    "RetentionPolicy",
    "RetrievalMetrics",
    "SequenceStep",
    "SessionCommits",
    "Signal",
    "SynthesisMetrics",
    "TaskMetrics",
    "ToolCall",
    "Trace",
    "TraceMessage",
    "TraceRef",
    "TraceRun",
    "WorkRecord",
    "WorkRecordTraceError",
]
