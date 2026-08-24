"""Read-only operator entry point for DeltaGrid operational safety readiness."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .operational_readiness_inspector import inspect_operational_readiness


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m offchain.safety",
        description=(
            "Inspect persisted operational readiness evidence without starting paper, "
            "live, exchange, order, or capital machinery."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    readiness = commands.add_parser(
        "readiness",
        help="Return one fail-closed read-only operational readiness verdict.",
    )
    readiness.add_argument(
        "--database",
        required=True,
        help="Existing SQLite database containing persisted paper/risk/capital/kill-switch evidence.",
    )
    return parser


def _json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _internal_failure() -> dict[str, Any]:
    return {
        "inspection_status": "ERROR",
        "release": {
            "status": "BLOCKED",
            "ready_for_extended_paper": False,
        },
        "inspector_blockers": ["OPERATOR_CLI_INTERNAL_FAILURE"],
        "sources": {},
        "authority_effect": "NONE",
        "live_trading_allowed": False,
        "exchange_access_allowed": False,
        "capital_deployment_allowed": False,
        "database_mode": "READ_ONLY_QUERY_ONLY",
    }


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command != "readiness":
            raise RuntimeError("UNREACHABLE_COMMAND")
        result = inspect_operational_readiness(arguments.database)
        sys.stdout.write(_json(result) + "\n")
        return 0
    except Exception:
        sys.stdout.write(_json(_internal_failure()) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
