"""Telemetry serialization.

Primary wire format = OpenTelemetry GenAI spans; ATIF (NVIDIA NAT's Agentic
Trajectory Interchange Format) is a *derived* export. OTel stays primary to avoid
single-vendor lock-in (plan §1c / §A; ARCHITECTURE.md Decision 12).
"""

from membench.telemetry.atif import trace_to_atif
from membench.telemetry.otel_spans import trace_to_spans

__all__ = ["trace_to_atif", "trace_to_spans"]
