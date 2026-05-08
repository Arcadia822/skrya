import json
import shutil
import unittest
from pathlib import Path

from skrya_orchestrator.delivery import DeliveryBindingService, DeliveryContext


ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = ROOT / "tmp" / "unit-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class DeliveryBindingServiceTests(unittest.TestCase):
    def test_matches_only_current_channel_binding(self) -> None:
        root = self._make_root("delivery-current-channel")
        self._write_topic(root, "ai-browser")
        self._write_topic(root, "military-civil")
        service = DeliveryBindingService(root)
        service.write_binding("ai-browser", self._binding("ai-browser", channel_id="chan-ai"))
        service.write_binding("military-civil", self._binding("military-civil", channel_id="chan-military"))

        match = service.match_current_context(DeliveryContext(host="openclaw", channel_id="chan-ai"))

        self.assertEqual("single", match.status)
        self.assertEqual(["ai-browser"], match.topic_ids)

    def test_no_current_channel_binding_does_not_return_global_topics(self) -> None:
        root = self._make_root("delivery-no-global-fallback")
        self._write_topic(root, "ai-browser")
        self._write_topic(root, "military-civil")
        service = DeliveryBindingService(root)
        service.write_binding("ai-browser", self._binding("ai-browser", channel_id="chan-ai"))
        service.write_binding("military-civil", self._binding("military-civil", channel_id="chan-military"))

        match = service.match_current_context(DeliveryContext(host="openclaw", channel_id="chan-unknown"))

        self.assertEqual("none", match.status)
        self.assertEqual([], match.topic_ids)

    def test_label_only_matches_report_ambiguity_instead_of_guessing(self) -> None:
        root = self._make_root("delivery-label-ambiguous")
        self._write_topic(root, "topic-a")
        self._write_topic(root, "topic-b")
        service = DeliveryBindingService(root)
        service.write_binding("topic-a", self._binding("topic-a", channel_id="", channel_label="每日简报"))
        service.write_binding("topic-b", self._binding("topic-b", channel_id="", channel_label="每日简报"))

        match = service.match_current_context(DeliveryContext(host="openclaw", channel_label="每日简报"))

        self.assertEqual("ambiguous", match.status)
        self.assertEqual(["topic-a", "topic-b"], sorted(match.topic_ids))

    def test_workspace_context_filters_other_workspace_bindings_when_available(self) -> None:
        root = self._make_root("delivery-workspace-filter")
        self._write_topic(root, "topic-a")
        self._write_topic(root, "topic-b")
        service = DeliveryBindingService(root)
        service.write_binding("topic-a", self._binding("topic-a", channel_id="chan-shared", workspace_id="workspace-a"))
        service.write_binding("topic-b", self._binding("topic-b", channel_id="chan-shared", workspace_id="workspace-b"))

        match = service.match_current_context(
            DeliveryContext(host="openclaw", channel_id="chan-shared", workspace_id="workspace-b")
        )

        self.assertEqual("single", match.status)
        self.assertEqual(["topic-b"], match.topic_ids)

    def test_rejects_raw_host_context_without_normalized_channel_or_conversation(self) -> None:
        root = self._make_root("delivery-invalid-schema")
        self._write_topic(root, "ai-browser")
        service = DeliveryBindingService(root)

        with self.assertRaisesRegex(ValueError, "must identify a channel or conversation"):
            service.write_binding(
                "ai-browser",
                {
                    "topic_id": "ai-browser",
                    "host": "openclaw",
                    "scope": "channel",
                    "status": "active",
                    "host_metadata": {"raw_openclaw_context": {"channel": "hidden in raw blob"}},
                },
            )

    def test_write_binding_updates_existing_binding_for_same_stable_identity(self) -> None:
        root = self._make_root("delivery-update-existing")
        self._write_topic(root, "ai-browser")
        service = DeliveryBindingService(root)
        service.write_binding("ai-browser", self._binding("ai-browser", channel_id="chan-ai", schedule="daily 08:00"))
        path = service.write_binding("ai-browser", self._binding("ai-browser", channel_id="chan-ai", schedule="daily 09:00"))

        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual("skrya.delivery-bindings.v1", payload["schema"])
        self.assertEqual(1, len(payload["bindings"]))
        self.assertEqual("daily 09:00", payload["bindings"][0]["automation"]["schedule"])

    @staticmethod
    def _make_root(name: str) -> Path:
        root = TEST_TEMP_ROOT / name
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        (root / ".skrya").mkdir(parents=True, exist_ok=True)
        (root / ".skrya" / "config.json").write_text(json.dumps({"data_root": "."}), encoding="utf-8")
        return root

    @staticmethod
    def _write_topic(root: Path, topic_id: str) -> None:
        topic_dir = root / "topics" / topic_id
        topic_dir.mkdir(parents=True)
        (topic_dir / "topic.json").write_text(json.dumps({"topic": topic_id}), encoding="utf-8")

    @staticmethod
    def _binding(
        topic_id: str,
        *,
        channel_id: str = "chan-1",
        channel_label: str = "Channel",
        workspace_id: str = "workspace-1",
        schedule: str = "daily 08:00",
    ) -> dict:
        channel = {"label": channel_label}
        if channel_id:
            channel["id"] = channel_id
        return {
            "id": f"openclaw:workspace:{channel_id or channel_label}:{topic_id}",
            "topic_id": topic_id,
            "host": "openclaw",
            "scope": "channel",
            "channel": channel,
            "workspace": {"id": workspace_id},
            "automation": {"id": f"auto-{topic_id}", "schedule": schedule},
            "status": "active",
            "host_metadata": {"message_tool": "wechat"},
        }


if __name__ == "__main__":
    unittest.main()
