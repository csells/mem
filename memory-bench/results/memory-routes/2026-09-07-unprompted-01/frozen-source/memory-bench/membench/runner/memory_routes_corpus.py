"""Deterministic, typed configuration tasks for natural capture and two recall routes.

These are synthetic project contracts, not production-repository samples. The
establish task encounters the complete approved contract while creating a real
artifact. Direct and search goals withhold its values; the supplied control does
not. Memory policy belongs to the runner and is identical across task domains.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any

Scalar = str | int | float | bool


@dataclass(frozen=True)
class Task:
    id: str
    domain: str
    key: str
    context_note: str
    expected_config: dict[str, Any]
    establish_prompt: str
    goal_prompt_direct: str
    goal_prompt_search: str
    goal_prompt_unnecessary: str
    decoys: dict[str, str]


# All choices are ordinary application settings. Field names encode units where
# needed; no random token stands in for a number, encoding, or other typed value.
_OPTIONS: dict[str, dict[str, tuple[Scalar, ...]]] = {
    "deployment": {
        "region": ("us-west-2", "us-east-2", "eu-west-1", "eu-central-1"),
        "replicas": (2, 3, 4, 6),
        "timeout_seconds": (35, 45, 60, 90),
        "health_path": ("/readyz", "/health/ready", "/status/ready", "/healthz"),
    },
    "csv_export": {
        "delimiter": (";", ",", "\t", "|"),
        "encoding": ("utf-8", "utf-8-sig", "utf-16"),
        "line_ending": ("CRLF", "LF"),
        "decimal_places": (2, 3, 4),
        "decimal_separator": (".", ","),
    },
    "retry_queue": {
        "max_attempts": (3, 4, 5, 7),
        "initial_delay_ms": (250, 500, 750, 1000),
        "backoff_multiplier": (2, 3, 4),
        "jitter": ("full", "equal", "none"),
        "dead_letter_queue": ("failed-events", "retry-exhausted", "delivery-failures"),
    },
    "image_export": {
        "format": ("webp", "jpeg", "avif"),
        "max_width_px": (960, 1280, 1600, 1920),
        "quality": (72, 80, 85, 90),
        "strip_metadata": (True, False),
        "resize_mode": ("contain", "cover", "inside"),
    },
    "logging": {
        "level": ("debug", "info", "warning", "error"),
        "format": ("json", "logfmt", "text"),
        "retention_days": (7, 14, 21, 30),
        "sample_rate": (0.1, 0.25, 0.5, 0.75),
        "redact_user_ids": (True, False),
    },
    "backups": {
        "utc_hour": (1, 3, 5, 7),
        "retention_days": (14, 21, 30, 60),
        "compression": ("gzip", "zstd", "none"),
        "storage_class": ("standard", "infrequent_access", "archive"),
        "verify_checksums": (True, False),
    },
    "report_format": {
        "paper_size": ("A4", "Letter", "Legal"),
        "orientation": ("portrait", "landscape"),
        "margin_mm": (12, 15, 18, 20),
        "date_format": ("yyyy-MM-dd", "dd/MM/yyyy", "MM/dd/yyyy"),
        "page_numbers": (True, False),
    },
    "cache": {
        "ttl_seconds": (120, 300, 600, 900),
        "max_entries": (500, 1000, 2000, 5000),
        "eviction_policy": ("lru", "lfu", "fifo"),
        "namespace": ("catalog-v2", "catalog-public", "catalog-shared"),
        "cache_misses": (True, False),
    },
}

_SUBJECTS = {
    "deployment": ("ledger-production", "Ledger production deployment"),
    "csv_export": ("acme-finance", "Acme finance invoice export"),
    "retry_queue": ("parcel-events", "Parcel event delivery retry queue"),
    "image_export": ("gallery-web", "Gallery website image exports"),
    "logging": ("dispatch-service", "Dispatch service application logging"),
    "backups": ("research-archive", "Research archive scheduled backups"),
    "report_format": ("quarterly-operations", "Quarterly operations report formatting"),
    "cache": ("catalog-api", "Catalog API response cache"),
}

_DECOY_PROJECTS = ("orchard", "willow", "summit", "tundra", "harbor")


def _block(config: dict[str, Any]) -> str:
    return "```json\n" + json.dumps(config, ensure_ascii=True, indent=2) + "\n```"


def _configuration(
    domain: str,
    project: str,
    rng: random.Random,
    target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = {}
    for field, choices in _OPTIONS[domain].items():
        candidates = [
            choice for choice in choices if target is None or choice != target[domain][field]
        ]
        settings[field] = rng.choice(candidates)
    return {"project": project, domain: settings}


def _note(key: str, topic: str, config: dict[str, Any]) -> str:
    return (
        f"Approved configuration decision: {topic}.\n"
        f"Decision reference: `{key}`.\n"
        "These are the agreed settings for the named project. The JSON keys, values, "
        "and scalar types below are the approved contract, including units in field names. "
        "Do not substitute conventional defaults.\n\n" + _block(config)
    )


def build_tasks(seed: int) -> list[Task]:
    """Return eight tasks with stable semantic addresses and seed-specific values.

    Five records for other projects resemble each target's topic and schema. Each
    corresponding scalar value differs from the target, so a decoy cannot supply
    any of its settings. The decoys are runner-side initial-store inputs, never
    part of a direct/search goal prompt.
    """
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    result = []
    for domain, (project, topic) in _SUBJECTS.items():
        # Domain-local randomness keeps one domain's additions from changing the
        # other seven task contracts at the same seed.
        rng = random.Random(f"memory-routes-v1:{seed}:{domain}")
        key = f"{domain}.{project}.config"
        config = _configuration(domain, project, rng)
        note = _note(key, topic, config)
        decoys = {}
        for other in _DECOY_PROJECTS:
            other_key = f"{domain}.{other}.config"
            other_config = _configuration(domain, other, rng, target=config)
            decoys[other_key] = _note(
                other_key,
                f"{domain.replace('_', ' ')} for the separate {other} project",
                other_config,
            )
        request = (
            f"Create config.json for {topic} in this fresh project workspace, using the "
            "configuration we agreed in the earlier work session. Write the complete "
            "configuration with its original field names and JSON types, then validate the JSON. "
            "This checkout does not include the earlier decision or configuration file."
        )
        result.append(
            Task(
                id=f"{domain}-seed-{seed}",
                domain=domain,
                key=key,
                context_note=note,
                expected_config=config,
                establish_prompt=(
                    f"Set up {topic} by creating config.json from the approved decision below. "
                    "Write the complete supplied JSON object with exactly its keys, values, "
                    "and types. Validate that the resulting file is valid JSON.\n\n" + note
                ),
                goal_prompt_direct=(
                    request + f"\n\nThe earlier decision's exact filing key is `{key}`."
                ),
                goal_prompt_search=request,
                goal_prompt_unnecessary=(
                    f"Create config.json for {topic}. All current approved settings are "
                    "provided below; use this complete JSON object exactly, including its "
                    "keys, values, and types. These current instructions take precedence "
                    "over any earlier settings. Validate the resulting JSON.\n\n" + _block(config)
                ),
                decoys=decoys,
            )
        )
    return result
