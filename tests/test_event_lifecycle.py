import fcntl
import hashlib
import json
import os
import shutil
import unittest
from pathlib import Path
from threading import Event, Thread, current_thread
from unittest.mock import patch

from skrya_orchestrator.event_lifecycle import (
    EventLifecycle,
    event_identity,
    identify_events,
    migrate_ingest_v1,
    prune_ingests,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = ROOT / "tmp" / "unit-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class EventIdentityTests(unittest.TestCase):
    def test_same_url_keeps_event_id_stable_across_title_change(self) -> None:
        first = {"source_id": "example.com", "url": "https://example.com/a", "title": "Old title", "summary": "s"}
        second = {"source_id": "example.com", "url": "https://example.com/a", "title": "New title", "summary": "s2"}

        first_id, first_hash = event_identity(first)
        second_id, second_hash = event_identity(second)

        self.assertEqual(first_id, second_id)
        self.assertNotEqual(first_hash, second_hash)

    def test_url_less_identity_uses_normalized_title(self) -> None:
        first = {"source_id": "cctv", "source_name": "央视军事", "title": "战区组织演练"}
        second = {"source_id": "cctv", "source_name": "央视军事", "title": "  战区组织演练  "}

        self.assertEqual(event_identity(first), event_identity(second))
        self.assertNotEqual(
            event_identity(first)[0],
            event_identity({"source_id": "other-source", "title": "战区组织演练"})[0],
        )

    def test_identify_events_infers_source_id_from_host_and_keeps_supplied(self) -> None:
        lifecycle = EventLifecycle(TEST_TEMP_ROOT / "identity-noop", "t")
        events = lifecycle.identify_events(
            [
                {"title": "A", "url": "https://www.example.com/a", "summary": "x"},
                {"title": "B", "url": "https://example.com/b", "summary": "y", "source_id": "cctv-military"},
                {"title": "C", "source_name": "央视军事", "summary": "z"},
            ]
        )

        self.assertEqual("example.com", events[0]["source_id"])
        self.assertEqual("cctv-military", events[1]["source_id"])
        for event in events:
            self.assertTrue(event["event_id"])
            self.assertTrue(event["content_hash"])


    def test_hostname_inference_preserves_domain_and_exact_article_url(self) -> None:
        url = "https://WWW.Example.COM:8443/a?x=1#section"
        lifecycle = EventLifecycle(TEST_TEMP_ROOT / "identity-noop", "t")
        event = lifecycle.identify_events([{"title": "Story", "url": url, "summary": "Body"}])[0]

        self.assertEqual("example.com", event["source_id"])
        self.assertEqual(url, event["url"])
        self.assertEqual(hashlib.sha256(f"example.com|{url}".encode()).hexdigest(), event["event_id"])

    def test_display_field_bodies_contribute_when_canonical_fields_are_absent(self) -> None:
        canonical = {"source_id": "feed-a", "title": "Story", "summary": "Short summary", "content": "Full body"}
        display = {"source_id": "feed-a", "title": "Story", "headline_summary": "Short summary", "analysis_body": "Full body"}
        list_only = {"source_id": "feed-a", "title": "Story", "list_summary": "Short summary", "analysis_body": "Full body"}

        self.assertEqual(event_identity(canonical), event_identity(display))
        self.assertEqual(event_identity(canonical), event_identity(list_only))
        for field in ("headline_summary", "analysis_body"):
            with self.subTest(field=field):
                changed = dict(display, **{field: "Changed actual text"})
                self.assertEqual(event_identity(display)[0], event_identity(changed)[0])
                self.assertNotEqual(event_identity(display)[1], event_identity(changed)[1])
        self.assertNotEqual(event_identity(list_only)[1], event_identity(dict(list_only, list_summary="New list text"))[1])


    def test_distinct_headline_and_list_summaries_both_contribute_to_hash(self) -> None:
        event = {
            "source_id": "feed-a",
            "title": "Story",
            "headline_summary": "Headline summary",
            "list_summary": "Different detailed list summary",
            "analysis_body": "Full body",
        }
        for field in ("headline_summary", "list_summary", "analysis_body"):
            with self.subTest(field=field):
                changed = dict(event, **{field: "Actual changed text"})
                self.assertEqual(event_identity(event)[0], event_identity(changed)[0])
                self.assertNotEqual(event_identity(event)[1], event_identity(changed)[1])


class EventLifecycleTests(unittest.TestCase):
    def _make_root(self, name: str) -> Path:
        root = TEST_TEMP_ROOT / f"lifecycle-{name}"
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _item(self, title: str, **overrides) -> dict:
        item = {
            "title": title,
            "url": f"https://example.com/{title.replace(' ', '-')}",
            "summary": f"summary {title}",
            "content": f"content {title}",
        }
        item.update(overrides)
        return item

    def test_constructor_is_read_only(self) -> None:
        root = self._make_root("readonly")
        EventLifecycle(root, "topic-a")

        self.assertFalse((root / "runs").exists())

    def test_record_source_advances_generation_and_filters_current_set(self) -> None:
        root = self._make_root("generations")
        lifecycle = EventLifecycle(root, "topic-a")

        first = lifecycle.record_source("feed-a", [self._item("First story")], persist=True)
        self.assertEqual(1, len(first))
        self.assertEqual(1, first[0]["generation"])
        self.assertTrue((root / "runs" / "topic-a" / "event-state.json").exists())

        second = lifecycle.record_source(
            "feed-a",
            [self._item("First story", summary="updated summary"), self._item("Second story")],
            persist=True,
        )
        self.assertEqual(2, len(second))
        self.assertEqual(2, second[0]["generation"])

        current = lifecycle.current_events("feed-a")
        self.assertEqual(2, len(current))
        self.assertEqual(2, current[0]["generation"])
        by_title = {event["title"]: event for event in current}
        self.assertEqual("updated summary", by_title["First story"]["summary"])

        third = lifecycle.record_source("feed-a", [self._item("Third story")], persist=True)
        self.assertEqual(3, third[0]["generation"])
        current = lifecycle.current_events()
        self.assertEqual(1, len(current))
        self.assertEqual("Third story", current[0]["title"])

        state = json.loads((root / "runs" / "topic-a" / "event-state.json").read_text(encoding="utf-8"))
        self.assertEqual(3, len(state["sources"]["feed-a"]["events"]))

    def test_same_article_upsert_returns_only_the_current_version(self) -> None:
        root = self._make_root("same-article-batch")
        lifecycle = EventLifecycle(root, "topic-a")
        old = self._item("Old title", url="https://example.com/article")
        new = self._item("New title", url="https://example.com/article")
        records = lifecycle.record_source("feed", [old, new])
        self.assertEqual(["New title"], [record["title"] for record in records])
        self.assertEqual(records, lifecycle.current_events("feed"))

    def test_merge_source_never_carries_previous_generation_content(self) -> None:
        root = self._make_root("stale-content")
        lifecycle = EventLifecycle(root, "topic-a")

        lifecycle.record_source(
            "feed-a", [self._item("Story", summary="old summary", content="old body")], persist=True
        )
        updated = lifecycle.record_source(
            "feed-a",
            [{"title": "Story", "url": "https://example.com/Story", "summary": "new summary"}],
            persist=True,
        )
        record = updated[0]
        self.assertEqual(2, record["generation"])
        self.assertIsNone(record.get("content"))
        self.assertEqual("new summary", record["summary"])

        reversed_update = lifecycle.record_source(
            "feed-a",
            [{"title": "Story", "url": "https://example.com/Story", "content": "newest body"}],
            persist=True,
        )
        record = reversed_update[0]
        self.assertEqual("newest body", record["content"])
        self.assertIsNone(record.get("summary"))

    def test_record_source_preserves_unknown_fields_on_upsert(self) -> None:
        root = self._make_root("unknown-fields")
        lifecycle = EventLifecycle(root, "topic-a")

        lifecycle.record_source(
            "feed-a", [self._item("Story", custom_trace="trace-1")], persist=True
        )
        updated = lifecycle.record_source("feed-a", [self._item("Story")], persist=True)

        self.assertEqual("trace-1", updated[0].get("custom_trace"))

    def test_record_source_without_persist_writes_nothing(self) -> None:
        root = self._make_root("preview")
        lifecycle = EventLifecycle(root, "topic-a")

        preview = lifecycle.record_source("feed-a", [self._item("Story")], persist=False)

        self.assertEqual(1, len(preview))
        self.assertEqual(1, preview[0]["generation"])
        self.assertFalse((root / "runs").exists())
        self.assertEqual([], EventLifecycle(root, "topic-a").current_events())

    def test_current_events_filters_per_source(self) -> None:
        root = self._make_root("per-source")
        lifecycle = EventLifecycle(root, "topic-a")

        lifecycle.record_source("feed-a", [self._item("Story A")], persist=True)
        lifecycle.record_source("feed-b", [self._item("Story B")], persist=True)

        self.assertEqual(1, len(lifecycle.current_events("feed-a")))
        self.assertEqual(1, len(lifecycle.current_events("feed-b")))
        self.assertEqual(2, len(lifecycle.current_events()))

    def _write_snapshot(self, root: Path, name: str, events: list[dict]) -> None:
        run_dir = root / "runs" / "topic-a"
        run_dir.mkdir(parents=True, exist_ok=True)
        items = {f"N-{index + 1:02d}": event for index, event in enumerate(events)}
        (run_dir / name).write_text(
            json.dumps({"schema": "skrya.digest-index.v1", "topic_id": "topic-a", "items": items}, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_filter_recent_hides_exact_id_and_hash_repeats_only(self) -> None:
        root = self._make_root("filter-recent")
        identified = EventLifecycle(root, "topic-a").identify_events(
            [self._item("Repeat story"), self._item("Fresh story")]
        )
        repeat, fresh = identified
        changed = EventLifecycle(root, "topic-a").identify_events(
            [dict(repeat, content="A genuinely changed article body")]
        )[0]
        self.assertEqual(repeat["event_id"], changed["event_id"])
        self.assertNotEqual(repeat["content_hash"], changed["content_hash"])

        self._write_snapshot(root, "digest-20260101T090000+0800.events.json", [dict(repeat)])
        self._write_snapshot(root, "digest-20260201T090000+0800.events.json", [dict(repeat)])
        self._write_snapshot(root, "digest-20260301T090000+0800.events.json", [dict(repeat)])
        self._write_snapshot(root, "digest-20251201T090000+0800.events.json", [dict(changed)])

        lifecycle = EventLifecycle(root, "topic-a")
        remaining = lifecycle.filter_recent(identified + [changed])

        self.assertEqual([dict(fresh), dict(changed)], remaining)

        remaining_narrow = lifecycle.filter_recent(identified, window=1)
        self.assertEqual([dict(fresh)], remaining_narrow)

    def test_filter_recent_ignores_latest_pointer_and_unreadable_snapshots(self) -> None:
        root = self._make_root("filter-pointer")
        identified = EventLifecycle(root, "topic-a").identify_events([self._item("Pointer story")])
        event = identified[0]

        self._write_snapshot(root, "latest-digest-events.json", [dict(event)])
        (root / "runs" / "topic-a" / "digest-20260101T090000+0800.events.json").write_text("not json", encoding="utf-8")

        remaining = EventLifecycle(root, "topic-a").filter_recent(identified)
        self.assertEqual([dict(event)], remaining)


    def test_record_source_uses_caller_identity_before_hashing(self) -> None:
        root = self._make_root("caller-source")
        item = self._item("Story", source_id="untrusted-incoming-source")
        lifecycle = EventLifecycle(root, "topic-a")

        record = lifecycle.record_source("feed-a", [item])[0]

        expected_id = hashlib.sha256(("feed-a|" + item["url"]).encode()).hexdigest()
        self.assertEqual("feed-a", record["source_id"])
        self.assertEqual(expected_id, record["event_id"])
        self.assertEqual(expected_id, lifecycle.identify_events([record])[0]["event_id"])
        self.assertEqual("untrusted-incoming-source", item["source_id"])

    def test_concurrent_updates_preserve_sources_and_generation_history(self) -> None:
        original_write = EventLifecycle._write_state
        original_flock = fcntl.flock
        for same_source in (False, True):
            with self.subTest(same_source=same_source):
                root = self._make_root(f"concurrent-{same_source}")
                first_ready = Event()
                release_first = Event()
                second_attempted = Event()
                errors = []

                def paused_write(lifecycle, state):
                    if current_thread().name == "lifecycle-first":
                        first_ready.set()
                        if not release_first.wait(10):
                            raise TimeoutError("First writer was not released")
                    original_write(lifecycle, state)

                def observed_flock(fd, operation):
                    if current_thread().name == "lifecycle-second" and operation == fcntl.LOCK_EX:
                        second_attempted.set()
                    return original_flock(fd, operation)

                def record(source_id, title):
                    try:
                        EventLifecycle(root, "topic-a").record_source(source_id, [self._item(title)])
                    except Exception as exc:
                        errors.append(exc)

                first = Thread(target=record, args=("feed-a", "First"), name="lifecycle-first")
                second = Thread(
                    target=record,
                    args=("feed-a" if same_source else "feed-b", "Second"),
                    name="lifecycle-second",
                )
                with patch.object(EventLifecycle, "_write_state", new=paused_write), patch(
                    "skrya_orchestrator.event_lifecycle.fcntl.flock", side_effect=observed_flock
                ):
                    first.start()
                    try:
                        self.assertTrue(first_ready.wait(10), "First writer did not reach persistence")
                        second.start()
                        self.assertTrue(second_attempted.wait(10), "Second writer did not attempt the lock")
                    finally:
                        release_first.set()
                        first.join(10)
                        if second.ident is not None:
                            second.join(10)
                self.assertFalse(first.is_alive())
                self.assertFalse(second.is_alive())
                self.assertEqual([], errors)
                state = json.loads(EventLifecycle(root, "topic-a").state_path.read_text())
                if same_source:
                    self.assertEqual(2, state["sources"]["feed-a"]["generation"])
                    self.assertEqual(2, len(state["sources"]["feed-a"]["events"]))
                    self.assertEqual(["Second"], [event["title"] for event in EventLifecycle(root, "topic-a").current_events()])
                else:
                    self.assertEqual({"feed-a", "feed-b"}, set(state["sources"]))
                    self.assertEqual({"First", "Second"}, {event["title"] for event in EventLifecycle(root, "topic-a").current_events()})

    def test_nonobject_state_is_rejected_without_replacing_original_bytes(self) -> None:
        for value in ([], None, "not an object", 42):
            with self.subTest(value=value):
                root = self._make_root(f"corrupt-{type(value).__name__}")
                lifecycle = EventLifecycle(root, "topic-a")
                lifecycle.state_path.parent.mkdir(parents=True)
                original = json.dumps(value).encode()
                lifecycle.state_path.write_bytes(original)
                with self.assertRaises(ValueError):
                    lifecycle.record_source("feed-a", [self._item("Story")])
                self.assertEqual(original, lifecycle.state_path.read_bytes())

    def test_preview_preserves_existing_state_and_unknown_fields(self) -> None:
        root = self._make_root("preview-existing")
        lifecycle = EventLifecycle(root, "topic-a")
        lifecycle.record_source("feed-a", [self._item("Story", custom_trace="trace")])
        state = json.loads(lifecycle.state_path.read_text())
        state["custom_state"] = {"keep": True}
        state["sources"]["feed-a"]["custom_source"] = "keep"
        lifecycle.state_path.write_text(json.dumps(state))
        before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

        preview = lifecycle.record_source("feed-a", [self._item("Story", content="Changed")], persist=False)

        self.assertEqual(2, preview[0]["generation"])
        self.assertEqual("trace", preview[0]["custom_trace"])
        self.assertEqual(before, {path: path.read_bytes() for path in root.rglob("*") if path.is_file()})
        lifecycle.record_source("feed-a", [self._item("Story", content="Changed")])
        saved = json.loads(lifecycle.state_path.read_text())
        self.assertEqual({"keep": True}, saved["custom_state"])
        self.assertEqual("keep", saved["sources"]["feed-a"]["custom_source"])

    def test_filter_window_zero_does_not_suppress_any_events(self) -> None:
        root = self._make_root("window-zero")
        lifecycle = EventLifecycle(root, "topic-a")
        events = lifecycle.identify_events([self._item("Repeat"), self._item("Fresh")])
        self._write_snapshot(root, "digest-20260101T090000+0800.events.json", events[:1])

        self.assertEqual(events, lifecycle.filter_recent(events, window=0))
        self.assertEqual(events[1:], lifecycle.filter_recent(events, window=1))

    def test_filter_uses_numeric_collision_suffix_for_last_three_real_snapshots(self) -> None:
        root = self._make_root("numeric-snapshots")
        lifecycle = EventLifecycle(root, "topic-a")
        events = lifecycle.identify_events([self._item(f"Story {suffix}") for suffix in (9, 10, 11, 12)])
        for suffix, event in zip((9, 10, 11, 12), events):
            self._write_snapshot(root, f"digest-20260101T090000+0800-{suffix}.events.json", [event])
        self._write_snapshot(root, "digest-not-a-real-execution.events.json", [events[0]])
        self._write_snapshot(root, "latest-digest-events.json", [events[0]])

        self.assertEqual(events[:1], lifecycle.filter_recent(events))
        self.assertEqual(events[:3], lifecycle.filter_recent(events, window=1))

    def test_filter_orders_execution_timestamps_across_timezones(self) -> None:
        root = self._make_root("timezone-snapshots")
        lifecycle = EventLifecycle(root, "topic-a")
        events = lifecycle.identify_events([self._item("Earlier"), self._item("Later")])
        self._write_snapshot(root, "digest-20260101T090000+0800.events.json", events[:1])
        self._write_snapshot(root, "digest-20260101T020000+0000.events.json", events[1:])

        self.assertEqual(events[:1], lifecycle.filter_recent(events, window=1))

    def test_unreadable_new_snapshot_does_not_displace_a_real_snapshot(self) -> None:
        root = self._make_root("unreadable-window")
        lifecycle = EventLifecycle(root, "topic-a")
        events = lifecycle.identify_events([self._item("Repeat"), self._item("Fresh")])
        self._write_snapshot(root, "digest-20260101T090000+0800.events.json", events[:1])
        (root / "runs" / "topic-a" / "digest-20260102T090000+0800.events.json").write_text("not JSON")

        self.assertEqual(events[1:], lifecycle.filter_recent(events, window=1))


    def test_record_source_refuses_linked_managed_state_paths(self) -> None:
        for component in ("runs", "topic", "state", "lock"):
            with self.subTest(component=component):
                root = self._make_root(f"state-linked-{component}")
                lifecycle = EventLifecycle(root, "topic-a")
                lifecycle.record_source("feed-a", [self._item("Story")])
                linked = {
                    "runs": root / "runs",
                    "topic": root / "runs" / "topic-a",
                    "state": lifecycle.state_path,
                    "lock": lifecycle.state_path.with_name("event-state.lock"),
                }[component]
                external = root / f"external-{component}"
                linked.rename(external)
                os.symlink(external, linked)
                before = {
                    path: path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file() and not path.is_symlink()
                }

                with self.assertRaises(ValueError):
                    EventLifecycle(root, "topic-a").record_source("feed-b", [self._item("Other story")])

                self.assertEqual(
                    before,
                    {path: path.read_bytes() for path in root.rglob("*") if path.is_file() and not path.is_symlink()},
                )
                self.assertTrue(linked.is_symlink())

    def test_state_staging_never_follows_a_preexisting_tmp_link(self) -> None:
        root = self._make_root("tmp-link")
        run_dir = root / "runs" / "topic-a"
        run_dir.mkdir(parents=True)
        outside = root / "frozen-digest.json"
        outside.write_bytes(b"frozen bytes must survive")
        tmp_link = run_dir / "event-state.tmp"
        os.symlink(outside, tmp_link)

        EventLifecycle(root, "topic-a").record_source("feed-a", [self._item("Story")])

        self.assertEqual(b"frozen bytes must survive", outside.read_bytes())
        self.assertTrue(tmp_link.is_symlink())
        state = json.loads(EventLifecycle(root, "topic-a").state_path.read_text(encoding="utf-8"))
        self.assertEqual(1, state["sources"]["feed-a"]["generation"])
        self.assertEqual("Story", next(iter(state["sources"]["feed-a"]["events"].values()))["title"])


class MigrateIngestV1Tests(unittest.TestCase):
    def _make_root(self, name: str) -> Path:
        root = TEST_TEMP_ROOT / f"migrate-{name}"
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _write_v1_latest(self, root: Path, topic_id: str = "agi-news") -> dict:
        payload = {
            "interface_version": "skrya.ingest.v1",
            "topic_id": topic_id,
            "retrieved_at": "2026-04-25T10:30:00+08:00",
            "producer": {"kind": "runtime-skill", "name": "agent-reach", "persistent": False},
            "items": [
                {
                    "id": "item-1",
                    "title": "Old v1 item",
                    "url": "https://example.com/old",
                    "source_name": "Example News",
                    "fetched_at": "2026-04-25T10:29:00+08:00",
                    "summary": "Old summary.",
                }
            ],
        }
        latest_path = root / "runs" / topic_id / "ingest" / "latest-ingest.json"
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def test_migrates_latest_state_with_backup_and_is_idempotent(self) -> None:
        root = self._make_root("basic")
        original = self._write_v1_latest(root)
        archived = root / "runs" / "agi-news" / "ingest" / "normalized" / "batch.json"
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_text('{"interface_version": "skrya.ingest.v1"}', encoding="utf-8")

        report = migrate_ingest_v1(root)

        self.assertEqual(1, len(report["migrated"]))
        self.assertEqual("agi-news", report["migrated"][0]["topic_id"])
        latest_path = root / "runs" / "agi-news" / "ingest" / "latest-ingest.json"
        converted = json.loads(latest_path.read_text(encoding="utf-8"))
        self.assertEqual("skrya.ingest.v2", converted["interface_version"])
        item = converted["items"][0]
        self.assertEqual("example.com", item["source_id"])
        self.assertTrue(item["event_id"])
        self.assertTrue(item["content_hash"])
        self.assertEqual({"example.com": 1}, converted["source_generations"])

        backup_path = Path(report["migrated"][0]["backup_path"])
        self.assertEqual(original, json.loads(backup_path.read_text(encoding="utf-8")))
        self.assertEqual(
            '{"interface_version": "skrya.ingest.v1"}',
            archived.read_text(encoding="utf-8"),
        )

        second = migrate_ingest_v1(root)
        self.assertEqual([], second["migrated"])
        self.assertEqual(["agi-news"], [entry["topic_id"] for entry in second["already_current"]])

    def test_failure_leaves_old_current_in_place(self) -> None:
        root = self._make_root("failure")
        original = self._write_v1_latest(root)
        latest_path = root / "runs" / "agi-news" / "ingest" / "latest-ingest.json"
        latest_path.write_text("{not json", encoding="utf-8")

        report = migrate_ingest_v1(root)

        self.assertEqual(1, len(report["failed"]))
        self.assertEqual([], report["migrated"])
        self.assertEqual("{not json", latest_path.read_text(encoding="utf-8"))
        self.assertFalse(
            (root / "runs" / "agi-news" / "ingest" / "latest-ingest.v1-backup.json").exists()
        )


    def test_migration_initializes_event_state_for_migrated_sources(self) -> None:
        root = self._make_root("migrate-init-state")
        payload = self._write_v1_latest(root)

        report = migrate_ingest_v1(root, "agi-news")

        self.assertEqual(["agi-news"], [entry["topic_id"] for entry in report["migrated"]])
        lifecycle = EventLifecycle(root, "agi-news")
        state = lifecycle.load_state()
        source_state = state["sources"]["example.com"]
        self.assertEqual("ingest", source_state["origin"])
        self.assertEqual(1, source_state["generation"])
        events = lifecycle.current_events("example.com")
        self.assertEqual([payload["items"][0]["title"]], [event["title"] for event in events])
        self.assertEqual(1, events[0]["generation"])

        # A rerun that only reports already_current never rewrites existing state.
        before = state
        rerun = migrate_ingest_v1(root, "agi-news")
        self.assertEqual([{"topic_id": "agi-news"}], rerun["already_current"])
        self.assertEqual(before, lifecycle.load_state())

    def test_concurrent_migration_never_overwrites_committed_v2_state(self) -> None:
        root = self._make_root("migrate-race")
        self._write_v1_latest(root)
        latest_path = root / "runs" / "agi-news" / "ingest" / "latest-ingest.json"

        committed = {
            "interface_version": "skrya.ingest.v2",
            "topic_id": "agi-news",
            "retrieved_at": "2026-04-26T10:30:00+08:00",
            "producer": {"kind": "runtime-skill", "name": "agent-reach", "persistent": False},
            "source_generations": {"example.com": 1},
            "items": identify_events(
                [
                    {
                        "id": "fresh",
                        "title": "Fresh committed item",
                        "url": "https://example.com/fresh",
                        "source_name": "Example News",
                        "fetched_at": "2026-04-26T10:29:00+08:00",
                        "summary": "Fresh summary.",
                    }
                ]
            ),
        }
        lifecycle = EventLifecycle(root, "agi-news")
        state = {"sources": {}}
        lifecycle.merge_source(state, "example.com", committed["items"], origin="ingest")
        lifecycle.commit_state(state)

        fired: list[bool] = []
        original_lock = EventLifecycle.state_lock

        def intruding_lock(lock_self):
            inner = original_lock(lock_self)

            class IntrudingLock:
                def __enter__(self):
                    inner.__enter__()
                    if not fired:
                        fired.append(True)
                        # A concurrent writer commits a newer v2 ingest right
                        # after this migration takes the lock and before it
                        # re-reads latest.
                        latest_path.write_text(
                            json.dumps(committed, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    return self

                def __exit__(self, *exc_info):
                    return inner.__exit__(*exc_info)

            return IntrudingLock()

        with patch.object(EventLifecycle, "state_lock", intruding_lock):
            report = migrate_ingest_v1(root, "agi-news")

        self.assertEqual([], report["migrated"])
        self.assertEqual([{"topic_id": "agi-news"}], report["already_current"])
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        self.assertEqual("Fresh committed item", latest["items"][0]["title"])
        self.assertEqual("Fresh committed item", lifecycle.current_events("example.com")[0]["title"])

    def test_migration_preserves_original_bytes_and_all_unknown_fields(self) -> None:
        root = self._make_root("unknown-bytes")
        payload = self._write_v1_latest(root)
        payload["custom_envelope"] = {"trace": "keep"}
        payload["producer"]["custom_producer"] = "keep"
        payload["items"][0]["custom_item"] = [1, 2]
        latest = root / "runs" / "agi-news" / "ingest" / "latest-ingest.json"
        original = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        latest.write_bytes(original)

        report = migrate_ingest_v1(root)

        self.assertEqual(["agi-news"], [entry["topic_id"] for entry in report["migrated"]])
        self.assertEqual(original, Path(report["migrated"][0]["backup_path"]).read_bytes())
        converted = json.loads(latest.read_bytes())
        self.assertEqual({"trace": "keep"}, converted["custom_envelope"])
        self.assertEqual("keep", converted["producer"]["custom_producer"])
        self.assertEqual([1, 2], converted["items"][0]["custom_item"])

    def test_conversion_and_durable_write_failures_preserve_original_current(self) -> None:
        targets = (
            "skrya_orchestrator.event_lifecycle._convert_v1_payload",
            "skrya_orchestrator.event_lifecycle.os.fsync",
            "skrya_orchestrator.event_lifecycle.os.replace",
        )
        for index, target in enumerate(targets):
            with self.subTest(target=target):
                root = self._make_root(f"atomic-failure-{index}")
                self._write_v1_latest(root)
                ingest_dir = root / "runs" / "agi-news" / "ingest"
                latest = ingest_dir / "latest-ingest.json"
                original = latest.read_bytes()
                backup = ingest_dir / "latest-ingest.v1-backup.json"
                with patch(target, side_effect=OSError("Injected migration failure")):
                    report = migrate_ingest_v1(root)
                self.assertEqual([], report["migrated"])
                self.assertEqual(1, len(report["failed"]))
                self.assertEqual(original, latest.read_bytes())
                if backup.exists():
                    self.assertEqual(original, backup.read_bytes())
                self.assertEqual([], list(ingest_dir.glob(".*.tmp")))
                recovered = migrate_ingest_v1(root)
                self.assertEqual(["agi-news"], [entry["topic_id"] for entry in recovered["migrated"]])

    def test_existing_unrelated_backup_is_never_overwritten(self) -> None:
        root = self._make_root("backup-conflict")
        self._write_v1_latest(root)
        ingest_dir = root / "runs" / "agi-news" / "ingest"
        latest = ingest_dir / "latest-ingest.json"
        original = latest.read_bytes()
        backup = ingest_dir / "latest-ingest.v1-backup.json"
        backup.write_bytes(b"An earlier unrelated recovery copy")

        report = migrate_ingest_v1(root)

        self.assertEqual([], report["migrated"])
        self.assertEqual(1, len(report["failed"]))
        self.assertEqual(original, latest.read_bytes())
        self.assertEqual(b"An earlier unrelated recovery copy", backup.read_bytes())

    def test_malformed_topics_fail_individually_without_losing_items(self) -> None:
        malformed = (
            {"items": None},
            {"items": "not a list"},
            {"items": ["not an item"]},
            {"items": [{"title": "Missing source and body"}]},
            {"topic_id": "other-topic"},
            {"producer": []},
        )
        root = self._make_root("malformed-topics")
        originals = {}
        for index, override in enumerate(malformed):
            topic_id = f"bad-{index}"
            payload = self._write_v1_latest(root, topic_id)
            payload.update(override)
            latest = root / "runs" / topic_id / "ingest" / "latest-ingest.json"
            latest.write_text(json.dumps(payload))
            originals[latest] = latest.read_bytes()
        self._write_v1_latest(root, "z-good")

        report = migrate_ingest_v1(root)

        self.assertEqual({f"bad-{index}" for index in range(len(malformed))}, {entry["topic_id"] for entry in report["failed"]})
        self.assertEqual(["z-good"], [entry["topic_id"] for entry in report["migrated"]])
        for latest, original in originals.items():
            self.assertEqual(original, latest.read_bytes())
            self.assertFalse(latest.with_name("latest-ingest.v1-backup.json").exists())

    def test_migration_refuses_linked_managed_inputs_and_outputs(self) -> None:
        for component in ("runs", "topic", "ingest", "latest", "backup"):
            with self.subTest(component=component):
                root = self._make_root(f"linked-{component}")
                self._write_v1_latest(root)
                ingest_dir = root / "runs" / "agi-news" / "ingest"
                latest = ingest_dir / "latest-ingest.json"
                original = latest.read_bytes()
                paths = {
                    "runs": root / "runs",
                    "topic": root / "runs" / "agi-news",
                    "ingest": ingest_dir,
                    "latest": latest,
                    "backup": ingest_dir / "latest-ingest.v1-backup.json",
                }
                linked = paths[component]
                external = root / f"external-{component}"
                if component == "backup":
                    external.write_bytes(b"External backup must not change")
                else:
                    linked.rename(external)
                os.symlink(external, linked)

                report = migrate_ingest_v1(root, "agi-news")

                self.assertEqual([], report["migrated"])
                self.assertEqual(1, len(report["failed"]))
                self.assertEqual(original, latest.read_bytes())
                self.assertTrue(linked.is_symlink())
                if component == "backup":
                    self.assertEqual(b"External backup must not change", external.read_bytes())
                elif component == "latest":
                    self.assertEqual(original, external.read_bytes())


class PruneIngestsTests(unittest.TestCase):
    def _make_root(self, name: str) -> Path:
        root = TEST_TEMP_ROOT / f"prune-{name}"
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _write_batches(self, root: Path, count: int, topic_id: str = "agi-news") -> list[str]:
        ingest_dir = root / "runs" / topic_id / "ingest"
        (ingest_dir / "normalized").mkdir(parents=True, exist_ok=True)
        (ingest_dir / "raw").mkdir(parents=True, exist_ok=True)
        stamps = []
        for index in range(count):
            stamp = f"2026-01-01T00-{index:02d}-00-00-00"
            retrieved_at = f"2026-01-01T00:{index:02d}:00+00:00"
            items = EventLifecycle(root, topic_id).identify_events([
                {
                    "id": f"i{index}",
                    "title": f"item {index}",
                    "url": f"https://example.com/item-{index}",
                    "fetched_at": retrieved_at,
                    "summary": f"Actual summary {index}",
                    "index": index,
                }
            ])
            payload = {
                "interface_version": "skrya.ingest.v2",
                "topic_id": topic_id,
                "retrieved_at": retrieved_at,
                "producer": {"name": "probe"},
                "source_generations": {"example.com": index + 1},
                "items": items,
            }
            (ingest_dir / "normalized" / f"{stamp}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (ingest_dir / "raw" / f"{stamp}-probe.txt").write_text(f"raw {index}", encoding="utf-8")
            stamps.append(stamp)
        return stamps

    def _protect_latest(self, root: Path, stamp: str) -> None:
        latest = root / "runs" / "agi-news" / "ingest" / "latest-ingest.json"
        latest.write_text(
            (root / "runs" / "agi-news" / "ingest" / "normalized" / f"{stamp}.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def test_dry_run_selects_oldest_batches_without_deletion(self) -> None:
        root = self._make_root("dry-run")
        stamps = self._write_batches(root, 12)

        report = prune_ingests(root, "agi-news", keep=10)

        self.assertEqual(12, report["total_batches"])
        self.assertEqual([], report["deleted"])
        self.assertEqual([f"{stamps[0]}.json", f"{stamps[1]}.json"], [batch["normalized"] for batch in report["selected"]])
        self.assertEqual(
            [f"{stamps[0]}-probe.txt", f"{stamps[1]}-probe.txt"],
            [batch["raw"][0] for batch in report["selected"]],
        )
        self.assertTrue((root / "runs" / "agi-news" / "ingest" / "normalized" / f"{stamps[0]}.json").exists())
        self.assertTrue((root / "runs" / "agi-news" / "ingest" / "raw" / f"{stamps[1]}-probe.txt").exists())

    def test_apply_deletes_selected_including_raw_and_protects_latest(self) -> None:
        root = self._make_root("apply")
        stamps = self._write_batches(root, 12)
        self._protect_latest(root, stamps[11])

        report = prune_ingests(root, "agi-news", keep=10, apply=True)

        self.assertEqual(
            [f"normalized/{stamps[0]}.json", f"raw/{stamps[0]}-probe.txt", f"normalized/{stamps[1]}.json", f"raw/{stamps[1]}-probe.txt"],
            report["deleted"],
        )
        self.assertFalse((root / "runs" / "agi-news" / "ingest" / "normalized" / f"{stamps[0]}.json").exists())
        self.assertFalse((root / "runs" / "agi-news" / "ingest" / "raw" / f"{stamps[0]}-probe.txt").exists())
        for index in range(2, 12):
            self.assertTrue((root / "runs" / "agi-news" / "ingest" / "normalized" / f"{stamps[index]}.json").exists())
            self.assertTrue((root / "runs" / "agi-news" / "ingest" / "raw" / f"{stamps[index]}-probe.txt").exists())
        self.assertTrue((root / "runs" / "agi-news" / "ingest" / "latest-ingest.json").exists())

    def test_apply_protects_identical_batch_and_never_touches_unrelated_files(self) -> None:
        root = self._make_root("protect")
        stamps = self._write_batches(root, 4)
        latest = root / "runs" / "agi-news" / "ingest" / "latest-ingest.json"
        latest.write_text(
            (root / "runs" / "agi-news" / "ingest" / "normalized" / f"{stamps[0]}.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        run_dir = root / "runs" / "agi-news"
        (run_dir / "event-state.json").write_text("{}", encoding="utf-8")
        (run_dir / "digest-20260101T000000+0800.events.json").write_text("{}", encoding="utf-8")
        (run_dir / "latest-ingest.v1-backup.json").write_text("{}", encoding="utf-8")
        threads_dir = run_dir / "threads"
        threads_dir.mkdir(parents=True, exist_ok=True)
        (threads_dir / "latest-threads.json").write_text("{}", encoding="utf-8")
        link = root / "runs" / "agi-news" / "ingest" / "normalized" / "link.json"
        os.symlink(run_dir / "event-state.json", link)

        prune_ingests(root, "agi-news", keep=1, apply=True)

        self.assertTrue(latest.exists())
        self.assertTrue((run_dir / "event-state.json").exists())
        self.assertTrue((run_dir / "digest-20260101T000000+0800.events.json").exists())
        self.assertTrue((run_dir / "latest-ingest.v1-backup.json").exists())
        self.assertTrue((threads_dir / "latest-threads.json").exists())
        self.assertTrue((root / "runs" / "agi-news" / "ingest" / "normalized" / f"{stamps[0]}.json").exists())
        self.assertTrue(link.is_symlink() and link.exists())

    def test_prune_orders_parsed_retrieved_at_utc_then_real_write_order(self) -> None:
        root = self._make_root("order-boundary")
        ingest_dir = root / "runs" / "agi-news" / "ingest"
        normalized_dir = ingest_dir / "normalized"
        raw_dir = ingest_dir / "raw"
        normalized_dir.mkdir(parents=True)
        raw_dir.mkdir(parents=True)

        def write_batch(name: str, retrieved_at: str, label: str, mtime_ns: int) -> None:
            payload = {
                "interface_version": "skrya.ingest.v2",
                "topic_id": "agi-news",
                "retrieved_at": retrieved_at,
                "producer": {"name": "probe"},
                "source_generations": {"example.com": 1},
                "items": EventLifecycle(root, "agi-news").identify_events(
                    [
                        {
                            "title": label,
                            "url": f"https://example.com/{label}",
                            "fetched_at": retrieved_at,
                            "summary": f"Actual summary {label}",
                        }
                    ]
                ),
            }
            path = normalized_dir / name
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            raw = raw_dir / f"{path.stem}-probe.txt"
            raw.write_text(label, encoding="utf-8")
            os.utime(path, ns=(mtime_ns, mtime_ns))
            os.utime(raw, ns=(mtime_ns, mtime_ns))

        oldest_stamp = "2026-10-20T06-00-00-02-00"  # 04:00Z despite the latest-looking filename
        collision_stamp = "2026-10-20T04-30-00-00-00"
        newest_stamp = "2026-10-20T05-00-00-00-00"
        write_batch(f"{oldest_stamp}.json", "2026-10-20T06:00:00+02:00", "offset-old", 10)
        write_batch(f"{collision_stamp}.json", "2026-10-20T04:30:00+00:00", "collision-first", 20)
        write_batch(f"{collision_stamp}-abcd1234.json", "2026-10-20T04:30:00+00:00", "collision-second", 20)
        write_batch(f"{newest_stamp}.json", "2026-10-20T05:00:00+00:00", "utc-latest", 30)

        keep_two = prune_ingests(root, "agi-news", keep=2)
        self.assertEqual(
            [f"{oldest_stamp}.json", f"{collision_stamp}.json"],
            [batch["normalized"] for batch in keep_two["selected"]],
        )

        keep_one = prune_ingests(root, "agi-news", keep=1)
        self.assertEqual(
            [f"{oldest_stamp}.json", f"{collision_stamp}.json", f"{collision_stamp}-abcd1234.json"],
            [batch["normalized"] for batch in keep_one["selected"]],
        )

        report = prune_ingests(root, "agi-news", keep=2, apply=True)
        self.assertEqual(
            [
                f"normalized/{oldest_stamp}.json",
                f"raw/{oldest_stamp}-probe.txt",
                f"normalized/{collision_stamp}.json",
                f"raw/{collision_stamp}-probe.txt",
            ],
            report["deleted"],
        )
        self.assertTrue((normalized_dir / f"{collision_stamp}-abcd1234.json").exists())
        self.assertTrue((normalized_dir / f"{newest_stamp}.json").exists())

    def test_missing_ingest_dir_reports_empty(self) -> None:
        root = self._make_root("missing")

        report = prune_ingests(root, "agi-news")

        self.assertEqual(0, report["total_batches"])
        self.assertEqual([], report["selected"])


    def test_longest_batch_stem_protects_latest_collision_raw_files(self) -> None:
        root = self._make_root("raw-collision")
        stamp = self._write_batches(root, 1)[0]
        ingest_dir = root / "runs" / "agi-news" / "ingest"
        old_path = ingest_dir / "normalized" / f"{stamp}.json"
        payload = json.loads(old_path.read_text())
        payload["source_generations"] = {"example.com": 2}
        payload["items"] = EventLifecycle(root, "agi-news").identify_events([
            dict(payload["items"][0], summary="Updated actual article summary")
        ])
        newest_stem = f"{stamp}-abcd1234-10"
        newest_path = ingest_dir / "normalized" / f"{newest_stem}.json"
        newest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        newest_raw = ingest_dir / "raw" / f"{newest_stem}-probe.txt"
        newest_raw.write_text("Protected newer raw")
        (ingest_dir / "latest-ingest.json").write_bytes(newest_path.read_bytes())

        preview = prune_ingests(root, "agi-news", keep=0)
        report = prune_ingests(root, "agi-news", keep=0, apply=True)

        self.assertEqual([{"normalized": f"{stamp}.json", "raw": [f"{stamp}-probe.txt"]}], preview["selected"])
        self.assertEqual(preview["selected"], report["selected"])
        self.assertEqual([f"normalized/{stamp}.json", f"raw/{stamp}-probe.txt"], report["deleted"])
        self.assertEqual("Protected newer raw", newest_raw.read_text())
        self.assertEqual(payload, json.loads(newest_path.read_text()))

    def test_unowned_json_and_ambiguous_raw_files_are_never_selected(self) -> None:
        root = self._make_root("ownership")
        stamp = self._write_batches(root, 1)[0]
        ingest_dir = root / "runs" / "agi-news" / "ingest"
        normalized_dir = ingest_dir / "normalized"
        raw_dir = ingest_dir / "raw"
        legitimate_payload = json.loads((normalized_dir / f"{stamp}.json").read_text())
        unowned = {
            "2020-01-01T00-00-00-00-00.json": {"notes": "Manual notes with timestamp-looking name"},
            f"{stamp}-abcd1234.json": {"notes": "Protected ambiguous longer prefix"},
            f"{stamp}.events.json": legitimate_payload,
            f"{stamp}.v1-backup.json": legitimate_payload,
            "other-topic.json": dict(legitimate_payload, topic_id="other-topic"),
            "malformed.json": dict(legitimate_payload, items=["not an item"]),
        }
        for name, payload in unowned.items():
            (normalized_dir / name).write_text(json.dumps(payload))
        unrelated_raw = (
            f"{stamp}-notes.txt",
            f"{stamp}-probe.json",
            f"{stamp}-probe-backup.zip",
            f"{stamp}-abcd1234-probe.txt",
        )
        for name in unrelated_raw:
            (raw_dir / name).write_text("Unrelated raw evidence")
        before = {path: path.read_bytes() for path in ingest_dir.rglob("*") if path.is_file()}

        preview = prune_ingests(root, "agi-news", keep=0)

        self.assertEqual(before, {path: path.read_bytes() for path in ingest_dir.rglob("*") if path.is_file()})
        self.assertEqual([{"normalized": f"{stamp}.json", "raw": [f"{stamp}-probe.txt"]}], preview["selected"])
        report = prune_ingests(root, "agi-news", keep=0, apply=True)
        self.assertEqual(1, report["total_batches"])
        self.assertEqual(set(unowned), set(report["protected_batches"]))
        for name in unowned:
            self.assertEqual(before[normalized_dir / name], (normalized_dir / name).read_bytes())
        for name in unrelated_raw:
            self.assertEqual("Unrelated raw evidence", (raw_dir / name).read_text())
        self.assertFalse((normalized_dir / f"{stamp}.json").exists())
        self.assertFalse((raw_dir / f"{stamp}-probe.txt").exists())

    def test_prune_refuses_all_linked_managed_parent_directories(self) -> None:
        for component in ("runs", "topic", "ingest", "normalized", "raw"):
            with self.subTest(component=component):
                root = self._make_root(f"linked-{component}")
                stamp = self._write_batches(root, 1)[0]
                ingest_dir = root / "runs" / "agi-news" / "ingest"
                normalized = ingest_dir / "normalized" / f"{stamp}.json"
                raw = ingest_dir / "raw" / f"{stamp}-probe.txt"
                original_normalized = normalized.read_bytes()
                original_raw = raw.read_bytes()
                linked = {
                    "runs": root / "runs",
                    "topic": root / "runs" / "agi-news",
                    "ingest": ingest_dir,
                    "normalized": ingest_dir / "normalized",
                    "raw": ingest_dir / "raw",
                }[component]
                external = root / f"external-{component}"
                linked.rename(external)
                os.symlink(external, linked)

                report = prune_ingests(root, "agi-news", keep=0, apply=True)

                self.assertEqual([], report["selected"])
                self.assertEqual([], report["deleted"])
                self.assertEqual(1, len(report["failed"]))
                self.assertEqual(original_normalized, normalized.read_bytes())
                self.assertEqual(original_raw, raw.read_bytes())
                self.assertTrue(linked.is_symlink())

    def test_migrated_latest_keeps_its_original_v1_archive_and_raw_provenance(self) -> None:
        root = self._make_root("migrated-latest")
        obsolete = self._write_batches(root, 1)[0]
        payload = MigrateIngestV1Tests()._write_v1_latest(root)
        ingest_dir = root / "runs" / "agi-news" / "ingest"
        latest = ingest_dir / "latest-ingest.json"
        original = latest.read_bytes()
        stamp = "2026-04-25T10-30-00-08-00"
        archive = ingest_dir / "normalized" / f"{stamp}.json"
        archive.write_bytes(original)
        raw = ingest_dir / "raw" / f"{stamp}-agent-reach.txt"
        raw.write_text("Original latest v1 evidence")

        migration = migrate_ingest_v1(root)
        report = prune_ingests(root, "agi-news", keep=0, apply=True)

        self.assertEqual(["agi-news"], [entry["topic_id"] for entry in migration["migrated"]])
        self.assertEqual([f"{stamp}.json"], report["protected_batches"])
        self.assertEqual(original, archive.read_bytes())
        self.assertEqual("Original latest v1 evidence", raw.read_text())
        self.assertEqual(payload, json.loads((ingest_dir / "latest-ingest.v1-backup.json").read_bytes()))
        self.assertEqual("skrya.ingest.v2", json.loads(latest.read_bytes())["interface_version"])
        self.assertEqual([f"normalized/{obsolete}.json", f"raw/{obsolete}-probe.txt"], report["deleted"])

    def test_partial_unlink_failure_reports_each_path_actually_removed(self) -> None:
        root = self._make_root("partial-unlink")
        stamp = self._write_batches(root, 1)[0]
        ingest_dir = root / "runs" / "agi-news" / "ingest"
        extra_raw = ingest_dir / "raw" / f"{stamp}-probe-1.txt"
        extra_raw.write_text("Another owned raw capture")
        blocked_raw = ingest_dir / "raw" / f"{stamp}-probe.txt"
        original_unlink = Path.unlink

        def unlink(path, *args, **kwargs):
            if path == blocked_raw:
                raise PermissionError("Injected raw deletion failure")
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", new=unlink):
            report = prune_ingests(root, "agi-news", keep=0, apply=True)

        self.assertEqual([f"normalized/{stamp}.json", f"raw/{extra_raw.name}"], report["deleted"])
        self.assertEqual([f"raw/{blocked_raw.name}"], [entry["path"] for entry in report["failed"]])
        self.assertFalse((ingest_dir / "normalized" / f"{stamp}.json").exists())
        self.assertFalse(extra_raw.exists())
        self.assertEqual("raw 0", blocked_raw.read_text())


if __name__ == "__main__":
    unittest.main()
