"""Synthetic BenchmarkSequence generators (Tier-0 pure-Python oracle authoring).

Per the PRD synthetic-generation tooling decision: WE author the ground truth —
the latent rule, the structural constraints (episode ⊨ rule; rule ∉ any episode) —
in pure Python, deterministically and seed-reproducibly. A local model may LATER
fill only the NL surface text of episodes, run offline into a frozen,
``generator_version``-tagged fixture; CI never calls a model.
"""

from membench.generators.enterprise_workflow import materialize_project, materialize_world
from membench.generators.ftp_shapes import (
    FTP_SHAPES,
    FtpShape,
    assert_shapes_grounded,
    memory_dependent_shapes,
)
from membench.generators.memory_necessity_gate import NecessityResult, memory_necessity_gate
from membench.generators.schema_induction import (
    GENERATOR_VERSION,
    generate_schema_induction_sequence,
)
from membench.generators.shape_wellformedness_gate import (
    WellformednessResult,
    shape_wellformedness_gate,
)
from membench.generators.synthetic_task import (
    SHAPE_BLUEPRINTS,
    generate_shape_sequences,
)

__all__ = [
    "FTP_SHAPES",
    "GENERATOR_VERSION",
    "SHAPE_BLUEPRINTS",
    "FtpShape",
    "NecessityResult",
    "WellformednessResult",
    "assert_shapes_grounded",
    "generate_schema_induction_sequence",
    "generate_shape_sequences",
    "materialize_project",
    "materialize_world",
    "memory_dependent_shapes",
    "memory_necessity_gate",
    "shape_wellformedness_gate",
]
