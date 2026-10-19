import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skrya_orchestrator.delivery_receipts import DeliveryError, DeliveryUnknownError
from skrya_orchestrator.feishu_api import (
    FeishuAPIError,
    FeishuCardFormatError,
    FeishuPermissionError,
    FeishuThreadNotSupportedError,
    FeishuUnknownError,
)
from skrya_orchestrator.feishu_delivery import FeishuDeliveryService
from skrya_orchestrator.references import build_snapshot


class RemoteBoundary:
    def __init__(self):
        self.calls = []
        self.accepted = []
        self.mode = None
        self.fail_at = None
        self.attempts = 0

    def get_tenant_access_token(self, app_id, app_secret, origin=None):
        self.calls.append("token")
        return "isolated-test-token"

    def check_read_access(self, token, target, target_type, origin=None):
        self.calls.append("read")
        return {"read_access": True, "permission_guaranteed": False}

    def _send(self, route, msg_type, content, message_uuid):
        self.attempts += 1
        self.calls.append(route)
        if self.mode == "unknown":
            raise FeishuUnknownError("response lost")
        if self.mode == "permission":
            raise FeishuPermissionError("card messaging permission denied")
        if self.fail_at == self.attempts:
            raise FeishuAPIError("request rejected")
        if self.mode == "no-thread" and route == "reply":
            raise FeishuThreadNotSupportedError("thread unsupported")
        if self.mode == "format" and msg_type == "interactive":
            raise FeishuCardFormatError("invalid card")
        message = {"route": route, "type": msg_type, "content": content, "uuid": message_uuid,
                   "message_id": f"om_{len(self.accepted) + 1}"}
        self.accepted.append(message)
        return {"message_id": message["message_id"]}

    def send_message(self, token, receive_id, msg_type, content, uuid, origin=None):
        return self._send("send", msg_type, content, uuid)

    def reply_message(self, token, message_id, msg_type, content, uuid, reply_in_thread=True, origin=None, *, target=None):
        if not message_id or not target or not reply_in_thread:
            raise AssertionError("Reply lost its root or destination pacing key")
        return self._send("reply", msg_type, content, uuid)


class FeishuDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.env = patch.dict(os.environ, {"SKRYA_FEISHU_APP_ID": "cli_test", "SKRYA_FEISHU_APP_SECRET": "test_secret"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.topic = "news"
        self.binding = "creator.channel.topic"
        self.target = "oc_destination"
        topic = self.root / "topics" / self.topic
        topic.mkdir(parents=True)
        self.binding_path = topic / "delivery-bindings.json"
        self.write_binding()
        self.api = RemoteBoundary()
        self.service = FeishuDeliveryService(self.root, self.api)

    def write_binding(self, layout="full-card", **options):
        self.binding_path.write_text(json.dumps({"schema": "skrya.delivery-bindings.v1", "bindings": [{
            "id": self.binding, "topic_id": self.topic, "host": "dsh", "scope": "channel", "status": "active",
            "channel": {"id": "oc_creator_context"},
            "target": {"channel": "feishu", "kind": "group", "ref": self.target},
            "delivery": {"layout": layout, **options},
        }]}), encoding="utf-8")

    def artifact(self, name="digest.md", count=2, size=1, key_prefix="news"):
        directory = self.root / "runs" / self.topic
        directory.mkdir(parents=True, exist_ok=True)
        artifact = directory / name
        lines = ["# 2026-10-19｜新闻｜每日简报", "", "## 今日简讯", ""]
        items = []
        for number in range(1, count + 1):
            facts = f"第{number}项完整事实。" * size
            url = f"https://example.org/news/{number}"
            lines.extend([f"### N-{number:02d} 事件{number} ｜ 2026-10-19", facts, "为何重要：正式行动改变状态。", f"信源：[媒体]({url})", ""])
            items.append({"number": number, "key": f"{key_prefix}-{number}", "title": f"事件{number}", "date": "2026-10-19", "sources": [url], "analysis_body": facts})
        lines.extend(["## 可继续操作", "- dig: N-01", "- track: N-02", "- dig: T-01", "- write: T-01", "- 自然语言反馈"])
        artifact.write_text("\n".join(lines), encoding="utf-8")
        artifact.with_suffix(".events.json").write_text(json.dumps(build_snapshot(self.topic, artifact, items, [])), encoding="utf-8")
        return artifact

    def test_preflight_never_sends_and_does_not_pretend_delivery_permission(self):
        result = self.service.check(self.topic, self.target, self.binding)
        self.assertEqual(["token", "read"], self.api.calls)
        self.assertFalse(result["permission_guaranteed"])
        self.assertEqual([], self.api.accepted)

    def test_explicit_recipient_cannot_be_redirected_by_alias_configuration(self):
        config = self.root / "credentials.json"
        config.write_text(json.dumps({"targets": {self.target: {"chatId": "oc_other"}}}))
        os.environ["SKRYA_FEISHU_CONFIG"] = str(config)
        result = self.service.check(self.topic, self.target, self.binding)
        self.assertEqual(self.target, result["resolved_target"])

    def test_alias_selection_skips_unrelated_configuration(self):
        payload = json.loads(self.binding_path.read_text())
        first = payload["bindings"][0]
        first["target"]["ref"] = "team-a"
        first["delivery"]["credential_ref"] = "a.json"
        second = json.loads(json.dumps(first))
        second["id"] = "second-binding"
        second["channel"]["id"] = "other-channel"
        second["target"]["ref"] = "team-b"
        second["delivery"]["credential_ref"] = "b.json"
        payload["bindings"].append(second)
        self.binding_path.write_text(json.dumps(payload))
        for alias, filename, target in (("team-a", "a.json", "oc_a"), ("team-b", "b.json", "oc_b")):
            (self.binding_path.parent / filename).write_text(json.dumps({"targets": {alias: {"chatId": target}}}))
        result = self.service.check(self.topic, "team-b")
        self.assertEqual("oc_b", result["resolved_target"])
        self.assertEqual("second-binding", result["binding_id"])

    def test_explicit_target_cannot_be_overridden_by_creator_channel(self):
        artifact = self.artifact()
        with self.assertRaises(ValueError):
            self.service.deliver(self.topic, artifact, "oc_creator_context", self.binding)
        self.assertEqual([], self.api.calls)

    def test_inactive_explicit_binding_cannot_send(self):
        payload = json.loads(self.binding_path.read_text())
        payload["bindings"][0]["status"] = "paused"
        self.binding_path.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            self.service.deliver(self.topic, self.artifact(), self.target, self.binding)
        self.assertEqual([], self.api.accepted)

    def test_half_environment_credentials_are_not_combined_with_other_accounts(self):
        os.environ.pop("SKRYA_FEISHU_APP_SECRET")
        with self.assertRaises(ValueError):
            self.service.check(self.topic, self.target, self.binding)
        self.assertEqual([], self.api.calls)

    def test_missing_explicit_credentials_do_not_fall_back_to_another_host_app(self):
        os.environ.clear()
        self.write_binding(credential_ref="deleted.json")
        with self.assertRaises(FileNotFoundError):
            self.service.check(self.topic, self.target, self.binding)
        self.assertEqual([], self.api.calls)

    def test_identical_success_is_not_sent_again(self):
        artifact = self.artifact()
        first = self.service.deliver(self.topic, artifact, self.target, self.binding)
        calls = list(self.api.calls)
        second = self.service.deliver(self.topic, artifact, self.target, self.binding)
        self.assertEqual("sent", second["state"])
        self.assertEqual(first["delivery_id"], second["delivery_id"])
        self.assertEqual(calls, self.api.calls)

    def test_summary_body_replies_have_the_destination_and_root(self):
        self.write_binding("summary+thread")
        receipt = self.service.deliver(self.topic, self.artifact(), self.target, self.binding)
        self.assertEqual("sent", receipt["state"])
        self.assertEqual("send", self.api.accepted[0]["route"])
        self.assertTrue(all(message["route"] == "reply" for message in self.api.accepted[1:]))
        self.assertIn("https://example.org/news/2", self.api.accepted[-1]["content"])

    def test_known_no_thread_capability_does_not_attempt_a_reply(self):
        self.write_binding("summary+thread", supports_thread=False)
        receipt = self.service.deliver(self.topic, self.artifact(), self.target, self.binding)
        self.assertEqual("summary+cards", receipt["layout_effective"])
        self.assertNotIn("reply", self.api.calls)

    def test_thread_rejection_preserves_complete_body_as_standalone_cards(self):
        self.write_binding("summary+thread")
        self.api.mode = "no-thread"
        receipt = self.service.deliver(self.topic, self.artifact(), self.target, self.binding)
        self.assertEqual("summary+cards", receipt["layout_effective"])
        self.assertIn("https://example.org/news/2", "".join(message["content"] for message in self.api.accepted))
        self.assertTrue(all(message["route"] == "send" for message in self.api.accepted))

    def test_text_degradation_preserves_every_news_item(self):
        self.api.mode = "format"
        receipt = self.service.deliver(self.topic, self.artifact(size=250), self.target, self.binding)
        text = "\n".join(json.loads(message["content"])["text"] for message in self.api.accepted)
        self.assertEqual("sent", receipt["state"])
        for number in (1, 2):
            self.assertIn(f"N-{number:02d}", text)
            self.assertIn(f"第{number}项完整事实。" * 250, text)
            self.assertIn(f"https://example.org/news/{number}", text)

    def test_text_summary_root_still_has_a_working_thread_root(self):
        self.write_binding("summary+thread")
        self.api.mode = "format"
        receipt = self.service.deliver(self.topic, self.artifact(), self.target, self.binding)
        self.assertEqual("sent", receipt["state"])
        self.assertEqual("text", self.api.accepted[0]["type"])
        self.assertEqual("reply", self.api.accepted[-1]["route"])

    def test_permission_error_does_not_trigger_format_fallback(self):
        self.api.mode = "permission"
        with self.assertRaises(FeishuPermissionError):
            self.service.deliver(self.topic, self.artifact(), self.target, self.binding)
        self.assertEqual(1, self.api.attempts)
        self.assertEqual([], self.api.accepted)

    def test_partial_delivery_freezes_references_and_skips_the_root_on_resume(self):
        self.write_binding("summary+thread")
        artifact = self.artifact(count=3, size=300)
        self.api.fail_at = 2
        with self.assertRaises(FeishuAPIError):
            self.service.deliver(self.topic, artifact, self.target, self.binding)
        root_message = self.api.accepted[0]["message_id"]
        frozen = self.service.load_snapshot(self.topic, self.binding, root_message)
        self.assertEqual("news-1", frozen["items"]["N-01"]["key"])
        altered = json.loads(artifact.with_suffix(".events.json").read_text())
        altered["items"]["N-01"]["key"] = "wrong-new-entity"
        artifact.with_suffix(".events.json").write_text(json.dumps(altered))
        self.api.fail_at = None
        receipt = self.service.deliver(self.topic, artifact, self.target, self.binding)
        self.assertEqual("sent", receipt["state"])
        self.assertEqual(1, sum(message["route"] == "send" for message in self.api.accepted))
        self.assertEqual("news-1", self.service.load_snapshot(self.topic, self.binding)["items"]["N-01"]["key"])

    def test_corrupt_sent_timestamp_blocks_resume_before_any_new_request(self):
        self.write_binding("summary+thread")
        artifact = self.artifact()
        self.api.fail_at = 2
        with self.assertRaises(FeishuAPIError):
            self.service.deliver(self.topic, artifact, self.target, self.binding)
        path = next((self.root / "runs" / self.topic / "delivery").rglob("receipt.json"))
        payload = json.loads(path.read_text())
        for invalid in (None, "invalid", "2026-10-19T08:00:00"):
            if invalid is None:
                payload["parts"][0].pop("sent_at", None)
            else:
                payload["parts"][0]["sent_at"] = invalid
            path.write_text(json.dumps(payload))
            calls = list(self.api.calls)
            with self.assertRaises(DeliveryError):
                self.service.deliver(self.topic, artifact, self.target, self.binding)
            self.assertEqual(calls, self.api.calls)

    def test_unknown_refuses_a_second_attempt(self):
        self.api.mode = "unknown"
        artifact = self.artifact()
        with self.assertRaises(DeliveryUnknownError):
            self.service.deliver(self.topic, artifact, self.target, self.binding)
        attempts = self.api.attempts
        with self.assertRaises(DeliveryUnknownError):
            self.service.deliver(self.topic, artifact, self.target, self.binding)
        self.assertEqual(attempts, self.api.attempts)
        with self.assertRaises(DeliveryError):
            self.service.load_snapshot(self.topic, self.binding)

    def test_old_message_references_survive_new_delivery_and_repeat(self):
        old = self.artifact("first.md", key_prefix="old")
        self.service.deliver(self.topic, old, self.target, self.binding)
        old_message = self.api.accepted[0]["message_id"]
        new = self.artifact("second.md", key_prefix="new")
        self.service.deliver(self.topic, new, self.target, self.binding)
        self.service.deliver(self.topic, old, self.target, self.binding)
        self.assertEqual("old-1", self.service.load_snapshot(self.topic, self.binding, old_message)["items"]["N-01"]["key"])
        self.assertEqual("new-1", self.service.load_snapshot(self.topic, self.binding)["items"]["N-01"]["key"])

    def test_wrong_artifact_topic_and_changed_bytes_fail_before_network(self):
        artifact = self.artifact()
        snapshot = json.loads(artifact.with_suffix(".events.json").read_text())
        snapshot["topic_id"] = "other"
        artifact.with_suffix(".events.json").write_text(json.dumps(snapshot))
        with self.assertRaises(ValueError):
            self.service.deliver(self.topic, artifact, self.target, self.binding)
        artifact = self.artifact()
        artifact.write_text(artifact.read_text() + "\nchanged facts\n")
        with self.assertRaises(ValueError):
            self.service.deliver(self.topic, artifact, self.target, self.binding)
        self.assertEqual([], self.api.calls)


if __name__ == "__main__":
    unittest.main()
