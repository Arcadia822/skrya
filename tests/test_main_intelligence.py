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
        self.assertIn("1. 鏌愬コ鍥㈢粌涔犵敓鍑哄湀鐗囨浠?INS 鎵╂暎鍒伴煩濯?, output)
        self.assertNotIn("### 1.", output)
        self.assertIn("濡傛灉浣犺缁х画锛屾垜鍙互鐩存帴瀵瑰叾涓换鎰忎竴鏉″仛娣卞叆鍒嗘瀽锛屼綘鍥炲缂栧彿灏辫銆?, output)

    def test_deep_analysis_command_accepts_event_number(self) -> None:
        root = self._make_root("cli-deep-analysis")
        self._write_topic(root)
        self._write_sample_events(root)

        with patch("sys.argv", ["skrya", "digest", "--topic", "k-entertainment", "--root", str(root)]):
            main()

        stdout = io.StringIO()
        with patch(
            "sys.argv",
            ["skrya", "deep-analysis", "--topic", "k-entertainment", "--root", str(root), "--event-number", "3"],
        ):
            with redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(0, exit_code)
        self.assertIn("鏌愭紨鍛樹笌鏂板墽閫夎浜夎鍗囨俯", stdout.getvalue())

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
                    "description": "闊╁浗濞变箰鑸嗘儏杩借釜",
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
    def _write_sample_events(root: Path) -> None:
        topic_dir = root / "topics" / "k-entertainment"
        events = [
            {
                "key": "trainee-ins",
                "title": "鏌愬コ鍥㈢粌涔犵敓鍑哄湀鐗囨浠?INS 鎵╂暎鍒伴煩濯掞紝寮€濮嬭褰撲綔鈥滄柊闈㈠瓟鈥濋泦涓璁?,
                "headline_summary": "杩囧幓 24 灏忔椂閲岋紝杩欎綅缁冧範鐢熺殑鐭棰戠墖娈靛厛鍦?INS 鍜屾惉杩愯处鍙峰彂閰碉紝闅忓悗琚ū涔愬獟浣撴暣鐞嗘垚鈥滀笅涓€浣嶅€煎緱鍏虫敞鐨勬柊浜衡€濊瘽棰樸€?,
                "list_summary": "鏌愮敺鍥㈡垚鍛樹釜浜鸿处鍙锋洿鏂板紩鍙戦€犲瀷璁ㄨ锛屾殏鏃惰繕鏄ぞ濯掑眰闈㈢殑杞婚噺鐑害銆?,
                "analysis_title": "鏌愬コ鍥㈢粌涔犵敓鍑哄湀鐗囨鎵╂暎",
                "analysis_body": "杩欒捣浜嬩欢鐩墠浠嶅鍦ㄦ棭鏈熷崌娓╅樁娈点€?,
                "sources": ["https://source.test/trainee-1"],
            },
            {
                "key": "survival-lineup",
                "title": "鏌愰€夌鑺傜洰鏈畼瀹ｉ樀瀹规彁鍓嶆硠闇诧紝璁ㄨ浠庤矾閫忚浆鍚戔€滆皝浼氳鑺傜洰甯︾伀鈥?,
                "headline_summary": "鏈€寮€濮嬪彧鏄矾閫忓拰褰曞埗浼犻椈锛屼粖澶╁凡缁忓嚭鐜板瀹跺獟浣撴暣鐞嗙増闃靛鐚滄祴銆?,
                "list_summary": "鏌愭柊鍓ч厤瑙掓紨鍛樺洜鑺辩诞鐗囨绐佺劧琚璁猴紝灏氭湭杩涘叆涓绘祦濯掍綋闆嗕腑鎶ラ亾銆?,
                "analysis_title": "鏌愰€夌鑺傜洰闃靛娉勯湶",
                "analysis_body": "鐩墠鏇村儚鏄墠鍝ㄤ簨浠惰€屼笉鏄粨璁烘€т簨浠躲€?,
                "sources": ["https://source.test/show-1"],
            },
            {
                "key": "actor-casting",
                "title": "鏌愭紨鍛樹笌鏂板墽閫夎浜夎鍗囨俯锛屽獟浣撴姤閬撳拰绀惧獟鎯呯华寮€濮嬪嚭鐜版槑鏄惧垎鍙?,
                "headline_summary": "涓绘祦濯掍綋鏇村鍥寸粫妗ｆ湡銆佸埗浣滃拰甯傚満棰勬湡鍦ㄥ啓锛屼絾绀句氦骞冲彴璁ㄨ宸茬粡杞悜鍘嗗彶浜夎鍜屾槸鍚﹂€傚悎鍑烘紨銆?,
                "list_summary": "鏌愬コ婕斿憳鍑哄腑娲诲姩鐨勭幇鍦哄浘鎵╂暎寰堝揩锛屼絾浜嬩欢鎬у亸寮便€?,
                "analysis_title": "鏌愭紨鍛樹笌鏂板墽閫夎浜夎鍗囨俯锛屽獟浣撴姤閬撳拰绀惧獟鎯呯华寮€濮嬪嚭鐜版槑鏄惧垎鍙?,
                "analysis_body": "杩欒捣浜嬩欢鐩墠宸茬粡浠庢櫘閫氶€夎璁ㄨ鍗囩骇鎴愬獟浣撳彊浜嬩笌绀句氦鎯呯华骞惰鐨勪簤璁簨浠躲€?,
                "sources": ["https://source.test/actor-casting-1", "https://source.test/actor-casting-2"],
            },
        ]
        (topic_dir / "sample-events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
