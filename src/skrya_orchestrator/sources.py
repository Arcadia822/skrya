"""Canonical boundary helpers for source records and fidelity."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import parse_qs, urlsplit

GENERIC_LINK_TEXT = {
    "链接",
    "链接地址",
    "原文",
    "原文链接",
    "报道",
    "详细报道",
    "详情",
    "查看",
    "查看详情",
    "新闻",
    "来源",
    "信源",
    "link",
    "url",
    "source",
    "sources",
    "article",
    "news",
    "view",
}

LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)]*)\)")
BARE_URL_RE = re.compile(r"https?://[^\s)\]]+")
SOURCE_TOKEN_RE = re.compile(f"{LINK_RE.pattern}|{BARE_URL_RE.pattern}")

HOMEPAGE_PATHS = {
    "",
    "/",
    "/index.html",
    "/index.htm",
    "/index.php",
    "/index.shtml",
    "/index.asp",
    "/default.aspx",
    "/default.asp",
    "/default.html",
    "/default.htm",
    "/home",
    "/home/",
}

SEARCH_PATH_PREFIXES = (
    "search",
    "query",
    "so",
    "find",
    "sousuo",
)

SEARCH_QUERY_PARAMS = {
    "q",
    "query",
    "keyword",
    "keywords",
    "search",
    "searchword",
    "search_query",
    "wd",
    "word",
}


@dataclass
class SourceRef:
    """Lightweight view of a source reference with name, optional URL, and extra metadata."""

    name: str
    url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.extra)
        result["name"] = self.name
        result["url"] = self.url
        return result


def clean_source_name(name: str) -> str:
    """Clean formatting and colon-delimited labels without stripping publisher prefixes."""
    cleaned = re.sub(r"</?font\b[^>]*>", "", name or "", flags=re.I)
    cleaned = LINK_RE.sub(r"\1", cleaned)
    cleaned = re.sub(r"[*`_]+", "", cleaned)
    cleaned = re.sub(r"^\s*(?:来源|信源|sources?)\s*[:：]\s*", "", cleaned, flags=re.I)
    return cleaned.strip()


def host_name(url: str) -> str:
    """Derive a friendly display name from a URL's hostname."""
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        host = ""
    host = re.sub(r"^www\.", "", host.lower())
    return host or "link"


def is_valid_article_url(url: str) -> bool:
    """Validate http(s) URL structure and detect obvious homepage/search placeholders.

    Returns True only for structurally sound http(s) URLs pointing to specific resource paths.
    Obvious homepage placeholders and search pages return False so they degrade to plain labels.
    Never uses regex fake-ID guesses or network link tests.
    """
    if not isinstance(url, str):
        return False
    trimmed = url.strip()
    if not trimmed or any(ch.isspace() for ch in url):
        return False
    try:
        parts = urlsplit(trimmed)
    except Exception:
        return False

    if parts.scheme.lower() not in ("http", "https"):
        return False

    netloc = parts.netloc.strip().lower()
    if not netloc or any(ch.isspace() for ch in netloc):
        return False
    try:
        hostname = parts.hostname
        port = parts.port
        username = parts.username
        password = parts.password
    except ValueError:
        return False
    if not hostname:
        return False
    if username or password:
        return False
    if "." not in hostname and hostname != "localhost":
        return False
    if port is not None and not (0 < port <= 65535):
        return False

    path = parts.path.strip()
    norm_path = path.rstrip("/") if path != "/" else "/"

    if (norm_path in HOMEPAGE_PATHS or path in HOMEPAGE_PATHS) and not parts.query and not parts.fragment:
        return False

    path_segments = [seg.lower() for seg in path.split("/") if seg]
    if path_segments and path_segments[0] in SEARCH_PATH_PREFIXES:
        return False

    if parts.query:
        try:
            params = parse_qs(parts.query, keep_blank_values=True)
            if any(k.lower() in SEARCH_QUERY_PARAMS for k in params) and len(path_segments) <= 1:
                return False
        except Exception:
            pass

    return True


def _is_date_token(token: str) -> bool:
    t = token.strip().strip("()（）")
    if re.match(r"^(?:\d{4}[-/])?\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$", t):
        return True
    if re.match(r"^\d{4}年\d{1,2}月\d{1,2}日", t):
        return True
    return False


