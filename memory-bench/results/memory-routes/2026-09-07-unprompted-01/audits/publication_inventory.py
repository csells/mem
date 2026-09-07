"""Hash omitted native cache files after the cohort; never edit retained state."""

import hashlib
import json
import os
from pathlib import Path


root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "manifest.json").read_text())
assert all(
    (root / "cases" / s["lifecycle"] / f"stage-{s['stage']}" / "result.json").is_file()
    for s in manifest["slots"]
), "Do not inventory an unfinished cohort"
omitted = []
for slot in manifest["slots"]:
    case = root / "cases" / slot["lifecycle"]
    state = json.loads((case / "state.json").read_text())
    native = Path(state["scratch"]) / f"stage-{slot['stage']}" / "native"
    for directory, names, files in os.walk(native, followlinks=False):
        path = Path(directory)
        relative_parts = path.relative_to(native).parts
        excluded = any(p in {"__pycache__", ".pytest_cache"} for p in relative_parts)
        excluded |= any(
            a == "plugins" and b == "cache"
            for a, b in zip(relative_parts, relative_parts[1:])
        )
        if excluded:
            for name in files:
                p = path / name
                if p.is_symlink():
                    row = {"symlink_target": os.readlink(p)}
                else:
                    data = p.read_bytes()
                    row = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                omitted.append({
                    "slot": slot["slot"],
                    "native_relative_path": str(p.relative_to(native)),
                    **row,
                })
report = {
    "purpose": "Post-run hashes for dependency/cache bytes omitted by native_snapshot; original scratch files preserved",
    "scheduled_sessions": len(manifest["slots"]),
    "omitted_files": omitted,
}
destination = root / "audits" / "omitted-native-cache-inventory.json"
with destination.open("x") as handle:
    json.dump(report, handle, indent=2)
    handle.write("\n")
print(json.dumps({"scheduled": len(manifest["slots"]), "omitted_files_hashed": len(omitted)}))
