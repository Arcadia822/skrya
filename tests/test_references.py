import json
from pathlib import Path
import sys
import tempfile
import unittest

SRC_DIR = Path(__file__).parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skrya_orchestrator.references import (
    SNAPSHOT_SCHEMA,
    build_snapshot,
    load_snapshot,
    resolve_reference,
    snapshot_path,
)


class ReferencesTests(unittest.TestCase):
    def test_snapshot_path_resolves_symlinks_and_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / "digest-20261019T060000+0800.md"
            target.write_text("# Digest", encoding="utf-8")
            latest = root / "latest-digest.md"
            latest.symlink_to(target.name)

            expected = (root / "digest-20261019T060000+0800.events.json").resolve()
            self.assertEqual(snapshot_path(target), expected)
            self.assertEqual(snapshot_path(latest), expected)

            events_json = (root / "digest-20261019T060000+0800.events.json").resolve()
            self.assertEqual(snapshot_path(events_json), events_json)

            legacy_events = root / "latest-digest-events.json"
            legacy_events.write_text("{}", encoding="utf-8")
            self.assertEqual(snapshot_path(legacy_events), expected)
    def test_build_snapshot_structure_and_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            artifact = root / "digest-20261019T060000+0800.md"
            items = [
                {
                    "key": "event-alpha",
                    "number": 1,
                    "title": "新闻标题一",
                    "sources": ["https://example.com/s1"],
                    "date": "2026-10-19",
                    "custom_metric": 999,
                },
                {
                    "key": "event-beta",
                    "title": "新闻标题二",
                    "sources": ["https://example.com/s2"],
                    "date": "2026-10-19",
                },
            ]
            threads = [
                {
                    "id": "th-tariffs",
                    "name": "关税线",
                    "status": "active",
                    "timeline": [{"date": "2026-10-18", "headline": "初步接触"}],
                    "custom_thread_tag": "vip",
                }
            ]

            snapshot = build_snapshot("policy", artifact, items, threads)
            self.assertEqual(snapshot["schema"], SNAPSHOT_SCHEMA)
            self.assertEqual(snapshot["topic_id"], "policy")
            self.assertEqual(snapshot["artifact_path"], str(artifact.resolve()))
            self.assertTrue(snapshot["raw_archive_path"].endswith("latest-threads.json"))

            self.assertIn("N-01", snapshot["items"])
            self.assertIn("N-02", snapshot["items"])
            self.assertEqual(snapshot["items"]["N-01"]["key"], "event-alpha")
            self.assertEqual(snapshot["items"]["N-01"]["custom_metric"], 999)
            self.assertEqual(snapshot["items"]["N-02"]["key"], "event-beta")
            self.assertEqual(snapshot["items"]["N-02"]["number"], 2)

            self.assertIn("T-01", snapshot["threads"])
            self.assertEqual(snapshot["threads"]["T-01"]["id"], "th-tariffs")
            self.assertEqual(snapshot["threads"]["T-01"]["custom_thread_tag"], "vip")
            self.assertTrue(snapshot["threads"]["T-01"]["raw_archive_path"].endswith("latest-threads.json"))

    def test_load_snapshot_reads_and_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            artifact = root / "digest-test.md"
            artifact.write_text("# Digest", encoding="utf-8")
            items = [{"key": "k1", "title": "t1", "number": 1}]
            payload = build_snapshot("tech", artifact, items, [])
            sidecar = snapshot_path(artifact)
            sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            loaded = load_snapshot(artifact)
            self.assertEqual(loaded["topic_id"], "tech")
            self.assertIn("N-01", loaded["items"])
            self.assertEqual(loaded["artifact_sha256"], payload["artifact_sha256"])

            loaded_sidecar = load_snapshot(sidecar)
            self.assertEqual(loaded_sidecar["topic_id"], "tech")

            with self.assertRaises(FileNotFoundError):
                load_snapshot(root / "nonexistent.md")
    def test_resolve_reference_normalizes_and_resolves(self):
        snapshot = {
            "schema": SNAPSHOT_SCHEMA,
            "topic_id": "world",
            "artifact_path": "/tmp/test/digest.md",
            "raw_archive_path": "/tmp/test/threads/latest-threads.json",
            "items": {
                "N-01": {"key": "news-1", "title": "第一条新闻"},
                "N-02": {"key": "news-2", "title": "第二条新闻"},
            },
            "threads": {
                "T-01": {"id": "thread-main", "name": "核心事件线"},
            },
        }

        res1 = resolve_reference(snapshot, "N-01")
        self.assertEqual(res1["kind"], "news")
        self.assertEqual(res1["reference"], "N-01")
        self.assertEqual(res1["entity"]["key"], "news-1")

        res_bare = resolve_reference(snapshot, "1")
        self.assertEqual(res_bare["reference"], "N-01")
        self.assertEqual(res_bare["kind"], "news")

        res_prefix = resolve_reference(snapshot, "dig: N-02")
        self.assertEqual(res_prefix["reference"], "N-02")
        self.assertEqual(res_prefix["entity"]["key"], "news-2")

        res_track = resolve_reference(snapshot, "track: N-01")
        self.assertEqual(res_track["reference"], "N-01")

        res_thread = resolve_reference(snapshot, "T-01")
        self.assertEqual(res_thread["kind"], "thread")
        self.assertEqual(res_thread["reference"], "T-01")
        self.assertEqual(res_thread["entity"]["id"], "thread-main")
        self.assertEqual(res_thread["raw_archive_path"], "/tmp/test/threads/latest-threads.json")

        res_write = resolve_reference(snapshot, "write: T-01")
        self.assertEqual(res_write["reference"], "T-01")
        self.assertEqual(res_write["kind"], "thread")

        with self.assertRaises(ValueError):
            resolve_reference(snapshot, "N-99")

        with self.assertRaises(ValueError):
            resolve_reference(snapshot, "T-99")

        with self.assertRaises(ValueError):
            resolve_reference(snapshot, "invalid-token")

        with self.assertRaises(ValueError):
            resolve_reference(snapshot, "")
    def test_build_snapshot_missing_key_derives_stable_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            artifact = root / "digest-hash.md"
            artifact.write_text("# Digest Hash Test\nContent", encoding="utf-8")
            items = [
                {
                    "number": 1,
                    "title": "无 Key 新闻测试",
                    "sources": ["https://example.com/unique-source"],
                    "date": "2026-10-19",
                }
            ]
            snapshot = build_snapshot("tech", artifact, items, [])
            key = snapshot["items"]["N-01"]["key"]
            self.assertTrue(key.startswith("event-"))
            self.assertNotEqual(key, "event-1")

            snapshot2 = build_snapshot("tech", artifact, items, [])
            self.assertEqual(snapshot2["items"]["N-01"]["key"], key)

    def test_build_snapshot_computes_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            import hashlib
            root = Path(tmp).resolve()
            artifact = root / "digest-sha.md"
            content = b"# Real bytes for sha test\n"
            artifact.write_bytes(content)
            expected_sha = hashlib.sha256(content).hexdigest()

            snapshot = build_snapshot("tech", artifact, [], [])
            self.assertEqual(snapshot["artifact_sha256"], expected_sha)

    def test_build_snapshot_rejects_duplicate_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            artifact = root / "digest-dup.md"
            artifact.write_text("# Dup", encoding="utf-8")
            items = [
                {"number": 1, "key": "k1", "title": "t1"},
                {"number": 1, "key": "k2", "title": "t2"},
            ]
            with self.assertRaises(ValueError):
                build_snapshot("tech", artifact, items, [])
    def test_load_and_resolve_reject_invalid_schema(self):
        invalid_snap = {
            "schema": "wrong.schema.v99",
            "topic_id": "tech",
            "artifact_path": "/tmp/a.md",
            "items": {},
            "threads": {},
        }
        with self.assertRaises(ValueError):
            resolve_reference(invalid_snap, "N-01")

    def test_load_snapshot_rejects_changed_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            artifact = root / "digest-changed.md"
            artifact.write_text("# Original Content\n", encoding="utf-8")
            items = [{"key": "k1", "title": "t1", "number": 1}]
            snapshot = build_snapshot("tech", artifact, items, [])
            sidecar = snapshot_path(artifact)
            sidecar.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

            artifact.write_text("# Tampered Content\n", encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                load_snapshot(artifact)
            self.assertIn("sha256", str(ctx.exception).lower())

    def test_load_snapshot_rejects_wrong_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            artifact_a = root / "digest-a.md"
            artifact_a.write_text("# Content A\n", encoding="utf-8")
            artifact_b = root / "digest-b.md"
            artifact_b.write_text("# Content B\n", encoding="utf-8")

            items = [{"key": "k1", "title": "t1", "number": 1}]
            snapshot_a = build_snapshot("tech", artifact_a, items, [])

            sidecar_b = snapshot_path(artifact_b)
            sidecar_b.write_text(json.dumps(snapshot_a, ensure_ascii=False, indent=2), encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                load_snapshot(artifact_b)
            self.assertIn("does not match", str(ctx.exception).lower())

    def test_load_snapshot_raises_when_artifact_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            artifact = root / "digest-missing.md"
            artifact.write_text("# Temporary\n", encoding="utf-8")
            snapshot = build_snapshot("tech", artifact, [], [])
            sidecar = snapshot_path(artifact)
            sidecar.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

            artifact.unlink()
            with self.assertRaises(FileNotFoundError):
                load_snapshot(sidecar)

if __name__ == "__main__":
    unittest.main()
