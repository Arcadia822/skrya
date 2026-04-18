from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


@dataclass(slots=True)
class DigestResult:
    markdown: str
    digest_path: Path
    artifact_path: Path


@dataclass(slots=True)
class DeepAnalysisResult:
    markdown: str
    artifact_path: Path


class IntelligenceService:
    def __init__(self, root: Path | str, fetcher=None, translator=None) -> None:
        self._root = Path(root)
        self._fetcher = fetcher or self._default_fetch
        self._translator = translator or self._default_translate

    def generate_digest(self, topic_id: str, prefer_live: bool = True) -> DigestResult:
        events = self._load_events(topic_id, prefer_live=prefer_live)
        self._ensure_topic(topic_id)

        lines: list[str] = ["# Digest", ""]
        for number, event in enumerate(events, start=1):
            lines.append(self._build_digest_entry(number, event))
            lines.append("")

        lines.append("如果你要继续，我可以直接对其中任意一条做深入分析，你回复编号就行。")

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
                    "items": [
                        {
                            "number": index,
                            "key": event["key"],
                            "title": event["title"],
                            "analysis_title": event["analysis_title"],
                            "analysis_body": event["analysis_body"],
                            "sources": event["sources"],
                        }
                        for index, event in enumerate(events, start=1)
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return DigestResult(
            markdown=markdown,
            digest_path=digest_path,
            artifact_path=event_index_path,
        )

    def generate_deep_analysis(self, topic_id: str, event_number: int) -> DeepAnalysisResult:
        event = self._resolve_event(topic_id, event_number)

        lines = [
            f"# {self._translate_title(event['analysis_title'])}",
            "",
            self._build_chinese_analysis(event["analysis_body"]),
            "",
        ]
        markdown = "\n".join(lines)

        artifact_dir = self._root / "runs" / topic_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        analysis_path = artifact_dir / f"deep-analysis-{event_number}.md"
        analysis_path.write_text(markdown, encoding="utf-8")

        return DeepAnalysisResult(markdown=markdown, artifact_path=analysis_path)

    def get_event_sources(self, topic_id: str, event_number: int) -> list[str]:
        event = self._resolve_event(topic_id, event_number)
        return list(event["sources"])

    def _resolve_event(self, topic_id: str, event_number: int) -> dict:
        event_index_path = self._root / "runs" / topic_id / "latest-digest-events.json"
        if not event_index_path.exists():
            raise FileNotFoundError(f"Digest artifact not found for topic '{topic_id}'")

        index = json.loads(event_index_path.read_text(encoding="utf-8"))
        for item in index["items"]:
            if item["number"] == event_number:
                return item

        raise ValueError(f"Event number {event_number} not found for topic '{topic_id}'")

    def _ensure_topic(self, topic_id: str) -> Path:
        topic_dir = self._root / "topics" / topic_id
        if not topic_dir.exists():
            raise FileNotFoundError(f"Topic '{topic_id}' not found")
        return topic_dir

    def _load_events(self, topic_id: str, prefer_live: bool = False) -> list[dict]:
        topic_dir = self._ensure_topic(topic_id)
        sample_path = topic_dir / "sample-events.json"
        sources_payload = json.loads((topic_dir / "sources.json").read_text(encoding="utf-8"))
        has_live_sources = any(
            source.get("enabled", True) and source.get("type") == "rss"
            for source in sources_payload.get("sources", [])
        )

        if prefer_live and has_live_sources:
            live_events = self._load_events_from_sources(topic_dir)
            if live_events:
                return live_events

        if sample_path.exists():
            return json.loads(sample_path.read_text(encoding="utf-8"))

        if has_live_sources:
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

            rss_text = self._fetcher(source["url"])
            root = ET.fromstring(rss_text)
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
