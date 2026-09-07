"""NeMo Data Designer world generation (Phase 1, mem-t1k5).

This subpackage runs OFFLINE only: it samples diverse enterprise worlds and their
surface prose, freezes them to ``fixtures/worlds/<seed>/``, and is NEVER imported
by CI or scoring. The ``data_designer`` SDK is imported lazily inside the builder
functions (the ``nat`` arm's pattern), so importing this package — and the test
suite — needs neither the SDK nor a running model.

Boundary (ZFC + the generators policy): NeMo produces only the *surface* (org,
personas, channels, prose). The memory-dependency structure and all oracle ground
truth are authored in pure Python by the Phase-2 materialiser. Nothing here
decides an outcome.
"""

from membench.generators.nemo.column_spec import (
    DEFAULT_MODEL_ALIAS,
    DEFAULT_WORLD_SPEC,
    CategorySampler,
    LLMTextColumn,
    WorldColumnSpec,
)
from membench.generators.nemo.world_builder import (
    read_world,
    records_to_world,
    write_world,
)

__all__ = [
    "DEFAULT_MODEL_ALIAS",
    "DEFAULT_WORLD_SPEC",
    "CategorySampler",
    "LLMTextColumn",
    "WorldColumnSpec",
    "read_world",
    "records_to_world",
    "write_world",
]
