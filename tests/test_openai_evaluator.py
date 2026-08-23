from __future__ import annotations

import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from adapters.openai_evaluator import (
    OpenAICompatibleEvaluatorAdapter,
    OpenAICompatibleEvaluatorConfig,
    OpenAICompatibleObservedEvaluatorAdapter,
    OpenAIEvaluatorError,
)
from observability.usage_ledger import ObservedExternalResult
from runtime.governor_modules import p6


class FakeResponse:
    def __init__(self, value: dict[str, object]) -> None:
        self.body = json.dumps(value).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


class OpenAICompatibleEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = OpenAICompatibleEvaluatorConfig(
            base_url="https://provider.example/v1",
            model="evaluator-model",
            credential_env="TEST_EVALUATOR_KEY",
            timeout_seconds=9,
            max_output_tokens=512,
            provider_options={"temperature": 0},
        )
        self.request = p6.EvaluatorInput(
            confirmed_frame={"problem": "reduce meal decision cost"},
            candidates=[{"id": "c2", "mechanism": "adaptive meal coach"}],
            recommendation={"candidate_id": "c2", "confidence": 0.58},
            evaluation_criteria=list(p6.REQUIRED_EVALUATION_CRITERIA),
            evidence_summary=[
                p6.EvidenceSummaryItem(
                    id="e1",
                    claim="portion estimates need confirmation",
                    source="https://example/e1",
                    evidence_strength="MODERATE",
                    contradictions=[],
                )
            ],
            output_contract={"required": ["recommendation", "cheapest_test"]},
        )

    @staticmethod
    def correction() -> dict[str, object]:
        return {
            "id": "q1",
            "check": "CHEAPEST_TEST_FALSIFIABILITY",
            "target": "recommendation.cheapest_test",
            "issue": "The test has no falsification threshold.",
            "required_change": "Add a numeric pass/fail threshold for week one.",
            "severity": "MEDIUM",
            "high_impact": True,
            "wording_only": False,
            "requires_external_information": False,
            "requires_user_information": False,
        }

    def test_success_posts_only_six_fields_and_returns_p6_invocation(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(http_request, timeout):
            captured["request"] = http_request
            captured["timeout"] = timeout
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps([self.correction()])
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 80,
                        "completion_tokens": 20,
                        "total_tokens": 100,
                    },
                    "raw_vendor_field": "must not escape",
                }
            )

        with patch.dict(
            os.environ, {"TEST_EVALUATOR_KEY": "secret-at-call-time"}
        ):
            with patch(
                "adapters.openai_evaluator.urlopen", side_effect=fake_urlopen
            ):
                result = OpenAICompatibleEvaluatorAdapter(self.config).evaluate(
                    self.request
                )

        self.assertIsInstance(result, p6.EvaluatorInvocation)
        self.assertEqual(len(result.report.corrections), 1)
        self.assertEqual(result.report.corrections[0].id, "q1")
        self.assertEqual(result.usage.token_usage, 100)
        self.assertIsNone(result.usage.tool_usage)
        self.assertFalse(hasattr(result, "raw_vendor_field"))

        http_request = captured["request"]
        self.assertEqual(
            http_request.full_url,
            "https://provider.example/v1/chat/completions",
        )
        self.assertEqual(
            http_request.get_header("Authorization"),
            "Bearer secret-at-call-time",
        )
        self.assertEqual(captured["timeout"], 9)
        body = json.loads(http_request.data.decode("utf-8"))
        self.assertEqual(body["model"], "evaluator-model")
        self.assertEqual(body["max_tokens"], 512)
        self.assertFalse(body["stream"])
        self.assertIn("ActionableCorrection[]", body["messages"][0]["content"])
        evaluator_payload = json.loads(body["messages"][1]["content"])
        self.assertEqual(
            set(evaluator_payload),
            {
                "confirmed_frame",
                "candidates",
                "recommendation",
                "evaluation_criteria",
                "evidence_summary",
                "output_contract",
            },
        )
        self.assertEqual(
            evaluator_payload["evidence_summary"][0]["treatment"],
            "DATA_ONLY",
        )

    def test_observed_adapter_preserves_provider_reported_usage(self) -> None:
        response = FakeResponse(
            {
                "id": "provider-request-1",
                "choices": [{"message": {"content": "[]"}}],
                "usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 20,
                    "total_tokens": 100,
                    "cached_tokens": 10,
                },
            }
        )
        with patch.dict(os.environ, {"TEST_EVALUATOR_KEY": "key"}):
            with patch(
                "adapters.openai_evaluator.urlopen", return_value=response
            ):
                result = OpenAICompatibleObservedEvaluatorAdapter(
                    self.config
                ).evaluate(self.request)

        self.assertIsInstance(result, ObservedExternalResult)
        self.assertEqual(result.payload.report.corrections, [])
        self.assertEqual(result.usage.request_id, "provider-request-1")
        self.assertEqual(result.usage.prompt_tokens, 80)
        self.assertEqual(result.usage.completion_tokens, 20)
        self.assertEqual(result.usage.cached_tokens, 10)

    def test_credential_is_resolved_only_at_evaluate_time(self) -> None:
        adapter = OpenAICompatibleEvaluatorAdapter(self.config)
        response = FakeResponse(
            {"choices": [{"message": {"content": "[]"}}]}
        )
        with patch.dict(os.environ, {}, clear=True):
            os.environ["TEST_EVALUATOR_KEY"] = "added-later"
            with patch(
                "adapters.openai_evaluator.urlopen", return_value=response
            ) as call:
                result = adapter.evaluate(self.request)

        self.assertEqual(result.report.corrections, [])
        self.assertEqual(
            call.call_args.args[0].get_header("Authorization"),
            "Bearer added-later",
        )

    def test_missing_credential_is_safe_and_skips_network(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("adapters.openai_evaluator.urlopen") as call:
                with self.assertRaisesRegex(
                    OpenAIEvaluatorError, "TEST_EVALUATOR_KEY"
                ):
                    OpenAICompatibleEvaluatorAdapter(self.config).evaluate(
                        self.request
                    )
        call.assert_not_called()

    def test_http_error_does_not_expose_secret_or_error_body(self) -> None:
        error = HTTPError(
            "https://provider.example/v1/chat/completions",
            401,
            "TOP_SECRET provider detail",
            hdrs=None,
            fp=io.BytesIO(b"RAW_TOP_SECRET_BODY"),
        )
        with patch.dict(os.environ, {"TEST_EVALUATOR_KEY": "secret-key"}):
            with patch("adapters.openai_evaluator.urlopen", side_effect=error):
                with self.assertRaises(OpenAIEvaluatorError) as caught:
                    OpenAICompatibleEvaluatorAdapter(self.config).evaluate(
                        self.request
                    )

        self.assertEqual(
            str(caught.exception),
            "provider HTTP request failed with status 401",
        )
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertNotIn("RAW", str(caught.exception))

    def test_invalid_provider_content_raises_only_generic_error(self) -> None:
        response = FakeResponse(
            {
                "choices": [
                    {"message": {"content": "RAW_PRIVATE_RESPONSE_NOT_JSON"}}
                ]
            }
        )
        with patch.dict(os.environ, {"TEST_EVALUATOR_KEY": "key"}):
            with patch(
                "adapters.openai_evaluator.urlopen", return_value=response
            ):
                with self.assertRaises(OpenAIEvaluatorError) as caught:
                    OpenAICompatibleEvaluatorAdapter(self.config).evaluate(
                        self.request
                    )

        self.assertEqual(str(caught.exception), "provider response was invalid")
        self.assertNotIn("RAW_PRIVATE", str(caught.exception))

    def test_usage_is_null_when_missing_or_inconsistent(self) -> None:
        responses = [
            FakeResponse({"choices": [{"message": {"content": "[]"}}]}),
            FakeResponse(
                {
                    "choices": [{"message": {"content": "```json\n[]\n```"}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 2,
                    },
                }
            ),
        ]
        adapter = OpenAICompatibleEvaluatorAdapter(self.config)
        with patch.dict(os.environ, {"TEST_EVALUATOR_KEY": "key"}):
            with patch(
                "adapters.openai_evaluator.urlopen", side_effect=responses
            ):
                missing = adapter.evaluate(self.request)
                inconsistent = adapter.evaluate(self.request)

        self.assertIsNone(missing.usage.token_usage)
        self.assertIsNone(inconsistent.usage.token_usage)

    def test_invalid_correction_is_rejected_without_returning_raw_content(self) -> None:
        invalid = self.correction()
        invalid["target"] = "recommendation"
        response = FakeResponse(
            {
                "choices": [
                    {"message": {"content": json.dumps([invalid])}}
                ]
            }
        )
        with patch.dict(os.environ, {"TEST_EVALUATOR_KEY": "key"}):
            with patch(
                "adapters.openai_evaluator.urlopen", return_value=response
            ):
                with self.assertRaises(OpenAIEvaluatorError) as caught:
                    OpenAICompatibleEvaluatorAdapter(self.config).evaluate(
                        self.request
                    )

        self.assertEqual(str(caught.exception), "provider response was invalid")
        self.assertNotIn("recommendation", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
