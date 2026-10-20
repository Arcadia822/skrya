from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from unittest import mock

from skrya_orchestrator.source_health import (
    BACKOFF_WINDOW,
    DEGRADED_THRESHOLD,
    ERROR_THRESHOLD,
    SCHEMA_VERSION,
    SourceHealthCorruptError,
    SourceHealthStore,
    redact_error,
)


class TestSourceHealth(unittest.TestCase):
    def test_constructor_creates_no_files_or_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            non_existent_topic = Path(temp_dir) / "topic_sub" / "topic_x"
            self.assertFalse(non_existent_topic.exists())

            store = SourceHealthStore(non_existent_topic)
            self.assertFalse(non_existent_topic.exists())
            self.assertFalse(store.file_path.exists())

            # Read-only operations must not create files or dirs
            self.assertTrue(store.should_fetch("source_1"))
            report = store.report("zh-CN")
            self.assertIn("信源状态良好", report)
            snap = store.snapshot()
            self.assertEqual(snap["interface_version"], SCHEMA_VERSION)
            self.assertFalse(non_existent_topic.exists())

    def test_save_refuses_linked_health_files_locks_and_replaced_scope(self) -> None:
        for kind in ("file", "lock", "scope"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                topic = root / "topic"
                topic.mkdir()
                outside = root / "outside"
                outside.mkdir()
                target = outside / "source-health.json"
                target.write_text(json.dumps({"sources": {}, "sentinel": "untouched"}))
                store = SourceHealthStore(topic)
                if kind == "scope":
                    topic.rmdir()
                    topic.symlink_to(outside, target_is_directory=True)
                else:
                    link = topic / ("source-health.json" if kind == "file" else "source-health.lock")
                    link.symlink_to(target)
                before = {path.name: path.read_bytes() for path in outside.iterdir()}
                store.record_failure("feed", "failure")
                with self.assertRaises(SourceHealthCorruptError):
                    store.save()
                self.assertEqual(before, {path.name: path.read_bytes() for path in outside.iterdir()})

    def test_constructor_rejects_preexisting_managed_topic_links(self) -> None:
        for parent_link in (False, True):
            with self.subTest(parent_link=parent_link), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                outside = root / "outside"
                outside.mkdir()
                topics = root / "topics"
                if parent_link:
                    topics.symlink_to(outside, target_is_directory=True)
                    topic = topics / "selected"
                else:
                    topics.mkdir()
                    topic = topics / "selected"
                    topic.symlink_to(outside, target_is_directory=True)
                with self.assertRaises(SourceHealthCorruptError):
                    SourceHealthStore(topic)
                self.assertEqual([], list(outside.iterdir()))

    def test_failure_boundaries_3_and_10(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            store = SourceHealthStore(topic_dir)

            sid = "my-feed"
            self.assertEqual(store.snapshot()["sources"].get(sid, {}).get("status", "ok"), "ok")
            self.assertTrue(store.should_fetch(sid))

            # Failures 1 and 2: remain ok
            store.record_failure(sid, "Network timeout")
            self.assertEqual(store.snapshot()["sources"][sid]["status"], "ok")
            self.assertEqual(store.snapshot()["sources"][sid]["consecutive_failures"], 1)

            store.record_failure(sid, "Network timeout")
            self.assertEqual(store.snapshot()["sources"][sid]["status"], "ok")
            self.assertEqual(store.snapshot()["sources"][sid]["consecutive_failures"], 2)

            # Failure 3: boundary -> degraded
            store.record_failure(sid, "500 Internal Server Error")
            self.assertEqual(store.snapshot()["sources"][sid]["status"], "degraded")
            self.assertEqual(store.snapshot()["sources"][sid]["consecutive_failures"], 3)
            # Degraded still allows fetching
            self.assertTrue(store.should_fetch(sid))

            # Failures 4 through 9: remain degraded
            for i in range(4, 10):
                store.record_failure(sid, f"Error {i}")
                self.assertEqual(store.snapshot()["sources"][sid]["status"], "degraded")
                self.assertEqual(store.snapshot()["sources"][sid]["consecutive_failures"], i)
                self.assertTrue(store.should_fetch(sid))

            # Failure 10: boundary -> error
            store.record_failure(sid, "403 Forbidden")
            self.assertEqual(store.snapshot()["sources"][sid]["status"], "error")
            self.assertEqual(store.snapshot()["sources"][sid]["consecutive_failures"], 10)
            # In error state right after failure, should_fetch is False
            self.assertFalse(store.should_fetch(sid))

    def test_24h_reprobe_and_two_step_recovery(self) -> None:
        current_time = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)

        def mock_clock() -> datetime:
            return current_time

        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            store = SourceHealthStore(topic_dir, clock=mock_clock)

            sid = "failing-source"
            for _ in range(10):
                store.record_failure(sid, "Connection reset")

            self.assertEqual(store.snapshot()["sources"][sid]["status"], "error")
            self.assertFalse(store.should_fetch(sid))

            # After 23 hours, should still be blocked (backed off)
            current_time += timedelta(hours=23)
            self.assertFalse(store.should_fetch(sid))

            # Skipped attempts do not count as failures or mutate failure count
            self.assertEqual(store.snapshot()["sources"][sid]["consecutive_failures"], 10)

            # After 24 hours, one probe attempt is allowed
            current_time += timedelta(hours=1, seconds=1)
            self.assertTrue(store.should_fetch(sid))

            # Step 1 of recovery: successful probe changes status from 'error' to 'degraded'
            store.record_success(sid, item_count=5)
            snap = store.snapshot()
            self.assertEqual(snap["sources"][sid]["status"], "degraded")
            self.assertEqual(snap["sources"][sid]["consecutive_failures"], 0)
            self.assertEqual(snap["sources"][sid]["item_count"], 5)
            self.assertTrue(store.should_fetch(sid))

            # Step 2 of recovery: next success changes status from 'degraded' to 'ok'
            current_time += timedelta(minutes=30)
            store.record_success(sid, item_count=8)
            snap = store.snapshot()
            self.assertEqual(snap["sources"][sid]["status"], "ok")
            self.assertEqual(snap["sources"][sid]["consecutive_failures"], 0)
            self.assertEqual(snap["sources"][sid]["item_count"], 8)

    def test_failed_reprobe_stays_in_error_and_resets_24h_window(self) -> None:
        current_time = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)

        def mock_clock() -> datetime:
            return current_time

        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            store = SourceHealthStore(topic_dir, clock=mock_clock)

            sid = "hard-failing-source"
            for _ in range(10):
                store.record_failure(sid, "Crash")

            self.assertEqual(store.snapshot()["sources"][sid]["status"], "error")

            # Fast forward 24h: probe allowed
            current_time += timedelta(hours=24)
            self.assertTrue(store.should_fetch(sid))

            # Probe fails
            store.record_failure(sid, "Crash again")
            self.assertEqual(store.snapshot()["sources"][sid]["status"], "error")
            self.assertEqual(store.snapshot()["sources"][sid]["consecutive_failures"], 11)

            # Immediately after failed probe, blocked again
            self.assertFalse(store.should_fetch(sid))

            # 12h later: still blocked
            current_time += timedelta(hours=12)
            self.assertFalse(store.should_fetch(sid))

            # 24h after the latest probe failure: allowed again
            current_time += timedelta(hours=12, seconds=1)
            self.assertTrue(store.should_fetch(sid))

    def test_degraded_success_resets_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            store = SourceHealthStore(topic_dir)

            sid = "sporadic"
            for _ in range(5):
                store.record_failure(sid, "Flaky")

            self.assertEqual(store.snapshot()["sources"][sid]["status"], "degraded")
            self.assertEqual(store.snapshot()["sources"][sid]["consecutive_failures"], 5)

            store.record_success(sid, item_count=3)
            self.assertEqual(store.snapshot()["sources"][sid]["status"], "ok")
            self.assertEqual(store.snapshot()["sources"][sid]["consecutive_failures"], 0)
            self.assertEqual(store.snapshot()["sources"][sid]["item_count"], 3)

    def test_persistence_across_instances_and_atomic_save(self) -> None:
        fixed_dt = datetime(2026, 10, 20, 15, 30, 0, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "my_topic"
            store1 = SourceHealthStore(topic_dir, clock=lambda: fixed_dt)

            store1.record_failure("src_a", "404 Not Found")
            store1.record_failure("src_a", "404 Not Found")
            store1.record_failure("src_a", "404 Not Found")
            store1.record_success("src_b", item_count=12)
            store1.save()

            self.assertTrue(store1.file_path.is_file())

            # Load in a fresh instance
            store2 = SourceHealthStore(topic_dir)
            snap = store2.snapshot()

            self.assertEqual(snap["interface_version"], SCHEMA_VERSION)
            self.assertEqual(snap["sources"]["src_a"]["status"], "degraded")
            self.assertEqual(snap["sources"]["src_a"]["consecutive_failures"], 3)
            self.assertEqual(snap["sources"]["src_a"]["last_error"], "404 Not Found")
            self.assertEqual(snap["sources"]["src_b"]["status"], "ok")
            self.assertEqual(snap["sources"]["src_b"]["item_count"], 12)

    def test_unknown_field_preservation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            topic_dir.mkdir(parents=True, exist_ok=True)
            health_file = topic_dir / "source-health.json"

            initial_json = {
                "interface_version": "skrya.source-health.v1",
                "updated_at": "2026-10-20T10:00:00+00:00",
                "custom_cluster_id": "cluster-999",
                "meta_flags": {"monitored": True},
                "sources": {
                    "source-1": {
                        "status": "ok",
                        "consecutive_failures": 0,
                        "item_count": 10,
                        "last_success_at": "2026-10-20T09:00:00+00:00",
                        "last_fetch_at": "2026-10-20T09:00:00+00:00",
                        "last_error": None,
                        "custom_source_metric": 42.5,
                        "legacy_tag": "archived_feed",
                    }
                },
            }
            health_file.write_text(json.dumps(initial_json, indent=2), encoding="utf-8")

            store = SourceHealthStore(topic_dir)
            # Record a failure on source-1
            store.record_failure("source-1", "Timeout")
            store.save()

            reloaded_json = json.loads(health_file.read_text(encoding="utf-8"))
            # Top-level custom fields preserved
            self.assertEqual(reloaded_json["custom_cluster_id"], "cluster-999")
            self.assertEqual(reloaded_json["meta_flags"], {"monitored": True})
            # Per-source custom fields preserved
            s1 = reloaded_json["sources"]["source-1"]
            self.assertEqual(s1["custom_source_metric"], 42.5)
            self.assertEqual(s1["legacy_tag"], "archived_feed")
            self.assertEqual(s1["consecutive_failures"], 1)

    def test_safe_handling_of_corrupt_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            topic_dir.mkdir(parents=True, exist_ok=True)
            health_file = topic_dir / "source-health.json"
            health_file.write_text("{{corrupted json syntax...", encoding="utf-8")

            # Store initialization must not crash
            store = SourceHealthStore(topic_dir)
            self.assertTrue(store.should_fetch("new_src"))
            self.assertEqual(store.snapshot()["sources"], {})

    def test_redact_error_removes_secrets_and_credentials(self) -> None:
        # Bearer token redaction
        err1 = "HTTP 401: Unauthorized for Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
        redacted1 = redact_error(err1)
        self.assertNotIn("eyJhb", redacted1)
        self.assertIn("Bearer [REDACTED]", redacted1)

        # Basic auth user:pass in URL
        err2 = "Failed to fetch https://user:secretpass123@api.example.com/feed"
        redacted2 = redact_error(err2)
        self.assertNotIn("secretpass123", redacted2)
        self.assertIn("[REDACTED]", redacted2)

        # Sensitive query params
        err3 = "Request failed: https://feed.example.com/rss?api_key=sk-1234567890abcdef&category=tech"
        redacted3 = redact_error(err3)
        self.assertNotIn("sk-1234567890abcdef", redacted3)
        self.assertIn("api_key=%5BREDACTED%5D", redacted3)
        self.assertIn("category=tech", redacted3)

    def test_redact_error_covers_sensitive_headers_and_payloads(self) -> None:
        sentinel = "secret-sentinel"

        # Sensitive header form
        redacted1 = redact_error(f"request rejected; X-API-Key: {sentinel}")
        self.assertNotIn(sentinel, redacted1)
        self.assertIn("X-API-Key: [REDACTED]", redacted1)

        # Non-bearer Authorization header
        redacted2 = redact_error(f"Authorization: {sentinel}")
        self.assertNotIn(sentinel, redacted2)
        self.assertIn("Authorization: [REDACTED]", redacted2)

        # Quoted JSON payload assignment; non-sensitive keys survive
        redacted3 = redact_error(f'{{"api_key": "{sentinel}", "category": "tech"}}')
        self.assertNotIn(sentinel, redacted3)
        self.assertIn('"category": "tech"', redacted3)
        self.assertIn("[REDACTED]", redacted3)

        # Python repr payload assignment with single quotes
        redacted4 = redact_error("headers={'Authorization': 'Bearer abc123.def456'}")
        self.assertNotIn("abc123.def456", redacted4)

        # Unquoted payload assignment; surrounding text survives
        redacted5 = redact_error(f"auth failed: password={sentinel} for user bob")
        self.assertNotIn(sentinel, redacted5)
        self.assertIn("user bob", redacted5)

    def test_persisted_secrets_never_saved_or_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            store = SourceHealthStore(
                topic_dir, clock=lambda: datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
            )
            for _ in range(DEGRADED_THRESHOLD):
                store.record_failure("src_a", "request rejected; X-API-Key: {{SECRET_pohdk5iu}}")
            store.save()

            raw = store.file_path.read_text(encoding="utf-8")
            self.assertNotIn("{{SECRET_pohdk5iu}}", raw)
            self.assertIn("[REDACTED]", raw)
            self.assertNotIn("{{SECRET_pohdk5iu}}", store.report("zh-CN"))
            self.assertNotIn("{{SECRET_pohdk5iu}}", store.report("en"))

    def test_load_sanitizes_persisted_last_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            topic_dir.mkdir(parents=True)
            health_file = topic_dir / "source-health.json"
            health_file.write_text(
                json.dumps(
                    {
                        "interface_version": SCHEMA_VERSION,
                        "sources": {
                            "src_a": {
                                "status": "degraded",
                                "consecutive_failures": 3,
                                "last_error": "request rejected; X-API-Key: {{SECRET_pohdk5iu}}",
                                "item_count": 0,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            store = SourceHealthStore(topic_dir)
            snap = store.snapshot()
            self.assertNotIn("{{SECRET_pohdk5iu}}", json.dumps(snap))
            self.assertIn("[REDACTED]", snap["sources"]["src_a"]["last_error"])
            self.assertNotIn("{{SECRET_pohdk5iu}}", store.report("zh-CN"))
            self.assertNotIn("{{SECRET_pohdk5iu}}", store.report("en"))

            store.save()
            self.assertNotIn("{{SECRET_pohdk5iu}}", health_file.read_text(encoding="utf-8"))

    def test_save_refuses_to_replace_corrupt_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            topic_dir.mkdir(parents=True)
            health_file = topic_dir / "source-health.json"
            original = "{corrupted json syntax..."
            health_file.write_text(original, encoding="utf-8")

            store = SourceHealthStore(topic_dir)
            self.assertTrue(store.should_fetch("new_src"))

            with self.assertRaises(SourceHealthCorruptError):
                store.save()
            self.assertEqual(health_file.read_text(encoding="utf-8"), original)

            store.record_failure("src_a", "Timeout")
            with self.assertRaises(SourceHealthCorruptError):
                store.save()
            self.assertEqual(health_file.read_text(encoding="utf-8"), original)

    def test_save_refuses_on_invalid_utf8_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            topic_dir.mkdir(parents=True)
            health_file = topic_dir / "source-health.json"
            original = b"\xff\xfe not utf-8 \x80"
            health_file.write_bytes(original)

            store = SourceHealthStore(topic_dir)
            self.assertEqual(store.snapshot()["sources"], {})

            with self.assertRaises(SourceHealthCorruptError):
                store.save()
            self.assertEqual(health_file.read_bytes(), original)

    def test_save_refuses_on_malformed_sources_container_or_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container_dir = Path(temp_dir) / "container"
            container_dir.mkdir(parents=True)
            container_file = container_dir / "source-health.json"
            container_original = json.dumps(
                {
                    "interface_version": SCHEMA_VERSION,
                    "custom_note": "keep",
                    "sources": ["src_a", "src_b"],
                }
            )
            container_file.write_text(container_original, encoding="utf-8")

            container_store = SourceHealthStore(container_dir)
            with self.assertRaises(SourceHealthCorruptError):
                container_store.save()
            self.assertEqual(container_file.read_text(encoding="utf-8"), container_original)

            entry_dir = Path(temp_dir) / "entry"
            entry_dir.mkdir(parents=True)
            entry_file = entry_dir / "source-health.json"
            entry_original = json.dumps(
                {
                    "interface_version": SCHEMA_VERSION,
                    "sources": {
                        "src_ok": {"status": "ok", "consecutive_failures": 0, "item_count": 1},
                        "src_opaque": "legacy-opaque-value",
                    },
                }
            )
            entry_file.write_text(entry_original, encoding="utf-8")

            entry_store = SourceHealthStore(entry_dir)
            with self.assertRaises(SourceHealthCorruptError):
                entry_store.save()
            self.assertEqual(entry_file.read_text(encoding="utf-8"), entry_original)

    def test_unreadable_file_is_not_treated_as_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            topic_dir.mkdir(parents=True)
            health_file = topic_dir / "source-health.json"
            health_file.write_text("{}", encoding="utf-8")

            with mock.patch.object(
                Path, "read_bytes", side_effect=PermissionError(13, "Permission denied")
            ):
                store = SourceHealthStore(topic_dir)
                self.assertEqual(store.snapshot()["sources"], {})
                with self.assertRaises(SourceHealthCorruptError):
                    store.save()
            self.assertEqual(health_file.read_text(encoding="utf-8"), "{}")

    def test_set_generation_mirrors_without_touching_health_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            store = SourceHealthStore(
                topic_dir, clock=lambda: datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
            )

            store.set_generation("src_a", 7)
            snap = store.snapshot()["sources"]["src_a"]
            self.assertEqual(snap["generation"], 7)
            self.assertEqual(snap["status"], "ok")
            self.assertEqual(snap["consecutive_failures"], 0)
            self.assertEqual(snap["item_count"], 0)
            self.assertTrue(store.should_fetch("src_a"))

            for _ in range(DEGRADED_THRESHOLD):
                store.record_failure("src_a", "Timeout")
            self.assertEqual(store.snapshot()["sources"]["src_a"]["generation"], 7)
            self.assertEqual(store.snapshot()["sources"]["src_a"]["consecutive_failures"], DEGRADED_THRESHOLD)

            store.save()
            reloaded = SourceHealthStore(topic_dir)
            snap = reloaded.snapshot()["sources"]["src_a"]
            self.assertEqual(snap["generation"], 7)
            self.assertEqual(snap["consecutive_failures"], DEGRADED_THRESHOLD)
            self.assertEqual(snap["status"], "degraded")

            reloaded.set_generation("src_a", 8)
            self.assertEqual(reloaded.snapshot()["sources"]["src_a"]["generation"], 8)

    def test_report_uses_display_names_and_truthful_wording(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            names = {
                "zhihu-hot": "知乎热榜",
                "verge-tech": "The Verge",
                "reuters-biz": "路透商业",
            }
            store = SourceHealthStore(topic_dir, source_names=names)

            store.record_success("reuters-biz", 10)
            for _ in range(4):
                store.record_failure("zhihu-hot", "Rate limited 429")
            for _ in range(10):
                store.record_failure("verge-tech", "503 Service Unavailable")

            report_zh = store.report("zh-CN")
            # Must display configured human name, not raw id
            self.assertIn("知乎热榜", report_zh)
            self.assertIn("The Verge", report_zh)
            self.assertNotIn("zhihu-hot", report_zh)
            self.assertNotIn("verge-tech", report_zh)

            # Must state backed off / 暂缓拉取, NOT misleading '已停用' or 'disabled'
            self.assertNotIn("已停用", report_zh)
            self.assertNotIn("已禁用", report_zh)
            self.assertIn("暂缓拉取", report_zh)

            # English report check
            report_en = store.report("en")
            self.assertIn("The Verge", report_en)
            self.assertIn("backed off", report_en)
            self.assertNotIn("disabled", report_en)


    def test_missing_or_null_sources_container_marks_corrupt_and_refuses_overwrite(self) -> None:
        for raw in (
            "{}",
            '{"sources": null}',
            '{"updated_at": "2026-10-20T10:00:00+00:00", "custom_note": "keep"}',
        ):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as temp_dir:
                topic_dir = Path(temp_dir) / "topic"
                topic_dir.mkdir(parents=True)
                health_file = topic_dir / "source-health.json"
                health_file.write_text(raw, encoding="utf-8")

                store = SourceHealthStore(topic_dir)

                # Preview stays usable and non-destructive.
                self.assertEqual(store.snapshot()["sources"], {})
                self.assertNotIn("状态良好", store.report("zh-CN"))
                self.assertNotIn("healthy", store.report("en").lower())
                self.assertTrue(store.should_fetch("src_a"))
                store.record_failure("src_a", "Timeout")
                self.assertIn("信源", store.report("zh-CN"))

                with self.assertRaises(SourceHealthCorruptError):
                    store.save()
                self.assertEqual(health_file.read_text(encoding="utf-8"), raw)

    def test_redact_error_redacts_complete_authorization_values(self) -> None:
        cases = {
            "Authorization: Token ghp_example": "ghp_example",
            "Authorization: Negotiate YIIvalidtoken": "YIIvalidtoken",
            "retry failed: Authorization=Token sk_live_example": "sk_live_example",
            'headers={"Authorization": "Token ghp_example"}': "ghp_example",
            "Proxy-Authorization: ApiKey abc123": "abc123",
            'Authorization: Digest username="u", realm="feed", nonce="n", response="0123456789abcdef0123456789abcdef"': "0123456789abcdef0123456789abcdef",
            "HTTP 401 for Basic dXNlcjpwYXNz": "dXNlcjpwYXNz",
        }
        for err, secret in cases.items():
            with self.subTest(err=err):
                redacted = redact_error(err)
                self.assertNotIn(secret, redacted)
        self.assertIn(
            "Authorization: [REDACTED]", redact_error("Authorization: Token ghp_example")
        )

        # Existing safe formatted header/list/dict cases stay protected.
        kept = redact_error("auth failed: password=secret-sentinel for user bob")
        self.assertNotIn("secret-sentinel", kept)
        self.assertIn("user bob", kept)
        listed = redact_error("headers={'Authorization': 'Bearer abc123.def456'}")
        self.assertNotIn("abc123.def456", listed)
        dumped = redact_error('{"api_key": "{{SECRET_x}}", "category": "tech"}')
        self.assertNotIn("{{SECRET_x}}", dumped)
        self.assertIn('"category": "tech"', dumped)

    def test_persisted_last_error_never_leaks_authorization_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            store = SourceHealthStore(topic_dir)
            store.record_failure("src_a", "HTTP 401: Authorization: Token ghp_example")
            store.save()

            raw = store.file_path.read_text(encoding="utf-8")
            self.assertNotIn("ghp_example", raw)
            self.assertIn("[REDACTED]", raw)

    def test_report_claims_all_healthy_only_with_zero_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            names = {"zhihu-hot": "知乎热榜", "reuters-biz": "路透商业"}
            store = SourceHealthStore(topic_dir, source_names=names)
            store.record_failure("zhihu-hot", "500 Internal Server Error")
            store.record_success("reuters-biz", item_count=4)

            # Threshold state machine unchanged: one failure is still formal 'ok'.
            self.assertEqual(store.snapshot()["sources"]["zhihu-hot"]["status"], "ok")

            report_zh = store.report("zh-CN")
            self.assertNotIn("状态正常", report_zh)
            self.assertIn("知乎热榜", report_zh)
            self.assertNotIn("zhihu-hot", report_zh)
            self.assertIn("连续失败 1 次", report_zh)
            self.assertIn("500 Internal Server Error", report_zh)

            report_en = store.report("en")
            self.assertNotIn("All 2 sources are healthy", report_en)
            self.assertIn("Recently failed sources (1)", report_en)
            self.assertIn("500 Internal Server Error", report_en)
            self.assertIn("知乎热榜", report_en)

            # Only a zero-failure run may claim all healthy.
            store.record_success("zhihu-hot", item_count=2)
            self.assertIn("全部 2 个信源状态正常", store.report("zh-CN"))
            self.assertIn("All 2 sources are healthy", store.report("en"))

    def test_overlapping_instances_replay_recorded_outcomes_on_save(self) -> None:
        clock = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            store_a = SourceHealthStore(topic_dir, clock=clock)
            store_b = SourceHealthStore(topic_dir, clock=clock)

            store_a.record_failure("src_a", "Boom A")
            store_b.record_failure("src_a", "Boom B")
            store_a.save()
            store_b.save()

            snap = SourceHealthStore(topic_dir, clock=clock).snapshot()["sources"]["src_a"]
            self.assertEqual(snap["consecutive_failures"], 2)
            self.assertEqual(snap["status"], "ok")

    def test_stale_save_never_regresses_generation_mirror(self) -> None:
        clock = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            topic_dir = Path(temp_dir) / "topic"
            store_old = SourceHealthStore(topic_dir, clock=clock)
            store_new = SourceHealthStore(topic_dir, clock=clock)

            store_old.record_success("src_a", item_count=3)
            store_new.set_generation("src_a", 8)
            store_new.save()
            store_old.save()

            snap = SourceHealthStore(topic_dir, clock=clock).snapshot()["sources"]["src_a"]
            self.assertEqual(snap["generation"], 8)
            self.assertEqual(snap["item_count"], 3)

            # A stale lower mirror op never overwrites the newer generation either.
            store_late = SourceHealthStore(topic_dir, clock=clock)
            store_late.set_generation("src_a", 7)
            store_late.save()
            snap = SourceHealthStore(topic_dir, clock=clock).snapshot()["sources"]["src_a"]
            self.assertEqual(snap["generation"], 8)


if __name__ == "__main__":
    unittest.main()
