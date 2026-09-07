"""M8 — the shared salience-signal bank (keystone).

A pure-arithmetic, no-model-call, no-network module. Three consumers read it: the
consolidation write-gate/sampler (S1), the foraging stop controller (N1), and the
compaction priority. Per PRD M8 (YAGNI) it ships only the two signals the first
consumer needs — novelty and similarity decay-slope.
"""

from membench.signals.salience import SalienceSignals

__all__ = ["SalienceSignals"]
