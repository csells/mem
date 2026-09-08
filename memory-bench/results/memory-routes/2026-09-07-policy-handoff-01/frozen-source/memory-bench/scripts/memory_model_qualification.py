"""Two explicit capture/reuse diagnostics per pinned model; never adoption scores.

Only --run starts inference. Each output directory and started slot is single-use.
Individual failures preserve their evidence and do not block unrelated profiles.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from membench.runner import memory_model_profiles
from scripts import memory_e2e_experiment as e2e
from scripts import memory_unprompted_smoke as smoke


def configuration_hashes() -> dict[str, str | None]:
    """Record configuration identity without reading or exporting credentials."""
    paths = [
        Path.home() / ".codex/config.toml",
        Path.home() / ".claude/settings.json",
        Path.home() / ".config/opencode/opencode.json",
        Path.home() / ".config/opencode/opencode.jsonc",
        Path.home() / ".zcode/cli/config.json",
    ]
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        for path in paths
    }


def qualify_profile(out: Path, profile_id: str) -> dict[str, Any]:
    profile = memory_model_profiles.get_profile(profile_id)
    if out.exists():
        raise FileExistsError("Existing qualification evidence is never reused")
    try:
        return smoke.run(out, profile.host, profile_id)
    except Exception as exc:
        # Existing evidence is kept exactly as written. A failure before a result
        # does not authorize recreating the output directory or repurchasing a slot.
        out.mkdir(parents=True, exist_ok=True)
        failure = {
            "profile_id": profile_id,
            "host": profile.host,
            "passed": False,
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "scope": "explicit integration only; no adoption result",
        }
        smoke.write_json(out / "failure.json", failure)
        return failure


def run(out: Path, profile_ids: list[str], workers: int) -> dict[str, Any]:
    if not profile_ids or len(profile_ids) != len(set(profile_ids)):
        raise ValueError("Declare distinct profile IDs; no repeated qualification slots")
    if workers < 1 or workers > 4:
        raise ValueError("Qualification concurrency must be between one and four")
    profiles = [memory_model_profiles.get_profile(name) for name in profile_ids]
    out.mkdir(parents=True, exist_ok=False)
    before = configuration_hashes()
    smoke.write_json(
        out / "plan.json",
        {
            "profiles": [dataclasses.asdict(profile) for profile in profiles],
            "planned_slots": 2 * len(profiles),
            "workers": workers,
            "timeout_seconds_per_slot": smoke.TIMEOUT,
            "requested_budget_usd_per_slot": 1.50,
            "budget_enforced_by_cli": "Claude only; others have deadline and usage receipts",
            "mode": "isolated",
            "scope": "explicit integration only; no adoption result",
            "retries": 0,
            "capture_host_failure": "retain unstarted reuse slot; continue other profiles",
            "configuration_sha256_before": before,
            "source_sha256": e2e.sources(),
        },
    )
    results = {}
    started = time.monotonic()
    print(
        f"PLAN {len(profiles)} profiles / {2 * len(profiles)} slots, workers={workers}", flush=True
    )
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(qualify_profile, out / profile.id, profile.id): profile.id
            for profile in profiles
        }
        for future in as_completed(futures):
            profile_id = futures[future]
            results[profile_id] = future.result()
            print(
                f"PROFILE {len(results)}/{len(profiles)} {profile_id}: "
                f"passed={results[profile_id]['passed']}",
                flush=True,
            )
    legs = [
        json.loads(path.read_text())
        for profile in profiles
        for path in sorted((out / profile.id).glob("*/result.json"))
    ]
    after = configuration_hashes()
    started_slots = sum(
        len(list((out / profile.id).glob("*/process.json"))) for profile in profiles
    )
    report = {
        "scope": "explicit integration only; no adoption result",
        "profiles": results,
        "planned_slots": 2 * len(profiles),
        "started_slots": started_slots,
        "assessed_slots": len(legs),
        "unstarted_slots": 2 * len(profiles) - started_slots,
        "passed_slots": sum(bool(leg["passed"]) for leg in legs),
        "timed_out_slots": sum(bool(leg["timed_out"]) for leg in legs),
        "reported_cost_usd": sum(leg["cost_usd"] for leg in legs if leg["cost_usd"] is not None),
        "cost_unreported_slots": sum(leg["cost_usd"] is None for leg in legs),
        "started_without_result_slots": started_slots - len(legs),
        "elapsed_s": time.monotonic() - started,
        "configuration_sha256_after": after,
        "configuration_unchanged": before == after,
        "passed": all(result["passed"] for result in results.values()) and before == after,
    }
    smoke.write_json(out / "result.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--profile", choices=memory_model_profiles.PROFILES, action="append")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print("No inference launched. --run qualifies each declared profile once.")
        return 0
    result = run(args.out, args.profile or list(memory_model_profiles.PROFILES), args.workers)
    print(
        json.dumps({key: value for key, value in result.items() if key != "profiles"}), flush=True
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
