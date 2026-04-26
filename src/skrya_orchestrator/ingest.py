from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import resolve_data_root


RETRIEVAL_REQUEST_VERSION = "skrya.retrieval-request.v1"
INGEST_VERSION = "skrya.ingest.v1"
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
        normalized = self._normalize_payload(topic_id, payload)

        ingest_dir = self._data_root / "runs" / topic_id / "ingest"
        normalized_dir = ingest_dir / "normalized"
        raw_dir = ingest_dir / "raw"
        normalized_dir.mkdir(parents=True, exist_ok=True)

        stamp = self._artifact_stamp(normalized.get("retrieved_at"))
        normalized_path = normalized_dir / f"{stamp}.json"
        latest_path = ingest_dir / "latest-ingest.json"
        self._write_json(normalized_path, normalized)
        self._write_json(latest_path, normalized)

        raw_path = None
        if raw_text is not None:
            raw_dir.mkdir(parents=True, exist_ok=True)
            producer = self._safe_filename(str(normalized.get("producer", {}).get("name", "provider")))
            raw_path = raw_dir / f"{stamp}-{producer}.txt"
            raw_path.write_text(raw_text, encoding="utf-8")

        return IngestWriteResult(latest_path=latest_path, normalized_path=normalized_path, raw_path=raw_path)

    def load_events(self, topic_reference: str) -> list[dict[str, Any]]:
        topic_id = self.resolve_topic_id(topic_reference)
        latest_path = self._data_root / "runs" / topic_id / "ingest" / "latest-ingest.json"
        if not latest_path.exists():
            return []

        payload = json.loads(latest_path.read_text(encoding="utf-8"))
        normalized = self._normalize_payload(topic_id, payload)
        events: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in normalized["items"]:
            key = str(item.get("id") or self._slugify(item["title"]))
            source = item.get("url") or item.get("source_name")
            dedupe_key = f"{item['title'].strip().lower()}|{source}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            summary = item.get("summary") or item.get("content") or item["title"]
            content = item.get("content") or summary
            events.append(
                {
                    "key": key,
                    "title": item["title"],
                    "headline_summary": summary,
                    "list_summary": summary,
                    "analysis_title": item["title"],
                    "analysis_body": content,
                    "sources": [source],
                }
            )
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

    def _normalize_payload(self, topic_id: str, payload: dict[str, Any]) -> dict[str, Any]:
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
            if isinstance(item, dict) and self._is_valid_item(item)
        ]

        return {
            "interface_version": INGEST_VERSION,
            "topic_id": topic_id,
            "retrieved_at": payload.get("retrieved_at") or self._now_iso(),
            "producer": producer,
            "items": items,
        }

    @classmethod
    def _is_valid_item(cls, item: dict[str, Any]) -> bool:
        title = str(item.get("title", "")).strip()
        source = str(item.get("url") or item.get("source_name") or "").strip()
        fetched_at = str(item.get("fetched_at", "")).strip()
        body = str(item.get("content") or item.get("summary") or "").strip()
        if not title or not source or not fetched_at or not body:
            return False
        lowered = body.lower()
        blocked_patterns = (
            "ignore previous instructions",
            "system prompt",
            "developer message",
            "reveal the system",
        )
        return not any(pattern in lowered for pattern in blocked_patterns)

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
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

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
