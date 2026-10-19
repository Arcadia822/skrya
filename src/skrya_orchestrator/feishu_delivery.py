from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .delivery import DeliveryBindingService
from .delivery_receipts import DeliveryError, DeliveryUnknownError, ReceiptStore
from .digest_document import parse_digest
from .feishu_api import (
    FeishuCardFormatError,
    FeishuClient,
    FeishuError,
    FeishuThreadNotSupportedError,
    FeishuUnknownError,
)
from .feishu_cards import render_card_bundle, summary_markdown
from .references import build_snapshot, load_snapshot, snapshot_path


FEISHU_CAPABILITIES = {
    "channel": "feishu",
    "render": ["card", "text"],
    "max_payload_bytes": 24000,
    "supports_thread": True,
    "supports_files": False,
    "rate_limit": {"requests_per_second_per_target": 4},
    "supports_display_components": True,
    "supports_action_callbacks": False,
}
_ORIGINS = {"https://open.feishu.cn", "https://open.larksuite.com"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _topic_dir(data_root: Path, topic_id: str) -> Path:
    if not topic_id or Path(topic_id).name != topic_id or topic_id in {".", ".."} or "\\" in topic_id:
        raise ValueError("Topic ID must identify one directory")
    path = data_root / "topics" / topic_id
    if not path.resolve().is_relative_to(data_root):
        raise ValueError("Topic path escapes the data root")
    return path


def _read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object at {path}")
    return value


@dataclass(frozen=True, slots=True)
class FeishuCredentials:
    app_id: str
    app_secret: str = field(repr=False)
    origin: str = "https://open.feishu.cn"


def _configuration(data_root: Path, topic_id: str, binding: dict) -> tuple[FeishuCredentials, dict]:
    app_id = os.environ.get("SKRYA_FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("SKRYA_FEISHU_APP_SECRET", "").strip()
    if bool(app_id) != bool(app_secret):
        raise ValueError("Set both SKRYA_FEISHU_APP_ID and SKRYA_FEISHU_APP_SECRET")
    config: dict = {}
    config_file = os.environ.get("SKRYA_FEISHU_CONFIG")
    ref = binding.get("delivery", {}).get("credential_ref")
    if config_file or ref:
        path = Path(config_file or ref).expanduser()
        if not config_file and not path.is_absolute():
            path = _topic_dir(data_root, topic_id) / path
        config = _read_object(path)
    elif not app_id and binding.get("host") == "openclaw":
        home = Path.home() / ".openclaw"
        host_config = _read_object(home / "openclaw.json")
        secrets = _read_object(home / "credentials" / "lark.secrets.json")
        channel = host_config.get("channels", {}).get("feishu", {})
        domain = channel.get("domain", "feishu")
        if domain not in {"feishu", "lark"}:
            raise ValueError("Unsupported OpenClaw Feishu domain")
        config = {
            "appId": channel.get("appId"),
            "appSecret": secrets.get("lark", {}).get("appSecret"),
            "origin": "https://open.larksuite.com" if domain == "lark" else "https://open.feishu.cn",
        }
    app_id = app_id or config.get("appId") or config.get("app_id")
    app_secret = app_secret or config.get("appSecret") or config.get("app_secret")
    if not isinstance(app_id, str) or not app_id.strip() or not isinstance(app_secret, str) or not app_secret.strip():
        raise ValueError("The selected host/application has no complete Feishu credentials")
    origin = config.get("origin", "https://open.feishu.cn")
    if origin not in _ORIGINS:
        raise ValueError("Feishu credentials require an allowlisted HTTPS origin")
    return FeishuCredentials(app_id.strip(), app_secret.strip(), origin), config


def _target(ref: str, config: dict) -> str:
    value = str(ref).removeprefix("chat:").strip()
    if re.fullmatch(r"(?:oc|ou)_[A-Za-z0-9_-]{1,124}", value):
        return value
    targets = config.get("targets", {})
    if not isinstance(targets, dict):
        raise ValueError("Credential configuration targets must be an object")
    if value in targets:
        entry = targets[value]
        value = entry.get("chatId") or entry.get("openId") if isinstance(entry, dict) else entry
    if not isinstance(value, str) or not re.fullmatch(r"(?:oc|ou)_[A-Za-z0-9_-]{1,124}", value):
        raise ValueError("Target must be an explicit chat/user ID or an alias in the selected configuration")
    return value


def _select_binding(data_root: Path, topic_id: str, target: str, binding_id: str | None) -> tuple[dict, str, FeishuCredentials]:
    payload = _read_object(_topic_dir(data_root, topic_id) / "delivery-bindings.json")
    DeliveryBindingService(data_root, data_root=data_root).validate_payload(payload)
    active = [b for b in payload["bindings"] if b["status"] == "active" and b["topic_id"] == topic_id]
    if binding_id:
        active = [b for b in active if b.get("id") == binding_id]
        if len(active) != 1:
            raise ValueError("The selected binding is absent, inactive or ambiguous")
    matches = []
    for binding in active:
        if not isinstance(binding.get("delivery", {}), dict):
            raise ValueError("Binding delivery options must be an object")
        explicit = binding.get("target")
        if explicit is not None:
            if not isinstance(explicit, dict) or explicit.get("channel") != "feishu":
                continue
            ref = explicit.get("ref")
        else:
            ref = binding.get("conversation", {}).get("id") or binding.get("channel", {}).get("id")
        if not ref:
            continue
        raw_target = str(target).removeprefix("chat:").strip()
        if str(ref).startswith(("oc_", "ou_")) and raw_target.startswith(("oc_", "ou_")) and raw_target != ref:
            continue
        credentials, config = _configuration(data_root, topic_id, binding)
        aliases = config.get("targets", {})
        if not isinstance(aliases, dict):
            raise ValueError("Credential configuration targets must be an object")
        if not raw_target.startswith(("oc_", "ou_")) and raw_target not in aliases:
            continue
        resolved = _target(target, config)
        if resolved == _target(ref, config):
            if not isinstance(binding.get("id"), str) or not binding["id"].strip():
                raise ValueError("Native delivery requires a stable binding ID")
            matches.append((binding, resolved, credentials))
    if len(matches) != 1:
        raise ValueError("No unique active binding matches this explicit target; select --binding")
    return matches[0]


def _snapshot(data_root: Path, topic_id: str, artifact: Path, markdown: str) -> dict:
    if not artifact.is_relative_to((data_root / "runs" / topic_id).resolve()):
        raise ValueError("Digest artifact does not belong to the selected topic")
    if snapshot_path(artifact).exists():
        snapshot = load_snapshot(artifact)
    else:
        doc = parse_digest(markdown)
        if doc.threads:
            raise ValueError("Thread delivery requires its immutable digest snapshot with stable Thread IDs")
        items = [
            {"number": item.number, "key": item.key, "title": item.title,
             "analysis_body": item.facts, "analysis_title": item.why,
             "sources": [{"name": s.name, "url": s.url} for s in item.sources], "date": item.date}
            for item in doc.items
        ]
        snapshot = build_snapshot(topic_id, artifact, items, [])
    if snapshot.get("schema") != "skrya.digest-index.v1" or snapshot.get("topic_id") != topic_id:
        raise ValueError("Digest snapshot schema/topic does not match this delivery")
    if Path(snapshot.get("artifact_path", "")).resolve() != artifact:
        raise ValueError("Digest snapshot belongs to another artifact")
    artifact_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    if snapshot.get("artifact_sha256") != artifact_hash:
        raise ValueError("Digest snapshot does not match the exact Markdown bytes")
    doc = parse_digest(markdown, snapshot=snapshot)
    if set(snapshot.get("items", {})) != {f"N-{item.number:02d}" for item in doc.items}:
        raise ValueError("Snapshot news references do not match the rendered document")
    if set(snapshot.get("threads", {})) != {f"T-{thread.number:02d}" for thread in doc.threads}:
        raise ValueError("Snapshot Thread references do not match the rendered document")
    return snapshot


def _card_text(card: dict) -> str:
    paragraphs = [card["header"]["title"]["content"]]

    def visit(element: dict) -> None:
        if element.get("tag") == "markdown":
            paragraphs.append(element["content"])
        for key in ("elements", "columns"):
            for child in element.get(key, []):
                visit(child)

    for element in card["body"]["elements"]:
        visit(element)
    return re.sub(r"</?(?:font|text_tag)\b[^>]*>", "", "\n\n".join(paragraphs))


def _part_uuid(delivery_id: str, part: dict) -> str:
    request = [part["part_id"], part["route"], part["msg_type"], part["content"]]
    return str(uuid.uuid5(uuid.NAMESPACE_URL, delivery_id + _digest(request)))


def _validate_parts(parts: list[dict], target: str) -> None:
    for part in parts:
        payload = {"msg_type": part["msg_type"], "content": part["content"], "uuid": part["uuid"]}
        if part["route"] == "send":
            payload["receive_id"] = target
        else:
            payload["reply_in_thread"] = True
        if len(_json(payload).encode("utf-8")) > FEISHU_CAPABILITIES["max_payload_bytes"]:
            raise ValueError("Delivery request exceeds the 24,000-byte budget")


def _plan(markdown: str, snapshot: dict, layout: str, delivery_id: str, options: dict, target: str) -> list[dict]:
    cards = render_card_bundle(markdown, snapshot=snapshot)["cards"]
    entries = []
    if layout != "full-card":
        summary = summary_markdown(markdown, limit=5)
        root = {
            "schema": "2.0",
            "header": {"title": {"tag": "plain_text", "content": parse_digest(markdown).title}, "template": "blue"},
            "body": {"elements": [{"tag": "markdown", "content": summary}]},
        }
        entries.append((root, "send"))
    entries.extend((card, "reply" if layout == "summary+thread" else "send") for card in cards)
    parts = []
    for number, (card, route) in enumerate(entries, 1):
        text = _card_text(card)
        msg_type = "text" if options.get("render") == "text" else "interactive"
        content = _json({"text": text}) if msg_type == "text" else _json(card)
        part = {"part_id": f"part_{number}", "route": route, "msg_type": msg_type,
                "content": content, "text_fallback": text, "state": "prepared", "message_id": None}
        part["uuid"] = _part_uuid(delivery_id, part)
        parts.append(part)
    _validate_parts(parts, target)
    return parts


class FeishuDeliveryService:
    def __init__(self, data_root: Path | str, client: Any = None) -> None:
        self.data_root = Path(data_root).resolve()
        self.client = client if client is not None else FeishuClient()

    def check(self, topic_id: str, target: str, binding_id: str | None = None) -> dict:
        binding, resolved, credentials = _select_binding(self.data_root, topic_id, target, binding_id)
        token = self.client.get_tenant_access_token(credentials.app_id, credentials.app_secret, origin=credentials.origin)
        kind = "open_id" if resolved.startswith("ou_") else "chat_id"
        result = self.client.check_read_access(token, resolved, kind, origin=credentials.origin)
        if result.get("read_access") is False and kind == "chat_id":
            raise DeliveryError("The bound chat is not readable by the selected application")
        return {"status": "ok" if result.get("read_access") else "limited", "topic_id": topic_id,
                "binding_id": binding["id"], "resolved_target": resolved, "target_type": kind,
                "read_access": result.get("read_access", False), "permission_guaranteed": False,
                "note": "Preflight is not proof of sending permission or delivery"}

    def deliver(self, topic_id: str, artifact: Path | str, target: str,
                binding_id: str | None = None, layout: str | None = None) -> dict:
        binding, resolved, credentials = _select_binding(self.data_root, topic_id, target, binding_id)
        artifact = Path(artifact).resolve()
        if not artifact.is_relative_to((self.data_root / "runs" / topic_id).resolve()):
            raise ValueError("Digest artifact does not belong to the selected topic")
        artifact_bytes = artifact.read_bytes()
        markdown = artifact_bytes.decode("utf-8")
        options = binding.get("delivery", {})
        requested = layout or options.get("layout", "full-card")
        if requested not in {"full-card", "summary+thread"}:
            raise ValueError("Unsupported delivery layout")
        if options.get("render", "card") not in {"card", "text"}:
            raise ValueError("Unsupported delivery rendering capability")
        if "supports_thread" in options and type(options["supports_thread"]) is not bool:
            raise ValueError("supports_thread must be a boolean")
        artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
        delivery_id = "deliv_" + _digest([topic_id, binding["id"], credentials.app_id, resolved,
                                         str(artifact), artifact_hash, requested, options.get("supports_thread", True), options.get("render", "card")])
        store = ReceiptStore(self.data_root, topic_id, binding["id"])
        with store.locked():
            receipt = store.load(delivery_id)
            if receipt is not None and receipt["state"] == "sent":
                store.publish(receipt)
                return receipt
            if receipt is not None and receipt["state"] == "unknown":
                raise DeliveryUnknownError("Delivery outcome is unknown; reconcile actual messages before resending")
            if receipt is None:
                snapshot = _snapshot(self.data_root, topic_id, artifact, markdown)
                effective = requested
                degradations = []
                if requested == "summary+thread" and options.get("supports_thread") is False:
                    effective = "summary+cards"
                    degradations.append({"type": "layout", "from": requested, "to": effective, "reason": "target capability"})
                parts = _plan(markdown, snapshot, effective, delivery_id, options, resolved)
                receipt = {"schema": "skrya.delivery-receipt.v1", "delivery_id": delivery_id,
                           "topic_id": topic_id, "binding_id": binding["id"], "target": resolved,
                           "app_id": credentials.app_id, "artifact_sha256": artifact_hash,
                           "snapshot_sha256": _digest(snapshot), "layout_requested": requested,
                           "layout_effective": effective,
                           "render_effective": "text" if options.get("render") == "text" else ("split-card" if len(parts) > (2 if effective != "full-card" else 1) else "card"),
                           "state": "prepared", "parts": parts, "degradations": degradations,
                           "created_at": _now(), "updated_at": _now()}
                store.save_index(delivery_id, snapshot)
                store.save(receipt)
            else:
                if _digest(store.index(delivery_id)) != receipt["snapshot_sha256"]:
                    raise DeliveryError("Frozen delivery index has changed")
            if all(part["state"] == "sent" for part in receipt["parts"]):
                return self._complete(store, receipt)
            token = self.client.get_tenant_access_token(credentials.app_id, credentials.app_secret, origin=credentials.origin)
            for part in receipt["parts"]:
                while part["state"] != "sent":
                    if part["state"] in {"sending", "unknown"}:
                        raise DeliveryUnknownError("A delivery part requires reconciliation before resending")
                    _validate_parts([part], resolved)
                    part["state"] = "sending"
                    receipt["state"] = "sending"
                    store.save(receipt)
                    try:
                        if part["route"] == "reply":
                            root_id = receipt["parts"][0]["message_id"]
                            if not root_id:
                                raise DeliveryError("Thread root message is missing")
                            result = self.client.reply_message(token, root_id, part["msg_type"], part["content"],
                                                               part["uuid"], reply_in_thread=True,
                                                               origin=credentials.origin, target=resolved)
                        else:
                            result = self.client.send_message(token, resolved, part["msg_type"], part["content"],
                                                              part["uuid"], origin=credentials.origin)
                        message_id = result.get("message_id")
                        if not isinstance(message_id, str) or not message_id.strip():
                            raise FeishuUnknownError("Send response did not establish a message ID")
                    except FeishuThreadNotSupportedError:
                        if part["route"] != "reply":
                            self._fail(store, receipt, part, "Unexpected thread rejection")
                            raise
                        receipt["layout_effective"] = "summary+cards"
                        receipt["degradations"].append({"type": "layout", "from": "summary+thread", "to": "summary+cards", "reason": "thread unsupported"})
                        for pending in receipt["parts"]:
                            if pending["state"] != "sent" and pending["route"] == "reply":
                                pending["route"] = "send"
                                pending["state"] = "prepared"
                                pending["uuid"] = _part_uuid(delivery_id, pending)
                        store.save(receipt)
                        continue
                    except FeishuCardFormatError:
                        if part["msg_type"] != "interactive":
                            self._fail(store, receipt, part, "Text message rejected")
                            raise
                        receipt["render_effective"] = "text"
                        receipt["degradations"].append({"type": "render", "from": "card", "to": "text", "reason": "definitive card rejection"})
                        for pending in receipt["parts"]:
                            if pending["state"] != "sent" and pending["msg_type"] == "interactive":
                                pending["msg_type"] = "text"
                                pending["content"] = _json({"text": pending["text_fallback"]})
                                pending["state"] = "prepared"
                                pending["uuid"] = _part_uuid(delivery_id, pending)
                        store.save(receipt)
                        continue
                    except FeishuUnknownError:
                        part["state"] = "unknown"
                        receipt["state"] = "unknown"
                        part["error"] = "Request outcome unknown; reconciliation required"
                        store.save(receipt)
                        raise DeliveryUnknownError(part["error"]) from None
                    except FeishuError as error:
                        self._fail(store, receipt, part, str(error))
                        raise
                    part["state"] = "sent"
                    part["message_id"] = message_id
                    part["sent_at"] = _now()
                    store.save(receipt)
            return self._complete(store, receipt)

    @staticmethod
    def _fail(store: ReceiptStore, receipt: dict, part: dict, reason: str) -> None:
        part["state"] = "failed"
        part["error"] = reason
        receipt["state"] = "partial" if any(p["state"] == "sent" for p in receipt["parts"]) else "failed"
        store.save(receipt)

    @staticmethod
    def _complete(store: ReceiptStore, receipt: dict) -> dict:
        receipt["state"] = "sent"
        receipt.setdefault("completed_at", max(part["sent_at"] for part in receipt["parts"]))
        store.save(receipt)
        store.publish(receipt)
        return receipt

    def load_snapshot(self, topic_id: str, binding_id: str, message_id: str | None = None) -> dict:
        _topic_dir(self.data_root, topic_id)
        return ReceiptStore(self.data_root, topic_id, binding_id).lookup(message_id)
