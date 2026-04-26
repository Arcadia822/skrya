from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from .ingest import IngestService


@dataclass(slots=True)
class DigestResult:
    markdown: str
    digest_path: Path
    artifact_path: Path


@dataclass(slots=True)
class DeepAnalysisResult:
    markdown: str
    artifact_path: Path


@dataclass(slots=True)
class EventThreadResult:
    markdown: str
    artifact_path: Path


@dataclass(slots=True)
class EventThreadRefreshResult:
    artifact_path: Path
    payload: dict


class IntelligenceService:
    def __init__(self, root: Path | str, fetcher=None, translator=None) -> None:
        self._root = Path(root)
        self._fetcher = fetcher or self._default_fetch
        self._translator = translator or self._default_translate

    def generate_digest(self, topic_id: str, prefer_live: bool = True) -> DigestResult:
        topic_id = self.resolve_topic_id(topic_id)
        events = self._load_events(topic_id, prefer_live=prefer_live)
        events = self._rank_events(topic_id, events)
        self._ensure_topic(topic_id)
        numbered_events = list(enumerate(events, start=1))
        event_thread_updates = self._build_digest_event_thread_updates(topic_id, numbered_events)

        lines: list[str] = ["# Digest", ""]
        if events:
            if event_thread_updates:
                lines.append("## 事件线更新")
                lines.append("")
                for update_lines in event_thread_updates:
                    lines.extend(update_lines)
                    lines.append("")

                lines.append("## 今日简讯")
                lines.append("")

            for number, event in numbered_events:
                lines.append(self._build_digest_entry(number, event))
                lines.append("")
        else:
            lines.append("暂时没有抓到足够新的真实内容，先不拿样例数据冒充日报。你可以稍后再试，或者明确告诉我用样例做演示。")
            lines.append("")

        lines.extend(self._build_digest_feedback_options())

        markdown = "\n".join(lines).strip() + "\n"

        artifact_dir = self._root / "runs" / topic_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        digest_path = artifact_dir / "latest-digest.md"
        digest_path.write_text(markdown, encoding="utf-8")

        event_index_path = artifact_dir / "latest-digest-events.json"
        event_index_path.write_text(
            json.dumps(
                {
                    "topic": topic_id,
                    "items": [self._digest_event_index_item(index, event) for index, event in numbered_events],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._persist_event_threads_from_digest_items(
            topic_id,
            [self._digest_event_index_item(index, event) for index, event in numbered_events],
        )

        return DigestResult(
            markdown=markdown,
            digest_path=digest_path,
            artifact_path=event_index_path,
        )

    def generate_deep_analysis(self, topic_id: str, event_number: int) -> DeepAnalysisResult:
        topic_id = self.resolve_topic_id(topic_id)
        event = self._resolve_event(topic_id, event_number)

        markdown = self._build_deep_analysis_markdown(event)

        artifact_dir = self._root / "runs" / topic_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        analysis_path = artifact_dir / f"deep-analysis-{event_number}.md"
        analysis_path.write_text(markdown, encoding="utf-8")

        return DeepAnalysisResult(markdown=markdown, artifact_path=analysis_path)

    def get_event_sources(self, topic_id: str, event_number: int) -> list[str]:
        topic_id = self.resolve_topic_id(topic_id)
        event = self._resolve_event(topic_id, event_number)
        return list(event["sources"])

    def generate_event_thread_timeline(self, topic_id: str, thread_reference: str) -> EventThreadResult:
        topic_id = self.resolve_topic_id(topic_id)
        thread, artifact_path = self._resolve_event_thread(topic_id, thread_reference)
        return EventThreadResult(
            markdown=self._build_event_thread_markdown(thread),
            artifact_path=artifact_path,
        )

    def refresh_event_threads(self, topic_id: str) -> EventThreadRefreshResult:
        topic_id = self.resolve_topic_id(topic_id)
        self._ensure_topic(topic_id)
        seed_payload = self._load_event_thread_seed_payload(topic_id)
        existing_payload = self._load_event_thread_payload(topic_id)
        definitions = self._event_thread_definitions(
            seed_payload.get("threads", []),
            existing_payload.get("threads", []),
        )
        if not definitions:
            raise FileNotFoundError(
                f"Event-thread seeds not found for topic '{topic_id}'. "
                "Create topics/<topic-id>/event-thread-seeds.json first."
            )

        items = self._load_digest_event_items(topic_id)
        artifact_path, payload = self._write_event_thread_artifact(topic_id, definitions, items)
        return EventThreadRefreshResult(artifact_path=artifact_path, payload=payload)

    def resolve_topic_id(self, topic_reference: str) -> str:
        topics_root = self._root / "topics"
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
        event_index_path = self._root / "runs" / topic_id / "latest-digest-events.json"
        if not event_index_path.exists():
            raise FileNotFoundError(f"Digest artifact not found for topic '{topic_id}'")

        index = json.loads(event_index_path.read_text(encoding="utf-8"))
        for item in index["items"]:
            if item["number"] == event_number:
                return item

        raise ValueError(f"Event number {event_number} not found for topic '{topic_id}'")

    def _resolve_event_thread(self, topic_id: str, thread_reference: str) -> tuple[dict, Path]:
        artifact_path = self._root / "runs" / topic_id / "event-threads" / "latest-event-threads.json"
        if not artifact_path.exists():
            raise FileNotFoundError(f"Event-thread artifact not found for topic '{topic_id}'")

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
            raise ValueError(f"Event thread reference '{thread_reference}' is ambiguous: {names}")

        raise ValueError(f"Event thread '{thread_reference}' not found for topic '{topic_id}'")

    def _load_digest_event_items(self, topic_id: str) -> list[dict]:
        event_index_path = self._root / "runs" / topic_id / "latest-digest-events.json"
        if not event_index_path.exists():
            raise FileNotFoundError(f"Digest artifact not found for topic '{topic_id}'")
        payload = json.loads(event_index_path.read_text(encoding="utf-8"))
        return [dict(item) for item in payload.get("items", []) if isinstance(item, dict)]

    def _load_event_thread_seed_payload(self, topic_id: str) -> dict:
        seed_path = self._root / "topics" / topic_id / "event-thread-seeds.json"
        if not seed_path.exists():
            return {}
        return json.loads(seed_path.read_text(encoding="utf-8"))

    def _load_event_thread_payload(self, topic_id: str) -> dict:
        artifact_path = self._root / "runs" / topic_id / "event-threads" / "latest-event-threads.json"
        if not artifact_path.exists():
            return {}
        return json.loads(artifact_path.read_text(encoding="utf-8"))

    def _persist_event_threads_from_digest_items(self, topic_id: str, items: list[dict]) -> None:
        seed_payload = self._load_event_thread_seed_payload(topic_id)
        existing_payload = self._load_event_thread_payload(topic_id)
        definitions = self._event_thread_definitions(
            seed_payload.get("threads", []),
            existing_payload.get("threads", []),
        )
        if not definitions:
            return

        self._write_event_thread_artifact(topic_id, definitions, items)

    def _write_event_thread_artifact(self, topic_id: str, definitions: list[dict], items: list[dict]) -> tuple[Path, dict]:
        threads = [self._materialize_event_thread(definition, items) for definition in definitions]
        payload = {
            "interface_version": "skrya.event-thread.v1",
            "topic_id": topic_id,
            "threads": threads,
        }
        artifact_path = self._root / "runs" / topic_id / "event-threads" / "latest-event-threads.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return artifact_path, payload

    def _event_thread_definitions(self, seed_threads: list[dict], existing_threads: list[dict]) -> list[dict]:
        definitions: dict[str, dict] = {}
        ordered_keys: list[str] = []

        for thread in existing_threads:
            if not isinstance(thread, dict):
                continue
            key = str(thread.get("id") or self._slugify(str(thread.get("name", "")))).strip()
            if not key:
                continue
            definitions[key] = {
                "id": key,
                "name": str(thread.get("name", "")).strip(),
                "status": str(thread.get("status", "")).strip(),
                "summary": str(thread.get("summary", "")).strip(),
                "callback_hint": str(thread.get("callback_hint", "")).strip(),
                "aliases": [str(alias) for alias in thread.get("aliases", []) if str(alias).strip()],
                "watchpoints": [str(point) for point in thread.get("watchpoints", []) if str(point).strip()],
                "timeline": [dict(entry) for entry in thread.get("timeline", []) if isinstance(entry, dict)],
                "_match_terms": self._event_thread_match_terms(thread),
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
                "_match_terms": self._event_thread_match_terms(seed, base),
            }
            definitions[key] = merged
            if key not in ordered_keys:
                ordered_keys.append(key)

        return [definitions[key] for key in ordered_keys]

    def _event_thread_match_terms(self, *threads: dict) -> list[str]:
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

    def _materialize_event_thread(self, definition: dict, items: list[dict]) -> dict:
        thread = {
            "id": definition["id"],
            "name": definition.get("name", ""),
            "status": definition.get("status", ""),
            "summary": definition.get("summary", ""),
            "callback_hint": definition.get("callback_hint", ""),
            "aliases": list(definition.get("aliases", [])),
            "watchpoints": list(definition.get("watchpoints", [])),
        }
        timeline = [dict(entry) for entry in definition.get("timeline", []) if isinstance(entry, dict)]
        seen_signatures = {self._event_thread_entry_signature(entry) for entry in timeline}
        new_entries: list[dict] = []

        for item in self._matched_event_thread_items(definition, items):
            entry = self._event_thread_entry_from_digest_item(item, has_existing=bool(timeline or new_entries))
            signature = self._event_thread_entry_signature(entry)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            new_entries.append(entry)

        thread["timeline"] = timeline + new_entries
        if not thread["status"]:
            thread["status"] = "active" if thread["timeline"] else "watching"
        return thread

    def _matched_event_thread_items(self, definition: dict, items: list[dict]) -> list[dict]:
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

    def _event_thread_entry_from_digest_item(self, item: dict, *, has_existing: bool) -> dict:
        raw_date = str(item.get("date", "")).strip()
        date = raw_date[:10] if raw_date else ""
        number = item.get("number")
        related_numbers = [int(number)] if isinstance(number, int) else []
        return {
            "date": date,
            "phase": "update" if has_existing else "seed",
            "headline": str(item.get("title") or item.get("analysis_title") or "事件推进").strip(),
            "summary": str(item.get("analysis_body") or item.get("analysis_title") or item.get("title") or "").strip(),
            "related_digest_numbers": related_numbers,
            "sources": [str(source) for source in item.get("sources", []) if str(source).strip()],
        }

    def _build_digest_event_thread_updates(self, topic_id: str, numbered_events: list[tuple[int, dict]]) -> list[list[str]]:
        seed_payload = self._load_event_thread_seed_payload(topic_id)
        existing_payload = self._load_event_thread_payload(topic_id)
        definitions = self._event_thread_definitions(
            seed_payload.get("threads", []),
            existing_payload.get("threads", []),
        )
        if not definitions:
            return []

        items = [self._digest_event_index_item(number, event) for number, event in numbered_events]
        updates: list[list[str]] = []
        for definition in definitions:
            matched_items = self._matched_event_thread_items(definition, items)
            if not matched_items:
                continue
            updates.append(self._build_digest_event_thread_update(definition, matched_items))
        return updates

    def _build_digest_event_thread_update(self, definition: dict, matched_items: list[dict]) -> list[str]:
        name = self._to_chinese(str(definition.get("name") or "未命名事件线"))
        related_numbers = "、".join(str(item.get("number")) for item in matched_items if item.get("number"))
        titles = "；".join(
            self._to_chinese(str(item.get("title", ""))).rstrip("。！？；：")
            for item in matched_items[:3]
            if str(item.get("title", "")).strip()
        )
        summaries = " ".join(
            self._build_chinese_analysis(str(item.get("analysis_body") or item.get("analysis_title") or item.get("title") or ""))
            for item in matched_items[:2]
        )
        watchpoints = "；".join(
            self._to_chinese(str(point)).rstrip("。！？；：")
            for point in definition.get("watchpoints", [])[:2]
            if str(point).strip()
        )

        lines = [
            f"**{name}**",
            f"今天命中的简讯：{related_numbers}。{titles}。",
            f"具体进展：{summaries}",
        ]
        if watchpoints:
            lines.append(f"后续看点：{watchpoints}。")
        else:
            callback_hint = self._build_chinese_analysis(str(definition.get("callback_hint", "")))
            lines.append(f"后续判断：{callback_hint}")
        return lines

    def _digest_event_index_item(self, number: int, event: dict) -> dict:
        return {
            "number": number,
            "key": event["key"],
            "title": event["title"],
            "analysis_title": event["analysis_title"],
            "analysis_body": event["analysis_body"],
            "sources": event["sources"],
            "date": event.get("date", ""),
        }

    def _event_thread_entry_signature(self, entry: dict) -> tuple[str, str, tuple[str, ...]]:
        return (
            str(entry.get("date", "")).strip(),
            self._normalize_reference(str(entry.get("headline", ""))),
            tuple(sorted(str(source) for source in entry.get("sources", []) if str(source).strip())),
        )

    def _ensure_topic(self, topic_id: str) -> Path:
        topic_dir = self._root / "topics" / topic_id
        if not topic_dir.exists():
            raise FileNotFoundError(f"Topic '{topic_id}' not found")
        return topic_dir

    def _load_events(self, topic_id: str, prefer_live: bool = False) -> list[dict]:
        topic_dir = self._ensure_topic(topic_id)
        sample_path = topic_dir / "sample-events.json"
        ingest_service = IngestService(self._root)
        sources_payload = json.loads((topic_dir / "sources.json").read_text(encoding="utf-8"))
        has_rss_sources = any(
            source.get("enabled", True) and source.get("type") == "rss"
            for source in sources_payload.get("sources", [])
        )
        has_runtime_retrieval_sources = ingest_service.has_runtime_retrieval_sources(topic_id)

        if prefer_live:
            ingest_events = ingest_service.load_events(topic_id)
            if ingest_events:
                return ingest_events
            if has_rss_sources:
                return self._load_events_from_sources(topic_dir)
            if has_runtime_retrieval_sources:
                return []

        if sample_path.exists():
            return json.loads(sample_path.read_text(encoding="utf-8"))

        if has_rss_sources:
            return self._load_events_from_sources(topic_dir)

        return []

    def _load_events_from_sources(self, topic_dir: Path) -> list[dict]:
        sources_payload = json.loads((topic_dir / "sources.json").read_text(encoding="utf-8"))
        events: list[dict] = []

        for source in sources_payload.get("sources", []):
            if not source.get("enabled", True):
                continue
            if source.get("type") != "rss":
                continue

            try:
                rss_text = self._fetcher(source["url"])
                root = ET.fromstring(rss_text)
            except Exception:
                continue
            items = root.findall("./channel/item")
            for item in items[:5]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                description = self._strip_html((item.findtext("description") or "").strip())
                if not title or not link:
                    continue
                events.append(
                    {
                        "key": self._slugify(title),
                        "title": title,
                        "headline_summary": description or title,
                        "list_summary": description or title,
                        "analysis_title": title,
                        "analysis_body": description or title,
                        "sources": [link],
                    }
                )

        unique: list[dict] = []
        seen_titles: set[str] = set()
        for event in events:
            normalized_title = event["title"].strip().lower()
            if normalized_title in seen_titles:
                continue
            seen_titles.add(normalized_title)
            unique.append(event)

        return unique[:15]

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
    def _default_fetch(url: str) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="ignore")

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

    @staticmethod
    def _strip_html(value: str) -> str:
        text = []
        in_tag = False
        for char in value:
            if char == "<":
                in_tag = True
                continue
            if char == ">":
                in_tag = False
                continue
            if not in_tag:
                text.append(char)

        cleaned = " ".join("".join(text).split())
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"Continue reading.*$", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"The post .*? appeared first on .*\.?$", "", cleaned, flags=re.IGNORECASE).strip()
        return cleaned

    def _translate_title(self, text: str) -> str:
        return self._to_chinese(text)

    def _build_digest_entry(self, number: int, event: dict) -> str:
        title = self._translate_title(event["title"]).rstrip("。！？；：")
        summary_source = event["headline_summary"] or event["list_summary"] or event["title"]
        summary = self._build_chinese_brief(summary_source)
        return f"{number}. {title}，{summary}"

    @staticmethod
    def _build_digest_feedback_options() -> list[str]:
        return [
            "你可以这样反馈：",
            "",
            "A. 详细分析指定今日简讯，例如：`A 3 5 12`。",
            "B. 创建新的事件线。事件线是 topic 下持续追踪同一件事进展的时间线，例如：`B 3 4 5 持续关注`。",
            "C. 对简讯和事件线的获取策略进行调整，例如：`C 6 7 我不喜欢，如果是 xxx 不要关注`。",
        ]

    def _build_chinese_brief(self, text: str) -> str:
        text = " ".join(text.split())
        if not text:
            return "当前抓到一条实时内容，后续可以继续展开。"
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
        translated = self._translator(text)
        return translated if translated else text

    def _build_deep_analysis_markdown(self, event: dict) -> str:
        title = self._translate_title(event["analysis_title"])
        body = self._build_chinese_analysis(event.get("analysis_body", ""))
        source_count = len(event.get("sources", []))
        evidence_note = "目前至少有多条来源支撑，可以把它当作已经进入事件层面的信号。" if source_count > 1 else "目前主要来自单条来源，判断时要保留一点余量。"
        uncertainty_note = self._uncertainty_note(event)

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

    def _build_event_thread_markdown(self, thread: dict) -> str:
        title = self._to_chinese(str(thread.get("name", "未命名事件线")))
        summary = self._build_chinese_analysis(str(thread.get("summary", "")))
        callback_hint = self._build_chinese_analysis(str(thread.get("callback_hint", "")))
        status = self._event_thread_status_label(str(thread.get("status", "")))
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
                phase = self._event_thread_phase_label(str(entry.get("phase", "")))
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
            lines.append("1. 这条事件线还没有写入时间线节点，后续出现新进展后再续写。")
        lines.append("")
        return "\n".join(lines)

    def _uncertainty_note(self, event: dict) -> str:
        text = self._event_text(event)
        if any(keyword in text for keyword in ("reportedly", "allegedly", "rumor", "传闻", "疑似", "据报")):
            return "这里仍有未经完全确认的部分，尤其要区分媒体报道、当事方正式说法和社交平台情绪。"
        if len(event.get("sources", [])) > 1:
            return "多个来源让事件轮廓更稳，但影响范围和后续走向仍需要等新的回应或数据来确认。"
        return "信息还偏薄，暂时适合当作观察线索，而不是确定结论。"

    @staticmethod
    def _event_thread_status_label(status: str) -> str:
        return {
            "active": "持续跟进",
            "watching": "继续观察",
            "closed": "暂时收束",
        }.get(status, status or "继续观察")

    @staticmethod
    def _event_thread_phase_label(phase: str) -> str:
        return {
            "seed": "建线观察",
            "update": "进展续写",
            "milestone": "关键节点",
            "closure": "阶段收束",
        }.get(phase, phase or "进展续写")

    @staticmethod
    def _normalize_reference(value: str) -> str:
        return re.sub(r"[\s_\-]+", "", value.strip().lower())
