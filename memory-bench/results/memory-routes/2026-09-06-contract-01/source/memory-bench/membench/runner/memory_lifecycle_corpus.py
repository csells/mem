"""Configuration lifecycles with public version requirements and private oracles.

The runner supplies the existing memory-routes PROCEDURE unchanged. The policy
strings here are additive treatments, not replacements for that baseline.
Every arm receives the same eight task prompts and historical-snapshot requirement.
Only actual agent-written memory may cross the fresh-session boundaries.
"""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass
from typing import Any, Literal

from membench.runner.memory_routes_corpus import Task, build_tasks

Version = Literal["v1", "v2"]
StageName = Literal[
    "establish",
    "direct",
    "search",
    "revise",
    "revised_direct",
    "revised_search",
    "supplied",
    "historical",
]

SELECTIVE_CAPTURE_GUIDANCE = """Capture an approved lasting decision or permanent correction
when future work will need it. An ordinary reproduction of an existing agreement,
including a task that supplies the whole agreement again, is not a new decision.
Do not create another memory just because you completed another task.
Use the stable current decision reference for a permanent update; preserve any
historical version the task explicitly requires. A required named historical
snapshot is intentional and must not be discarded as a duplicate.
Keep the approved contract and its source distinct from your task-completion notes.
"""

WORKFLOW_CHECK_GUIDANCE = """At task start, identify the requested version and whether the
current request supplies every required value. If values are missing, retrieve the
matching project and version before constructing the artifact: use its exact key
when supplied, otherwise search a distinctive project/topic word and inspect the
matching record. A current contract does not answer a historical-version request.
Before finishing, compare the complete artifact against that contract. Then check
whether this task approved a new contract, permanently revised one, or merely
reproduced it. For a new approval or permanent revision, verify that each required
decision reference contains the intended full contract and that protected history
is preserved. For an ordinary reproduction, avoid redundant memory writes.
Use actual tool results for these checks; do not claim unperformed checks.
"""


@dataclass(frozen=True)
class LifecycleStage:
    name: StageName
    prompt: str
    expected_config: dict[str, Any]
    expected_version: Version
    source_label: str
    lookup_key: str | None
    capture_required: bool
    retrieval_required: bool
    required_write_keys: tuple[str, ...]


@dataclass(frozen=True)
class LifecycleTask:
    id: str
    domain: str
    key: str
    historical_key: str
    task: Task
    initial_config: dict[str, Any]
    revised_config: dict[str, Any]
    revision_patch: dict[str, Any]
    stages: tuple[LifecycleStage, ...]


_REVISION_CHOICES: dict[str, tuple[str, tuple[int | float | bool, ...]]] = {
    "cache": ("ttl_seconds", (120, 300, 600, 900)),
    "csv_export": ("decimal_places", (2, 3, 4)),
    "image_export": ("strip_metadata", (True, False)),
    "logging": ("sample_rate", (0.1, 0.25, 0.5, 0.75)),
}


def _block(value: dict[str, Any]) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=True, indent=2) + "\n```"


