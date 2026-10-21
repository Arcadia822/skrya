"""Named document model and parsers for Skrya digests."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any
from urllib.parse import urlparse

from .sources import (
    SourceRef,
    is_valid_article_url,
    normalize_sources,
    parse_sources,
    primary_article_url,
)

LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
CJK_RE = re.compile(r"[\u2e80-\u9fff\u3000-\u303f\uff00-\uffef]")

SECTIONS = [
    ("threads", ["事件线", "时间线", "持续追踪", "追踪", "thread", "threads", "event timeline"]),
    ("news", ["今日简讯", "简讯", "热点", "舆情", "速览", "新闻", "briefs", "brief", "news", "top"]),
    ("background", ["背景", "延续观察", "观察", "background"]),
    ("intel", ["情报", "研判", "深度", "intel", "analysis"]),
    ("actions", ["可继续操作", "操作", "available actions", "actions"]),
]


def vwidth(s: str) -> float:
    """Visual width: CJK fullwidth counts 1.0, others 0.5."""
    return sum(1.0 if CJK_RE.match(ch) else 0.5 for ch in s)


def is_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text))


def detect_language(content: str) -> str:
    content_lower = content.lower()
    if (
        "## event timeline updates" in content_lower
        or "## today's briefs" in content_lower
        or "daily briefing" in content_lower
        or "## available actions" in content_lower
        or "latest developments" in content_lower
        or "historical timeline" in content_lower
    ):
        return "en"
    if "## 今日简讯" in content or "## 事件线时间线更新" in content or "每日简报" in content or "涉军速览" in content:
        return "zh-CN"
    cjk_count = sum(1 for ch in content if CJK_RE.match(ch))
    ascii_letter_count = sum(1 for ch in content if ch.isascii() and ch.isalpha())
    return "en" if ascii_letter_count > cjk_count * 2 else "zh-CN"


def extract_badge(text: str) -> str:
    """Extract an explicit recorded date badge. Never fabricate a date."""
    if not text:
        return ""

    def _valid(y: int | None, m: int, d: int, h: int | None = None, mi: int | None = None) -> bool:
        if y is not None and not (1970 <= y <= 2100):
            return False
        if not (1 <= m <= 12 and 1 <= d <= 31):
            return False
        if h is not None and not (0 <= h <= 23):
            return False
        if mi is not None and not (0 <= mi <= 59):
            return False
        return True

    # 1. ISO / Dash: (YYYY-)?MM-DD (HH:mm(:ss))?
    m_iso = re.search(r"(?<!\d)(?:(\d{4})-)?(\d{1,2})-(\d{1,2})(?:[T\s]+(\d{1,2}):(\d{2})(?::\d{2})?)?", text)
    if m_iso:
        y = int(m_iso.group(1)) if m_iso.group(1) else None
        m = int(m_iso.group(2))
        d = int(m_iso.group(3))
        h = int(m_iso.group(4)) if m_iso.group(4) else None
        mi = int(m_iso.group(5)) if m_iso.group(5) else None
        if _valid(y, m, d, h, mi):
            time_part = f" {h:02d}:{mi:02d}" if h is not None else ""
            return f"{y:04d}-{m:02d}-{d:02d}{time_part}" if y is not None else f"{m:02d}-{d:02d}{time_part}"

    # 2. Chinese style: (YYYY年)? MM月DD日 (HH:mm)?
    m_cn = re.search(r"(?<!\d)(?:(\d{4})年\s*)?(\d{1,2})月(\d{1,2})日?(?:\s+(\d{1,2}):(\d{2}))?", text)
    if m_cn:
        y = int(m_cn.group(1)) if m_cn.group(1) else None
        m = int(m_cn.group(2))
        d = int(m_cn.group(3))
        h = int(m_cn.group(4)) if m_cn.group(4) else None
        mi = int(m_cn.group(5)) if m_cn.group(5) else None
        if _valid(y, m, d, h, mi):
            time_part = f" {h:02d}:{mi:02d}" if h is not None else ""
            return f"{y:04d}-{m:02d}-{d:02d}{time_part}" if y is not None else f"{m:02d}-{d:02d}{time_part}"

    # 3. Slash style: (YYYY/)?MM/DD (HH:mm)?
    m_sl = re.search(r"(?<!\d)(?:(\d{4})/)?(\d{1,2})/(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?", text)
    if m_sl:
        y = int(m_sl.group(1)) if m_sl.group(1) else None
        m = int(m_sl.group(2))
        d = int(m_sl.group(3))
        h = int(m_sl.group(4)) if m_sl.group(4) else None
        mi = int(m_sl.group(5)) if m_sl.group(5) else None
        if _valid(y, m, d, h, mi):
            time_part = f" {h:02d}:{mi:02d}" if h is not None else ""
            return f"{y:04d}-{m:02d}-{d:02d}{time_part}" if y is not None else f"{m:02d}-{d:02d}{time_part}"

    return ""



@dataclass
class Milestone:
    title: str
    url: str = ""
    date: str = ""
    badge: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.badge and self.date:
            self.badge = self.date
        elif not self.date and self.badge:
            self.date = self.badge


@dataclass
class ThreadProgress:
    title: str
    url: str = ""
    badge: str = ""
    date: str = ""
    facts: str = ""
    comment: str = ""
    news_number: int | None = None
    sources: list[SourceRef] = field(default_factory=list)
    refs: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.badge and self.date:
            self.badge = self.date
        elif not self.date and self.badge:
            self.date = self.badge


@dataclass
class ThreadView:
    id: str
    number: int
    name: str
    stable_id: str = ""
    status: str = "active"
    latest_state: str = ""
    progress: list[ThreadProgress] = field(default_factory=list)
    timeline: list[Milestone] = field(default_factory=list)
    refs: list[int] = field(default_factory=list)
    raw_thread: dict[str, Any] = field(default_factory=dict)
    facts: str = ""
    comment: str = ""
    follow: str = ""


@dataclass
class DigestItem:
    key: str
    number: int
    title: str
    facts: str = ""
    why: str = ""
    sources: list[SourceRef] = field(default_factory=list)
    date: str = ""
    badge: str = ""
    extra: str = ""
    ref: str | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        if not self.badge and self.date:
            self.badge = self.date
        elif not self.date and self.badge:
            self.date = self.badge


@dataclass
class DigestDocument:
    title: str
    subtitle: str = ""
    scan_interval: str = ""
    lead: str = ""
    items: list[DigestItem] = field(default_factory=list)
    threads: list[ThreadView] = field(default_factory=list)
    background_blocks: list[dict[str, Any]] = field(default_factory=list)
    intel_blocks: list[dict[str, Any]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    language: str = "zh-CN"
    news_groups: list[tuple[str, str, list[DigestItem]]] = field(default_factory=list)

def _split_into_sections(lines: list[str]) -> tuple[str, str, str, str, list[dict[str, Any]]]:
    title = ""
    subtitle = ""
    scan_interval = ""
    lead_lines: list[str] = []
    blocks: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None

    for raw_ln in lines:
        ln = raw_ln.strip()
        if raw_ln.startswith("# ") and not title:
            title = raw_ln[2:].strip()
            continue
        if re.match(r"^\*\*[^*]+\*\*$", ln) and not subtitle and not blocks:
            subtitle = ln.strip("*").strip()
            continue
        scan_m = re.match(r"^(?:扫描时间范围|扫描时间|Scan window)\s*[:：]\s*(.*)$", ln, flags=re.I)
        if scan_m and not scan_interval:
            scan_interval = scan_m.group(1).strip()
            continue
        if raw_ln.startswith("## "):
            head = raw_ln[3:].strip()
            kind = "news"
            head_lower = head.lower()
            for k, keys in SECTIONS:
                if any(key in head_lower for key in keys):
                    kind = k
                    break
            cur = {"kind": kind, "heading": head, "lines": []}
            blocks.append(cur)
            continue
        if cur is None:
            if ln and not raw_ln.startswith("#"):
                lead_lines.append(ln)
        else:
            cur["lines"].append(raw_ln)

    return title, subtitle, scan_interval, " ".join(lead_lines), blocks


def _split_items_by_separators(lines: list[str]) -> list[str]:
    txt = "\n".join(lines)
    txt = re.sub(r"(?m)^\s*---+\s*$", "\n@@ITEM_SPLIT@@\n", txt)
    parts: list[str] = []
    for chunk in txt.split("@@ITEM_SPLIT@@"):
        chunk = chunk.strip()
        if not chunk:
            continue
        sub = re.split(
            r"(?m)^(?=###\s*N-\d+|###\s*[☐☑]?\s*\d+\s*[.｜|]|###\s*\d+\s*[.｜|]|"
            r"【\s*(?:🥇|🥈|🥉)?[\d\s]*】|N-\d+\s+|-\s*\*\*N-\d+\*\*|┌─)",
            chunk,
        )
        for s in sub:
            s = s.strip()
            if s:
                parts.append(s)
    return parts


def _parse_single_news_item(raw: str, fallback_idx: int) -> DigestItem | None:
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if not lines:
        return None

    first = lines[0]
    if first.startswith("# ") or first.startswith("## "):
        return None

    if "【Thread" in first or "【事件线" in first or re.match(r"^(?:###\s*T-?\d+|T-?\d+[\s.、])", first):
        return None

    idx = fallback_idx
    badge = ""
    title = ""
    is_news = False

    m_box = re.match(r"^┌─\s*\*\*【(?:简讯|Brief)\s*(\d+)】(.*)$", first)
    if m_box:
        is_news = True
        idx = int(m_box.group(1))
        title = m_box.group(2).strip("* ")
    elif first.startswith("┌─"):
        return None

    m_n = re.match(r"^###\s*N-(\d+)\s*(.*)$", first)
    if m_n:
        is_news = True
        idx = int(m_n.group(1))
        title = m_n.group(2)
    elif (m_bare := re.match(r"^N-(\d+)\s+(.*)$", first)):
        is_news = True
        idx = int(m_bare.group(1))
        title = m_bare.group(2)
    elif (m_bullet := re.match(r"^-\s*\*\*N-(\d+)\*\*\s*(.*)$", first)):
        is_news = True
        idx = int(m_bullet.group(1))
        title = m_bullet.group(2)

    m_cb = re.match(r"^###\s*(?:[☐☑]\s*)?(\d+)\s*[.｜|]\s*(.*)$", first)
    if m_cb and not is_news:
        is_news = True
        idx = int(m_cb.group(1))
        title = m_cb.group(2)

    m_br = re.match(r"^【\s*(?:🥇|🥈|🥉)?\s*(\d+)\s*】\s*(.*)$", first)
    if m_br and not is_news:
        is_news = True
        idx = int(m_br.group(1))
        title = m_br.group(2)

    if not is_news and first.startswith("### "):
        is_news = True
        title = first[4:].strip()

    if not is_news:
        has_news_structure = any(
            re.match(r"^\**(?:\s*信源|来源|Sources|Source|为何重要|Why it matters)\**\s*[:：]", l, flags=re.I)
            for l in lines[1:]
        )
        if has_news_structure:
            is_news = True
            title = first
        else:
            return None

    m_date = re.search(r"^(.*?)\s*[｜|]\s*((?:\d{4}[-/年])?\s*\d{1,2}[-/月]\d{1,2}日?(?:[T\s]+\d{1,2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)\s*$", title)
    if m_date:
        title = m_date.group(1)
        badge = extract_badge(m_date.group(2))

    title = re.sub(r"^###\s*", "", title)
    title = re.sub(r"^\*+|\*+$", "", title).strip()
    title = re.sub(r"\s*[｜|]\s*$", "", title).strip()

    facts_lines: list[str] = []
    why = ""
    sources: list[SourceRef] = []
    extra_lines: list[str] = []
    detected_url: str | None = None

    for raw_l in lines[1:]:
        l = raw_l.strip()
        l = re.sub(r"^[│└]\s*", "", l).strip()
        l = re.sub(r"</?font[^>]*>", "", l).strip()
        if not l or l == "└":
            continue

        if re.match(r"^\**(?:\s*信源|来源|Sources|Source)\**\s*[:：]", l, flags=re.I):
            parsed_srcs = parse_sources(l)
            sources.extend(parsed_srcs)
            if not badge:
                badge = extract_badge(l)
            continue

        m_why = re.match(r"^\**(?:为何重要|判断|价值点|核心影响|态势评估|Why it matters|Impact)\**\s*[:：]\s*(.*)$", l, flags=re.I)
        if m_why:
            val = m_why.group(1)
            val = re.sub(r"</?font[^>]*>", "", val).strip()
            val = re.sub(r"\*+", "", val).strip()
            if not why:
                why = val
            continue

        m_sum = re.match(r"^\**(?:摘要|事实|Summary|Facts)\**\s*[:：]\s*(.*)$", l, flags=re.I)
        if m_sum:
            s_val = m_sum.group(1).strip()
            if s_val:
                facts_lines.append(s_val)
            continue

        if re.match(r"^(?:今日增量|时间线位置)", l):
            extra_lines.append(re.split(r"[:：]", l, maxsplit=1)[-1].strip())
            continue

        facts_lines.append(l)

    link_m = LINK_RE.search(title)
    if link_m:
        cand_url = link_m.group(2).strip()
        if is_valid_article_url(cand_url):
            detected_url = cand_url

    primary_url = detected_url or primary_article_url(sources)

    return DigestItem(
        key=f"news-{idx}",
        number=idx,
        title=title,
        facts=" ".join(facts_lines).strip(),
        why=why,
        sources=sources,
        date=badge,
        badge=badge,
        extra=" ".join(extra_lines).strip(),
        url=primary_url,
    )

def _parse_thread_blocks(lines: list[str]) -> list[ThreadView]:
    text = "\n".join(lines)
    header = r"(?:###\s*T-?\d+|T-?\d+[\s.、]|【Thread[:：]|┌─\s*\*\*【Thread】|【Thread】)"
    chunks = re.split(r"(?m)^(?=" + header + r")", text)
    threads: list[ThreadView] = []

    for chunk in chunks:
        chunk = chunk.strip()
        if not re.match(header, chunk):
            continue

        chunk_lines = [l.rstrip() for l in chunk.splitlines() if l.strip()]
        first = chunk_lines[0]
        number = len(threads) + 1
        name = ""
        stable_id = ""

        m_num = re.search(r"T-?(\d+)", first)
        if m_num:
            number = int(m_num.group(1))

        if "【Thread】" in first:
            m_tag = re.search(r"【Thread】\s*(.*?)(?:\(([^)]+)\))?(?:\s*\*\*)?$", first)
            if m_tag:
                name = m_tag.group(1).strip("* ")
                stable_id = m_tag.group(2) or ""
        elif "【Thread" in first:
            m_th = re.search(r"【Thread[:：]?\s*(.+?)】(?:\(([^)]+)\))?", first)
            if m_th:
                name = m_th.group(1).strip()
                stable_id = m_th.group(2) or ""
        elif first.startswith("┌─"):
            m_box = re.search(r"【Thread】\s*(.*?)(?:\(([^)]+)\))?\s*\*\*", first)
            if m_box:
                name = m_box.group(1).strip()
                stable_id = m_box.group(2) or ""
        else:
            name = re.sub(r"^(?:###\s*)?T-?\d+[.]?\s*", "", first).strip("* ")
        slug = re.search(r"[（(]([a-z0-9][a-z0-9_-]+)[）)]\s*$", name)
        if slug:
            if not stable_id:
                stable_id = slug.group(1)
            name = name[:slug.start()].strip()

        references: set[int] = set()
        for group in re.findall(r"第\s*(\d+(?:\s*[、,，]\s*\d+)*)\s*条", chunk):
            references.update(int(num) for num in re.findall(r"\d+", group))
        for group in re.findall(r"(?:Brief|items?)\s*(\d+(?:\s*[,，]\s*\d+)*)", chunk, flags=re.I):
            references.update(int(num) for num in re.findall(r"\d+", group))
        references.update(int(num) for num in re.findall(r"\bN-?(\d+)\b", chunk))
        progress_entries: list[ThreadProgress] = []
        timeline_entries: list[Milestone] = []
        latest_state = ""
        follow = ""
        facts = ""
        comment = ""

        current_progress: ThreadProgress | None = None
        pending_sources: list[SourceRef] = []
        in_historical = False

        for raw_line in chunk_lines[1:]:
            line = re.sub(r"^[│└]\s*", "", raw_line).strip()
            line = re.sub(r"</?font[^>]*>", "", line).strip()
            if not line:
                continue

            if re.match(r"^\**(?:\s*最新进展|今日增量|Latest developments)\**\s*[:：]?", line, flags=re.I):
                in_historical = False
                current_progress = None
                remainder = re.split(r"[:：]", line, maxsplit=1)[-1].strip()
                if remainder and not re.match(r"^\**最新进展\**", line):
                    facts = (facts + " " + remainder).strip()
                continue

            if re.match(r"^\**(?:\s*历史时间线|时间线|Historical timeline)\**\s*[:：]?", line, flags=re.I):
                in_historical = True
                current_progress = None
                continue

            if re.search(r"(?:本轮暂无可核验新增|复核结果|No verified update)", line, flags=re.I):
                continue

            m_state = re.match(r"^\**(?:\s*最新状态|时间线位置|Latest state|Latest known state)\**\s*[:：]\s*(.*)$", line, flags=re.I)
            if m_state:
                latest_state = m_state.group(1).strip()
                continue

            m_follow = re.match(r"^\**(?:\s*下一步观察|后续观察|Watch next)\**\s*[:：]\s*(.*)$", line, flags=re.I)
            if m_follow:
                follow = m_follow.group(1).strip()
                continue

            m_comm = re.match(r"^\**(?:\s*点评|态势评估|影响判断|Comment|Impact)\**\s*[:：]\s*(.*)$", line, flags=re.I)
            if m_comm:
                c_val = m_comm.group(1).strip()
                if current_progress:
                    current_progress.comment = c_val
                else:
                    comment = c_val
                continue
            if re.match(r"^\**(?:\s*信源|来源|Sources|Source)\**\s*[:：]", line, flags=re.I):
                if not in_historical:
                    parsed_srcs = parse_sources(line)
                    if current_progress:
                        current_progress.sources.extend(parsed_srcs)
                    else:
                        pending_sources.extend(parsed_srcs)
                continue

            link_m = LINK_RE.search(line)
            if link_m:
                entry_title = link_m.group(1).strip("* ")
                entry_url = link_m.group(2)
                badge = extract_badge(line)

                if in_historical:
                    recorded_date = extract_badge(line[:link_m.start()] + line[link_m.end():])
                    if recorded_date and is_valid_article_url(entry_url):
                        timeline_entries.append(
                            Milestone(title=entry_title, url=entry_url, date=recorded_date, badge=recorded_date)
                        )
                    current_progress = None
                    continue
                else:
                    news_num: int | None = None
                    m_nref = re.search(r"N-(\d+)", line)
                    if m_nref:
                        news_num = int(m_nref.group(1))
                        references.add(news_num)
                    p_entry = ThreadProgress(
                        title=entry_title,
                        url=entry_url,
                        date=badge,
                        badge=badge,
                        news_number=news_num,
                    )
                    progress_entries.append(p_entry)
                    current_progress = p_entry
                    continue

            if not in_historical:
                if current_progress:
                    current_progress.facts = (current_progress.facts + " " + line).strip()
                else:
                    facts = (facts + " " + line).strip()

        if facts or pending_sources:
            progress_entries.insert(
                0,
                ThreadProgress(
                    title=name,
                    facts=facts,
                    comment=comment,
                    date=latest_state,
                    badge=latest_state,
                    sources=pending_sources,
                ),
            )

        thread = ThreadView(
            id=stable_id or f"thread-{number}",
            number=number,
            name=name,
            stable_id=stable_id,
            status="active",
            latest_state=latest_state,
            progress=progress_entries,
            timeline=timeline_entries,
            refs=sorted(references),
            raw_thread={},
            facts=facts,
            comment=comment,
            follow=follow,
        )
        threads.append(thread)

    return threads


def parse_digest(markdown: str, *, snapshot: dict[str, Any] | None = None) -> DigestDocument:
    if not markdown or not markdown.strip():
        raise ValueError("Cannot parse empty markdown document.")

    content = markdown.strip()
    language = detect_language(content)
    lines = content.splitlines()

    title, subtitle, scan_interval, lead, blocks = _split_into_sections(lines)

    # Detect numbered items in raw content to ensure none vanish
    numbered_news_markers = re.findall(
        r"(?m)^\s*(?:###\s*N-\d+|###\s*[☐☑]?\s*\d+\s*[.｜|]|┌─\s*\*\*【(?:简讯|Brief)\s*\d+】|【\s*(?:🥇|🥈|🥉)?\s*\d+\s*】|-\s*\*\*N-\d+\*\*|N-\d+\s+)",
        content,
    )

    items: list[DigestItem] = []
    threads: list[ThreadView] = []
    background_blocks: list[dict[str, Any]] = []
    intel_blocks: list[dict[str, Any]] = []
    news_groups: list[tuple[str, str, list[DigestItem]]] = []

    if blocks:
        for b in blocks:
            kind = b["kind"]
            heading = b["heading"]
            sec_lines = b["lines"]

            if kind == "threads":
                threads.extend(_parse_thread_blocks(sec_lines))
            elif kind == "news":
                item_chunks = _split_items_by_separators(sec_lines)
                group_items: list[DigestItem] = []
                note = ""
                if item_chunks and not re.match(
                    r"^\s*(?:###\s*N-\d+|###\s*[☐☑]?\s*\d+\s*[.｜|]|┌─|【\s*(?:🥇|🥈|🥉)?\s*\d+\s*】|N-\d+\s+|-\s*\*\*N-\d+)",
                    item_chunks[0],
                ):
                    note = item_chunks[0]
                    item_chunks = item_chunks[1:]

                for ch in item_chunks:
                    parsed_it = _parse_single_news_item(ch, len(items) + 1)
                    if parsed_it:
                        items.append(parsed_it)
                        group_items.append(parsed_it)
                    else:
                        if not any(k in ch for k in ("本轮暂无可核验", "暂无", "No verified", "没有抓到", "暂无可核验")):
                            raise ValueError(f"Unparseable news content in digest: {ch[:60]}")
                if group_items:
                    news_groups.append((heading, note, group_items))
                elif note and not any(k in note for k in ("本轮暂无可核验", "暂无", "No verified", "没有抓到", "暂无可核验")):
                    raise ValueError(f"Unparseable news section: {note[:60]}")
            elif kind == "background":
                background_blocks.append(b)
            elif kind == "intel":
                intel_blocks.append(b)
    else:
        thread_lines = [l for l in lines if "Thread" in l or re.match(r"^###\s*T-?\d+", l)]
        if thread_lines:
            threads.extend(_parse_thread_blocks(lines))
        item_chunks = _split_items_by_separators(lines)
        for ch in item_chunks:
            parsed_it = _parse_single_news_item(ch, len(items) + 1)
            if parsed_it:
                items.append(parsed_it)

    if numbered_news_markers and len(items) < len(numbered_news_markers):
        raise ValueError(
            f"Detected {len(numbered_news_markers)} numbered news items but only parsed {len(items)}. "
            "Numbered items cannot silently vanish."
        )

    if not items and not threads:
        is_known_structure = (
            bool(title)
            and (
                "每日简报" in title
                or "Daily Briefing" in title
                or "速览" in title
                or any(b["kind"] in ("news", "threads") for b in blocks)
                or "本轮暂无可核验" in content
                or "No verified update" in content
                or "没有抓到" in content
                or "暂时没有" in content
            )
        )
        if not is_known_structure:
            raise ValueError("Unknown digest document format: no valid news items, threads, or recognized digest structure found.")
    if snapshot:
        snapshot_items = snapshot.get("items") or snapshot.get("news") or {}
        for it in items:
            ref_tag = f"N-{it.number:02d}"
            snap_entry = snapshot_items.get(ref_tag)
            if isinstance(snap_entry, dict):
                if snap_entry.get("key"):
                    it.key = snap_entry["key"]
                if not it.badge and snap_entry.get("date"):
                    it.badge = snap_entry["date"]
                    it.date = snap_entry["date"]
                if snap_entry.get("sources"):
                    snap_sources = normalize_sources(snap_entry["sources"])
                    reconciled_sources = normalize_sources([*it.sources, *snap_sources])
                    it.sources = [
                        SourceRef(
                            name=source["name"],
                            url=source["url"],
                            extra={k: v for k, v in source.items() if k not in ("name", "url")},
                        )
                        for source in reconciled_sources
                    ]
                if not it.url or not is_valid_article_url(it.url):
                    it.url = primary_article_url(it.sources)

        snapshot_threads = snapshot.get("threads") or {}
        for th in threads:
            t_tag = f"T-{th.number:02d}"
            snap_th = snapshot_threads.get(t_tag)
            if isinstance(snap_th, dict):
                if snap_th.get("id"):
                    th.stable_id = snap_th["id"]
                th.raw_thread = snap_th

    actions = [
        "回复 `dig: N-01` — 展开指定条目的深度分析与专家级背景研判",
        "回复 `track: N-02` — 为指定事件建立持续追踪线",
        "回复 `dig: T-01` — 查看该事件线的全量历史脉络",
        "回复 `write: T-01` — 把这一系列事件写成一篇文章",
        "自然语言反馈 — 例如“增加涉华舆情分析”或“减少例行口水争端”",
    ] if language == "zh-CN" else [
        "Reply `dig: N-01` — expand deep analysis and expert context",
        "Reply `track: N-02` — start a continuous tracking thread",
        "Reply `dig: T-01` — view full historical timeline",
        "Reply `write: T-01` — draft an article from this thread",
        "Natural-language feedback — e.g. 'more enterprise coverage' or 'reduce routine noise'",
    ]

    return DigestDocument(
        title=title or ("Skrya 日报" if language == "zh-CN" else "Skrya Daily Briefing"),
        subtitle=subtitle,
        scan_interval=scan_interval,
        lead=lead,
        items=items,
        threads=threads,
        background_blocks=background_blocks,
        intel_blocks=intel_blocks,
        actions=actions,
        language=language,
        news_groups=news_groups,
    )




def parse_threads(lines_or_text: list[str] | str) -> list[ThreadView]:
    """Parse an isolated Thread section without reading or writing history."""
    lines = lines_or_text.splitlines() if isinstance(lines_or_text, str) else list(lines_or_text)
    return _parse_thread_blocks(lines)


