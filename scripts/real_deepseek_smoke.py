#!/usr/bin/env python3
"""Run one sanitized end-to-end DeepSeek P1 + P6 smoke through the web host."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web_host.service import BrainstormService, ServiceError  # noqa: E402


def _frames() -> dict[str, object]:
    values = {
        "target_user": "需要把模糊产品想法收敛为可验证方案的小型产品团队",
        "core_task": "比较机制不同的候选方案并保留明确权衡",
        "desired_change": "在人工确认前得到可审查的推荐与最便宜验证实验",
        "hard_constraints": ["不得把模型推断表述为外部事实", "必须经过 Human Gate"],
        "success_metrics": ["至少三个机制不同的候选通过 Governor schema"],
        "abandonment_criteria": ["没有候选满足硬约束"],
        "non_goals": ["外部事实研究", "多 Provider Council", "生产部署"],
        "validation_horizon": "一周内完成最便宜的验证实验",
    }
    return {
        key: {"value": value, "status": "KNOWN", "source": "user"}
        for key, value in values.items()
    }


def run(session_root: Path, *, stop_after_p1: bool = False) -> dict[str, object]:
    service = BrainstormService(session_root)
    created = service.create_session(
        {
            "idea": "为团队提供一个结构化、可恢复、有质量门的头脑风暴 Web Host",
            "mode": "Spark",
            "frames": _frames(),
        }
    )
    reviewed = service.start_run(created["id"], created["revision"])
    if stop_after_p1:
        stored = service.store.load(created["id"])
        return {
            "status": reviewed["governorStatus"],
            "session_id": created["id"],
            "model": (reviewed.get("review") or {}).get("model"),
            "provider_calls": len(stored.get("usage", [])),
            "usage": stored.get("usage", []),
            "handoff_available": False,
        }
    committed = service.submit_human_gate(
        reviewed["id"], reviewed["revision"], {"kind": "confirm"}
    )
    stored = service.store.load(created["id"])
    return {
        "status": committed["governorStatus"],
        "session_id": created["id"],
        "model": (reviewed.get("review") or {}).get("model"),
        "provider_calls": len(stored.get("usage", [])),
        "usage": [
            {
                "request_id": item.get("request_id"),
                "prompt_tokens": item.get("prompt_tokens"),
                "completion_tokens": item.get("completion_tokens"),
                "total_tokens": item.get("total_tokens"),
                "latency_ms": item.get("latency_ms"),
            }
            for item in stored.get("usage", [])
        ],
        "handoff_available": service.get_handoff(created["id"]) is not None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-root",
        type=Path,
        default=PROJECT_ROOT / "var" / "real-smoke" / "sessions",
    )
    parser.add_argument("--stop-after-p1", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run(args.session_root.resolve(), stop_after_p1=args.stop_after_p1)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        expected_status = "ITERATE" if args.stop_after_p1 else "COMMIT"
        return 0 if result["status"] == expected_status else 2
    except ServiceError as exc:
        print(json.dumps({"status": "ERROR", "code": exc.code, "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
