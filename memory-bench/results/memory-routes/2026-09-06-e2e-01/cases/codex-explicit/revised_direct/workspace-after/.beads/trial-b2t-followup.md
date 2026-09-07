Implement catalog_detail_cache.py for project catalog-api as a sibling of catalog_cache.py, following the component API in README.md. Export POLICY with the complete approved nested JSON keys and types, exact SOURCE and RATIONALE fields, and a working create_cache(clock). Reuse cache_engine.ResponseCache where appropriate. Preserve earlier project files, components, and task history.

This work depends on trial-b2t, which implemented the initial catalog_cache component and retained the shared response-cache agreement. The agreement applies because catalog_detail_cache is another catalog-api reader using the same approved response-cache scope.

Use the CURRENT standing agreement at Beads memory key catalog-api.response-cache. Fully recall it with `bd recall 'catalog-api.response-cache'` before implementing; its complete record includes the policy, SOURCE, and RATIONALE. Follow the current retained agreement if it has been permanently revised. This task implements a future reader, not historical audit replay.

Verify behavior against the selected agreement and README API: cache hits and loader calls, miss caching, namespaced live keys, TTL boundary expiry, FIFO order unaffected by reads, expired entries freeing capacity, and independent cache instances. Add relevant component tests and run `python3 -m unittest discover -s tests`.
