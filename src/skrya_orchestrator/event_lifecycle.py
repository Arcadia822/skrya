"""Event identity, per-source generation lifecycle, and ingest migration/pruning."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterator
from urllib.parse import urlsplit

from .sources import primary_article_url


INGEST_VERSION_V1 = "skrya.ingest.v1"
INGEST_VERSION_V2 = "skrya.ingest.v2"
EVENT_STATE_SCHEMA = "skrya.event-state.v1"
EVENT_STATE_FILENAME = "event-state.json"
EVENT_STATE_LOCK_FILENAME = "event-state.lock"
SNAPSHOT_WINDOW_DEFAULT = 3
_CONTENT_FIELDS = (
    "content",
    "summary",
    "headline_summary",
    "list_summary",
    "analysis_title",
    "analysis_body",
)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _collapse(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalized_title(title: Any) -> str:
    return _collapse(title).lower()


def content_hash_of(item: dict[str, Any]) -> str:
    summary = _collapse(item.get("summary"))
    additional_summary = ""
    if "summary" not in item:
        headline_summary = _collapse(item.get("headline_summary"))
        list_summary = _collapse(item.get("list_summary"))
        summary = headline_summary or list_summary
        if headline_summary and list_summary and headline_summary != list_summary:
            additional_summary = list_summary
    content = item.get("content", item.get("analysis_body"))
    parts = [_collapse(item.get("title")), summary, _collapse(content)]
    if additional_summary:
        parts.append(additional_summary)
    return _sha256_hex("\x1f".join(parts))


def infer_source_id(item: dict[str, Any]) -> str:
    supplied = str(item.get("source_id") or "").strip()
    if supplied:
        return supplied
    url = _article_url(item)
    if url:
        hostname = (urlsplit(url).hostname or "").lower().strip(".")
        if hostname:
            return hostname.removeprefix("www.")
    name = str(item.get("source_name") or "").strip()
    if name:
        return _slugify(name)
    return "unknown-source"


def _article_url(item: dict[str, Any]) -> str:
    url = str(item.get("url") or "").strip()
    if url:
        return url
    return primary_article_url(item)


def event_identity(item: dict[str, Any]) -> tuple[str, str]:
    source_id = infer_source_id(item)
    url = _article_url(item)
    if url:
        event_id = _sha256_hex(f"{source_id}|{url}")
    else:
        event_id = _sha256_hex(f"{source_id}|title:{normalized_title(item.get('title'))}")
    return event_id, content_hash_of(item)


def identify_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    identified: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        record = dict(event)
        event_id, content_hash = event_identity(record)
        record["source_id"] = infer_source_id(record)
        record["event_id"] = event_id
        record["content_hash"] = content_hash
        identified.append(record)
    return identified


def _slugify(value: str) -> str:
    chars: list[str] = []
    for char in value.strip().lower():
        if char.isalnum():
            chars.append(char)
        elif chars and chars[-1] != "-":
            chars.append("-")
    return "".join(chars).strip("-") or "unknown-source"


class EventLifecycle:
    """Per-source generation lifecycle backed by runs/<topic>/event-state.json.

    The constructor and all read paths are side-effect free: nothing is created
    on disk until record_source persists. Preview paths never write.
    """

    def __init__(self, data_root: Path | str, topic_id: str) -> None:
        self._data_root = Path(data_root)
        self._topic_id = str(topic_id)

    @property
    def state_path(self) -> Path:
        return self._data_root / "runs" / self._topic_id / EVENT_STATE_FILENAME

    @property
    def topic_id(self) -> str:
        return self._topic_id

    def identify_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return identify_events(events)

    def record_source(
        self,
        source_id: str,
        events: list[dict[str, Any]],
        *,
        persist: bool = True,
    ) -> list[dict[str, Any]]:
        if not persist:
            return self.merge_source(self.load_state(), source_id, events)
        with self.state_lock():
            state = self.load_state()
            upserted = self.merge_source(state, source_id, events)
            self.commit_state(state)
            return upserted

    def load_state(self) -> dict[str, Any]:
        """Return the current state object; refuses a linked state file."""
        return self._load_state()

    def merge_source(
        self,
        state: dict[str, Any],
        source_id: str,
        events: list[dict[str, Any]],
        *,
        origin: str = "feed",
    ) -> list[dict[str, Any]]:
        """Merge events into a caller-held state object in memory; writes nothing."""
        source_id = str(source_id).strip() or "unknown-source"
        identified = identify_events(
            [dict(event, source_id=source_id) for event in events if isinstance(event, dict)]
        )
        sources = state.setdefault("sources", {})
        source_state = sources.setdefault(source_id, {"generation": 0, "events": {}})
        records: dict[str, dict[str, Any]] = source_state.setdefault("events", {})
        generation = int(source_state.get("generation", 0) or 0) + 1
        source_state["generation"] = generation
        source_state["origin"] = origin

        upserted: dict[str, dict[str, Any]] = {}
        for record in identified:
            event_id = record["event_id"]
            merged = dict(records.get(event_id) or {})
            # Content fields absent from the new generation must never be
            # inherited from the previous one: drop them so every surviving
            # content field is sourced from the current generation. They are
            # not backfilled here because identify_events' content_hash covers
            # content/summary, and backfilling would change hashes of records
            # whose canonical body fields stay absent.
            for field in _CONTENT_FIELDS:
                if field in merged and field not in record:
                    del merged[field]
            merged.update(record)
            merged["generation"] = generation
            records[event_id] = merged
            upserted[event_id] = merged
        return list(upserted.values())

    def commit_state(self, state: dict[str, Any]) -> None:
        """Persist a state object; the caller must hold state_lock()."""
        state["schema"] = EVENT_STATE_SCHEMA
        state["topic_id"] = self._topic_id
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_state(state)

    def current_events(self, source_id: str | None = None) -> list[dict[str, Any]]:
        state = self._load_state()
        result: list[dict[str, Any]] = []
        for sid, source_state in state.get("sources", {}).items():
            if source_id is not None and sid != source_id:
                continue
            generation = int(source_state.get("generation", 0) or 0)
            for record in source_state.get("events", {}).values():
                if int(record.get("generation", 0) or 0) == generation:
                    result.append(record)
        return result

    def filter_recent(
        self,
        events: list[dict[str, Any]],
        window: int = SNAPSHOT_WINDOW_DEFAULT,
    ) -> list[dict[str, Any]]:
        known = self._snapshot_identity_pairs(window)
        result: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("event_id") or "").strip()
            content_hash = str(event.get("content_hash") or "").strip()
            if not event_id or not content_hash:
                event_id, content_hash = event_identity(event)
            if (event_id, content_hash) in known:
                continue
            result.append(event)
        return result

    def _load_state(self) -> dict[str, Any]:
        path = self.state_path
        if path.is_symlink():
            raise ValueError(f"Refusing linked event state path: {path}")
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid event state at {path}: expected a JSON object")
        return payload

    @contextmanager
    def state_lock(self) -> Iterator[None]:
        """Per-topic exclusive lock; managed paths are checked before any mutation."""
        _assert_state_paths(self._data_root, self._topic_id)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_path.with_name(EVENT_STATE_LOCK_FILENAME)
        try:
            lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644)
        except OSError as exc:
            if lock_path.is_symlink():
                raise ValueError(f"Refusing linked event state path: {lock_path}") from exc
            raise
        with os.fdopen(lock_fd, "r+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _write_state(self, state: dict[str, Any]) -> None:
        path = self.state_path
        payload = json.dumps(state, ensure_ascii=False, indent=2)
        staged_path = _stage_ingest_bytes(path, payload.encode("utf-8"))
        try:
            os.replace(staged_path, path)
        finally:
            staged_path.unlink(missing_ok=True)

    def _snapshot_identity_pairs(self, window: int) -> set[tuple[str, str]]:
        window = max(int(window), 0)
        if not window:
            return set()
        run_dir = self._data_root / "runs" / self._topic_id
        snapshots: list[tuple[datetime, int, Path]] = []
        try:
            for path in run_dir.glob("digest-*.events.json"):
                if not path.is_file() or path.is_symlink():
                    continue
                match = re.fullmatch(
                    r"digest-(\d{8}T\d{6}(?:[+-]\d{4}|Z))(?:-(\d+))?\.events\.json",
                    path.name,
                )
                if match is None:
                    continue
                try:
                    timestamp = datetime.strptime(match[1], "%Y%m%dT%H%M%S%z")
                except ValueError:
                    continue
                snapshots.append((timestamp, int(match[2] or 0), path))
        except OSError:
            return set()
        pairs: set[tuple[str, str]] = set()
        snapshot_count = 0
        for _, _, path in sorted(snapshots, reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            items = payload.get("items") if isinstance(payload, dict) else None
            if isinstance(payload, dict) and payload.get("collection_mode") == "sample":
                continue
            if not isinstance(items, (dict, list, tuple)):
                continue
            values = items.values() if isinstance(items, dict) else items
            for item in values:
                if not isinstance(item, dict):
                    continue
                event_id = str(item.get("event_id") or "").strip()
                content_hash = str(item.get("content_hash") or "").strip()
                if not event_id or not content_hash:
                    event_id, content_hash = event_identity(item)
                if event_id and content_hash:
                    pairs.add((event_id, content_hash))
            snapshot_count += 1
            if snapshot_count == window:
                break
        return pairs


def is_valid_ingest_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    for field in ("title", "url", "source_name", "fetched_at", "content", "summary"):
        value = item.get(field)
        if value is not None and not isinstance(value, str):
            return False
    title = str(item.get("title") or "").strip()
    source = str(item.get("url") or item.get("source_name") or "").strip()
    fetched_at = str(item.get("fetched_at") or "").strip()
    body = str(item.get("content") or item.get("summary") or "").strip()
    if not title or not source or not fetched_at or not body:
        return False
    blocked_patterns = (
        "ignore previous instructions",
        "system prompt",
        "developer message",
        "reveal the system",
    )
    return not any(pattern in body.lower() for pattern in blocked_patterns)


def _validate_ingest_payload(payload: Any, topic_id: str, version: str) -> None:
    if not isinstance(payload, dict) or payload.get("interface_version") != version:
        raise ValueError(f"Invalid ingest payload: expected {version}")
    if payload.get("topic_id") != topic_id:
        raise ValueError(f"Ingest topic does not match {topic_id}")
    if not isinstance(payload.get("producer"), dict):
        raise ValueError("Invalid ingest producer: expected a JSON object")
    retrieved_at = payload.get("retrieved_at")
    if not isinstance(retrieved_at, str) or not retrieved_at.strip():
        raise ValueError("Invalid ingest retrieved_at: expected an ISO-8601 timestamp")
    datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    items = payload.get("items")
    if not isinstance(items, list) or any(not is_valid_ingest_item(item) for item in items):
        raise ValueError("Invalid ingest items: expected complete ingest item objects")
    if version == INGEST_VERSION_V2:
        generations = payload.get("source_generations")
        if not isinstance(generations, dict) or any(
            not isinstance(sid, str) or type(generation) is not int or generation < 0
            for sid, generation in generations.items()
        ):
            raise ValueError("Invalid ingest source_generations")
        for item in items:
            event_id, content_hash = event_identity(item)
            if (
                item.get("source_id") != infer_source_id(item)
                or item.get("event_id") != event_id
                or item.get("content_hash") != content_hash
            ):
                raise ValueError("Invalid ingest item identity")


def _assert_topic_id(topic_id: str) -> None:
    if not topic_id or topic_id in (".", "..") or Path(topic_id).name != topic_id or "\\" in topic_id:
        raise ValueError("Invalid topic identifier")


def _assert_state_paths(data_root: Path, topic_id: str) -> None:
    _assert_topic_id(topic_id)
    runs_root = data_root / "runs"
    topic_dir = runs_root / topic_id
    for path in (runs_root, topic_dir, topic_dir / EVENT_STATE_FILENAME, topic_dir / EVENT_STATE_LOCK_FILENAME):
        if path.is_symlink():
            raise ValueError(f"Refusing linked event state path: {path}")


def _assert_ingest_paths(data_root: Path, topic_id: str, *names: str) -> None:
    _assert_topic_id(topic_id)
    runs_root = data_root / "runs"
    topic_dir = runs_root / topic_id
    ingest_dir = topic_dir / "ingest"
    for path in (runs_root, topic_dir, ingest_dir, *(ingest_dir / name for name in names)):
        if path.is_symlink():
            raise ValueError(f"Refusing linked ingest path: {path}")


def _stage_ingest_bytes(path: Path, content: bytes) -> Path:
    with NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
        staged_path = Path(handle.name)
        try:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        except Exception:
            staged_path.unlink(missing_ok=True)
            raise
    return staged_path


def migrate_ingest_v1(data_root: Path | str, topic_id: str | None = None) -> dict[str, Any]:
    "Convert only validated current ingest state, preserving its original backup and archives."
    data_root = Path(data_root)
    runs_root = data_root / "runs"
    report: dict[str, Any] = {
        "data_root": str(data_root),
        "migrated": [],
        "already_current": [],
        "failed": [],
    }
    topic_ids: list[str] = []
    if topic_id is not None:
        topic_ids = [str(topic_id)]
    else:
        try:
            if runs_root.is_symlink():
                raise ValueError(f"Refusing linked ingest path: {runs_root}")
            if runs_root.is_dir():
                for topic_dir in sorted(runs_root.iterdir()):
                    if topic_dir.is_symlink():
                        report["failed"].append({"topic_id": topic_dir.name, "error": "Linked topic directory"})
                    elif topic_dir.is_dir():
                        topic_ids.append(topic_dir.name)
        except (OSError, ValueError) as exc:
            report["failed"].append({"topic_id": "", "error": str(exc)})
            return report

    for tid in topic_ids:
        staged_paths: list[Path] = []
        lifecycle = EventLifecycle(data_root, tid)
        try:
            _assert_ingest_paths(data_root, tid, "latest-ingest.json", "latest-ingest.v1-backup.json")
            latest_path = runs_root / tid / "ingest" / "latest-ingest.json"
            if not latest_path.exists():
                continue
            with lifecycle.state_lock():
                # From the original read through os.replace the migration runs
                # under the per-topic state lock, so no concurrent migration or
                # ingest commit can interleave; re-reading latest inside the
                # lock skips topics another writer already migrated.
                _assert_ingest_paths(data_root, tid, "latest-ingest.json", "latest-ingest.v1-backup.json")
                latest_path = runs_root / tid / "ingest" / "latest-ingest.json"
                if not latest_path.exists():
                    continue
                original_bytes = latest_path.read_bytes()
                payload = json.loads(original_bytes)
                version = payload.get("interface_version") if isinstance(payload, dict) else None
                if version == INGEST_VERSION_V2:
                    _validate_ingest_payload(payload, tid, INGEST_VERSION_V2)
                    report["already_current"].append({"topic_id": tid})
                    continue
                _validate_ingest_payload(payload, tid, INGEST_VERSION_V1)
                converted = _convert_v1_payload(payload)
                _validate_ingest_payload(converted, tid, INGEST_VERSION_V2)
                converted_bytes = json.dumps(converted, ensure_ascii=False, indent=2).encode("utf-8")
                backup_path = latest_path.with_name("latest-ingest.v1-backup.json")
                if backup_path.exists() and backup_path.read_bytes() != original_bytes:
                    raise ValueError(f"Existing ingest backup differs from current state: {backup_path}")

                staged_current = _stage_ingest_bytes(latest_path, converted_bytes)
                staged_paths.append(staged_current)
                if not backup_path.exists():
                    staged_backup = _stage_ingest_bytes(backup_path, original_bytes)
                    staged_paths.append(staged_backup)
                    try:
                        os.link(staged_backup, backup_path)
                    except FileExistsError:
                        if backup_path.read_bytes() != original_bytes:
                            raise ValueError(f"Existing ingest backup differs from current state: {backup_path}")
                if backup_path.read_bytes() != original_bytes:
                    raise ValueError(f"Existing ingest backup differs from current state: {backup_path}")
                os.replace(staged_current, latest_path)
                report["migrated"].append(
                    {"topic_id": tid, "backup_path": str(backup_path), "item_count": len(converted["items"])}
                )

                # Initialize event state in the same lock so the first
                # incremental ingest after migration keeps every migrated
                # source instead of only the sources in the new batch. An
                # already-current topic never reaches this, and an existing
                # state with committed sources is never overwritten.
                state = lifecycle.load_state()
                if not state.get("sources"):
                    initialized: dict[str, Any] = {"sources": {}}
                    by_source: dict[str, list[dict[str, Any]]] = {}
                    for item in converted["items"]:
                        by_source.setdefault(item["source_id"], []).append(item)
                    for source_id, group in by_source.items():
                        lifecycle.merge_source(initialized, source_id, group, origin="ingest")
                    for source_id, source_generation in converted["source_generations"].items():
                        source_state = initialized["sources"].get(source_id)
                        if source_state is not None:
                            source_state["generation"] = int(source_generation)
                            for record in source_state["events"].values():
                                record["generation"] = int(source_generation)
                    lifecycle.commit_state(initialized)
        except (OSError, ValueError, TypeError) as exc:
            report["failed"].append({"topic_id": tid, "error": str(exc)})
        finally:
            for staged_path in staged_paths:
                try:
                    staged_path.unlink(missing_ok=True)
                except OSError as exc:
                    report["failed"].append({"topic_id": tid, "error": str(exc)})
    return report


def _convert_v1_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or any(not is_valid_ingest_item(item) for item in raw_items):
        raise ValueError("Invalid ingest items: expected complete ingest item objects")
    items = identify_events(raw_items)
    converted = dict(payload)
    converted["interface_version"] = INGEST_VERSION_V2
    converted["source_generations"] = {item["source_id"]: 1 for item in items}
    converted["items"] = items
    return converted


def _retrieved_at_utc(payload: dict[str, Any]) -> datetime:
    retrieved = datetime.fromisoformat(str(payload["retrieved_at"]).strip().replace("Z", "+00:00"))
    if retrieved.tzinfo is None:
        return retrieved.replace(tzinfo=timezone.utc)
    return retrieved.astimezone(timezone.utc)


def _writer_rank(name: str, stamp: str) -> tuple[int, str, int]:
    """Rank a validated writer filename inside one retrieved_at collision group.

    The writer publishes the bare stamp first, then ``-<hash8>`` on collision,
    then ``-<counter>`` afterwards, so the rank follows real write order.
    """
    suffix = name[len(stamp) : -len(".json")]
    match = re.fullmatch(r"(?:-([0-9a-f]{8})(?:-([1-9]\d*))?)?", suffix)
    if match is None or not match[1]:
        return (0, "", 0)
    return (1, match[1], int(match[2] or 0))


def prune_ingests(
    data_root: Path | str,
    topic_id: str,
    keep: int = 10,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    "Select owned ingest batches only; deletion remains explicit and dry-run by default."
    data_root = Path(data_root)
    topic_id = str(topic_id)
    ingest_dir = data_root / "runs" / topic_id / "ingest"
    normalized_dir = ingest_dir / "normalized"
    raw_dir = ingest_dir / "raw"
    report: dict[str, Any] = {
        "topic_id": topic_id,
        "keep": int(keep),
        "apply": bool(apply),
        "total_batches": 0,
        "protected_batches": [],
        "selected": [],
        "deleted": [],
        "failed": [],
    }
    try:
        _assert_ingest_paths(
            data_root, topic_id, "normalized", "raw", "latest-ingest.json", "latest-ingest.v1-backup.json"
        )
    except ValueError as exc:
        report["failed"].append({"path": "ingest", "error": str(exc)})
        return report
    if not normalized_dir.is_dir():
        return report

    batch_files: list[Path] = []
    batch_payloads: dict[str, dict[str, Any]] = {}
    batch_contents: dict[str, bytes] = {}
    batch_order: dict[str, tuple[datetime, int, tuple[int, str, int]]] = {}
    protected_other: list[str] = []
    raw_by_stem: dict[str, list[Path]] = {}
    for entry in sorted(normalized_dir.iterdir()):
        if entry.suffix == ".json" and not entry.name.startswith("."):
            raw_by_stem[entry.stem] = []
        if entry.is_symlink() or not entry.is_file() or entry.suffix != ".json" or entry.name.startswith("."):
            protected_other.append(entry.name)
            continue
        try:
            content = entry.read_bytes()
            payload = json.loads(content)
            version = payload.get("interface_version") if isinstance(payload, dict) else None
            if version not in (INGEST_VERSION_V1, INGEST_VERSION_V2):
                raise ValueError("Not an ingest batch")
            _validate_ingest_payload(payload, topic_id, version)
            stamp = re.sub(r"[^A-Za-z0-9._-]+", "-", payload["retrieved_at"].strip()).strip("-")
            if re.fullmatch(re.escape(stamp) + r"(?:-[0-9a-f]{8}(?:-[1-9]\d*)?)?\.json", entry.name) is None:
                raise ValueError("Not an ingest writer filename")
            order_key = (_retrieved_at_utc(payload), entry.stat().st_mtime_ns, _writer_rank(entry.name, stamp))
        except (OSError, ValueError, TypeError):
            protected_other.append(entry.name)
            continue
        batch_files.append(entry)
        batch_payloads[entry.stem] = payload
        batch_contents[entry.name] = content
        batch_order[entry.name] = order_key
    batch_files.sort(key=lambda path: batch_order[path.name])
    report["total_batches"] = len(batch_files)
    report["protected_batches"] = list(protected_other)
    keep_count = max(int(keep), 0)
    protected = {path.name for path in batch_files[-keep_count:]} if keep_count else set()

    latest_path = ingest_dir / "latest-ingest.json"
    backup_path = ingest_dir / "latest-ingest.v1-backup.json"
    try:
        if latest_path.exists():
            latest_content = latest_path.read_bytes()
            latest_payload = json.loads(latest_content)
            version = latest_payload.get("interface_version") if isinstance(latest_payload, dict) else None
            if version not in (INGEST_VERSION_V1, INGEST_VERSION_V2):
                raise ValueError("Invalid latest ingest version")
            _validate_ingest_payload(latest_payload, topic_id, version)
            protected.update(
                path.name for path in batch_files
                if batch_contents[path.name] == latest_content or batch_payloads[path.stem] == latest_payload
            )
            if backup_path.exists():
                backup_content = backup_path.read_bytes()
                backup_payload = json.loads(backup_content)
                _validate_ingest_payload(backup_payload, topic_id, INGEST_VERSION_V1)
                if _convert_v1_payload(backup_payload) == latest_payload:
                    protected.update(
                        path.name for path in batch_files
                        if batch_contents[path.name] == backup_content or batch_payloads[path.stem] == backup_payload
                    )
    except (OSError, ValueError, TypeError) as exc:
        report["protected_batches"] += [path.name for path in batch_files]
        report["failed"].append({"path": "latest-ingest.json", "error": str(exc)})
        return report

    if raw_dir.is_dir():
        stems = sorted(raw_by_stem, key=len, reverse=True)
        for entry in sorted(raw_dir.iterdir()):
            if entry.is_symlink() or not entry.is_file() or entry.suffix != ".txt":
                continue
            owner = next(
                (stem for stem in stems if entry.name.startswith(f"{stem}-")),
                None,
            )
            if owner is None or owner not in batch_payloads:
                continue
            producer = str(batch_payloads[owner]["producer"].get("name", "provider"))
            producer = re.sub(r"[^A-Za-z0-9._-]+", "-", producer).strip("-") or "artifact"
            if re.fullmatch(re.escape(f"{owner}-{producer}") + r"(?:-[1-9]\d*)?\.txt", entry.name):
                raw_by_stem[owner].append(entry)

    report["protected_batches"] += [path.name for path in batch_files if path.name in protected]
    for path in batch_files:
        if path.name in protected:
            continue
        raw_files = raw_by_stem[path.stem]
        report["selected"].append({"normalized": path.name, "raw": [raw.name for raw in raw_files]})
        if not apply:
            continue
        try:
            path.unlink()
        except OSError as exc:
            report["failed"].append({"path": f"normalized/{path.name}", "error": str(exc)})
            continue
        report["deleted"].append(f"normalized/{path.name}")
        for raw_file in raw_files:
            try:
                raw_file.unlink()
            except OSError as exc:
                report["failed"].append({"path": f"raw/{raw_file.name}", "error": str(exc)})
            else:
                report["deleted"].append(f"raw/{raw_file.name}")
    return report
