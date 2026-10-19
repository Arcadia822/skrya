import copy
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest

from skrya_orchestrator.delivery_receipts import (
    DeliveryError, DeliveryLockError, ReceiptStore, canonical_sha256,
)


def hold_binding(root, ready, release):
    with ReceiptStore(root, "news", "group").locked():
        ready.send(True)
        release.recv()


class ReceiptStoreTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.store = ReceiptStore(self.root, "news", "group")
        self.snapshot = {"schema": "skrya.digest-index.v1", "topic_id": "news",
                         "artifact_path": str(self.root / "digest.md"),
                         "items": {"N-01": {"key": "original"}}, "threads": {}}

    def receipt(self, delivery_id="deliv_01", state="sent", sent_at="2026-10-19T08:00:00+00:00"):
        return {"schema": "skrya.delivery-receipt.v1", "topic_id": "news", "binding_id": "group",
                "delivery_id": delivery_id, "artifact_sha256": "a" * 64,
                "snapshot_sha256": canonical_sha256(self.snapshot), "app_id": "cli_test", "target": "oc_target",
                "layout_requested": "full-card", "layout_effective": "full-card", "render_effective": "card",
                "state": state, "degradations": [], "created_at": sent_at, "completed_at": sent_at,
                "parts": [{"part_id": "part_1", "route": "send", "msg_type": "text",
                           "content": '{"text":"complete news"}', "text_fallback": "complete news",
                           "uuid": "01234567-1234-1234-1234-012345678901", "state": state,
                           "message_id": "om_" + delivery_id, "sent_at": sent_at}]}

    def save(self, receipt):
        self.store.save_index(receipt["delivery_id"], self.snapshot)
        self.store.save(receipt)
        return self.store.run_dir(receipt["delivery_id"]) / "receipt.json"

    def test_binding_and_topic_names_do_not_alias(self):
        first = ReceiptStore(self.root, "a.b", "a.b")
        second = ReceiptStore(self.root, "a_b", "a_b")
        same_topic = ReceiptStore(self.root, "a.b", "a_b")
        self.assertEqual(3, len({first.binding_dir, second.binding_dir, same_topic.binding_dir}))
        receipt = self.receipt()
        self.save(receipt)
        self.store.publish(receipt)
        other = ReceiptStore(self.root, "news", "other")
        with self.assertRaises(DeliveryError):
            other.lookup(receipt["parts"][0]["message_id"])
        with self.assertRaises(DeliveryError):
            other.lookup()

    def test_corrupt_receipts_never_become_absent_new_deliveries(self):
        receipt = self.receipt()
        path = self.save(receipt)
        self.assertIsNone(self.store.load("deliv_02"))
        for value in ("", "{", "[]"):
            with self.subTest(value=value):
                path.write_text(value)
                with self.assertRaises(DeliveryError):
                    self.store.load("deliv_01")
        cases = [("schema", "wrong"), ("topic_id", "other"), ("binding_id", "other"),
                 ("delivery_id", "deliv_02"), ("state", "invented")]
        for key, value in cases:
            with self.subTest(key=key):
                corrupt = copy.deepcopy(receipt)
                corrupt[key] = value
                path.write_text(json.dumps(corrupt))
                with self.assertRaises(DeliveryError):
                    self.store.load("deliv_01")
        for key in ("route", "content", "uuid"):
            corrupt = copy.deepcopy(receipt)
            del corrupt["parts"][0][key]
            with self.assertRaises(DeliveryError):
                self.store.save(corrupt)
            path.write_text(json.dumps(corrupt))
            with self.assertRaises(DeliveryError):
                self.store.load("deliv_01")

    def test_index_is_immutable_and_tampering_blocks_reference_resolution(self):
        receipt = self.receipt()
        self.save(receipt)
        self.store.publish(receipt)
        changed = copy.deepcopy(self.snapshot)
        changed["items"]["N-01"]["key"] = "wrong"
        with self.assertRaises(DeliveryError):
            self.store.save_index("deliv_01", changed)
        (self.store.run_dir("deliv_01") / "index.json").write_text(json.dumps(changed))
        for message in (None, receipt["parts"][0]["message_id"]):
            with self.assertRaises(DeliveryError):
                self.store.lookup(message)
        with self.assertRaises(DeliveryError):
            self.store.publish(receipt)

    def test_partial_delivery_resolves_only_confirmed_sent_parts(self):
        receipt = self.receipt(state="partial")
        receipt["parts"][0]["state"] = "sent"
        for number, state in enumerate(("prepared", "failed", "unknown"), 2):
            part = copy.deepcopy(receipt["parts"][0])
            part.update(part_id=f"part_{number}", state=state, message_id=f"om_fake_{number}")
            receipt["parts"].append(part)
        self.save(receipt)
        self.assertEqual("original", self.store.lookup("om_deliv_01")["items"]["N-01"]["key"])
        for message in (None, "om_fake_2", "om_fake_3", "om_fake_4"):
            with self.assertRaises(DeliveryError):
                self.store.lookup(message)
        with self.assertRaises(DeliveryError):
            self.store.publish(receipt)

    def test_uncertain_part_becomes_unknown_but_definite_fallback_can_resume(self):
        receipt = self.receipt(state="sending")
        receipt["parts"][0]["message_id"] = None
        self.save(receipt)
        loaded = self.store.load("deliv_01")
        self.assertEqual("unknown", loaded["state"])
        self.assertEqual("unknown", loaded["parts"][0]["state"])
        receipt["parts"][0]["state"] = "prepared"
        self.store.save(receipt)
        loaded = self.store.load("deliv_01")
        self.assertNotEqual("unknown", loaded["state"])
        self.assertEqual("prepared", loaded["parts"][0]["state"])

    def test_completed_parts_survive_interrupted_finalization(self):
        receipt = self.receipt(state="sending")
        receipt["parts"][0]["state"] = "sent"
        self.save(receipt)
        loaded = self.store.load("deliv_01")
        self.assertNotEqual("unknown", loaded["state"])
        loaded["state"] = "sent"
        self.store.save(loaded)
        self.store.publish(loaded)
        self.assertEqual(self.snapshot, self.store.lookup())
        (self.store.binding_dir / "latest-card-index.json").unlink()
        self.store.publish(self.store.load("deliv_01"))
        self.assertEqual(self.snapshot, self.store.lookup())

    def test_resaved_old_completion_cannot_regress_latest_pointer(self):
        old = self.receipt()
        self.save(old)
        self.store.publish(old)
        new = self.receipt("deliv_02", sent_at="2026-10-19T09:00:00+00:00")
        newer_index = copy.deepcopy(self.snapshot)
        newer_index["items"]["N-01"]["key"] = "new"
        new["snapshot_sha256"] = canonical_sha256(newer_index)
        self.store.save_index("deliv_02", newer_index)
        self.store.save(new)
        self.store.publish(new)
        old["completed_at"] = "2026-10-19T10:00:00+00:00"
        self.store.save(old)
        self.store.publish(old)
        self.assertEqual("new", self.store.lookup()["items"]["N-01"]["key"])
        self.assertEqual("original", self.store.lookup("om_deliv_01")["items"]["N-01"]["key"])

    def test_latest_completion_orders_instants_not_timezone_strings(self):
        old = self.receipt(sent_at="2026-10-19T09:00:00+02:00")
        self.save(old)
        self.store.publish(old)
        newer = self.receipt("deliv_02", sent_at="2026-10-19T08:00:00Z")
        self.save(newer)
        self.store.publish(newer)
        pointer = json.loads((self.store.binding_dir / "latest-card-index.json").read_text())
        self.assertEqual("deliv_02", pointer["delivery_id"])

    def test_corrupt_or_foreign_pointer_cannot_be_overwritten(self):
        receipt = self.receipt()
        self.save(receipt)
        self.store.publish(receipt)
        pointer = self.store.binding_dir / "latest-card-index.json"
        original = json.loads(pointer.read_text())
        bad_pointers = ["{", json.dumps({**original, "binding_id": "other"}), json.dumps({**original, "topic_id": "other"})]
        for bad in bad_pointers:
            pointer.write_text(bad)
            with self.assertRaises(DeliveryError):
                self.store.publish(receipt)
            with self.assertRaises(DeliveryError):
                self.store.lookup()
            self.assertEqual(bad, pointer.read_text())

    def test_symlinks_and_path_traversal_cannot_cross_receipt_scope(self):
        for topic in ("../other", "a/b", ".", "..", "a\\b"):
            with self.assertRaises(DeliveryError):
                ReceiptStore(self.root, topic, "group")
        receipt = self.receipt()
        self.save(receipt)
        alias = ReceiptStore(self.root, "news", "alias")
        alias.binding_dir.symlink_to(self.store.binding_dir, target_is_directory=True)
        for operation in (lambda: alias.run_dir("deliv_01"), lambda: alias.load("deliv_01"), lambda: alias.lookup()):
            with self.assertRaises(DeliveryError):
                operation()
        with self.assertRaises(DeliveryError):
            with alias.locked():
                self.fail("Aliased binding acquired a lock")
        outside = self.root / "outside"
        outside.mkdir()
        (self.store.run_dir("deliv_01") / "receipt.json").unlink()
        (self.store.run_dir("deliv_01") / "receipt.json").symlink_to(outside / "receipt.json")
        with self.assertRaises(DeliveryError):
            self.store.load("deliv_01")

    def test_process_lock_excludes_same_binding_but_not_other_bindings(self):
        context = multiprocessing.get_context("spawn")
        ready_read, ready_write = context.Pipe(duplex=False)
        release_read, release_write = context.Pipe(duplex=False)
        process = context.Process(target=hold_binding, args=(str(self.root), ready_write, release_read))
        process.start()
        try:
            self.assertTrue(ready_read.poll(10), "Lock holder did not start")
            self.assertTrue(ready_read.recv())
            with self.assertRaises(DeliveryLockError):
                with self.store.locked():
                    self.fail("Two processes acquired the same binding")
            with ReceiptStore(self.root, "news", "other").locked():
                self.assertTrue(process.is_alive())
        finally:
            release_write.send(True)
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join()
            for connection in (ready_read, ready_write, release_read, release_write):
                connection.close()
        self.assertEqual(0, process.exitcode)
