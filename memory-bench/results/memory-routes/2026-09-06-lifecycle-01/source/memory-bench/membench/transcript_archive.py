"""Bead-linked transcript archival (mem-75t.4, time-sensitive piece).

The Claude Code transcript corpus is a ~6-week ROLLING window (the earliest
surviving session is 2026-04-30; old session jsonl is pruned), so every ingest
run copies the bead-linked raw transcripts to durable storage before they age
out. Raw jsonl is required for future bundle replay (gold diffs) — extracted
projections are not enough.

Idempotent: a manifest (jsonl, append-only) records every archived file by
source path, size, and mtime; an unchanged source is skipped on re-run, a
changed one (still-live session that grew) is re-archived in place. Copies are
gzip-compressed and written atomically (tmp + rename).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_NAME = "manifest.jsonl"


@dataclass(frozen=True)
class ArchiveReport:
    archived: int
    refreshed: int
    skipped_unchanged: int
    missing: int

    def to_json(self) -> dict[str, int]:
        return {
            "archived": self.archived,
            "refreshed": self.refreshed,
            "skipped_unchanged": self.skipped_unchanged,
            "missing": self.missing,
        }


def archive_name(source: Path) -> str:
    """Stable, collision-free archive filename for a transcript path: a short
    path digest plus the original name (uuid stems collide across project dirs
    only via subagent sidecars, the digest disambiguates everything)."""
    digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:12]
    return f"{digest}__{source.name}.gz"


def load_manifest(dest_dir: Path) -> dict[str, dict[str, Any]]:
    """Latest manifest entry per source path (the manifest is append-only;
    later lines supersede earlier ones)."""
    manifest_path = dest_dir / MANIFEST_NAME
    entries: dict[str, dict[str, Any]] = {}
    if not manifest_path.is_file():
        return entries
    with manifest_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, Mapping) and isinstance(entry.get("source"), str):
                entries[entry["source"]] = dict(entry)
    return entries


def _gzip_copy(source: Path, dest: Path) -> str:
    """Atomic gzip copy; returns the sha256 of the UNCOMPRESSED content."""
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    sha = hashlib.sha256()
    with source.open("rb") as src, gzip.open(tmp, "wb") as out:
        while True:
            chunk = src.read(1 << 20)
            if not chunk:
                break
            sha.update(chunk)
            out.write(chunk)
    tmp.replace(dest)
    return sha.hexdigest()


def archive_transcripts(sources: Iterable[str | Path], dest_dir: str | Path) -> ArchiveReport:
    """Archive every existing source transcript into `dest_dir`, idempotently."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(dest)
    manifest_path = dest / MANIFEST_NAME

    archived = refreshed = skipped = missing = 0
    with manifest_path.open("a", encoding="utf-8") as manifest_out:
        for raw in sorted({str(s) for s in sources}):
            source = Path(raw)
            try:
                stat = source.stat()
            except OSError:
                missing += 1
                continue
            previous = manifest.get(raw)
            if (
                previous is not None
                and previous.get("size") == stat.st_size
                and previous.get("mtime_ns") == stat.st_mtime_ns
                and (dest / str(previous.get("name"))).is_file()
            ):
                skipped += 1
                continue
            name = archive_name(source)
            try:
                sha = _gzip_copy(source, dest / name)
            except OSError:
                missing += 1
                continue
            entry = {
                "source": raw,
                "name": name,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": sha,
                "archived_at": datetime.now(UTC).isoformat(),
            }
            manifest_out.write(json.dumps(entry) + "\n")
            if previous is None:
                archived += 1
            else:
                refreshed += 1
    return ArchiveReport(
        archived=archived, refreshed=refreshed, skipped_unchanged=skipped, missing=missing
    )


def restore_transcript(dest_dir: str | Path, source_path: str, out_path: str | Path) -> None:
    """Decompress one archived transcript back to `out_path` (for replay)."""
    dest = Path(dest_dir)
    entry = load_manifest(dest).get(source_path)
    if entry is None:
        raise FileNotFoundError(f"{source_path} not in archive manifest under {dest}")
    archived = dest / str(entry["name"])
    with gzip.open(archived, "rb") as src, Path(out_path).open("wb") as out:
        shutil.copyfileobj(src, out)


# Where `restore_pruned` lands decompressed transcripts inside the archive dir.
RESTORED_SUBDIR = "restored"


@dataclass(frozen=True)
class RestoredTranscript:
    """One pruned transcript brought back from the archive: the durable restored
    jsonl plus the ORIGINAL live path (the manifest key) -- callers need the
    original for path-based semantics (e.g. subagent-sidecar detection)."""

    path: Path
    source: str


def restore_pruned(dest_dir: str | Path) -> list[RestoredTranscript]:
    """Restore every archived transcript whose original source no longer exists.

    The ~6-week rolling retention prunes live session jsonl; the archive is the
    durable copy. This decompresses each pruned transcript to
    ``<dest_dir>/restored/<digest>/<original name>`` (the manifest name's digest
    prefix keeps same-named transcripts from different project dirs apart; the
    restored filename stem stays the session uuid). Idempotent: a restored file
    whose size matches the manifest's recorded source size is kept as-is.
    Returns the restored entries sorted by original source path."""
    dest = Path(dest_dir)
    restored: list[RestoredTranscript] = []
    for source, entry in sorted(load_manifest(dest).items()):
        if Path(source).exists():
            continue
        name = str(entry["name"])
        digest, _, original = name.partition("__")
        out = dest / RESTORED_SUBDIR / digest / original.removesuffix(".gz")
        if not (out.is_file() and out.stat().st_size == entry.get("size")):
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(out.suffix + ".tmp")
            with gzip.open(dest / name, "rb") as src, tmp.open("wb") as handle:
                shutil.copyfileobj(src, handle)
            tmp.replace(out)
        restored.append(RestoredTranscript(path=out, source=source))
    return restored
