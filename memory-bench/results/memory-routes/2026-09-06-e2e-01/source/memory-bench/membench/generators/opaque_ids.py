"""Opaque agent-visible memory ids (mem-z3gi).

``build_agent_prompt`` renders memory ids verbatim to the real agent
("[{mid}] {content}"), so a labeled id — ``...-distractor``, ``...-v1``, an
embedded subject key — leaks the class ground truth: a Confusion/Staleness run
would measure suffix-reading, not memory. Generators therefore derive every
agent-visible id through ``opaque_memory_id``: a deterministic, content-keyed
hash that carries zero class information. The label→id mapping is never stored
in an agent-visible field; it is a pure function of ``(namespace, label)``, so
harness-side code (grading, diagnostics, tests) recomputes it on demand.
"""

from __future__ import annotations

import hashlib
import re

# What an opaque agent-visible id looks like. Tests assert every id a generator
# exposes to the agent matches this — the format itself cannot encode a class.
OPAQUE_ID_PATTERN = re.compile(r"^m-[0-9a-f]{16}$")


def opaque_memory_id(namespace: str, label: str) -> str:
    """The opaque id for harness-side ``label`` under ``namespace`` (the sequence /
    world scope that keeps ids collision-free across tasks). Deterministic: same
    inputs ⇒ same id, so frozen worlds stay byte-reproducible."""
    digest = hashlib.sha256(f"{namespace}/{label}".encode()).hexdigest()
    return f"m-{digest[:16]}"
