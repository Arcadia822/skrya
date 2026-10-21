from __future__ import annotations

import json
from typing import Any, Iterator
import unittest

from skrya_orchestrator.digest_document import (
    DigestDocument,
    DigestItem,
    Milestone,
    ThreadProgress,
    ThreadView,
    detect_language,
    parse_digest,
    parse_threads,
)
from skrya_orchestrator.feishu_cards import (
    DEFAULT_PAYLOAD_BYTES,
    ELEMENT_BUDGET,
    count_elements,
    estimate_request_envelope_bytes,
    render_card_bundle,
    summary_markdown,
)
from skrya_orchestrator.sources import parse_sources


def extract_markdown_texts(element: dict[str, Any]) -> Iterator[str]:
    if element.get("tag") == "markdown":
        yield element.get("content", "")
    for col in element.get("columns", []):
        yield from extract_markdown_texts(col)
    for sub in element.get("elements", []):
        yield from extract_markdown_texts(sub)


class TestFeishuCards(unittest.TestCase):
    def test_one_thread_keeps_progress_and_history_together_until_capacity_requires_split(self):
        for progress in ("- **2026-10-19** · [Update](https://example.org/update)\nVerified progress.", "No verified update in this scan.\nLatest known state: Approved."):
            markdown = f"# Daily briefing\n\n## Event Timeline Updates\n\n### T-01 Project\n\n**Latest developments**:\n{progress}\n\n**Historical timeline**:\n- [Start](https://example.org/start) ｜ 2025-01-02\n"
            cards = render_card_bundle(markdown)["cards"]
            blocks = [element for card in cards for element in card["body"]["elements"] if element.get("background_style") == "yellow-50"]
            self.assertEqual(1, len(blocks))
            text = "\n".join(extract_markdown_texts(blocks[0]))
            self.assertEqual(1, text.count("T-01"))
            self.assertIn("Latest developments", text)
            self.assertIn("Historical timeline", text)
            self.assertIn("https://example.org/start", text)
            self.assertIn("2025-01-02", text)
            self.assertNotIn("(续)", text)

    def test_news_badges_use_month_day_time_without_changing_history(self):
        for size in (1, 16000):
            for date, expected in (("2026-10-18T08:35:27+08:00", "10-18 08:35"), ("2026-10-19", "10-19")):
                markdown = f"# Daily briefing\n\n## Event Timeline Updates\n\n### T-01 Project\n\n**Latest developments**:\nNo verified update in this scan.\n\n**Historical timeline**:\n- [Start](https://example.org/start) ｜ 2025-01-02\n\n## Today's Briefs\n\n### N-01 Report ｜ {date}\n{'fact ' * size}\nSources: [Original](https://example.org/report)\n"
                cards = render_card_bundle(markdown)["cards"]
                news = []
                history = []
                for card in cards:
                    for element in card["body"]["elements"]:
                        texts = list(extract_markdown_texts(element))
                        if element.get("background_style") == "blue-50":
                            news.extend(texts)
                        elif element.get("background_style") == "yellow-50":
                            history.extend(texts)
                badges = [part for part in news if '<text_tag color="neutral">' in part]
                self.assertTrue(badges)
                self.assertTrue(all(f">{expected}</text_tag>" in badge for badge in badges))
                self.assertIn("2025-01-02", "".join(history))
                self.assertEqual(date[:10], parse_digest(markdown).items[0].date[:10])

    def test_split_preserves_inline_source_links_and_rejects_impossible_budget(self):
        link = "[Original report](https://example.org/" + "source" * 90 + ")"
        facts = ("a" * 17500 + link) * 3
        markdown = f"# Daily briefing\n\n## Today's Briefs\n\n### N-01 Report ｜ 2026-10-19\n{facts}\nWhy it matters: decision\nSources: [Media](https://example.org/media)\n"
        cards = render_card_bundle(markdown)["cards"]
        texts = [text for card in cards for element in card["body"]["elements"] for text in extract_markdown_texts(element)]
        self.assertEqual(3, sum(text.count(link) for text in texts))
        self.assertTrue(all(estimate_request_envelope_bytes(card) <= DEFAULT_PAYLOAD_BYTES for card in cards))
        with self.assertRaises(ValueError):
            render_card_bundle(markdown, max_payload_bytes=100)

    def test_historical_rows_split_by_wire_budget_and_keep_links_dates_and_thread(self):
        urls = [f"https://example.org/{i}/" + "source" * 340 for i in range(12)]
        rows = "\n".join(f"- [Milestone {i}]({url}) ｜ 2025-10-{i+1:02d}" for i, url in enumerate(urls))
        markdown = f"# Daily briefing\n\n## Event Timeline Updates\n\n### T-01 Regulation\n\n**Latest developments**:\nNo verified update in this scan.\n\n**Historical timeline**:\n{rows}\n"
        cards = render_card_bundle(markdown)["cards"]
        retained = []
        for card in cards:
            self.assertLessEqual(estimate_request_envelope_bytes(card), DEFAULT_PAYLOAD_BYTES)
            for element in card["body"]["elements"]:
                texts = list(extract_markdown_texts(element))
                if any(url in text for url in urls for text in texts):
                    self.assertIn("T-01", "".join(texts))
                    retained.extend(texts)
        for i, url in enumerate(urls):
            self.assertEqual(1, sum(text.count(url) for text in retained))
            self.assertIn(f"2025-10-{i+1:02d}", "".join(retained))

    def test_plain_markdown_news_heading_uses_its_source_link(self):
        cards = render_card_bundle("# Daily briefing\n\n## Today's Briefs\n\n### N-01 Decision\nFacts.\nSources: [Original](https://example.org/original)\n")["cards"]
        text = "\n".join(text for card in cards for element in card["body"]["elements"] for text in extract_markdown_texts(element))
        self.assertIn("[Decision](https://example.org/original)", text)

    def test_thread_comment_and_next_watch_continuations_keep_identity_and_formatting(self):
        for field in ("comment", "watch"):
            with self.subTest(field=field):
                text = ('Ω"\\\\' * 17000)
                progress = f"- **2026-10-19** · [Decision](https://example.org/new) · N-01\nShort facts.\nComment: {text}" if field == "comment" else f"No verified update in this scan.\nLatest known state: Approved.\nWatch next: {text}"
                markdown = f"# Daily briefing\n\n## Event Timeline Updates\n\n### T-01 Regulation\n\n**Latest developments**:\n{progress}\n\n**Historical timeline**:\nNo verified milestones.\n"
                cards = render_card_bundle(markdown)["cards"]
                found = []
                for card in cards:
                    for element in card["body"]["elements"]:
                        if element.get("background_style") != "yellow-50":
                            continue
                        texts = list(extract_markdown_texts(element))
                        if any('Ω' in part for part in texts):
                            self.assertIn("T-01", "".join(texts))
                            found.extend(texts)
                            for part in texts:
                                self.assertEqual(part.count('<font '), part.count('</font>'))
                    self.assertLessEqual(estimate_request_envelope_bytes(card), DEFAULT_PAYLOAD_BYTES)
                self.assertEqual(17000, "".join(found).count('Ω'))

    def test_render_card_bundle_basic(self) -> None:
        content = """# 2026-10-19｜AI 浏览器｜每日简报

扫描时间范围：2026-10-18 00:00 至 2026-10-19 00:00 UTC。

## 事件线时间线更新

### T-01 企业级智能体竞逐

**最新进展**：
- **2026-10-19 08:30** · [Comet 正式上线企业代理](https://example.com/comet) · N-01
Comet 增加了用于多步骤浏览任务的企业代理模式。
点评：对传统桌面企业工作流产生直接冲击。

**历史时间线**：
- [最初发布预览版](https://example.com/preview) ｜ 2026-04-01

## 今日简讯

### N-01 Comet 扩展企业部署 ｜ 2026-10-19 08:30
Comet 增加了用于多步骤浏览任务的企业代理模式，支持跨标签页协同。
为何重要：多步骤代理从玩具演变为生产力工具。
信源：[官方博客](https://example.com/blog) | [路透社](https://example.com/reuters)

---

### N-02 某搜索巨头跟进推出自主代理架构 ｜ 2026-10-19 11:20
搜索巨头公布了自主代理架构，集成端侧多模态模型。
为何重要：底层基模与浏览器环境结合日益紧密。
信源：[科技媒体](https://example.com/tech)

## 可继续操作

- 回复 `dig: N-01`，展开指定新闻的深度分析与专家级背景研判。
- 回复 `track: N-02`，为指定事件建立持续追踪线。
- 回复 `dig: T-01`，查看事件线的全量历史脉络。
- 回复 `write: T-01`，把这一系列事件写成有来源的文章草稿，不自动发布。
- 自然语言反馈，例如增加涉华舆情分析或减少例行口水争端。
"""
        bundle = render_card_bundle(content)
        self.assertEqual(bundle["interface_version"], "skrya.card-bundle.v1")
        self.assertIsInstance(bundle["cards"], list)
        self.assertGreaterEqual(len(bundle["cards"]), 1)

        first_card = bundle["cards"][0]
        self.assertEqual(first_card["schema"], "2.0")
        self.assertEqual(first_card["header"]["template"], "blue")
        self.assertTrue(first_card["config"]["update_multi"])
        self.assertIn("2026-10-19｜AI 浏览器｜每日简报", first_card["header"]["title"]["content"])

        env_bytes = estimate_request_envelope_bytes(first_card)
        self.assertLessEqual(env_bytes, DEFAULT_PAYLOAD_BYTES)
        elems_count = sum(count_elements(el) for el in first_card["body"]["elements"])
        self.assertLessEqual(elems_count, ELEMENT_BUDGET)

        all_text = " ".join(extract_markdown_texts(first_card["body"]))
        self.assertIn("T-01", all_text)
        self.assertIn("N-01", all_text)
        self.assertIn("N-02", all_text)
        self.assertIn("dig: N-01", all_text)
        self.assertIn("write: T-01", all_text)

    def test_payload_completeness_no_truncation(self) -> None:
        long_facts = "这是一段非常详尽的事实描述，包含关键主体、各方行动、具体数据以及详细时间表，绝不应在渲染时被任何截断算法省略或打省略号。" * 3
        long_why = "这是一段深入的研判分析，详细阐述了该事件对行业格局和技术路线的深远影响，保持完整呈现。" * 2
        content = f"""# 2026-10-19｜完整性测试｜每日简报

## 今日简讯

### N-01 关键技术突破 ｜ 2026-10-19 15:00
{long_facts}
为何重要：{long_why}
信源：[技术报告](https://example.org/report) | [权威期刊](https://example.org/journal)
"""
        bundle = render_card_bundle(content)
        card = bundle["cards"][0]
        all_text = " ".join(extract_markdown_texts(card["body"]))

        self.assertIn(long_facts, all_text)
        self.assertIn(long_why, all_text)
        self.assertIn("https://example.org/report", all_text)
        self.assertIn("https://example.org/journal", all_text)

    def test_constraints_and_budget_splitting_40_items(self) -> None:
        items_md = []
        for i in range(1, 41):
            items_md.append(f"""### N-{i:02d} 第 {i} 项重要事件标题 ｜ 2026-10-19 10:{i % 60:02d}
第 {i} 条事件的事实描述正文，详细记录了事件发生的过程与细节数据。
为何重要：评估该事件在全局中的定位与长期潜在价值。
信源：[媒体{i}](https://example.org/news/{i})
""")

        content = "# 2026-10-19｜40条超长简报｜每日简报\n\n## 今日简讯\n\n" + "\n---\n\n".join(items_md)
        bundle = render_card_bundle(content)

        self.assertEqual(bundle["interface_version"], "skrya.card-bundle.v1")
        cards = bundle["cards"]
        self.assertGreater(len(cards), 1, "40 items must split across multiple cards to fit payload budgets")

        total_parts = len(cards)
        all_card_text = ""
        for idx, card in enumerate(cards, 1):
            env_bytes = estimate_request_envelope_bytes(card)
            self.assertLessEqual(env_bytes, DEFAULT_PAYLOAD_BYTES, f"Card {idx}/{total_parts} exceeded envelope budget")
            elem_count = sum(count_elements(el) for el in card["body"]["elements"])
            self.assertLessEqual(elem_count, ELEMENT_BUDGET, f"Card {idx}/{total_parts} exceeded element budget")

            self.assertIn(f"({idx}/{total_parts})", card["header"]["title"]["content"])
            all_card_text += " " + " ".join(extract_markdown_texts(card["body"]))

        for i in range(1, 41):
            self.assertIn(f"N-{i:02d}", all_card_text, f"Item N-{i:02d} vanished during card splitting")
            self.assertIn(f"https://example.org/news/{i}", all_card_text)

    def test_huge_one_thread_block_splitting_repeats_entity_badge(self) -> None:
        milestones_md = []
        for i in range(1, 35):
            milestones_md.append(f"- [重大历史节点 {i}](https://example.org/milestone/{i}) ｜ 2026-01-{i % 28 + 1:02d}")

        content = f"""# 2026-10-19｜超大事件线测试｜每日简报

## 事件线时间线更新

### T-01 跨年度核心调查线

**最新进展**：
- **2026-10-19 09:00** · [最新关键口供曝光](https://example.org/progress) · N-01
核心证人提供了关键笔录，案件出现重大转折。
点评：诉讼流程进入实质审查阶段。

**历史时间线**：
""" + "\n".join(milestones_md) + """

## 今日简讯

### N-01 最新关键口供曝光 ｜ 2026-10-19 09:00
核心证人提供了关键笔录，案件出现重大转折。
为何重要：实质审查加速。
信源：[法制网](https://example.org/legal)
"""
        bundle = render_card_bundle(content)
        cards = bundle["cards"]
        all_card_text = " ".join(" ".join(extract_markdown_texts(c["body"])) for c in cards)

        self.assertIn("T-01", all_card_text)
        for i in range(1, 35):
            self.assertIn(f"https://example.org/milestone/{i}", all_card_text)

        for card in cards:
            self.assertLessEqual(estimate_request_envelope_bytes(card), DEFAULT_PAYLOAD_BYTES)
            self.assertLessEqual(sum(count_elements(el) for el in card["body"]["elements"]), ELEMENT_BUDGET)

    def test_overlarge_paragraph_character_split(self) -> None:
        huge_paragraph = "这是一段极长的新闻事实正文，包含不可压缩的专业技术细节。" * 350
        content = f"""# 2026-10-19｜巨型段落测试｜每日简报

## 今日简讯

### N-01 超长专报条目 ｜ 2026-10-19 12:00
{huge_paragraph}
为何重要：超长段落不应导致解析失败或整条丢失。
信源：[权威来源](https://example.org/huge)
"""
        bundle = render_card_bundle(content)
        cards = bundle["cards"]
        self.assertGreater(len(cards), 1)

        for idx, card in enumerate(cards):
            self.assertLessEqual(
                estimate_request_envelope_bytes(card),
                DEFAULT_PAYLOAD_BYTES,
                f"Card {idx} exceeded envelope budget",
            )
            self.assertLessEqual(
                sum(count_elements(el) for el in card["body"]["elements"]),
                ELEMENT_BUDGET,
                f"Card {idx} exceeded element budget",
            )

        card_text_blocks = []
        for c in cards:
            for text in extract_markdown_texts(c["body"]):
                if "这是一段极长的新闻事实正文" in text:
                    card_text_blocks.append(text)
        self.assertEqual("".join(card_text_blocks), huge_paragraph)

        all_card_text = " ".join(" ".join(extract_markdown_texts(c["body"])) for c in cards)
        self.assertIn("N-01", all_card_text)
        self.assertIn("https://example.org/huge", all_card_text)
        self.assertIn("超长段落不应导致解析失败", all_card_text)
    def test_impossible_to_fit_link_raises_explicit_error(self) -> None:
        impossible_url = "https://example.org/" + ("a" * 25000)
        content = f"""# 2026-10-19｜超大链接｜每日简报

## 今日简讯

### N-01 链接超限条目 ｜ 2026-10-19 12:00
事实内容。
为何重要：核心影响。
信源：[超长链接]({impossible_url})
"""
        with self.assertRaises(ValueError) as ctx:
            render_card_bundle(content)
        self.assertIn("Cannot preserve atomic source link", str(ctx.exception))

    def test_legacy_checkbox_archive_parsing(self) -> None:
        content = """# 2026-10-15｜X1 项目｜涉军速览
## 一、热点舆情
### ☐ 1｜新制度发布
**摘要**：主管部门发布正式制度。
**价值点**：实施范围发生变化。
**信源**：[官方](https://example.org/rule)（10-15 09:16）
### ☐ 2｜执行细则生效
**摘要**：执行细则于10-15正式生效。
**价值点**：程序开始实施。
**信源**：[公告](https://example.org/implementation)
"""
        doc = parse_digest(content)
        self.assertEqual([item.title for item in doc.items], ["新制度发布", "执行细则生效"])
        self.assertEqual(
            [item.facts for item in doc.items],
            ["主管部门发布正式制度。", "执行细则于10-15正式生效。"],
        )
        self.assertEqual([item.why for item in doc.items], ["实施范围发生变化。", "程序开始实施。"])
        self.assertEqual(
            [item.sources[0].url for item in doc.items],
            ["https://example.org/rule", "https://example.org/implementation"],
        )
        self.assertEqual(doc.items[0].badge, "10-15 09:16")
        self.assertEqual(doc.items[1].badge, "")

        bundle = render_card_bundle(content)
        card = bundle["cards"][0]
        card_text = " ".join(extract_markdown_texts(card["body"]))
        self.assertIn("新制度发布", card_text)
        self.assertIn("执行细则生效", card_text)
        self.assertIn("10-15 09:16", card_text)

    def test_old_line_boxes_parsing(self) -> None:
        content = """# 2026-10-19 ｜ AI Browsers ｜ Daily Briefing

┌─ **【Brief 1】Comet expands enterprise rollout**
│ Comet expands enterprise rollout with multi-step workflows.
│
│ Sources: [example.com](https://example.com/comet-enterprise)
└

┌─ **【Thread】比亚迪闪充站 (byd-flash-charge-station)**
│ 今日增量：增量事实
│ 时间线位置：承接 2026-03-20 闪充协议
│ 影响判断：影响分析
│ 下一步观察：首批站点在哪些城市真正落地
└
"""
        doc = parse_digest(content)
        self.assertEqual(len(doc.items), 1)
        self.assertEqual(doc.items[0].title, "Comet expands enterprise rollout")
        self.assertEqual(doc.items[0].facts, "Comet expands enterprise rollout with multi-step workflows.")
        self.assertEqual(doc.items[0].sources[0].url, "https://example.com/comet-enterprise")

        self.assertEqual(len(doc.threads), 1)
        self.assertEqual(doc.threads[0].name, "比亚迪闪充站")
        self.assertEqual(doc.threads[0].stable_id, "byd-flash-charge-station")
        self.assertEqual(doc.threads[0].progress[0].facts, "增量事实")
        self.assertEqual(doc.threads[0].progress[0].comment, "影响分析")

        bundle = render_card_bundle(content)
        self.assertEqual(len(bundle["cards"]), 1)

    def test_source_cleaning(self) -> None:
        raw_text = (
            "信源：[原文链接](https://news.ycombinator.com/item?id=1) | "
            "[查看](https://www.reuters.com/world/1) | "
            "[*Bloomberg*](https://bloomberg.com/news/2) | "
            "[link](https://example.org/item) | "
            "[view](https://www.reuters.com/world/2)"
        )
        sources = parse_sources(raw_text)
        self.assertEqual(sources[0].name, "news.ycombinator.com")
        self.assertEqual(sources[0].url, "https://news.ycombinator.com/item?id=1")

        self.assertEqual(sources[1].name, "reuters.com")
        self.assertEqual(sources[1].url, "https://www.reuters.com/world/1")

        self.assertEqual(sources[2].name, "Bloomberg")
        self.assertEqual(sources[2].url, "https://bloomberg.com/news/2")

        self.assertEqual(sources[3].name, "example.org")
        self.assertEqual(sources[3].url, "https://example.org/item")

        self.assertEqual(sources[4].name, "reuters.com")
        self.assertEqual(sources[4].url, "https://www.reuters.com/world/2")

    def test_news_card_retains_every_link_within_source_segments(self) -> None:
        for sources in (
            "https://example.org/a https://example.org/b",
            "[A](https://example.org/a) [B](https://example.org/b) | CCTV",
        ):
            with self.subTest(sources=sources):
                markdown = (
                    "# Daily Briefing\n\n## News\n\n### N-01 Report\nFacts.\n"
                    f"Sources: {sources}\n"
                )
                doc = parse_digest(markdown)
                self.assertEqual(
                    [source.url for source in doc.items[0].sources if source.url],
                    ["https://example.org/a", "https://example.org/b"],
                )
                bundle = render_card_bundle(markdown)
                text = "\n".join(text for card in bundle["cards"] for text in extract_markdown_texts(card["body"]))
                self.assertIn("](https://example.org/a)", text)
                self.assertIn("](https://example.org/b)", text)
                if "CCTV" in sources:
                    self.assertIn("CCTV", text)

    def test_name_only_thread_progress_sources_reach_full_cards(self) -> None:
        cases = [
            (
                "# 每日简报\n\n## 事件线时间线更新\n\n### T-01 演练\n\n"
                "**最新进展**：\n演练进入新阶段\n多型舰艇开展演训。\n信源：央视军事\n",
                "演练进入新阶段 多型舰艇开展演训。",
            ),
            (
                "# Daily Briefing\n\n## Event Timeline Updates\n\n### T-01 Drill\n\n"
                "**Latest developments**:\nDrill advances\nJoint exercises continue.\nSources: CCTV\n",
                "Drill advances Joint exercises continue.",
            ),
            (
                "# 每日简报\n\n┌─ **【Thread】演练 (drill)**\n"
                "│ 今日增量：多型舰艇开展演训。\n│ 信源：央视军事\n└\n",
                "多型舰艇开展演训。",
            ),
            (
                "# 每日简报\n\n## 事件线时间线更新\n\n### T-01 演练\n\n"
                "**最新进展**：\n信源：央视军事\n",
                "",
            ),
        ]
        for markdown, facts in cases:
            with self.subTest(markdown=markdown):
                thread = parse_digest(markdown).threads[0]
                self.assertEqual(len(thread.progress), 1)
                progress = thread.progress[0]
                name = "CCTV" if "Sources: CCTV" in markdown else "央视军事"
                self.assertEqual(progress.facts, facts)
                self.assertEqual([(source.name, source.url) for source in progress.sources], [(name, "")])
                self.assertEqual(progress.url, "")
                bundle = render_card_bundle(markdown)
                text = "\n".join(text for card in bundle["cards"] for text in extract_markdown_texts(card["body"]))
                self.assertIn(name, text)
                if facts:
                    self.assertIn(facts, text)
                self.assertNotIn("](http", text)

    def test_pending_thread_sources_do_not_attach_to_later_linked_progress_or_history(self) -> None:
        markdown = (
            "# Daily Briefing\n\n## Event Timeline Updates\n\n### T-01 Drill\n\n"
            "**Latest developments**:\nPlain update.\nSources: CCTV\n"
            "- **2026-10-20** · [Linked update](https://example.org/update) · N-01\n"
            "New facts.\nSources: [Reuters](https://example.org/reuters)\n"
            "**Historical timeline**:\n"
            "- [Initial decision](https://example.org/initial) | 2025-01-02\n"
            "Sources: [Historical publisher](https://example.org/history-source)\n"
        )
        thread = parse_digest(markdown).threads[0]
        self.assertEqual(len(thread.progress), 2)
        self.assertEqual(thread.progress[0].facts, "Plain update.")
        self.assertEqual([(source.name, source.url) for source in thread.progress[0].sources], [("CCTV", "")])
        self.assertEqual(thread.progress[1].title, "Linked update")
        self.assertEqual(
            [(source.name, source.url) for source in thread.progress[1].sources],
            [("Reuters", "https://example.org/reuters")],
        )
        self.assertEqual([(entry.title, entry.url, entry.date) for entry in thread.timeline], [
            ("Initial decision", "https://example.org/initial", "2025-01-02"),
        ])
        bundle = render_card_bundle(markdown)
        text = "\n".join(text for card in bundle["cards"] for text in extract_markdown_texts(card["body"]))
        self.assertIn("CCTV", text)
        self.assertIn("[Reuters](https://example.org/reuters)", text)
        self.assertIn("[Initial decision](https://example.org/initial)", text)
        self.assertNotIn("https://example.org/history-source", text)

    def test_thread_history_requires_an_explicit_date_and_article_url(self) -> None:
        markdown = (
            "# Daily Briefing\n\n## Event Timeline Updates\n\n### T-01 Project\n\n"
            "**Latest developments**:\nNo verified update in this scan.\n"
            "**Historical timeline**:\n"
            "- [Initial decision](https://example.org/initial) | 2025-01-02\n"
            "- [Undated article](https://example.org/2024-02-03/report)\n"
            "- [Homepage](https://example.org/) | 2025-02-03\n"
            "- Date without a source | 2025-03-04\n"
            "Sources: [Publisher](https://example.org/source) | 2025-04-05\n"
        )
        thread = parse_digest(markdown).threads[0]
        self.assertEqual([(entry.title, entry.url, entry.date) for entry in thread.timeline], [
            ("Initial decision", "https://example.org/initial", "2025-01-02"),
        ])
        bundle = render_card_bundle(markdown)
        text = "\n".join(text for card in bundle["cards"] for text in extract_markdown_texts(card["body"]))
        self.assertIn("[Initial decision](https://example.org/initial)", text)
        self.assertIn("2025-01-02", text)
        self.assertNotIn("https://example.org/2024-02-03/report", text)
        self.assertNotIn("https://example.org/source", text)

    def test_no_date_handling_no_clock_fallback(self) -> None:
        content = """# 2026-10-19｜无日期新闻｜每日简报

## 今日简讯

### N-01 某项技术原则探讨
这是一篇关于纯技术哲学的讨论，不包含具体发布时刻。在 2025-06-01 该团队曾经发布过前身版本。
为何重要：探讨软件架构哲学。
信源：[探讨原文](https://example.org/essay)
"""
        doc = parse_digest(content)
        item = doc.items[0]
        # Body mentioning 2025-06-01 must not become the publication badge
        self.assertEqual(item.badge, "")
        self.assertEqual(item.date, "")
        self.assertIn("在 2025-06-01 该团队曾经发布过前身版本", item.facts)

        bundle = render_card_bundle(content)
        card = bundle["cards"][0]
        self.assertEqual(len(bundle["cards"]), 1)

    def test_thread_news_count_and_individual_summaries(self) -> None:
        content = """T-01 调查线 (investigation)
**最新进展**：
• **10-16 09:30** · [任命生效](https://example.org/appointment) · N-01
内阁通过核心人事任命。
点评：调查程序预计提速。
• **10-16 14:00** · [听证会敲定](https://example.org/hearing) · N-02
听证会定于下周举行。
点评：朝野博弈公开化。
**历史时间线**：
- [最初立案](https://example.org/open) ｜ 2026-04-01
"""
        threads = parse_threads(content)
        self.assertEqual(len(threads), 1)
        th = threads[0]
        self.assertEqual(th.name, "调查线")
        self.assertEqual(th.stable_id, "investigation")
        self.assertEqual(len(th.progress), 2)

        self.assertEqual(th.progress[0].title, "任命生效")
        self.assertEqual(th.progress[0].badge, "10-16 09:30")
        self.assertEqual(th.progress[0].facts, "内阁通过核心人事任命。")
        self.assertEqual(th.progress[0].comment, "调查程序预计提速。")
        self.assertEqual(th.progress[0].news_number, 1)

        self.assertEqual(th.progress[1].title, "听证会敲定")
        self.assertEqual(th.progress[1].badge, "10-16 14:00")
        self.assertEqual(th.progress[1].facts, "听证会定于下周举行。")
        self.assertEqual(th.progress[1].comment, "朝野博弈公开化。")
        self.assertEqual(th.progress[1].news_number, 2)

        self.assertEqual(th.refs, [1, 2])
        self.assertEqual(len(th.timeline), 1)
        self.assertEqual(th.timeline[0].title, "最初立案")
        self.assertEqual(th.timeline[0].date, "2026-04-01")

    def test_legacy_references_extraction(self) -> None:
        content = """【Thread: 安全线】(security)
见第 4、5、9、12 条
- 进展描述
"""
        threads = parse_threads(content)
        self.assertEqual(threads[0].refs, [4, 5, 9, 12])

    def test_active_thread_with_no_updates(self) -> None:
        content = """# 2026-10-19｜无增量Active Thread｜每日简报

## 事件线时间线更新

### T-01 持续基准观测线

**最新进展**：
本轮暂无可核验新增。
最新状态：2026-10-15：基准指标稳定，等待下一轮审计。
下一步观察：关注下季度财务报告披露。

**历史时间线**：
- [启动立案](https://example.org/start) ｜ 2026-03-01

## 可继续操作

- 回复 `dig: T-01`，查看事件线的全量历史脉络。
"""
        doc = parse_digest(content)
        self.assertEqual(len(doc.threads), 1)
        th = doc.threads[0]
        self.assertEqual(th.name, "持续基准观测线")
        self.assertEqual(len(th.progress), 0)
        self.assertEqual(th.latest_state, "2026-10-15：基准指标稳定，等待下一轮审计。")
        self.assertEqual(th.follow, "关注下季度财务报告披露。")

        bundle = render_card_bundle(content)
        card_text = " ".join(extract_markdown_texts(bundle["cards"][0]["body"]))
        self.assertIn("本轮暂无可核验新增", card_text)
        self.assertIn("最新状态：2026-10-15：基准指标稳定", card_text)

    def test_english_digest(self) -> None:
        content = """# 2026-10-19 | AI Browsers | Daily Briefing

Scan window: 2026-10-18 00:00 to 2026-10-19 00:00 UTC.

## Event Timeline Updates

### T-01 Enterprise Browser Race

**Latest developments**:
- **2026-10-19 08:30** · [Comet rollout](https://example.com/comet) · N-01
Comet expands enterprise rollout with multi-step workflows.
Comment: Direct impact on enterprise browser usage.

**Historical timeline**:
- [Initial preview](https://example.com/init) | 2026-04-01

## Today's Briefs

### N-01 Comet expands enterprise rollout | 2026-10-19 08:30
Comet expands enterprise rollout with multi-step workflows.
Why it matters: Shift from simple chat to agentic workflows.
Sources: [TechCrunch](https://example.com/tc) | [Reuters](https://example.com/reuters)

---

## Available Actions

- Reply `dig: N-01` to expand deep analysis and expert context.
- Reply `track: N-02` to start a continuous tracking thread.
- Reply `dig: T-01` to view full historical timeline.
- Reply `write: T-01` to draft an article from this thread.
- Natural-language feedback, e.g. "more enterprise coverage".
"""
        doc = parse_digest(content)
        self.assertEqual(doc.language, "en")
        self.assertEqual(doc.scan_interval, "2026-10-18 00:00 to 2026-10-19 00:00 UTC.")

        bundle = render_card_bundle(content)
        card = bundle["cards"][0]
        card_text = " ".join(extract_markdown_texts(card["body"]))
        self.assertIn("Event Timeline Updates", card_text)
        self.assertIn("Today's Briefs", card_text)
        self.assertIn("Why it matters", card_text)
        self.assertIn("Sources: ", card_text)
        self.assertIn("Reply `dig: N-01`", card_text)

        summary = summary_markdown(content, limit=5)
        self.assertIn("Scan window", summary)
        self.assertIn("2026-10-18 00:00 to 2026-10-19 00:00 UTC.", summary)
        self.assertIn("Full briefing and event timelines are available in the reply thread.", summary)
        self.assertIn("- **N-01** Comet expands enterprise rollout", summary)

    def test_unknown_input_rejection(self) -> None:
        with self.assertRaises(ValueError):
            parse_digest("Hello world this is random text without any digest structure")

    def test_unparsed_numbered_news_cannot_silently_vanish(self) -> None:
        malformed = """# 2026-10-19｜测试｜每日简报

## 今日简讯

### N-01 正常条目 ｜ 2026-10-19
正常事实。
信源：[A](https://example.com/a)

### N-02
"""
        try:
            doc = parse_digest(malformed)
            self.assertEqual(len(doc.items), 2)
        except ValueError as err:
            self.assertIn("Numbered items cannot silently vanish", str(err))

    def test_summary_markdown_no_invented_interval_and_five_items_limit(self) -> None:
        items_md = []
        for i in range(1, 10):
            items_md.append(f"""### N-{i:02d} 新闻标题 {i} ｜ 2026-10-19 10:00
新闻摘要第 {i} 条。后续还有更多描述。
信源：[媒体](https://example.com/{i})
""")
        content = "# 2026-10-19｜测试｜每日简报\n\n## 今日简讯\n\n" + "\n---\n\n".join(items_md)
        summary = summary_markdown(content, limit=5)

        self.assertNotIn("扫描时间范围", summary, "Must not invent scan interval when absent")
        self.assertIn("N-01", summary)
        self.assertIn("N-05", summary)
        self.assertNotIn("N-06", summary, "Must cap at limit=5 items")
        self.assertIn("💬 完整简报与事件线见本条回复。", summary)
        self.assertNotIn("dig:", summary)
        self.assertNotIn("track:", summary)


    def test_summary_markdown_retains_health_lead_notice(self) -> None:
        content = """# 2026-10-19｜测试｜每日简报

RSS 采集有 2 个信源连续失败，本期部分内容依赖运行时检索补充。

## 今日简讯

### N-01 事实标题 ｜ 2026-10-19 10:00
事实简介。
信源：[媒体](https://example.com/source)

## 可继续操作
- dig: N-01
"""
        summary = summary_markdown(content, limit=5)
        self.assertIn("RSS 采集有 2 个信源连续失败", summary)
        self.assertIn("N-01", summary)
        self.assertNotIn("dig:", summary)

    def test_cross_year_date_badge_retention(self) -> None:
        content = """# 2026-10-19｜跨年度新闻｜每日简报

## 今日简讯

### N-01 历史重要决议 ｜ 2025-10-15 09:30
这是一条跨年度事件。
信源：[历史档案](https://example.org/archive)

---

### N-02 中文格式年份 ｜ 2024年08月20日 14:00
中文格式跨年度事实。
信源：[公报](https://example.org/bulletin)
"""
        doc = parse_digest(content)
        self.assertEqual(len(doc.items), 2)
        self.assertEqual(doc.items[0].badge, "2025-10-15 09:30")
        self.assertEqual(doc.items[1].badge, "2024-08-20 14:00")

    def test_huge_why_field_in_news_item_fits_budget(self) -> None:
        huge_why = "这是极其详尽的战略研判与技术架构分析，包含深入推演。" * 250
        content = f"""# 2026-10-19｜超长研判测试｜每日简报

## 今日简讯

### N-01 架构重大变更 ｜ 2026-10-19 10:00
架构变更简要事实。
为何重要：{huge_why}
信源：[分析报告](https://example.org/analysis)
"""
        bundle = render_card_bundle(content)
        for idx, card in enumerate(bundle["cards"]):
            self.assertLessEqual(estimate_request_envelope_bytes(card), DEFAULT_PAYLOAD_BYTES)
            self.assertLessEqual(sum(count_elements(el) for el in card["body"]["elements"]), ELEMENT_BUDGET)
        all_card_text = " ".join(" ".join(extract_markdown_texts(c["body"])) for c in bundle["cards"])
        self.assertIn("N-01", all_card_text)
        self.assertIn("https://example.org/analysis", all_card_text)

    def test_oversized_single_thread_splits_semantically(self) -> None:
        progress_md = []
        for i in range(1, 15):
            progress_md.append(f"""• **2026-10-19 10:{i:02d}** · [关键进展节点 {i}](https://example.org/th/{i}) · N-{i:02d}
事实记录第 {i} 条，包含关键执行细节与数据。
点评：研判第 {i} 条影响。
信源：[媒体{i}](https://example.org/media/{i})""")

        content = f"""# 2026-10-19｜超大事件线测试｜每日简报

## 事件线时间线更新

### T-01 综合调查线 (comprehensive-investigation)

**最新进展**：
""" + "\n\n".join(progress_md) + """

**历史时间线**：
- [最初立项](https://example.org/start) ｜ 2026-01-01

## 今日简讯

### N-01 关键进展节点 1 ｜ 2026-10-19 10:01
事实内容。
信源：[媒体1](https://example.org/media/1)
"""
        bundle = render_card_bundle(content)
        all_card_text = " ".join(" ".join(extract_markdown_texts(c["body"])) for c in bundle["cards"])
        self.assertIn("T-01", all_card_text)
        for i in range(1, 15):
            self.assertIn(f"https://example.org/th/{i}", all_card_text)
            self.assertIn(f"N-{i:02d}", all_card_text)
        for card in bundle["cards"]:
            self.assertLessEqual(estimate_request_envelope_bytes(card), DEFAULT_PAYLOAD_BYTES)
            self.assertLessEqual(sum(count_elements(el) for el in card["body"]["elements"]), ELEMENT_BUDGET)

    def test_huge_thread_facts_30k_ascii_and_scan_interval_rendered(self) -> None:
        thread_facts_30k = "Thread fact detailed sentence about technical development. " * 500
        milestones = "\n".join(f"- [立项节点 {i}](https://example.org/node/{i}) ｜ 2026-01-{i % 28 + 1:02d}" for i in range(1, 40))
        huge_why = "战略研判与技术架构深度推演细节。" * 200

        content = f"""# 2026-10-19｜超大事件线与简报｜每日简报

扫描时间范围：2026-10-18 00:00 至 2026-10-19 00:00 UTC。

## 事件线时间线更新

### T-01 智能体发展线 (agent-dev)

**最新进展**：
• **2026-10-19 10:00** · [重大进展](https://example.org/th) · N-01
{thread_facts_30k}
点评：影响深远。
信源：[权威来源](https://example.org/source)

**历史时间线**：
{milestones}

## 今日简讯

### N-01 重大进展 ｜ 2026-10-19 10:00
事实内容。
为何重要：{huge_why}
信源：[权威来源](https://example.org/source)
"""
        bundle = render_card_bundle(content)
        cards = bundle["cards"]
        self.assertGreater(len(cards), 1)

        for idx, card in enumerate(cards):
            self.assertLessEqual(estimate_request_envelope_bytes(card), DEFAULT_PAYLOAD_BYTES, f"Card {idx} exceeded payload budget")
            self.assertLessEqual(sum(count_elements(el) for el in card["body"]["elements"]), ELEMENT_BUDGET, f"Card {idx} exceeded element budget")

        first_card_text = " ".join(extract_markdown_texts(cards[0]["body"]))
        self.assertIn("扫描时间范围", first_card_text)
        self.assertIn("2026-10-18 00:00 至 2026-10-19 00:00 UTC。", first_card_text)

        all_text = " ".join(" ".join(extract_markdown_texts(c["body"])) for c in cards)
        self.assertIn("T-01", all_text)
        self.assertIn("N-01", all_text)
        self.assertIn("https://example.org/source", all_text)
        self.assertIn("https://example.org/node/1", all_text)
        self.assertIn("https://example.org/node/39", all_text)

if __name__ == "__main__":
    unittest.main()
