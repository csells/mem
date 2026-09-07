Verification is prepared but has not started. The parent must signal that the cross-host sources are frozen before `verify.py --execute` runs. The runner creates an exclusive `gates-01` directory, saves raw logs and per-gate source hashes, and uses fresh external temporary directories with a restricted test subprocess PATH. It makes no model calls and does not format or alter maintained source.

Planned checks: full Python Ruff, Black check, strict mypy crawl, explicit strict mypy for the host/lifecycle/routes scripts, and the targeted host/lifecycle/routes/receipt/native-hook tests. Collection records the final test denominator after source freeze. Unchanged TypeScript and the unrelated full Python runtime suite retain their prior verification.

The earlier lifecycle verification directory and all model/smoke artifacts remain unchanged.
