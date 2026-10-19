"""Pure Python Feishu card renderer producing Schema 2.0 card bundles."""
from __future__ import annotations

import json
import re
from typing import Any

from .digest_document import (
    DigestItem,
    ThreadView,
    parse_digest,
    extract_badge,
    render_sources,
)

BG_NEWS = "blue-50"
BG_THREAD = "yellow-50"
BG_OPS = "grey"

ELEMENT_BUDGET = 190
DEFAULT_PAYLOAD_BYTES = 24000


def md(content: str, align: str | None = None) -> dict[str, Any]:
    el: dict[str, Any] = {"tag": "markdown", "content": content}
    if align:
        el["text_align"] = align
    return el


def box(children: list[dict[str, Any]], bg: str, weight: int = 1) -> dict[str, Any]:
    return {
        "tag": "column_set",
        "flex_mode": "stretch",
        "background_style": bg,
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": weight,
                "padding": "14px 18px",
                "elements": children,
            }
        ],
    }


def two_col(
    left_md: dict[str, Any],
    right_md: dict[str, Any],
    weights: tuple[int, int] = (7, 1),
    bg: str | None = None,
) -> dict[str, Any]:
    el: dict[str, Any] = {
        "tag": "column_set",
        "flex_mode": "stretch",
        "columns": [
            {"tag": "column", "width": "weighted", "weight": weights[0], "elements": [left_md]},
            {"tag": "column", "width": "weighted", "weight": weights[1], "elements": [right_md]},
        ],
    }
    if bg:
        el["background_style"] = bg
    return el


def section_header(text: str) -> dict[str, Any]:
    return md(f"✦ ─── {text} ─── ✦", align="center")


def count_elements(el: dict[str, Any]) -> int:
    """Count components recursively per Feishu Schema 2.0 component limits."""
    c = 1
    if "columns" in el:
        for col in el["columns"]:
            c += count_elements(col)
    elif "elements" in el:
        for sub in el["elements"]:
            c += count_elements(sub)
    return c


def estimate_request_envelope_bytes(card: dict[str, Any]) -> int:
    """Measure serialized request envelope bytes using conservative 256-byte target/root placeholders."""
    card_json = json.dumps(card, ensure_ascii=False, separators=(",", ":"))
    envelope = {
        "receive_id": "x" * 128,
        "root_id": "x" * 128,
        "msg_type": "interactive",
        "content": card_json,
        "uuid": "00000000-0000-0000-0000-000000000000",
    }
    return len(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def build_card_dict(
    base_title: str,
    subtitle: str,
    elements: list[dict[str, Any]],
    part_idx: int = 1,
    total_parts: int = 1,
) -> dict[str, Any]:
    if total_parts > 1:
        title = f"{base_title} ({part_idx}/{total_parts})"
    else:
        title = base_title

    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": title or "Skrya 日报"},
            "subtitle": {"tag": "plain_text", "content": subtitle or ""},
            "template": "blue",
        },
        "body": {"direction": "vertical", "elements": elements},
    }


def card_fits_budget(
    base_title: str,
    subtitle: str,
    elements: list[dict[str, Any]],
    part_idx: int,
    total_parts: int,
    max_payload_bytes: int = DEFAULT_PAYLOAD_BYTES,
    max_elements: int = ELEMENT_BUDGET,
) -> bool:
    total_elements = sum(count_elements(el) for el in elements)
    if total_elements > max_elements:
        return False
    card = build_card_dict(base_title, subtitle, elements, part_idx, total_parts)
    envelope_bytes = estimate_request_envelope_bytes(card)
    return envelope_bytes <= max_payload_bytes


def news_badge(value: str) -> str:
    return re.sub(r"^\d{4}-", "", extract_badge(value))


