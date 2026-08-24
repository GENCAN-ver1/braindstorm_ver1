from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from adapters.deepseek_p1 import (
    DEEPSEEK_ENDPOINT,
    DEEPSEEK_MODEL,
    DeepSeekP1Adapter,
    DeepSeekProviderError,
)


def _provider_payload(content: dict[str, object]) -> bytes:
    return json.dumps(
        {
            "id": "req-live-1",
            "model": DEEPSEEK_MODEL,
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(content)},
                }
            ],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 80,
                "total_tokens": 200,
            },
        }
    ).encode("utf-8")


class DeepSeekP1AdapterTests(unittest.TestCase):
    def test_fixed_endpoint_model_json_mode_and_call_time_secret(self) -> None:
        captured = {}

        def transport(request, timeout_seconds, max_response_bytes):
            captured["url"] = request.full_url
            captured["authorization"] = request.headers["Authorization"]
            captured["timeout"] = timeout_seconds
            captured["max_response_bytes"] = max_response_bytes
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _provider_payload({"candidates": [], "recommended_candidate_id": None})

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-secret"}, clear=False):
            result = DeepSeekP1Adapter(transport=transport).generate(
                {"problem_frame": {"problem": "DATA_ONLY"}},
                operation_id="session-1:run:0",
            )

        self.assertEqual(captured["url"], DEEPSEEK_ENDPOINT)
        self.assertEqual(captured["authorization"], "Bearer test-secret")
        self.assertEqual(captured["body"]["model"], DEEPSEEK_MODEL)
        self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})
        self.assertEqual(captured["body"]["thinking"], {"type": "disabled"})
        self.assertEqual(captured["body"]["max_tokens"], 8192)
        self.assertFalse(captured["body"]["stream"])
        self.assertNotIn("test-secret", json.dumps(result.to_dict()))
        self.assertEqual(result.usage["request_id"], "req-live-1")
        self.assertEqual(result.usage["prompt_tokens"], 120)

    def test_missing_secret_fails_before_transport(self) -> None:
        calls = 0

        def transport(*_args):
            nonlocal calls
            calls += 1
            raise AssertionError("transport must not run")

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(DeepSeekProviderError, "DEEPSEEK_API_KEY"):
                DeepSeekP1Adapter(transport=transport).generate({}, operation_id="op")
        self.assertEqual(calls, 0)

    def test_http_and_network_failures_are_redacted(self) -> None:
        failures = [
            HTTPError(DEEPSEEK_ENDPOINT, 429, "secret response", {}, None),
            URLError("credential=test-secret"),
        ]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                def transport(*_args):
                    raise failure

                with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-secret"}, clear=False):
                    with self.assertRaises(DeepSeekProviderError) as caught:
                        DeepSeekP1Adapter(transport=transport).generate({}, operation_id="op")
                message = str(caught.exception)
                self.assertNotIn("test-secret", message)
                self.assertNotIn("secret response", message)

    def test_rejects_invalid_or_truncated_provider_output(self) -> None:
        invalid_payloads = [
            b"not-json",
            json.dumps(
                {
                    "id": "req-1",
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": "{}"},
                        }
                    ],
                }
            ).encode("utf-8"),
            json.dumps(
                {
                    "id": "req-1",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "[]", "tool_calls": [{}]},
                        }
                    ],
                }
            ).encode("utf-8"),
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload[:20]):
                with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-secret"}, clear=False):
                    with self.assertRaisesRegex(DeepSeekProviderError, "invalid"):
                        DeepSeekP1Adapter(transport=lambda *_args: payload).generate(
                            {}, operation_id="op"
                        )

    def test_invalid_generated_content_retains_safe_usage(self) -> None:
        payload = json.dumps(
            {
                "id": "req-invalid-1",
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": "{}"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 34,
                    "total_tokens": 46,
                },
            }
        ).encode("utf-8")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-secret"}, clear=False):
            with self.assertRaisesRegex(DeepSeekProviderError, "finish_reason=length") as caught:
                DeepSeekP1Adapter(transport=lambda *_args: payload).generate({}, operation_id="op")

        self.assertEqual(caught.exception.usage["request_id"], "req-invalid-1")
        self.assertEqual(caught.exception.usage["total_tokens"], 46)


if __name__ == "__main__":
    unittest.main()
