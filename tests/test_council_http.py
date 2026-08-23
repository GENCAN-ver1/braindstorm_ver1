from __future__ import annotations

import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from adapters.council_http import OpenAICompatibleCouncilAdapter
from p5_council import (
    CouncilEvidenceDatum,
    CouncilMemberRequest,
    CouncilMemberResult,
    CouncilProtocol,
    CouncilProvider,
    CouncilProviderConfig,
)


class FakeResponse:
    def __init__(self, value: dict[str, object]) -> None:
        self.body = json.dumps(value).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


class CouncilHttpAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = CouncilProviderConfig(
            provider=CouncilProvider.DEEPSEEK,
            enabled=True,
            protocol=CouncilProtocol.OPENAI_COMPATIBLE,
            base_url="https://provider.example/v1",
            model="test-model",
            credential_env="TEST_COUNCIL_KEY",
            timeout_seconds=7,
            max_output_tokens=321,
            provider_options={"temperature": 0.2},
        )
        self.request = CouncilMemberRequest(
            member_id="deepseek-product",
            provider=CouncilProvider.DEEPSEEK,
            shared_frame={"problem": "reduce meal decision cost"},
            question="Should the confirmed mechanism proceed?",
            assigned_dimension="behavior loop and product value",
            hard_constraints=["no medical diagnosis"],
            evidence_summary=[
                CouncilEvidenceDatum(
                    "e1", "photo portions require confirmation", "https://example/e1"
                )
            ],
            output_contract={"required": ["verdict", "risks"]},
        )

    def test_success_uses_chat_completions_and_returns_normalized_usage(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(http_request, timeout):
            captured["request"] = http_request
            captured["timeout"] = timeout
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"verdict": "REFINE", "risks": ["trust"]}
                                )
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                    },
                    "raw_vendor_field": "must not escape",
                }
            )

        with patch.dict(os.environ, {"TEST_COUNCIL_KEY": "secret-at-call-time"}):
            with patch("adapters.council_http.urlopen", side_effect=fake_urlopen):
                result = OpenAICompatibleCouncilAdapter().invoke(
                    self.config, self.request
                )

        self.assertIsInstance(result, CouncilMemberResult)
        self.assertTrue(result.success)
        self.assertEqual(result.output, {"verdict": "REFINE", "risks": ["trust"]})
        self.assertEqual(result.usage.prompt_tokens, 100)
        self.assertEqual(result.usage.completion_tokens, 20)
        self.assertEqual(result.usage.total_tokens, 120)
        self.assertFalse(hasattr(result, "raw_vendor_field"))
        http_request = captured["request"]
        self.assertEqual(http_request.full_url, "https://provider.example/v1/chat/completions")
        self.assertEqual(http_request.get_header("Authorization"), "Bearer secret-at-call-time")
        self.assertEqual(captured["timeout"], 7)
        body = json.loads(http_request.data.decode("utf-8"))
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(body["max_tokens"], 321)
        self.assertFalse(body["stream"])
        member_payload = json.loads(body["messages"][1]["content"])
        self.assertEqual(member_payload["member_id"], "deepseek-product")
        self.assertEqual(member_payload["evidence_summary"][0]["treatment"], "DATA_ONLY")
        self.assertNotIn("peer_outputs", member_payload)

    def test_credential_is_resolved_only_when_invoke_runs(self) -> None:
        adapter = OpenAICompatibleCouncilAdapter()
        response = FakeResponse(
            {
                "choices": [
                    {"message": {"content": '{"verdict":"PROCEED","risks":[]}'}}
                ]
            }
        )
        with patch.dict(os.environ, {}, clear=True):
            os.environ["TEST_COUNCIL_KEY"] = "added-after-construction"
            with patch("adapters.council_http.urlopen", return_value=response) as call:
                result = adapter.invoke(self.config, self.request)

        self.assertTrue(result.success)
        self.assertEqual(
            call.call_args.args[0].get_header("Authorization"),
            "Bearer added-after-construction",
        )

    def test_missing_credential_returns_failure_without_network_call(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("adapters.council_http.urlopen") as call:
                result = OpenAICompatibleCouncilAdapter().invoke(
                    self.config, self.request
                )

        self.assertFalse(result.success)
        self.assertIsNone(result.output)
        self.assertIn("TEST_COUNCIL_KEY", result.error)
        self.assertIsNone(result.usage.total_tokens)
        call.assert_not_called()

    def test_http_error_does_not_expose_secret_or_raw_error_body(self) -> None:
        error = HTTPError(
            "https://provider.example/v1/chat/completions",
            401,
            "TOP_SECRET provider detail",
            hdrs=None,
            fp=io.BytesIO(b"RAW_TOP_SECRET_BODY"),
        )
        with patch.dict(os.environ, {"TEST_COUNCIL_KEY": "key"}):
            with patch("adapters.council_http.urlopen", side_effect=error):
                result = OpenAICompatibleCouncilAdapter().invoke(
                    self.config, self.request
                )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "provider HTTP request failed with status 401")
        self.assertNotIn("SECRET", result.error)

    def test_missing_or_inconsistent_usage_remains_null_not_estimated(self) -> None:
        response = FakeResponse(
            {
                "choices": [
                    {"message": {"content": "```json\n{\"verdict\":\"REFINE\"}\n```"}}
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 2,
                },
            }
        )
        with patch.dict(os.environ, {"TEST_COUNCIL_KEY": "key"}):
            with patch("adapters.council_http.urlopen", return_value=response):
                result = OpenAICompatibleCouncilAdapter().invoke(
                    self.config, self.request
                )

        self.assertTrue(result.success)
        self.assertEqual(result.usage.prompt_tokens, 10)
        self.assertEqual(result.usage.completion_tokens, 5)
        self.assertIsNone(result.usage.total_tokens)

    def test_invalid_provider_content_returns_only_structured_failure(self) -> None:
        response = FakeResponse(
            {
                "choices": [
                    {"message": {"content": "RAW_PRIVATE_RESPONSE_NOT_JSON"}}
                ]
            }
        )
        with patch.dict(os.environ, {"TEST_COUNCIL_KEY": "key"}):
            with patch("adapters.council_http.urlopen", return_value=response):
                result = OpenAICompatibleCouncilAdapter().invoke(
                    self.config, self.request
                )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "provider response was invalid")
        self.assertNotIn("RAW_PRIVATE", result.error)


if __name__ == "__main__":
    unittest.main()
