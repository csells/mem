"""Small host boundary for the local, externally sandboxed memory experiments.

Launch environments can contain transient credentials and must never be serialized.
Only ``public_settings`` belongs in experiment receipts. Host observations preserve
unknown model/session information rather than inventing a successful identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from membench.schemas.trace import ToolCall


@dataclass
class HostLaunch:
    argv: list[str]
    env: dict[str, str]
    readable_roots: list[Path] = field(default_factory=list)
    public_settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class HostObservation:
    session_id: str | None
    models: list[str]
    calls: list[ToolCall]
    completed: bool
    success: bool
    usage: dict[str, Any] = field(default_factory=dict)
    cost_usd: float | None = None
    errors: list[str] = field(default_factory=list)
    model_evidence: str = "unobserved"
