"""Comprehensive tests for FeishuClient API covering serialization, pacing, budget, and error handling."""
from __future__ import annotations

import json
import socket
import time
import unittest
import urllib.parse
import urllib.request
from unittest.mock import MagicMock, patch

from skrya_orchestrator.feishu_api import (
    ALLOWLISTED_ORIGINS,
    FEISHU_OPEN_ORIGIN,
    LARK_OPEN_ORIGIN,
    MAX_PAYLOAD_BYTES,
    FeishuAPIError,
    FeishuAuthError,
    FeishuCardFormatError,
    FeishuClient,
    FeishuError,
    FeishuPermissionError,
    FeishuRateLimitError,
    FeishuThreadNotSupportedError,
    FeishuUnknownError,
    TargetRateLimiter,
)


class TestFeishuApi(unittest.TestCase):
    """Deterministic tests for FeishuClient and related API components."""

    def test_malformed_error_codes_never_authorize_fallback_or_leak_provider_data(self):
        for code in (None, True, "secret-provider-value", {"secret": "value"}):
            with self.subTest(code=code):
                client = FeishuClient(transport=lambda *_: (200, {}, json.dumps({"code": code}).encode()))
                with self.assertRaises(FeishuUnknownError) as caught:
                    client.send_message("token", "oc_target", "text", '{"text":"news"}', "unique")
                self.assertNotIn("secret", str(caught.exception))

    def test_whitespace_message_ids_are_unknown_for_send_and_reply(self):
        for route in ("send", "reply"):
            with self.subTest(route=route):
                client = FeishuClient(transport=lambda *_: (200, {}, b'{"code":0,"data":{"message_id":" "}}'))
                with self.assertRaises(FeishuUnknownError):
                    if route == "send":
                        client.send_message("token", "oc_target", "text", '{"text":"news"}', "unique")
                    else:
                        client.reply_message("token", "om_root", "text", '{"text":"news"}', "unique", target="oc_target")

    # -------------------------------------------------------------------------
    # 1. Actual API Serialization
    # -------------------------------------------------------------------------

    def test_actual_api_serialization_send_message_chat_id(self) -> None:
        captured_req: list[urllib.request.Request] = []

        def transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            captured_req.append(req)
            return 200, {"Content-Type": "application/json"}, json.dumps({
                "code": 0,
                "msg": "ok",
                "data": {"message_id": "om_send_123"},
            }).encode("utf-8")

        client = FeishuClient(transport=transport)
        res = client.send_message(
            token="test_tok_abc",
            receive_id="oc_chat_001",
            msg_type="interactive",
            content='{"header":{"title":{"content":"Test"}}}',
            uuid="uuid-send-001",
        )

        self.assertEqual("om_send_123", res["message_id"])
        self.assertEqual(1, len(captured_req))
        req = captured_req[0]
        self.assertEqual("POST", req.get_method())
        self.assertEqual(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            req.full_url,
        )
        self.assertEqual("Bearer test_tok_abc", req.headers.get("Authorization"))
        self.assertIn("application/json", req.headers.get("Content-type", ""))

        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual("oc_chat_001", body["receive_id"])
        self.assertEqual("interactive", body["msg_type"])
        self.assertEqual('{"header":{"title":{"content":"Test"}}}', body["content"])
        self.assertEqual("uuid-send-001", body["uuid"])

        # Verify compact JSON encoding: no spaces around delimiters
        raw_body_str = req.data.decode("utf-8")
        self.assertNotIn(": ", raw_body_str)
        self.assertNotIn(", ", raw_body_str)

    def test_actual_api_serialization_send_message_open_id(self) -> None:
        captured_req: list[urllib.request.Request] = []

        def transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            captured_req.append(req)
            return 200, {"Content-Type": "application/json"}, json.dumps({
                "code": 0,
                "msg": "ok",
                "data": {"message_id": "om_send_456"},
            }).encode("utf-8")

        client = FeishuClient(transport=transport)
        client.send_message(
            token="test_tok_user",
            receive_id="ou_user_999",
            msg_type="text",
            content='{"text":"hello"}',
            uuid="uuid-send-002",
        )

        self.assertEqual(1, len(captured_req))
        req = captured_req[0]
        self.assertEqual(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            req.full_url,
        )

    def test_actual_api_serialization_reply_message(self) -> None:
        captured_req: list[urllib.request.Request] = []

        def transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            captured_req.append(req)
            return 200, {"Content-Type": "application/json"}, json.dumps({
                "code": 0,
                "msg": "ok",
                "data": {"message_id": "om_reply_789"},
            }).encode("utf-8")

        client = FeishuClient(transport=transport)
        res = client.reply_message(
            token="test_tok_reply",
            message_id="om_root_root",
            msg_type="interactive",
            content='{"card":"reply"}',
            uuid="uuid-reply-003",
            reply_in_thread=True,
            target="oc_chat_target",
        )

        self.assertEqual("om_reply_789", res["message_id"])
        self.assertEqual(1, len(captured_req))
        req = captured_req[0]
        self.assertEqual("POST", req.get_method())
        self.assertEqual(
            "https://open.feishu.cn/open-apis/im/v1/messages/om_root_root/reply",
            req.full_url,
        )
        self.assertEqual("Bearer test_tok_reply", req.headers.get("Authorization"))

        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual('{"card":"reply"}', body["content"])
        self.assertEqual("interactive", body["msg_type"])
        self.assertTrue(body["reply_in_thread"])
        self.assertEqual("uuid-reply-003", body["uuid"])

    def test_actual_api_serialization_token_and_group_read(self) -> None:
        captured_req: list[urllib.request.Request] = []

        def transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            captured_req.append(req)
            if "tenant_access_token" in req.full_url:
                return 200, {"Content-Type": "application/json"}, json.dumps({
                    "code": 0,
                    "msg": "ok",
                    "tenant_access_token": "t-token-xyz",
                }).encode("utf-8")
            return 200, {"Content-Type": "application/json"}, json.dumps({
                "code": 0,
                "msg": "ok",
                "data": {"name": "Test Group"},
            }).encode("utf-8")

        client = FeishuClient(transport=transport)
        tok = client.get_tenant_access_token("cli_test_app", "sec_test_secret")
        self.assertEqual("t-token-xyz", tok)
        self.assertEqual("POST", captured_req[0].get_method())
        self.assertEqual(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            captured_req[0].full_url,
        )

        read_res = client.check_read_access("t-token-xyz", "oc_group_123", "chat_id")
        self.assertTrue(read_res["read_access"])
        self.assertFalse(read_res["permission_guaranteed"])
        self.assertEqual("GET", captured_req[1].get_method())
        self.assertEqual(
            "https://open.feishu.cn/open-apis/im/v1/chats/oc_group_123",
            captured_req[1].full_url,
        )

    # -------------------------------------------------------------------------
    # 2. Redirect Rejection
    # -------------------------------------------------------------------------

    def test_redirect_rejection_302(self) -> None:
        def redirect_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            return 302, {"Location": "https://attacker.example.com/steal"}, b""

        client = FeishuClient(transport=redirect_transport)
        with self.assertRaises(FeishuAPIError) as ctx:
            client.send_message("token_1", "oc_chat", "text", "{}", "uuid-red-1")
        self.assertEqual(302, ctx.exception.status_code)
        self.assertIn("302", str(ctx.exception))
        self.assertNotIn("attacker.example.com", str(ctx.exception))

    def test_redirect_rejection_307(self) -> None:
        def redirect_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            return 307, {"Location": "https://open.larksuite.com/open-apis/..."}, b""

        client = FeishuClient(transport=redirect_transport)
        with self.assertRaises(FeishuAPIError) as ctx:
            client.get_tenant_access_token("app_id", "app_sec")
        self.assertEqual(307, ctx.exception.status_code)

    # -------------------------------------------------------------------------
    # 3. Actual Budget: No API Call on Oversized Payload
    # -------------------------------------------------------------------------

    def test_actual_budget_no_apicall_on_oversized_payload(self) -> None:
        transport_calls: list[urllib.request.Request] = []

        def tracking_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            transport_calls.append(req)
            return 200, {"Content-Type": "application/json"}, json.dumps({
                "code": 0,
                "msg": "ok",
                "data": {"message_id": "om_ok"},
            }).encode("utf-8")

        client = FeishuClient(transport=tracking_transport)

        # Build payload that exceeds MAX_PAYLOAD_BYTES (24000)
        # Envelope boilerplate for send_message is ~80 bytes.
        large_content = "X" * 24000

        with self.assertRaises(FeishuCardFormatError) as ctx:
            client.send_message(
                token="tok",
                receive_id="oc_chat_large",
                msg_type="interactive",
                content=large_content,
                uuid="uuid-large",
            )
        self.assertIn("exceeds", str(ctx.exception))
        # Ensure NO API call was dispatched over network/transport
        self.assertEqual(0, len(transport_calls))

        # Test same budget enforcement on reply_message
        with self.assertRaises(FeishuCardFormatError):
            client.reply_message(
                token="tok",
                message_id="om_root",
                msg_type="interactive",
                content=large_content,
                uuid="uuid-large-reply",
            )
        self.assertEqual(0, len(transport_calls))

        # Payload within budget succeeds and executes transport
        small_content = '{"title":"Within budget"}'
        res = client.send_message(
            token="tok",
            receive_id="oc_chat_large",
            msg_type="interactive",
            content=small_content,
            uuid="uuid-small",
        )
        self.assertEqual("om_ok", res["message_id"])
        self.assertEqual(1, len(transport_calls))

    # -------------------------------------------------------------------------
    # 4. Malformed-Success Uncertainty
    # -------------------------------------------------------------------------

    def test_malformed_success_missing_message_id_is_unknown(self) -> None:
        def missing_id_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            return 200, {"Content-Type": "application/json"}, json.dumps({
                "code": 0,
                "msg": "success",
                "data": {},  # Missing message_id
            }).encode("utf-8")

        client = FeishuClient(transport=missing_id_transport)
        with self.assertRaises(FeishuUnknownError) as ctx:
            client.send_message("tok", "oc_chat", "text", "{}", "u1")
        self.assertIn("message_id", str(ctx.exception))

    def test_malformed_success_empty_message_id_is_unknown(self) -> None:
        def empty_id_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            return 200, {"Content-Type": "application/json"}, json.dumps({
                "code": 0,
                "msg": "success",
                "data": {"message_id": ""},
            }).encode("utf-8")

        client = FeishuClient(transport=empty_id_transport)
        with self.assertRaises(FeishuUnknownError):
            client.reply_message("tok", "om_root", "text", "{}", "u2")

    def test_malformed_json_after_send_is_unknown(self) -> None:
        def bad_json_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            return 200, {"Content-Type": "text/html"}, b"<html>502 Bad Gateway</html>"

        client = FeishuClient(transport=bad_json_transport)
        with self.assertRaises(FeishuUnknownError):
            client.send_message("tok", "oc_chat", "text", "{}", "u3")

    def test_http_5xx_after_send_is_unknown(self) -> None:
        def http500_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            return 500, {"Content-Type": "application/json"}, json.dumps({
                "code": 99991500,
                "msg": "Internal server error",
            }).encode("utf-8")

        client = FeishuClient(transport=http500_transport)
        with self.assertRaises(FeishuUnknownError) as ctx:
            client.send_message("tok", "oc_chat", "text", "{}", "u4")
        self.assertEqual(500, ctx.exception.status_code)

    def test_transport_timeout_after_send_is_unknown(self) -> None:
        def timeout_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            raise socket.timeout("Connection timed out after send")

        client = FeishuClient(transport=timeout_transport)
        with self.assertRaises(FeishuUnknownError):
            client.send_message("tok", "oc_chat", "text", "{}", "u5")

    # -------------------------------------------------------------------------
    # 5. Misleading Permission Message Containing Card (Not Format Fallback)
    # -------------------------------------------------------------------------

    def test_misleading_permission_message_containing_card_not_format_fallback(self) -> None:
        # Feishu returns code 230013 (permission denied) with a message mentioning "card"
        def permission_card_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            return 200, {"Content-Type": "application/json"}, json.dumps({
                "code": 230013,
                "msg": "Bot has no permission to send card message in this group (schema check)",
            }).encode("utf-8")

        client = FeishuClient(transport=permission_card_transport)

        # Must raise FeishuPermissionError, NOT FeishuCardFormatError
        with self.assertRaises(FeishuPermissionError) as ctx:
            client.send_message("tok", "oc_chat", "interactive", "{}", "u-perm-1")

        self.assertFalse(isinstance(ctx.exception, FeishuCardFormatError))
        self.assertEqual(230013, ctx.exception.code)

        # Error message must NOT reveal raw provider string
        err_msg = str(ctx.exception)
        self.assertNotIn("Bot has no permission to send card", err_msg)
        self.assertNotIn("schema check", err_msg)

    def test_definitive_card_format_codes_classified_correctly(self) -> None:
        for card_code in (230099, 200621, 200861):
            def card_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
                return 200, {"Content-Type": "application/json"}, json.dumps({
                    "code": card_code,
                    "msg": "card structure error",
                }).encode("utf-8")

            client = FeishuClient(transport=card_transport)
            with self.assertRaises(FeishuCardFormatError) as ctx:
                client.send_message("tok", "oc_chat", "interactive", "{}", "u-card")
            self.assertEqual(card_code, ctx.exception.code)

    def test_thread_not_supported_exact_codes(self) -> None:
        for thread_code in (230071, 230072):
            def thread_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
                return 200, {"Content-Type": "application/json"}, json.dumps({
                    "code": thread_code,
                    "msg": "Chat does not support thread mode",
                }).encode("utf-8")

            client = FeishuClient(transport=thread_transport)
            with self.assertRaises(FeishuThreadNotSupportedError) as ctx:
                client.reply_message("tok", "om_root", "text", "{}", "u-th")
            self.assertEqual(thread_code, ctx.exception.code)

    # -------------------------------------------------------------------------
    # 6. Common Target Pacing
    # -------------------------------------------------------------------------

    def test_common_target_pacing_shared_between_send_and_reply(self) -> None:
        def ok_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            return 200, {"Content-Type": "application/json"}, json.dumps({
                "code": 0,
                "msg": "ok",
                "data": {"message_id": "om_paced"},
            }).encode("utf-8")

        limiter = TargetRateLimiter(min_interval=0.25)
        client = FeishuClient(transport=ok_transport, rate_limiter=limiter)

        sleep_calls: list[float] = []

        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)), \
             patch("time.monotonic") as mock_time:
            # First call at t = 100.0
            mock_time.return_value = 100.0
            client.send_message("tok", "oc_shared_chat", "text", "{}", "u-p1")
            self.assertEqual(0, len(sleep_calls))

            # Second call (reply) at t = 100.1 (< 0.25s) with explicit target="oc_shared_chat"
            mock_time.return_value = 100.1
            client.reply_message(
                "tok",
                "om_root_id",
                "text",
                "{}",
                "u-p2",
                target="oc_shared_chat",
            )
            # Must sleep 0.25 - 0.1 = 0.15s
            self.assertEqual(1, len(sleep_calls))
            self.assertAlmostEqual(0.15, sleep_calls[0], places=5)

            # Third call to a DIFFERENT target at t = 100.1 should NOT sleep
            mock_time.return_value = 100.1
            client.send_message("tok", "oc_other_chat", "text", "{}", "u-p3")
            self.assertEqual(1, len(sleep_calls))

    # -------------------------------------------------------------------------
    # 7. Token Retrieval Failure
    # -------------------------------------------------------------------------

    def test_token_retrieval_failure_missing_token(self) -> None:
        def no_token_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            return 200, {"Content-Type": "application/json"}, json.dumps({
                "code": 0,
                "msg": "ok",
            }).encode("utf-8")

        client = FeishuClient(transport=no_token_transport)
        with self.assertRaises(FeishuAuthError) as ctx:
            client.get_tenant_access_token("app_1", "sec_1")
        self.assertIn("missing tenant_access_token", str(ctx.exception))
        self.assertNotIn("sec_1", str(ctx.exception))

    def test_token_retrieval_failure_auth_error_code(self) -> None:
        secret = "s1"  # short secret to verify no leakage

        def auth_error_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            return 400, {"Content-Type": "application/json"}, json.dumps({
                "code": 99991661,
                "msg": f"Secret {secret} is invalid",
            }).encode("utf-8")

        client = FeishuClient(transport=auth_error_transport)
        with self.assertRaises(FeishuAuthError) as ctx:
            client.get_tenant_access_token("app_1", secret)
        self.assertEqual(99991661, ctx.exception.code)
        self.assertNotIn(secret, str(ctx.exception))
        self.assertNotIn(f"Secret {secret} is invalid", str(ctx.exception))

    def test_token_retrieval_failure_http_401(self) -> None:
        def http401_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            return 401, {"Content-Type": "application/json"}, b'{"msg":"Unauthorized"}'

        client = FeishuClient(transport=http401_transport)
        with self.assertRaises(FeishuAuthError):
            client.get_tenant_access_token("app_1", "sec_secret")

    # -------------------------------------------------------------------------
    # 8. Private Preflight Accurately Limited
    # -------------------------------------------------------------------------

    def test_private_preflight_accurately_limited_without_contact_scope(self) -> None:
        transport_mock = MagicMock()
        client = FeishuClient(transport=transport_mock)

        # ou_ target does NOT invoke transport
        res_ou = client.check_read_access("tok", "ou_user_123", "open_id")
        self.assertFalse(res_ou["read_access"])
        self.assertFalse(res_ou["permission_guaranteed"])
        self.assertEqual("unavailable", res_ou["status"])
        self.assertEqual("limited", res_ou["preflight"])
        self.assertEqual(0, transport_mock.call_count)

        # target_type="open_id" also does NOT invoke transport
        res_open_id = client.check_read_access("tok", "user_without_ou", "open_id")
        self.assertFalse(res_open_id["read_access"])
        self.assertFalse(res_open_id["permission_guaranteed"])
        self.assertEqual("unavailable", res_open_id["status"])
        self.assertEqual(0, transport_mock.call_count)

    def test_group_preflight_success_and_failure(self) -> None:
        def group_transport(req: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
            if "oc_allowed" in req.full_url:
                return 200, {"Content-Type": "application/json"}, json.dumps({
                    "code": 0,
                    "msg": "ok",
                    "data": {"name": "Allowed Chat"},
                }).encode("utf-8")
            return 403, {"Content-Type": "application/json"}, json.dumps({
                "code": 230013,
                "msg": "Bot not in chat",
            }).encode("utf-8")

        client = FeishuClient(transport=group_transport)

        # Succeeded group check
        ok_res = client.check_read_access("tok", "oc_allowed", "chat_id")
        self.assertTrue(ok_res["read_access"])
        self.assertFalse(ok_res["permission_guaranteed"])
        self.assertEqual("ok", ok_res["status"])

        # Failed group check must NOT return status ok
        denied_res = client.check_read_access("tok", "oc_denied", "chat_id")
        self.assertFalse(denied_res["read_access"])
        self.assertFalse(denied_res["permission_guaranteed"])
        self.assertEqual("denied", denied_res["status"])
        self.assertNotEqual("ok", denied_res["status"])

        # Malformed group target
        malformed_res = client.check_read_access("tok", "../escape/path", "chat_id")
        self.assertFalse(malformed_res["read_access"])
        self.assertFalse(malformed_res["permission_guaranteed"])
        self.assertEqual("malformed", malformed_res["status"])

    # -------------------------------------------------------------------------
    # 9. Origins and Allowlist
    # -------------------------------------------------------------------------

    def test_origin_allowlist_enforcement(self) -> None:
        with self.assertRaises(FeishuError):
            FeishuClient(base_url="https://attacker.example.com")

        client = FeishuClient(base_url=FEISHU_OPEN_ORIGIN)
        with self.assertRaises(FeishuError):
            client.send_message("tok", "oc_chat", "text", "{}", "u", origin="https://invalid.com")

        # Larksuite origin allowed
        lark_client = FeishuClient(base_url=LARK_OPEN_ORIGIN)
        self.assertEqual(LARK_OPEN_ORIGIN, lark_client.base_url)


if __name__ == "__main__":
    unittest.main()
