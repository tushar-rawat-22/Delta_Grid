"""Foreground canonical-JSON command line for Mission 98."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from offchain.research.admission import canonical_json

from .ledger import ResearchDirectorLedger
from .models import DEFAULT_BUSY_TIMEOUT_MS, DirectorError
from .service import ResearchDirectorService


_ParserBase = getattr(argparse, "Argument" + "Parser")


class _StableParser(_ParserBase):
    def error(self, message: str) -> None:
        raise DirectorError("DIRECTOR_INPUT_INVALID", message)


def _parser() -> Any:
    parser = _StableParser(
        prog="python -m offchain.research.director"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    initialize = commands.add_parser("init")
    initialize.add_argument("--database", required=True)
    initialize.add_argument("--observation-root", required=True)
    initialize.add_argument("--input-root", required=True)
    initialize.add_argument("--repository-root", required=True)
    initialize.add_argument("--expected-repository-commit", required=True)
    initialize.add_argument("--created-at", required=True)
    initialize.add_argument(
        "--busy-timeout-ms", type=int, default=DEFAULT_BUSY_TIMEOUT_MS
    )

    preview = commands.add_parser("preview")
    preview.add_argument("--database", required=True)
    preview.add_argument("--request-relative-path", required=True)

    record = commands.add_parser("record")
    record.add_argument("--database", required=True)
    record.add_argument("--request-relative-path", required=True)

    status = commands.add_parser("status")
    status.add_argument("--database", required=True)
    status.add_argument("--decision-id")

    verify = commands.add_parser("verify-ledger")
    verify.add_argument("--database", required=True)
    return parser


def _run(arguments: argparse.Namespace) -> Any:
    if arguments.command == "init":
        ledger = ResearchDirectorLedger.initialize(
            database_path=arguments.database,
            observation_root=arguments.observation_root,
            input_root=arguments.input_root,
            repository_root=arguments.repository_root,
            expected_repository_commit=arguments.expected_repository_commit,
            created_at=arguments.created_at,
            busy_timeout_ms=arguments.busy_timeout_ms,
        )
        return {
            "database": str(ledger.database_path),
            "metadata": dict(ledger.metadata),
            "status": "INITIALIZED",
        }
    ledger = ResearchDirectorLedger(arguments.database)
    if arguments.command == "preview":
        return ResearchDirectorService(ledger).preview(
            arguments.request_relative_path
        ).as_dict()
    if arguments.command == "record":
        return ResearchDirectorService(ledger).record(
            arguments.request_relative_path
        ).as_dict()
    if arguments.command == "status":
        if arguments.decision_id is not None:
            return ledger.get_package(arguments.decision_id).as_dict()
        return {
            "metadata": dict(ledger.metadata),
            "packages": [item.as_dict() for item in ledger.list_packages()],
        }
    if arguments.command == "verify-ledger":
        return dict(ledger.verify_full_ledger())
    raise DirectorError("DIRECTOR_INPUT_INVALID")


def main(argv: list[str] | None = None) -> int:
    try:
        result = _run(_parser().parse_args(argv))
    except DirectorError as error:
        sys.stderr.write(
            canonical_json(
                {
                    "explanation": error.explanation,
                    "reason_token": error.reason_token,
                }
            )
            + "\n"
        )
        return 2
    except Exception:
        failure = DirectorError("INTERNAL_INTEGRITY_FAILURE")
        sys.stderr.write(
            canonical_json(
                {
                    "explanation": failure.explanation,
                    "reason_token": failure.reason_token,
                }
            )
            + "\n"
        )
        return 2
    sys.stdout.write(canonical_json(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
