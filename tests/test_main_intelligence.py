import io
import json
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from skrya_orchestrator.main import main


ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = ROOT / "tmp" / "unit-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class MainIntelligenceCommandTests(unittest.TestCase):
    def test_digest_command_prints_markdown(self) -> None:
        root = self._make_root("cli-digest")
        self._write_topic(root)
        self._write_sample_events(root)

        stdout = io.StringIO()
        with patch("sys.argv", ["skrya", "digest", "--topic", "k-entertainment", "--root", str(root)]):
            with redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(0, exit_code)
        output = stdout.getvalue()
        self.assertIn("┌─ **【简讯1】", output)
        self.assertIn("某演员与新剧选角争议升温", output)
        self.assertIn("┌─ **【简讯2】", output)
        self.assertIn("某女团练习生出圈片段从 INS 扩散到韩媒", output)
        self.assertIn("│ 信源：[source.test]", output)
        self.assertNotIn("### 1.", output)
        self.assertIn("A. 详细分析指定今日简讯", output)
        self.assertIn("B. 创建新的事件线", output)
        self.assertIn("## 系统提示", output)
        self.assertIn("C. 调整简讯和事件线的获取策略", output)

    def test_digest_command_sample_mode_uses_fixture_events_for_demo_topic(self) -> None:
        root = self._make_root("cli-digest-sample")
        self._copy_new_energy_topic_fixture(root)

        stdout = io.StringIO()
        with patch(
            "sys.argv",
            ["skrya", "digest", "--topic", "new-energy-vehicles", "--root", str(root), "--sample"],
        ):
            with redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(0, exit_code)
        output = stdout.getvalue()
        self.assertIn("## 事件线更新", output)
        self.assertIn("┌─ **【事件线】比亚迪闪充站**", output)
        self.assertNotIn("今天命中的简讯：", output)
        self.assertIn("## 今日简讯", output)
        self.assertTrue((root / "runs" / "new-energy-vehicles" / "latest-digest-events.json").exists())
        self.assertTrue(
            (root / "runs" / "new-energy-vehicles" / "event-threads" / "latest-event-threads.json").exists()
        )

    def test_event_thread_command_replays_timeline_after_sample_digest(self) -> None:
        root = self._make_root("cli-event-thread-after-digest")
        self._copy_new_energy_topic_fixture(root)

        with patch(
            "sys.argv",
            ["skrya", "digest", "--topic", "new-energy-vehicles", "--root", str(root), "--sample"],
        ):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main())

        stdout = io.StringIO()
        with patch(
            "sys.argv",
            ["skrya", "event-thread", "--topic", "new-energy-vehicles", "--thread", "比亚迪闪充站", "--root", str(root)],
        ):
            with redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(0, exit_code)
        output = stdout.getvalue()
        self.assertIn("# 比亚迪闪充站", output)
        self.assertIn("## 时间线", output)
        self.assertIn("关联日报：", output)
        self.assertNotIn("https://example.com", output)

    def test_deep_analysis_command_accepts_event_number(self) -> None:
        root = self._make_root("cli-deep-analysis")
        self._write_topic(root)
        self._write_sample_events(root)

        with patch("sys.argv", ["skrya", "digest", "--topic", "k-entertainment", "--root", str(root)]):
            with redirect_stdout(io.StringIO()):
                main()

        stdout = io.StringIO()
        with patch(
            "sys.argv",
            ["skrya", "deep-analysis", "--topic", "k-entertainment", "--root", str(root), "--event-number", "1"],
        ):
            with redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(0, exit_code)
        self.assertIn("某演员与新剧选角争议升温", stdout.getvalue())

    def test_event_thread_command_prints_timeline_for_visible_thread_name(self) -> None:
        root = self._make_root("cli-event-thread")
        self._write_new_energy_topic(root)
        self._write_byd_event_thread(root)

        stdout = io.StringIO()
        with patch(
            "sys.argv",
            ["skrya", "event-thread", "--topic", "新能源汽车", "--thread", "比亚迪闪充站", "--root", str(root)],
        ):
            with redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(0, exit_code)
        self.assertIn("# 比亚迪闪充站", stdout.getvalue())
        self.assertIn("## 时间线", stdout.getvalue())
        self.assertIn("2026-04-27 · 进展续写", stdout.getvalue())
        self.assertNotIn("https://example.com", stdout.getvalue())

    def test_refresh_event_threads_command_writes_runtime_artifact(self) -> None:
        root = self._make_root("cli-refresh-event-threads")
        self._write_new_energy_topic(root)
        self._write_byd_event_thread_seed(root)
        self._write_byd_digest_event_index(root)

        stdout = io.StringIO()
        with patch(
            "sys.argv",
            ["skrya", "refresh-event-threads", "--topic", "新能源汽车", "--root", str(root)],
        ):
            with redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(0, exit_code)
        artifact_path = root / "runs" / "new-energy-vehicles" / "event-threads" / "latest-event-threads.json"
        self.assertTrue(artifact_path.exists())
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual("比亚迪闪充站", payload["threads"][0]["name"])
        self.assertIn("latest-event-threads.json", stdout.getvalue())

    def test_retrieval_request_command_prints_provider_neutral_request(self) -> None:
        root = self._make_root("cli-retrieval-request")
        self._write_topic(root)
        topic_dir = root / "topics" / "k-entertainment"
        (topic_dir / "sources.json").write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "id": "public-web-k-entertainment",
                            "name": "公开网页检索",
                            "type": "runtime-retrieval",
                            "enabled": True,
                            "capabilities": ["web_search", "news_search"],
                            "binding": "runtime",
                            "queries": ["kpop contract controversy"],
                            "languages": ["zh-CN", "en"],
                            "max_items": 20,
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with patch("sys.argv", ["skrya", "retrieval-request", "--topic", "k-entertainment", "--root", str(root)]):
            with redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(0, exit_code)
        payload = json.loads(stdout.getvalue())
        self.assertEqual("skrya.retrieval-request.v1", payload["interface_version"])
        self.assertEqual(["web_search", "news_search"], payload["capabilities"])
        self.assertNotIn("agent-reach", stdout.getvalue())

    def test_ingest_command_records_normalized_ingest(self) -> None:
        root = self._make_root("cli-ingest")
        self._write_topic(root)
        payload_path = root / "ingest.json"
        payload_path.write_text(
            json.dumps(
                {
                    "interface_version": "skrya.ingest.v1",
                    "topic_id": "k-entertainment",
                    "retrieved_at": "2026-04-25T10:30:00+08:00",
                    "producer": {"kind": "runtime-skill", "name": "agent-reach", "persistent": False},
                    "items": [
                        {
                            "title": "K-pop contract dispute update",
                            "url": "https://example.com/kpop-contract",
                            "source_name": "Example",
                            "fetched_at": "2026-04-25T10:29:00+08:00",
                            "summary": "A contract dispute has a new company response.",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with patch(
            "sys.argv",
            ["skrya", "ingest", "--topic", "k-entertainment", "--root", str(root), "--file", str(payload_path)],
        ):
            with redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(0, exit_code)
        latest_path = root / "runs" / "k-entertainment" / "ingest" / "latest-ingest.json"
        self.assertTrue(latest_path.exists())
        self.assertIn("latest-ingest.json", stdout.getvalue())

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
        (topic_dir / "brief.json").write_text(json.dumps({"requests": []}, ensure_ascii=False), encoding="utf-8")
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
        (topic_dir / "brief.json").write_text(json.dumps({"requests": []}, ensure_ascii=False), encoding="utf-8")
        (topic_dir / "sources.json").write_text(json.dumps({"sources": []}, ensure_ascii=False), encoding="utf-8")
        (topic_dir / "digest.md").write_text("# Digest Standard", encoding="utf-8")
        (topic_dir / "deep-analysis.md").write_text("# Deep Analysis Standard", encoding="utf-8")

    @staticmethod
    def _write_byd_event_thread(root: Path) -> None:
        artifact_dir = root / "runs" / "new-energy-vehicles" / "event-threads"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        payload = json.loads((ROOT / "docs" / "byd-flash-charge-event-thread.example.json").read_text(encoding="utf-8"))
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
    def _write_byd_digest_event_index(root: Path) -> None:
        artifact_dir = root / "runs" / "new-energy-vehicles"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "topic": "new-energy-vehicles",
            "items": [
                {
                    "number": 2,
                    "title": "比亚迪闪充站从发布概念进入首批落地讨论",
                    "analysis_title": "比亚迪闪充站从发布概念进入首批落地讨论",
                    "analysis_body": "这条线开始从产品能力展示，推进到站点建设节奏、城市覆盖和补能体验是否可验证的讨论。",
                    "sources": ["https://example.com/byd-flash-charge-launch"],
                    "date": "2026-04-25",
                }
            ],
        }
        (artifact_dir / "latest-digest-events.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _copy_new_energy_topic_fixture(root: Path) -> None:
        destination = root / "topics" / "new-energy-vehicles"
        shutil.copytree(ROOT / "topics" / "new-energy-vehicles", destination)

    @staticmethod
    def _write_sample_events(root: Path) -> None:
        topic_dir = root / "topics" / "k-entertainment"
        events = [
            {
                "key": "trainee-ins",
                "title": "某女团练习生出圈片段从 INS 扩散到韩媒，开始被当作“新面孔”集中讨论",
                "headline_summary": "过去 24 小时里，这位练习生的短视频片段先在 INS 和搬运账号发酵，随后被娱乐媒体整理成“下一位值得关注的新人”话题。",
                "list_summary": "某男团成员个人账号更新引发造型讨论，暂时还是社媒层面的轻量热度。",
                "analysis_title": "某女团练习生出圈片段扩散",
                "analysis_body": "这起事件目前仍处在早期升温阶段。",
                "sources": ["https://source.test/trainee-1"],
            },
            {
                "key": "survival-lineup",
                "title": "某选秀节目未官宣阵容提前泄露，讨论从路透转向“谁会被节目带火”",
                "headline_summary": "最开始只是路透和录制传闻，今天已经出现多家媒体整理版阵容猜测。",
                "list_summary": "某新剧配角演员因花絮片段突然被讨论，尚未进入主流媒体集中报道。",
                "analysis_title": "某选秀节目阵容泄露",
                "analysis_body": "目前更像是前哨事件而不是结论性事件。",
                "sources": ["https://source.test/show-1"],
            },
            {
                "key": "actor-casting",
                "title": "某演员与新剧选角争议升温，媒体报道和社媒情绪开始出现明显分叉",
                "headline_summary": "主流媒体更多围绕档期、制作和市场预期在写，但社交平台讨论已经转向历史争议和是否适合出演。",
                "list_summary": "某女演员出席活动的现场图扩散很快，但事件性偏弱。",
                "analysis_title": "某演员与新剧选角争议升温，媒体报道和社媒情绪开始出现明显分叉",
                "analysis_body": "这起事件目前已经从普通选角讨论升级成媒体叙事与社交情绪并行的争议事件。",
                "sources": ["https://source.test/actor-casting-1", "https://source.test/actor-casting-2"],
            },
        ]
        (topic_dir / "sample-events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
