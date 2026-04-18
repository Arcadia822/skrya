import json
import shutil
import unittest
from pathlib import Path

from skrya_orchestrator.intelligence import IntelligenceService


ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = ROOT / "tmp" / "unit-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class IntelligenceServiceTests(unittest.TestCase):
    def test_generate_digest_writes_all_items_as_single_paragraph_numbered_entries(self) -> None:
        root = self._make_root("digest-output")
        self._write_topic(root)
        self._write_sample_events(root)

        service = IntelligenceService(root)
        digest = service.generate_digest("k-entertainment")

        self.assertIn("1. 鏌愬コ鍥㈢粌涔犵敓鍑哄湀鐗囨浠?INS 鎵╂暎鍒伴煩濯?, digest.markdown)
        self.assertNotIn("### 1.", digest.markdown)
        self.assertIn("6. 鏌愮敺鍥㈡垚鍛樹釜浜鸿处鍙锋洿鏂板紩鍙戦€犲瀷璁ㄨ", digest.markdown)
        self.assertNotIn("涓枃瀵艰锛?, digest.markdown)
        self.assertNotIn("Top 5 蹇呯湅", digest.markdown)
        self.assertNotIn("浠婃棩瑙傚療", digest.markdown)
        self.assertNotIn("寤鸿娣辨寲", digest.markdown)
        self.assertIn("濡傛灉浣犺缁х画锛屾垜鍙互鐩存帴瀵瑰叾涓换鎰忎竴鏉″仛娣卞叆鍒嗘瀽锛屼綘鍥炲缂栧彿灏辫銆?, digest.markdown)
        self.assertNotIn("$deep-analysis", digest.markdown)
        self.assertNotIn("REQ-001", digest.markdown)
        self.assertNotIn("https://source.test", digest.markdown)
        self.assertTrue(digest.digest_path.exists())
        self.assertTrue(digest.artifact_path.exists())

    def test_deep_analysis_resolves_digest_item_number_and_hides_sources_by_default(self) -> None:
        root = self._make_root("deep-analysis")
        self._write_topic(root)
        self._write_sample_events(root)

        service = IntelligenceService(root)
        service.generate_digest("k-entertainment")

        analysis = service.generate_deep_analysis("k-entertainment", event_number=3)

        self.assertIn("鏌愭紨鍛樹笌鏂板墽閫夎浜夎鍗囨俯", analysis.markdown)
        self.assertIn("濯掍綋鎶ラ亾鍜岀ぞ濯掓儏缁紑濮嬪嚭鐜版槑鏄惧垎鍙?, analysis.markdown)
        self.assertNotIn("涓枃鍒ゆ柇锛?, analysis.markdown)
        self.assertNotIn("https://source.test", analysis.markdown)

    def test_deep_analysis_sources_are_available_on_demand(self) -> None:
        root = self._make_root("sources-on-demand")
        self._write_topic(root)
        self._write_sample_events(root)

        service = IntelligenceService(root)
        service.generate_digest("k-entertainment")

        sources = service.get_event_sources("k-entertainment", event_number=3)

        self.assertEqual(
            [
                "https://source.test/actor-casting-1",
                "https://source.test/actor-casting-2",
            ],
            sources,
        )

    def test_generate_digest_fetches_real_rss_when_sample_events_are_absent(self) -> None:
        root = self._make_root("live-rss")
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
        (topic_dir / "brief.json").write_text(
            json.dumps({"requests": [{"req": "REQ-001", "content": "闊╁浗濞变箰鐑偣"}]}, ensure_ascii=False),
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
            "Rookie group teaser gains traction": "鏂颁汉缁勫悎棰勫憡鐗囧紑濮嬪崌娓?,
            "The teaser clip is spreading across fan communities.": "棰勫憡鐗囨鍦ㄧ矇涓濈ぞ鍖哄揩閫熸墿鏁ｃ€?,
            "Actor casting debate keeps growing": "婕斿憳閫夎浜夎鎸佺画鍗囨俯",
            "Discussion is splitting between media coverage and social chatter.": "濯掍綋鎶ラ亾涓庣ぞ浜よ璁哄紑濮嬪嚭鐜板垎鍙夈€?,
        }.get(text, f"璇戞枃锛歿text}")

        service = IntelligenceService(root, fetcher=lambda url: rss, translator=translator)
        digest = service.generate_digest("k-entertainment", prefer_live=True)

        self.assertIn("1. 鏂颁汉缁勫悎棰勫憡鐗囧紑濮嬪崌娓?, digest.markdown)
        self.assertNotIn("### 1.", digest.markdown)
        self.assertIn("棰勫憡鐗囨鍦ㄧ矇涓濈ぞ鍖哄揩閫熸墿鏁ｃ€?, digest.markdown)
        self.assertIn("婕斿憳閫夎浜夎鎸佺画鍗囨俯", digest.markdown)
        self.assertIn("濡傛灉浣犺缁х画锛屾垜鍙互鐩存帴瀵瑰叾涓换鎰忎竴鏉″仛娣卞叆鍒嗘瀽锛屼綘鍥炲缂栧彿灏辫銆?, digest.markdown)
        self.assertNotIn("https://feed.test/rookie-teaser", digest.markdown)
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
                    "description": "闊╁浗濞变箰鑸嗘儏杩借釜",
                    "language": "zh-CN",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (topic_dir / "brief.json").write_text(
            json.dumps({"requests": [{"req": "REQ-001", "content": "鏈€杩戞柊鐏捣鏉ョ殑 kpop 缁冧範鐢?}]}, ensure_ascii=False),
            encoding="utf-8",
        )
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
                "headline_summary": "杩囧幓 24 灏忔椂閲岋紝杩欎綅缁冧範鐢熺殑鐭棰戠墖娈靛厛鍦?INS 鍜岀煭瑙嗛鎼繍璐﹀彿鍙戦叺锛岄殢鍚庤濞变箰濯掍綋鏁寸悊鎴愨€滀笅涓€浣嶅€煎緱鍏虫敞鐨勬柊浜衡€濊瘽棰樸€傜幇鍦ㄥ凡缁忎笉鍐嶆槸鍗曠偣鐑笘锛岃€屾槸杩涘叆浜嗗獟浣撹窡杩涢樁娈点€?,
                "list_summary": "鏌愮敺鍥㈡垚鍛樹釜浜鸿处鍙锋洿鏂板紩鍙戦€犲瀷璁ㄨ锛屾殏鏃惰繕鏄ぞ濯掑眰闈㈢殑杞婚噺鐑害銆?,
                "analysis_title": "鏌愬コ鍥㈢粌涔犵敓鍑哄湀鐗囨鎵╂暎",
                "analysis_body": "杩欒捣浜嬩欢鐩墠浠嶅鍦ㄦ棭鏈熷崌娓╅樁娈碉紝鏍稿績鐪嬬偣涓嶅湪鍗曟潯鍐呭锛岃€屽湪浜庡畠宸茬粡鍑虹幇浜嗕粠绀惧獟鎵╂暎鍒板獟浣撹窡杩涚殑杩硅薄銆?,
                "sources": ["https://source.test/trainee-1"],
            },
            {
                "key": "survival-lineup",
                "title": "鏌愰€夌鑺傜洰鏈畼瀹ｉ樀瀹规彁鍓嶆硠闇诧紝璁ㄨ浠庤矾閫忚浆鍚戔€滆皝浼氳鑺傜洰甯︾伀鈥?,
                "headline_summary": "鏈€寮€濮嬪彧鏄矾閫忓拰褰曞埗浼犻椈锛屼粖澶╁凡缁忓嚭鐜板瀹跺獟浣撴暣鐞嗙増闃靛鐚滄祴锛岃璁洪噸鐐逛粠鐪熷亣杞悜娼滃湪鍙楃泭鑰呫€?,
                "list_summary": "鏌愭柊鍓ч厤瑙掓紨鍛樺洜鑺辩诞鐗囨绐佺劧琚璁猴紝灏氭湭杩涘叆涓绘祦濯掍綋闆嗕腑鎶ラ亾銆?,
                "analysis_title": "鏌愰€夌鑺傜洰闃靛娉勯湶",
                "analysis_body": "鐩墠鏇村儚鏄墠鍝ㄤ簨浠惰€屼笉鏄粨璁烘€т簨浠讹紝鍚庣画瑕佺湅鑺傜洰鐗╂枡鍜屾寮忓畼瀹ｆ槸鍚﹁窡涓娿€?,
                "sources": ["https://source.test/show-1"],
            },
            {
                "key": "actor-casting",
                "title": "鏌愭紨鍛樹笌鏂板墽閫夎浜夎鍗囨俯锛屽獟浣撴姤閬撳拰绀惧獟鎯呯华寮€濮嬪嚭鐜版槑鏄惧垎鍙?,
                "headline_summary": "涓绘祦濯掍綋鐩墠鏇村鍥寸粫妗ｆ湡銆佸埗浣滃拰甯傚満棰勬湡鍦ㄥ啓锛屼絾绀句氦骞冲彴璁ㄨ宸茬粡杞悜鍘嗗彶浜夎鍜屾槸鍚﹂€傚悎鍑烘紨銆備袱杈瑰彊浜嬪紑濮嬪垎瑁傦紝浜嬩欢杩樺湪鍙戦叺銆?,
                "list_summary": "鏌愬コ婕斿憳鍑哄腑娲诲姩鐨勭幇鍦哄浘鎵╂暎寰堝揩锛屼絾浜嬩欢鎬у亸寮憋紝鍏堣瀵熸槸鍚︾户缁彂閰点€?,
                "analysis_title": "鏌愭紨鍛樹笌鏂板墽閫夎浜夎鍗囨俯锛屽獟浣撴姤閬撳拰绀惧獟鎯呯华寮€濮嬪嚭鐜版槑鏄惧垎鍙?,
                "analysis_body": "杩欒捣浜嬩欢鐩墠宸茬粡浠庢櫘閫氶€夎璁ㄨ鍗囩骇鎴愬獟浣撳彊浜嬩笌绀句氦鎯呯华骞惰鐨勪簤璁簨浠躲€傚凡鐭ヤ簨瀹炰富瑕侀泦涓湪閫夎鏈韩鍜岄」鐩帹杩涚姸鎬侊紝鐪熸瀛樺湪鍒嗘鐨勬槸杩欐浜夎浼氫笉浼氳繘涓€姝ュ奖鍝嶄綔鍝佸０閲忓拰婕斿憳鍙ｇ銆?,
                "sources": [
                    "https://source.test/actor-casting-1",
                    "https://source.test/actor-casting-2",
                ],
            },
            {
                "key": "old-mv-revival",
                "title": "娴峰 K-pop 鍦堢獊鐒跺甫鐏竴鏀棫 MV锛屼腑鏂囪璁哄紑濮嬭窡杩涳紝浣滃搧浜屾鐖嗗彂杩硅薄鏄庢樉",
                "headline_summary": "鍘熸湰鏄捣澶栫ぞ濯掔殑鎬€鏃т紶鎾紝浠婂ぉ涓枃绔欑偣鍜岃嫳鏂囧獟浣撻兘寮€濮嬪嚭鐜扳€滀负浠€涔堢獊鐒跺張绾簡鈥濈殑鏁寸悊鍐呭銆傜幇鍦ㄧ湅璧锋潵涓嶅儚鍗曠函鍥炲繂鏉€锛屾洿鍍忎竴娆＄湡瀹炵殑浜屾浼犳挱銆?,
                "list_summary": "鏌愮粍鍚堝洖褰?teaser 鏃堕棿鐤戜技鎻愬墠娉勯湶锛屽凡鍑虹幇灏戦噺绔欑偣鏁寸悊銆?,
                "analysis_title": "鏌愭棫 MV 娴峰甯︾伀鍚庝簩娆′紶鎾?,
                "analysis_body": "浜屾浼犳挱鏄惁浼氭紨鍙樻垚鑹轰汉鏁翠綋鐑害鍥炲崌锛屽彇鍐充簬鍚庣画鏄惁鏈夋洿澶氫富娴佸獟浣撳拰涓枃绀惧尯鎸佺画璺熻繘銆?,
                "sources": ["https://source.test/mv-1"],
            },
            {
                "key": "variety-teaser",
                "title": "鏌愮患鑹哄綍鍒剁幇鍦虹浉鍏宠瘽棰樻寔缁崌娓╋紝鑺傜洰鍐呭灏氭湭鍏紑浣嗗槈瀹句簰鍔ㄥ凡寮曞彂璁ㄨ",
                "headline_summary": "鐩墠杩樻病鏈夋寮忔挱鍑哄唴瀹癸紝浣嗙浉鍏冲綍鍒跺浘銆佺幇鍦轰簰鍔ㄥ拰浜屾浼犳挱鍐呭宸茬粡璁╄璁虹儹璧锋潵銆傚鑺傜洰鏈韩鏉ヨ锛岃繖灞炰簬鎾嚭鍓嶉潪甯稿吀鍨嬬殑鐑害鍓嶅摠銆?,
                "list_summary": "鏌愭捣澶栭噰璁跨墖娈佃鎼繍鍚庡湪涓枃绀惧尯鍗囨俯锛屾牳蹇冧粛鏄棫璇濋缈荤儹銆?,
                "analysis_title": "鏌愮患鑹哄綍鍒剁幇鍦鸿瘽棰樺崌娓?,
                "analysis_body": "褰撳墠浠嶆槸鍓嶅摠鐑害锛岀湡姝ｈ鐪嬬殑鏄笉鏄粖澶╁鐑紝鑰屾槸瀹樻柟鍐呭涓婄嚎鍚庤兘涓嶈兘鎺ヤ綇銆?,
                "sources": ["https://source.test/variety-1"],
            },
            {
                "key": "list-6",
                "title": "鏌愮敺鍥㈡垚鍛樹釜浜鸿处鍙锋洿鏂板紩鍙戦€犲瀷璁ㄨ",
                "headline_summary": "",
                "list_summary": "鏌愮敺鍥㈡垚鍛樹釜浜鸿处鍙锋洿鏂板紩鍙戦€犲瀷璁ㄨ锛屾殏鏃惰繕鏄ぞ濯掑眰闈㈢殑杞婚噺鐑害銆?,
                "analysis_title": "鏌愮敺鍥㈡垚鍛樹釜浜鸿处鍙锋洿鏂板紩鍙戦€犲瀷璁ㄨ",
                "analysis_body": "褰撳墠鐑害浠嶅亸杞伙紝鏇村鏄€犲瀷鍜屼釜浜虹姸鎬佽璁猴紝浜嬩欢鎬т笉寮恒€?,
                "sources": ["https://source.test/list-6"],
            },
        ]
        (topic_dir / "sample-events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
