"""Feishu and Lark Open API client with strict origin validation, rate pacing, and safe error classification."""
from __future__ import annotations

import http.client
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

FEISHU_OPEN_ORIGIN = "https://open.feishu.cn"
LARK_OPEN_ORIGIN = "https://open.larksuite.com"
ALLOWLISTED_ORIGINS = frozenset({FEISHU_OPEN_ORIGIN, LARK_OPEN_ORIGIN})

MAX_PAYLOAD_BYTES = 24000
MIN_PACING_INTERVAL = 0.25


class FeishuError(RuntimeError):
    """Base exception for all Feishu API errors."""


class FeishuAPIError(FeishuError):
    """Base exception for confirmed Feishu API errors."""

    def __init__(
        self,
        message: str = "Feishu API error",
        *,
        status_code: int | None = None,
        code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class FeishuAuthError(FeishuAPIError):
    """Authentication or credential failure."""


class FeishuPermissionError(FeishuAPIError):
    """Authorization or permission denied."""


class FeishuRateLimitError(FeishuAPIError):
    """Rate limit exceeded."""


class FeishuThreadNotSupportedError(FeishuAPIError):
    """Thread mode not supported by target chat."""


class FeishuCardFormatError(FeishuAPIError):
    """Card JSON schema, structural format, or size budget rejected."""


class FeishuUnknownError(FeishuError):
    """Write outcome is unknown (transport drop, timeout, HTTP 5xx, or malformed success)."""

    def __init__(
        self,
        message: str = "Feishu write outcome unknown",
        *,
        status_code: int | None = None,
        code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class TargetRateLimiter:
    """Enforces at most 4 requests per second per target (min 0.25s interval)."""

    def __init__(self, min_interval: float = MIN_PACING_INTERVAL) -> None:
        self.min_interval = min_interval
        self._last_call: dict[str, float] = {}

    def pace(self, target: str) -> None:
        if not target:
            return
        now = time.monotonic()
        last = self._last_call.get(target)
        if last is not None:
            elapsed = now - last
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
        self._last_call[target] = time.monotonic()


class DisallowRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Disallows HTTP redirects so credentials and tokens are never forwarded."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _classify_error(http_status: int, code: int | None) -> FeishuAPIError:
    """Classifies Feishu API errors strictly by numeric code, never by message substrings."""
    # 1. Thread unsupported: exact codes 230071, 230072
    if code in {230071, 230072}:
        return FeishuThreadNotSupportedError(
            f"Thread mode not supported (code={code})",
            status_code=http_status,
            code=code,
        )

    # 2. Card format error: definitive codes only, never message substring inspection
    if code in {230099, 200621, 200861}:
        return FeishuCardFormatError(
            f"Card format rejected (code={code})",
            status_code=http_status,
            code=code,
        )

    # 3. Rate limit: HTTP 429 or code 99991400
    if http_status == 429 or code == 99991400:
        return FeishuRateLimitError(
            f"Rate limit exceeded (status_code={http_status}, code={code})",
            status_code=http_status,
            code=code,
        )

    # 4. Auth error: HTTP 401 or codes 99991661, 99991668
    if http_status == 401 or code in {99991661, 99991668}:
        return FeishuAuthError(
            f"Authentication failed (status_code={http_status}, code={code})",
            status_code=http_status,
            code=code,
        )

    # 5. Permission error: HTTP 403 or specific permission codes
    if http_status == 403 or code in {
        99991663,
        99991664,
        230002,
        230006,
        230013,
        230018,
        230027,
        230035,
    }:
        return FeishuPermissionError(
            f"Permission denied (status_code={http_status}, code={code})",
            status_code=http_status,
            code=code,
        )

    # 6. General API error
    return FeishuAPIError(
        f"Feishu API error (status_code={http_status}, code={code})",
        status_code=http_status,
        code=code,
    )


class FeishuClient:
    """Client for Feishu / Lark Open API with strict origins, pacing, and safe errors."""

    def __init__(
        self,
        base_url: str = FEISHU_OPEN_ORIGIN,
        *,
        timeout: float = 30.0,
        transport: Callable[[urllib.request.Request, float], tuple[int, dict[str, str], bytes]] | None = None,
        rate_limiter: TargetRateLimiter | None = None,
    ) -> None:
        normalized = base_url.rstrip("/")
        if normalized not in ALLOWLISTED_ORIGINS:
            raise FeishuError(
                f"Base URL origin is not in allowlisted origins: {normalized!r}"
            )
        self.base_url = normalized
        self.timeout = float(timeout)
        self.transport = transport
        self.rate_limiter = rate_limiter or TargetRateLimiter(min_interval=MIN_PACING_INTERVAL)
        self._opener = urllib.request.build_opener(DisallowRedirectHandler())

    def _resolve_origin(self, origin: str | None = None) -> str:
        base = (origin or self.base_url).rstrip("/")
        if base not in ALLOWLISTED_ORIGINS:
            raise FeishuError(
                f"Origin {base!r} is not in allowlisted origins: {sorted(ALLOWLISTED_ORIGINS)}"
            )
        return base

    def _http_request(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        *,
        is_write: bool = False,
        target_for_pacing: str | None = None,
    ) -> dict[str, Any]:
        # Validate origin for this specific request
        parsed = urllib.parse.urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in ALLOWLISTED_ORIGINS:
            raise FeishuError(
                f"Request URL origin {origin!r} is not in allowlisted origins"
            )

        if target_for_pacing:
            self.rate_limiter.pace(target_for_pacing)

        req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)

        http_status: int
        resp_bytes: bytes

        if self.transport is not None:
            try:
                http_status, _, resp_bytes = self.transport(req, self.timeout)
            except (
                TimeoutError,
                urllib.error.URLError,
                ConnectionResetError,
                socket.timeout,
                http.client.IncompleteRead,
                ConnectionError,
                BrokenPipeError,
                OSError,
            ) as e:
                if is_write:
                    raise FeishuUnknownError(
                        "Transport uncertainty during write operation",
                        status_code=None,
                        code=None,
                    ) from e
                raise FeishuAPIError(
                    "Transport error during read request",
                    status_code=None,
                    code=None,
                ) from e
        else:
            try:
                with self._opener.open(req, timeout=self.timeout) as resp:
                    http_status = getattr(resp, "status", 200)
                    resp_bytes = resp.read()
            except urllib.error.HTTPError as e:
                http_status = e.code
                try:
                    resp_bytes = e.read()
                except Exception:
                    resp_bytes = b""
            except (
                TimeoutError,
                urllib.error.URLError,
                ConnectionResetError,
                socket.timeout,
                http.client.IncompleteRead,
                ConnectionError,
                BrokenPipeError,
                OSError,
            ) as e:
                if is_write:
                    raise FeishuUnknownError(
                        "Transport uncertainty during write operation",
                        status_code=None,
                        code=None,
                    ) from e
                raise FeishuAPIError(
                    "Transport error during read request",
                    status_code=None,
                    code=None,
                ) from e

        # Disallow HTTP redirects
        if 300 <= http_status < 400:
            raise FeishuAPIError(
                f"HTTP redirect {http_status} disallowed",
                status_code=http_status,
                code=None,
            )

        # HTTP 5xx: write outcome is unknown; read is confirmed server error
        if http_status >= 500:
            if is_write:
                raise FeishuUnknownError(
                    f"Server error (HTTP {http_status}) after write operation",
                    status_code=http_status,
                    code=None,
                )
            raise FeishuAPIError(
                f"Server error (HTTP {http_status})",
                status_code=http_status,
                code=None,
            )

        # Parse JSON response
        try:
            resp_text = resp_bytes.decode("utf-8")
            data = json.loads(resp_text)
        except Exception as e:
            if is_write:
                raise FeishuUnknownError(
                    f"Malformed response JSON after write (HTTP {http_status})",
                    status_code=http_status,
                    code=None,
                ) from e
            raise FeishuAPIError(
                f"Malformed response JSON (HTTP {http_status})",
                status_code=http_status,
                code=None,
            ) from e

        if not isinstance(data, dict):
            if is_write:
                raise FeishuUnknownError(
                    f"Malformed response: expected JSON object (HTTP {http_status})",
                    status_code=http_status,
                    code=None,
                )
            raise FeishuAPIError(
                f"Malformed response: expected JSON object (HTTP {http_status})",
                status_code=http_status,
                code=None,
            )

        code = data.get("code")
        if type(code) is not int:
            error = FeishuUnknownError if is_write else FeishuAPIError
            raise error("Malformed response code", status_code=http_status)
        if code != 0:
            raise _classify_error(http_status, code)

        if http_status >= 400:
            raise _classify_error(http_status, code)

        return data

    def get_tenant_access_token(
        self, app_id: str, app_secret: str, origin: str | None = None
    ) -> str:
        """Obtains internal tenant access token for the given app credentials."""
        base = self._resolve_origin(origin)
        url = f"{base}/open-apis/auth/v3/tenant_access_token/internal"
        payload = json.dumps(
            {"app_id": app_id, "app_secret": app_secret},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8"}

        try:
            resp = self._http_request(
                url,
                method="POST",
                headers=headers,
                body=payload,
                is_write=False,
            )
        except (FeishuAPIError, FeishuError) as e:
            raise FeishuAuthError(
                f"Token retrieval failed (status_code={getattr(e, 'status_code', None)}, code={getattr(e, 'code', None)})",
                status_code=getattr(e, "status_code", None),
                code=getattr(e, "code", None),
            ) from e

        token = resp.get("tenant_access_token")
        if not token or not isinstance(token, str):
            raise FeishuAuthError(
                "Token retrieval failed: response missing tenant_access_token",
                status_code=200,
                code=resp.get("code"),
            )
        return str(token)

    def check_read_access(
        self,
        token: str,
        target: str,
        target_type: str,
        origin: str | None = None,
    ) -> dict[str, Any]:
        """Preflights read access without requiring unnecessary contact scopes for private targets."""
        base = self._resolve_origin(origin)

        # Private targets (ou_ / open_id): no safe read API without requiring extra contact scopes.
        # Return explicit limited preflight, never fake read success or guaranteed permission.
        if target_type == "open_id" or target.startswith("ou_"):
            return {
                "read_access": False,
                "permission_guaranteed": False,
                "target": target,
                "target_type": target_type,
                "status": "unavailable",
                "preflight": "limited",
                "reason": "Private target preflight read API unavailable without contact scopes",
            }

        # Validate group target format
        if (
            not target
            or not isinstance(target, str)
            or not target.strip()
            or "/" in target
            or ".." in target
            or "\\" in target
        ):
            return {
                "read_access": False,
                "permission_guaranteed": False,
                "target": target,
                "target_type": target_type,
                "status": "malformed",
                "error": "Target ID is invalid or malformed",
            }

        safe_target = urllib.parse.quote(target.strip(), safe="")
        url = f"{base}/open-apis/im/v1/chats/{safe_target}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        try:
            resp = self._http_request(
                url,
                method="GET",
                headers=headers,
                is_write=False,
                target_for_pacing=target,
            )
            return {
                "read_access": True,
                "permission_guaranteed": False,
                "target": target,
                "target_type": target_type,
                "status": "ok",
                "details": resp.get("data", {}),
            }
        except (FeishuPermissionError, FeishuAPIError, FeishuError) as e:
            return {
                "read_access": False,
                "permission_guaranteed": False,
                "target": target,
                "target_type": target_type,
                "status": "denied" if isinstance(e, FeishuPermissionError) else "failed",
                "code": getattr(e, "code", None),
                "error": f"Group access check failed (code={getattr(e, 'code', None)})",
            }

    def send_message(
        self,
        token: str,
        receive_id: str,
        msg_type: str,
        content: str,
        uuid: str,
        origin: str | None = None,
    ) -> dict[str, Any]:
        """Sends a root message to receive_id, strictly enforcing <=24000 byte compact UTF-8 budget."""
        base = self._resolve_origin(origin)

        if (
            not receive_id
            or not isinstance(receive_id, str)
            or not receive_id.strip()
            or "/" in receive_id
            or ".." in receive_id
            or "\\" in receive_id
        ):
            raise ValueError("receive_id is invalid or malformed")

        receive_id_type = "open_id" if receive_id.startswith("ou_") else "chat_id"
        url = f"{base}/open-apis/im/v1/messages?receive_id_type={receive_id_type}"

        payload_obj = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": content,
            "uuid": uuid,
        }
        payload_bytes = json.dumps(
            payload_obj,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        if len(payload_bytes) > MAX_PAYLOAD_BYTES:
            raise FeishuCardFormatError(
                f"Payload size {len(payload_bytes)} bytes exceeds limit of {MAX_PAYLOAD_BYTES} bytes"
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        resp = self._http_request(
            url,
            method="POST",
            headers=headers,
            body=payload_bytes,
            is_write=True,
            target_for_pacing=receive_id,
        )

        data = resp.get("data")
        if not isinstance(data, dict):
            raise FeishuUnknownError(
                f"Send message response missing data object (code={resp.get('code')})"
            )
        message_id = data.get("message_id")
        if not isinstance(message_id, str) or not message_id.strip():
            raise FeishuUnknownError(
                f"Send message response missing valid message_id (code={resp.get('code')})"
            )
        return data

    def reply_message(
        self,
        token: str,
        message_id: str,
        msg_type: str,
        content: str,
        uuid: str,
        reply_in_thread: bool = True,
        origin: str | None = None,
        *,
        target: str | None = None,
    ) -> dict[str, Any]:
        """Replies to a message, sharing destination pacing key across roots and replies."""
        base = self._resolve_origin(origin)

        if (
            not message_id
            or not isinstance(message_id, str)
            or not message_id.strip()
            or "/" in message_id
            or ".." in message_id
            or "\\" in message_id
        ):
            raise ValueError("message_id is invalid or malformed")

        safe_msg_id = urllib.parse.quote(message_id.strip(), safe="")
        url = f"{base}/open-apis/im/v1/messages/{safe_msg_id}/reply"

        payload_obj = {
            "content": content,
            "msg_type": msg_type,
            "reply_in_thread": reply_in_thread,
            "uuid": uuid,
        }
        payload_bytes = json.dumps(
            payload_obj,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        if len(payload_bytes) > MAX_PAYLOAD_BYTES:
            raise FeishuCardFormatError(
                f"Payload size {len(payload_bytes)} bytes exceeds limit of {MAX_PAYLOAD_BYTES} bytes"
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        # Shared destination pacing key: target (chat/user ID) if provided, else message_id
        pacing_target = target if target is not None else message_id

        resp = self._http_request(
            url,
            method="POST",
            headers=headers,
            body=payload_bytes,
            is_write=True,
            target_for_pacing=pacing_target,
        )

        data = resp.get("data")
        if not isinstance(data, dict):
            raise FeishuUnknownError(
                f"Reply message response missing data object (code={resp.get('code')})"
            )
        reply_message_id = data.get("message_id")
        if not isinstance(reply_message_id, str) or not reply_message_id.strip():
            raise FeishuUnknownError(
                f"Reply message response missing valid message_id (code={resp.get('code')})"
            )
        return data


__all__ = [
    "ALLOWLISTED_ORIGINS",
    "FEISHU_OPEN_ORIGIN",
    "LARK_OPEN_ORIGIN",
    "MAX_PAYLOAD_BYTES",
    "MIN_PACING_INTERVAL",
    "FeishuAPIError",
    "FeishuAuthError",
    "FeishuCardFormatError",
    "FeishuClient",
    "FeishuError",
    "FeishuPermissionError",
    "FeishuRateLimitError",
    "FeishuThreadNotSupportedError",
    "FeishuUnknownError",
    "TargetRateLimiter",
]