def _is_ref_token(token: str) -> bool:
    return bool(re.match(r"^[NT]-\d+$", token.strip(), flags=re.I))


def _split_source_string(text: str) -> list[str]:
    """Retain every link and unlinked label within each source-line segment."""
    cleaned = re.sub(r"</?font[^>]*>", "", text or "").strip()
    cleaned = re.sub(r"^\**\s*(?:信源|来源|sources?)\s*\**\s*[:：]\s*", "", cleaned, flags=re.I).strip()
    if not cleaned:
        return []

    tokens: list[str] = []
    for segment in re.split(r"\s*[|｜]\s*", cleaned):
        cursor = 0
        for match in SOURCE_TOKEN_RE.finditer(segment):
            label = segment[cursor:match.start()].strip(" \t\r\n,;，；·")
            if label:
                tokens.append(label)
            tokens.append(match.group(0))
            cursor = match.end()
        label = segment[cursor:].strip(" \t\r\n,;，；·")
        if label:
            tokens.append(label)
    return tokens


def _attach_url_provenance(record: dict[str, Any], raw_url: str) -> None:
    """Preserve the original URL as provenance when the display URL degrades to a plain label."""
    if raw_url and not record.get("url") and not record.get("original_url"):
        record["original_url"] = raw_url


def _merge_metadata(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any] | None:
    """Combine missing metadata fields without replacing recorded evidence."""
    merged = dict(left)
    for key, value in right.items():
        if key not in merged:
            merged[key] = value
        elif isinstance(merged[key], dict) and isinstance(value, dict):
            nested = _merge_metadata(merged[key], value)
            if nested is None:
                return None
            merged[key] = nested
        elif merged[key] != value:
            return None
    return merged


def normalize_sources(sources: Any) -> list[dict[str, Any]]:
    """Normalize source inputs into canonical source dicts preserving name and valid URL.

    Accepts:
    - None or empty
    - list/tuple of strings, dicts, or SourceRef
    - single string (plain media name, bare URL, markdown link, or pipe-separated)
    - single dict or SourceRef

    Guarantees:
    - Retains all source names/labels (even without URL).
    - Degrades invalid/homepage/search URLs to plain labels (url=""), keeping the name.
    - Keeps the original rejected URL as `original_url` provenance when degrading.
    - Never fabricates or reassigns URLs across items.
    - Merges compatible duplicate metadata; retains conflicting provenance as separate records.
    - Matches articles by URL; only metadata-free plain labels can gain a link by name.
    """
    if sources is None:
        return []

    if isinstance(sources, (dict, SourceRef)):
        raw_items = [sources]
    elif isinstance(sources, str):
        raw_items = _split_source_string(sources)
    elif isinstance(sources, Iterable):
        raw_items = []
        for s in sources:
            if isinstance(s, str):
                raw_items.extend(_split_source_string(s))
            else:
                raw_items.append(s)
    else:
        return []

    raw_records: list[dict[str, Any]] = []

    for item in raw_items:
        if item is None:
            continue
        if isinstance(item, SourceRef):
            name = clean_source_name(item.name)
            raw_url = item.url or ""
            url = raw_url if is_valid_article_url(raw_url) else ""
            if not name and raw_url:
                name = host_name(raw_url)
            record = dict(item.extra)
            record["name"] = name
            record["url"] = url
            _attach_url_provenance(record, raw_url)
            raw_records.append(record)
        elif isinstance(item, dict):
            raw_url = str(item.get("url") or "")
            url = raw_url if is_valid_article_url(raw_url) else ""
            raw_name = item.get("name") or item.get("source_name") or item.get("title") or ""
            name = clean_source_name(str(raw_name))
            if not name and raw_url:
                name = host_name(raw_url)
            record = dict(item)
            record["name"] = name
            record["url"] = url
            _attach_url_provenance(record, raw_url)
            if "source_name" in item and not record.get("source_name"):
                record["source_name"] = name
            raw_records.append(record)
        elif isinstance(item, str):
            token = item.strip()
            if not token or _is_date_token(token) or _is_ref_token(token):
                continue
            m = LINK_RE.fullmatch(token)
            if m:
                raw_name = m.group(1)
                raw_url = m.group(2)
                name = clean_source_name(raw_name)
                url = raw_url if is_valid_article_url(raw_url) else ""
                if not name or name.lower() in GENERIC_LINK_TEXT:
                    name = host_name(raw_url)
                record = {"name": name, "url": url}
                _attach_url_provenance(record, raw_url)
                raw_records.append(record)
            elif token.startswith("http://") or token.startswith("https://") or BARE_URL_RE.match(token):
                raw_url = token.rstrip(".,;，。")
                url = raw_url if is_valid_article_url(raw_url) else ""
                name = host_name(raw_url)
                record = {"name": name, "url": url}
                _attach_url_provenance(record, raw_url)
                raw_records.append(record)
            else:
                name = clean_source_name(token)
                if not name or name.lower() in GENERIC_LINK_TEXT:
                    continue
                raw_records.append({"name": name, "url": ""})

    result: list[dict[str, Any]] = []

    for record in raw_records:
        name = record.get("name", "").strip()
        url = record.get("url", "").strip()
        if not name and not url:
            continue
        if not name:
            name = host_name(url)
            record["name"] = name

        metadata = {k: v for k, v in record.items() if k not in ("name", "url")}
        for index, existing in enumerate(result):
            existing_url = existing["url"]
            existing_metadata = {k: v for k, v in existing.items() if k not in ("name", "url")}
            if url and existing_url:
                if url != existing_url:
                    continue
            else:
                if name.lower() != existing["name"].lower():
                    continue
                # Name alone cannot identify the article behind an evidence-bearing record.
                if (url and existing_metadata) or (existing_url and metadata):
                    continue
            merged = _merge_metadata(existing_metadata, metadata)
            if merged is None:
                continue
            result[index] = {**merged, "name": existing["name"], "url": existing_url or url}
            break
        else:
            result.append(record)

    return result


