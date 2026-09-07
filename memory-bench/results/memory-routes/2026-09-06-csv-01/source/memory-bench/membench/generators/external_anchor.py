"""External real-anchor loader: adapt an external schema corpus into BenchmarkSequences.

B-1 resolved the headline as SYNTHETIC-ONLY on our own corpus (the coding bundles
can't carry a shared-latent-rule signal — the LOO invariant makes admitted bundles
cross-sibling-disjoint), so the mandatory real anchor is an EXTERNAL dataset loaded
as ``BenchmarkSequence``s. The corpus is BIG-bench ``list_functions``, adapted
offline by ``anchor_adaptation.py`` (mem-mmuu; the earlier SEA-Eval/AgingBench
aspiration never materialised — see Decision 23). This loader reads the
offline-adapted record shape — one JSONL row per task:

    {"task_id", "source", "latent_rule", "episodes": [text, ...], "probe"}

and emits a sequence per row (episodes → write steps, ``latent_rule`` → the probe's
oracle), the SAME shape the S2 generator emits, so one arm scores on both legs. The
checked-in fixture is manifest-frozen (``fixtures/external_anchor/manifest.json``)
so the real-anchor leg runs in CI with no network and no model call (the no-paid-API
posture). Rows where the latent rule appears verbatim — whitespace-normalized — in
an episode OR the probe are REJECTED: an anchor that hands the oracle to the reader
measures recall, not induction. Rows with a blank (whitespace-only) latent_rule are
rejected too — an empty needle would trivially satisfy the leak check and bypass it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from membench.schemas.sequence import (
    BenchmarkSequence,
    MemoryProbe,
    OutcomeCheck,
    SequenceStep,
)


def _normalized(text: str) -> str:
    """Whitespace-collapsed lowercase form, so a rule reformatted with extra spaces,
    line wraps, or case changes still counts as a verbatim leak."""
    return " ".join(text.split()).lower()


def _sequence_from_record(record: dict[str, Any]) -> BenchmarkSequence:
    task_id = record["task_id"]
    latent_rule = record["latent_rule"]
    episodes = record["episodes"]
    if len(episodes) < 2:
        raise ValueError(f"task {task_id!r}: need >= 2 episodes to induce a rule")
    probe = record.get("probe", "What convention do the prior records share?")
    rule_needle = _normalized(latent_rule)
    if not rule_needle:
        raise ValueError(
            f"task {task_id!r}: latent_rule is blank — an empty needle bypasses the "
            "verbatim-leak check, so the loader refuses it (recall-not-induction, mem-z9g6)"
        )
    for text in [*episodes, probe]:
        if rule_needle in _normalized(text):
            raise ValueError(
                f"task {task_id!r}: latent_rule appears verbatim in an episode or the "
                "probe — the anchor would measure recall, not induction (mem-mmuu)"
            )

    steps: list[SequenceStep] = []
    episode_ids: list[str] = []
    for i, content in enumerate(episodes):
        ep_id = f"{task_id}-ep{i}"
        episode_ids.append(ep_id)
        steps.append(
            SequenceStep(
                step_id=f"s{i}-write-{ep_id}",
                user_request=f"Record example {i}.",
                expected_memory_writes={ep_id: content},
            )
        )
    steps.append(
        SequenceStep(
            step_id=f"s{len(episodes)}-probe-rule",
            user_request=probe,
            expected_memory_reads=list(episode_ids),
            memory_probes=[
                MemoryProbe(
                    probe_id="rule-recall",
                    expected_memory_id=episode_ids[0],
                    description=f"latent rule to induce: {latent_rule}",
                )
            ],
            outcome_checks=[
                OutcomeCheck(
                    check_id="rule-recovered",
                    description="the induced rule matches the latent_rule oracle",
                    requires_memory=list(episode_ids),
                )
            ],
        )
    )
    return BenchmarkSequence(
        sequence_id=f"anchor-{task_id}",
        title=f"Real anchor: {task_id}",
        domain=f"schema-induction/anchor:{record.get('source', 'external')}",
        goal=latent_rule,
        steps=steps,
        latent_rule=latent_rule,
    )


def load_external_schema_sequences(path: str | Path) -> list[BenchmarkSequence]:
    """Load the offline-adapted external schema corpus (one JSONL row per task) into
    ``BenchmarkSequence``s — the real-anchor leg for the schema-induction headline."""
    text = Path(path).read_text(encoding="utf-8")
    sequences: list[BenchmarkSequence] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        sequences.append(_sequence_from_record(json.loads(line)))
    if not sequences:
        raise ValueError(f"no records in external anchor {path}")
    return sequences
