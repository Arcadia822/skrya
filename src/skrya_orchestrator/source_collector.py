"""Live source collection: feed config validation, RSS2/Atom/RDF parsing, RSSHub hedging and health results."""
from __future__ import annotations

import html
import json
import re
import time
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urljoin, urlsplit

from .event_lifecycle import EventLifecycle
from .http_cache import HttpCache, default_ttl
from .rsshub import fetch_rsshub
from .source_health import SourceHealthCorruptError, SourceHealthStore
from .sources import host_name, normalize_sources, source_identity

NEUTRAL_CAPABILITIES = ("web_search", "news_search")
FALLBACK_TERMS_LIMIT = 6
DEFAULT_MAX_ITEMS = 5

XML_BASE_ATTR = "{http://www.w3.org/XML/1998/namespace}base"
_FEED_TYPES = ("rss", "rsshub")

_BRIEF_STOP_TERMS = {
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



@dataclass(slots=True)
class CollectionResult:
    """Outcome of one live collection pass over a topic's enabled feed sources.

    events carry canonical source records plus lifecycle identity fields
    (source_id/event_id/content_hash). health_notice is a concise single lead
    line, empty when no relevant problem exists. fallbacks are provider-neutral
    retrieval fallback records ready for with_source_fallbacks().
    """

    events: list[dict] = field(default_factory=list)
    health_notice: str = ""
    failed_source_ids: list[str] = field(default_factory=list)
    fallbacks: list[dict] = field(default_factory=list)


class SourceCollector:
    """Collect enabled rss/rsshub sources for one topic, with health and lifecycle updates.

    Receives an explicit topic_dir, an HttpCache or an injected one-argument
    fetcher(url)->str. write=False (preview) performs read-only collection:
    no cache writes, no health save, no lifecycle persistence. force_refresh
    bypasses HTTP cache freshness for every source fetch.
    """

    def __init__(
        self,
        topic_dir: Path | str,
        http_cache: HttpCache | None = None,
        fetcher: Callable[[str], str] | None = None,
        *,
        clock: Callable[[], datetime | float] | datetime | float | None = None,
        opener: Any = None,
        force_refresh: bool = False,
        write: bool = True,
        health: SourceHealthStore | None = None,
        lifecycle: EventLifecycle | None = None,
    ) -> None:
        self._topic_dir = Path(topic_dir)
        self._http_cache = http_cache
        self._fetcher = fetcher
        self._clock = clock
        self._opener = opener
        self._force_refresh = force_refresh
        self._write = write
        self._health = health or SourceHealthStore(
            self._topic_dir, clock=clock, source_names=self._source_names()
        )
        self._lifecycle = lifecycle or EventLifecycle(self._data_root(), self._topic_dir.name)

    @property
    def topic_dir(self) -> Path:
        return self._topic_dir

    def collect(self) -> CollectionResult:
        """Run one live collection pass and persist health/lifecycle when write=True."""
        failed: list[tuple[str, dict]] = []
        events: list[dict] = []

        for source in self._enabled_feed_sources():
            source_id = self._source_id(source)
            if not self._health.should_fetch(source_id):
                if str(source.get("type") or "").strip().lower() == "rsshub":
                    failed.append((source_id, source))
                continue
            source_events, error = self._collect_source(source)
            if error is not None:
                failed.append((source_id, source))
                self._health.record_failure(source_id, error)
                continue
            if not source_events:
                failed.append((source_id, source))
                self._health.record_failure(source_id, "feed returned no usable items")
                continue
            identified = self._lifecycle.identify_events(source_events)
            events.extend(self._record_success(source_id, identified))

        fallbacks = self._fallback_records(failed)
        notice = self._notice_from_health(
            [source_id for source_id, _ in failed],
            extra=self._save_health() if self._enabled_feed_sources() else [],
        )
        return CollectionResult(
            events=events,
            health_notice=notice,
            failed_source_ids=[source_id for source_id, source in failed if str(source.get("type") or "").strip().lower() == "rsshub"],
            fallbacks=fallbacks,
        )

    def health_notice(self) -> str:
        """Reading entry: concise lead line for the current health state, no collection."""
        return self._notice_from_health([], extra=[])

    def health_snapshot(self) -> dict:
        """Reading entry: serializable health state, no collection."""
        return self._health.snapshot()

    def failing_source_ids(self) -> list[str]:
        """Reading entry: source ids currently degraded or in error backoff."""
        result: list[str] = []
        for source_id, entry in self._health.snapshot().get("sources", {}).items():
            if int(entry.get("consecutive_failures") or 0) > 0 or str(entry.get("status") or "") in ("degraded", "error"):
                result.append(source_id)
        return result

    def fallback_records(self, failed_source_ids: Sequence[str] | None = None) -> list[dict]:
        """Fallback records for the given failed source ids, or currently failing ones."""
        if failed_source_ids is None:
            failed_source_ids = self.failing_source_ids()
        by_id = {self._source_id(source): source for source in self._enabled_feed_sources()}
        failed = [(source_id, by_id[source_id]) for source_id in failed_source_ids if source_id in by_id]
        return self._fallback_records(failed)

    def _save_health(self) -> list[str]:
        if not self._write:
            return []
        try:
            self._health.save()
        except SourceHealthCorruptError:
            if self._language() == "en":
                return [
                    "Source health file is corrupt; health state was not written and the original file is preserved."
                ]
            return ["信源健康文件损坏，本轮健康状态未写入，原文件保持不动。"]
        return []

    def _record_success(self, source_id: str, identified_events: list[dict]) -> list[dict]:
        self._health.record_success(source_id, len(identified_events))
        if not self._write:
            return identified_events
        recorded = self._lifecycle.record_source(source_id, identified_events, persist=True)
        generations = [
            int(record.get("generation") or 0) for record in recorded if isinstance(record, dict)
        ]
        if generations:
            self._health.set_generation(source_id, max(generations))
        return recorded

    def _collect_source(self, source: dict) -> tuple[list[dict], Any]:
        """Return (events, error); error None means the source produced a parsed result."""
        try:
            if str(source.get("type") or "").strip().lower() == "rsshub":
                body = fetch_rsshub(source, self._rsshub_fetch_callback(source))
            else:
                url = str(source.get("url") or "").strip()
                if not _is_http_url(url):
                    raise ValueError(f"invalid rss source url: {url!r}")
                body = self._fetch_body(url, 20, source)
            events = self._events_from_items(parse_feed_items(body), source)
        except Exception as exc:
            return [], exc
        return events, None

    def _rsshub_fetch_callback(self, source: dict) -> Callable[[str, float], str]:
        """RSSHub hedge callback: validation happens inside _fetch_body before any
        cache write, and the deadline bounds the underlying HTTP read."""

        def fetch(url: str, timeout_seconds: float) -> str:
            deadline = time.monotonic() + timeout_seconds
            return self._fetch_body(url, timeout_seconds, source, deadline=deadline)

        return fetch

    def _feed_validator(self, source: dict) -> Callable[[str], None]:
        """Reject bodies with no usable items before they reach the cache."""

        def validate(body_text: str) -> None:
            items = parse_feed_items(body_text)
            if not self._events_from_items(items, source):
                raise ValueError("feed response has no usable items")

        return validate

    def _fetch_body(
        self, url: str, timeout: float, source: dict, *, deadline: float | None = None
    ) -> str:
        validate = self._feed_validator(source)
        if self._fetcher is not None:
            body = self._fetcher(url)
            validate(body)
            return body
        if self._http_cache is None:
            self._http_cache = HttpCache(self._data_root(), clock=self._clock, opener=self._opener)
        return self._http_cache.fetch(
            url,
            ttl_seconds=default_ttl(source),
            force_refresh=self._force_refresh,
            write=self._write,
            timeout=timeout,
            deadline=deadline,
            validate=validate,
        )

    def _events_from_items(self, items: list[dict], source: dict) -> list[dict]:
        source_name = str(source.get("name") or "").strip()
        try:
            max_items = int(source.get("max_items") or DEFAULT_MAX_ITEMS)
        except (TypeError, ValueError):
            max_items = DEFAULT_MAX_ITEMS
        max_items = max(1, max_items)

        events: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            title = str(item.get("title") or "").strip()
            link = str(item.get("link") or "").strip()
            if not title or (not link and not source_name):
                continue
            dedupe_key = (title.lower(), link)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            if link:
                raw_record = {"name": source_name or host_name(link), "url": link}
            else:
                raw_record = {"name": source_name, "url": ""}
            summary = _strip_html(str(item.get("summary") or "")) or title
            event: dict[str, Any] = {
                "key": _slugify(title),
                "source_id": self._source_id(source),
                "title": title,
                "summary": summary,
                "content": _strip_html(str(item.get("content") or "")) or summary,
                "headline_summary": summary,
                "list_summary": summary,
                "analysis_title": title,
                "analysis_body": summary,
                "sources": normalize_sources([raw_record]),
            }
            date_raw = str(item.get("date") or "").strip()
            if date_raw:
                event["date"] = feed_date_iso(date_raw)
            events.append(event)
            if len(events) >= max_items:
                break
        return events

    def _enabled_feed_sources(self) -> list[dict]:
        path = self._topic_dir / "sources.json"
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        sources: list[dict] = []
        for source in payload.get("sources", []):
            if not isinstance(source, dict):
                continue
            if not source.get("enabled", True):
                continue
            if str(source.get("type") or "").strip().lower() not in _FEED_TYPES:
                continue
            sources.append(source)
        return sources

    def _fallback_records(self, failed: Sequence[tuple[str, dict]]) -> list[dict]:
        if not failed:
            return []
        brief_terms = self._brief_terms()
        records: list[dict] = []
        for source_id, source in failed:
            if str(source.get("type") or "").strip().lower() != "rsshub":
                continue
            name = str(source.get("name") or "").strip() or source_id
            block = source.get("fallback") if isinstance(source.get("fallback"), dict) else None
            if block is not None:
                capabilities = [
                    cap.strip()
                    for cap in block.get("capabilities", [])
                    if isinstance(cap, str) and cap.strip() in NEUTRAL_CAPABILITIES
                ]
                queries = [
                    query.strip()
                    for query in block.get("queries", [])
                    if isinstance(query, str) and query.strip()
                ]
                origin = "configured"
            else:
                capabilities = list(NEUTRAL_CAPABILITIES)
                query_parts = [name, *brief_terms]
                queries = [" ".join(part for part in query_parts if part)]
                origin = "generated"
            if not capabilities and not queries:
                continue
            records.append(
                {
                    "source_id": source_id,
                    "name": name,
                    "capabilities": capabilities,
                    "queries": queries,
                    "origin": origin,
                }
            )
        return records

    def _brief_terms(self) -> list[str]:
        path = self._topic_dir / "brief.json"
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        text = " ".join(
            str(request.get("content", ""))
            for request in payload.get("requests", [])
            if isinstance(request, dict)
        ).lower()
        terms: list[str] = []
        for token in re.findall(r"[a-z0-9][a-z0-9\-]{2,}|[\u4e00-\u9fff]{2,}", text):
            if token in _BRIEF_STOP_TERMS or token in terms:
                continue
            terms.append(token)
            if len(terms) >= FALLBACK_TERMS_LIMIT:
                break
        return terms

    def _notice_from_health(self, failed_now: Sequence[str], *, extra: Sequence[str]) -> str:
        is_en = self._language() == "en"
        parts: list[str] = []
        failed_set = set(failed_now)
        enabled = {self._source_id(source) for source in self._enabled_feed_sources()}
        for source_id, entry in self._health.snapshot().get("sources", {}).items():
            if source_id not in enabled:
                continue
            status = str(entry.get("status") or "")
            failures = int(entry.get("consecutive_failures") or 0)
            name = self._health.get_source_display_name(source_id)
            if status == "error":
                if is_en:
                    parts.append(f"{name} ({failures} consecutive failures, fetch paused)")
                else:
                    parts.append(f"{name}（连续失败 {failures} 次，暂缓拉取）")
            elif status == "degraded":
                if is_en:
                    parts.append(f"{name} ({failures} consecutive failures, degraded)")
                else:
                    parts.append(f"{name}（连续失败 {failures} 次，已降级）")
            elif source_id in failed_set:
                if is_en:
                    parts.append(f"{name} (failed this run)")
                else:
                    parts.append(f"{name}（本轮拉取失败）")
        if not parts and not extra:
            return ""
        lead = "Source notice: " + ", ".join(parts) if is_en else "信源提示：" + "；".join(parts)
        tail = " ".join(str(note) for note in extra if note)
        return f"{lead} {tail}".strip()

    def _language(self) -> str:
        path = self._topic_dir / "topic.json"
        if not path.is_file():
            return "zh-CN"
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "zh-CN"
        language = str(metadata.get("language", "")).strip().lower()
        return "en" if language in {"en", "en-us", "en-gb"} else "zh-CN"

    def _source_names(self) -> dict[str, str]:
        path = self._topic_dir / "sources.json"
        names: dict[str, str] = {}
        if not path.is_file():
            return names
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return names
        for source in payload.get("sources", []):
            if not isinstance(source, dict):
                continue
            source_id = self._source_id(source)
            name = str(source.get("name") or "").strip()
            if source_id and name:
                names[source_id] = name
        return names

    @staticmethod
    def _source_id(source: dict) -> str:
        return source_identity(source)

    def _data_root(self) -> Path:
        return self._topic_dir.parent.parent


def with_source_fallbacks(
    request: dict[str, Any],
    *,
    fallbacks: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Pure builder: merge provider-neutral fallback records into a retrieval request copy.

    Capabilities and queries from fallback records are appended to the request's
    existing ones; records carry source_id/name/capabilities/queries/origin.
    """
    merged = deepcopy(request) if isinstance(request, dict) else {}
    fallback_list = [deepcopy(fb) for fb in fallbacks if isinstance(fb, dict)]

    capabilities = [
        cap.strip() for cap in merged.get("capabilities", []) if isinstance(cap, str) and cap.strip()
    ]
    queries = [query.strip() for query in merged.get("queries", []) if isinstance(query, str) and query.strip()]
    for record in fallback_list:
        for cap in record.get("capabilities", []):
            cap = str(cap).strip()
            if cap and cap not in capabilities:
                capabilities.append(cap)
        for query in record.get("queries", []):
            query = str(query).strip()
            if query and query not in queries:
                queries.append(query)

    merged["capabilities"] = capabilities
    merged["queries"] = queries
    if fallback_list:
        merged["fallbacks"] = fallback_list
    return merged


def parse_feed_items(body: str) -> list[dict]:
    """Parse RSS2/Atom/RDF items into title/link/summary/date records.

    Shared by RSSHub hedge acceptance and event construction: a body is usable
    exactly when this parser yields at least one titled item.
    """
    if not isinstance(body, str) or not body.strip():
        return []
    try:
        root = ET.fromstring(body.strip().encode("utf-8"))
    except ET.ParseError:
        return []

    if _local_name(root.tag).lower() not in ("rss", "feed", "rdf"):
        return []
    root_base = (root.get(XML_BASE_ATTR) or "").strip()
    items: list[dict] = []
    for node in root.findall(".//{*}item") + root.findall(".//{*}entry"):
        title = _node_text(node, ("title",))
        if not title:
            continue
        entry_base = _inherited_base(root_base, node)
        items.append(
            {
                "title": title,
                "link": _feed_link(node, entry_base),
                "summary": _node_text(node, ("description", "summary", "content", "encoded")),
                "content": _node_text(node, ("content", "encoded")),
                "date": _node_text(node, ("pubDate", "published", "updated", "date")),
            }
        )
    return items


def feed_date_iso(raw: str) -> str:
    """Return the real date as ISO-8601 when parseable, otherwise the raw text."""
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        parsed = parsedate_to_datetime(text)
        if parsed is not None and parsed.year >= 1900:
            return parsed.isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return text


def _node_text(node: ET.Element, local_names: tuple[str, ...]) -> str:
    for child in node:
        if _local_name(child.tag) in local_names:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return ""


def _feed_link(node: ET.Element, base: str = "") -> str:
    alternates: list[str] = []
    first_href = ""
    for child in node:
        if _local_name(child.tag) != "link":
            continue
        child_base = _inherited_base(base, child)
        text = (child.text or "").strip()
        if text:
            return urljoin(child_base, text)
        href = (child.get("href") or "").strip()
        if not href:
            continue
        resolved = urljoin(child_base, href)
        if not first_href:
            first_href = resolved
        rel = (child.get("rel") or "").strip()
        if rel in ("", "alternate"):
            alternates.append(resolved)
    return alternates[0] if alternates else first_href


def _inherited_base(parent_base: str, node: ET.Element) -> str:
    """Resolve a node's xml:base against its parent's inherited base."""
    own = (node.get(XML_BASE_ATTR) or "").strip()
    if not own:
        return parent_base
    return urljoin(parent_base, own)

def _local_name(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


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


def _slugify(value: str) -> str:
    chars = []
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
        elif chars and chars[-1] != "-":
            chars.append("-")
    return "".join(chars).strip("-") or "event"


def _is_http_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)




