from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .event_lifecycle import (
    INGEST_VERSION_V1,
    EventLifecycle,
    _assert_ingest_paths,
    _stage_ingest_bytes,
    event_identity,
    identify_events,
    is_valid_ingest_item,
)
from .paths import resolve_data_root
from .sources import normalize_sources


RETRIEVAL_REQUEST_VERSION = "skrya.retrieval-request.v1"
INGEST_VERSION = "skrya.ingest.v2"
RUNTIME_RETRIEVAL_TYPE = "runtime-retrieval"


@dataclass(slots=True)
class IngestWriteResult:
    latest_path: Path
    normalized_path: Path
    raw_path: Path | None = None


class IngestService:
    def __init__(self, root: Path | str, data_root: Path | str | None = None) -> None:
        self._root = Path(root)
        self._data_root = resolve_data_root(self._root, data_root).data_root

    def build_retrieval_request(
        self,
        topic_reference: str,
        *,
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, Any]:
        topic_id = self.resolve_topic_id(topic_reference)
        sources = self._runtime_retrieval_sources(topic_id)

        capabilities = self._unique(
            capability
            for source in sources
            for capability in source.get("capabilities", [])
            if isinstance(capability, str) and capability
        )
        queries = self._unique(
            query
            for source in sources
            for query in source.get("queries", [])
            if isinstance(query, str) and query
        )
        languages = self._unique(
            language
            for source in sources
            for language in source.get("languages", [])
            if isinstance(language, str) and language
        )
        max_items = max([int(source.get("max_items", 0) or 0) for source in sources] or [0])

        request: dict[str, Any] = {
            "interface_version": RETRIEVAL_REQUEST_VERSION,
            "topic_id": topic_id,
            "capabilities": capabilities,
            "queries": queries,
            "languages": languages,
            "max_items": max_items or 50,
        }
        if since or until:
            request["time_window"] = {"since": since, "until": until}
        return request

    def record_ingest_result(
        self,
        topic_reference: str,
        payload: dict[str, Any],
        *,
        raw_text: str | None = None,
    ) -> IngestWriteResult:
        topic_id = self.resolve_topic_id(topic_reference)
        lifecycle = EventLifecycle(self._data_root, topic_id)
        ingest_dir = self._data_root / "runs" / topic_id / "ingest"
        normalized_dir = ingest_dir / "normalized"
        raw_dir = ingest_dir / "raw"
        latest_path = ingest_dir / "latest-ingest.json"

        # Managed paths are checked before any mutation, including lock creation,
        # and re-checked inside the lock to close the check-then-write race where feasible.
        _assert_ingest_paths(self._data_root, topic_id, "normalized", "raw", "latest-ingest.json")
        self._require_migrated_current(latest_path)
        with lifecycle.state_lock():
            _assert_ingest_paths(self._data_root, topic_id, "normalized", "raw", "latest-ingest.json")
            self._require_migrated_current(latest_path)

            normalized = self._normalize_payload(topic_id, payload)
            envelope_producer = normalized.get("producer")
            envelope_retrieved_at = normalized.get("retrieved_at")
            for item in normalized["items"]:
                # Persist each item's actual recording provenance; items keep
                # their own, and nothing is invented for older records.
                if envelope_producer and not item.get("producer"):
                    item["producer"] = dict(envelope_producer)
                if envelope_retrieved_at and not item.get("retrieved_at"):
                    item["retrieved_at"] = envelope_retrieved_at
            normalized["items"] = identify_events(normalized["items"])

            state = lifecycle.load_state()
            source_generations: dict[str, int] = {}
            generations_by_event: dict[str, int] = {}
            groups: dict[str, list[dict[str, Any]]] = {}
            for item in normalized["items"]:
                groups.setdefault(item["source_id"], []).append(item)
            for source_id, group in groups.items():
                records = lifecycle.merge_source(state, source_id, group, origin="ingest")
                if records:
                    source_generations[source_id] = int(records[-1]["generation"])
                for record in records:
                    generations_by_event[record["event_id"]] = int(record["generation"])
            for item in normalized["items"]:
                generation = generations_by_event.get(item["event_id"])
                if generation is not None:
                    item["generation"] = generation
            normalized["source_generations"] = source_generations

            normalized_dir.mkdir(parents=True, exist_ok=True)

            producer = self._safe_filename(str(normalized["producer"].get("name", "provider")))
            if raw_text is not None:
                raw_dir.mkdir(parents=True, exist_ok=True)
            stamp = self._artifact_stamp(normalized.get("retrieved_at"))
            base = stamp
            normalized_path = normalized_dir / f"{base}.json"
            raw_path = raw_dir / f"{base}-{producer}.txt" if raw_text is not None else None
            digest8 = ""
            counter = 0
            while normalized_path.exists() or (raw_path is not None and raw_path.exists()):
                if not digest8:
                    digest8 = hashlib.sha256(
                        json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")
                    ).hexdigest()[:8]
                base = f"{stamp}-{digest8}" + (f"-{counter}" if counter else "")
                counter += 1
                normalized_path = normalized_dir / f"{base}.json"
                raw_path = raw_dir / f"{base}-{producer}.txt" if raw_text is not None else None

            previous_latest = latest_path.read_bytes() if latest_path.exists() else None
            staged_raw: Path | None = None
            published_paths: list[Path] = []
            try:
                if raw_path is not None:
                    staged_raw = _stage_ingest_bytes(raw_path, raw_text.encode("utf-8"))
                self._write_json(normalized_path, normalized, replace=False)
                published_paths.append(normalized_path)
                if raw_path is not None:
                    os.link(staged_raw, raw_path)
                    published_paths.append(raw_path)
                self._write_json(latest_path, normalized)
            except Exception:
                for published_path in reversed(published_paths):
                    published_path.unlink(missing_ok=True)
                raise
            finally:
                if staged_raw is not None:
                    staged_raw.unlink(missing_ok=True)

            if groups:
                try:
                    lifecycle.commit_state(state)
                except Exception:
                    # Roll the published batch back so digest/load_events consumers
                    # keep seeing the previous published set. Multi-file crash
                    # atomicity is not claimed here.
                    for published_path in reversed(published_paths):
                        published_path.unlink(missing_ok=True)
                    if previous_latest is None:
                        latest_path.unlink(missing_ok=True)
                    else:
                        staged_latest = _stage_ingest_bytes(latest_path, previous_latest)
                        try:
                            os.replace(staged_latest, latest_path)
                        finally:
                            staged_latest.unlink(missing_ok=True)
                    raise

        return IngestWriteResult(latest_path=latest_path, normalized_path=normalized_path, raw_path=raw_path)

    def load_events(self, topic_reference: str) -> list[dict[str, Any]]:
        topic_id = self.resolve_topic_id(topic_reference)
        lifecycle = EventLifecycle(self._data_root, topic_id)
        latest_path = self._data_root / "runs" / topic_id / "ingest" / "latest-ingest.json"
        _assert_ingest_paths(self._data_root, topic_id, "latest-ingest.json")
        if not latest_path.exists():
            return []
        lock_path = lifecycle.state_path.with_name("event-state.lock")
        try:
            fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644)
        except OSError as exc:
            if lock_path.is_symlink():
                raise ValueError(f"Refusing linked event state path: {lock_path}") from exc
            raise
        with os.fdopen(fd, "r", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            try:
                # Re-check under the shared lock: a first-ingest rollback may
                # remove latest between the pre-lock check and this point, and
                # no unlocked capture may survive to answer for it.
                if not latest_path.exists():
                    return []
                payload = json.loads(latest_path.read_text(encoding="utf-8"))
                state_sources = lifecycle.load_state().get("sources", {})
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        normalized = self._normalize_payload(topic_id, payload)
        current_items = [
            item
            for source in state_sources.values()
            if source.get("origin") == "ingest"
            for item in source.get("events", {}).values()
            if item.get("generation") == source.get("generation")
        ]
        current_items.extend(
            dict(item, producer=item.get("producer") or normalized.get("producer"))
            for item in normalized["items"]
            if item.get("source_id") not in state_sources
        )
        events: list[dict[str, Any]] = []
        positions: dict[str, int] = {}
        for item in current_items:
            key = str(item.get("id") or self._slugify(item["title"]))

            # Primary item attribution is combined with structured sources: the
            # exact article URL and producer/fetched evidence are never dropped,
            # and canonical normalization handles deduplication.
            source_record = {
                k: v
                for k, v in item.items()
                if k not in ("id", "title", "summary", "content", "sources", "generation")
            }
            structured = item.get("sources")
            if isinstance(structured, (list, tuple)):
                candidates = [source_record, *structured]
            elif structured:
                candidates = [source_record, structured]
            else:
                candidates = [source_record]
            item_sources = normalize_sources(candidates)

            summary = item.get("summary") or item.get("content") or item["title"]
            content = item.get("content") or summary
            event: dict[str, Any] = {
                "key": key,
                "title": item["title"],
                "summary": item.get("summary") or "",
                "content": item.get("content") or "",
                "headline_summary": summary,
                "list_summary": summary,
                "analysis_title": item["title"],
                "analysis_body": content,
                "sources": item_sources,
            }
            date_val = str(item.get("published_at") or item.get("fetched_at") or item.get("date") or "").strip()
            if date_val:
                event["date"] = date_val
            for field in ("event_id", "content_hash", "source_id", "generation"):
                if item.get(field) is not None:
                    event[field] = item[field]

            # Stable identity with latest-version-wins semantics, matching the
            # lifecycle last upsert instead of first-wins title/URL deduplication.
            identity = str(item.get("event_id") or "").strip() or event_identity(item)[0]
            position = positions.get(identity)
            if position is None:
                positions[identity] = len(events)
                events.append(event)
            else:
                events[position] = event
        return events

    def has_runtime_retrieval_sources(self, topic_reference: str) -> bool:
        topic_id = self.resolve_topic_id(topic_reference)
        return bool(self._runtime_retrieval_sources(topic_id))

    def resolve_topic_id(self, topic_reference: str) -> str:
        topics_root = self._data_root / "topics"
        normalized_reference = self._normalize_reference(topic_reference)
        if not topics_root.exists():
            raise FileNotFoundError("Topics directory not found")

        matches: list[str] = []
        for topic_dir in topics_root.iterdir():
            if not topic_dir.is_dir():
                continue
            metadata_path = topic_dir / "topic.json"
            metadata = {}
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

            candidates = [
                topic_dir.name,
                str(metadata.get("topic", "")),
                str(metadata.get("name", "")),
                str(metadata.get("description", "")),
            ]
            if any(self._normalize_reference(candidate) == normalized_reference for candidate in candidates):
                matches.append(topic_dir.name)

        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"Topic reference '{topic_reference}' is ambiguous: {', '.join(sorted(matches))}")

        raise FileNotFoundError(f"Topic '{topic_reference}' not found")

    def _runtime_retrieval_sources(self, topic_id: str) -> list[dict[str, Any]]:
        sources_path = self._data_root / "topics" / topic_id / "sources.json"
        payload = json.loads(sources_path.read_text(encoding="utf-8"))
        return [
            source
            for source in payload.get("sources", [])
            if source.get("enabled", True) and source.get("type") == RUNTIME_RETRIEVAL_TYPE
        ]

    def _require_migrated_current(self, latest_path: Path) -> None:
        "Refuse to overwrite an unmigrated current ingest state before any lifecycle mutation."
        if not latest_path.exists():
            return
        try:
            payload = json.loads(latest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(
                f"Unreadable current ingest state at {latest_path}; refusing to overwrite it. "
                "Repair or migrate it explicitly before recording new ingest."
            ) from exc
        version = payload.get("interface_version") if isinstance(payload, dict) else None
        if version == INGEST_VERSION_V1:
            raise ValueError(
                "skrya.ingest.v1 current state requires explicit migration. "
                "Run `skrya upgrade --migrate-ingest-v2` to migrate the current "
                "latest-ingest state, then record with skrya.ingest.v2."
            )
        if version != INGEST_VERSION:
            raise ValueError(
                f"Unsupported current ingest interface version at {latest_path}: {version}"
            )

    def _normalize_payload(self, topic_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("interface_version") == INGEST_VERSION_V1:
            raise ValueError(
                "skrya.ingest.v1 payloads are no longer accepted. "
                "Run `skrya upgrade --migrate-ingest-v2` to migrate the current "
                "latest-ingest state, then record with skrya.ingest.v2."
            )
        if payload.get("interface_version") != INGEST_VERSION:
            raise ValueError(f"Unsupported ingest interface version: {payload.get('interface_version')}")
        payload_topic = self.resolve_topic_id(str(payload.get("topic_id", "")))
        if payload_topic != topic_id:
            raise ValueError(f"Ingest topic '{payload_topic}' does not match requested topic '{topic_id}'")

        producer = dict(payload.get("producer") or {})
        producer["persistent"] = bool(producer.get("persistent", False))
        items = [
            dict(item)
            for item in payload.get("items", [])
            if is_valid_ingest_item(item)
        ]

        retrieved_at = payload.get("retrieved_at") or self._now_iso()
        if not isinstance(retrieved_at, str) or not retrieved_at.strip():
            raise ValueError("Invalid ingest retrieved_at: expected a non-empty ISO-8601 timestamp")
        try:
            datetime.fromisoformat(retrieved_at.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"Invalid ingest retrieved_at: {retrieved_at!r} is not an ISO-8601 timestamp; "
                "refusing to publish ingest state"
            ) from exc

        return {
            **payload,
            "interface_version": INGEST_VERSION,
            "topic_id": topic_id,
            "retrieved_at": retrieved_at,
            "producer": producer,
            "source_generations": dict(payload.get("source_generations") or {}),
            "items": items,
        }

    @staticmethod
    def _unique(values) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any], *, replace: bool = True) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        staged_path = _stage_ingest_bytes(path, content)
        try:
            if replace:
                os.replace(staged_path, path)
            else:
                os.link(staged_path, path)
        finally:
            staged_path.unlink(missing_ok=True)

    @staticmethod
    def _artifact_stamp(value: Any) -> str:
        if isinstance(value, str) and value.strip():
            return IngestService._safe_filename(value.strip())
        return IngestService._safe_filename(IngestService._now_iso())

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe_filename(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "artifact"

    @staticmethod
    def _normalize_reference(value: str) -> str:
        return re.sub(r"[\s_\-]+", "", value.strip().lower())

    @staticmethod
    def _slugify(value: str) -> str:
        chars = []
        for char in value.lower():
            if char.isalnum():
                chars.append(char)
            elif chars and chars[-1] != "-":
                chars.append("-")
        return "".join(chars).strip("-") or "event"
