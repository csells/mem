from __future__ import annotations

import math

from membench.beads_ordering.models import (
    ExperimentMode,
    OrderingArm,
    OrderingRunResult,
    ToolLogEntry,
)


def score_agent_run(
    *,
    task_id: str,
    query: str = "",
    corpus_size: int,
    arm: OrderingArm,
    mode: ExperimentMode = ExperimentMode.NAVIGATION,
    repeat: int,
    page_size_label: str | None = None,
    primary_id: str,
    acceptable_ids: set[str],
    expected_facts: list[str],
    forbidden_facts: list[str],
    final_answer: str,
    logs: list[ToolLogEntry],
    input_tokens: int,
    output_tokens: int,
    end_to_end_ms: float,
    primary_rank: int,
    acceptable_rank: int | None,
    page_size: int,
    total_matched: int | None = None,
    failure: str | None = None,
    mem_git_sha: str = "",
    mem_git_dirty: bool = False,
    mem_git_diff_sha256: str = "",
    beads_git_sha: str = "",
    beads_git_dirty: bool = False,
    beads_git_diff_sha256: str = "",
    beads_bin_sha256: str = "",
    structural_order_source_git_sha: str = "",
    agent_model: str = "",
    agent_cli_version: str = "",
) -> OrderingRunResult:
    relevant = acceptable_ids | {primary_id}
    page_logs = [
        entry for entry in logs if entry.operation in {"search", "continue"} and entry.error is None
    ]
    recall_logs = [
        entry for entry in logs if entry.operation == "recall" and entry.memory_id is not None
    ]
    visible_ids = [memory_id for entry in page_logs for memory_id in entry.visible_ids]
    first_useful_log = next(
        (
            entry
            for entry in logs
            if relevant.intersection(entry.visible_ids)
            or (entry.operation == "recall" and entry.memory_id in relevant)
        ),
        None,
    )
    if first_useful_log is None:
        time_to_useful = None
        pages_to_useful = None
        logs_to_useful = logs
    elif first_useful_log.since_agent_start_ms is not None:
        time_to_useful = first_useful_log.since_agent_start_ms + first_useful_log.elapsed_ms
        logs_to_useful = logs[: logs.index(first_useful_log) + 1]
    else:
        cutoff = logs.index(first_useful_log) + 1
        time_to_useful = sum(entry.elapsed_ms for entry in logs[:cutoff])
        logs_to_useful = logs[:cutoff]
    if first_useful_log is not None:
        pages_to_useful = sum(
            1
            for entry in logs[: logs.index(first_useful_log) + 1]
            if entry.operation in {"search", "continue"} and entry.error is None
        )

    recalled_ids = [entry.memory_id for entry in recall_logs if entry.memory_id]
    first_relevant = None if not recalled_ids else recalled_ids[0] in relevant
    first_useful_sequence = first_useful_log.sequence if first_useful_log is not None else 0
    hops = sum(
        1
        for entry in recall_logs
        if entry.followed_reference and entry.sequence >= first_useful_sequence
    )
    total_hops = sum(1 for entry in recall_logs if entry.followed_reference)
    branch_counts = [len(entry.references) for entry in recall_logs]
    navigation_reached_primary = any(
        entry.memory_id == primary_id and entry.followed_reference for entry in recall_logs
    )

    answer = final_answer.casefold()
    decision_lines = [
        line.partition(":")[2].strip().casefold()
        for line in final_answer.splitlines()
        if line.strip().casefold().startswith("decision:")
    ]
    decision = decision_lines[-1] if len(decision_lines) == 1 else ""
    success = (
        failure is None
        and bool(decision)
        and all(fact.casefold() in decision for fact in expected_facts)
        and all(fact.casefold() not in decision for fact in forbidden_facts)
    )
    abstained = any(
        token in answer for token in ("abstain", "insufficient information", "cannot determine")
    )
    useful_reached = any(memory_id in relevant for memory_id in visible_ids) or any(
        memory_id in relevant for memory_id in recalled_ids
    )
    compact_bytes = sum(entry.response_bytes for entry in page_logs)
    compact_tokens = sum(entry.response_tokens_estimate for entry in page_logs)
    retrieval_tokens = sum(entry.response_tokens_estimate for entry in logs)
    useful_page_logs = [
        entry
        for entry in logs_to_useful
        if entry.operation in {"search", "continue"} and entry.error is None
    ]

    return OrderingRunResult(
        run_id=f"{task_id}:{mode.value}:{arm.value}:p{page_size_label or page_size}:r{repeat}",
        task_id=task_id,
        query=query,
        corpus_size=corpus_size,
        arm=arm,
        mode=mode,
        repeat=repeat,
        page_size=page_size_label or str(page_size),
        total_matched=(
            total_matched
            if total_matched is not None
            else next(
                (entry.total_matched for entry in page_logs if entry.total_matched is not None), 0
            )
        ),
        primary_rank=primary_rank,
        primary_page=math.ceil(primary_rank / page_size),
        acceptable_rank=acceptable_rank,
        acceptable_page=(
            math.ceil(acceptable_rank / page_size) if acceptable_rank is not None else None
        ),
        pages_requested=len(page_logs),
        pages_to_first_useful=pages_to_useful,
        page_one_acceptable_visible=(
            primary_rank <= page_size
            or (acceptable_rank is not None and acceptable_rank <= page_size)
        ),
        compact_records_visible=len(visible_ids),
        compact_result_bytes=compact_bytes,
        compact_result_tokens=compact_tokens,
        compact_bytes_to_first_useful=sum(entry.response_bytes for entry in useful_page_logs),
        compact_tokens_to_first_useful=sum(
            entry.response_tokens_estimate for entry in useful_page_logs
        ),
        retrieval_tokens_to_first_useful=sum(
            entry.response_tokens_estimate for entry in logs_to_useful
        ),
        tool_calls_to_first_useful=len(logs_to_useful),
        retrieval_tool_calls=len(logs),
        time_to_first_useful_ms=time_to_useful,
        full_recalls=len(recall_logs),
        first_recalled_relevant=first_relevant,
        graph_hops_after_first_useful=hops,
        graph_hops_total=total_hops,
        reference_edges_exposed=sum(branch_counts),
        branching_factor_mean=(sum(branch_counts) / len(branch_counts) if branch_counts else 0),
        branching_factor_max=max(branch_counts, default=0),
        navigation_reached_primary=navigation_reached_primary,
        retrieval_related_tokens=retrieval_tokens,
        retrieval_latency_ms=sum(entry.elapsed_ms for entry in logs),
        server_candidate_generation_ms=sum(
            entry.server_candidate_generation_ms for entry in page_logs
        ),
        server_ordering_ms=sum(entry.server_ordering_ms for entry in page_logs),
        end_to_end_ms=end_to_end_ms,
        task_success=success,
        abstained=abstained,
        premature_stop=not useful_reached and not abstained,
        agent_input_tokens=input_tokens,
        agent_output_tokens=output_tokens,
        mem_git_sha=mem_git_sha,
        mem_git_dirty=mem_git_dirty,
        mem_git_diff_sha256=mem_git_diff_sha256,
        beads_git_sha=beads_git_sha,
        beads_git_dirty=beads_git_dirty,
        beads_git_diff_sha256=beads_git_diff_sha256,
        beads_bin_sha256=beads_bin_sha256,
        structural_order_source_git_sha=structural_order_source_git_sha,
        agent_model=agent_model,
        agent_cli_version=agent_cli_version,
        final_answer=final_answer,
        failure=failure,
    )
