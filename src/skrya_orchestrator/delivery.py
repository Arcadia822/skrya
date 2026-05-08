from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import resolve_data_root


DELIVERY_BINDINGS_SCHEMA = "skrya.delivery-bindings.v1"
DELIVERY_BINDINGS_FILE = "delivery-bindings.json"


@dataclass(frozen=True, slots=True)
class DeliveryContext:
    host: str
    channel_id: str | None = None
    conversation_id: str | None = None
    workspace_id: str | None = None
    user_id: str | None = None
    channel_label: str | None = None
    conversation_label: str | None = None
    workspace_label: str | None = None
    user_label: str | None = None


@dataclass(frozen=True, slots=True)
class DeliveryBindingMatch:
    status: str
    bindings: list[dict[str, Any]]

    @property
    def topic_ids(self) -> list[str]:
        return [str(binding.get("topic_id")) for binding in self.bindings]

    @property
    def is_single(self) -> bool:
        return self.status == "single"


class DeliveryBindingService:
    def __init__(self, root: Path | str, data_root: Path | str | None = None) -> None:
        self._root = Path(root)
        self._data_root = resolve_data_root(self._root, data_root).data_root

    def write_binding(self, topic_id: str, binding: dict[str, Any]) -> Path:
        topic_id = self._normalize_topic_id(topic_id)
        if str(binding.get("topic_id", "")).strip() not in {"", topic_id}:
            raise ValueError("Delivery binding topic_id does not match target topic")
        binding = dict(binding)
        binding["topic_id"] = topic_id
        binding.setdefault("status", "active")
        now = datetime.now(timezone.utc).isoformat()
        binding.setdefault("created_at", now)
        binding["updated_at"] = now

        self.validate_binding(binding)

        path = self._binding_path(topic_id)
        payload = self._load_payload(path)
        bindings = [
            existing
            for existing in payload["bindings"]
            if self._binding_key(existing) != self._binding_key(binding)
        ]
        bindings.append(binding)
        payload["bindings"] = bindings
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def match_current_context(self, context: DeliveryContext) -> DeliveryBindingMatch:
        candidates: list[dict[str, Any]] = []
        for topic_dir in self._topics_root().iterdir() if self._topics_root().exists() else []:
            if not topic_dir.is_dir():
                continue
            path = topic_dir / DELIVERY_BINDINGS_FILE
            if not path.exists():
                continue
            payload = self._load_payload(path)
            for binding in payload["bindings"]:
                self.validate_binding(binding)
                if self._matches_context(binding, context):
                    candidates.append(binding)

        active = [binding for binding in candidates if binding.get("status", "active") == "active"]
        if not active:
            return DeliveryBindingMatch(status="none", bindings=[])
        if len(active) == 1:
            return DeliveryBindingMatch(status="single", bindings=active)
        return DeliveryBindingMatch(status="ambiguous", bindings=active)

    def validate_payload(self, payload: dict[str, Any]) -> None:
        if payload.get("schema") != DELIVERY_BINDINGS_SCHEMA:
            raise ValueError(f"Unsupported delivery binding schema: {payload.get('schema')!r}")
        bindings = payload.get("bindings")
        if not isinstance(bindings, list):
            raise ValueError("delivery-bindings.json must contain a bindings list")
        for binding in bindings:
            self.validate_binding(binding)

    @staticmethod
    def validate_binding(binding: dict[str, Any]) -> None:
        for field in ("topic_id", "host", "scope", "status"):
            if not str(binding.get(field, "")).strip():
                raise ValueError(f"Delivery binding missing required field: {field}")
        if binding["scope"] not in {"channel", "conversation"}:
            raise ValueError("Delivery binding scope must be channel or conversation")
        if not any(
            DeliveryBindingService._nested_text(binding, path)
            for path in (
                ("channel", "id"),
                ("conversation", "id"),
                ("channel", "label"),
                ("conversation", "label"),
            )
        ):
            raise ValueError("Delivery binding must identify a channel or conversation")
        host_metadata = binding.get("host_metadata", {})
        if host_metadata is not None and not isinstance(host_metadata, dict):
            raise ValueError("host_metadata must be an object when present")

    def _load_payload(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"schema": DELIVERY_BINDINGS_SCHEMA, "bindings": []}
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.validate_payload(payload)
        return payload

    def _binding_path(self, topic_id: str) -> Path:
        return self._topics_root() / topic_id / DELIVERY_BINDINGS_FILE

    def _topics_root(self) -> Path:
        return self._data_root / "topics"

    def _normalize_topic_id(self, topic_id: str) -> str:
        topic_id = str(topic_id).strip()
        if not topic_id:
            raise ValueError("topic_id is required")
        topic_path = self._topics_root() / topic_id
        if not topic_path.exists():
            raise FileNotFoundError(f"Topic '{topic_id}' not found")
        return topic_id

    @staticmethod
    def _binding_key(binding: dict[str, Any]) -> tuple[str, str, str, str, str]:
        return (
            str(binding.get("host", "")),
            DeliveryBindingService._nested_text(binding, ("channel", "id")),
            DeliveryBindingService._nested_text(binding, ("conversation", "id")),
            DeliveryBindingService._nested_text(binding, ("workspace", "id")),
            DeliveryBindingService._nested_text(binding, ("user", "id")),
        )

    @staticmethod
    def _matches_context(binding: dict[str, Any], context: DeliveryContext) -> bool:
        if str(binding.get("host", "")).strip() != context.host:
            return False

        channel_match = DeliveryBindingService._matches_identifier_or_label(
            binding,
            "channel",
            context.channel_id,
            context.channel_label,
        )
        conversation_match = DeliveryBindingService._matches_identifier_or_label(
            binding,
            "conversation",
            context.conversation_id,
            context.conversation_label,
        )
        if not channel_match and not conversation_match:
            return False

        if not DeliveryBindingService._optional_identity_matches(binding, "workspace", context.workspace_id):
            return False
        if not DeliveryBindingService._optional_identity_matches(binding, "user", context.user_id):
            return False
        return True

    @staticmethod
    def _matches_identifier_or_label(
        binding: dict[str, Any],
        key: str,
        context_id: str | None,
        context_label: str | None,
    ) -> bool:
        binding_id = DeliveryBindingService._nested_text(binding, (key, "id"))
        if binding_id and context_id:
            return binding_id == context_id
        if binding_id or context_id:
            return False
        binding_label = DeliveryBindingService._nested_text(binding, (key, "label"))
        return bool(binding_label and context_label and binding_label == context_label)

    @staticmethod
    def _optional_identity_matches(binding: dict[str, Any], key: str, context_id: str | None) -> bool:
        if not context_id:
            return True
        binding_id = DeliveryBindingService._nested_text(binding, (key, "id"))
        if binding_id:
            return binding_id == context_id
        return True

    @staticmethod
    def _nested_text(payload: dict[str, Any], path: tuple[str, str]) -> str:
        value: Any = payload
        for key in path:
            if not isinstance(value, dict):
                return ""
            value = value.get(key)
        return str(value).strip() if value is not None else ""
