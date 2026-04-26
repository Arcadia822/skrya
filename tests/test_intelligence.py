import json
import shutil
import unittest
from pathlib import Path

from skrya_orchestrator.intelligence import IntelligenceService


ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = ROOT / "tmp" / "unit-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class IntelligenceServiceTests(unittest.TestCase):
    def test_generate_digest_writes_all_items_as_numbered_unicode_blocks(self) -> None:
        root = self._make_root("digest-output")
        self._write_topic(root)
        self._write_sample_events(root)

        service = IntelligenceService(root)
        digest = service.generate_digest("k-entertainment")

        self.assertIn("｜K-Entertainment｜每日简报", digest.markdown)
        self.assertIn("┌─ **【简讯1】", digest.markdown)
        self.assertIn("某女团练习生出圈片段从 INS 扩散到韩媒", digest.markdown)
        self.assertIn("\n│\n│ 信源：", digest.markdown)
        self.assertNotIn("### 1.", digest.markdown)
        self.assertIn("┌─ **【简讯6】", digest.markdown)
        self.assertIn("某男团成员个人账号更新引发造型讨论", digest.markdown)
        self.assertIn("│ 信源：[source.test](https://source.test/trainee-1)", digest.markdown)
        self.assertNotIn("中文导读：", digest.markdown)
        self.assertNotIn("Top 5 必看", digest.markdown)
        self.assertNotIn("今日观察", digest.markdown)
        self.assertNotIn("建议深挖", digest.markdown)
        self.assertIn("A. 详细分析指定今日简讯", digest.markdown)
        self.assertIn("B. 创建新的事件线", digest.markdown)
        self.assertIn("---\n\n## 系统提示", digest.markdown)
        self.assertIn("- 执行时间：", digest.markdown)
        self.assertIn("- 执行状态：完成：生成 6 条简讯，更新 0 条事件线。", digest.markdown)
        self.assertIn("- 扫描时间范围：最近 24 小时（默认）", digest.markdown)
        self.assertIn("- 可继续操作：", digest.markdown)
        self.assertIn("C. 调整简讯和事件线的获取策略", digest.markdown)
        self.assertNotIn("$deep-analysis", digest.markdown)
        self.assertNotIn("REQ-001", digest.markdown)
        self.assertTrue(digest.digest_path.exists())
        self.assertTrue(digest.artifact_path.exists())

    def test_generate_digest_resolves_topic_name_for_nontechnical_users(self) -> None:
        root = self._make_root("digest-topic-name")
        self._write_topic(root)
        self._write_sample_events(root)

        service = IntelligenceService(root)
        digest = service.generate_digest("韩国娱乐舆情追踪")

        self.assertIn("┌─ **【简讯1】", digest.markdown)
        self.assertIn("某女团练习生出圈片段从 INS 扩散到韩媒", digest.markdown)
        self.assertEqual(root / "runs" / "k-entertainment" / "latest-digest.md", digest.digest_path)

    def test_live_sources_do_not_fall_back_to_sample_events_when_empty(self) -> None:
        root = self._make_root("live-empty-no-sample-fallback")
        self._write_topic(root)
        self._write_sample_events(root)
        topic_dir = root / "topics" / "k-entertainment"
        (topic_dir / "sources.json").write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "id": "empty-feed",
                            "name": "Empty Feed",
                            "type": "rss",
                            "enabled": True,
                            "url": "https://feed.test/empty.xml",
                            "adapter": "rss",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        empty_rss = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"><channel><title>Empty Feed</title></channel></rss>