def _render_single_news_block(item: DigestItem, language: str = "zh-CN", suffix: str = "") -> dict[str, Any]:
    """Render a single news item box with linked heading left/date right, and separate body."""
    title_text = item.title + (f" {suffix}" if suffix else "")
    if item.url and not item.title.startswith("["):
        title_link = f"[{title_text}]({item.url})"
    else:
        title_link = title_text

    left_md = md(f'<text_tag color="blue">N-{item.number:02d}</text_tag> **{title_link}**')
    right_md = md(f'<text_tag color="neutral">{news_badge(item.badge)}</text_tag>', align="right") if item.badge else md("")
    header_row = two_col(left_md, right_md, weights=(7, 1))

    children: list[dict[str, Any]] = [header_row]

    if item.facts:
        children.append(md(item.facts))

    if item.why:
        why_label = "为何重要" if language == "zh-CN" else "Why it matters"
        children.append(md(f'<font color="grey">{why_label}：{item.why}</font>'))

    src_rendered = render_sources(item.sources, language=language)
    if src_rendered:
        children.append(md(src_rendered))

    return box(children, BG_NEWS)


def _wire_text_bytes(text: str) -> int:
    encoded = json.dumps(json.dumps(text, ensure_ascii=False), ensure_ascii=False)
    return len(encoded.encode("utf-8")) - 6


def _split_text_to_fit(text: str, max_bytes: int) -> list[str]:
    """Split losslessly without breaking a source URL or Markdown link."""
    if max_bytes < 1:
        raise ValueError("No space remains for card content")
    if not text:
        return [""]
    atomic = re.compile(r"\[[^\]\n]*\]\(https?://[^)\s]+\)|https?://[^\s<>)]+")
    chunks: list[str] = []
    current: list[str] = []
    size = 0

    def append(piece: str) -> None:
        nonlocal size, current
        length = _wire_text_bytes(piece)
        if length > max_bytes:
            raise ValueError("Cannot preserve an atomic source link within the card budget")
        if size + length > max_bytes:
            chunks.append("".join(current))
            current = []
            size = 0
        current.append(piece)
        size += length

    position = 0
    for match in atomic.finditer(text):
        for character in text[position:match.start()]:
            append(character)
        append(match.group())
        position = match.end()
    for character in text[position:]:
        append(character)
    if current:
        chunks.append("".join(current))
    return chunks


def _split_overlarge_news_item(
    item: DigestItem,
    language: str,
    max_payload_bytes: int,
) -> list[dict[str, Any]]:
    """Split an overlarge news item by paragraph / character boundaries without losing facts, why, or sources."""
    # Validate atomic source links first
    for s in item.sources:
        atomic_link = f"[{s.name}]({s.url})"
        if len(atomic_link.encode("utf-8")) > max_payload_bytes - 2000:
            raise ValueError(f"Cannot preserve atomic source link within card budget: {s.url}")

    card_overhead = 2200
    safe_content_bytes = max(800, max_payload_bytes - card_overhead)

    facts = item.facts or ""
    why = item.why or ""
    src_rendered = render_sources(item.sources, language=language)
    src_bytes = len(src_rendered.encode("utf-8")) if src_rendered else 0

    why_label = "为何重要" if language == "zh-CN" else "Why it matters"
    why_prefix = f'<font color="grey">{why_label}：'
    why_suffix = '</font>'
    why_overhead = len((why_prefix + why_suffix).encode("utf-8"))

    # Determine why chunks if why is present
    why_chunks: list[str] = []
    if why:
        avail_for_why = max(400, safe_content_bytes - why_overhead)
        why_chunks = _split_text_to_fit(why, avail_for_why)

    # Determine facts chunks
    facts_chunks = _split_text_to_fit(facts, safe_content_bytes) if facts else [""]

    box_specs: list[dict[str, Any]] = []

    for idx, f_chunk in enumerate(facts_chunks):
        is_last_fact = (idx == len(facts_chunks) - 1)
        if not is_last_fact or not why_chunks:
            box_specs.append({"facts": f_chunk, "why": "", "sources": src_rendered if (is_last_fact and not why_chunks) else ""})
        else:
            f_bytes = len(f_chunk.encode("utf-8"))
            w_bytes = len(why_chunks[0].encode("utf-8")) + why_overhead
            if f_bytes + w_bytes + src_bytes <= safe_content_bytes and len(why_chunks) == 1:
                box_specs.append({"facts": f_chunk, "why": why_chunks[0], "sources": src_rendered})
            else:
                box_specs.append({"facts": f_chunk, "why": "", "sources": ""})
                for w_idx, w_chunk in enumerate(why_chunks):
                    is_last_why = (w_idx == len(why_chunks) - 1)
                    w_suffix = f" ({w_idx+1}/{len(why_chunks)})" if len(why_chunks) > 1 else ""
                    box_specs.append({
                        "facts": "",
                        "why": w_chunk,
                        "why_suffix": w_suffix,
                        "sources": src_rendered if is_last_why else "",
                    })

    total_boxes = len(box_specs)
    result_boxes: list[dict[str, Any]] = []

    for i, spec in enumerate(box_specs, 1):
        suffix = f"({i}/{total_boxes})" if total_boxes > 1 else ""
        title_text = item.title + (f" {suffix}" if suffix else "")
        if item.url and not item.title.startswith("["):
            title_link = f"[{title_text}]({item.url})"
        else:
            title_link = title_text

        left_md = md(f'<text_tag color="blue">N-{item.number:02d}</text_tag> **{title_link}**')
        right_md = md(f'<text_tag color="neutral">{news_badge(item.badge)}</text_tag>', align="right") if item.badge else md("")
        header_row = two_col(left_md, right_md, weights=(7, 1))

        children: list[dict[str, Any]] = [header_row]
        if spec.get("facts"):
            children.append(md(spec["facts"]))
        if spec.get("why"):
            w_suf = spec.get("why_suffix", "")
            children.append(md(f'<font color="grey">{why_label}{w_suf}：{spec["why"]}</font>'))
        if spec.get("sources"):
            children.append(md(spec["sources"]))

        result_boxes.append(box(children, BG_NEWS))

    return result_boxes


