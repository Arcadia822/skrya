from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from skrya_orchestrator.translation_cache import TranslationCache


class TranslationCacheTests(unittest.TestCase):
    def test_constructor_creates_no_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            cache = TranslationCache(data_root)
            self.assertEqual(cache.data_root, data_root.resolve(strict=False))
            self.assertFalse(data_root.exists())
            self.assertFalse((data_root / "cache").exists())

    def test_whitespace_normalization_cache_hit_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"

            calls = 0

            def translator(text: str) -> str:
                nonlocal calls
                calls += 1
                return "OpenAI 推出 ChatGPT 代理浏览器"

            instance1 = TranslationCache(data_root)
            result1 = instance1.translate(
                "  OpenAI   launches\nChatGPT agent\tbrowser  ",
                translator,
            )
            self.assertEqual(result1, "OpenAI 推出 ChatGPT 代理浏览器")
            self.assertEqual(calls, 1)

            def failing_translator(text: str) -> str:
                self.fail("Translator should not be called when cache hits")

            instance2 = TranslationCache(data_root)
            result2 = instance2.translate(
                "OpenAI launches ChatGPT agent browser",
                failing_translator,
            )
            self.assertEqual(result2, "OpenAI 推出 ChatGPT 代理浏览器")
            self.assertEqual(calls, 1)

    def test_provider_isolation_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            text = "Tesla delivers new vehicle model"

            instance1 = TranslationCache(data_root)
            res_google = instance1.translate(
                text,
                lambda t: "特斯拉交付新车型 (google)",
                provider="google-translate",
            )
            self.assertEqual(res_google, "特斯拉交付新车型 (google)")

            instance2 = TranslationCache(data_root)
            res_deepl = instance2.translate(
                text,
                lambda t: "特斯拉交付新车型 (deepl)",
                provider="deepl",
            )
            self.assertEqual(res_deepl, "特斯拉交付新车型 (deepl)")

            def forbidden_translator(t: str) -> str:
                self.fail("Translator invoked despite cached entry")

            instance3 = TranslationCache(data_root)
            cached_google = instance3.translate(
                text,
                forbidden_translator,
                provider="google-translate",
            )
            self.assertEqual(cached_google, "特斯拉交付新车型 (google)")

            cached_deepl = instance3.translate(
                text,
                forbidden_translator,
                provider="deepl",
            )
            self.assertEqual(cached_deepl, "特斯拉交付新车型 (deepl)")

    def test_target_language_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            text = "Good morning"

            cache = TranslationCache(data_root)
            res_zh = cache.translate(text, lambda t: "早上好", language="zh-CN")
            self.assertEqual(res_zh, "早上好")

            res_ja = cache.translate(text, lambda t: "おはよう", language="ja")
            self.assertEqual(res_ja, "おはよう")

            def forbidden(t: str) -> str:
                self.fail("Translator invoked despite cached entry")

            self.assertEqual(cache.translate(text, forbidden, language="zh-CN"), "早上好")
            self.assertEqual(cache.translate(text, forbidden, language="ja"), "おはよう")

    def test_read_only_translate_creates_no_files_or_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            cache = TranslationCache(data_root)

            result = cache.translate("Hello world", lambda t: "你好世界", write=False)
            self.assertEqual(result, "你好世界")
            self.assertFalse(data_root.exists())
            self.assertFalse((data_root / "cache").exists())

            written = cache.translate("Hello world", lambda t: "你好世界", write=True)
            self.assertEqual(written, "你好世界")
            h = TranslationCache.content_hash("Hello world")
            entry_file = data_root / "cache" / "translations" / "zh-CN" / "google-translate" / f"{h}.json"
            self.assertTrue(entry_file.is_file())
            stat_before = entry_file.stat()

            cached = cache.translate(
                "Hello world",
                lambda t: self.fail("Translator invoked"),
                write=False,
            )
            self.assertEqual(cached, "你好世界")
            stat_after = entry_file.stat()
            self.assertEqual(stat_before.st_mtime_ns, stat_after.st_mtime_ns)

    def test_empty_or_whitespace_text_passthrough(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            cache = TranslationCache(data_root)

            def failing(t: str) -> str:
                self.fail("Translator should not be called for empty or whitespace text")

            self.assertEqual(cache.translate("", failing), "")
            self.assertEqual(cache.translate("   \n\t  ", failing), "   \n\t  ")
            self.assertFalse(data_root.exists())

    def test_failure_does_not_poison_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            cache = TranslationCache(data_root)
            text = "Breaking industry news"

            def raise_error(t: str) -> str:
                raise RuntimeError("API rate limited")

            res1 = cache.translate(text, raise_error)
            self.assertEqual(res1, text)
            self.assertFalse((data_root / "cache").exists())

            res2 = cache.translate(text, lambda t: "")
            self.assertEqual(res2, text)
            self.assertFalse((data_root / "cache").exists())

            res3 = cache.translate(text, lambda t: "Breaking industry news")
            self.assertEqual(res3, text)
            self.assertFalse((data_root / "cache").exists())

            res4 = cache.translate(text, lambda t: "突发行业资讯")
            self.assertEqual(res4, "突发行业资讯")
            self.assertTrue((data_root / "cache").exists())

            res5 = cache.translate(text, raise_error)
            self.assertEqual(res5, "突发行业资讯")

    def test_corrupted_cache_tolerated_and_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            cache = TranslationCache(data_root)
            text = "System maintenance notice"

            h = TranslationCache.content_hash(text)
            bad_file = data_root / "cache" / "translations" / "zh-CN" / "google-translate" / f"{h}.json"
            bad_file.parent.mkdir(parents=True, exist_ok=True)
            bad_file.write_text("{corrupt-json-payload-truncated", encoding="utf-8")

            repaired = cache.translate(text, lambda t: "系统维护通知")
            self.assertEqual(repaired, "系统维护通知")

            payload = json.loads(bad_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["translated_text"], "系统维护通知")
            self.assertEqual(payload["content_hash"], h)

            cached = cache.translate(text, lambda t: self.fail("Cache should have hit"))
            self.assertEqual(cached, "系统维护通知")

    def test_targeted_clear_by_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            cache = TranslationCache(data_root)

            cache.translate("Title 1", lambda t: "标题1", language="zh-CN")
            cache.translate("Title 2", lambda t: "标题2", language="zh-CN")
            cache.translate("Title 1", lambda t: "Title 1 (en)", language="en")

            unrelated_file = data_root / "cache" / "translations" / "zh-CN" / "manual-note.txt"
            unrelated_file.write_text("keep me", encoding="utf-8")

            sibling_cache_file = data_root / "cache" / "http" / "response.xml"
            sibling_cache_file.parent.mkdir(parents=True, exist_ok=True)
            sibling_cache_file.write_text("<xml>response</xml>", encoding="utf-8")

            removed = cache.clear(language="zh-CN")
            self.assertEqual(removed, 2)

            self.assertTrue(unrelated_file.exists())
            self.assertTrue(sibling_cache_file.exists())

            en_h = TranslationCache.content_hash("Title 1")
            en_file = data_root / "cache" / "translations" / "en" / "google-translate" / f"{en_h}.json"
            self.assertTrue(en_file.is_file())

    def test_clear_all_owned_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            cache = TranslationCache(data_root)

            cache.translate("Title A", lambda t: "标题A", language="zh-CN")
            cache.translate("Title B", lambda t: "タイトルB", language="ja")

            sibling_cache_file = data_root / "cache" / "http" / "response.xml"
            sibling_cache_file.parent.mkdir(parents=True, exist_ok=True)
            sibling_cache_file.write_text("<xml>data</xml>", encoding="utf-8")

            removed = cache.clear()
            self.assertEqual(removed, 2)
            self.assertTrue(sibling_cache_file.exists())

            self.assertEqual(cache.clear(), 0)

    def test_filename_safety_and_path_traversal_prevention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            cache = TranslationCache(data_root)

            with self.assertRaises(ValueError):
                cache.translate("Hello", lambda t: "你好", language="../evil")

            with self.assertRaises(ValueError):
                cache.translate("Hello", lambda t: "你好", language="/etc/passwd")

            with self.assertRaises(ValueError):
                cache.clear(language="../evil")

            safe_result = cache.translate(
                "Hello",
                lambda t: "你好",
                provider="../../unsafe/path",
            )
            self.assertEqual(safe_result, "你好")

            h = TranslationCache.content_hash("Hello")
            hashed_prov = TranslationCache._provider_key("../../unsafe/path")
            self.assertRegex(hashed_prov, r"^[0-9a-f]{16}$")
            expected_file = data_root / "cache" / "translations" / "zh-CN" / hashed_prov / f"{h}.json"
            self.assertTrue(expected_file.is_file())
            self.assertTrue(str(expected_file.resolve()).startswith(str((data_root / "cache").resolve())))

    def test_injectable_clock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"

            cache_str_clock = TranslationCache(
                data_root,
                clock=lambda: "2026-05-17T10:00:00+08:00",
            )
            cache_str_clock.translate("Autonomous agent", lambda t: "自主智能体")

            h = TranslationCache.content_hash("Autonomous agent")
            entry_path = data_root / "cache" / "translations" / "zh-CN" / "google-translate" / f"{h}.json"
            payload = json.loads(entry_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["source_text"], "Autonomous agent")
            self.assertEqual(payload["translated_text"], "自主智能体")
            self.assertEqual(payload["content_hash"], h)
            self.assertEqual(payload["lang"], "zh-CN")
            self.assertEqual(payload["model"], "google-translate")
            self.assertEqual(payload["created_at"], "2026-05-17T10:00:00+08:00")

            fixed_dt = datetime(2026, 6, 1, 12, 30, tzinfo=timezone.utc)
            cache_dt_clock = TranslationCache(
                data_root,
                clock=lambda: fixed_dt,
            )
            cache_dt_clock.translate("Next generation", lambda t: "次世代", language="ja")
            h_dt = TranslationCache.content_hash("Next generation")
            entry_dt_path = data_root / "cache" / "translations" / "ja" / "google-translate" / f"{h_dt}.json"
            payload_dt = json.loads(entry_dt_path.read_text(encoding="utf-8"))
            self.assertEqual(payload_dt["created_at"], "2026-06-01T12:30:00+00:00")

    def test_clear_boundary_validation_independent_of_filesystem_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            cache = TranslationCache(data_root)

            self.assertEqual(cache.clear(), 0)
            self.assertEqual(cache.clear(language=None), 0)
            self.assertFalse(data_root.exists())

            with self.assertRaises(ValueError):
                cache.clear(language="")

            with self.assertRaises(ValueError):
                cache.clear(language="../evil")

            with self.assertRaises(ValueError):
                cache.clear(language="/etc/passwd")

            with self.assertRaises(ValueError):
                cache.clear(language=".")

            with self.assertRaises(ValueError):
                cache.clear(language="..")

            with self.assertRaises(ValueError):
                cache.clear(language="invalid/path")

            self.assertFalse(data_root.exists())

    def test_clear_preserves_unrelated_json_notes_and_sibling_caches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            cache = TranslationCache(data_root)

            cache.translate("Alpha text", lambda t: "Alpha 翻译", language="zh-CN")
            cache.translate("Beta text", lambda t: "Beta 翻译", language="zh-CN")
            cache.translate("Gamma text", lambda t: "Gamma translation", language="en")

            manifest_file = data_root / "cache" / "translations" / "manifest.json"
            manifest_file.write_text(json.dumps({"manifest_version": 1}), encoding="utf-8")

            lang_note = data_root / "cache" / "translations" / "zh-CN" / "notes.json"
            lang_note.write_text(json.dumps({"notes": "review needed"}), encoding="utf-8")

            prov_note = data_root / "cache" / "translations" / "zh-CN" / "google-translate" / "meta.json"
            prov_note.write_text(json.dumps({"quota": 1000}), encoding="utf-8")

            unrelated_hex_file = (
                data_root / "cache" / "translations" / "zh-CN" / "google-translate" / "0123456789abcdef.json"
            )
            unrelated_hex_file.write_text(json.dumps({"user_note": "custom data"}), encoding="utf-8")

            mismatched_file = (
                data_root / "cache" / "translations" / "zh-CN" / "google-translate" / "1234567890abcdef.json"
            )
            mismatched_file.write_text(
                json.dumps(
                    {
                        "content_hash": "1234567890abcdef",
                        "lang": "zh-CN",
                        "model": "google-translate",
                        "source_text": "Mismatch text",
                        "translated_text": "不匹配",
                    }
                ),
                encoding="utf-8",
            )

            sibling_cache_file = data_root / "cache" / "http" / "cached_response.json"
            sibling_cache_file.parent.mkdir(parents=True, exist_ok=True)
            sibling_cache_file.write_text(json.dumps({"status": 200}), encoding="utf-8")

            removed_zh = cache.clear(language="zh-CN")
            self.assertEqual(removed_zh, 2)

            self.assertTrue(manifest_file.is_file())
            self.assertEqual(json.loads(manifest_file.read_text(encoding="utf-8")), {"manifest_version": 1})
            self.assertTrue(lang_note.is_file())
            self.assertTrue(prov_note.is_file())
            self.assertTrue(unrelated_hex_file.is_file())
            self.assertTrue(mismatched_file.is_file())
            self.assertTrue(sibling_cache_file.is_file())

            en_h = TranslationCache.content_hash("Gamma text")
            en_file = data_root / "cache" / "translations" / "en" / "google-translate" / f"{en_h}.json"
            self.assertTrue(en_file.is_file())

            removed_remaining = cache.clear()
            self.assertEqual(removed_remaining, 1)

            self.assertTrue(manifest_file.is_file())
            self.assertTrue(lang_note.is_file())
            self.assertTrue(prov_note.is_file())
            self.assertTrue(unrelated_hex_file.is_file())
            self.assertTrue(mismatched_file.is_file())
            self.assertTrue(sibling_cache_file.is_file())

            self.assertEqual(cache.clear(), 0)
            self.assertTrue(manifest_file.is_file())

    def test_clear_skips_invalid_models_and_still_removes_valid_entries(self) -> None:
        for language in (None, "zh-CN"):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as temp_dir:
                data_root = Path(temp_dir) / "data"
                cache = TranslationCache(data_root)
                self.assertEqual(cache.translate("Valid Chinese", lambda t: "有效中文"), "有效中文")
                self.assertEqual(
                    cache.translate("Valid English", lambda t: "Translated English", language="en"),
                    "Translated English",
                )
                chinese_hash = TranslationCache.content_hash("Valid Chinese")
                english_hash = TranslationCache.content_hash("Valid English")
                chinese_file = cache.cache_dir / "zh-CN" / "google-translate" / f"{chinese_hash}.json"
                english_file = cache.cache_dir / "en" / "google-translate" / f"{english_hash}.json"
                english_bytes = english_file.read_bytes()
                invalid_files = {}
                invalid_models = ("", None, [], {}, 123, "   ", "\ud800")
                for index, model in enumerate(invalid_models):
                    source_text = f"Invalid model entry {index}"
                    h = TranslationCache.content_hash(source_text)
                    path = cache.cache_dir / "zh-CN" / "google-translate" / f"{h}.json"
                    path.write_text(
                        json.dumps({
                            "source_text": source_text,
                            "translated_text": "保留无效元数据",
                            "content_hash": h,
                            "lang": "zh-CN",
                            "model": model,
                        }),
                        encoding="utf-8",
                    )
                    invalid_files[path] = path.read_bytes()

                self.assertEqual(cache.clear(language=language), 2 if language is None else 1)
                self.assertFalse(chinese_file.exists())
                if language is None:
                    self.assertFalse(english_file.exists())
                else:
                    self.assertEqual(english_file.read_bytes(), english_bytes)
                self.assertEqual({path: path.read_bytes() for path in invalid_files}, invalid_files)
                self.assertEqual(cache.clear(), 0 if language is None else 1)
                self.assertFalse(english_file.exists())
                self.assertEqual({path: path.read_bytes() for path in invalid_files}, invalid_files)


    def test_cache_hit_rejects_corrupted_or_unrelated_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            cache = TranslationCache(data_root)
            text = "Quantum computing breakthrough"
            h = TranslationCache.content_hash(text)
            entry_path = data_root / "cache" / "translations" / "zh-CN" / "google-translate" / f"{h}.json"
            entry_path.parent.mkdir(parents=True, exist_ok=True)

            entry_path.write_text(
                json.dumps(
                    {
                        "source_text": "Unrelated topic",
                        "translated_text": "无关主题",
                        "content_hash": h,
                        "lang": "zh-CN",
                        "model": "google-translate",
                    }
                ),
                encoding="utf-8",
            )
            result1 = cache.translate(text, lambda t: "量子计算重大突破")
            self.assertEqual(result1, "量子计算重大突破")

            entry_path.write_text(
                json.dumps(
                    {
                        "source_text": text,
                        "translated_text": text,
                        "content_hash": h,
                        "lang": "zh-CN",
                        "model": "google-translate",
                    }
                ),
                encoding="utf-8",
            )
            result2 = cache.translate(text, lambda t: "量子计算重大突破")
            self.assertEqual(result2, "量子计算重大突破")

            entry_path.write_text(
                json.dumps(
                    {
                        "source_text": text,
                        "translated_text": "   ",
                        "content_hash": h,
                        "lang": "zh-CN",
                        "model": "google-translate",
                    }
                ),
                encoding="utf-8",
            )
            result3 = cache.translate(text, lambda t: "量子计算重大突破")
            self.assertEqual(result3, "量子计算重大突破")

            entry_path.write_text("{broken-json-data", encoding="utf-8")
            result4 = cache.translate(text, lambda t: "量子计算重大突破")
            self.assertEqual(result4, "量子计算重大突破")

            def forbidden(t: str) -> str:
                self.fail("Translator called when cache should have hit")

            cached_result = cache.translate(text, forbidden)
            self.assertEqual(cached_result, "量子计算重大突破")

    def test_clear_and_translate_skip_linked_cache_ancestry(self) -> None:
        """A linked cache root or parent must never expose outside validated envelopes."""
        for component in ("translations", "cache", "data", "ancestor"):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as temp_dir:
                base = Path(temp_dir)
                case_dir = base / component
                outside_dir = case_dir / "outside"
                outside_root = outside_dir / "data"
                external = TranslationCache(outside_root)
                text = "Good morning"
                self.assertEqual(external.translate(text, lambda t: "早上好"), "早上好")
                (outside_dir / "sentinel.txt").write_bytes(b"Do not change")
                before = {
                    str(path.relative_to(outside_dir)): path.read_bytes() if path.is_file() else None
                    for path in outside_dir.rglob("*")
                }

                data_root = case_dir / "live" / "data"
                cache = TranslationCache(data_root)
                links = {
                    "translations": (data_root / "cache" / "translations", external.cache_dir),
                    "cache": (data_root / "cache", outside_root / "cache"),
                    "data": (data_root, outside_root),
                    "ancestor": (case_dir / "live", outside_dir),
                }
                link_path, target_path = links[component]
                link_path.parent.mkdir(parents=True, exist_ok=True)
                link_path.symlink_to(target_path, target_is_directory=True)

                # Translation still works via the translator, never through the link.
                self.assertEqual(cache.translate(text, lambda t: "早上好-新"), "早上好-新")

                # Clearing removes nothing through the link.
                self.assertEqual(cache.clear(), 0)
                self.assertEqual(cache.clear(language="zh-CN"), 0)
                self.assertTrue(link_path.is_symlink())
                self.assertEqual(
                    {
                        str(path.relative_to(outside_dir)): path.read_bytes() if path.is_file() else None
                        for path in outside_dir.rglob("*")
                    },
                    before,
                )

                # The outside envelope is still a valid, usable cache entry.
                def forbidden(t: str) -> str:
                    self.fail("Outside validated envelope must survive linked clear")

                self.assertEqual(external.translate(text, forbidden), "早上好")

    def test_translate_and_clear_skip_symlinked_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            data_root = base / "data"
            cache = TranslationCache(data_root)
            text = "Quantum computing breakthrough"
            h = TranslationCache.content_hash(text)
            outside_dir = base / "outside-entry"
            outside_dir.mkdir()
            outside_file = outside_dir / f"{h}.json"
            outside_file.write_text(
                json.dumps(
                    {
                        "source_text": text,
                        "translated_text": "外部植入翻译",
                        "content_hash": h,
                        "lang": "zh-CN",
                        "model": "google-translate",
                    }
                ),
                encoding="utf-8",
            )
            before = {path.name: path.read_bytes() for path in outside_dir.iterdir()}

            entry_path = (
                data_root / "cache" / "translations" / "zh-CN" / "google-translate" / f"{h}.json"
            )
            entry_path.parent.mkdir(parents=True, exist_ok=True)
            entry_path.symlink_to(outside_file)

            # The planted envelope is never read and nothing is written through the link.
            self.assertEqual(cache.translate(text, lambda t: "量子计算重大突破"), "量子计算重大突破")
            self.assertTrue(entry_path.is_symlink())
            self.assertEqual({path.name: path.read_bytes() for path in outside_dir.iterdir()}, before)

            # clear() removes owned entries only; the linked file and its target survive.
            self.assertEqual(cache.clear(), 0)
            self.assertTrue(outside_file.is_file())
            self.assertEqual({path.name: path.read_bytes() for path in outside_dir.iterdir()}, before)

    def test_explicit_data_root_alias_still_caches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            target = base / "selected-data"
            target.mkdir()
            alias = base / "selected-data-alias"
            alias.symlink_to(target, target_is_directory=True)
            cache = TranslationCache(alias)
            text = "Good morning"
            calls: list[str] = []

            def translator(t: str) -> str:
                calls.append(t)
                return "早上好"

            self.assertEqual(cache.translate(text, translator), "早上好")
            self.assertEqual(cache.translate(text, translator), "早上好")
            self.assertEqual(calls, [text])
            entry_path = (
                target
                / "cache"
                / "translations"
                / "zh-CN"
                / "google-translate"
                / f"{TranslationCache.content_hash(text)}.json"
            )
            self.assertTrue(entry_path.is_file())
            self.assertEqual(cache.clear(), 1)
            self.assertFalse(entry_path.exists())
