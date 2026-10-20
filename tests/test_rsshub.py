from __future__ import annotations

import json
from pathlib import Path
import threading
import time
import unittest
from typing import Any

from skrya_orchestrator.rsshub import (
    RsshubConfig,
    RsshubConfigError,
    RsshubError,
    RsshubUnavailable,
    MAX_ACTIVE_REQUESTS,
    fetch_rsshub,
    parse_rsshub_config,
    build_rsshub_url,
    _summarize_body,
    validate_feed_xml,
    validate_instance_url,
    validate_route,
)

SAMPLE_RSS_FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>知乎热榜</title>
    <link>https://www.zhihu.com/billboard</link>
    <description>知乎热榜</description>
    <item>
      <title>热榜问题 1</title>
      <link>https://www.zhihu.com/question/123456</link>
      <description>问题讨论详情</description>
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM_FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Bilibili Ranking</title>
  <link href="https://www.bilibili.com" rel="alternate"/>
  <entry>
    <title>热门视频 1</title>
    <link href="https://www.bilibili.com/video/BV1xx411c7mD"/>
    <summary>视频精彩摘要</summary>
  </entry>
</feed>
"""

SAMPLE_RDF_FEED = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/">
  <channel rdf:about="https://example.com">
    <title>RDF Feed</title>
  </channel>
</rdf:RDF>
"""

SAMPLE_HTML_ERROR = """<!DOCTYPE html>
<html lang="en">
<head>
  <title>502 Bad Gateway - RSSHub</title>
</head>
<body>
  <h1>502 Bad Gateway</h1>
  <p>Target site response error.</p>
</body>
</html>
"""

SAMPLE_MALFORMED_XML = """<rss version="2.0"><channel><title>Broken<item>"""