def _lifecycle(task: Task, seed: int) -> LifecycleTask:
    initial = copy.deepcopy(task.expected_config)
    revised = copy.deepcopy(initial)
    field, choices = _REVISION_CHOICES[task.domain]
    rng = random.Random(f"memory-lifecycle-v1:{seed}:{task.domain}")
    replacement = rng.choice(
        [choice for choice in choices if choice != initial[task.domain][field]]
    )
    revised[task.domain][field] = replacement
    patch = {task.domain: {field: replacement}}
    historical_key = task.key + ".v1"
    topic = f"{initial['project']} {task.domain.replace('_', ' ')}"
    sources = {
        "v1": f"Initial approved {topic} configuration (v1)",
        "v2": f"Permanently revised approved {topic} configuration (v2)",
    }
    replay = (
        "\n\nThis is an ordinary reproduction of an existing approval, not a new "
        "agreement or a change to the current or historical configuration."
    )

    def stage(
        name: StageName,
        prompt: str,
        version: Version,
        lookup_key: str | None,
        required_write_keys: tuple[str, ...] = (),
    ) -> LifecycleStage:
        return LifecycleStage(
            name=name,
            prompt=prompt,
            expected_config=copy.deepcopy(initial if version == "v1" else revised),
            expected_version=version,
            source_label=sources[version],
            lookup_key=lookup_key,
            capture_required=bool(required_write_keys),
            retrieval_required=name not in {"establish", "supplied"},
            required_write_keys=required_write_keys,
        )

    stages = (
        stage(
            "establish",
            task.establish_prompt
            + f"\n\nSource label: {sources['v1']}.\n"
            + "This approval is version v1. Future fresh work sessions must be able to "
            + "reproduce both the current agreement and this initial version. Preserve the "
            + f"complete approved contract under the current decision reference `{task.key}` "
            + f"and also under the stable historical reference `{historical_key}`. "
            + "The historical reference must continue to describe this exact v1 even if "
            + "the current agreement is permanently revised later.",
            "v1",
            None,
            (task.key, historical_key),
        ),
        stage(
            "direct",
            task.goal_prompt_direct + "\n\nUse the current approved version v1." + replay,
            "v1",
            task.key,
        ),
        stage(
            "search",
            task.goal_prompt_search + "\n\nUse the current approved version v1." + replay,
            "v1",
            None,
        ),
        stage(
            "revise",
            f"Permanently revise the approved {topic} configuration to version v2. "
            "Create config.json in this fresh workspace by starting with the earlier "
            "approved contract and applying only the field change below. Retain every "
            "other field, value, and JSON type; validate the resulting complete JSON. "
            "The earlier configuration file is absent from this checkout.\n\n"
            f"The current decision reference is `{task.key}`. "
            f"Preserve the initial v1 contract at `{historical_key}` unchanged. "
            "The revised full contract becomes the current agreement at the current "
            "reference for future work; this is a permanent decision, not a one-off "
            "reproduction or temporary override.\n\n"
            f"Source label: {sources['v2']}.\n"
            "Approved field change (all unlisted fields stay as previously approved):\n\n"
            + _block(patch),
            "v2",
            task.key,
            (task.key,),
        ),
        stage(
            "revised_direct",
            task.goal_prompt_direct
            + "\n\nUse the current permanently revised version v2."
            + replay,
            "v2",
            task.key,
        ),
        stage(
            "revised_search",
            task.goal_prompt_search
            + "\n\nUse the current permanently revised version v2."
            + replay,
            "v2",
            None,
        ),
        stage(
            "supplied",
            f"Create config.json for {topic} using the complete existing approved version "
            "v2 supplied below. Keep exactly its keys, values, and JSON types, and validate "
            "the result. This supplied contract is sufficient for this task."
            + replay
            + "\n\n"
            + _block(revised),
            "v2",
            None,
        ),
        stage(
            "historical",
            f"Reproduce the original approved version v1 of the {topic} configuration "
            "as config.json in this fresh workspace. The earlier contract and file are "
            "absent from this checkout. Use every original field, value, and JSON type "
            "and validate the complete JSON.\n\n"
            f"The stable historical decision reference for v1 is `{historical_key}`. "
            "This task requests historical reproduction; the permanent current agreement "
            "remains version v2." + replay,
            "v1",
            historical_key,
        ),
    )
    return LifecycleTask(
        id=f"memory-lifecycle-{task.domain}-seed-{seed}",
        domain=task.domain,
        key=task.key,
        historical_key=historical_key,
        task=task,
        initial_config=initial,
        revised_config=revised,
        revision_patch=patch,
        stages=stages,
    )


def build_lifecycles(seed: int = 20260907) -> list[LifecycleTask]:
    """Return four independent eight-session lifecycles from an existing corpus seed.

    Expected configurations are private grading oracles. Stage labels, references,
    and workflow flags describe requirements already stated in the public prompts.
    Deliver the prompt rather than serializing a whole stage to the agent, and do
    not seed either required decision record on the agent's behalf.
    """
    tasks = {task.domain: task for task in build_tasks(seed)}
    return [_lifecycle(tasks[domain], seed) for domain in _REVISION_CHOICES]
