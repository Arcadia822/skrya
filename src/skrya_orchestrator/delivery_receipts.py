from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Generator

DELIVERY_RECEIPT_SCHEMA = "skrya.delivery-receipt.v1"
LATEST_CARD_INDEX_SCHEMA = "skrya.latest-card-index.v1"
SNAPSHOT_SCHEMA = "skrya.digest-index.v1"

STATE_PREPARED = "prepared"
STATE_SENDING = "sending"
STATE_PARTIAL = "partial"
STATE_SENT = "sent"
STATE_UNKNOWN = "unknown"
STATE_FAILED = "failed"

VALID_RECEIPT_STATES = {
    STATE_PREPARED,
    STATE_SENDING,
    STATE_PARTIAL,
    STATE_SENT,
    STATE_UNKNOWN,
    STATE_FAILED,
}

VALID_PART_STATES = {
    STATE_PREPARED,
    STATE_SENDING,
    STATE_SENT,
    STATE_UNKNOWN,
    STATE_FAILED,
}

LAYOUT_FULL_CARD = "full-card"
LAYOUT_SUMMARY_THREAD = "summary+thread"
LAYOUT_SUMMARY_CARDS = "summary+cards"

RENDER_CARD = "card"
RENDER_SPLIT_CARD = "split-card"
RENDER_TEXT = "text"


class DeliveryError(RuntimeError):
    """Base error for delivery and receipt operations."""


class DeliveryLockError(DeliveryError):
    """Raised when per-binding process flock cannot be acquired."""


class DeliveryUnknownError(DeliveryError):
    """Raised when delivery outcome is uncertain and requires reconciliation."""


