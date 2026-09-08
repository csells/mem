"""S2 — the schema-induction ``BenchmarkSequence`` generator (Tier 0, pure Python).

A schema-induction sequence is N episode-writing steps + 1 probe step. Every
episode INSTANTIATES one latent rule (it contains the rule's signature tokens) but
never states the rule sentence verbatim — so recovering the rule requires
abstracting across episodes, which is exactly the capability ``recombine`` has and
``dedupe_only`` lacks. The probe step's answer is the sequence-level ``latent_rule``
oracle, not any single episode.

The oracle and the whole structure are authored HERE, deterministically: given a
seed the sequence is byte-reproducible (no ``Random`` state escapes; the seed picks
a rule template and the per-episode instance details). This is the Tier-0 floor;
a local model may later fill richer surface prose offline into a frozen fixture,
but the rule, the constraints, and the ids are always ours. CI never calls a model.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from membench.schemas.sequence import (
    BenchmarkSequence,
    MemoryProbe,
    OutcomeCheck,
    SequenceStep,
)

GENERATOR_VERSION = "schema-induction.v1"


@dataclass(frozen=True)
class RuleTemplate:
    """One latent rule + the raw material to instantiate it. ``latent_rule`` is the
    oracle sentence (never emitted verbatim in an episode); ``signature`` are the
    tokens every episode must carry (the rule made concrete); ``instances`` are the
    per-episode varying details that keep episodes distinct."""

    rule_id: str
    latent_rule: str
    signature: tuple[str, ...]
    instances: tuple[str, ...]


# A small bank of templates. Each latent_rule is a full sentence; its signature
# tokens recur in every episode; the instance pool supplies the per-episode surface.
_RULES: tuple[RuleTemplate, ...] = (
    RuleTemplate(
        rule_id="db-naming",
        latent_rule="database columns use snake_case naming",
        signature=("snake_case", "columns"),
        instances=("user_id", "order_total", "created_at", "is_active", "row_count", "last_seen"),
    ),
    RuleTemplate(
        rule_id="handler-logging",
        latent_rule="every request handler logs before it raises",
        signature=("logs", "before", "raises"),
        instances=(
            "auth_handler",
            "upload_handler",
            "search_handler",
            "billing_handler",
            "sync_handler",
        ),
    ),
    RuleTemplate(
        rule_id="retry-backoff",
        latent_rule="network calls retry with exponential backoff",
        signature=("retry", "exponential", "backoff"),
        instances=("fetch_user", "post_event", "load_config", "push_metric", "pull_queue"),
    ),
)


def _instantiate(rule: RuleTemplate, instance: str) -> str:
    """One episode's surface: the rule signature tokens + a distinct instance, never
    the latent_rule sentence verbatim. Deterministic given (rule, instance)."""
    sig = " ".join(rule.signature)
    return f"record for {instance}: {sig} ({instance} convention)"


def generate_schema_induction_sequence(
    *,
    seed: int,
    n_episodes: int = 4,
    rule: RuleTemplate | None = None,
) -> BenchmarkSequence:
    """Emit a deterministic schema-induction ``BenchmarkSequence`` for ``seed``.

    Same seed ⇒ byte-identical sequence. The seed selects the rule template (unless
    one is supplied) and deterministically samples ``n_episodes`` distinct instances."""
    if n_episodes < 2:
        raise ValueError(f"need >= 2 episodes to induce a rule, got {n_episodes}")
    rng = random.Random(seed)
    rule = rule or _RULES[seed % len(_RULES)]
    if n_episodes > len(rule.instances):
        raise ValueError(
            f"rule {rule.rule_id!r} has {len(rule.instances)} instances, asked for {n_episodes}"
        )
    chosen = rng.sample(rule.instances, n_episodes)

    steps: list[SequenceStep] = []
    episode_ids: list[str] = []
    for i, instance in enumerate(chosen):
        ep_id = f"{rule.rule_id}-ep{i}"
        episode_ids.append(ep_id)
        steps.append(
            SequenceStep(
                step_id=f"s{i}-write-{ep_id}",
                user_request=f"Record convention example {i} ({instance}).",
                expected_memory_writes={ep_id: _instantiate(rule, instance)},
            )
        )

    steps.append(
        SequenceStep(
            step_id=f"s{n_episodes}-probe-rule",
            user_request=(
                f"What single convention do the {n_episodes} prior records share? "
                "State the rule, not any one example."
            ),
            expected_memory_reads=list(episode_ids),
            memory_probes=[
                MemoryProbe(
                    probe_id="rule-recall",
                    expected_memory_id=episode_ids[0],
                    description=f"latent rule to induce: {rule.latent_rule}",
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
        sequence_id=f"schema-{rule.rule_id}-seed{seed}-n{n_episodes}",
        title=f"Schema induction: {rule.rule_id}",
        domain="schema-induction",
        goal=rule.latent_rule,
        steps=steps,
        latent_rule=rule.latent_rule,
    )
