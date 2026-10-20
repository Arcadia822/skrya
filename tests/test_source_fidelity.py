"""Tests for source fidelity, landing page preservation, and plain text degradation."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from skrya_orchestrator.digest_document import DigestItem, parse_digest
from skrya_orchestrator.feishu_cards import _render_single_news_block
from skrya_orchestrator.ingest import IngestService
from skrya_orchestrator.sources import (
    SourceRef,
    clean_source_name,
    host_name,
    is_valid_article_url,
    normalize_sources,
    parse_sources,
    primary_article_url,
    render_sources,
    source_identity,
)


class SourceFidelityTests(unittest.TestCase):
    def test_ingest_with_only_source_name_survives_load_snapshot_and_render(self) -> None:
        """Item with only source_name retains media identity without fabricating a URL."""
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            topic_dir = tmp_dir / "topics" / "military"
            topic_dir.mkdir(parents=True)
            (topic_dir / "topic.json").write_text(
                json.dumps({"name": "军事", "language": "zh-CN"}, ensure_ascii=False),
                encoding="utf-8",
            )
            ingest_payload = {
                "interface_version": "skrya.ingest.v2",
                "topic_id": "military",
                "retrieved_at": "2026-10-20T10:00:00+08:00",
                "producer": {
                    "kind": "runtime-skill",
                    "name": "weibo-trending",
                    "persistent": False,
                },
                "items": [
                    {
                        "id": "cctv-military-drill",
                        "title": "某战区组织两栖联合演练",
                        "source_name": "央视军事",
                        "published_at": "2026-10-20T09:00:00+08:00",
                        "fetched_at": "2026-10-20T09:30:00+08:00",
                        "summary": "多型舰艇组成编队开展实战化演训。",
                        "evidence_type": "social_hotlist",
                        "confidence": "high",
                        "custom_retrieval_trace": "trace-12345",
                    }
                ],
            }

            service = IngestService(tmp_dir, data_root=tmp_dir)
            service.record_ingest_result("military", ingest_payload)
            events = service.load_events("military")

            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event["title"], "某战区组织两栖联合演练")

            sources = event["sources"]
            self.assertEqual(len(sources), 1)
            src = sources[0]
            self.assertEqual(src["name"], "央视军事")
            self.assertEqual(src["url"], "")
            self.assertEqual(src["source_name"], "央视军事")
            self.assertEqual(src["fetched_at"], "2026-10-20T09:30:00+08:00")
            self.assertEqual(src["evidence_type"], "social_hotlist")
            self.assertEqual(src["confidence"], "high")
            self.assertEqual(src["custom_retrieval_trace"], "trace-12345")
            self.assertEqual(src["producer"]["name"], "weibo-trending")

            rendered_src = render_sources(sources)
            self.assertIn("央视军事", rendered_src)
            self.assertNotIn("http", rendered_src)
            self.assertNotIn("None", rendered_src)

            item = DigestItem(
                key="N-01",
                number=1,
                title="某战区组织两栖联合演练",
                facts="多型舰艇组成编队开展实战化演训。",
                sources=[SourceRef(name="央视军事", url="", extra=src)],
            )
            self.assertEqual(primary_article_url(item), "")

            card_block = _render_single_news_block(item, language="zh-CN")
            all_text = json.dumps(card_block, ensure_ascii=False)
            self.assertIn("央视军事", all_text)
            self.assertNotIn("](http", all_text)

            snapshot = {
                "items": {
                    "N-01": {
                        "key": "cctv-military-drill",
                        "title": "某战区组织两栖联合演练",
                        "sources": sources,
                    }
                }
            }
            digest_md = (
                "# 2026-10-20｜军事｜每日简报\n\n"
                "## 今日简讯\n\n"
                "### N-01 某战区组织两栖联合演练 ｜ 2026-10-20 09:00\n"
                "多型舰艇组成编队开展实战化演训。\n"
                "信源：央视军事\n\n"
                "---\n\n"
                "## 可继续操作\n"
                "- dig: N-01\n"
            )
            doc = parse_digest(digest_md, snapshot=snapshot)
            self.assertEqual(len(doc.items), 1)
            restored_item = doc.items[0]
            self.assertEqual(len(restored_item.sources), 1)
            self.assertEqual(restored_item.sources[0].name, "央视军事")
            self.assertEqual(restored_item.sources[0].url, "")
            self.assertEqual(restored_item.sources[0].extra["custom_retrieval_trace"], "trace-12345")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_mixed_linked_and_plain_sources_parsed_and_rendered(self) -> None:
        """Mixed sources on the same line retain linked Xinhua and plain CCTV Military/Weibo."""
        raw_line = "信源：[新华社](https://www.xinhuanet.com/milpro/20261016/364c7e4075a942c78d80e3930650f6a3/c.html) | 央视军事 | 微博热搜"
        sources = parse_sources(raw_line)

        self.assertEqual(len(sources), 3)
        self.assertEqual(sources[0].name, "新华社")
        self.assertEqual(
            sources[0].url,
            "https://www.xinhuanet.com/milpro/20261016/364c7e4075a942c78d80e3930650f6a3/c.html",
        )
        self.assertEqual(sources[1].name, "央视军事")
        self.assertEqual(sources[1].url, "")
        self.assertEqual(sources[2].name, "微博热搜")
        self.assertEqual(sources[2].url, "")

        rendered = render_sources(sources)
        expected = (
            '<font color="grey">信源：</font>'
            "[新华社](https://www.xinhuanet.com/milpro/20261016/364c7e4075a942c78d80e3930650f6a3/c.html) | "
            "央视军事 | 微博热搜"
        )
        self.assertEqual(rendered, expected)

    def test_legacy_url_only_inputs_continue_working(self) -> None:
        """Legacy URL-only inputs without explicit names derive host and keep valid link."""
        normalized = normalize_sources(["https://example.com/comet-enterprise"])
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["name"], "example.com")
        self.assertEqual(normalized[0]["url"], "https://example.com/comet-enterprise")

        rendered = render_sources(["https://example.com/comet-enterprise"])
        self.assertEqual(
            rendered,
            '<font color="grey">信源：</font>[example.com](https://example.com/comet-enterprise)',
        )
        self.assertEqual(
            primary_article_url(["https://example.com/comet-enterprise"]),
            "https://example.com/comet-enterprise",
        )

    def test_source_prefixed_publishers_survive_structured_and_display_boundaries(self) -> None:
        for name in ("source.test", "SourceForge", "SourceMaterial", "Source New Mexico", "Sources News"):
            for url in ("", "https://publisher.test/report"):
                record = {
                    "name": name,
                    "url": url,
                    "source_name": name,
                    "evidence": {"trace": "retrieved-report"},
                }
                source_ref = SourceRef(
                    name=name,
                    url=url,
                    extra={"source_name": name, "evidence": {"trace": "retrieved-report"}},
                )
                for source in (record, source_ref):
                    with self.subTest(name=name, url=url, source_type=type(source).__name__):
                        normalized = normalize_sources(source)
                        self.assertEqual(normalized, [record])
                        self.assertEqual(normalize_sources(normalized), [record])
                        for language in ("en", "zh-CN"):
                            rendered = render_sources(normalized, language=language)
                            parsed = parse_sources(rendered)
                            self.assertEqual([(entry.name, entry.url) for entry in parsed], [(name, url)])
                            markdown = (
                                "# Daily Briefing\n\n## News\n\n### N-01 Report\nFacts.\n"
                                f"{rendered}\n"
                            )
                            snapshot = {"items": {"N-01": {"sources": normalized}}}
                            item = parse_digest(markdown, snapshot=snapshot).items[0]
                            self.assertEqual([entry.to_dict() for entry in item.sources], [record])
                            card_text = json.dumps(_render_single_news_block(item, language=language), ensure_ascii=False)
                            self.assertIn(f"[{name}]({url})" if url else name, card_text)

    def test_source_labels_strip_only_a_colon_delimited_prefix(self) -> None:
        cases = [
            ("Source: SourceForge", "SourceForge"),
            ("Sources：source.test", "source.test"),
            ("**Sources**: Source New Mexico", "Source New Mexico"),
            ("<font color=\"grey\">来源：</font>SourceMaterial", "SourceMaterial"),
            ("信源：Sources News", "Sources News"),
            ("Source New Mexico", "Source New Mexico"),
            ("source.test", "source.test"),
        ]
        for text, name in cases:
            with self.subTest(text=text):
                self.assertEqual(clean_source_name(text), name)
                self.assertEqual([entry.to_dict() for entry in parse_sources(text)], [{"name": name, "url": ""}])
        source_url = "https://source.test/actor-casting-1"
        parsed = parse_sources(source_url)
        self.assertEqual([entry.to_dict() for entry in parsed], [{"name": "source.test", "url": source_url}])
        self.assertEqual(
            [entry.to_dict() for entry in parse_sources(render_sources(parsed, language="en"))],
            [{"name": "source.test", "url": source_url}],
        )

    def test_unsafe_homepage_and_search_placeholders_degrade_to_plain_label(self) -> None:
        """Obvious homepages and search pages lose hyperlinks but retain media labels."""
        inputs = [
            {"name": "中国军网", "url": "http://www.81.cn/"},
            {"name": "UKMTO", "url": "https://www.ukmto.org"},
            {"name": "抖音热搜", "url": "https://www.douyin.com/search/%E5%86%9B%E4%BA%8B"},
            {"name": "微博搜索", "url": "https://s.weibo.com/weibo?q=pla"},
            {"name": "百度搜索", "url": "https://www.baidu.com/s?wd=test"},
            {"name": "脚本注入", "url": "javascript:alert(1)"},
        ]
        normalized = normalize_sources(inputs)
        self.assertEqual(len(normalized), 6)

        for item in normalized:
            self.assertEqual(item["url"], "", f"URL for {item['name']} should have degraded to empty")
            self.assertTrue(item["name"], "Source name must be retained")

        rendered = render_sources(normalized)
        self.assertNotIn("http://www.81.cn", rendered)
        self.assertNotIn("https://www.ukmto.org", rendered)
        self.assertNotIn("douyin.com/search", rendered)
        self.assertNotIn("s.weibo.com/weibo", rendered)
        self.assertNotIn("javascript:", rendered)
        self.assertIn("中国军网", rendered)
        self.assertIn("UKMTO", rendered)
        self.assertIn("抖音热搜", rendered)

    def test_direct_article_links_stay_hyperlinks_and_malformed_urls_degrade_safely(self) -> None:
        """Article-shaped URLs stay linked; malformed URLs degrade with provenance."""
        linked = parse_sources("[微信公众号](https://mp.weixin.qq.com/s/actual-article)")
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0].url, "https://mp.weixin.qq.com/s/actual-article")
        self.assertEqual(linked[0].name, "微信公众号")

        rendered = render_sources(linked)
        self.assertIn("](https://mp.weixin.qq.com/s/actual-article)", rendered)

        malformed = normalize_sources(
            [
                {"name": "带凭据链接", "url": "https://user:{{EMAIL_bpwbejbp}}@example.com/article-1"},
                {"name": "坏端口链接", "url": "http://example.com:notaport/article-1"},
                {"name": "端口超界链接", "url": "http://example.com:99999999/article-1"},
            ]
        )
        self.assertEqual(len(malformed), 3)
        by_name = {item["name"]: item for item in malformed}
        self.assertEqual(by_name["带凭据链接"]["url"], "")
        self.assertEqual(by_name["坏端口链接"]["url"], "")
        self.assertEqual(by_name["端口超界链接"]["url"], "")
        self.assertEqual(
            by_name["带凭据链接"].get("original_url"),
            "https://user:{{EMAIL_bpwbejbp}}@example.com/article-1",
        )
        self.assertEqual(by_name["坏端口链接"].get("original_url"), "http://example.com:notaport/article-1")
        self.assertEqual(by_name["端口超界链接"].get("original_url"), "http://example.com:99999999/article-1")

    def test_wechat_short_path_article_survives_rendering(self) -> None:
        """A WeChat /s/<id> URL keeps its shape through parsing and card rendering."""
        digest_md = (
            "# 2026-10-20｜军事｜每日简报\n\n"
            "## 今日简讯\n\n"
            "### N-01 某战区组织两栖联合演练 ｜ 2026-10-20 09:00\n"
            "多型舰艇组成编队开展实战化演训。\n"
            "信源：[微信公众号文章](https://mp.weixin.qq.com/s/actual-article)\n\n"
            "---\n\n"
            "## 可继续操作\n"
            "- dig: N-01\n"
        )
        doc = parse_digest(digest_md)
        self.assertEqual(len(doc.items), 1)
        item = doc.items[0]
        self.assertEqual(item.sources[0].url, "https://mp.weixin.qq.com/s/actual-article")
        self.assertEqual(primary_article_url(item), "https://mp.weixin.qq.com/s/actual-article")

        card_block = _render_single_news_block(item, language="zh-CN")
        all_text = json.dumps(card_block, ensure_ascii=False)
        self.assertIn("](https://mp.weixin.qq.com/s/actual-article)", all_text)

    def test_unrelated_article_urls_never_reassigned(self) -> None:
        """When an event has only plain or degraded sources, primary_article_url returns empty."""
        item_plain = DigestItem(
            key="N-01",
            number=1,
            title="新闻一",
            sources=[SourceRef(name="央视军事", url="")],
        )
        self.assertEqual(primary_article_url(item_plain), "")

        item_homepage = DigestItem(
            key="N-02",
            number=2,
            title="新闻二",
            sources=[SourceRef(name="中国军网", url="http://www.81.cn/")],
        )
        self.assertEqual(primary_article_url(item_homepage), "")

        item_title_homepage = DigestItem(
            key="N-03",
            number=3,
            title="[新闻三](http://www.81.cn/)",
            sources=[SourceRef(name="微博热搜", url="")],
        )
        self.assertEqual(primary_article_url(item_title_homepage), "")

    def test_duplicate_name_and_link_handling(self) -> None:
        """Deduplicates redundant names and links while upgrading plain labels when linked version arrives."""
        s1 = normalize_sources(
            [
                {"name": "新华社", "url": "https://xinhuanet.com/article-1"},
                {"name": "新华网", "url": "https://xinhuanet.com/article-1"},
            ]
        )
        self.assertEqual(len(s1), 1)

        s2 = normalize_sources(["央视军事", "央视军事"])
        self.assertEqual(len(s2), 1)
        self.assertEqual(s2[0]["name"], "央视军事")

        s3 = normalize_sources(
            [
                {"name": "央视军事", "url": ""},
                {"name": "央视军事", "url": "https://cctv.com/article-123", "extra_note": "article-trace"},
            ]
        )
        self.assertEqual(len(s3), 1)
        self.assertEqual(s3[0]["url"], "https://cctv.com/article-123")
        self.assertEqual(s3[0].get("extra_note"), "article-trace")

        s4 = normalize_sources(
            [
                {"name": "央视军事", "url": "https://cctv.com/article-123"},
                {"name": "央视军事", "url": ""},
            ]
        )
        self.assertEqual(len(s4), 1)
        self.assertEqual(s4[0]["url"], "https://cctv.com/article-123")

        s5 = normalize_sources(["央视军事", "微博热搜"])
        self.assertEqual(len(s5), 2)
        self.assertEqual(s5[0]["name"], "央视军事")
        self.assertEqual(s5[1]["name"], "微博热搜")

    def test_snapshot_backed_source_restoration_retains_all_actual_source_labels(self) -> None:
        """parse_digest with snapshot restores all actual source labels even if markdown is partial."""
        snapshot = {
            "items": {
                "N-01": {
                    "key": "drill-key",
                    "title": "联合演练",
                    "sources": [
                        {"name": "新华社", "url": "https://xinhuanet.com/drill"},
                        {"name": "央视军事", "url": ""},
                        {"name": "微博热搜", "url": "", "trending_rank": 3},
                    ],
                }
            }
        }
        md_text = (
            "# 2026-10-20｜军事｜每日简报\n\n"
            "## 今日简讯\n\n"
            "### N-01 联合演练 ｜ 2026-10-20 09:00\n"
            "事实简介。\n"
            "信源：[新华社](https://xinhuanet.com/drill)\n\n"
            "---\n\n"
            "## 可继续操作\n"
            "- dig: N-01\n"
        )
        doc = parse_digest(md_text, snapshot=snapshot)
        self.assertEqual(len(doc.items), 1)
        item = doc.items[0]

        self.assertEqual(len(item.sources), 3)
        names = [s.name for s in item.sources]
        self.assertEqual(names, ["新华社", "央视军事", "微博热搜"])
        self.assertEqual(item.sources[0].url, "https://xinhuanet.com/drill")
        self.assertEqual(item.sources[1].url, "")
        self.assertEqual(item.sources[2].extra["trending_rank"], 3)

    def test_source_segments_tokenize_every_link_and_keep_plain_labels(self) -> None:
        cases = [
            (
                "Sources: https://example.org/a https://example.org/b",
                [("example.org", "https://example.org/a"), ("example.org", "https://example.org/b")],
            ),
            (
                "Sources: [A](https://example.org/a) [B](https://example.org/b) | CCTV",
                [("A", "https://example.org/a"), ("B", "https://example.org/b"), ("CCTV", "")],
            ),
            (
                "Sources: CCTV [A](https://example.org/a) https://example.org/b | BBC News",
                [("CCTV", ""), ("A", "https://example.org/a"), ("example.org", "https://example.org/b"), ("BBC News", "")],
            ),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                parsed = parse_sources(raw)
                self.assertEqual([(source.name, source.url) for source in parsed], expected)
                self.assertEqual(
                    [(source.name, source.url) for source in parse_sources(render_sources(parsed, language="en"))],
                    expected,
                )
                self.assertEqual(
                    [(source["name"], source["url"]) for source in normalize_sources([raw])],
                    expected,
                )
                self.assertEqual(primary_article_url(raw), "https://example.org/a")

    def test_url_whitespace_is_rejected_without_losing_original_evidence(self) -> None:
        for url in (
            "https://example.org/report one",
            "https://example.org/report\tone",
            "https://example.org/report\none",
            "https://example.org/a https://example.org/b",
        ):
            with self.subTest(url=url):
                self.assertFalse(is_valid_article_url(url))
                self.assertEqual(
                    normalize_sources({"name": "Reuters", "url": url, "evidence_type": "retrieved"}),
                    [{"name": "Reuters", "url": "", "original_url": url, "evidence_type": "retrieved"}],
                )
                parsed = parse_sources(f"[Reuters]({url})")
                self.assertEqual(
                    [source.to_dict() for source in parsed],
                    [{"name": "Reuters", "url": "", "original_url": url}],
                )
                self.assertEqual(primary_article_url(parsed), "")
        self.assertTrue(is_valid_article_url("https://example.org/report%20one"))
        self.assertEqual(primary_article_url("https://example.org/report%20one"), "https://example.org/report%20one")

    def test_duplicate_urls_merge_compatible_metadata_without_mutating_inputs(self) -> None:
        sources = [
            {"name": "Reuters", "url": "https://example.org/report", "evidence": {"trace": "article-a"}},
            {
                "name": "Reuters",
                "url": "https://example.org/report",
                "evidence": {"trace": "article-a", "fetched_at": "2026-10-20T09:00:00Z"},
                "confidence": "high",
                "archived": False,
            },
        ]
        original = json.loads(json.dumps(sources))
        normalized = normalize_sources(sources)
        self.assertEqual(normalized, [{
            "name": "Reuters",
            "url": "https://example.org/report",
            "evidence": {"trace": "article-a", "fetched_at": "2026-10-20T09:00:00Z"},
            "confidence": "high",
            "archived": False,
        }])
        self.assertEqual(sources, original)
        self.assertEqual(normalize_sources(normalized), normalized)

    def test_same_name_rejected_urls_retain_distinct_originals_and_evidence(self) -> None:
        sources = [
            {"name": "Reuters", "url": "https://example.org/", "retrieval_trace": "homepage"},
            {"name": "Reuters", "url": "https://example.org/search?q=report", "retrieval_trace": "search"},
        ]
        normalized = normalize_sources(sources)
        self.assertEqual(normalized, [
            {"name": "Reuters", "url": "", "original_url": "https://example.org/", "retrieval_trace": "homepage"},
            {"name": "Reuters", "url": "", "original_url": "https://example.org/search?q=report", "retrieval_trace": "search"},
        ])
        self.assertEqual(normalize_sources(normalized), normalized)

    def test_conflicting_duplicate_evidence_and_original_urls_stay_separate(self) -> None:
        metadata_pairs = [
            ({"original_url": "https://example.org/original-a"}, {"original_url": "https://example.org/original-b"}),
            ({"evidence": {"trace": "a"}}, {"evidence": {"trace": "b"}}),
            ({"archived": False}, {"archived": True}),
        ]
        for url in ("", "https://example.org/report"):
            for left, right in metadata_pairs:
                with self.subTest(url=url, left=left, right=right):
                    sources = [
                        {"name": "Reuters", "url": url, **left},
                        {"name": "Reuters", "url": url, **right},
                    ]
                    normalized = normalize_sources(sources)
                    self.assertEqual(normalized, sources)
                    self.assertEqual(normalize_sources(normalized), sources)

    def test_evidence_bearing_unlinked_sources_do_not_gain_an_article_by_name(self) -> None:
        unlinked = {"name": "Reuters", "url": "", "evidence": {"trace": "hotlist"}}
        linked = {"name": "Reuters", "url": "https://example.org/report", "evidence": {"trace": "article"}}
        for sources in ([unlinked, linked], [linked, unlinked]):
            with self.subTest(sources=sources):
                self.assertEqual(normalize_sources(sources), sources)

    def test_snapshot_matches_same_publisher_articles_by_url_without_cross_attaching_evidence(self) -> None:
        snapshot = {"items": {"N-01": {"sources": [
            {"name": "Reuters", "url": "https://example.org/report-a", "evidence": {"trace": "a"}},
            {"name": "Reuters", "url": "https://example.org/report-b", "evidence": {"trace": "b"}},
            {"name": "Reuters", "url": "https://example.org/report-b", "fetched_at": "2026-10-20T09:00:00Z"},
        ]}}}
        for source_line in ("[Reuters](https://example.org/report-a)", "Reuters"):
            with self.subTest(source_line=source_line):
                markdown = (
                    "# Daily Briefing\n\n## News\n\n### N-01 Report\nFacts.\n"
                    f"Sources: {source_line}\n"
                )
                item = parse_digest(markdown, snapshot=snapshot).items[0]
                self.assertEqual([source.url for source in item.sources], ["https://example.org/report-a", "https://example.org/report-b"])
                self.assertEqual(item.sources[0].extra, {"evidence": {"trace": "a"}})
                self.assertEqual(item.sources[1].extra, {"evidence": {"trace": "b"}, "fetched_at": "2026-10-20T09:00:00Z"})
                card_text = json.dumps(_render_single_news_block(item, language="en"), ensure_ascii=False)
                self.assertIn("[Reuters](https://example.org/report-a)", card_text)
                self.assertIn("[Reuters](https://example.org/report-b)", card_text)

    def test_snapshot_keeps_conflicting_evidence_and_unlinked_provenance_separate(self) -> None:
        snapshot_sources = [
            {"name": "Reuters", "url": "https://example.org/report", "evidence": {"trace": "a"}},
            {"name": "Reuters", "url": "https://example.org/report", "evidence": {"trace": "b"}},
            {"name": "Reuters", "url": "https://example.org/search?q=other", "evidence": {"trace": "search"}},
        ]
        snapshot = {"items": {"N-01": {"sources": snapshot_sources}}}
        markdown = (
            "# Daily Briefing\n\n## News\n\n### N-01 Report\nFacts.\n"
            "Sources: [Reuters](https://example.org/report)\n"
        )
        restored = parse_digest(markdown, snapshot=snapshot).items[0].sources
        self.assertEqual([source.to_dict() for source in restored], [
            {"name": "Reuters", "url": "https://example.org/report", "evidence": {"trace": "a"}},
            {"name": "Reuters", "url": "https://example.org/report", "evidence": {"trace": "b"}},
            {"name": "Reuters", "url": "", "original_url": "https://example.org/search?q=other", "evidence": {"trace": "search"}},
        ])

    def test_wechat_query_article_url_remains_linked(self) -> None:
        url = "https://mp.weixin.qq.com/s?__biz=example&mid=123&idx=1&sn=article"
        sources = normalize_sources({"name": "微信公众号", "url": url})
        self.assertEqual(sources, [{"name": "微信公众号", "url": url}])
        parsed = parse_sources(render_sources(sources))
        self.assertEqual([(source.name, source.url) for source in parsed], [("微信公众号", url)])

    def test_canonical_source_names_cannot_supply_unrecorded_link_destinations(self) -> None:
        embedded_name = "[Reuters](https://unverified.test/article)"
        plain_sources = [{"name": embedded_name, "url": ""}]
        self.assertEqual(normalize_sources(plain_sources), [{"name": "Reuters", "url": ""}])
        self.assertEqual(
            render_sources(plain_sources, language="en"),
            "<font color=\"grey\">Sources: </font>Reuters",
        )
        self.assertEqual(primary_article_url(plain_sources), "")
        self.assertEqual(
            render_sources([{"name": embedded_name, "url": "https://example.org/report"}], language="en"),
            "<font color=\"grey\">Sources: </font>[Reuters](https://example.org/report)",
        )
        intentional_markdown = parse_sources(embedded_name)
        self.assertEqual(
            [(source.name, source.url) for source in intentional_markdown],
            [("Reuters", "https://unverified.test/article")],
        )
        item = DigestItem(key="report", number=1, title="Report", sources=[SourceRef(name=embedded_name)])
        card_text = json.dumps(_render_single_news_block(item, language="en"), ensure_ascii=False)
        self.assertIn("Reuters", card_text)
        self.assertNotIn("https://unverified.test/article", card_text)

    def test_source_name_brackets_cannot_replace_the_recorded_link_destination(self) -> None:
        source = {
            "name": "Reuters](https://unverified.test/article) [Other",
            "url": "https://example.org/report",
        }
        self.assertEqual(
            render_sources([source], language="en"),
            "<font color=\"grey\">Sources: </font>"
            "[Reuters\\](https://unverified.test/article) \\[Other](https://example.org/report)",
        )
        self.assertEqual(primary_article_url([source]), "https://example.org/report")

    def test_english_rendering_and_labels(self) -> None:
        """English source labels render with Sources prefix and preserve mixed links."""
        sources = [
            {"name": "Reuters", "url": "https://reuters.com/world/article-1"},
            {"name": "BBC News", "url": ""},
        ]
        rendered = render_sources(sources, language="en")
        self.assertEqual(
            rendered,
            '<font color="grey">Sources: </font>[Reuters](https://reuters.com/world/article-1) | BBC News',
        )

    def test_clean_source_name_and_host_derivation(self) -> None:
        """Strips formatting, leading labels, and font tags while deriving clean hosts."""
        self.assertEqual(clean_source_name("**信源**：央视军事"), "央视军事")
        self.assertEqual(clean_source_name("<font color=grey>来源：</font>人民日报"), "人民日报")
        self.assertEqual(clean_source_name("Sources: Reuters"), "Reuters")
        self.assertEqual(host_name("https://www.xinhuanet.com/mil/123.htm"), "xinhuanet.com")
        self.assertEqual(host_name("http://news.cctv.com:8080/test"), "news.cctv.com")

    def test_bare_url_paired_parentheses_survive_and_unpaired_terminate(self) -> None:
        """Paired ASCII parentheses stay inside a bare URL; unpaired trailing parens terminate it."""
        linked = [r for r in normalize_sources("详情见 https://en.wikipedia.org/wiki/GPT_(language_model) 说明") if r["url"]]
        self.assertEqual(
            ["https://en.wikipedia.org/wiki/GPT_(language_model)"],
            [r["url"] for r in linked],
        )
        structured = normalize_sources([
            {"name": "Wikipedia", "url": "https://en.wikipedia.org/wiki/GPT_(language_model)"}
        ])[0]
        self.assertEqual("https://en.wikipedia.org/wiki/GPT_(language_model)", structured["url"])
        trailing = [r for r in normalize_sources("（见 https://x.com/a）") if r["url"]]
        self.assertEqual(["https://x.com/a"], [r["url"] for r in trailing])

    def test_ipv6_literal_article_urls_are_valid(self) -> None:
        self.assertTrue(is_valid_article_url("http://[::1]:8000/posts/1"))
        self.assertTrue(is_valid_article_url("http://[2001:db8::1]/articles/one"))
        self.assertFalse(is_valid_article_url("http://[::1]/"))
        self.assertFalse(is_valid_article_url("https://[fe80::1]/search?q=x"))

    def test_source_identity_single_convention(self) -> None:
        """Explicit ids win; otherwise identity digests the type-specific reference."""
        self.assertEqual("confirmed", source_identity({"id": " confirmed ", "url": "https://a.test/x"}))
        self.assertEqual(
            "rss:" + hashlib.sha256(b"https://news.test/rss").hexdigest(),
            source_identity({"type": "rss", "url": "https://news.test/rss"}),
        )
        self.assertEqual(
            "rsshub:" + hashlib.sha256(b"/confirmed/news").hexdigest(),
            source_identity({"type": "rsshub", "route": "/confirmed/news"}),
        )


if __name__ == "__main__":
    unittest.main()