class TestRsshubConfigValidation(unittest.TestCase):
    def test_valid_route_normalization(self) -> None:
        self.assertEqual(validate_route("/zhihu/hot"), "/zhihu/hot")
        self.assertEqual(validate_route("zhihu/hot"), "/zhihu/hot")
        self.assertEqual(validate_route("/bilibili/ranking/0/3"), "/bilibili/ranking/0/3")

    def test_invalid_routes(self) -> None:
        invalid_cases = [
            "",
            "   ",
            123,
            "https://evil.com/zhihu/hot",
            "http://evil.com/zhihu/hot",
            "ftp://evil.com/zhihu/hot",
            "//evil.com/zhihu/hot",
            "/../etc/passwd",
            "../secret",
            "/a/../../secret",
            "foo\\bar",
        ]
        for route in invalid_cases:
            with self.subTest(route=route):
                with self.assertRaises((RsshubConfigError, ValueError)):
                    validate_route(route)

    def test_valid_instance_urls(self) -> None:
        self.assertEqual(
            validate_instance_url("https://rsshub.app"),
            "https://rsshub.app",
        )
        self.assertEqual(
            validate_instance_url("https://rsshub.rssforever.com/"),
            "https://rsshub.rssforever.com",
        )
        self.assertEqual(
            validate_instance_url("http://127.0.0.1:1200"),
            "http://127.0.0.1:1200",
        )

    def test_invalid_instance_urls(self) -> None:
        invalid_urls = [
            "",
            "   ",
            None,
            "ftp://rsshub.app",
            "rsshub.app",
            "https://user:pass@rsshub.app",
            "https://rsshub.app?token=secret",
            "https://rsshub.app#top",
            "http://",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises((RsshubConfigError, ValueError)):
                    validate_instance_url(url)

    def test_invalid_host_or_port_rejected_before_callback(self) -> None:
        invalid_urls = [
            "https://:1200",
            "https://rsshub.example:invalid",
            "https://rsshub.example:70000",
            "https://rsshub.example:0",
            "https://[::1",
        ]
        calls: list[str] = []

        def counting_fetch(url: str, timeout: float) -> str:
            calls.append(url)
            return SAMPLE_RSS_FEED

        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(RsshubConfigError):
                    validate_instance_url(url)
                source = {"id": "t", "route": "/zhihu/hot", "instance_urls": [url]}
                with self.assertRaises(RsshubConfigError):
                    parse_rsshub_config(source)
                with self.assertRaises(RsshubConfigError):
                    fetch_rsshub(source, counting_fetch)
        self.assertEqual(calls, [])

    def test_config_rejection_does_not_echo_credentials(self) -> None:
        sentinel = "secret-sentinel-SK"
        bad_urls = [
            f"https://user:{sentinel}@host.example",
            f"https://host.example?api_key={sentinel}",
            f"https://host.example#{sentinel}",
            f"https://host.example:{sentinel}",
        ]
        for url in bad_urls:
            with self.subTest(url=url):
                with self.assertRaises(RsshubConfigError) as cm:
                    validate_instance_url(url)
                self.assertNotIn(sentinel, str(cm.exception))

    def test_parse_rsshub_config_boundary(self) -> None:
        source = {
            "id": "zhihu-hot",
            "name": "知乎热榜",
            "type": "rsshub",
            "route": "/zhihu/hot",
            "instance_urls": [
                "https://rsshub.app",
                "https://rsshub.rssforever.com/",
            ],
            "timeout_ms": 2500,
            "hedge_delay_ms": 200,
        }
        cfg = parse_rsshub_config(source)
        self.assertEqual(cfg.route, "/zhihu/hot")
        self.assertEqual(
            cfg.instance_urls,
            ("https://rsshub.app", "https://rsshub.rssforever.com"),
        )
        self.assertEqual(cfg.timeout_ms, 2500)
        self.assertEqual(cfg.hedge_delay_ms, 200)
        self.assertEqual(cfg.source_id, "zhihu-hot")

    def test_parse_config_rejects_missing_instances(self) -> None:
        source = {
            "id": "test",
            "type": "rsshub",
            "route": "/zhihu/hot",
        }
        with self.assertRaises(RsshubConfigError):
            parse_rsshub_config(source)

    def test_parse_config_rejects_empty_instances(self) -> None:
        source = {
            "id": "test",
            "type": "rsshub",
            "route": "/zhihu/hot",
            "instance_urls": [],
        }
        with self.assertRaises(RsshubConfigError):
            parse_rsshub_config(source)

    def test_parse_config_numeric_validation(self) -> None:
        base: dict[str, Any] = {
            "route": "/zhihu/hot",
            "instance_urls": ["https://rsshub.app"],
        }
        with self.assertRaises(RsshubConfigError):
            parse_rsshub_config({**base, "timeout_ms": 0})
        with self.assertRaises(RsshubConfigError):
            parse_rsshub_config({**base, "timeout_ms": -100})
        with self.assertRaises(RsshubConfigError):
            parse_rsshub_config({**base, "timeout_ms": "fast"})
        with self.assertRaises(RsshubConfigError):
            parse_rsshub_config({**base, "hedge_delay_ms": -1})
        with self.assertRaises(RsshubConfigError):
            parse_rsshub_config({**base, "hedge_delay_ms": "none"})

    def test_build_rsshub_url_prevents_host_escape(self) -> None:
        url = build_rsshub_url("https://rsshub.app", "/zhihu/hot")
        self.assertEqual(url, "https://rsshub.app/zhihu/hot")


class TestRsshubFeedValidation(unittest.TestCase):
    def test_feed_validation(self) -> None:
        self.assertTrue(validate_feed_xml(SAMPLE_RSS_FEED))
        self.assertTrue(validate_feed_xml(SAMPLE_ATOM_FEED))
        self.assertTrue(validate_feed_xml(SAMPLE_RDF_FEED))
        self.assertFalse(validate_feed_xml(SAMPLE_HTML_ERROR))
        self.assertFalse(validate_feed_xml(SAMPLE_MALFORMED_XML))
        self.assertFalse(validate_feed_xml("<error><code>500</code></error>"))
        self.assertFalse(validate_feed_xml(""))
        self.assertFalse(validate_feed_xml("   "))


class TestRsshubHedgedFetch(unittest.TestCase):
    def test_slow_primary_vs_valid_hedge(self) -> None:
        calls: list[str] = []

        def slow_fetch(url: str, timeout: float) -> str:
            calls.append(url)
            if "primary" in url:
                time.sleep(0.4)
                return SAMPLE_RSS_FEED
            time.sleep(0.01)
            return SAMPLE_ATOM_FEED

        source = {
            "id": "test-hedged",
            "route": "/test",
            "instance_urls": [
                "https://primary.example.com",
                "https://secondary.example.com",
            ],
            "timeout_ms": 2000,
            "hedge_delay_ms": 50,
        }

        start = time.monotonic()
        result = fetch_rsshub(source, slow_fetch)
        duration = time.monotonic() - start

        self.assertIn("Bilibili Ranking", result)
        self.assertLess(duration, 0.3)
        self.assertIn("https://secondary.example.com/test", calls)

    def test_failed_primary_vs_valid_hedge(self) -> None:
        calls: list[str] = []

        def failing_primary_fetch(url: str, timeout: float) -> str:
            calls.append(url)
            if "primary" in url:
                raise ConnectionResetError("Connection reset by peer")
            return SAMPLE_RSS_FEED

        source = {
            "id": "test-failed-primary",
            "route": "/zhihu/hot",
            "instance_urls": [
                "https://primary.example.com",
                "https://secondary.example.com",
            ],
            "timeout_ms": 2000,
            "hedge_delay_ms": 100,
        }

        result = fetch_rsshub(source, failing_primary_fetch)
        self.assertEqual(result, SAMPLE_RSS_FEED)
        self.assertEqual(calls, [
            "https://primary.example.com/zhihu/hot",
            "https://secondary.example.com/zhihu/hot",
        ])

    def test_malformed_feed_not_winner(self) -> None:
        calls: list[str] = []

        def malformed_primary_fetch(url: str, timeout: float) -> str:
            calls.append(url)
            if "primary" in url:
                return SAMPLE_HTML_ERROR
            time.sleep(0.02)
            return SAMPLE_RSS_FEED

        source = {
            "id": "test-malformed-primary",
            "route": "/zhihu/hot",
            "instance_urls": [
                "https://primary.example.com",
                "https://secondary.example.com",
            ],
            "timeout_ms": 2000,
            "hedge_delay_ms": 50,
        }

        result = fetch_rsshub(source, malformed_primary_fetch)
        self.assertEqual(result, SAMPLE_RSS_FEED)
        self.assertNotIn("502 Bad Gateway", result)

    def test_all_fail_raises_specific_rsshub_unavailable(self) -> None:
        def all_failing_fetch(url: str, timeout: float) -> str:
            if "inst1" in url:
                raise ConnectionRefusedError("Connection refused")
            if "inst2" in url:
                return SAMPLE_HTML_ERROR
            return SAMPLE_MALFORMED_XML

        source = {
            "id": "zhihu-failing",
            "route": "/zhihu/hot",
            "instance_urls": [
                "https://inst1.example.com",
                "https://inst2.example.com",
                "https://inst3.example.com",
            ],
            "timeout_ms": 2000,
            "hedge_delay_ms": 30,
        }

        with self.assertRaises(RsshubUnavailable) as cm:
            fetch_rsshub(source, all_failing_fetch)

        exc = cm.exception
        self.assertIsInstance(exc, RsshubError)
        self.assertEqual(exc.source_id, "zhihu-failing")
        self.assertIsInstance(exc.error_summary, str)
        self.assertIn("All 3 RSSHub instances failed", exc.error_summary)
        self.assertEqual(len(exc.failures), 3)

        inst1_fail = next(f for f in exc.failures if "inst1" in f["instance_url"])
        self.assertEqual(inst1_fail["status"], "error")
        self.assertIn("Connection refused", inst1_fail["error"])

        inst2_fail = next(f for f in exc.failures if "inst2" in f["instance_url"])
        self.assertEqual(inst2_fail["status"], "invalid_feed")

    def test_no_later_hedge_launched_after_success(self) -> None:
        launched: list[str] = []

        def fast_primary_fetch(url: str, timeout: float) -> str:
            launched.append(url)
            time.sleep(0.01)
            return SAMPLE_RSS_FEED

        source = {
            "id": "test-fast",
            "route": "/fast",
            "instance_urls": [
                "https://inst1.example.com",
                "https://inst2.example.com",
                "https://inst3.example.com",
            ],
            "timeout_ms": 2000,
            "hedge_delay_ms": 80,
        }

        result = fetch_rsshub(source, fast_primary_fetch)
        self.assertEqual(result, SAMPLE_RSS_FEED)

        time.sleep(0.12)
        self.assertEqual(launched, ["https://inst1.example.com/fast"])

    def test_does_not_wait_synchronously_for_losing_requests(self) -> None:
        def slow_primary_fast_secondary(url: str, timeout: float) -> str:
            if "primary" in url:
                time.sleep(2.0)
                return SAMPLE_RSS_FEED
            time.sleep(0.02)
            return SAMPLE_ATOM_FEED

        source = {
            "id": "test-nowait",
            "route": "/nowait",
            "instance_urls": [
                "https://primary.example.com",
                "https://secondary.example.com",
            ],
            "timeout_ms": 3000,
            "hedge_delay_ms": 40,
        }

        start = time.monotonic()
        result = fetch_rsshub(source, slow_primary_fast_secondary)
        duration = time.monotonic() - start

        self.assertIn("Bilibili Ranking", result)
        self.assertLess(duration, 0.3)

    def test_timeout_budget_and_seconds_supplied_to_fetch(self) -> None:
        recorded_timeouts: list[float] = []

        def timeout_fetch(url: str, timeout: float) -> str:
            recorded_timeouts.append(timeout)
            time.sleep(0.3)
            return SAMPLE_RSS_FEED

        source = {
            "id": "test-timeout-budget",
            "route": "/budget",
            "instance_urls": [
                "https://inst1.example.com",
                "https://inst2.example.com",
            ],
            "timeout_ms": 80,
            "hedge_delay_ms": 20,
        }

        start = time.monotonic()
        with self.assertRaises(RsshubUnavailable) as cm:
            fetch_rsshub(source, timeout_fetch)
        duration = time.monotonic() - start

        self.assertLess(duration, 0.4)
        self.assertEqual(len(recorded_timeouts), 2)
        for t in recorded_timeouts:
            self.assertAlmostEqual(t, 0.08, places=3)

        self.assertIn("timed out within deadline", cm.exception.error_summary)


class TestRsshubRedaction(unittest.TestCase):
    def test_unavailable_exception_hides_secrets_across_all_fields(self) -> None:
        sentinel = "secret-sentinel-SK"

        def leaky_fetch(url: str, timeout: float) -> str:
            if "inst1" in url:
                raise RuntimeError(f"callback failed: Bearer {sentinel}")
            if "inst2" in url:
                return (
                    "<!DOCTYPE html><html><head><title>"
                    f"Error {sentinel}"
                    "</title></head><body>oops</body></html>"
                )
            return SAMPLE_MALFORMED_XML

        source = {
            "id": "redact-test",
            "route": "/private/feed?token=secret-sentinel-SK",
            "instance_urls": [
                "https://inst1.example.com",
                "https://inst2.example.com",
                "https://inst3.example.com",
            ],
            "timeout_ms": 2000,
            "hedge_delay_ms": 20,
        }

        with self.assertRaises(RsshubUnavailable) as cm:
            fetch_rsshub(source, leaky_fetch)

        exc = cm.exception
        blob = json.dumps(
            {
                "str": str(exc),
                "message": exc.message,
                "error_summary": exc.error_summary,
                "route": exc.route,
                "source_id": exc.source_id,
                "failures": exc.failures,
            },
            default=str,
        )
        self.assertNotIn(sentinel, blob)

        inst1_fail = next(f for f in exc.failures if "inst1" in f["instance_url"])
        self.assertEqual(inst1_fail["status"], "error")
        self.assertIn("[REDACTED]", inst1_fail["error"])

        inst2_fail = next(f for f in exc.failures if "inst2" in f["instance_url"])
        self.assertEqual(inst2_fail["status"], "invalid_feed")
        self.assertNotIn(sentinel, inst2_fail["error"])


    def test_unknown_query_keys_and_path_credentials_never_enter_diagnostics(self) -> None:
        secret = "privateCredentialSentinel"
        endpoints = (
            (f"/private/feed?account={secret}", "https://instance.test"),
            (f"/private/{secret}/feed", "https://instance.test"),
            ("/news", f"https://instance.test/proxy/{secret}"),
        )
        for route, instance in endpoints:
            with self.subTest(route=route, instance=instance):
                def fail(url, timeout):
                    raise RuntimeError(f"request failed for {url}")
                with self.assertRaises(RsshubUnavailable) as context:
                    fetch_rsshub({"route": route, "instance_urls": [instance], "timeout_ms": 100}, fail)
                error = context.exception
                diagnostics = json.dumps({
                    "message": str(error), "source_id": error.source_id,
                    "route": error.route, "failures": error.failures,
                })
                self.assertNotIn(secret, diagnostics)
                self.assertIn("instance.test", diagnostics)

    def test_html_error_page_title_withheld(self) -> None:
        sentinel = "secret-sentinel-SK"
        body = f"<!DOCTYPE html><html><head><title>502 {sentinel}</title></head></html>"
        summary = _summarize_body(body)
        self.assertNotIn(sentinel, summary)


class TestRsshubActiveRequestCap(unittest.TestCase):
    def test_oversized_zero_delay_config_never_exceeds_cap(self) -> None:
        lock = threading.Lock()
        state = {"active": 0, "peak": 0}
        calls: list[str] = []
        release = threading.Event()

        def blocking_fetch(url: str, timeout: float) -> str:
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
                calls.append(url)
            release.wait(timeout=3.0)
            with lock:
                state["active"] -= 1
            return SAMPLE_RSS_FEED

        source = {
            "id": "test-cap",
            "route": "/cap",
            "instance_urls": [f"https://inst{i}.example.com" for i in range(10)],
            "timeout_ms": 120,
            "hedge_delay_ms": 0,
        }

        try:
            start = time.monotonic()
            with self.assertRaises(RsshubUnavailable) as cm:
                fetch_rsshub(source, blocking_fetch)
            duration = time.monotonic() - start
        finally:
            release.set()
        time.sleep(0.05)

        self.assertLess(duration, 1.0)
        self.assertLessEqual(state["peak"], MAX_ACTIVE_REQUESTS)
        self.assertLessEqual(len(calls), MAX_ACTIVE_REQUESTS)
        self.assertEqual(len(calls), state["peak"])
        self.assertEqual(len(cm.exception.failures), 10)
        statuses = {f["status"] for f in cm.exception.failures}
        self.assertIn("not_attempted", statuses)

    def test_winner_returns_while_capped_losers_in_flight(self) -> None:
        lock = threading.Lock()
        state = {"active": 0, "peak": 0}
        release = threading.Event()

        def fetch(url: str, timeout: float) -> str:
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            if "inst0" in url:
                release.wait(timeout=3.0)
            else:
                time.sleep(0.02)
            with lock:
                state["active"] -= 1
            return SAMPLE_RSS_FEED if "inst0" in url else SAMPLE_ATOM_FEED

        source = {
            "id": "test-capped-winner",
            "route": "/winner",
            "instance_urls": [f"https://inst{i}.example.com" for i in range(8)],
            "timeout_ms": 3000,
            "hedge_delay_ms": 0,
        }

        try:
            start = time.monotonic()
            result = fetch_rsshub(source, fetch)
            duration = time.monotonic() - start
        finally:
            release.set()

        self.assertIn("Bilibili Ranking", result)
        self.assertLess(duration, 0.5)
        self.assertLessEqual(state["peak"], MAX_ACTIVE_REQUESTS)


class TestRsshubRoutePresetsSchema(unittest.TestCase):
    def test_routes_schema_and_required_platforms(self) -> None:
        routes_file = Path("source-curation/presets/rsshub-routes.json")
        self.assertTrue(routes_file.exists(), "rsshub-routes.json must exist in presets directory")

        data = json.loads(routes_file.read_text(encoding="utf-8"))
        self.assertIn("routes", data)
        self.assertIsInstance(data["routes"], list)

        routes = data["routes"]
        self.assertGreaterEqual(len(routes), 4)

        platforms = {entry.get("platform") for entry in routes}
        required_platforms = {"zhihu", "bilibili", "weibo", "juejin"}
        missing = required_platforms - platforms
        self.assertFalse(missing, f"Missing required platforms in routes map: {missing}")

        for entry in routes:
            self.assertIn("platform", entry)
            self.assertIn("name", entry)
            self.assertIn("route", entry)
            has_doc = "documentation" in entry or "documentation_source" in entry
            self.assertTrue(has_doc, f"Entry {entry.get('name')} missing documentation source")

            normalized_route = validate_route(entry["route"])
            self.assertEqual(normalized_route, entry["route"])
            self.assertFalse(entry["route"].startswith("http"))


if __name__ == "__main__":
    unittest.main()
