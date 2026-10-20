from __future__ import annotations

import email.message
import hashlib
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from skrya_orchestrator.event_lifecycle import EventLifecycle
from skrya_orchestrator.http_cache import HttpCache
from skrya_orchestrator.source_collector import SourceCollector, with_source_fallbacks
from skrya_orchestrator.source_health import SourceHealthStore
from skrya_orchestrator.sources import normalize_sources, source_identity

RSS = "<rss><channel><item><title>Launch</title><link>https://news.test/launch</link><description>Launch details</description><pubDate>Tue, 20 Oct 2026 01:00:00 GMT</pubDate></item></channel></rss>"

class StaticHttpResponse:
    """Fake HTTP response with a scripted body, for opener-driven cache tests."""

    def __init__(self, body: str, status: int = 200):
        self._body = body.encode("utf-8")
        self.status = status
        self.code = status
        self.closed = False
        self.headers = email.message.Message()

    def read(self, size: int = -1) -> bytes:
        body, self._body = self._body, b""
        return body

    def close(self) -> None:
        self.closed = True


class ScriptedOpener:
    """Opener fake returning scripted responses in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[str] = []

    def open(self, request, timeout: float = 20):
        self.calls.append(request.full_url)
        return self.responses.pop(0)


class SlowChunkResponse:
    """Fake response serving the body in delayed chunks to exercise deadline reads."""

    def __init__(self, body: str, chunk_delay: float, chunk_size: int = 64):
        self._chunks = [
            body[i : i + chunk_size].encode("utf-8")
            for i in range(0, len(body), chunk_size)
        ] or [b""]
        self._delay = chunk_delay
        self.status = 200
        self.code = 200
        self.closed = False
        self.headers = email.message.Message()

    def read(self, size: int = -1) -> bytes:
        time.sleep(self._delay)
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    def read1(self, size: int = -1) -> bytes:
        # Faithful to http.client.HTTPResponse.read1: returns available data
        # promptly instead of blocking until `size` bytes accumulate.
        return self.read(size if size and size > 0 else -1)

    def close(self) -> None:
        self.closed = True


def tree_bytes(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() if p.is_file() else None for p in root.rglob("*")}


class SourceCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.topic = self.root / "topics" / "space"
        self.topic.mkdir(parents=True)
        (self.topic / "topic.json").write_text(json.dumps({"language": "en"}))
        (self.topic / "brief.json").write_text(json.dumps({"requests": [{"content": "orbital launch coverage"}]}))
        self.source = {"id": "confirmed", "name": "Confirmed News", "type": "rss", "url": "https://news.test/rss"}
        self.configure(self.source)

    def configure(self, *sources):
        (self.topic / "sources.json").write_text(json.dumps({"sources": list(sources)}))

    def hub(self, **extra):
        return {"id": "confirmed", "name": "Confirmed News", "type": "rsshub", "route": "/confirmed/news", "instance_urls": ["https://one.test", "https://two.test"], "hedge_delay_ms": 1, "timeout_ms": 1000, **extra}

    def test_supported_feeds_produce_canonical_sources_and_real_dates(self):
        bodies = [RSS,
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Launch</title><link href="https://news.test/launch" rel="alternate"/><summary>Launch details</summary><updated>2026-10-20T01:00:00Z</updated></entry></feed>',
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"><item><title>Launch</title><link>https://news.test/launch</link><description>Launch details</description></item></rdf:RDF>']
        for body in bodies:
            with self.subTest(body=body[:20]):
                result = SourceCollector(self.topic, fetcher=lambda url: body, write=False).collect()
                self.assertEqual(["Launch"], [event["title"] for event in result.events])
                self.assertEqual({"name": "Confirmed News", "url": "https://news.test/launch"}, result.events[0]["sources"][0])
                self.assertEqual("confirmed", result.events[0]["source_id"])
                self.assertEqual(64, len(result.events[0]["event_id"]))
        result = SourceCollector(self.topic, fetcher=lambda url: RSS, write=False).collect()
        self.assertEqual("2026-10-20T01:00:00+00:00", result.events[0]["date"])

    def test_empty_fast_hedge_cannot_hide_usable_second_instance(self):
        self.configure(self.hub())
        first_returned = threading.Event()
        def get_feed(url):
            if url.startswith("https://one.test"):
                first_returned.set()
                return "<rss><channel/></rss>"
            self.assertTrue(first_returned.wait(1))
            return RSS
        result = SourceCollector(self.topic, fetcher=get_feed).collect()
        self.assertEqual(["Launch"], [event["title"] for event in result.events])
        self.assertEqual([], result.failed_source_ids)
        health = json.loads((self.topic / "source-health.json").read_text())["sources"]["confirmed"]
        self.assertEqual(("ok", 0, 1), (health["status"], health["consecutive_failures"], health["generation"]))

    def test_titled_but_unattributable_hedge_is_not_a_winner(self):
        self.configure(self.hub(name=""))
        def get_feed(url):
            return "<rss><channel><item><title>Unattributed</title></item></channel></rss>" if url.startswith("https://one.test") else RSS
        result = SourceCollector(self.topic, fetcher=get_feed, write=False).collect()
        self.assertEqual(["Launch"], [event["title"] for event in result.events])

    def test_failure_yields_same_source_fallback_and_read_only_pending_request(self):
        self.configure(self.hub())
        configured = (self.topic / "sources.json").read_bytes()
        result = SourceCollector(self.topic, fetcher=lambda url: "<html>unavailable</html>").collect()
        self.assertEqual([], result.events)
        self.assertEqual(["confirmed"], result.failed_source_ids)
        self.assertEqual(["web_search", "news_search"], result.fallbacks[0]["capabilities"])
        self.assertIn("Confirmed News", result.fallbacks[0]["queries"][0])
        self.assertIn("orbital", result.fallbacks[0]["queries"][0])
        before = tree_bytes(self.root)
        pending = SourceCollector(self.topic, write=False).fallback_records()
        self.assertEqual(result.fallbacks, pending)
        self.assertEqual(before, tree_bytes(self.root))
        self.assertEqual(configured, (self.topic / "sources.json").read_bytes())
        self.assertFalse((self.root / "runs").exists())

    def test_configured_fallback_overrides_generated_queries_without_mutating_request(self):
        self.configure(self.hub(fallback={"capabilities": ["news_search"], "queries": ["Confirmed News orbital"]}))
        result = SourceCollector(self.topic, fetcher=lambda url: "bad", write=False).collect()
        request = {"capabilities": ["web_search"], "queries": ["baseline"], "extra": {"keep": True}}
        merged = with_source_fallbacks(request, fallbacks=result.fallbacks)
        self.assertEqual(["web_search", "news_search"], merged["capabilities"])
        self.assertEqual(["baseline", "Confirmed News orbital"], merged["queries"])
        self.assertEqual(["baseline"], request["queries"])
        self.assertEqual("configured", merged["fallbacks"][0]["origin"])

    def test_sensitive_route_stays_exact_for_fetch_but_never_leaks_into_generated_records(self):
        self.configure({
            "name": "Private Watch", "type": "rsshub", "route": "/private/feed?token=SECRETVALUE",
            "instance_urls": ["https://one.test", "https://two.test"], "hedge_delay_ms": 1, "timeout_ms": 1000,
        })
        fetched = []

        def get_feed(url):
            fetched.append(url)
            return RSS

        result = SourceCollector(self.topic, fetcher=get_feed).collect()
        self.assertEqual(["Launch"], [event["title"] for event in result.events])
        self.assertTrue(fetched)
        self.assertTrue(all("token=SECRETVALUE" in url for url in fetched))
        source_id = result.events[0]["source_id"]
        self.assertTrue(source_id)
        self.assertNotIn("SECRETVALUE", source_id)
        second = SourceCollector(self.topic, fetcher=get_feed).collect()
        self.assertEqual(source_id, second.events[0]["source_id"])

        result = SourceCollector(self.topic, fetcher=lambda url: "<html>unavailable</html>").collect()
        self.assertNotIn("SECRETVALUE", json.dumps(result.fallbacks))
        self.assertIn("Private Watch", result.fallbacks[0]["queries"][0])
        self.assertIn("orbital", result.fallbacks[0]["queries"][0])
        self.assertNotIn("SECRETVALUE", json.dumps(with_source_fallbacks(
            {"capabilities": ["web_search"], "queries": ["baseline"]}, fallbacks=result.fallbacks,
        )))
        for _ in range(3):
            SourceCollector(self.topic, fetcher=lambda url: "<html>unavailable</html>").collect()
        pending = SourceCollector(self.topic, write=False)
        self.assertTrue(pending.health_notice())
        self.assertNotIn("SECRETVALUE", pending.health_notice())
        self.assertNotIn("SECRETVALUE", json.dumps(pending.health_snapshot()))

    def test_query_distinct_endpoints_keep_independent_health_and_generations(self):
        self.configure(
            {"name": "Space", "type": "rsshub", "route": "/feed?category=space", "instance_urls": ["https://one.test"]},
            {"name": "Energy", "type": "rsshub", "route": "/feed?category=energy", "instance_urls": ["https://one.test"]},
        )
        for _ in range(3):
            result = SourceCollector(
                self.topic, fetcher=lambda url: RSS if "category=space" in url else "<html>unavailable</html>"
            ).collect()
        successful = result.events[0]["source_id"]
        failed = result.failed_source_ids[0]
        self.assertNotEqual(successful, failed)
        states = json.loads((self.topic / "source-health.json").read_text())["sources"]
        self.assertEqual((3, 0, "ok"), (states[successful]["generation"], states[successful]["consecutive_failures"], states[successful]["status"]))
        self.assertEqual((3, "degraded"), (states[failed]["consecutive_failures"], states[failed]["status"]))

    def test_real_success_advances_generation_but_preview_and_failure_do_not(self):
        real = SourceCollector(self.topic, fetcher=lambda url: RSS).collect()
        self.assertEqual(1, real.events[0]["generation"])
        before = tree_bytes(self.root)
        preview = SourceCollector(self.topic, fetcher=lambda url: RSS, write=False).collect()
        self.assertEqual(real.events[0]["event_id"], preview.events[0]["event_id"])
        self.assertEqual(before, tree_bytes(self.root))
        SourceCollector(self.topic, fetcher=lambda url: "bad").collect()
        self.assertEqual(1, EventLifecycle(self.root, "space").current_events()[0]["generation"])
        real = SourceCollector(self.topic, fetcher=lambda url: RSS).collect()
        self.assertEqual(2, real.events[0]["generation"])

    def test_backoff_skips_collection_and_still_supplies_fallback_without_generation(self):
        self.configure(self.hub())
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        health = SourceHealthStore(self.topic, clock=lambda: now)
        for _ in range(10): health.record_failure("confirmed", "unavailable")
        health.save()
        def forbidden(url): self.fail("backoff must not fetch")
        result = SourceCollector(self.topic, fetcher=forbidden, clock=lambda: now).collect()
        self.assertEqual(["confirmed"], result.failed_source_ids)
        self.assertIn("Confirmed News", result.health_notice)
        self.assertEqual(10, SourceHealthStore(self.topic).snapshot()["sources"]["confirmed"]["consecutive_failures"])
        self.assertFalse((self.root / "runs").exists())
        now += timedelta(hours=24)
        recovered = SourceCollector(self.topic, fetcher=lambda url: RSS, clock=lambda: now).collect()
        self.assertEqual(1, recovered.events[0]["generation"])
        self.assertEqual("degraded", SourceHealthStore(self.topic).snapshot()["sources"]["confirmed"]["status"])

    def test_disabled_failed_sources_do_not_leak_into_notices_or_fallbacks(self):
        self.configure(self.hub())
        for _ in range(3): SourceCollector(self.topic, fetcher=lambda url: "bad").collect()
        self.assertIn("Confirmed News", SourceCollector(self.topic, write=False).health_notice())
        self.configure(self.hub(enabled=False))
        collector = SourceCollector(self.topic, write=False)
        self.assertEqual("", collector.health_notice())
        self.assertEqual([], collector.fallback_records())

    def test_corrupt_health_is_preserved_and_reported_after_success(self):
        (self.topic / "source-health.json").write_bytes(b"broken health")
        result = SourceCollector(self.topic, fetcher=lambda url: RSS).collect()
        self.assertEqual("Launch", result.events[0]["title"])
        self.assertIn("corrupt", result.health_notice)
        self.assertEqual(b"broken health", (self.topic / "source-health.json").read_bytes())

    def test_http_200_error_page_does_not_poison_feed_cache(self):
        self.configure(self.source)
        error_page = "<html><body><h1>Access blocked</h1></body></html>"
        opener = ScriptedOpener([StaticHttpResponse(error_page), StaticHttpResponse(RSS)])
        collector = SourceCollector(self.topic, opener=opener)
        first = collector.collect()
        self.assertEqual([], first.events)
        second = collector.collect()
        self.assertEqual(["Launch"], [event["title"] for event in second.events])
        self.assertEqual(["https://news.test/rss", "https://news.test/rss"], opener.calls)

    def test_rsshub_deadline_bounds_underlying_body_read(self):
        self.configure({
            "id": "confirmed", "name": "Confirmed News", "type": "rsshub",
            "route": "/confirmed/news", "instance_urls": ["https://one.test"],
            "hedge_delay_ms": 1, "timeout_ms": 50,
        })
        slow = SlowChunkResponse(RSS, chunk_delay=0.2, chunk_size=64)
        opener = ScriptedOpener([slow])
        result = SourceCollector(self.topic, opener=opener).collect()
        self.assertEqual([], result.events)
        health = json.loads((self.topic / "source-health.json").read_text())["sources"]["confirmed"]
        self.assertEqual(1, health["consecutive_failures"])
        # The hedger gives up at the total deadline while the worker read is
        # still in flight; the deadline then aborts that read and closes it.
        time.sleep(0.4)
        self.assertTrue(slow.closed)

    def test_atom_xml_base_links_resolve_through_inheritance_chain(self):
        atom = (
            '<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://news.test/feed/">'
            '<entry xml:base="entries/2026/">'
            '<title>Launch</title><link xml:base="october/" href="launch" rel="alternate"/>'
            '<summary>Launch details</summary><updated>2026-10-20T01:00:00Z</updated>'
            '</entry></feed>'
        )
        result = SourceCollector(self.topic, fetcher=lambda url: atom, write=False).collect()
        self.assertEqual(
            "https://news.test/feed/entries/2026/october/launch",
            result.events[0]["sources"][0]["url"],
        )

    def test_rss_link_text_resolves_against_inherited_xml_base(self):
        rss = (
            '<rss xml:base="https://news.test/rss/">'
            '<channel><item><title>Launch</title><link>launch</link>'
            '<description>Launch details</description>'
            '<pubDate>Tue, 20 Oct 2026 01:00:00 GMT</pubDate></item></channel></rss>'
        )
        result = SourceCollector(self.topic, fetcher=lambda url: rss, write=False).collect()
        self.assertEqual("https://news.test/rss/launch", result.events[0]["sources"][0]["url"])

    def test_no_id_source_failure_report_shows_configured_name(self):
        self.configure({"name": "Configured News", "type": "rss", "url": "https://news.test/rss"})
        result = SourceCollector(self.topic, fetcher=lambda url: "<html>blocked</html>").collect()
        self.assertEqual([], result.events)
        digest = "rss:" + hashlib.sha256(b"https://news.test/rss").hexdigest()
        self.assertEqual(digest, source_identity({"name": "Configured News", "type": "rss", "url": "https://news.test/rss"}))
        self.assertEqual({digest: "Configured News"}, SourceCollector(self.topic, write=False)._source_names())
        payload = json.loads((self.topic / "sources.json").read_text())
        source_names = {
            source_identity(source): str(source.get("name") or source_identity(source))
            for source in normalize_sources(payload.get("sources", []))
        }
        report = SourceHealthStore(self.topic, source_names=source_names).report(language="en")
        self.assertIn("Configured News", report)
        self.assertNotIn(digest, report)
