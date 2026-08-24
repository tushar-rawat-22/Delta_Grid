"""Foreground command-line composition for Mission 97."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import sys
from typing import Any

from offchain.research.admission import canonical_json
from offchain.safety.operational_readiness_inspector import inspect_operational_readiness

from .ledger import WorkflowLedger
from .models import OrchestrationError
from .service import WorkflowOrchestrator


class _StableArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise OrchestrationError("WORKFLOW_INPUT_INVALID", message)


def _parser() -> argparse.ArgumentParser:
    parser = _StableArgumentParser(prog="python -m offchain.orchestration")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("--database", required=True)
    init.add_argument("--output-root", required=True)
    init.add_argument("--repository-root", required=True)
    init.add_argument("--created-at", required=True)

    create = commands.add_parser("create-observation-run")
    create.add_argument("--database", required=True)
    create.add_argument("--run-key", required=True)
    create.add_argument("--research-ledger", required=True)
    create.add_argument("--result-root", required=True)
    create.add_argument("--expected-repository-commit", required=True)
    create.add_argument("--observation-as-of", required=True)
    create.add_argument("--requested-at", required=True)
    create.add_argument("--requested-by", required=True)

    tick = commands.add_parser("tick")
    tick.add_argument("--database", required=True)
    tick.add_argument("--worker-id", required=True)
    tick.add_argument("--now", required=True)

    recover = commands.add_parser("recover")
    recover.add_argument("--database", required=True)
    recover.add_argument("--now", required=True)

    until = commands.add_parser("run-until-idle")
    until.add_argument("--database", required=True)
    until.add_argument("--worker-id", required=True)
    until.add_argument("--max-ticks", type=int, default=10000)
    until.add_argument("--now")

    status = commands.add_parser("status")
    status.add_argument("--database", required=True)
    status.add_argument("--run-id")
    status.add_argument(
        "--operational-readiness",
        action="store_true",
        help=(
            "Inspect persisted paper/risk/capital/kill-switch evidence read-only "
            "instead of opening an orchestration ledger."
        ),
    )

    cancel = commands.add_parser("cancel")
    cancel.add_argument("--database", required=True)
    cancel.add_argument("--run-id", required=True)
    cancel.add_argument("--at", required=True)
    cancel.add_argument("--reason", required=True)
    return parser


def _utc_now() -> str:
    value = datetime.now(timezone.utc)
    if value.microsecond:
        return (
            f"{value.strftime('%Y-%m-%dT%H:%M:%S')}."
            f"{value.microsecond:06d}".rstrip("0")
            + "Z"
        )
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(arguments: argparse.Namespace) -> Any:
    if arguments.command == "init":
        ledger = WorkflowLedger.initialize(
            database_path=arguments.database,
            output_root=arguments.output_root,
            governance_repository_root=arguments.repository_root,
            created_at=arguments.created_at,
        )
        return {
            "database": str(ledger.database_path),
            "metadata": ledger.metadata,
            "status": "INITIALIZED",
        }
    if arguments.command == "status" and arguments.operational_readiness:
        if arguments.run_id is not None:
            raise OrchestrationError(
                "WORKFLOW_INPUT_INVALID",
                "--run-id cannot be combined with --operational-readiness",
            )
        return inspect_operational_readiness(arguments.database)
    ledger = WorkflowLedger(arguments.database)
    service = WorkflowOrchestrator(ledger)
    if arguments.command == "create-observation-run":
        return service.create_run(
            run_key=arguments.run_key,
            research_ledger_path=arguments.research_ledger,
            result_root=arguments.result_root,
            expected_repository_commit=arguments.expected_repository_commit,
            observation_as_of=arguments.observation_as_of,
            requested_at=arguments.requested_at,
            requested_by=arguments.requested_by,
        ).as_dict()
    if arguments.command == "tick":
        return service.tick(arguments.worker_id, arguments.now).as_dict()
    if arguments.command == "recover":
        return {
            "recovered_runs": [
                item.as_dict()
                for item in service.recover_expired_claims(arguments.now)
            ]
        }
    if arguments.command == "run-until-idle":
        provider = (
            _utc_now if arguments.now is None else lambda: arguments.now
        )
        return {
            "outcomes": [
                item.as_dict()
                for item in service.run_until_idle(
                    arguments.worker_id, provider, arguments.max_ticks
                )
            ]
        }
    if arguments.command == "status":
        if arguments.run_id is not None:
            return service.get_run(arguments.run_id).as_dict()
        return {"runs": [item.as_dict() for item in service.list_runs()]}
    if arguments.command == "cancel":
        return service.cancel_run(
            arguments.run_id, arguments.at, arguments.reason
        ).as_dict()
    raise OrchestrationError("ACTION_NOT_AUTHORIZED")


def main(argv: list[str] | None = None) -> int:
    try:
        value = _run(_parser().parse_args(argv))
    except OrchestrationError as error:
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
        failure = OrchestrationError("INTERNAL_INTEGRITY_FAILURE")
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
    sys.stdout.write(canonical_json(value) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())