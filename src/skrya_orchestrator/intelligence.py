from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .event_lifecycle import EventLifecycle, _stage_ingest_bytes, event_identity, infer_source_id
from .http_cache import HttpCache
from .ingest import IngestService
from .source_collector import CollectionResult, SourceCollector, with_source_fallbacks
from .sources import normalize_sources, primary_article_url, render_sources
from .translation_cache import TranslationCache
from .paths import resolve_data_root
from .references import build_snapshot, snapshot_path
from .thread_milestones import recorded_date, select_milestones

MAX_VISIBLE_EVENTS = 15


def _write_artifact(path: Path, text: str) -> None:
    """Stage exclusively then replace, so a planted symlink can never truncate a frozen target."""
    staged = _stage_ingest_bytes(path, text.encode("utf-8"))
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


@dataclass(slots=True)
class DigestResult:
    markdown: str
    digest_path: Path
    artifact_path: Path
    preview: bool = False
    retrieval_request: dict | None = None


@dataclass(slots=True)
class DeepAnalysisResult:
    markdown: str
    artifact_path: Path


@dataclass(slots=True)
class ThreadResult:
    markdown: str
    artifact_path: Path


@dataclass(slots=True)
class ThreadRefreshResult:
    artifact_path: Path
    payload: dict


class IntelligenceService:
    def __init__(
        self, root: Path | str, fetcher=None, translator=None,
        data_root: Path | str | None = None, *, translation_provider: str | None = None,
    ) -> None:
        self._root = Path(root)
        self._data_root = resolve_data_root(self._root, data_root).data_root
        self._fetcher = fetcher
        self._translator = translator if translator is not None else self._default_translate
        self._translation_provider = (
            translation_provider if translator is not None else "google-translate"
        )
        self._http_cache = HttpCache(self._data_root)
        self._translation_cache = TranslationCache(self._data_root)
        self._translation_write = True

    def generate_digest(
        self, topic_id: str, prefer_live: bool = True, preview: bool = False,
        force_refresh: bool = False,
    ) -> DigestResult:
        previous_write = self._translation_write
        self._translation_write = not preview
        try:
            return self._generate_digest(topic_id, prefer_live, preview, force_refresh)
        finally:
            self._translation_write = previous_write

    def _generate_digest(
        self, topic_id: str, prefer_live: bool, preview: bool, force_refresh: bool,
    ) -> DigestResult:
        topic_id = self.resolve_topic_id(topic_id)
        collection, real_collection = self._load_collection(
            topic_id, prefer_live=prefer_live, write=not preview, force_refresh=force_refresh,
        )
        retrieval_request = with_source_fallbacks(
            IngestService(self._root, data_root=self._data_root).build_retrieval_request(topic_id),
            fallbacks=collection.fallbacks,
        ) if collection.fallbacks else None
        all_events = self._rank_events(topic_id, collection.events)
        events = EventLifecycle(self._data_root, topic_id).filter_recent(all_events) if real_collection else all_events
        if real_collection:
            events = events[:MAX_VISIBLE_EVENTS]
        numbered_events = list(enumerate(events, start=1))
        execution_time = datetime.now(ZoneInfo("Asia/Shanghai"))
        language = self._topic_output_language(topic_id)
        indexed_items = [self._digest_event_index_item(index, event) for index, event in numbered_events]

        visible_numbers = {id(event): number for number, event in numbered_events}
        archive_items = [
            self._digest_event_index_item(visible_numbers.get(id(event)), event)
            for event in all_events
        ]
        materialized_threads, active_threads = self._materialize_topic_threads(topic_id, archive_items)
        for thread in materialized_threads:
            thread["_matched_items"] = [
                item for item in thread.get("_matched_items", []) if isinstance(item.get("number"), int)
            ]
        thread_updates, updated_thread_count = self._build_digest_thread_updates(
            topic_id,
            numbered_events,
            language,
            active_threads=active_threads,
        )
        lines: list[str] = [self._build_digest_title(topic_id, execution_time, language), ""]
        scan_label = self._scan_time_range_label(topic_id, language)
        if scan_label:
            prefix = "Scan window: " if language == "en" else "扫描时间范围："
            lines.append(f"{prefix}{scan_label}")
            lines.append("")
        if collection.health_notice:
            lines.extend([collection.health_notice, ""])
        if thread_updates:
            lines.append("## Event Timeline Updates" if language == "en" else "## 事件线时间线更新")
            lines.append("")
            for update_lines in thread_updates:
                lines.extend(update_lines)
                lines.append("")
        if events:
            lines.append("## Today's Briefs" if language == "en" else "## 今日简讯")
            lines.append("")

            for number, event in numbered_events:
                lines.append(self._build_digest_entry(number, event, language))
                lines.append("")
        else:
            lines.append(
                "No sufficiently fresh real items were found. I will not pretend sample data is today's briefing."
                if language == "en"
                else "暂时没有抓到足够新的真实内容，先不拿样例数据冒充日报。你可以稍后再试，或者明确告诉我用样例做演示。"
            )
            lines.append("")

        lines.extend(self._build_digest_followups(language))

        markdown = "\n".join(lines).strip() + "\n"

        if preview:
            return DigestResult(
                markdown=markdown,
                digest_path=Path(""),
                artifact_path=Path(""),
                preview=True,
                retrieval_request=retrieval_request,
            )

        artifact_dir = self._data_root / "runs" / topic_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        base_name = f"digest-{execution_time:%Y%m%dT%H%M%S%z}"
        digest_path = artifact_dir / f"{base_name}.md"
        counter = 1
        while digest_path.exists() or snapshot_path(digest_path).exists():
            digest_path = artifact_dir / f"{base_name}-{counter}.md"
            counter += 1

        _write_artifact(digest_path, markdown)

        indexed_items = [self._digest_event_index_item(index, event) for index, event in numbered_events]

        event_index_path = artifact_dir / "latest-digest-events.json"
        _write_artifact(
            event_index_path,
            json.dumps({"topic": topic_id, "items": indexed_items}, ensure_ascii=False, indent=2),
        )

        clean_threads = [
            {k: v for k, v in t.items() if not k.startswith("_")}
            for t in materialized_threads
        ]
        if clean_threads:
            thread_artifact_path = self._data_root / "runs" / topic_id / "threads" / "latest-threads.json"
            thread_artifact_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "interface_version": "skrya.thread.v1",
                "topic_id": topic_id,
                "threads": clean_threads,
            }
            _write_artifact(thread_artifact_path, json.dumps(payload, ensure_ascii=False, indent=2))

        snapshot_active_threads = [
            {k: v for k, v in t.items() if not k.startswith("_")}
            for t in active_threads
        ]
        sidecar = build_snapshot(topic_id, digest_path, indexed_items, snapshot_active_threads)
        sidecar["collection_mode"] = "real" if real_collection else "sample"
        sidecar_path = snapshot_path(digest_path)
        _write_artifact(sidecar_path, json.dumps(sidecar, ensure_ascii=False, indent=2))

        self._point_latest_artifact(artifact_dir / "latest-digest.md", digest_path)

        return DigestResult(
            markdown=markdown,
            digest_path=digest_path,
            artifact_path=event_index_path,
            retrieval_request=retrieval_request,
        )

    @staticmethod
    def _point_latest_artifact(latest_path: Path, target_path: Path) -> None:
        if latest_path.exists() or latest_path.is_symlink():
            latest_path.unlink()
        try:
            latest_path.symlink_to(os.path.relpath(target_path, latest_path.parent))
        except OSError:
            _write_artifact(latest_path, target_path.read_text(encoding="utf-8"))

    def _build_digest_title(self, topic_id: str, execution_time: datetime, language: str) -> str:
        topic_name = self._topic_display_name(topic_id)
        if language == "en":
            return f"# {execution_time:%Y-%m-%d} | {topic_name} | Daily Briefing"
        label = "每日简报"
        return f"# {execution_time:%Y-%m-%d}｜{topic_name}｜{label}"

    def _topic_display_name(self, topic_id: str) -> str:
        topic_path = self._data_root / "topics" / topic_id / "topic.json"
        if not topic_path.exists():
            return topic_id
        metadata = json.loads(topic_path.read_text(encoding="utf-8"))
        return str(metadata.get("name") or metadata.get("description") or topic_id)

    def _topic_output_language(self, topic_id: str) -> str:
        topic_path = self._data_root / "topics" / topic_id / "topic.json"
        if not topic_path.exists():
            return "zh-CN"
        metadata = json.loads(topic_path.read_text(encoding="utf-8"))
        language = str(metadata.get("language", "")).strip().lower()
        if language in {"en", "en-us", "en-gb"}:
            return "en"
        if language in {"zh", "zh-cn", "zh-hans", "zh_cn"}:
            return "zh-CN"
        return "zh-CN"

    @staticmethod
    def _build_digest_followups(language: str) -> list[str]:
        if language == "en":
            return [
                "---",
                "",
                "## Available actions",
                "",
                "- Reply `dig: N-01` — Deep analysis and expert background for this news item",
                "- Reply `track: N-02` — Start a continuing event thread",
                "- Reply `dig: T-01` — Review the thread's complete history",
                "- Reply `write: T-01` — Turn this series of events into an article",
                "- Natural-language feedback — Ask for more China-related analysis or fewer routine partisan disputes",
            ]
        return [
            "---",
            "",
            "## 可继续操作",
            "",
            "- 回复 `dig: N-01` — 展开指定条目的深度分析与专家级背景研判",
            "- 回复 `track: N-02` — 为指定事件建立持续追踪线",
            "- 回复 `dig: T-01` — 查看该事件线的全量历史脉络",
            "- 回复 `write: T-01` — 把这一系列事件写成一篇文章",
            "- 自然语言反馈 — 例如“增加涉华舆情分析”或“减少例行口水争端”",
        ]

    def _scan_time_range_label(self, topic_id: str, language: str = "zh-CN") -> str:
        ingest_path = self._data_root / "runs" / topic_id / "ingest" / "latest-ingest.json"
        if ingest_path.exists():
            payload = json.loads(ingest_path.read_text(encoding="utf-8"))
            fetched_times = [
                str(item.get("fetched_at", "")).strip()
                for item in payload.get("items", [])
                if isinstance(item, dict) and str(item.get("fetched_at", "")).strip()
            ]
            if fetched_times:
                if language == "en":
                    return f"{min(fetched_times)} to {max(fetched_times)}"
                return f"{min(fetched_times)} 至 {max(fetched_times)}"
            retrieved_at = str(payload.get("retrieved_at", "")).strip()
            if retrieved_at:
                if language == "en":
                    return f"latest retrieval as of {retrieved_at}"
                return f"截至 {retrieved_at} 的最近一轮检索"
        return "last 24 hours (default)" if language == "en" else "最近 24 小时（默认）"

    def generate_deep_analysis(self, topic_id: str, event_number: int) -> DeepAnalysisResult:
        topic_id = self.resolve_topic_id(topic_id)
        event = self._resolve_event(topic_id, event_number)
        language = self._topic_output_language(topic_id)

        markdown = self._build_deep_analysis_markdown(event, language=language)

        artifact_dir = self._data_root / "runs" / topic_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        analysis_path = artifact_dir / f"deep-analysis-{event_number}.md"
        _write_artifact(analysis_path, markdown)

        return DeepAnalysisResult(markdown=markdown, artifact_path=analysis_path)

    def get_event_sources(self, topic_id: str, event_number: int) -> list[dict]:
        topic_id = self.resolve_topic_id(topic_id)
        event = self._resolve_event(topic_id, event_number)
        return normalize_sources(event.get("sources", []))

    def generate_thread_timeline(self, topic_id: str, thread_reference: str) -> ThreadResult:
        topic_id = self.resolve_topic_id(topic_id)
        thread, artifact_path = self._resolve_thread(topic_id, thread_reference)
        return ThreadResult(
            markdown=self._build_thread_markdown(thread),
            artifact_path=artifact_path,
        )

    def refresh_threads(self, topic_id: str) -> ThreadRefreshResult:
        topic_id = self.resolve_topic_id(topic_id)
        self._ensure_topic(topic_id)
        seed_payload = self._load_thread_seed_payload(topic_id)
        existing_payload = self._load_thread_payload(topic_id)
        definitions = self._thread_definitions(
            seed_payload.get("threads", []),
            existing_payload.get("threads", []),
        )
        if not definitions:
            raise FileNotFoundError(
                f"Thread seeds not found for topic '{topic_id}'. "
                "Create topics/<topic-id>/thread-seeds.json first."
            )

        items = self._load_digest_event_items(topic_id)
        artifact_path, payload = self._write_thread_artifact(topic_id, definitions, items)
        return ThreadRefreshResult(artifact_path=artifact_path, payload=payload)

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

    def _resolve_event(self, topic_id: str, event_number: int) -> dict:
        event_index_path = self._data_root / "runs" / topic_id / "latest-digest-events.json"
        if not event_index_path.exists():
            raise FileNotFoundError(f"Digest artifact not found for topic '{topic_id}'")

        index = json.loads(event_index_path.read_text(encoding="utf-8"))
        for item in index["items"]:
            if item["number"] == event_number:
                return item

        raise ValueError(f"Event number {event_number} not found for topic '{topic_id}'")

    def _resolve_thread(self, topic_id: str, thread_reference: str) -> tuple[dict, Path]:
        artifact_path = self._thread_artifact_path(topic_id)
        if not artifact_path.exists():
            raise FileNotFoundError(f"Thread artifact not found for topic '{topic_id}'")

        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        normalized_reference = self._normalize_reference(thread_reference)
        matches: list[dict] = []
        for thread in payload.get("threads", []):
            candidates = [
                str(thread.get("id", "")),
                str(thread.get("name", "")),
                *(str(alias) for alias in thread.get("aliases", [])),
            ]
            if any(self._normalize_reference(candidate) == normalized_reference for candidate in candidates):
                matches.append(thread)

        if len(matches) == 1:
            return matches[0], artifact_path
        if len(matches) > 1:
            names = ", ".join(sorted(str(thread.get("name", "")) for thread in matches))
            raise ValueError(f"Thread reference '{thread_reference}' is ambiguous: {names}")

        raise ValueError(f"Thread '{thread_reference}' not found for topic '{topic_id}'")

    def _load_digest_event_items(self, topic_id: str) -> list[dict]:
        event_index_path = self._data_root / "runs" / topic_id / "latest-digest-events.json"
        if not event_index_path.exists():
            raise FileNotFoundError(f"Digest artifact not found for topic '{topic_id}'")
        payload = json.loads(event_index_path.read_text(encoding="utf-8"))
        return [dict(item) for item in payload.get("items", []) if isinstance(item, dict)]

    def _load_thread_seed_payload(self, topic_id: str) -> dict:
        seed_path = self._thread_seed_path(topic_id)
        if not seed_path.exists():
            return {}
        return self._normalize_thread_payload(json.loads(seed_path.read_text(encoding="utf-8")))

    def _load_thread_payload(self, topic_id: str) -> dict:
        artifact_path = self._thread_artifact_path(topic_id)
        if not artifact_path.exists():
            return {}
        return self._normalize_thread_payload(json.loads(artifact_path.read_text(encoding="utf-8")))

    def _thread_seed_path(self, topic_id: str) -> Path:
        seed_path = self._data_root / "topics" / topic_id / "thread-seeds.json"
        if seed_path.exists():
            return seed_path
        return self._data_root / "topics" / topic_id / "event-thread-seeds.json"

    def _thread_artifact_path(self, topic_id: str) -> Path:
        artifact_path = self._data_root / "runs" / topic_id / "threads" / "latest-threads.json"
        if artifact_path.exists():
            return artifact_path
        return self._data_root / "runs" / topic_id / "event-threads" / "latest-event-threads.json"

    @staticmethod
    def _normalize_thread_payload(payload: dict) -> dict:
        if "threads" not in payload and "event_threads" in payload:
            payload = dict(payload)
            payload["threads"] = payload.get("event_threads", [])
        return payload

    def _materialize_topic_threads(
        self, topic_id: str, items: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        seed_payload = self._load_thread_seed_payload(topic_id)
        existing_payload = self._load_thread_payload(topic_id)
        definitions = self._thread_definitions(
            seed_payload.get("threads", []),
            existing_payload.get("threads", []),
        )
        if not definitions:
            return [], []

        materialized_threads: list[dict] = []
        for defn in definitions:
            matched_items = self._matched_thread_items(defn, items)
            thread = self._materialize_thread(defn, matched_items)
            thread["_matched_items"] = matched_items
            materialized_threads.append(thread)

        active_threads = [
            thread
            for thread in materialized_threads
            if str(thread.get("status", "")).strip().lower() == "active"
        ]
        return materialized_threads, active_threads

    def _persist_threads_from_digest_items(self, topic_id: str, items: list[dict]) -> list[dict]:
        materialized_threads, _ = self._materialize_topic_threads(topic_id, items)
        clean_threads = [{k: v for k, v in t.items() if not k.startswith("_")} for t in materialized_threads]
        if clean_threads:
            artifact_threads_path = self._data_root / "runs" / topic_id / "threads" / "latest-threads.json"
            artifact_threads_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "interface_version": "skrya.thread.v1",
                "topic_id": topic_id,
                "threads": clean_threads,
            }
            _write_artifact(artifact_threads_path, json.dumps(payload, ensure_ascii=False, indent=2))
        return materialized_threads
    def _write_thread_artifact(self, topic_id: str, definitions: list[dict], items: list[dict]) -> tuple[Path, dict]:
        threads = [self._materialize_thread(definition, items) for definition in definitions]
        payload = {
            "interface_version": "skrya.thread.v1",
            "topic_id": topic_id,
            "threads": threads,
        }
        artifact_path = self._data_root / "runs" / topic_id / "threads" / "latest-threads.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        _write_artifact(artifact_path, json.dumps(payload, ensure_ascii=False, indent=2))
        return artifact_path, payload

    def _thread_definitions(self, seed_threads: list[dict], existing_threads: list[dict]) -> list[dict]:
        definitions: dict[str, dict] = {}
        ordered_keys: list[str] = []

        for thread in existing_threads:
            if not isinstance(thread, dict):
                continue
            key = str(thread.get("id") or self._slugify(str(thread.get("name", "")))).strip()
            if not key:
                continue
            definitions[key] = {
                **thread,
                "id": key,
                "name": str(thread.get("name", "")).strip(),
                "status": str(thread.get("status", "")).strip(),
                "summary": str(thread.get("summary", "")).strip(),
                "callback_hint": str(thread.get("callback_hint", "")).strip(),
                "aliases": [str(alias) for alias in thread.get("aliases", []) if str(alias).strip()],
                "watchpoints": [str(point) for point in thread.get("watchpoints", []) if str(point).strip()],
                "timeline": [dict(entry) for entry in thread.get("timeline", []) if isinstance(entry, dict)],
                "_match_terms": self._thread_match_terms(thread),
            }
            ordered_keys.append(key)

        for seed in seed_threads:
            if not isinstance(seed, dict):
                continue
            key = str(seed.get("id") or self._slugify(str(seed.get("name", "")))).strip()
            if not key:
                continue
            base = definitions.get(key, {})
            merged = {
                **base,
                **seed,
                "id": key,
                "name": str(seed.get("name") or base.get("name", "")).strip(),
                "status": str(seed.get("status") or base.get("status", "")).strip(),
                "summary": str(seed.get("summary") or base.get("summary", "")).strip(),
                "callback_hint": str(seed.get("callback_hint") or base.get("callback_hint", "")).strip(),
                "aliases": [str(alias) for alias in seed.get("aliases", []) if str(alias).strip()]
                or list(base.get("aliases", [])),
                "watchpoints": [str(point) for point in seed.get("watchpoints", []) if str(point).strip()]
                or list(base.get("watchpoints", [])),
                "timeline": [dict(entry) for entry in base.get("timeline", []) if isinstance(entry, dict)],
                "_match_terms": self._thread_match_terms(seed, base),
            }
            definitions[key] = merged
            if key not in ordered_keys:
                ordered_keys.append(key)

        return [definitions[key] for key in ordered_keys]

    def _thread_match_terms(self, *threads: dict) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for thread in threads:
            if not isinstance(thread, dict):
                continue
            candidates = [
                str(thread.get("id", "")),
                str(thread.get("name", "")),
                *(str(alias) for alias in thread.get("aliases", [])),
                *(str(term) for term in thread.get("match_terms", [])),
            ]
            for candidate in candidates:
                normalized = self._normalize_reference(candidate)
                if len(normalized) < 2 or normalized in seen:
                    continue
                seen.add(normalized)
                terms.append(candidate.strip())
        return terms

    def _materialize_thread(self, definition: dict, items: list[dict]) -> dict:
        thread = {
            **definition,
            "id": definition["id"],
            "name": definition.get("name", ""),
            "status": definition.get("status", ""),
            "summary": definition.get("summary", ""),
            "callback_hint": definition.get("callback_hint", ""),
            "aliases": list(definition.get("aliases", [])),
            "watchpoints": list(definition.get("watchpoints", [])),
        }
        thread = {k: v for k, v in thread.items() if not k.startswith("_")}
        timeline = [dict(entry) for entry in definition.get("timeline", []) if isinstance(entry, dict)]
        entries_by_signature = {self._thread_entry_signature(entry): entry for entry in timeline}
        new_entries: list[dict] = []

        for item in self._matched_thread_items(definition, items):
            entry = self._thread_entry_from_digest_item(item, has_existing=bool(timeline or new_entries))
            signature = self._thread_entry_signature(entry)
            if signature in entries_by_signature:
                entries_by_signature[signature].update({
                    key: value for key, value in entry.items() if key.startswith("milestone_")
                })
                entries_by_signature[signature]["sources"] = normalize_sources(
                    entry["sources"] + normalize_sources(entries_by_signature[signature].get("sources", []))
                )
                continue
            entries_by_signature[signature] = entry
            new_entries.append(entry)

        thread["timeline"] = timeline + new_entries
        if not thread["status"]:
            thread["status"] = "active" if thread["timeline"] else "watching"
        return thread
    def _matched_thread_items(self, definition: dict, items: list[dict]) -> list[dict]:
        match_terms = [self._normalize_reference(term) for term in definition.get("_match_terms", []) if term]
        if not match_terms:
            return []

        matches: list[dict] = []
        for item in items:
            text = self._normalize_reference(
                " ".join(
                    [
                        str(item.get("title", "")),
                        str(item.get("analysis_title", "")),
                        str(item.get("analysis_body", "")),
                    ]
                )
            )
            if any(term in text for term in match_terms):
                matches.append(item)

        matches.sort(
            key=lambda item: (
                str(item.get("date", "")).strip(),
                int(item.get("number", 0) or 0),
            )
        )
        return matches

    def _thread_entry_from_digest_item(self, item: dict, *, has_existing: bool) -> dict:
        raw_date = str(item.get("date", "")).strip()
        date = recorded_date(raw_date)
        number = item.get("number")
        related_numbers = [int(number)] if isinstance(number, int) else []
        entry = {
            **item,
            "date": date,
            "phase": "update" if has_existing else "seed",
            "headline": str(item.get("analysis_title") or item.get("title") or "事件推进").strip(),
            "summary": str(item.get("analysis_body") or item.get("analysis_title") or item.get("title") or "").strip(),
            "related_digest_numbers": related_numbers,
            "sources": normalize_sources(item.get("sources", [])),
        }
        for key in ("milestone_reason", "milestone_title", "milestone_date", "milestone_date_basis"):
            if item.get(key):
                entry[key] = item[key]
        return entry

    def _build_digest_thread_updates(
        self,
        topic_id: str,
        numbered_events: list[tuple[int, dict]],
        language: str = "zh-CN",
        active_threads: list[dict] | None = None,
    ) -> tuple[list[list[str]], int]:
        if active_threads is None:
            items = [self._digest_event_index_item(number, event) for number, event in numbered_events]
            _, active_threads = self._materialize_topic_threads(topic_id, items)

        if not active_threads:
            return [], 0

        updates: list[list[str]] = []
        updated_thread_count = 0
        for number, thread in enumerate(active_threads, start=1):
            matched_items = thread.get("_matched_items")
            if matched_items is None:
                items = [self._digest_event_index_item(num, ev) for num, ev in numbered_events]
                matched_items = self._matched_thread_items(thread, items)
            if matched_items:
                updated_thread_count += 1
            updates.append(self._build_digest_thread_update(thread, matched_items, language, number))
        return updates, updated_thread_count

    def _build_digest_thread_update(
        self, definition: dict, matched_items: list[dict], language: str = "zh-CN", number: int = 1
    ) -> list[str]:
        name = str(definition.get("name") or definition["id"])
        lines = [
            f"### T-{number:02d} {name}",
            "",
            "**Latest developments**:" if language == "en" else "**最新进展**：",
        ]
        for item in matched_items:
            title = str(item.get("title") or item.get("analysis_title") or "")
            first_url = primary_article_url(item)
            link = f"[{title}]({first_url})" if first_url else title
            raw_date = str(item.get("date", "")).strip()
            date = recorded_date(raw_date) or raw_date
            item_num = item.get("number", 1)
            date_prefix = f"**{date}** · " if date else ""
            lines.extend([
                f"- {date_prefix}{link} · N-{item_num:02d}",
                str(item.get("analysis_body") or item.get("analysis_title") or item.get("title") or "").strip(),
            ])
            comment = str(item.get("analysis_title", "")).strip()
            if comment and comment != title:
                label = "Comment" if language == "en" else "点评"
                lines.append(f"{label}：{comment}")
            lines.append("")
        if not matched_items:
            latest_state = self._latest_thread_state(definition, language)
            watchpoints = "；".join(
                str(item).strip() for item in definition.get("watchpoints", []) if str(item).strip()
            )
            callback_hint = str(definition.get("callback_hint", "")).strip()
            watch_label = "Watch next" if language == "en" else "下一步观察"
            sep = ": " if language == "en" else "："
            if watchpoints:
                suffix = "." if language == "en" else "。"
                next_watch = f"{watchpoints}{suffix}"
            else:
                fallback = callback_hint or (
                    "Continue checking the configured thread scope."
                    if language == "en"
                    else "继续按事件线既定范围复核。"
                )
                next_watch = fallback

            if language == "en":
                lines.extend([
                    "No verified update in this scan.",
                    f"Latest known state: {latest_state}",
                    f"{watch_label}{sep}{next_watch}",
                    "",
                ])
            else:
                lines.extend([
                    "本轮暂无可核验新增。",
                    f"最新状态：{latest_state}",
                    f"{watch_label}{sep}{next_watch}",
                    "",
                ])
        lines.extend(["**Historical timeline**:" if language == "en" else "**历史时间线**：", ""])
        history = select_milestones(self._materialize_thread(definition, matched_items)["timeline"])
        for entry in history:
            title = str(entry.get("headline", "")).strip()
            first_url = primary_article_url(entry)
            link = f"[{title}]({first_url})" if first_url else title
            lines.append(f"- {link} ｜ {entry.get('date', '')}")
        if not history:
            lines.append(
                "No verified milestones selected yet; the full reporting archive is retained."
                if language == "en"
                else "尚无已核定日期的重要节点，全量报道档案仍保留。"
            )
        return lines

    def _latest_thread_state(self, definition: dict, language: str = "zh-CN") -> str:
        timeline = [entry for entry in definition.get("timeline", []) if isinstance(entry, dict)]
        if timeline:
            dated_entries = [
                (str(entry.get("date", "")).strip(), index, entry)
                for index, entry in enumerate(timeline)
                if str(entry.get("date", "")).strip()
            ]
            latest = max(dated_entries, key=lambda item: (item[0], item[1]))[2] if dated_entries else timeline[-1]
            date = str(latest.get("date", "")).strip()
            headline = self._build_brief(str(latest.get("headline", "")), language=language)
            summary = self._build_brief(str(latest.get("summary", "")), language=language)
            state = " — ".join(part for part in [headline, summary] if part)
            if date and state:
                return f"{date}: {state}" if language == "en" else f"{date}：{state}"
            return state or date

        summary = self._build_brief(str(definition.get("summary", "")), language=language)
        if summary:
            prefix = "tracking baseline" if language == "en" else "当前追踪基线"
            return f"{prefix}: {summary}" if language == "en" else f"{prefix}：{summary}"
        return "the configured tracking baseline" if language == "en" else "已配置的追踪基线"

    def _digest_event_index_item(self, number: int | None, event: dict) -> dict:
        item = {
            **event,
            "number": number,
            "key": event.get("key", f"event-{number}"),
            "title": event.get("title", ""),
            "analysis_title": event.get("analysis_title", event.get("title", "")),
            "analysis_body": event.get("analysis_body", ""),
            "sources": normalize_sources(event.get("sources", [])),
            "date": event.get("date", ""),
        }
        for key in ("milestone_reason", "milestone_title", "milestone_date", "milestone_date_basis"):
            if event.get(key):
                item[key] = event[key]
        return item

    def _thread_entry_signature(self, entry: dict) -> tuple[str, str, tuple[str, ...], str]:
        return (
            str(entry.get("date", "")).strip(),
            self._normalize_reference(str(entry.get("headline", ""))),
            tuple(sorted({
                str(source.get("url") or self._normalize_reference(source.get("name", "")))
                for source in normalize_sources(entry.get("sources", []))
            })),
            " ".join(str(entry.get("summary") or entry.get("analysis_body") or "").split()),
        )

    def _ensure_topic(self, topic_id: str) -> Path:
        topic_dir = self._data_root / "topics" / topic_id
        if not topic_dir.exists():
            raise FileNotFoundError(f"Topic '{topic_id}' not found")
        return topic_dir

    def pending_source_fallbacks(self, topic_id: str) -> list[dict]:
        topic_id = self.resolve_topic_id(topic_id)
        return SourceCollector(self._ensure_topic(topic_id), write=False).fallback_records()

    def _load_collection(
        self, topic_id: str, *, prefer_live: bool, write: bool, force_refresh: bool,
    ) -> tuple[CollectionResult, bool]:
        topic_dir = self._ensure_topic(topic_id)
        sample_path = topic_dir / "sample-events.json"
        if not prefer_live and sample_path.exists():
            return CollectionResult(events=json.loads(sample_path.read_text(encoding="utf-8"))), False

        ingest_service = IngestService(self._root, data_root=self._data_root)
        sources_path = topic_dir / "sources.json"
        payload = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {}
        has_feeds = any(
            isinstance(source, dict) and source.get("enabled", True)
            and str(source.get("type", "")).lower() in {"rss", "rsshub"}
            for source in payload.get("sources", [])
        )
        ingest_events = ingest_service.load_events(topic_id) if prefer_live else []
        has_live = has_feeds or bool(ingest_events) or ingest_service.has_runtime_retrieval_sources(topic_id)
        if not has_live and sample_path.exists():
            return CollectionResult(events=json.loads(sample_path.read_text(encoding="utf-8"))), False

        collection = SourceCollector(
            topic_dir, self._http_cache, self._fetcher, write=write, force_refresh=force_refresh,
        ).collect() if has_feeds else CollectionResult()
        collection.events = self._merge_current_source_events(topic_id, collection.events, ingest_events)
        return collection, True

    def _merge_current_source_events(
        self, topic_id: str, live_events: list[dict], ingest_events: list[dict]
    ) -> list[dict]:
        fresh_sources = {infer_source_id(event) for event in live_events}
        current_ingest = [
            event for event in ingest_events
            if infer_source_id(event) not in fresh_sources
        ]
        by_identity: dict[str, dict] = {}
        for event in live_events + current_ingest:
            event_id = str(event.get("event_id") or "").strip() or event_identity(event)[0]
            by_identity[event_id] = event
        return list(by_identity.values())


    def _rank_events(self, topic_id: str, events: list[dict]) -> list[dict]:
        if not events:
            return []

        topic_dir = self._ensure_topic(topic_id)
        brief_payload = json.loads((topic_dir / "brief.json").read_text(encoding="utf-8"))
        request_text = " ".join(str(request.get("content", "")) for request in brief_payload.get("requests", []))
        request_terms = self._extract_request_terms(request_text)
        total = len(events)

        scored = [
            (self._score_event(event, request_terms) + ((total - index) * 0.01), index, event)
            for index, event in enumerate(events)
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [event for _, _, event in scored]

    @classmethod
    def _score_event(cls, event: dict, request_terms: set[str]) -> float:
        text = cls._event_text(event)
        score = 0.0

        for term in request_terms:
            if term and term in text:
                score += 5.0

        score += min(len(event.get("sources", [])), 3) * 1.0

        for keyword in cls._strong_event_keywords():
            if keyword in text:
                score += 1.5

        for pattern in cls._low_value_patterns():
            if pattern in text:
                score -= 4.0

        return score

    @classmethod
    def _extract_request_terms(cls, request_text: str) -> set[str]:
        text = request_text.lower()
        terms = {
            token
            for token in re.findall(r"[a-z0-9][a-z0-9\-]{2,}|[\u4e00-\u9fff]{2,}", text)
            if token not in cls._request_stop_terms()
        }

        bridges = {
            "合约": ["contract", "termination", "renewal"],
            "终止": ["termination", "terminate"],
            "法律": ["legal", "court", "prison", "sentence", "offender"],
            "判刑": ["prison", "sentence", "sentences"],
            "公司": ["company", "agency"],
            "回应": ["update", "statement", "respond"],
            "争议": ["controversy", "debate", "slammed", "dispute"],
            "练习生": ["trainee", "rookie"],
            "预告": ["teaser"],
            "回归": ["comeback"],
            "选角": ["casting"],
            "收视": ["rating", "ratings"],
            "深伪": ["deepfake"],
        }
        for source, additions in bridges.items():
            if source in text:
                terms.update(additions)

        return terms

    @staticmethod
    def _request_stop_terms() -> set[str]:
        return {
            "优先",
            "这类",
            "事件",
            "继续",
            "发酵",
            "最近",
            "起来",
            "已经",
            "开始",
            "内容",
            "the",
            "and",
            "for",
            "with",
        }

    @staticmethod
    def _strong_event_keywords() -> tuple[str, ...]:
        return (
            "contract",
            "termination",
            "terminate",
            "legal",
            "lawsuit",
            "court",
            "prison",
            "sentence",
            "offender",
            "controversy",
            "debate",
            "dispute",
            "formal notice",
            "unpaid",
            "hiatus",
            "renewal",
            "deepfake",
            "teaser",
            "comeback",
            "casting",
            "ratings rise",
            "升温",
            "争议",
            "发酵",
            "分叉",
            "扩散",
            "媒体",
            "合约",
            "判刑",
            "法律",
        )

    @staticmethod
    def _low_value_patterns() -> tuple[str, ...]:
        return (
            "watch list",
            "viewing guide",
            "brand reputation rankings",
            "performances by",
            "no new event movement",
            "片单",
            "榜单",
        )

    @staticmethod
    def _event_text(event: dict) -> str:
        parts = [
            str(event.get("title", "")),
            str(event.get("headline_summary", "")),
            str(event.get("list_summary", "")),
            str(event.get("analysis_title", "")),
            str(event.get("analysis_body", "")),
        ]
        return " ".join(parts).lower()

    @staticmethod
    def _default_translate(text: str) -> str:
        request = Request(
            "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q=" + quote(text),
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/javascript, */*",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            segments = payload[0] if payload and payload[0] else []
            translated = "".join(part[0] for part in segments if part and part[0])
            return translated or text
        except Exception:
            return text

    @staticmethod
    def _slugify(value: str) -> str:
        chars = []
        for char in value.lower():
            if char.isalnum():
                chars.append(char)
            elif chars and chars[-1] != "-":
                chars.append("-")
        return "".join(chars).strip("-") or "event"

    def _translate_title(self, text: str, language: str = "zh-CN") -> str:
        if language == "en":
            return text
        return self._to_chinese(text)

    def _build_digest_entry(self, number: int, event: dict, language: str = "zh-CN") -> str:
        title = self._translate_title(event["title"], language=language).rstrip("。！？；：")
        raw_date = str(event.get("date") or "").strip()
        date_str = recorded_date(raw_date) or raw_date
        date_badge = f" ｜ {date_str}" if date_str else ""
        header = f"### N-{number:02d} {title}{date_badge}"

        summary_source = event.get("headline_summary") or event.get("list_summary") or event.get("title", "")
        summary = self._build_brief(summary_source, language=language)

        analysis = str(event.get("analysis_body") or "").strip()
        if analysis and language != "en":
            analysis = self._to_chinese(analysis)

        sources = render_sources(event.get("sources", []), language=language)

        lines = [header, summary]
        if analysis:
            label = "Why it matters" if language == "en" else "为何重要"
            sep = ": " if language == "en" else "："
            lines.append(f"{label}{sep}{analysis}")
        if sources:
            lines.append(sources)
        return "\n".join(lines)

    def _build_chinese_brief(self, text: str) -> str:
        return self._build_brief(text, language="zh-CN")

    def _build_brief(self, text: str, language: str = "zh-CN") -> str:
        text = " ".join(text.split())
        if not text:
            if language == "en":
                return "A real-time item was found and can be expanded later."
            return "当前抓到一条实时内容，后续可以继续展开。"
        if language == "en":
            return text if text.endswith((".", "!", "?")) else text + "."
        translated = self._to_chinese(text)
        return translated if translated.endswith(("。", "！", "？")) else translated + "。"

    def _build_chinese_analysis(self, text: str) -> str:
        text = " ".join(text.split())
        if not text:
            return "当前可用信息有限，建议继续观察后续更新。"
        translated = self._to_chinese(text)
        return translated if translated.endswith(("。", "！", "？")) else translated + "。"

    def _to_chinese(self, text: str) -> str:
        if any("\u4e00" <= char <= "\u9fff" for char in text):
            return text
        if self._translation_provider:
            return self._translation_cache.translate(
                text, self._translator, language="zh-CN", provider=self._translation_provider,
                write=self._translation_write,
            )
        try:
            translated = self._translator(text)
        except Exception:
            return text
        return translated if isinstance(translated, str) and translated.strip() else text

    def _build_deep_analysis_markdown(self, event: dict, language: str = "zh-CN") -> str:
        title = self._translate_title(event["analysis_title"], language=language)
        if language == "en":
            body = self._build_brief(event.get("analysis_body", ""), language=language)
            source_count = len(event.get("sources", []))
            evidence_note = (
                "multiple sources support the signal, so it can be treated as event-level movement."
                if source_count > 1
                else "it currently relies mainly on one source, so keep some uncertainty in the judgment."
            )
            lines = [
                f"# {title}",
                "",
                f"**Short take:** {body}",
                "",
                f"**Known facts:** The event has been recorded, and {evidence_note}",
                "",
                f"**Uncertainty:** {self._uncertainty_note(event, language=language)}",
                "",
                "**What to watch next:** Look for formal responses, independent follow-up reporting, platform data, or concrete legal/business movement. Repeated rewrites without new evidence should be discounted; new evidence or official action makes it worth continued tracking.",
                "",
            ]
            return "\n".join(lines)

        body = self._build_chinese_analysis(event.get("analysis_body", ""))
        source_count = len(event.get("sources", []))
        evidence_note = "目前至少有多条来源支撑，可以把它当作已经进入事件层面的信号。" if source_count > 1 else "目前主要来自单条来源，判断时要保留一点余量。"
        uncertainty_note = self._uncertainty_note(event, language=language)

        lines = [
            f"# {title}",
            "",
            f"**简要结论：** {body}",
            "",
            f"**已知事实：** 当前能确认的是事件本身已经被记录下来，{evidence_note}",
            "",
            f"**分歧与不确定性：** {uncertainty_note}",
            "",
            "**接下来观察：** 继续看是否出现当事方正式回应、更多独立来源跟进、平台数据或法律/商业层面的实质进展。如果后续只有重复转述，热度可能会自然回落；如果出现新证据或官方动作，就值得继续追。",
            "",
        ]
        return "\n".join(lines)

    def _build_thread_markdown(self, thread: dict) -> str:
        title = self._to_chinese(str(thread.get("name", "未命名thread")))
        summary = self._build_chinese_analysis(str(thread.get("summary", "")))
        callback_hint = self._build_chinese_analysis(str(thread.get("callback_hint", "")))
        status = self._thread_status_label(str(thread.get("status", "")))
        watchpoints = "；".join(
            self._to_chinese(str(item)).rstrip("。！？；：")
            for item in thread.get("watchpoints", [])
            if str(item).strip()
        )
        timeline_entries = thread.get("timeline", [])

        lines = [
            f"# {title}",
            "",
            f"**这条线在追什么：** {summary}",
            "",
            f"**当前状态：** {status}",
            "",
            f"**续写判断：** {callback_hint}",
            "",
        ]
        if watchpoints:
            lines.extend([f"**接下来观察：** {watchpoints}。", ""])

        lines.append("## 时间线")
        lines.append("")
        if timeline_entries:
            for index, entry in enumerate(timeline_entries, start=1):
                phase = self._thread_phase_label(str(entry.get("phase", "")))
                headline = self._to_chinese(str(entry.get("headline", "事件推进")))
                entry_summary = self._build_chinese_analysis(str(entry.get("summary", "")))
                date = str(entry.get("date", "")).strip()
                related_numbers = entry.get("related_digest_numbers", [])
                digest_note = ""
                if related_numbers:
                    digest_note = f" 关联日报：{', '.join(str(number) for number in related_numbers)}。"
                prefix = f"{date} · {phase}" if date else phase
                lines.append(f"{index}. {prefix}：{headline}。{entry_summary}{digest_note}")
        else:
            lines.append("1. 这条thread还没有写入时间线节点，后续出现新进展后再续写。")
        lines.append("")
        return "\n".join(lines)

    def _uncertainty_note(self, event: dict, language: str = "zh-CN") -> str:
        text = self._event_text(event)
        if language == "en":
            if any(keyword in text for keyword in ("reportedly", "allegedly", "rumor", "传闻", "疑似", "据报")):
                return "Some details are still not fully confirmed; distinguish reporting, official statements, and social-platform emotion."
            if len(event.get("sources", [])) > 1:
                return "Multiple sources make the outline stronger, but impact and next steps still need fresh responses or data."
            return "The evidence is still thin, so treat this as a watch signal rather than a settled conclusion."
        if any(keyword in text for keyword in ("reportedly", "allegedly", "rumor", "传闻", "疑似", "据报")):
            return "这里仍有未经完全确认的部分，尤其要区分媒体报道、当事方正式说法和社交平台情绪。"
        if len(event.get("sources", [])) > 1:
            return "多个来源让事件轮廓更稳，但影响范围和后续走向仍需要等新的回应或数据来确认。"
        return "信息还偏薄，暂时适合当作观察线索，而不是确定结论。"

    @staticmethod
    def _thread_status_label(status: str) -> str:
        return {
            "active": "持续跟进",
            "watching": "继续观察",
            "closed": "暂时收束",
        }.get(status, status or "继续观察")

    @staticmethod
    def _thread_phase_label(phase: str) -> str:
        return {
            "seed": "建线观察",
            "update": "进展续写",
            "milestone": "关键节点",
            "closure": "阶段收束",
        }.get(phase, phase or "进展续写")

    @staticmethod
    def _normalize_reference(value: str) -> str:
        return re.sub(r"[\s_\-]+", "", value.strip().lower())
