from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import Message
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
import unittest
import urllib.error
from urllib.request import Request

from skrya_orchestrator.http_cache import (
    CLEANUP_GRACE_SECONDS,
    DEFAULT_HEADERS,
    HttpCache,
    HttpCacheMetadata,
    default_ttl,
    url_hash,
)


class FakeHttpResponse:
    def __init__(
        self,
        body: str,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._body_bytes = body.encode("utf-8")
        self.status = status
        self.code = status
        self.closed = False
        msg = Message()
        if headers:
            for k, v in headers.items():
                msg[k] = v
        self.headers = msg

    def read(self, size: int | None = None) -> bytes:
        if size is None:
            return self._body_bytes
        return self._body_bytes[:size]

    def info(self) -> Message:
        return self.headers

    def close(self) -> None:
        self.closed = True


class ControllableOpener:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.handler: Any = None

    def open(self, request: Request, timeout: int | float = 20) -> Any:
        record = {
            "url": request.full_url,
            "headers": dict(request.headers),
            "timeout": timeout,
        }
        self.calls.append(record)
        if self.handler is None:
            return FakeHttpResponse("<rss>default</rss>")
        if callable(self.handler):
            return self.handler(request, timeout)
        return self.handler


class TestHttpCache(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="skrya-test-http-cache-")).resolve()
        self.data_root = self.temp_dir / "data_root"
        self.fixed_time = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
        self.current_time = self.fixed_time
        self.clock = lambda: self.current_time
        self.opener = ControllableOpener()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_ttl_sources_and_tiers(self) -> None:
        self.assertEqual(default_ttl("rss"), 1800)
        self.assertEqual(default_ttl("rss", tier="hot"), 1800)
        self.assertEqual(default_ttl("rss", tier="warm"), 7200)
        self.assertEqual(default_ttl("rsshub"), 600)
        self.assertEqual(default_ttl("translation"), 604800)
        self.assertEqual(default_ttl("runtime-retrieval"), 0)

        self.assertEqual(default_ttl({"type": "rss"}), 1800)
        self.assertEqual(default_ttl({"type": "rss", "tier": "hot"}), 1800)
        self.assertEqual(default_ttl({"type": "rss", "tier": "warm"}), 7200)
        self.assertEqual(default_ttl({"type": "rsshub"}), 600)
        self.assertEqual(default_ttl({"type": "translation"}), 604800)
        self.assertEqual(default_ttl({"type": "runtime-retrieval"}), 0)

    def test_default_ttl_overrides_and_validation(self) -> None:
        self.assertEqual(default_ttl({"type": "rss", "ttl_seconds": 300}), 300)
        self.assertEqual(default_ttl({"type": "rss", "ttl_seconds": 120.0}), 120)

        with self.assertRaises(ValueError):
            default_ttl({"type": "rss", "ttl_seconds": 0})
        with self.assertRaises(ValueError):
            default_ttl({"type": "rss", "ttl_seconds": -60})
        with self.assertRaises(ValueError):
            default_ttl({"type": "rss", "ttl_seconds": "invalid"})
        with self.assertRaises(ValueError):
            default_ttl({"type": "rss", "ttl_seconds": False})
        with self.assertRaises(ValueError):
            default_ttl({"type": "rss", "ttl_seconds": None})

        with self.assertRaises(ValueError):
            default_ttl(None)
        with self.assertRaises(ValueError):
            default_ttl("unsupported_source_type")
        with self.assertRaises(ValueError):
            default_ttl("rss", tier="invalid")
        with self.assertRaises(ValueError):
            default_ttl({"type": "rss", "tier": "invalid"})
        with self.assertRaises(ValueError):
            default_ttl({"type": "unknown_type"})
        with self.assertRaises(TypeError):
            default_ttl(12345)  # type: ignore

    def test_constructor_creates_no_directories(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        self.assertFalse(self.data_root.exists())
        self.assertFalse(cache.cache_dir.exists())

    def test_fetch_200_persisted_cache_hit(self) -> None:
        xml_content = "<rss><channel><title>AI News</title></channel></rss>"
        self.opener.handler = FakeHttpResponse(
            xml_content,
            status=200,
            headers={
                "ETag": '"etag-v1"',
                "Last-Modified": "Mon, 20 Oct 2026 09:00:00 GMT",
                "Content-Type": "application/rss+xml",
            },
        )
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        target_url = "https://example.com/feed.xml"

        result1 = cache.fetch(target_url, ttl_seconds=1800)
        self.assertEqual(result1, xml_content)
        self.assertEqual(len(self.opener.calls), 1)

        h = url_hash(target_url)
        entry_dir = cache.cache_dir / h
        self.assertTrue(entry_dir.is_dir())
        response_file = entry_dir / "response.xml"
        meta_file = entry_dir / "meta.json"
        self.assertTrue(response_file.is_file())
        self.assertTrue(meta_file.is_file())

        with meta_file.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta["url"], target_url)
        self.assertEqual(meta["url_hash"], h)
        self.assertEqual(meta["status"], 200)
        self.assertEqual(meta["etag"], '"etag-v1"')
        self.assertEqual(meta["last_modified"], "Mon, 20 Oct 2026 09:00:00 GMT")
        self.assertEqual(meta["content_type"], "application/rss+xml")
        self.assertEqual(meta["ttl_seconds"], 1800)
        self.assertEqual(meta["fetched_at"], self.current_time.isoformat())
        expected_expiry = (self.current_time + timedelta(seconds=1800)).isoformat()
        self.assertEqual(meta["expires_at"], expected_expiry)
        self.assertTrue(meta["body_digest"])
        self.assertNotIn("body_sha256", meta)

        self.current_time += timedelta(seconds=600)
        result2 = cache.fetch(target_url, ttl_seconds=1800)
        self.assertEqual(result2, xml_content)
        self.assertEqual(len(self.opener.calls), 1)

    def test_expired_conditional_get_304_refresh_urllib_httperror(self) -> None:
        target_url = "https://example.com/conditional.xml"
        body_v1 = "<rss><channel><title>V1</title></channel></rss>"
        self.opener.handler = FakeHttpResponse(
            body_v1,
            status=200,
            headers={"ETag": '"etag-v1"', "Last-Modified": "Mon, 20 Oct 2026 08:00:00 GMT"},
        )
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        cache.fetch(target_url, ttl_seconds=1800)
        self.assertEqual(len(self.opener.calls), 1)

        self.current_time += timedelta(seconds=1801)

        def raise_304(request: Request, timeout: int | float) -> Any:
            self.assertEqual(request.headers.get("If-none-match"), '"etag-v1"')
            self.assertEqual(
                request.headers.get("If-modified-since"), "Mon, 20 Oct 2026 08:00:00 GMT"
            )
            msg = Message()
            msg["ETag"] = '"etag-v2"'
            raise urllib.error.HTTPError(
                request.full_url, 304, "Not Modified", msg, None  # type: ignore
            )

        self.opener.handler = raise_304

        result = cache.fetch(target_url, ttl_seconds=1800)
        self.assertEqual(result, body_v1)
        self.assertEqual(len(self.opener.calls), 2)

        meta = cache.get_metadata(target_url)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.etag, '"etag-v2"')  # type: ignore
        self.assertEqual(meta.fetched_at, self.current_time.isoformat())  # type: ignore
        refreshed_expiry = (self.current_time + timedelta(seconds=1800)).isoformat()
        self.assertEqual(meta.expires_at, refreshed_expiry)  # type: ignore

    def test_expired_conditional_get_304_refresh_response_object(self) -> None:
        target_url = "https://example.com/obj304.xml"
        body = "<rss><channel><title>Obj304</title></channel></rss>"
        self.opener.handler = FakeHttpResponse(
            body,
            status=200,
            headers={"ETag": '"obj-etag"'},
        )
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        cache.fetch(target_url, ttl_seconds=600)

        self.current_time += timedelta(seconds=601)
        self.opener.handler = FakeHttpResponse(
            "",
            status=304,
            headers={"ETag": '"obj-etag-new"'},
        )

        result = cache.fetch(target_url, ttl_seconds=600)
        self.assertEqual(result, body)
        meta = cache.get_metadata(target_url)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.etag, '"obj-etag-new"')  # type: ignore

    def test_expired_conditional_get_200_updates_cache(self) -> None:
        target_url = "https://example.com/feed-update.xml"
        body_v1 = "<rss><title>V1</title></rss>"
        body_v2 = "<rss><title>V2</title></rss>"
        self.opener.handler = FakeHttpResponse(
            body_v1,
            status=200,
            headers={"ETag": '"v1"'},
        )
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        cache.fetch(target_url, ttl_seconds=600)

        self.current_time += timedelta(seconds=601)
        self.opener.handler = FakeHttpResponse(
            body_v2,
            status=200,
            headers={"ETag": '"v2"'},
        )

        result = cache.fetch(target_url, ttl_seconds=600)
        self.assertEqual(result, body_v2)
        meta = cache.get_metadata(target_url)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.etag, '"v2"')  # type: ignore

    def test_force_refresh_bypasses_cache_and_conditional_headers(self) -> None:
        target_url = "https://example.com/fresh.xml"
        body_v1 = "<rss><title>V1</title></rss>"
        body_v2 = "<rss><title>V2</title></rss>"
        self.opener.handler = FakeHttpResponse(
            body_v1,
            status=200,
            headers={"ETag": '"v1"', "Last-Modified": "Sun, 19 Oct 2026 00:00:00 GMT"},
        )
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        cache.fetch(target_url, ttl_seconds=1800)
        self.assertEqual(len(self.opener.calls), 1)

        self.opener.handler = FakeHttpResponse(body_v2, status=200, headers={"ETag": '"v2"'})
        result = cache.fetch(target_url, force_refresh=True)
        self.assertEqual(result, body_v2)
        self.assertEqual(len(self.opener.calls), 2)

        second_headers = self.opener.calls[1]["headers"]
        self.assertNotIn("If-none-match", second_headers)
        self.assertNotIn("If-modified-since", second_headers)

    def test_corrupted_meta_json_handled_as_cache_miss(self) -> None:
        target_url = "https://example.com/corrupt-meta.xml"
        self.opener.handler = FakeHttpResponse("<rss>Initial</rss>", status=200)
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        cache.fetch(target_url, ttl_seconds=1800)

        h = url_hash(target_url)
        meta_file = cache.cache_dir / h / "meta.json"
        meta_file.write_text("{broken json syntax: true", encoding="utf-8")

        self.opener.handler = FakeHttpResponse("<rss>Repaired</rss>", status=200)
        result = cache.fetch(target_url, ttl_seconds=1800)
        self.assertEqual(result, "<rss>Repaired</rss>")

        meta = cache.get_metadata(target_url)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.status, 200)  # type: ignore

    def test_corrupted_response_body_digest_mismatch_handled_as_cache_miss(self) -> None:
        target_url = "https://example.com/mismatch.xml"
        self.opener.handler = FakeHttpResponse(
            "<rss>Legitimate</rss>", status=200, headers={"ETag": '"etag-legit"'}
        )
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        cache.fetch(target_url, ttl_seconds=1800)
        self.assertEqual(len(self.opener.calls), 1)

        h = url_hash(target_url)
        response_file = cache.cache_dir / h / "response.xml"
        response_file.write_text("<rss>Tampered</rss>", encoding="utf-8")

        self.opener.handler = FakeHttpResponse("<rss>Restored</rss>", status=200)
        result = cache.fetch(target_url, ttl_seconds=1800)
        self.assertEqual(result, "<rss>Restored</rss>")
        self.assertEqual(len(self.opener.calls), 2)

        second_headers = self.opener.calls[1]["headers"]
        self.assertNotIn("If-none-match", second_headers)
        self.assertNotIn("If-modified-since", second_headers)

        meta = cache.get_metadata(target_url)
        self.assertIsNotNone(meta)
        restored_body = (cache.cache_dir / h / "response.xml").read_text(encoding="utf-8")
        self.assertEqual(
            meta.body_digest,  # type: ignore
            hashlib.sha256(restored_body.encode("utf-8")).hexdigest(),
        )

    def test_preexisting_corrupted_body_triggers_single_unconditional_fetch(self) -> None:
        target_url = "https://example.com/tampered-304.xml"
        self.opener.handler = FakeHttpResponse(
            "<rss>Good</rss>", status=200, headers={"ETag": '"v1"'}
        )
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        cache.fetch(target_url, ttl_seconds=600)
        self.assertEqual(len(self.opener.calls), 1)

        h = url_hash(target_url)
        (cache.cache_dir / h / "response.xml").write_text("<rss>Broken</rss>", encoding="utf-8")

        self.current_time += timedelta(seconds=601)

        # Because cached body is corrupted before fetch, _read_entry rejects it immediately as a miss.
        # It must issue exactly ONE unconditional request (no 304 attempt).
        self.opener.handler = FakeHttpResponse("<rss>Fresh200</rss>", status=200)
        result = cache.fetch(target_url, ttl_seconds=600)

        self.assertEqual(result, "<rss>Fresh200</rss>")
        self.assertEqual(len(self.opener.calls), 2)  # 1 initial + 1 unconditional fetch
        second_headers = self.opener.calls[1]["headers"]
        self.assertNotIn("If-none-match", second_headers)
        self.assertNotIn("If-modified-since", second_headers)
        self.assertEqual(
            (cache.cache_dir / h / "response.xml").read_text(encoding="utf-8"),
            "<rss>Fresh200</rss>",
        )

    def test_in_flight_tampering_during_304_falls_back_to_unconditional_fetch(self) -> None:
        target_url = "https://example.com/inflight-tampered.xml"
        self.opener.handler = FakeHttpResponse(
            "<rss>Good</rss>", status=200, headers={"ETag": '"v1"'}
        )
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        cache.fetch(target_url, ttl_seconds=600)

        self.current_time += timedelta(seconds=601)
        h = url_hash(target_url)
        request_count = 0

        def dynamic_handler(request: Request, timeout: int | float) -> Any:
            nonlocal request_count
            request_count += 1
            if request_count == 1:
                self.assertEqual(request.headers.get("If-none-match"), '"v1"')
                # Simulate in-flight corruption of the cached file before 304 is processed
                (cache.cache_dir / h / "response.xml").write_text(
                    "<rss>BrokenInFlight</rss>", encoding="utf-8"
                )
                msg = Message()
                raise urllib.error.HTTPError(request.full_url, 304, "Not Modified", msg, None)  # type: ignore
            self.assertNotIn("If-none-match", request.headers)
            return FakeHttpResponse("<rss>FreshFallback</rss>", status=200)

        self.opener.handler = dynamic_handler
        result = cache.fetch(target_url, ttl_seconds=600)
        self.assertEqual(result, "<rss>FreshFallback</rss>")
        self.assertEqual(request_count, 2)  # 1 conditional (304), 1 fallback unconditional (200)
        self.assertEqual(
            (cache.cache_dir / h / "response.xml").read_text(encoding="utf-8"),
            "<rss>FreshFallback</rss>",
        )

    def test_resource_closure_on_success_304_and_errors(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        target_url = "https://example.com/closure.xml"

        resp_200 = FakeHttpResponse("<rss>A</rss>", status=200, headers={"ETag": '"v1"'})
        self.opener.handler = resp_200
        cache.fetch(target_url, ttl_seconds=600)
        self.assertTrue(resp_200.closed)

        self.current_time += timedelta(seconds=601)
        resp_304 = FakeHttpResponse("", status=304)
        self.opener.handler = resp_304
        cache.fetch(target_url, ttl_seconds=600)
        self.assertTrue(resp_304.closed)

        self.current_time += timedelta(seconds=601)
        resp_206 = FakeHttpResponse("<rss>Partial</rss>", status=206)
        self.opener.handler = resp_206
        with self.assertRaises(urllib.error.HTTPError):
            cache.fetch(target_url, ttl_seconds=600)
        self.assertTrue(resp_206.closed)

    def test_bad_metadata_and_status_cannot_become_hit(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        target_url = "https://example.com/bad-meta.xml"
        self.opener.handler = FakeHttpResponse("<rss>Initial</rss>", status=200)
        cache.fetch(target_url, ttl_seconds=600)
        h = url_hash(target_url)
        meta_path = cache.cache_dir / h / "meta.json"

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["status"] = 500
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        self.opener.handler = FakeHttpResponse("<rss>RestoredStatus</rss>", status=200)
        result = cache.fetch(target_url, ttl_seconds=600)
        self.assertEqual(result, "<rss>RestoredStatus</rss>")

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["url_hash"] = "0" * 64
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        self.opener.handler = FakeHttpResponse("<rss>RestoredHash</rss>", status=200)
        result = cache.fetch(target_url, ttl_seconds=600)
        self.assertEqual(result, "<rss>RestoredHash</rss>")

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["url"] = "https://other.com/spoofed.xml"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        self.opener.handler = FakeHttpResponse("<rss>RestoredUrl</rss>", status=200)
        result = cache.fetch(target_url, ttl_seconds=600)
        self.assertEqual(result, "<rss>RestoredUrl</rss>")

    def test_partial_content_206_rejected_and_not_cached(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        target_url = "https://example.com/partial.xml"
        self.opener.handler = FakeHttpResponse("<rss>Partial206</rss>", status=206)

        with self.assertRaises(urllib.error.HTTPError):
            cache.fetch(target_url, ttl_seconds=600)

        h = url_hash(target_url)
        self.assertFalse((cache.cache_dir / h).exists())

    def test_conditional_non_200_rejected_and_not_cached(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        target_url = "https://example.com/cond-non-200.xml"
        self.opener.handler = FakeHttpResponse(
            "<rss>Good</rss>", status=200, headers={"ETag": '"v1"'}
        )
        cache.fetch(target_url, ttl_seconds=600)

        self.current_time += timedelta(seconds=601)
        self.opener.handler = FakeHttpResponse("", status=204)
        with self.assertRaises(urllib.error.HTTPError):
            cache.fetch(target_url, ttl_seconds=600)

        h = url_hash(target_url)
        self.assertEqual(
            (cache.cache_dir / h / "response.xml").read_text(encoding="utf-8"),
            "<rss>Good</rss>",
        )

    def test_network_failure_and_timeout_no_poisoned_writes(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        target_url = "https://example.com/timeout.xml"

        self.opener.handler = lambda req, timeout: (_ for _ in ()).throw(
            TimeoutError("RSSHub request timed out")
        )
        with self.assertRaises(TimeoutError):
            cache.fetch(target_url)
        self.assertFalse((cache.cache_dir / url_hash(target_url)).exists())

        self.opener.handler = FakeHttpResponse("<rss>Working</rss>", status=200)
        cache.fetch(target_url, ttl_seconds=600)
        self.current_time += timedelta(seconds=601)

        self.opener.handler = FakeHttpResponse("Server error", status=500)
        with self.assertRaises(urllib.error.HTTPError):
            cache.fetch(target_url)

        h = url_hash(target_url)
        self.assertEqual(
            (cache.cache_dir / h / "response.xml").read_text(encoding="utf-8"),
            "<rss>Working</rss>",
        )

    def test_cleanup_grace_window_24h(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        url_fresh = "https://example.com/fresh"
        url_grace = "https://example.com/grace"
        url_expired = "https://example.com/expired"

        self.opener.handler = FakeHttpResponse("<rss>A</rss>", status=200)
        cache.fetch(url_fresh, ttl_seconds=3600)

        self.opener.handler = FakeHttpResponse("<rss>B</rss>", status=200)
        cache.fetch(url_grace, ttl_seconds=3600)

        self.opener.handler = FakeHttpResponse("<rss>C</rss>", status=200)
        cache.fetch(url_expired, ttl_seconds=3600)

        h_fresh = url_hash(url_fresh)
        h_grace = url_hash(url_grace)
        h_expired = url_hash(url_expired)

        def set_expiry(h: str, offset: timedelta) -> None:
            meta_path = cache.cache_dir / h / "meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["expires_at"] = (self.current_time + offset).isoformat()
            meta_path.write_text(json.dumps(meta), encoding="utf-8")

        set_expiry(h_fresh, timedelta(hours=1))
        set_expiry(h_grace, -timedelta(hours=2))
        set_expiry(h_expired, -timedelta(hours=25))

        removed = cache.cleanup()
        self.assertEqual(removed, 1)

        self.assertTrue((cache.cache_dir / h_fresh).is_dir())
        self.assertTrue((cache.cache_dir / h_grace).is_dir())
        self.assertFalse((cache.cache_dir / h_expired).exists())

        # Advance clock by 23 hours: now grace item is expired by 25 hours
        self.current_time += timedelta(hours=23)
        removed2 = cache.cleanup()
        self.assertEqual(removed2, 1)
        self.assertFalse((cache.cache_dir / h_grace).exists())
        self.assertTrue((cache.cache_dir / h_fresh).is_dir())

    def test_clear_removes_all_entries(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        self.opener.handler = FakeHttpResponse("<rss>content</rss>", status=200)
        cache.fetch("https://example.com/1", ttl_seconds=600)
        cache.fetch("https://example.com/2", ttl_seconds=600)
        cache.fetch("https://example.com/3", ttl_seconds=600)

        self.assertEqual(len(list(cache.cache_dir.iterdir())), 3)
        cleared = cache.clear()
        self.assertEqual(cleared, 3)
        self.assertEqual(len(list(cache.cache_dir.iterdir())), 0)
        self.assertEqual(cache.clear(), 0)

    def test_clear_and_cleanup_preserve_manual_files_and_symlinks(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        self.opener.handler = FakeHttpResponse("<rss>Item</rss>", status=200)
        cache.fetch("https://example.com/active", ttl_seconds=600)

        h = url_hash("https://example.com/active")
        entry_dir = cache.cache_dir / h

        root_manual = cache.cache_dir / "manual_notes.txt"
        root_manual.write_text("Do not delete", encoding="utf-8")

        manual_dir = cache.cache_dir / "non_hash_dir"
        manual_dir.mkdir(parents=True, exist_ok=True)
        (manual_dir / "keep.txt").write_text("Keep me", encoding="utf-8")

        entry_manual = entry_dir / "custom_extra.txt"
        entry_manual.write_text("Keep inside entry", encoding="utf-8")

        outside_dir = self.temp_dir / "outside_data"
        outside_dir.mkdir(parents=True, exist_ok=True)
        outside_file = outside_dir / "secret.txt"
        outside_file.write_text("Never delete", encoding="utf-8")

        symlink_path = cache.cache_dir / ("a" * 64)
        try:
            symlink_path.symlink_to(outside_dir)
        except OSError:
            pass

        cache.cleanup()
        self.assertTrue(root_manual.is_file())
        self.assertTrue((manual_dir / "keep.txt").is_file())
        self.assertTrue(entry_manual.is_file())
        self.assertTrue(outside_file.is_file())

        cleared = cache.clear()
        self.assertEqual(cleared, 1)

        self.assertTrue(root_manual.is_file())
        self.assertTrue((manual_dir / "keep.txt").is_file())
        self.assertTrue(entry_manual.is_file())
        self.assertTrue(outside_file.is_file())
        self.assertFalse((entry_dir / "meta.json").exists())
        self.assertFalse((entry_dir / "response.xml").exists())

    def test_readonly_mode_filesystem_equality(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        target_url = "https://example.com/readonly.xml"
        self.opener.handler = FakeHttpResponse(
            "<rss>Readonly</rss>", status=200, headers={"ETag": '"r1"'}
        )

        def snapshot(path: Path) -> dict[str, Any]:
            if not path.exists():
                return {}
            data = {}
            for root, dirs, files in os.walk(path):
                for f in files:
                    fp = Path(root) / f
                    rel = str(fp.relative_to(path))
                    data[rel] = fp.read_bytes()
            return data

        body1 = cache.fetch(target_url, write=False)
        self.assertEqual(body1, "<rss>Readonly</rss>")
        self.assertFalse(self.data_root.exists())

        cache.fetch(target_url, write=True, ttl_seconds=600)
        before_snap = snapshot(self.data_root)
        self.assertTrue(len(before_snap) > 0)

        body2 = cache.fetch(target_url, write=False, ttl_seconds=600)
        self.assertEqual(body2, "<rss>Readonly</rss>")
        self.assertEqual(snapshot(self.data_root), before_snap)

        self.current_time += timedelta(seconds=601)
        self.opener.handler = FakeHttpResponse(
            "", status=304, headers={"ETag": '"r2"'}
        )
        body3 = cache.fetch(target_url, write=False, ttl_seconds=600)
        self.assertEqual(body3, "<rss>Readonly</rss>")
        self.assertEqual(snapshot(self.data_root), before_snap)

    def test_timeout_passed_to_opener(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        self.opener.handler = FakeHttpResponse("<rss>TimeoutTest</rss>", status=200)
        cache.fetch("https://example.com/timeout-check.xml", timeout=45)
        self.assertEqual(len(self.opener.calls), 1)
        self.assertEqual(self.opener.calls[0]["timeout"], 45)

    def test_ttl_zero_not_cached(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        self.opener.handler = FakeHttpResponse("<rss>LiveOnly</rss>", status=200)
        result = cache.fetch("https://example.com/live.xml", ttl_seconds=0)
        self.assertEqual(result, "<rss>LiveOnly</rss>")
        self.assertFalse((cache.cache_dir / url_hash("https://example.com/live.xml")).exists())

    def test_cache_preserves_crlf_and_bare_cr_bodies(self) -> None:
        for index, newline in enumerate(("\r\n", "\r")):
            with self.subTest(newline=repr(newline)):
                target_url = f"https://example.com/newlines-{index}.xml"
                body = f"<rss>{newline}<title>News</title>{newline}</rss>"
                self.opener.handler = FakeHttpResponse(body, headers={"ETag": "newlines"})
                cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
                calls_before = len(self.opener.calls)
                self.assertEqual(cache.fetch(target_url, ttl_seconds=600), body)
                self.assertEqual(len(self.opener.calls), calls_before + 1)
                self.assertEqual(
                    (cache.cache_dir / url_hash(target_url) / "response.xml").read_bytes(),
                    body.encode("utf-8"),
                )

                reopened = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
                self.opener.handler = lambda req, timeout: self.fail("Fresh cache hit used network")
                self.assertEqual(reopened.fetch(target_url, ttl_seconds=600), body)
                self.assertEqual(len(self.opener.calls), calls_before + 1)

                self.current_time += timedelta(seconds=601)
                self.opener.handler = FakeHttpResponse("", status=304)
                self.assertEqual(reopened.fetch(target_url, ttl_seconds=600), body)
                self.assertEqual(len(self.opener.calls), calls_before + 2)
                self.assertEqual(self.opener.calls[-1]["headers"].get("If-none-match"), "newlines")

    def test_fetch_does_not_write_through_symlinked_entry(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        target_url = "https://example.com/linked-entry.xml"
        cache.cache_dir.mkdir(parents=True)
        outside_dir = self.temp_dir / "outside-entry"
        outside_dir.mkdir()
        (outside_dir / "meta.json").write_bytes(b"manual metadata\r\n")
        (outside_dir / "response.xml").write_bytes(b"outside response\r\n")
        (outside_dir / "sentinel.txt").write_bytes(b"outside sentinel")
        before = {path.name: path.read_bytes() for path in outside_dir.iterdir()}
        entry_dir = cache.cache_dir / url_hash(target_url)
        entry_dir.symlink_to(outside_dir, target_is_directory=True)

        self.opener.handler = FakeHttpResponse("<rss>Network</rss>")
        self.assertEqual(cache.fetch(target_url), "<rss>Network</rss>")
        self.assertEqual(cache.fetch(target_url, force_refresh=True), "<rss>Network</rss>")
        self.assertEqual(len(self.opener.calls), 2)
        self.assertTrue(entry_dir.is_symlink())
        self.assertEqual(
            {path.name: path.read_bytes() for path in outside_dir.iterdir()}, before
        )

    def test_fetch_and_maintenance_skip_symlinked_cache_ancestry(self) -> None:
        for component in ("http", "cache", "data", "ancestor"):
            with self.subTest(component=component):
                self.current_time = self.fixed_time
                case_dir = self.temp_dir / component
                outside_dir = case_dir / "outside"
                outside_root = outside_dir / "data"
                external_cache = HttpCache(outside_root, clock=self.clock, opener=self.opener)
                self.opener.handler = FakeHttpResponse("<rss>Keep outside</rss>")
                self.assertEqual(
                    external_cache.fetch("https://example.com/outside.xml", ttl_seconds=600),
                    "<rss>Keep outside</rss>",
                )
                (outside_dir / "sentinel.txt").write_bytes(b"Do not change")
                before = {
                    str(path.relative_to(outside_dir)): path.read_bytes() if path.is_file() else None
                    for path in outside_dir.rglob("*")
                }
                data_root = case_dir / "live" / "data"
                cache = HttpCache(data_root, clock=self.clock, opener=self.opener)
                links = {
                    "http": (data_root / "cache" / "http", external_cache.cache_dir),
                    "cache": (data_root / "cache", outside_root / "cache"),
                    "data": (data_root, outside_root),
                    "ancestor": (case_dir / "live", outside_dir),
                }
                link_path, target_path = links[component]
                link_path.parent.mkdir(parents=True, exist_ok=True)
                link_path.symlink_to(target_path, target_is_directory=True)
                self.current_time += timedelta(days=2)
                self.opener.handler = FakeHttpResponse("<rss>Fresh network</rss>")
                self.assertEqual(cache.fetch("https://example.com/new.xml"), "<rss>Fresh network</rss>")
                self.assertEqual(cache.cleanup(), 0)
                self.assertEqual(cache.clear(), 0)
                self.assertTrue(link_path.is_symlink())
                self.assertEqual(
                    {
                        str(path.relative_to(outside_dir)): path.read_bytes() if path.is_file() else None
                        for path in outside_dir.rglob("*")
                    },
                    before,
                )

    def test_wrong_typed_metadata_is_a_miss_and_fetch_repairs_it(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        invalid_fields = (
            ("status", None), ("status", []), ("status", "200"), ("status", True),
            ("ttl_seconds", None), ("ttl_seconds", []), ("ttl_seconds", {}),
            ("ttl_seconds", "600"), ("ttl_seconds", True), ("ttl_seconds", 600.0),
            ("expires_at", 123), ("expires_at", []), ("expires_at", {}),
            ("expires_at", None),
        )
        for index, (field, value) in enumerate(invalid_fields):
            with self.subTest(field=field, value=value):
                target_url = f"https://example.com/invalid-field-{index}.xml"
                self.opener.handler = FakeHttpResponse("<rss>Initial</rss>", headers={"ETag": "old"})
                self.assertEqual(cache.fetch(target_url), "<rss>Initial</rss>")
                meta_path = cache.cache_dir / url_hash(target_url) / "meta.json"
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
                payload[field] = value
                meta_path.write_text(json.dumps(payload), encoding="utf-8")

                calls_before = len(self.opener.calls)
                self.opener.handler = FakeHttpResponse("<rss>Repaired</rss>")
                self.assertEqual(cache.fetch(target_url), "<rss>Repaired</rss>")
                self.assertEqual(len(self.opener.calls), calls_before + 1)
                self.assertNotIn("If-none-match", self.opener.calls[-1]["headers"])
                self.assertEqual(cache.fetch(target_url), "<rss>Repaired</rss>")
                self.assertEqual(len(self.opener.calls), calls_before + 1)

    def test_malformed_unrelated_metadata_does_not_abort_successful_fetch(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        invalid_fields = (("status", None), ("ttl_seconds", []), ("expires_at", 123))
        entries = []
        self.opener.handler = FakeHttpResponse("<rss>Old</rss>")
        for index, (field, value) in enumerate(invalid_fields):
            url = f"https://example.com/cleanup-invalid-{index}.xml"
            self.assertEqual(cache.fetch(url, ttl_seconds=600), "<rss>Old</rss>")
            entries.append((cache.cache_dir / url_hash(url) / "meta.json", field, value))
        for meta_path, field, value in entries:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            payload[field] = value
            meta_path.write_text(json.dumps(payload), encoding="utf-8")
        before = {path: path.read_bytes() for path, _, _ in entries}
        self.current_time += timedelta(days=2)

        response = FakeHttpResponse("<rss>Success</rss>")
        self.opener.handler = response
        self.assertEqual(cache.fetch("https://example.com/success.xml"), "<rss>Success</rss>")
        self.assertTrue(response.closed)
        self.assertEqual(cache.cleanup(), 0)
        self.assertEqual({path: path.read_bytes() for path, _, _ in entries}, before)
        self.assertEqual(cache.fetch("https://example.com/success.xml"), "<rss>Success</rss>")

    def test_clear_and_cleanup_require_owned_metadata_envelopes(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        self.opener.handler = FakeHttpResponse("<rss>Owned</rss>")
        valid_url = "https://example.com/owned-expired.xml"
        self.assertEqual(cache.fetch(valid_url, ttl_seconds=600), "<rss>Owned</rss>")
        manual_files = {}
        cases = ("note", "body-only", "url-hash-only", "wrong-url", "wrong-hash", "wrong-status", "missing-status")
        for index, case in enumerate(cases):
            url = f"https://example.com/manual-{index}.xml"
            h = url_hash(url)
            entry_dir = cache.cache_dir / h
            entry_dir.mkdir()
            body_path = entry_dir / "response.xml"
            body_path.write_bytes(b"Manual response\r\n")
            manual_files[body_path] = body_path.read_bytes()
            payload = {
                "url": url,
                "url_hash": h,
                "status": 200,
                "ttl_seconds": 600,
                "fetched_at": self.fixed_time.isoformat(),
                "expires_at": self.fixed_time.isoformat(),
                "body_digest": hashlib.sha256(body_path.read_bytes()).hexdigest(),
            }
            if case == "body-only":
                continue
            if case == "note":
                payload = {"note": "Keep manual metadata"}
            elif case == "url-hash-only":
                payload = {"url_hash": h, "expires_at": self.fixed_time.isoformat()}
            elif case == "wrong-url":
                payload["url"] = "https://other.example.com/manual.xml"
            elif case == "wrong-hash":
                payload["url_hash"] = "0" * 64
            elif case == "wrong-status":
                payload["status"] = 500
            elif case == "missing-status":
                del payload["status"]
            meta_path = entry_dir / "meta.json"
            meta_path.write_text(json.dumps(payload), encoding="utf-8")
            manual_files[meta_path] = meta_path.read_bytes()

        self.current_time += timedelta(days=2)
        self.assertEqual(cache.cleanup(), 1)
        self.assertFalse((cache.cache_dir / url_hash(valid_url)).exists())
        self.assertEqual({path: path.read_bytes() for path in manual_files}, manual_files)
        fresh_url = "https://example.com/owned-fresh.xml"
        self.assertEqual(cache.fetch(fresh_url), "<rss>Owned</rss>")
        self.assertEqual(cache.clear(), 1)
        self.assertFalse((cache.cache_dir / url_hash(fresh_url)).exists())
        self.assertEqual({path: path.read_bytes() for path in manual_files}, manual_files)
        self.assertEqual(cache.clear(), 0)


    def test_explicit_data_root_alias_still_caches(self) -> None:
        target = self.temp_dir / "selected-data"
        target.mkdir()
        alias = self.temp_dir / "selected-data-alias"
        alias.symlink_to(target, target_is_directory=True)
        self.opener.handler = FakeHttpResponse("<rss>\r\nSelected root\r\n</rss>")
        cache = HttpCache(alias, clock=self.clock, opener=self.opener)
        url = "https://example.com/selected-root.xml"

        self.assertEqual(cache.fetch(url), "<rss>\r\nSelected root\r\n</rss>")
        self.assertEqual(cache.fetch(url), "<rss>\r\nSelected root\r\n</rss>")
        self.assertEqual(len(self.opener.calls), 1)
        self.assertTrue((target / "cache" / "http" / url_hash(url) / "meta.json").is_file())

    def test_invalid_fetch_parameters(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        with self.assertRaises(ValueError):
            cache.fetch("")
        with self.assertRaises(ValueError):
            cache.fetch(None)  # type: ignore
        with self.assertRaises(ValueError):
            cache.fetch("https://example.com", ttl_seconds=-1)
        with self.assertRaises(ValueError):
            cache.fetch("https://example.com", ttl_seconds="invalid")  # type: ignore
        with self.assertRaises(ValueError):
            cache.fetch("https://example.com", ttl_seconds=True)  # type: ignore

    def test_shared_cache_hit_respects_request_ttl(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        url = "https://example.com/shared.xml"
        body = "<rss><title>Shared</title></rss>"
        self.opener.handler = FakeHttpResponse(
            body, status=200, headers={"ETag": '"v1"'}
        )
        cache.fetch(url, ttl_seconds=7200)
        self.assertEqual(len(self.opener.calls), 1)

        # Still within the write-time 7200s expiry, but this request asks for
        # a 1800s TTL, so the shared hit must not be served: revalidate.
        self.current_time += timedelta(seconds=2400)
        self.opener.handler = FakeHttpResponse(
            "", status=304, headers={"ETag": '"v1"'}
        )
        result = cache.fetch(url, ttl_seconds=1800)
        self.assertEqual(result, body)
        self.assertEqual(len(self.opener.calls), 2)

        meta = cache.get_metadata(url)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.ttl_seconds, 1800)  # type: ignore
        self.assertEqual(meta.fetched_at, self.current_time.isoformat())  # type: ignore

    def test_request_ttl_longer_than_remaining_expiry_still_hits(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        url = "https://example.com/warm.xml"
        body = "<rss><title>Warm</title></rss>"
        self.opener.handler = FakeHttpResponse(body, status=200)
        cache.fetch(url, ttl_seconds=600)
        self.assertEqual(len(self.opener.calls), 1)

        self.current_time += timedelta(seconds=100)
        result = cache.fetch(url, ttl_seconds=7200)
        self.assertEqual(result, body)
        self.assertEqual(len(self.opener.calls), 1)

    def test_legacy_metadata_with_unparseable_fetched_at_falls_back_to_expires_at(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        url = "https://example.com/legacy.xml"
        body = "<rss>legacy</rss>"
        h = url_hash(url)
        entry_dir = cache.cache_dir / h
        entry_dir.mkdir(parents=True, exist_ok=True)
        legacy_meta = {
            "url": url,
            "url_hash": h,
            "fetched_at": "not-a-real-timestamp",
            "etag": None,
            "last_modified": None,
            "content_type": None,
            "status": 200,
            "ttl_seconds": 1800,
            "expires_at": (self.fixed_time + timedelta(seconds=1800)).isoformat(),
            "body_digest": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        }
        (entry_dir / "meta.json").write_text(json.dumps(legacy_meta), encoding="utf-8")
        (entry_dir / "response.xml").write_text(body, encoding="utf-8")

        # Old-format metadata must not crash: fall back to expires_at judgment.
        result = cache.fetch(url, ttl_seconds=1800)
        self.assertEqual(result, body)
        self.assertEqual(len(self.opener.calls), 0)

    def test_cleanup_skips_entry_with_active_tmp_file(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        url = "https://example.com/inflight.xml"
        self.opener.handler = FakeHttpResponse("<rss>A</rss>", status=200)
        cache.fetch(url, ttl_seconds=600)
        h = url_hash(url)
        entry_dir = cache.cache_dir / h
        meta_path = entry_dir / "meta.json"

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["expires_at"] = (self.current_time - timedelta(hours=25)).isoformat()
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        tmp_file = entry_dir / f".tmp.response.{os.getpid()}.999.xml"
        tmp_file.write_text("partial", encoding="utf-8")
        stamp = self.current_time.timestamp()
        os.utime(tmp_file, (stamp, stamp))

        removed = cache.cleanup()
        self.assertEqual(removed, 0)
        self.assertTrue(entry_dir.is_dir())
        self.assertTrue(tmp_file.exists())
        self.assertTrue(meta_path.exists())

    def test_cleanup_removes_stale_tmp_files_with_expired_entry(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        url = "https://example.com/abandoned.xml"
        self.opener.handler = FakeHttpResponse("<rss>B</rss>", status=200)
        cache.fetch(url, ttl_seconds=600)
        h = url_hash(url)
        entry_dir = cache.cache_dir / h
        meta_path = entry_dir / "meta.json"

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["expires_at"] = (self.current_time - timedelta(hours=25)).isoformat()
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        tmp_file = entry_dir / f".tmp.meta.{os.getpid()}.998.json"
        tmp_file.write_text("stale", encoding="utf-8")
        stamp = (self.current_time - timedelta(hours=2)).timestamp()
        os.utime(tmp_file, (stamp, stamp))

        removed = cache.cleanup()
        self.assertEqual(removed, 1)
        self.assertFalse(entry_dir.exists())

    def test_clear_skips_entry_with_active_tmp_file(self) -> None:
        cache = HttpCache(self.data_root, clock=self.clock, opener=self.opener)
        url = "https://example.com/clear-inflight.xml"
        self.opener.handler = FakeHttpResponse("<rss>C</rss>", status=200)
        cache.fetch(url, ttl_seconds=600)
        h = url_hash(url)
        entry_dir = cache.cache_dir / h

        tmp_file = entry_dir / f".tmp.response.{os.getpid()}.997.xml"
        tmp_file.write_text("partial", encoding="utf-8")
        stamp = self.current_time.timestamp()
        os.utime(tmp_file, (stamp, stamp))

        self.assertEqual(cache.clear(), 0)
        self.assertTrue(entry_dir.is_dir())
        self.assertTrue(tmp_file.exists())

        self.current_time += timedelta(hours=2)
        self.assertEqual(cache.clear(), 1)
        self.assertFalse(entry_dir.exists())

    def test_deadline_aborts_real_drip_fed_response_read(self) -> None:
        # Regression for the chunked-read path against a real HTTPResponse:
        # resp.read(n) blocks until n bytes or EOF, so a server dribbling
        # bytes below the socket timeout must be bounded by read1 + deadline.
        import threading
        import time as time_module
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class DripHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.end_headers()
                try:
                    while True:
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time_module.sleep(0.02)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), DripHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)

        cache = HttpCache(self.data_root, clock=self.clock)
        url = f"http://127.0.0.1:{server.server_port}/drip"
        deadline = time_module.monotonic() + 0.5
        started = time_module.monotonic()
        with self.assertRaises(TimeoutError):
            cache.fetch(url, ttl_seconds=600, write=False, timeout=30, deadline=deadline)
        elapsed = time_module.monotonic() - started
        # The read must abort near the deadline, not run for the full timeout.
        self.assertLess(elapsed, 5.0)
        self.assertFalse((self.data_root / "http-cache" / url_hash(url)).exists())
