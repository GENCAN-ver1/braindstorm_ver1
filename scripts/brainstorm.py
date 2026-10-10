#!/usr/bin/env python3
"""One-command entrypoint for the brainstorm-governor full-cycle runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.config_loader import ConfigError, load_config  # noqa: E402
from runtime.full_cycle import (  # noqa: E402
    FullCycleRunner,
    RequestError,
    p0,
    request_from_dict,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    storm_parser = subparsers.add_parser("storm", help="open exploration graph and optional model Council")
    storm_parser.add_argument("storm_args", nargs=argparse.REMAINDER)
    run_parser = subparsers.add_parser("run", help="run to a legal stop or COMMIT")
    run_parser.add_argument(
        "--request",
        default="-",
        help="request JSON path; use '-' or omit for stdin",
    )
    run_parser.add_argument("--config", required=True, help="runtime config path")
    run_parser.add_argument(
        "--brief",
        help="Living Brief path override; relative paths use the current directory",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    effective_argv = list(argv) if argv is not None else sys.argv[1:]
    if effective_argv and effective_argv[0] == "storm":
        from scripts.open_storm import main as storm_main
        return storm_main(effective_argv[1:])
    args = build_parser().parse_args(argv)
    try:
        if args.command != "run":
            raise RequestError(f"unsupported command: {args.command}")
        config_path = Path(args.config).resolve()
        config = load_config(config_path)
        request = request_from_dict(_load_json(args.request))
        summary = FullCycleRunner(
            config,
            config_base_dir=config_path.parent,
        ).run(request, brief_path=args.brief)
        _emit(summary.to_dict())
        return 0
    except (ConfigError, RequestError, p0.ContractError) as exc:
        _emit({"valid": False, "error": str(exc)})
        return 2
    except (OSError, UnicodeError) as exc:
        _emit({"valid": False, "error": str(exc)})
        return 1


def _load_json(source: str) -> Any:
    try:
        if source == "-":
            return json.load(sys.stdin)
        return json.loads(Path(source).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError) as exc:
        raise RequestError(f"invalid request JSON: {exc}") from exc
    except (OSError, UnicodeError) as exc:
        raise RequestError(f"cannot read request {source}: {exc}") from exc


def _emit(value: Any) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
