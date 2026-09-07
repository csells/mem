"""OpenRath incorporation — the single projecting-adapter boundary (PRD Phase 1).

mem adopts OpenRath (`docs/prd-openrath-incorporation.md`) at EXACTLY ONE boundary:
a one-direction projecting adapter that reads a runtime `Session` and emits only
mem's existing field-separated types. The Session is never persisted or carried
forward. See `membench.openrath.adapter`.
"""

from membench.openrath.adapter import (
    project_cut_events,
    project_memory_events,
    project_session_to_record,
)

__all__ = [
    "project_cut_events",
    "project_memory_events",
    "project_session_to_record",
]