def canonical_json_bytes(data: Any) -> bytes:
    """Serialize data to canonical JSON bytes: UTF-8, ensure_ascii=False, sorted keys, compact separators."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(data: Any) -> str:
    """Compute SHA256 hex digest of canonical JSON representation."""
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()


def hash_binding_id(binding_id: str) -> str:
    """Compute deterministic collision-free hash for binding path isolation."""
    if not isinstance(binding_id, str) or not binding_id.strip():
        raise DeliveryError(f"Invalid binding_id: {binding_id!r}")
    return hashlib.sha256(binding_id.encode("utf-8")).hexdigest()


def _receipt_completion_time(receipt: dict[str, Any]) -> datetime:
    return max(
        datetime.fromisoformat(part["sent_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
        for part in receipt["parts"]
    )


class ReceiptStore:
    """Filesystem-backed store for delivery receipts, frozen indexes, and pointers."""

    def __init__(self, data_root: Path | str, topic_id: str, binding_id: str) -> None:
        if not isinstance(data_root, (Path, str)):
            raise DeliveryError(f"Invalid data_root: {data_root!r}")
        self.data_root = Path(data_root).resolve()

        if not isinstance(topic_id, str) or not topic_id.strip():
            raise DeliveryError(f"Invalid topic_id: {topic_id!r}")
        if "/" in topic_id or "\\" in topic_id or topic_id in {".", ".."} or "\0" in topic_id:
            raise DeliveryError(f"Topic ID must be a single directory component, got: {topic_id!r}")
        self.topic_id = topic_id

        if not isinstance(binding_id, str) or not binding_id.strip():
            raise DeliveryError(f"Invalid binding_id: {binding_id!r}")
        self.binding_id = binding_id

        self.binding_hash = hash_binding_id(binding_id)
        self.binding_dir = self.data_root / "runs" / self.topic_id / "delivery" / self.binding_hash

    def _guard_path(self, path: Path) -> Path:
        """Ensure path and all its ancestor components do not escape data_root and contain no symlinks."""
        resolved_root = self.data_root.resolve()
        try:
            resolved_path = path.resolve()
            resolved_path.relative_to(resolved_root)
        except (ValueError, OSError, RuntimeError) as exc:
            raise DeliveryError(f"Path escapes data root: {path}") from exc

        try:
            rel_parts = path.relative_to(self.data_root).parts
        except ValueError as exc:
            raise DeliveryError(f"Path escapes data root: {path}") from exc

        if any(part in {".", ".."} for part in rel_parts):
            raise DeliveryError(f"Relative path traversal not permitted: {path}")

        curr = self.data_root
        for part in rel_parts:
            curr = curr / part
            if curr.is_symlink():
                raise DeliveryError(f"Symlink path component not permitted: {curr}")

        return path

    def _validate_delivery_id(self, delivery_id: str) -> None:
        if not isinstance(delivery_id, str) or not delivery_id:
            raise DeliveryError(f"Invalid delivery_id: {delivery_id!r}")
        if "/" in delivery_id or "\\" in delivery_id or delivery_id in {".", ".."} or "\0" in delivery_id:
            raise DeliveryError(f"Delivery ID must be a single filename component, got: {delivery_id!r}")
        if not re.match(r"^deliv_[0-9a-fA-F]+$", delivery_id):
            raise DeliveryError(f"Delivery ID must match deliv_<hex>, got: {delivery_id!r}")

    def run_dir(self, delivery_id: str) -> Path:
        """Return scoped directory for a specific delivery run."""
        self._validate_delivery_id(delivery_id)
        target = self.binding_dir / delivery_id
        self._guard_path(target)
        return target

    @contextmanager
    def locked(self) -> Generator[ReceiptStore, None, None]:
        """Contextmanager acquiring non-blocking flock per binding."""
        self._guard_path(self.binding_dir)
        self.binding_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.binding_dir / ".lock"
        self._guard_path(lock_path)

        try:
            f = open(lock_path, "a+", encoding="utf-8")
        except OSError as e:
            raise DeliveryLockError(f"Cannot open lock file {lock_path}: {e}") from e

        try:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError) as e:
                raise DeliveryLockError(f"Binding lock held for {self.binding_id}: {lock_path}") from e
            yield self
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            finally:
                try:
                    f.close()
                except OSError:
                    pass

    def _atomic_write_json(self, file_path: Path, data: dict[str, Any]) -> None:
        """Write JSON payload atomically using temporary file and fsync."""
        self._guard_path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        self._guard_path(file_path.parent)

        tmp_path = file_path.with_name(f".{file_path.name}.tmp.{os.getpid()}.{time.time_ns()}")
        self._guard_path(tmp_path)
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            with open(tmp_path, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, file_path)
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    def _validate_receipt(
        self,
        receipt: dict[str, Any],
        delivery_id: str | None = None,
    ) -> None:
        """Strict validation of receipt schema, identity, fields, and part structures."""
        if not isinstance(receipt, dict):
            raise DeliveryError(f"Receipt must be a dict, got {type(receipt).__name__}")

        if receipt.get("schema") != DELIVERY_RECEIPT_SCHEMA:
            raise DeliveryError(
                f"Schema mismatch: expected {DELIVERY_RECEIPT_SCHEMA}, got {receipt.get('schema')!r}"
            )

        if receipt.get("topic_id") != self.topic_id:
            raise DeliveryError(
                f"Topic ID mismatch: expected {self.topic_id!r}, got {receipt.get('topic_id')!r}"
            )
        if receipt.get("binding_id") != self.binding_id:
            raise DeliveryError(
                f"Binding ID mismatch: expected {self.binding_id!r}, got {receipt.get('binding_id')!r}"
            )

        rec_deliv_id = receipt.get("delivery_id")
        if not isinstance(rec_deliv_id, str):
            raise DeliveryError(f"Invalid delivery_id in receipt: {rec_deliv_id!r}")
        self._validate_delivery_id(rec_deliv_id)

        if delivery_id is not None and rec_deliv_id != delivery_id:
            raise DeliveryError(
                f"Delivery ID mismatch: expected {delivery_id!r}, got {rec_deliv_id!r}"
            )

        receipt_state = receipt.get("state")
        if receipt_state not in VALID_RECEIPT_STATES:
            raise DeliveryError(f"Invalid receipt state: {receipt_state!r}")

        for req_field in (
            "artifact_sha256",
            "snapshot_sha256",
            "target",
            "app_id",
            "layout_requested",
            "layout_effective",
            "render_effective",
        ):
            val = receipt.get(req_field)
            if not isinstance(val, str) or not val.strip():
                raise DeliveryError(f"Missing or invalid required receipt field: {req_field!r}")

        degradations = receipt.get("degradations")
        if degradations is not None and not isinstance(degradations, list):
            raise DeliveryError(f"degradations must be a list, got {type(degradations).__name__}")

        parts = receipt.get("parts")
        if not isinstance(parts, list):
            raise DeliveryError(f"parts must be a list, got {type(parts).__name__}")

        if receipt_state == STATE_SENT and not parts:
            raise DeliveryError("Sent receipt must have at least one part")

        for idx, part in enumerate(parts):
            if not isinstance(part, dict):
                raise DeliveryError(f"Part {idx} must be a dict")
            for pkey in ("part_id", "route", "msg_type", "content", "text_fallback", "uuid", "state"):
                if pkey not in part:
                    raise DeliveryError(f"Part {idx} missing field {pkey!r}")
            if part.get("route") not in ("send", "reply"):
                raise DeliveryError(f"Part {idx} invalid route: {part.get('route')!r}")
            if part.get("msg_type") not in ("interactive", "text"):
                raise DeliveryError(f"Part {idx} invalid msg_type: {part.get('msg_type')!r}")
            if not isinstance(part.get("content"), str):
                raise DeliveryError(
                    f"Part {idx} content must be a JSON string, got {type(part.get('content')).__name__}"
                )
            if not isinstance(part.get("text_fallback"), str):
                raise DeliveryError(f"Part {idx} text_fallback must be str")
            uuid_val = part.get("uuid")
            if not isinstance(uuid_val, str) or not uuid_val.strip():
                raise DeliveryError(f"Part {idx} uuid must be a non-empty str")
            pstate = part.get("state")
            if pstate not in VALID_PART_STATES:
                raise DeliveryError(f"Part {idx} invalid state: {pstate!r}")
            if pstate == STATE_SENT:
                msg_id = part.get("message_id")
                if not msg_id or not isinstance(msg_id, str) or not msg_id.strip():
                    raise DeliveryError(f"Part {idx} in state 'sent' missing valid message_id")
                try:
                    sent_at = datetime.fromisoformat(part["sent_at"].replace("Z", "+00:00"))
                    if sent_at.tzinfo is None:
                        raise ValueError("Missing timezone")
                except (KeyError, AttributeError, TypeError, ValueError):
                    raise DeliveryError(f"Part {idx} in state 'sent' missing a valid timestamp") from None
            if receipt_state == STATE_SENT and pstate != STATE_SENT:
                raise DeliveryError(f"Receipt state is 'sent' but part {idx} state is {pstate!r}")

    def load(self, delivery_id: str) -> dict[str, Any] | None:
        """Load receipt for delivery_id. Corrupt or mismatched receipts fail closed by raising."""
        self._validate_delivery_id(delivery_id)
        run_path = self.run_dir(delivery_id)
        receipt_path = run_path / "receipt.json"
        self._guard_path(receipt_path)

        if not receipt_path.exists():
            return None

        try:
            raw_bytes = receipt_path.read_bytes()
        except OSError as e:
            raise DeliveryError(f"Failed to read receipt at {receipt_path}: {e}") from e

        if not raw_bytes.strip():
            raise DeliveryError(f"Corrupt receipt (empty file) at {receipt_path}")

        try:
            data = json.loads(raw_bytes.decode("utf-8"))
        except Exception as e:
            raise DeliveryError(f"Corrupt receipt JSON at {receipt_path}: {e}") from e

        self._validate_receipt(data, delivery_id=delivery_id)

        parts = data.get("parts", [])
        has_sending_part = False
        for part in parts:
            if part.get("state") == STATE_SENDING:
                has_sending_part = True
                part["state"] = STATE_UNKNOWN

        if has_sending_part or data.get("state") == STATE_UNKNOWN or any(p.get("state") == STATE_UNKNOWN for p in parts):
            data["state"] = STATE_UNKNOWN

        return data

    def save(self, receipt: dict[str, Any]) -> None:
        """Save delivery receipt atomically after strict validation."""
        self._validate_receipt(receipt)
        delivery_id = receipt["delivery_id"]

        now_iso = datetime.now(timezone.utc).isoformat()
        if not receipt.get("created_at"):
            receipt["created_at"] = now_iso
        receipt["updated_at"] = now_iso

        run_path = self.run_dir(delivery_id)
        run_path.mkdir(parents=True, exist_ok=True)
        receipt_path = run_path / "receipt.json"
        self._atomic_write_json(receipt_path, receipt)

    def save_index(self, delivery_id: str, snapshot: dict[str, Any]) -> None:
        """Save frozen digest index snapshot immutably."""
        self._validate_delivery_id(delivery_id)
        if not isinstance(snapshot, dict):
            raise DeliveryError(f"Snapshot must be a dict, got {type(snapshot).__name__}")

        if snapshot.get("schema") != SNAPSHOT_SCHEMA:
            raise DeliveryError(
                f"Snapshot schema mismatch: expected {SNAPSHOT_SCHEMA}, got {snapshot.get('schema')!r}"
            )
        if snapshot.get("topic_id") != self.topic_id:
            raise DeliveryError(
                f"Snapshot topic_id mismatch: expected {self.topic_id!r}, got {snapshot.get('topic_id')!r}"
            )

        run_path = self.run_dir(delivery_id)
        index_path = run_path / "index.json"
        self._guard_path(index_path)

        if index_path.exists():
            try:
                raw = index_path.read_text(encoding="utf-8")
                existing = json.loads(raw)
            except Exception as e:
                raise DeliveryError(f"Corrupt existing index at {index_path}: {e}") from e

            if not isinstance(existing, dict):
                raise DeliveryError(f"Corrupt existing index at {index_path}: not a dict")

            if existing != snapshot or canonical_sha256(existing) != canonical_sha256(snapshot):
                raise DeliveryError(
                    f"Immutable index violation for {delivery_id}: existing index differs from proposed"
                )
            return

        run_path.mkdir(parents=True, exist_ok=True)
        self._atomic_write_json(index_path, snapshot)

    def index(self, delivery_id: str) -> dict[str, Any]:
        """Load frozen index snapshot for delivery_id within current binding scope."""
        self._validate_delivery_id(delivery_id)
        run_path = self.run_dir(delivery_id)
        index_path = run_path / "index.json"
        self._guard_path(index_path)

        if not index_path.exists():
            raise DeliveryError(
                f"Index not found for delivery_id {delivery_id!r} under topic {self.topic_id!r}"
            )

        try:
            raw = index_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as e:
            raise DeliveryError(f"Corrupt index at {index_path}: {e}") from e

        if not isinstance(data, dict):
            raise DeliveryError(f"Index must be a dict, got {type(data).__name__}")

        if data.get("schema") != SNAPSHOT_SCHEMA:
            raise DeliveryError(
                f"Index schema mismatch: expected {SNAPSHOT_SCHEMA}, got {data.get('schema')!r}"
            )
        if data.get("topic_id") != self.topic_id:
            raise DeliveryError(
                f"Index topic_id mismatch: expected {self.topic_id!r}, got {data.get('topic_id')!r}"
            )

        return data

    def publish(self, receipt: dict[str, Any]) -> None:
        """Publish sent receipt as latest pointer, ensuring crash repair and pointer non-regression."""
        self._validate_receipt(receipt)
        delivery_id = receipt["delivery_id"]

        if receipt.get("state") != STATE_SENT:
            raise DeliveryError(
                f"Cannot publish receipt in state {receipt.get('state')!r}; must be {STATE_SENT!r}"
            )

        parts = receipt.get("parts", [])
        if not parts:
            raise DeliveryError("Cannot publish receipt with empty or missing parts")

        for idx, p in enumerate(parts):
            if not isinstance(p, dict) or p.get("state") != STATE_SENT or not p.get("message_id"):
                raise DeliveryError(f"Part {idx} is not completed with state 'sent' and valid message_id")

        index_data = self.index(delivery_id)
        actual_hash = canonical_sha256(index_data)
        expected_hash = receipt.get("snapshot_sha256")
        if actual_hash != expected_hash:
            raise DeliveryError(
                f"Index canonical SHA256 mismatch for delivery {delivery_id}: "
                f"expected {expected_hash!r}, got {actual_hash!r}"
            )

        pointer_path = self.binding_dir / "latest-card-index.json"
        self._guard_path(pointer_path)

        if pointer_path.exists():
            try:
                raw_ptr = pointer_path.read_text(encoding="utf-8")
                curr_ptr = json.loads(raw_ptr)
            except Exception as e:
                raise DeliveryError(f"Corrupt latest card index at {pointer_path}: {e}") from e

            if not isinstance(curr_ptr, dict):
                raise DeliveryError(f"Latest card index must be a dict at {pointer_path}")
            if curr_ptr.get("schema") != LATEST_CARD_INDEX_SCHEMA:
                raise DeliveryError(f"Schema mismatch in latest pointer: {curr_ptr.get('schema')!r}")
            if curr_ptr.get("topic_id") != self.topic_id:
                raise DeliveryError(f"Topic ID mismatch in latest pointer: {curr_ptr.get('topic_id')!r}")
            if curr_ptr.get("binding_id") != self.binding_id:
                raise DeliveryError(f"Binding ID mismatch in latest pointer: {curr_ptr.get('binding_id')!r}")

            curr_deliv_id = curr_ptr.get("delivery_id")
            if not isinstance(curr_deliv_id, str):
                raise DeliveryError(f"Invalid delivery_id in latest pointer: {curr_deliv_id!r}")
            self._validate_delivery_id(curr_deliv_id)

            if curr_deliv_id == delivery_id:
                pass
            else:
                existing_receipt = self.load(curr_deliv_id)
                if not existing_receipt:
                    raise DeliveryError(
                        f"Latest pointer references missing delivery receipt: {curr_deliv_id!r}"
                    )
                if existing_receipt.get("state") != STATE_SENT:
                    raise DeliveryError(
                        f"Latest pointer references non-sent delivery receipt: {curr_deliv_id!r}"
                    )

                existing_time = _receipt_completion_time(existing_receipt)
                this_time = _receipt_completion_time(receipt)
                if existing_time > this_time:
                    return

        pointer_data = {
            "schema": LATEST_CARD_INDEX_SCHEMA,
            "topic_id": self.topic_id,
            "binding_id": self.binding_id,
            "delivery_id": delivery_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.binding_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write_json(pointer_path, pointer_data)

    def lookup(self, message_id: str | None = None) -> dict[str, Any]:
        """Look up frozen snapshot by message_id or latest completed delivery."""
        if message_id is None:
            pointer_path = self.binding_dir / "latest-card-index.json"
            self._guard_path(pointer_path)
            if not pointer_path.exists():
                raise DeliveryError(
                    f"No latest card index recorded for topic {self.topic_id!r} binding {self.binding_id!r}"
                )

            try:
                raw_ptr = pointer_path.read_text(encoding="utf-8")
                pointer_data = json.loads(raw_ptr)
            except Exception as e:
                raise DeliveryError(f"Corrupt latest card index at {pointer_path}: {e}") from e

            if not isinstance(pointer_data, dict):
                raise DeliveryError(
                    f"Latest card index must be a dict, got {type(pointer_data).__name__}"
                )
            if pointer_data.get("schema") != LATEST_CARD_INDEX_SCHEMA:
                raise DeliveryError(f"Schema mismatch in latest pointer: {pointer_data.get('schema')!r}")
            if pointer_data.get("topic_id") != self.topic_id:
                raise DeliveryError(f"Topic ID mismatch in latest pointer: {pointer_data.get('topic_id')!r}")
            if pointer_data.get("binding_id") != self.binding_id:
                raise DeliveryError(
                    f"Binding ID mismatch in latest pointer: {pointer_data.get('binding_id')!r}"
                )

            delivery_id = pointer_data.get("delivery_id")
            if not isinstance(delivery_id, str):
                raise DeliveryError(f"Invalid delivery_id in latest pointer: {delivery_id!r}")
            self._validate_delivery_id(delivery_id)

            receipt = self.load(delivery_id)
            if not receipt:
                raise DeliveryError(f"Receipt missing for latest pointer delivery {delivery_id!r}")
            if receipt.get("state") != STATE_SENT:
                raise DeliveryError(
                    f"Latest delivery {delivery_id!r} is not complete-successful (state: {receipt.get('state')!r})"
                )

            parts = receipt.get("parts", [])
            if not parts:
                raise DeliveryError(f"Latest delivery {delivery_id!r} has no parts")
            for idx, p in enumerate(parts):
                if not isinstance(p, dict) or p.get("state") != STATE_SENT or not p.get("message_id"):
                    raise DeliveryError(f"Part {idx} in latest delivery is not complete-successful")

            index_data = self.index(delivery_id)
            actual_hash = canonical_sha256(index_data)
            expected_hash = receipt.get("snapshot_sha256")
            if actual_hash != expected_hash:
                raise DeliveryError(
                    f"Index canonical SHA256 mismatch for latest delivery {delivery_id}: "
                    f"expected {expected_hash!r}, got {actual_hash!r}"
                )
            return index_data

        msg_id = str(message_id).strip()
        if not msg_id:
            raise DeliveryError("message_id cannot be empty")

        if not self.binding_dir.exists():
            raise DeliveryError(
                f"No deliveries recorded for topic {self.topic_id!r} binding {self.binding_id!r}"
            )

        runs: list[Path] = []
        for item in self.binding_dir.iterdir():
            if item.name.startswith("."):
                continue
            if item.is_symlink():
                continue
            if not item.is_dir():
                continue
            try:
                self._validate_delivery_id(item.name)
                self._guard_path(item)
                runs.append(item)
            except DeliveryError:
                continue

        runs.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

        for run_path in runs:
            deliv_id = run_path.name
            receipt_path = run_path / "receipt.json"
            if not receipt_path.exists():
                continue
            try:
                receipt = self.load(deliv_id)
            except Exception:
                continue
            if not receipt:
                continue

            parts = receipt.get("parts", [])
            if isinstance(parts, list):
                for p in parts:
                    if (
                        isinstance(p, dict)
                        and p.get("state") == STATE_SENT
                        and p.get("message_id")
                        and str(p.get("message_id")).strip() == msg_id
                    ):
                        index_data = self.index(deliv_id)
                        actual_hash = canonical_sha256(index_data)
                        expected_hash = receipt.get("snapshot_sha256")
                        if actual_hash != expected_hash:
                            raise DeliveryError(
                                f"Index canonical SHA256 mismatch for delivery {deliv_id}: "
                                f"expected {expected_hash!r}, got {actual_hash!r}"
                            )
                        return index_data

        raise DeliveryError(
            f"No delivery found for message_id {msg_id!r} under topic {self.topic_id!r} binding {self.binding_id!r}"
        )


__all__ = [
    "ReceiptStore",
    "DeliveryError",
    "DeliveryLockError",
    "DeliveryUnknownError",
    "DELIVERY_RECEIPT_SCHEMA",
    "LATEST_CARD_INDEX_SCHEMA",
    "SNAPSHOT_SCHEMA",
    "STATE_PREPARED",
    "STATE_SENDING",
    "STATE_PARTIAL",
    "STATE_SENT",
    "STATE_UNKNOWN",
    "STATE_FAILED",
    "VALID_RECEIPT_STATES",
    "VALID_PART_STATES",
    "LAYOUT_FULL_CARD",
    "LAYOUT_SUMMARY_THREAD",
    "LAYOUT_SUMMARY_CARDS",
    "RENDER_CARD",
    "RENDER_SPLIT_CARD",
    "RENDER_TEXT",
    "hash_binding_id",
    "canonical_json_bytes",
    "canonical_sha256",
]
