"""Digest reference snapshot building, persistence, and resolution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

SNAPSHOT_SCHEMA = "skrya.digest-index.v1"


def snapshot_path(artifact_path: Path | str) -> Path:
    """Return the immutable sidecar path for a digest artifact.

    Resolves symlinks (e.g. latest-digest.md -> digest-<timestamp>.md),
    then replaces the suffix with '.events.json'.
    """
    path = Path(artifact_path).resolve()
    if path.name == "latest-digest-events.json":
        latest_md = path.parent / "latest-digest.md"
        if latest_md.exists() or latest_md.is_symlink():
            return latest_md.resolve().with_suffix(".events.json")
    if path.name.endswith(".events.json") and path.name != "latest-digest-events.json":
        return path
    return path.with_suffix(".events.json")


def _derive_stable_event_key(sources: list[Any], date: str, title: str) -> str:
    first_source = ""
    if sources:
        s = sources[0]
        first_source = s.get("url", "") if isinstance(s, dict) else str(s)
    clean_title = re.sub(r"[\s_\-]+", "", str(title or "").strip().lower())
    seed = f"{first_source.strip()}|{str(date or '').strip()}|{clean_title}"
    return f"event-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def build_snapshot(
    topic_id: str,
    artifact_path: Path | str,
    items: list[dict],
    threads: list[dict],
    *,
    artifact_sha256: str | None = None,
) -> dict:
    """Build a deterministic reference snapshot dictionary conforming to skrya.digest-index.v1.

    Items are mapped as N-01, N-02, ... maintaining complete event dicts.
    Threads are mapped as T-01, T-02, ... maintaining full raw thread dicts with stable id.
    Missing item keys derive a stable hash from source/date/title, never an arbitrary event-{number}.
    Duplicate references are rejected.
    """
    resolved_path = Path(artifact_path).resolve()
    raw_archive_path = str((resolved_path.parent / "threads" / "latest-threads.json").resolve())

    sha256_val = artifact_sha256
    if sha256_val is None:
        if resolved_path.exists() and resolved_path.is_file():
            sha256_val = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
        else:
            sha256_val = ""

    items_map: dict[str, dict] = {}
    for idx, item in enumerate(items, start=1):
        num = item.get("number", idx)
        ref_key = f"N-{int(num):02d}"
        if ref_key in items_map:
            raise ValueError(f"Duplicate item reference in snapshot: {ref_key}")

        item_copy = dict(item)
        item_copy["number"] = int(num)
        if not item_copy.get("key"):
            item_copy["key"] = _derive_stable_event_key(
                item_copy.get("sources", []),
                str(item_copy.get("date", "")),
                str(item_copy.get("title", "")),
            )
        items_map[ref_key] = item_copy

    threads_map: dict[str, dict] = {}
    for idx, thread in enumerate(threads, start=1):
        ref_key = f"T-{idx:02d}"
        if ref_key in threads_map:
            raise ValueError(f"Duplicate thread reference in snapshot: {ref_key}")

        thread_copy = dict(thread)
        thread_copy["raw_archive_path"] = raw_archive_path
        threads_map[ref_key] = thread_copy

    return {
        "schema": SNAPSHOT_SCHEMA,
        "topic_id": str(topic_id),
        "artifact_path": str(resolved_path),
        "artifact_sha256": sha256_val,
        "raw_archive_path": raw_archive_path,
        "items": items_map,
        "threads": threads_map,
    }


def validate_snapshot_schema(data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError("Invalid snapshot payload: expected JSON object")
    if data.get("schema") != SNAPSHOT_SCHEMA:
        raise ValueError(f"Invalid snapshot schema: expected {SNAPSHOT_SCHEMA!r}, got {data.get('schema')!r}")
    if not str(data.get("topic_id") or "").strip():
        raise ValueError("Invalid snapshot: missing or empty 'topic_id'")
    if not str(data.get("artifact_path") or "").strip():
        raise ValueError("Invalid snapshot: missing or empty 'artifact_path'")
    if not isinstance(data.get("items"), dict):
        raise ValueError("Invalid snapshot: 'items' must be a dictionary")
    if not isinstance(data.get("threads"), dict):
        raise ValueError("Invalid snapshot: 'threads' must be a dictionary")


def load_snapshot(artifact_path: Path | str) -> dict:
    """Load and strictly validate the immutable reference snapshot corresponding to an artifact or snapshot path.

    Validates that:
    1. The snapshot schema and required fields are strictly valid.
    2. The snapshot's artifact_path matches the requested resolved artifact (or its sidecar sibling).
    3. The artifact exists and its actual SHA256 matches the snapshot's artifact_sha256.
    """
    target_path = snapshot_path(artifact_path)
    if not target_path.exists():
        raise FileNotFoundError(f"Snapshot file not found: {target_path}")
    data = json.loads(target_path.read_text(encoding="utf-8"))
    validate_snapshot_schema(data)

    snap_artifact = Path(data["artifact_path"]).resolve()
    requested_resolved = Path(artifact_path).resolve()
    expected_sidecar = snapshot_path(snap_artifact)

    if (
        requested_resolved != snap_artifact
        and requested_resolved != expected_sidecar
        and target_path != expected_sidecar
    ):
        raise ValueError(
            f"Snapshot artifact_path '{data['artifact_path']}' does not match requested artifact '{requested_resolved}'"
        )

    expected_sha = str(data.get("artifact_sha256") or "").strip()
    if not expected_sha:
        raise ValueError("Invalid snapshot: missing or empty 'artifact_sha256'")

    if not snap_artifact.exists() or not snap_artifact.is_file():
        raise FileNotFoundError(f"Artifact file not found: {snap_artifact}")

    actual_sha = hashlib.sha256(snap_artifact.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        raise ValueError(
            f"Artifact sha256 mismatch for '{snap_artifact}': expected {expected_sha}, got {actual_sha}"
        )

    return data


def resolve_reference(snapshot: dict, reference: str) -> dict:
    """Resolve N-xx or T-xx reference token against a strictly validated snapshot dictionary.

    Returns dict with keys: reference, kind, entity, topic_id, artifact_path, raw_archive_path.
    Bare numeric token normalizes to N-xx.
    Unknown or invalid reference raises ValueError without guessing.
    """
    validate_snapshot_schema(snapshot)

    ref_str = str(reference or "").strip()
    ref_clean = re.sub(r"^(?:dig|track|write)\s*:\s*", "", ref_str, flags=re.IGNORECASE).strip()

    if not ref_clean:
        raise ValueError(f"Empty or missing reference: {reference!r}")

    normalized: str
    kind: str
    if re.fullmatch(r"\d+", ref_clean):
        normalized = f"N-{int(ref_clean):02d}"
        kind = "news"
    else:
        m_news = re.fullmatch(r"(?i)N-?(\d+)", ref_clean)
        m_thread = re.fullmatch(r"(?i)T-?(\d+)", ref_clean)
        if m_news:
            normalized = f"N-{int(m_news.group(1)):02d}"
            kind = "news"
        elif m_thread:
            normalized = f"T-{int(m_thread.group(1)):02d}"
            kind = "thread"
        else:
            raise ValueError(f"Invalid reference format '{reference}': expected N-xx or T-xx")

    if kind == "news":
        items = snapshot["items"]
        if normalized not in items:
            raise ValueError(f"News reference '{normalized}' not found in snapshot")
        entity = items[normalized]
    elif kind == "thread":
        threads = snapshot["threads"]
        if normalized not in threads:
            raise ValueError(f"Thread reference '{normalized}' not found in snapshot")
        entity = threads[normalized]
    else:
        raise ValueError(f"Unknown reference kind for '{reference}'")

    res = {
        "reference": normalized,
        "kind": kind,
        "entity": entity,
        "topic_id": snapshot["topic_id"],
        "artifact_path": snapshot["artifact_path"],
    }
    raw_archive_path = snapshot.get("raw_archive_path")
    if not raw_archive_path and snapshot.get("artifact_path"):
        raw_archive_path = str((Path(snapshot["artifact_path"]).resolve().parent / "threads" / "latest-threads.json").resolve())
    if raw_archive_path:
        res["raw_archive_path"] = str(raw_archive_path)
    return res
