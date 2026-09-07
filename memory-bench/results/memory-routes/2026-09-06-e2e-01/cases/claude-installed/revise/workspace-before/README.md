# Catalog reader components

This disposable Python project supplies a generic in-memory `ResponseCache` in
`cache_engine.py`. Implement the component requested by the assigned issue.
Python's standard library is sufficient; no dependency installation is required.

Each component module exports:

- `POLICY`: the complete approved nested policy, preserving JSON keys and types.
- `SOURCE` and `RATIONALE`: the exact named approval fields; keep interpretations
  separate from these fields.
- `create_cache(clock)`: returns a working cache governed by that policy. `clock`
  is an injected function returning seconds. Reusing the generic engine is fine.

A cache supports `get(key, loader)`, returning a cached value or calling the
zero-argument loader. Its `keys()` exposes live namespaced keys. Expiry occurs at
age greater than or equal to TTL; reads do not change FIFO insertion order;
expired entries do not consume capacity. The policy decides whether loader
results of `None` are cached. A cache instance owns its own entries.

Retain earlier components and project history. Each new reader is a sibling
component; implementing one does not require deleting earlier work. Run
`python3 -m unittest discover -s tests` for the public API check, and add relevant
component tests when implementing behavior. These checks do not certify that a
component uses the approved policy.
