"""Memory systems (arms) behind one uniform interface (§14 memory_systems/).

First-run arm scope is `none` / `ours` / `builtin` (fork 4):

- `none` — the no-memory control (condition A).
- `oracle` — the memory-sensitivity ceiling (condition B), harness-injected.
- `filesystem` — the skeleton's id-based reference integrated system.
- `ours` — retrieval-v1 (mem-di8) over the work-audit graph (condition C);
  failure-triggered/replay-only.
- `builtin` — the agent's own native Claude/Codex memory, the baseline-to-beat
  (mem-whi). mem's store stays uninvolved (no surface, no capture); the agent's
  native memory is the continuity channel, enabled at launch (mem-mor1 D-F).

`mem0`, `a-mem`, `nat`, and `graphiti` are the wired competitive arms (mem-lvp.2 /
mem-lvp.9 / mem-lvp.3 / mem-lvp.4), all `AbstractSemanticArm` subclasses behind an
injectable client. `nemo-embed` (mem-sikg) is a second, architecturally-different
neural BASELINE next to `mem0` — a plain dense NVIDIA NeMo embedder with exact cosine
top-k, same seam, NOT an `ours` upgrade.
"""

from typing import Any

from membench.memory_systems.amem_system import AMemMemory
from membench.memory_systems.async_bridge import AsyncClientBridge
from membench.memory_systems.base import (
    MemorySystem,
    RetrievalRequest,
    RetrieveResult,
)
from membench.memory_systems.builtin_system import BuiltinMemory
from membench.memory_systems.consolidating_system import ConsolidatingMemory
from membench.memory_systems.filesystem_system import FilesystemMemory
from membench.memory_systems.graphiti_system import GraphitiMemory
from membench.memory_systems.lexical_system import LexicalTopKMemory
from membench.memory_systems.local_stack import (
    LocalModelStack,
    LocalStackUnavailableError,
)
from membench.memory_systems.mem0_system import Mem0Memory
from membench.memory_systems.nat_system import NatMemory
from membench.memory_systems.nemo_embed_system import NemoEmbedMemory
from membench.memory_systems.none_system import NoneMemory
from membench.memory_systems.openwiki_system import OpenWikiMemory
from membench.memory_systems.oracle_system import OracleMemory
from membench.memory_systems.ours_live_system import OursLiveMemory
from membench.memory_systems.ours_system import OursIssueTriggerMemory, OursMemory
from membench.memory_systems.retention_scheduled_system import RetentionScheduledMemory
from membench.memory_systems.semantic_base import (
    AbstractSemanticArm,
    SemanticHit,
    SemanticMemoryClient,
)

__all__ = [
    "AMemMemory",
    "AbstractSemanticArm",
    "AsyncClientBridge",
    "BuiltinMemory",
    "ConsolidatingMemory",
    "FilesystemMemory",
    "GraphitiMemory",
    "LexicalTopKMemory",
    "LocalModelStack",
    "LocalStackUnavailableError",
    "Mem0Memory",
    "MemorySystem",
    "NatMemory",
    "NemoEmbedMemory",
    "NoneMemory",
    "OpenWikiMemory",
    "OracleMemory",
    "OursIssueTriggerMemory",
    "OursLiveMemory",
    "OursMemory",
    "RetentionScheduledMemory",
    "RetrievalRequest",
    "RetrieveResult",
    "SemanticHit",
    "SemanticMemoryClient",
    "build_memory_system",
    "wired_memory_systems",
]


def _systems_registry() -> dict[str, type[MemorySystem]]:
    """The single source of truth for the wired arm set (name → class)."""
    return {
        "none": NoneMemory,
        "oracle": OracleMemory,
        "filesystem": FilesystemMemory,
        "lexical": LexicalTopKMemory,
        "consolidating": ConsolidatingMemory,
        "retention_scheduled": RetentionScheduledMemory,
        "ours": OursMemory,
        "ours-issue-trigger": OursIssueTriggerMemory,
        "ours-live": OursLiveMemory,
        "builtin": BuiltinMemory,
        "mem0": Mem0Memory,
        "nemo-embed": NemoEmbedMemory,
        "a-mem": AMemMemory,
        "nat": NatMemory,
        "graphiti": GraphitiMemory,
        "openwiki": OpenWikiMemory,
    }


def wired_memory_systems() -> tuple[str, ...]:
    """The wired arm names, sorted — the validation surface for callers that select
    an arm by name at a boundary (e.g. the `MEMBENCH_MEMORY_SYSTEM` launch override)
    without constructing one. Reflects `_systems_registry` so it never drifts."""
    return tuple(sorted(_systems_registry()))


def build_memory_system(name: str, **kwargs: Any) -> MemorySystem:
    """Factory over the wired arm set. Raises on an unknown name rather than silently
    substituting a default (an unknown memory system is a config error)."""
    systems = _systems_registry()
    cls = systems.get(name)
    if cls is None:
        raise ValueError(f"Unknown memory system {name!r}. Wired: {sorted(systems)}.")
    return cls(**kwargs)
