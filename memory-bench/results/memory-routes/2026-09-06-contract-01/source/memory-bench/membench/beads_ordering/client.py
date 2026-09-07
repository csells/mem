from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict

from membench.beads_ordering.models import (
    BM25FConfig,
    CompactMemory,
    DiscoveryPage,
    ExhaustedDiscovery,
    OrderingArm,
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


class CandidateParity(TypedDict):
    candidate_ids: list[str]
    total_matched: int
    candidate_digest: str


class BeadsExperimentError(RuntimeError):
    pass


@dataclass(frozen=True)
class BeadsExperimentClient:
    beads_bin: str
    workspace: str
    page_size: int | str
    bm25f: BM25FConfig
    runner: Runner = subprocess.run

    def page(self, query: str, arm: OrderingArm, continuation: str = "") -> DiscoveryPage:
        argv = [
            self.beads_bin,
            "--json",
            "memories",
            query,
            "--experimental-order",
            arm.value,
            "--page-size",
            str(self.page_size),
            "--bm25f-key-weight",
            str(self.bm25f.key_weight),
            "--bm25f-alias-weight",
            str(self.bm25f.alias_weight),
            "--bm25f-title-weight",
            str(self.bm25f.title_weight),
            "--bm25f-body-weight",
            str(self.bm25f.body_weight),
            "--bm25f-k1",
            str(self.bm25f.k1),
            "--bm25f-b",
            str(self.bm25f.b),
        ]
        if continuation:
            argv += ["--continuation", continuation]
        completed = self.runner(
            argv,
            cwd=self.workspace,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            raise BeadsExperimentError(
                f"bd memories exited {completed.returncode}: {completed.stderr.strip()}"
            )
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise BeadsExperimentError("bd memories emitted malformed JSON") from exc
        payload = raw.get("data", raw) if isinstance(raw, dict) else raw
        try:
            return DiscoveryPage.model_validate(payload)
        except Exception as exc:
            raise BeadsExperimentError("bd memories emitted an invalid experimental page") from exc

    def exhaust(self, query: str, arm: OrderingArm) -> ExhaustedDiscovery:
        pages: list[DiscoveryPage] = []
        items: list[CompactMemory] = []
        continuation = ""
        while True:
            page = self.page(query, arm, continuation)
            pages.append(page)
            items.extend(page.items)
            if page.complete:
                break
            if not page.continuation:
                raise BeadsExperimentError("incomplete page omitted continuation")
            continuation = page.continuation
        if len(items) != pages[0].total_matched:
            raise BeadsExperimentError(
                f"exhausted {len(items)} items but first page declared {pages[0].total_matched}"
            )
        return ExhaustedDiscovery(
            items=tuple(items), pages=tuple(pages), candidate_digest=pages[0].candidate_digest
        )


def _payload_items(payload: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    raw = payload.get("items", ())
    if not isinstance(raw, Sequence):
        raise ValueError("candidate parity: items is not a sequence")
    return [item for item in raw if isinstance(item, Mapping)]


def candidate_parity(pages: Mapping[OrderingArm, Mapping[str, Any]]) -> CandidateParity:
    if OrderingArm.KEY not in pages or len(pages) < 2:
        raise ValueError("candidate parity requires key and at least one competing arm")
    projections: dict[OrderingArm, dict[str, dict[str, Any]]] = {}
    for arm, payload in pages.items():
        by_id: dict[str, dict[str, Any]] = {}
        for raw in _payload_items(payload):
            item = dict(raw)
            item.pop("rank", None)
            memory_id = item.get("id")
            if not isinstance(memory_id, str) or memory_id in by_id:
                raise ValueError(f"candidate parity: invalid or duplicate id under {arm.value}")
            by_id[memory_id] = item
        projections[arm] = by_id
    baseline = projections[OrderingArm.KEY]
    for arm in pages:
        if arm is OrderingArm.KEY:
            continue
        if set(projections[arm]) != set(baseline):
            raise ValueError(f"candidate-set parity failed for {arm.value}")
        for memory_id, projection in projections[arm].items():
            if projection != baseline[memory_id]:
                raise ValueError(f"compact projection parity failed for {arm.value}/{memory_id}")
    totals = {int(payload.get("total_matched", -1)) for payload in pages.values()}
    digests = {str(payload.get("candidate_digest", "")) for payload in pages.values()}
    if len(totals) != 1 or len(digests) != 1:
        raise ValueError("candidate count/digest parity failed")
    return {
        "candidate_ids": sorted(baseline),
        "total_matched": totals.pop(),
        "candidate_digest": digests.pop(),
    }
