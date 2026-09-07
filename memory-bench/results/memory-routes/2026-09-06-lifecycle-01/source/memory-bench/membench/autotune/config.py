"""The trial config — the single surface the agent edits between experiments.

This is the autoresearch ``train.py`` analog: everything the agent is allowed to vary
in one place, validated, so a malformed experiment fails loud instead of silently
running something other than what was written.

Scope (v1): **client-side + workload knobs** that need no engine restart — the engine
is assumed already running on its port. Server-launch knobs (gpu-memory-utilization,
max-num-batched-tokens, quantization, prefix-caching on/off) change the *engine*
container and so are driven by editing the compose ``.env`` and relaunching, not by
this config; they are intentionally out of v1's editable surface and noted in
``program.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from membench.autotune._coerce import as_bool, as_float, as_int, as_str

# The engines a trial may target. "local" engines run on the workstation GPU;
# "tokenspeed" is datacenter-only (won't run on a 5090) but is a valid target on a
# rented box — validation allows it, the live run is what would fail there.
_VALID_ENGINES = ("vllm", "sglang", "tokenspeed")


@dataclass(frozen=True)
class TrialConfig:
    """One experiment's knobs. Immutable; the agent writes a fresh JSON each trial."""

    engine: str
    concurrencies: tuple[int, ...]
    max_tokens: int
    temperature: float
    groups: int
    prompts_per_group: int
    prefix_words: int
    logprobs: bool = False

    def __post_init__(self) -> None:
        if self.engine not in _VALID_ENGINES:
            raise ValueError(f"engine must be one of {_VALID_ENGINES}, got {self.engine!r}")
        if not self.concurrencies or any(c < 1 for c in self.concurrencies):
            raise ValueError("concurrencies must be a non-empty list of ints >= 1")
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be in [0, 2]")
        if self.groups < 1 or self.prompts_per_group < 1 or self.prefix_words < 1:
            raise ValueError("groups, prompts_per_group, prefix_words must all be >= 1")

    @property
    def total_requests(self) -> int:
        return self.groups * self.prompts_per_group

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> TrialConfig:
        """Build from a parsed JSON object, failing loud on an unknown key so a typo'd
        knob (e.g. ``max_token``) is an error, not a silently-ignored default."""
        known = set(cls.__dataclass_fields__)
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}; allowed: {sorted(known)}")
        concurrencies = raw.get("concurrencies", [])
        if not isinstance(concurrencies, list):
            raise ValueError("concurrencies must be a JSON array")
        return cls(
            engine=as_str(raw["engine"], "engine"),
            concurrencies=tuple(as_int(c, "concurrencies[]") for c in concurrencies),
            max_tokens=as_int(raw.get("max_tokens", 128), "max_tokens"),
            temperature=as_float(raw.get("temperature", 0.0), "temperature"),
            groups=as_int(raw.get("groups", 1), "groups"),
            prompts_per_group=as_int(raw.get("prompts_per_group", 64), "prompts_per_group"),
            prefix_words=as_int(raw.get("prefix_words", 800), "prefix_words"),
            logprobs=as_bool(raw.get("logprobs", False), "logprobs"),
        )

    @classmethod
    def from_json_file(cls, path: Path) -> TrialConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, object]:
        return {
            "engine": self.engine,
            "concurrencies": list(self.concurrencies),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "groups": self.groups,
            "prompts_per_group": self.prompts_per_group,
            "prefix_words": self.prefix_words,
            "logprobs": self.logprobs,
        }