"""

        service = IntelligenceService(root, fetcher=lambda url: empty_rss)
        digest = service.generate_digest("k-entertainment", prefer_live=True)

        self.assertIn("暂时没有抓到足够新的真实内容", digest.markdown)
        self.assertNotIn("某女团练习生出圈片段", digest.markdown)

    def test_generate_digest_ranks_events_using_brief_and_value_signals(self) -> None:
        root = self._make_root("digest-ranking")
        self._write_topic(root)
        topic_dir = root / "topics" / "k-entertainment"
        (topic_dir / "brief.json").write_text(
            json.dumps(
                {
                    "requests": [
                        {
                            "req": "REQ-001",
                            "content": "优先看合约终止、法律进展、判刑和公司回应这类会继续发酵的事件。",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        events = [
            {
                "key": "watch-list",
                "title": "5 Chae Jong Hyeop K-Dramas To Add To Your Watch List",
                "headline_summary": "A lightweight viewing guide with no new event movement.",
                "list_summary": "",
                "analysis_title": "Watch list",
                "analysis_body": "A viewing guide.",
                "sources": ["https://source.test/watch-list"],
            },
            {
                "key": "contract",
                "title": "Chen, Baekhyun, And Xiumin Reportedly Notify INB100 Of Contract Termination",
                "headline_summary": "The members requested clarification regarding unpaid settlements and contract termination.",
                "list_summary": "",
                "analysis_title": "Contract termination",
                "analysis_body": "A formal notice has moved the dispute into company-level conflict.",
                "sources": ["https://source.test/contract"],
            },
            {
                "key": "deepfake",
                "title": "SM Entertainment Provides Update As Deepfake Offenders Receive Prison Sentences",
                "headline_summary": "The agency shared legal progress as offenders receive prison sentences.",
                "list_summary": "",
                "analysis_title": "Deepfake legal update",
                "analysis_body": "Legal action has produced a concrete court outcome.",
                "sources": [
                    "https://source.test/deepfake-1",
                    "https://source.test/deepfake-2",
                ],
            },
        ]
        (topic_dir / "sample-events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")

        translator = lambda text: {
            events[0]["title"]: "5 部值得加入片单的蔡钟协韩剧",
            events[0]["headline_summary"]: "一篇轻量片单，没有新的事件进展。",
            events[1]["title"]: "CBX 向 INB100 发出合约终止通知",
            events[1]["headline_summary"]: "成员要求说明未结算款项和合约终止问题。",
            events[2]["title"]: "SM 公布深伪犯罪法律进展并出现判刑结果",
            events[2]["headline_summary"]: "公司披露法律进展，涉案者已收到刑期。",
        }.get(text, text)

        service = IntelligenceService(root, translator=translator)
        digest = service.generate_digest("k-entertainment")

        self.assertLess(digest.markdown.index("┌─ **【简讯1】"), digest.markdown.index("┌─ **【简讯3】"))
        self.assertLess(digest.markdown.index("SM 公布深伪犯罪法律进展"), digest.markdown.index("5 部值得加入片单"))
        self.assertLess(digest.markdown.index("CBX 向 INB100 发出合约终止通知"), digest.markdown.index("5 部值得加入片单"))

    def test_deep_analysis_resolves_digest_item_number_and_hides_sources_by_default(self) -> None:
        root = self._make_root("deep-analysis")
        self._write_topic(root)
        self._write_sample_events(root)

        service = IntelligenceService(root)
        service.generate_digest("k-entertainment")

        analysis = service.generate_deep_analysis("k-entertainment", event_number=2)

        self.assertIn("某演员与新剧选角争议升温", analysis.markdown)
        self.assertIn("媒体报道和社媒情绪开始出现明显分叉", analysis.markdown)
        self.assertIn("简要结论", analysis.markdown)
        self.assertIn("已知事实", analysis.markdown)
        self.assertIn("不确定性", analysis.markdown)
        self.assertIn("接下来观察", analysis.markdown)
        self.assertNotIn("中文判断：", analysis.markdown)
        self.assertNotIn("https://source.test", analysis.markdown)

    def test_deep_analysis_sources_are_available_on_demand(self) -> None:
        root = self._make_root("sources-on-demand")
        self._write_topic(root)
        self._write_sample_events(root)

        service = IntelligenceService(root)
        service.generate_digest("k-entertainment")

        sources = service.get_event_sources("k-entertainment", event_number=2)

        self.assertEqual(
            [
                "https://source.test/actor-casting-1",
                "https://source.test/actor-casting-2",
            ],
            sources,
        )

    def test_event_thread_timeline_replays_runtime_artifact_without_showing_sources(self) -> None:
        root = self._make_root("event-thread-timeline")
        self._write_new_energy_topic(root)
        self._write_byd_event_thread(root)

        service = IntelligenceService(root)
        timeline = service.generate_event_thread_timeline("新能源汽车", "比亚迪闪充站")

        self.assertEqual(
            root / "runs" / "new-energy-vehicles" / "event-threads" / "latest-event-threads.json",
            timeline.artifact_path,
        )
        self.assertIn("# 比亚迪闪充站", timeline.markdown)
        self.assertIn("**当前状态：** 持续跟进", timeline.markdown)
        self.assertIn("2026-04-25 · 建线观察", timeline.markdown)
        self.assertIn("2026-04-27 · 进展续写", timeline.markdown)
        self.assertIn("关联日报：2。", timeline.markdown)
        self.assertIn("关联日报：1, 4。", timeline.markdown)
        self.assertIn("首批站点在哪些城市真正落地", timeline.markdown)
        self.assertNotIn("https://example.com", timeline.markdown)
        self.assertNotIn("byd-flash-charge-station", timeline.markdown)

    def test_event_thread_timeline_accepts_alias_reference(self) -> None:
        root = self._make_root("event-thread-alias")
        self._write_new_energy_topic(root)
        self._write_byd_event_thread(root)

        service = IntelligenceService(root)
        timeline = service.generate_event_thread_timeline("new-energy-vehicles", "BYD 闪充站")

        self.assertIn("# 比亚迪闪充站", timeline.markdown)
        self.assertIn("**续写判断：**", timeline.markdown)

    def test_generate_digest_writes_detailed_event_thread_updates_when_items_match_seed(self) -> None:
        root = self._make_root("event-thread-digest")
        self._write_new_energy_topic(root)
        self._write_byd_event_thread_seed(root)
        sample_events = json.loads((ROOT / "topics" / "new-energy-vehicles" / "sample-events.json").read_text(encoding="utf-8"))
        topic_dir = root / "topics" / "new-energy-vehicles"
        (topic_dir / "sample-events.json").write_text(
            json.dumps(sample_events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        service = IntelligenceService(root)
        digest = service.generate_digest("新能源汽车", prefer_live=False)

        self.assertIn("## 事件线更新", digest.markdown)
        self.assertIn("┌─ **【事件线】比亚迪闪充站**", digest.markdown)
        self.assertNotIn("今天命中的简讯：", digest.markdown)
        self.assertIn("│ 后续看点：首批站点在哪些城市真正落地", digest.markdown)
        self.assertLess(digest.markdown.index("## 事件线更新"), digest.markdown.index("## 今日简讯"))
        self.assertIn("A. 详细分析指定今日简讯", digest.markdown)
        self.assertIn("- 执行状态：完成：生成 3 条简讯，更新 1 条事件线。", digest.markdown)

    def test_generate_digest_persists_event_thread_runtime_artifact_when_seed_matches(self) -> None:
        root = self._make_root("event-thread-digest-runtime-artifact")
        self._write_new_energy_topic(root)
        self._write_byd_event_thread_seed(root)
        sample_events = json.loads((ROOT / "topics" / "new-energy-vehicles" / "sample-events.json").read_text(encoding="utf-8"))
        topic_dir = root / "topics" / "new-energy-vehicles"
        (topic_dir / "sample-events.json").write_text(
            json.dumps(sample_events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        service = IntelligenceService(root)
        service.generate_digest("新能源汽车", prefer_live=False)
        timeline = service.generate_event_thread_timeline("新能源汽车", "比亚迪闪充站")

        self.assertEqual(
            root / "runs" / "new-energy-vehicles" / "event-threads" / "latest-event-threads.json",
            timeline.artifact_path,
        )
        self.assertIn("# 比亚迪闪充站", timeline.markdown)
        self.assertIn("关联日报：", timeline.markdown)

    def test_refresh_event_threads_builds_runtime_artifact_from_seed_and_digest_events(self) -> None:
        root = self._make_root("event-thread-refresh")
        self._write_new_energy_topic(root)
        self._write_byd_event_thread_seed(root)
        self._write_byd_digest_event_index(
            root,
            items=[
                {
                    "number": 2,
                    "title": "比亚迪闪充站从发布概念进入首批落地讨论",
                    "analysis_title": "比亚迪闪充站从发布概念进入首批落地讨论",
                    "analysis_body": "这条线开始从产品能力展示，推进到站点建设节奏、城市覆盖和补能体验是否可验证的讨论。",
                    "sources": ["https://example.com/byd-flash-charge-launch"],
                    "date": "2026-04-25",
                },
                {
                    "number": 4,
                    "title": "首批 BYD 闪充站城市名单开始清晰，媒体出现实测补能效率报道",
                    "analysis_title": "首批 BYD 闪充站城市名单开始清晰，媒体出现实测补能效率报道",
                    "analysis_body": "事件从概念热度转向建设兑现，用户开始能用同一条线回看是否真的铺开、体验是否站得住。",
                    "sources": [
                        "https://example.com/byd-flash-charge-cities",
                        "https://example.com/byd-flash-charge-test",
                    ],
                    "date": "2026-04-27",
                },
            ],
        )

        service = IntelligenceService(root)
        result = service.refresh_event_threads("新能源汽车")

        self.assertEqual(
            root / "runs" / "new-energy-vehicles" / "event-threads" / "latest-event-threads.json",
            result.artifact_path,
        )
        thread = result.payload["threads"][0]
        self.assertEqual("比亚迪闪充站", thread["name"])
        self.assertEqual(["BYD 闪充站", "比亚迪兆瓦闪充站"], thread["aliases"])
        self.assertEqual("active", thread["status"])
        self.assertEqual(2, len(thread["timeline"]))
        self.assertEqual("seed", thread["timeline"][0]["phase"])
        self.assertEqual("update", thread["timeline"][1]["phase"])
        self.assertEqual([2], thread["timeline"][0]["related_digest_numbers"])
        self.assertEqual([4], thread["timeline"][1]["related_digest_numbers"])

    def test_refresh_event_threads_preserves_existing_timeline_and_appends_new_progress(self) -> None:
        root = self._make_root("event-thread-refresh-append")
        self._write_new_energy_topic(root)
        self._write_byd_event_thread_seed(root)
        self._write_byd_event_thread(root)
        payload = json.loads(
            (root / "runs" / "new-energy-vehicles" / "event-threads" / "latest-event-threads.json").read_text(
                encoding="utf-8"
            )
        )
        payload["threads"][0]["timeline"] = payload["threads"][0]["timeline"][:1]
        (root / "runs" / "new-energy-vehicles" / "event-threads" / "latest-event-threads.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._write_byd_digest_event_index(
            root,
            items=[
                {
                    "number": 4,
                    "title": "首批 BYD 闪充站城市名单开始清晰，媒体出现实测补能效率报道",
                    "analysis_title": "首批 BYD 闪充站城市名单开始清晰，媒体出现实测补能效率报道",
                    "analysis_body": "事件从概念热度转向建设兑现，用户开始能用同一条线回看是否真的铺开、体验是否站得住。",
                    "sources": [
                        "https://example.com/byd-flash-charge-cities",
                        "https://example.com/byd-flash-charge-test",
                    ],
                    "date": "2026-04-27",
                }
            ],
        )

        service = IntelligenceService(root)
        result = service.refresh_event_threads("new-energy-vehicles")

        timeline = result.payload["threads"][0]["timeline"]
        self.assertEqual(2, len(timeline))
        self.assertEqual("2026-04-25", timeline[0]["date"])
        self.assertEqual("2026-04-27", timeline[1]["date"])
        self.assertEqual("update", timeline[1]["phase"])

    def test_generate_digest_fetches_real_rss_when_sample_events_are_absent(self) -> None:
        root = self._make_root("live-rss")
        topic_dir = root / "topics" / "k-entertainment"
        topic_dir.mkdir(parents=True)
        (topic_dir / "topic.json").write_text(
            json.dumps(
                {
                    "topic": "k-entertainment",
                    "name": "K-Entertainment",
                    "description": "韩国娱乐舆情追踪",
                    "language": "zh-CN",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (topic_dir / "brief.json").write_text(
            json.dumps({"requests": [{"req": "REQ-001", "content": "韩国娱乐热点"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (topic_dir / "sources.json").write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "id": "feed-1",
                            "name": "Feed 1",
                            "type": "rss",
                            "enabled": True,
                            "url": "https://feed.test/rss",
                            "adapter": "rss",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (topic_dir / "digest.md").write_text("# Digest Standard", encoding="utf-8")
        (topic_dir / "deep-analysis.md").write_text("# Deep Analysis Standard", encoding="utf-8")

        rss = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Feed 1</title>
    <item>
      <title>Rookie group teaser gains traction</title>
      <link>https://feed.test/rookie-teaser</link>
      <description>The teaser clip is spreading across fan communities. Continue reading Rookie group teaser gains traction The post Rookie group teaser gains traction appeared first on Feed 1.</description>
      <pubDate>Fri, 11 Apr 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Actor casting debate keeps growing</title>
      <link>https://feed.test/actor-casting</link>
      <description>Discussion is splitting between media coverage and social chatter.</description>
      <pubDate>Fri, 11 Apr 2026 09:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

        translator = lambda text: {
            "Rookie group teaser gains traction": "新人组合预告片开始升温",
            "The teaser clip is spreading across fan communities.": "预告片正在粉丝社区快速扩散。",
            "Actor casting debate keeps growing": "演员选角争议持续升温",
            "Discussion is splitting between media coverage and social chatter.": "媒体报道与社交讨论开始出现分叉。",
        }.get(text, f"译文：{text}")

        service = IntelligenceService(root, fetcher=lambda url: rss, translator=translator)
        digest = service.generate_digest("k-entertainment", prefer_live=True)

        self.assertIn("新人组合预告片开始升温", digest.markdown)
        self.assertNotIn("### 1.", digest.markdown)
        self.assertIn("预告片正在粉丝社区快速扩散。", digest.markdown)
        self.assertIn("┌─ **【简讯1】", digest.markdown)
        self.assertIn("演员选角争议持续升温", digest.markdown)
        self.assertIn("A. 详细分析指定今日简讯", digest.markdown)
        self.assertIn("B. 创建新的事件线", digest.markdown)
        self.assertIn("C. 调整简讯和事件线的获取策略", digest.markdown)
        self.assertIn("│ 信源：[feed.test](https://feed.test/rookie-teaser)", digest.markdown)
        self.assertNotIn("Continue reading", digest.markdown)
        self.assertNotIn("appeared first on", digest.markdown)

    @staticmethod
    def _make_root(name: str) -> Path:
        root = TEST_TEMP_ROOT / name
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _write_topic(root: Path) -> None:
        topic_dir = root / "topics" / "k-entertainment"
        topic_dir.mkdir(parents=True)
        (topic_dir / "topic.json").write_text(
            json.dumps(
                {
                    "topic": "k-entertainment",
                    "name": "K-Entertainment",
                    "description": "韩国娱乐舆情追踪",
                    "language": "zh-CN",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (topic_dir / "brief.json").write_text(
            json.dumps({"requests": [{"req": "REQ-001", "content": "最近新火起来的 kpop 练习生"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (topic_dir / "sources.json").write_text(json.dumps({"sources": []}, ensure_ascii=False), encoding="utf-8")
        (topic_dir / "digest.md").write_text("# Digest Standard", encoding="utf-8")
        (topic_dir / "deep-analysis.md").write_text("# Deep Analysis Standard", encoding="utf-8")

    @staticmethod
    def _write_new_energy_topic(root: Path) -> None:
        topic_dir = root / "topics" / "new-energy-vehicles"
        topic_dir.mkdir(parents=True)
        (topic_dir / "topic.json").write_text(
            json.dumps(
                {
                    "topic": "new-energy-vehicles",
                    "name": "新能源汽车",
                    "description": "新能源汽车",
                    "language": "zh-CN",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (topic_dir / "brief.json").write_text(
            json.dumps({"requests": [{"req": "REQ-001", "content": "追踪新能源汽车的重要动态"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (topic_dir / "sources.json").write_text(json.dumps({"sources": []}, ensure_ascii=False), encoding="utf-8")
        (topic_dir / "digest.md").write_text("# Digest Standard", encoding="utf-8")
        (topic_dir / "deep-analysis.md").write_text("# Deep Analysis Standard", encoding="utf-8")

    @staticmethod
    def _write_byd_event_thread(root: Path) -> None:
        artifact_dir = root / "runs" / "new-energy-vehicles" / "event-threads"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        example_path = ROOT / "docs" / "byd-flash-charge-event-thread.example.json"
        payload = json.loads(example_path.read_text(encoding="utf-8"))
        (artifact_dir / "latest-event-threads.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _write_byd_event_thread_seed(root: Path) -> None:
        topic_dir = root / "topics" / "new-energy-vehicles"
        payload = json.loads((ROOT / "docs" / "byd-flash-charge-event-thread-seed.example.json").read_text(encoding="utf-8"))
        (topic_dir / "event-thread-seeds.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _write_byd_digest_event_index(root: Path, items: list[dict]) -> None:
        artifact_dir = root / "runs" / "new-energy-vehicles"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "topic": "new-energy-vehicles",
            "items": items,
        }
        (artifact_dir / "latest-digest-events.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _write_sample_events(root: Path) -> None:
        topic_dir = root / "topics" / "k-entertainment"
        events = [
            {
                "key": "trainee-ins",
                "title": "某女团练习生出圈片段从 INS 扩散到韩媒，开始被当作“新面孔”集中讨论",
                "headline_summary": "过去 24 小时里，这位练习生的短视频片段先在 INS 和短视频搬运账号发酵，随后被娱乐媒体整理成“下一位值得关注的新人”话题。现在已经不再是单点热帖，而是进入了媒体跟进阶段。",
                "list_summary": "某男团成员个人账号更新引发造型讨论，暂时还是社媒层面的轻量热度。",
                "analysis_title": "某女团练习生出圈片段扩散",
                "analysis_body": "这起事件目前仍处在早期升温阶段，核心看点不在单条内容，而在于它已经出现了从社媒扩散到媒体跟进的迹象。",
                "sources": ["https://source.test/trainee-1"],
            },
            {
                "key": "survival-lineup",
                "title": "某选秀节目未官宣阵容提前泄露，讨论从路透转向“谁会被节目带火”",
                "headline_summary": "最开始只是路透和录制传闻，今天已经出现多家媒体整理版阵容猜测，讨论重点从真假转向潜在受益者。",
                "list_summary": "某新剧配角演员因花絮片段突然被讨论，尚未进入主流媒体集中报道。",
                "analysis_title": "某选秀节目阵容泄露",
                "analysis_body": "目前更像是前哨事件而不是结论性事件，后续要看节目物料和正式官宣是否跟上。",
                "sources": ["https://source.test/show-1"],
            },
            {
                "key": "actor-casting",
                "title": "某演员与新剧选角争议升温，媒体报道和社媒情绪开始出现明显分叉",
                "headline_summary": "主流媒体目前更多围绕档期、制作和市场预期在写，但社交平台讨论已经转向历史争议和是否适合出演。两边叙事开始分裂，事件还在发酵。",
                "list_summary": "某女演员出席活动的现场图扩散很快，但事件性偏弱，先观察是否继续发酵。",
                "analysis_title": "某演员与新剧选角争议升温，媒体报道和社媒情绪开始出现明显分叉",
                "analysis_body": "这起事件目前已经从普通选角讨论升级成媒体叙事与社交情绪并行的争议事件。已知事实主要集中在选角本身和项目推进状态，真正存在分歧的是这次争议会不会进一步影响作品声量和演员口碑。",
                "sources": [
                    "https://source.test/actor-casting-1",
                    "https://source.test/actor-casting-2",
                ],
            },
            {
                "key": "old-mv-revival",
                "title": "海外 K-pop 圈突然带火一支旧 MV，中文讨论开始跟进，作品二次爆发迹象明显",
                "headline_summary": "原本是海外社媒的怀旧传播，今天中文站点和英文媒体都开始出现“为什么突然又红了”的整理内容。现在看起来不像单纯回忆杀，更像一次真实的二次传播。",
                "list_summary": "某组合回归 teaser 时间疑似提前泄露，已出现少量站点整理。",
                "analysis_title": "某旧 MV 海外带火后二次传播",
                "analysis_body": "二次传播是否会演变成艺人整体热度回升，取决于后续是否有更多主流媒体和中文社区持续跟进。",
                "sources": ["https://source.test/mv-1"],
            },
            {
                "key": "variety-teaser",
                "title": "某综艺录制现场相关话题持续升温，节目内容尚未公开但嘉宾互动已引发讨论",
                "headline_summary": "目前还没有正式播出内容，但相关录制图、现场互动和二次传播内容已经让讨论热起来。对节目本身来说，这属于播出前非常典型的热度前哨。",
                "list_summary": "某海外采访片段被搬运后在中文社区升温，核心仍是旧话题翻热。",
                "analysis_title": "某综艺录制现场话题升温",
                "analysis_body": "当前仍是前哨热度，真正要看的是不是今天多热，而是官方内容上线后能不能接住。",
                "sources": ["https://source.test/variety-1"],
            },
            {
                "key": "list-6",
                "title": "某男团成员个人账号更新引发造型讨论",
                "headline_summary": "",
                "list_summary": "某男团成员个人账号更新引发造型讨论，暂时还是社媒层面的轻量热度。",
                "analysis_title": "某男团成员个人账号更新引发造型讨论",
                "analysis_body": "当前热度仍偏轻，更多是造型和个人状态讨论，事件性不强。",
                "sources": ["https://source.test/list-6"],
            },
        ]
        (topic_dir / "sample-events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