def primary_article_url(target: Any) -> str:
    """Extract the primary valid article URL from an item, event, source list, or source.

    Returns the first valid, non-placeholder article URL found.
    Returns empty string if all sources are plain labels or invalid/placeholder URLs.
    Never invents URLs or borrows URLs from other items.
    """
    if target is None:
        return ""

    if isinstance(target, str):
        for source in normalize_sources(target):
            if source["url"]:
                return source["url"]
        return ""

    if isinstance(target, SourceRef):
        if target.url and is_valid_article_url(target.url):
            return target.url.strip()
        return ""

    if isinstance(target, dict):
        raw_url = str(target.get("url") or "")
        if raw_url and is_valid_article_url(raw_url):
            return raw_url
        if target.get("sources"):
            return primary_article_url(target["sources"])
        return ""

    if hasattr(target, "url") and target.url and is_valid_article_url(str(target.url)):
        return str(target.url).strip()

    if hasattr(target, "sources") and target.sources:
        return primary_article_url(target.sources)

    if isinstance(target, Iterable):
        for s in target:
            url = primary_article_url(s)
            if url:
                return url
        return ""

    return ""


def render_sources(sources: Any, language: str = "zh-CN") -> str:
    """Render source records in Feishu grey font prefix and linked/plain media names.

    Sources with valid URLs render as markdown hyperlinks: [Name](url).
    Sources without URLs render as plain text media names: Name.
    Canonical names are display text; only the URL field supplies a link destination.
    Multiple sources are separated with ' | '.
    """
    normalized = normalize_sources(sources)
    if not normalized:
        return ""

    parts: list[str] = []
    for s in normalized:
        name = s.get("name", "").strip()
        url = s.get("url", "").strip()
        if not name and not url:
            continue
        if not name:
            name = host_name(url)
        display_name = name.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        if url:
            parts.append(f"[{display_name}]({url})")
        else:
            parts.append(display_name)

    if not parts:
        return ""

    label = "信源：" if language == "zh-CN" else "Sources: "
    return f'<font color="grey">{label}</font>' + " | ".join(parts)


def parse_sources(text: str) -> list[SourceRef]:
    """Parse source links and plain media names from a line or block into clean SourceRefs.

    Accepts:
    - Markdown links: [新华社](https://...)
    - Bare URLs: https://...
    - Plain media names: 央视军事, 微博热搜
    - Mixed formats: [新华社](https://...) | 央视军事 | 微博热搜
    """
    if not text:
        return []
    normalized = normalize_sources(text)
    return [
        SourceRef(
            name=s["name"],
            url=s["url"],
            extra={k: v for k, v in s.items() if k not in ("name", "url")},
        )
        for s in normalized
    ]


