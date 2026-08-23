from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path

from scripts.run_diet_app_council import (
    DEFAULT_CONFIG,
    DEFAULT_EVIDENCE,
    DEFAULT_REQUEST,
    evidence_from_document,
    execute_diet_council,
    prepare_diet_member_requests,
)
from p5_council import CouncilMemberResult, CouncilProvider, CouncilUsage, runtime_config_from_dict


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def valid_output(provider: CouncilProvider) -> dict[str, object]:
    return {
        "verdict": "REFINE",
        "strongest_case": f"strongest case from {provider.value}",
        "fatal_risks": [],
        "repairable_risks": ["photo estimate needs confirmation"],
        "recommendation": "run a behavior-focused one-week prototype",
        "decisive_uncertainties": ["acceptable suggestion error"],
        "one_week_validation": {
            "hypothesis": "next-meal guidance lowers decision cost",
            "method": "seven-day assisted prototype",
            "pass_signal": "reported decision-cost reduction",
            "fail_signal": "neither continued-use intent nor lower decision cost",
        },
        "evidence_used": ["e3-photo-portions-need-confirmation"],
    }


class ConcurrentAdapter:
    barrier = threading.Barrier(2)
    invoked: list[CouncilProvider] = []
    lock = threading.Lock()

    def invoke(self, config, request):
        with self.lock:
            self.invoked.append(request.provider)
        self.barrier.wait(timeout=2)
        return CouncilMemberResult(
            member_id=request.member_id,
            provider=request.provider,
            model=config.model,
            success=True,
            output=valid_output(request.provider),
            usage=CouncilUsage(40, 20, 60),
        )


class OneFailureAdapter:
    def invoke(self, config, request):
        if request.provider is CouncilProvider.KIMI:
            return CouncilMemberResult(
                member_id=request.member_id,
                provider=request.provider,
                model=config.model,
                success=False,
                output=None,
                error="provider request failed",
            )
        return CouncilMemberResult(
            member_id=request.member_id,
            provider=request.provider,
            model=config.model,
            success=True,
            output=valid_output(request.provider),
        )


class DietCouncilRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = runtime_config_from_dict(load(DEFAULT_CONFIG))
        cls.request = load(DEFAULT_REQUEST)
        cls.evidence = load(DEFAULT_EVIDENCE)

    def setUp(self) -> None:
        ConcurrentAdapter.barrier = threading.Barrier(2)
        ConcurrentAdapter.invoked = []

    def test_prepares_two_distinct_peer_isolated_provider_requests(self) -> None:
        requests = prepare_diet_member_requests(
            self.config, self.request, self.evidence
        )

        self.assertEqual(len(requests), 2)
        self.assertEqual(
            {item.provider for item in requests},
            {CouncilProvider.DEEPSEEK, CouncilProvider.KIMI},
        )
        self.assertNotEqual(
            requests[0].assigned_dimension, requests[1].assigned_dimension
        )
        requests[0].shared_frame["confirmed_candidate"]["title"] = "local mutation"
        self.assertNotEqual(
            requests[1].shared_frame["confirmed_candidate"]["title"],
            "local mutation",
        )
        self.assertFalse(any("peer" in item.shared_frame for item in requests))

    def test_multisource_evidence_is_joined_and_remains_data_only(self) -> None:
        evidence = evidence_from_document(self.evidence)
        competitor = next(item for item in evidence if item.id == "e5-current-competitor-overlap")

        self.assertEqual(len(evidence), 5)
        self.assertEqual(competitor.treatment, "DATA_ONLY")
        self.assertIn("myfitnesspal.com", competitor.source)
        self.assertIn("lifesum.com", competitor.source)
        self.assertIn("macrofactorapp.com", competitor.source)
        self.assertIn(" | ", competitor.source)

    def test_dispatches_both_members_concurrently_then_admits_council(self) -> None:
        result = execute_diet_council(
            self.config,
            self.request,
            self.evidence,
            adapter_factory=ConcurrentAdapter,
        )

        self.assertEqual(result["status"], "COUNCIL_MEMBERS_READY_FOR_SYNTHESIS")
        self.assertEqual(result["council_label"], "COUNCIL")
        self.assertEqual(len(result["successful_member_ids"]), 2)
        self.assertEqual(
            set(ConcurrentAdapter.invoked),
            {CouncilProvider.DEEPSEEK, CouncilProvider.KIMI},
        )
        self.assertTrue(all(item["success"] for item in result["member_results"]))
        self.assertTrue(
            all(item["usage"]["total_tokens"] == 60 for item in result["member_results"])
        )

    def test_one_provider_failure_cannot_be_labeled_council(self) -> None:
        result = execute_diet_council(
            self.config,
            self.request,
            self.evidence,
            adapter_factory=OneFailureAdapter,
        )

        self.assertEqual(result["status"], "INSUFFICIENT_SUCCESS")
        self.assertEqual(result["council_label"], "NOT_COUNCIL")
        self.assertEqual(len(result["successful_member_ids"]), 1)
        self.assertIn("fewer than", result["admission_error"])


if __name__ == "__main__":
    unittest.main()
