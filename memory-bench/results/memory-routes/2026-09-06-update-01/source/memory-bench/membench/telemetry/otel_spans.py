"""Serialize a trace as OpenTelemetry GenAI spans (the primary wire format).

One root span per step (`gen_ai` operation), with child spans per tool call and per
normalized memory event. GenAI semantic-convention attribute keys are used where
they exist (`gen_ai.*`); memory-specific fields are namespaced under `membench.*`.

Returns plain dicts so callers can persist/inspect spans without an OTLP collector.
"""

from typing import TYPE_CHECKING, Any

from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from membench.schemas.trace import Trace

if TYPE_CHECKING:
    from membench.replay import ReplayRun

GEN_AI_SYSTEM = "anthropic"


def _span_to_dict(span: ReadableSpan) -> dict[str, Any]:
    ctx = span.get_span_context()
    if ctx is None:
        raise ValueError(f"span {span.name!r} has no span context")
    parent = span.parent
    return {
        "name": span.name,
        "span_id": format(ctx.span_id, "016x"),
        "trace_id": format(ctx.trace_id, "032x"),
        "parent_span_id": format(parent.span_id, "016x") if parent else None,
        "attributes": dict(span.attributes or {}),
    }


def trace_to_spans(trace: Trace) -> list[dict[str, Any]]:
    """Convert one `Trace` into a flat list of OTel GenAI span dicts."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("membench")

    with tracer.start_as_current_span("memory_eval.step") as step_span:
        step_span.set_attribute("gen_ai.system", GEN_AI_SYSTEM)
        step_span.set_attribute("gen_ai.operation.name", "execute_task")
        step_span.set_attribute("membench.trial_id", trace.trial_id)
        step_span.set_attribute("membench.experiment_id", trace.experiment_id)
        step_span.set_attribute("membench.step_id", trace.step_id)
        step_span.set_attribute("membench.agent_config_id", trace.agent_config_id)
        step_span.set_attribute("membench.memory_config_id", trace.memory_config_id)
        if trace.verifier_result:
            step_span.set_attribute(
                "membench.reward", float(trace.verifier_result.get("reward", 0.0))
            )

        for i, tc in enumerate(trace.tool_calls):
            with tracer.start_as_current_span(f"gen_ai.tool.{tc.name}") as s:
                s.set_attribute("gen_ai.operation.name", "execute_tool")
                s.set_attribute("gen_ai.tool.name", tc.name)
                s.set_attribute("gen_ai.tool.call.id", f"{trace.trial_id}:tool:{i}")

        for ev in trace.memory_events:
            with tracer.start_as_current_span(
                f"membench.memory.{ev.normalized_operation.value}"
            ) as s:
                s.set_attribute("membench.memory.operation", ev.normalized_operation.value)
                s.set_attribute("membench.memory.backend", ev.backend.value)
                s.set_attribute("membench.memory.concrete_tool", ev.concrete_tool)
                s.set_attribute("membench.memory.retrieved_ids", list(ev.retrieved_ids))
                s.set_attribute("membench.memory.written_ids", list(ev.written_ids))
                s.set_attribute("membench.memory.success", ev.success)

    provider.force_flush()
    spans = [_span_to_dict(s) for s in exporter.get_finished_spans()]
    provider.shutdown()
    return spans


def replay_to_spans(run: "ReplayRun") -> list[dict[str, Any]]:
    """Convert a replay run into OTel GenAI span dicts — one root span per
    (arm, track) retrieval, with a child span for its normalized memory event.

    The replay path is failure-triggered retrieval, so its primary telemetry is
    the retrieval-precision-guard signal (Decision 10) carried on the root span.
    The learned-controller feature vector (`rerank_features`, full per-stage
    decisions) is a controller concern (D14, mem-lvp) and is deliberately not
    fabricated here — only what the v1 retrieval arm actually measures is logged.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("membench")

    for result in run.results:
        with tracer.start_as_current_span("memory_eval.replay") as root:
            root.set_attribute("gen_ai.system", GEN_AI_SYSTEM)
            root.set_attribute("gen_ai.operation.name", "retrieve_memory")
            root.set_attribute("membench.work_id", result.work_id)
            root.set_attribute("membench.arm", result.arm)
            root.set_attribute("membench.scope", result.scope or "none")
            root.set_attribute("membench.storage_tier", result.event.backend.value)
            root.set_attribute("membench.retrieval.total_matched", result.total_matched)
            root.set_attribute("membench.retrieval.near_duplicate_top", result.near_duplicate_top)
            root.set_attribute(
                "membench.retrieval.injected_context_chars", result.injected_context_chars
            )
            root.set_attribute("membench.retrieval.eligible_count", result.eligible_count)

            ev = result.event
            with tracer.start_as_current_span(
                f"membench.memory.{ev.normalized_operation.value}"
            ) as s:
                s.set_attribute("membench.memory.operation", ev.normalized_operation.value)
                s.set_attribute("membench.memory.backend", ev.backend.value)
                s.set_attribute("membench.memory.concrete_tool", ev.concrete_tool)
                s.set_attribute("membench.memory.retrieved_ids", list(ev.retrieved_ids))
                s.set_attribute("membench.memory.success", ev.success)

    provider.force_flush()
    spans = [_span_to_dict(s) for s in exporter.get_finished_spans()]
    provider.shutdown()
    return spans