def _render_thread_subblocks(
    t: ThreadView,
    language: str,
    max_payload_bytes: int,
    base_title: str,
    subtitle: str,
) -> list[dict[str, Any]]:
    """Keep a Thread together, splitting only at the request or component limit."""
    latest_label = "最新进展" if language == "zh-CN" else "Latest developments"
    history_label = "历史时间线" if language == "zh-CN" else "Historical timeline"
    comment_label = "点评" if language == "zh-CN" else "Comment"
    watch_label = "下一步观察" if language == "zh-CN" else "Watch next"
    safe_text_bytes = max(1000, max_payload_bytes - 3000)
    sections: list[tuple[str, list[dict[str, Any]]]] = []

    def heading(continuation: bool) -> dict[str, Any]:
        suffix = " (续)" if continuation else ""
        return md(f'<text_tag color="orange">T-{t.number:02d}</text_tag> **{t.name}{suffix}**')

    def fits(children: list[dict[str, Any]]) -> bool:
        return card_fits_budget(
            base_title, subtitle, [box([heading(True), *children], BG_THREAD)],
            99, 99, max_payload_bytes=max_payload_bytes,
        )

    if t.progress:
        for progress in t.progress:
            title = f"[{progress.title}]({progress.url})" if progress.url else progress.title
            if progress.news_number:
                title += f" · N-{progress.news_number:02d}"
            date = progress.badge or progress.date
            progress_header = two_col(
                md(f"• {title}"),
                md(f'<text_tag color="neutral">{date}</text_tag>', align="right") if date else md(""),
            )
            fields = [
                (progress.facts or "", ""),
                (progress.comment or "", comment_label),
                (render_sources(progress.sources, language=language), ""),
            ]
            children = [progress_header]
            for value, label in fields:
                if value:
                    children.append(md(f'<font color="grey">{label}：{value}</font>' if label else value))
            if fits([md(f"**{latest_label}**"), *children]):
                sections.append((latest_label, children))
            else:
                for value, label in fields:
                    if not value:
                        continue
                    for chunk in _split_text_to_fit(value, safe_text_bytes):
                        body = f'<font color="grey">{label}：{chunk}</font>' if label else chunk
                        sections.append((latest_label, [progress_header, md(body)]))
    else:
        message = "本轮暂无可核验新增。" if language == "zh-CN" else "No verified update in this scan."
        if t.latest_state:
            label = "最新状态" if language == "zh-CN" else "Latest known state"
            message += f"\n\n{label}：{t.latest_state}"
        if t.follow:
            message += f"\n\n{watch_label}：{t.follow}"
        for chunk in _split_text_to_fit(message, safe_text_bytes):
            sections.append((latest_label, [md(chunk)]))

    if t.timeline:
        for entry in t.timeline:
            title = f"• [{entry.title}]({entry.url})" if entry.url else f"• {entry.title}"
            date = entry.badge or entry.date
            row = two_col(
                md(title),
                md(f'<text_tag color="neutral">{date}</text_tag>' if date else "", align="right"),
            )
            sections.append((history_label, [row]))
    else:
        message = (
            "尚无已核定日期的重要节点，全量报道档案仍保留。"
            if language == "zh-CN" else "No verified milestone dates yet; full archive is retained."
        )
        sections.append((history_label, [md(message)]))

    blocks: list[dict[str, Any]] = []
    children: list[dict[str, Any]] = []
    current_label = None
    for label, elements in sections:
        addition = elements if label == current_label else [md(f"**{label}**"), *elements]
        if children and not fits([*children, *addition]):
            blocks.append(box([heading(bool(blocks)), *children], BG_THREAD))
            children = []
            addition = [md(f"**{label}**"), *elements]
        if not fits(addition):
            raise ValueError("Cannot preserve an atomic Thread entry within the card budget")
        children.extend(addition)
        current_label = label
    if children:
        blocks.append(box([heading(bool(blocks)), *children], BG_THREAD))
    return blocks

def _build_action_footer(actions: list[str], language: str = "zh-CN") -> list[dict[str, Any]]:
    actions_label = "💡 **可继续操作**" if language == "zh-CN" else "💡 **Available Actions**"
    return [
        section_header(actions_label),
        box([md("\n".join(actions))], BG_OPS),
    ]


def render_card_bundle(
    markdown: str,
    *,
    max_payload_bytes: int = DEFAULT_PAYLOAD_BYTES,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render a digest document into a Feishu Schema 2.0 card bundle strictly respecting payload budgets."""
    doc = parse_digest(markdown, snapshot=snapshot)
    base_title = doc.title or ("Skrya 日报" if doc.language == "zh-CN" else "Skrya Daily Briefing")
    subtitle = doc.subtitle
    if estimate_request_envelope_bytes(build_card_dict(base_title, subtitle, [], 99, 99)) > max_payload_bytes:
        raise ValueError("Card header exceeds the request budget")

    # Build atomic components
    components: list[dict[str, Any]] = []

    # Scan interval & Lead intro
    if doc.scan_interval:
        scan_label = "扫描时间范围" if doc.language == "zh-CN" else "Scan window"
        sep = "：" if doc.language == "zh-CN" else ": "
        components.append(md(f'<font color="grey">{scan_label}{sep}{doc.scan_interval}</font>'))
    if doc.lead:
        components.append(md(f'<font color="grey">{doc.lead}</font>'))

    # Threads
    if doc.threads:
        th_label = "📌 **持续追踪**" if doc.language == "zh-CN" else "📌 **Event Timeline Updates**"
        components.append(section_header(th_label))
        for t in doc.threads:
            t_subblocks = _render_thread_subblocks(t, doc.language, max_payload_bytes, base_title, subtitle)
            for sb in t_subblocks:
                components.append(sb)
    # News
    if doc.items:
        news_label = "📰 **今日简讯**" if doc.language == "zh-CN" else "📰 **Today's Briefs**"
        components.append(section_header(news_label))
        for item in doc.items:
            news_box = _render_single_news_block(item, language=doc.language)
            # Check if this single news box fits envelope budget by itself
            test_card = build_card_dict(base_title, subtitle, [news_box], 1, 99)
            if estimate_request_envelope_bytes(test_card) <= max_payload_bytes:
                components.append(news_box)
            else:
                # Decompose overlarge news item
                split_boxes = _split_overlarge_news_item(item, doc.language, max_payload_bytes)
                components.extend(split_boxes)

    # Actions footer
    if doc.actions:
        components.extend(_build_action_footer(doc.actions, language=doc.language))

    # Attempt single card first
    if card_fits_budget(base_title, subtitle, components, part_idx=1, total_parts=1, max_payload_bytes=max_payload_bytes, max_elements=ELEMENT_BUDGET):
        single_card = build_card_dict(base_title, subtitle, components, part_idx=1, total_parts=1)
        return {
            "interface_version": "skrya.card-bundle.v1",
            "cards": [single_card],
            "total_cards": 1,
            "title": base_title,
        }

    # Greedily pack components into cards
    packed_card_element_groups: list[list[dict[str, Any]]] = []
    current_group: list[dict[str, Any]] = []

    # Reserve 64 bytes in envelope for title (i/n) suffix during greedy packing
    packing_budget_bytes = max_payload_bytes - 64

    for comp in components:
        candidate = current_group + [comp]
        candidate_card = build_card_dict(base_title, subtitle, candidate, 99, 99)
        c_elements = sum(count_elements(el) for el in candidate)
        c_bytes = estimate_request_envelope_bytes(candidate_card)

        if c_elements <= ELEMENT_BUDGET and c_bytes <= packing_budget_bytes:
            current_group.append(comp)
        else:
            if current_group:
                packed_card_element_groups.append(current_group)
                current_group = []

            # Check if comp fits alone
            solo_card = build_card_dict(base_title, subtitle, [comp], 99, 99)
            solo_elements = count_elements(comp)
            solo_bytes = estimate_request_envelope_bytes(solo_card)
            if solo_elements <= ELEMENT_BUDGET and solo_bytes <= packing_budget_bytes:
                current_group.append(comp)
            else:
                # Component alone exceeds budget even after prior decomposition
                # As a last resort, if component is a box with elements, split elements
                if "columns" in comp and comp["columns"] and "elements" in comp["columns"][0]:
                    inner_elements = comp["columns"][0]["elements"]
                    box_bg = comp.get("background_style", BG_NEWS)
                    safe_content_bytes = max(800, max_payload_bytes - 2200)
                    expanded_inners: list[dict[str, Any]] = []
                    for in_el in inner_elements:
                        if in_el.get("tag") == "markdown" and len(in_el.get("content", "").encode("utf-8")) > safe_content_bytes:
                            for ch_t in _split_text_to_fit(in_el["content"], safe_content_bytes):
                                expanded_inners.append(md(ch_t, align=in_el.get("text_align")))
                        else:
                            expanded_inners.append(in_el)

                    cur_inner: list[dict[str, Any]] = []
                    for in_el in expanded_inners:
                        test_box = box(cur_inner + [in_el], box_bg)
                        if (
                            count_elements(test_box) <= ELEMENT_BUDGET
                            and estimate_request_envelope_bytes(build_card_dict(base_title, subtitle, [test_box], 99, 99))
                            <= packing_budget_bytes
                        ):
                            cur_inner.append(in_el)
                        else:
                            if cur_inner:
                                packed_card_element_groups.append([box(cur_inner, box_bg)])
                                cur_inner = []
                            cur_inner.append(in_el)
                    if cur_inner:
                        current_group.append(box(cur_inner, box_bg))
                else:
                    current_group.append(comp)

    if current_group:
        packed_card_element_groups.append(current_group)

    # Post-check final cards with exact part_idx and total_parts
    repack = True
    while repack:
        repack = False
        total_parts = len(packed_card_element_groups)
        for idx in range(total_parts):
            grp = packed_card_element_groups[idx]
            card = build_card_dict(base_title, subtitle, grp, part_idx=idx + 1, total_parts=total_parts)
            if (
                estimate_request_envelope_bytes(card) > max_payload_bytes
                or sum(count_elements(el) for el in grp) > ELEMENT_BUDGET
            ):
                if len(grp) > 1:
                    overflow_item = grp.pop()
                    if idx + 1 < len(packed_card_element_groups):
                        packed_card_element_groups[idx + 1].insert(0, overflow_item)
                    else:
                        packed_card_element_groups.append([overflow_item])
                    repack = True
                    break
                else:
                    # Single component alone exceeds budget: decompose inner box
                    over_comp = grp[0]
                    if "columns" in over_comp and over_comp["columns"] and "elements" in over_comp["columns"][0]:
                        inner = over_comp["columns"][0]["elements"]
                        bg = over_comp.get("background_style", BG_NEWS)
                        if len(inner) > 1:
                            mid = len(inner) // 2
                            box1 = box(inner[:mid], bg)
                            box2 = box(inner[mid:], bg)
                            packed_card_element_groups[idx] = [box1]
                            if idx + 1 < len(packed_card_element_groups):
                                packed_card_element_groups[idx + 1].insert(0, box2)
                            else:
                                packed_card_element_groups.append([box2])
                            repack = True
                            break
                        elif len(inner) == 1 and inner[0].get("tag") == "markdown":
                            txt = inner[0]["content"]
                            chunks = _split_text_to_fit(txt, len(txt.encode("utf-8")) // 2)
                            if len(chunks) < 2:
                                raise ValueError("Card component cannot fit the request budget")
                            box1 = box([md(chunks[0])], bg)
                            box2 = box([md("".join(chunks[1:]))], bg)
                            packed_card_element_groups[idx] = [box1]
                            if idx + 1 < len(packed_card_element_groups):
                                packed_card_element_groups[idx + 1].insert(0, box2)
                            else:
                                packed_card_element_groups.append([box2])
                            repack = True
                            break

    total_parts = len(packed_card_element_groups)
    final_cards: list[dict[str, Any]] = []

    for idx, grp in enumerate(packed_card_element_groups, 1):
        card = build_card_dict(base_title, subtitle, grp, part_idx=idx, total_parts=total_parts)
        env_bytes = estimate_request_envelope_bytes(card)
        if env_bytes > max_payload_bytes:
            raise ValueError(
                f"Card {idx}/{total_parts} envelope ({env_bytes} bytes) exceeds limit ({max_payload_bytes} bytes)"
            )
        el_count = sum(count_elements(el) for el in card["body"]["elements"])
        if el_count > ELEMENT_BUDGET:
            raise ValueError(
                f"Card {idx}/{total_parts} element count ({el_count}) exceeds limit ({ELEMENT_BUDGET})"
            )
        final_cards.append(card)
    return {
        "interface_version": "skrya.card-bundle.v1",
        "cards": final_cards,
        "total_cards": len(final_cards),
        "title": base_title,
    }


def summary_markdown(markdown: str, limit: int = 5) -> str:
    """Generate concise summary markdown for root thread message in summary+thread mode."""
    doc = parse_digest(markdown)
    is_cn = doc.language == "zh-CN"

    lines: list[str] = [f"# {doc.title}"]

    if doc.scan_interval:
        scan_label = "扫描时间范围" if is_cn else "Scan window"
        sep = "：" if is_cn else ": "
        lines.append(f"\n{scan_label}{sep}{doc.scan_interval}")

    lines.append("")

    items_to_show = doc.items[:limit]
    if items_to_show:
        for it in items_to_show:
            first_sentence = ""
            if it.facts:
                clean_facts = " ".join(it.facts.splitlines()).strip()
                if is_cn:
                    first_sentence = clean_facts.split("。")[0].strip()
                else:
                    first_sentence = clean_facts.split(".")[0].strip()
            if first_sentence and first_sentence != it.title:
                sep = "：" if is_cn else ": "
                punct = "。" if is_cn else "."
                lines.append(f"- **N-{it.number:02d}** {it.title}{sep}{first_sentence}{punct}")
            else:
                lines.append(f"- **N-{it.number:02d}** {it.title}")
    else:
        if doc.threads:
            msg = (
                "- 持续追踪事件线已有最新研判与历史时间线更新。"
                if is_cn
                else "- Event tracking threads have verified updates and historical timeline records."
            )
            lines.append(msg)
        else:
            msg = "- 本期暂无可核验简讯。" if is_cn else "- No verified brief items in this scan window."
            lines.append(msg)

    lines.append("")
    indication = (
        "💬 完整简报与事件线见本条回复。"
        if is_cn
        else "💬 Full briefing and event timelines are available in the reply thread."
    )
    lines.append(indication)

    return "\n".join(lines).strip() + "\n"


