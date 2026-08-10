"""Narrow operator CLI for Mission 102 development result execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .artifacts import verify_development_result
from .core import (
    ACK_EXECUTE,
    ACK_INITIALIZE_RESULTS,
    MISSION102_PATH,
    DevelopmentRuntimeError,
    load_contracts,
    strict_json_load,
)
from .registry import production_registry
from .runtime import initialize_result_runtime
from .service import execute_development_trial, inspect_development_results, plan_development_execution


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise DevelopmentRuntimeError("CLI_ARGUMENT_INVALID", message)


def _common(parser: argparse.ArgumentParser, *, result: bool = False) -> None:
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--trial-ledger", required=True)
    parser.add_argument("--authority-root", required=True)
    parser.add_argument("--dataset-descriptor", required=True)
    parser.add_argument("--custody-runtime", required=True)
    parser.add_argument("--release-directory", required=True)
    if result:
        parser.add_argument("--result-runtime", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m offchain.research.development_runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show-contract")
    sub.add_parser("inspect-experiment-registry")
    plan = sub.add_parser("plan-development-execution")
    _common(plan)
    initialize = sub.add_parser("init-development-results")
    initialize.add_argument("--result-runtime", required=True)
    initialize.add_argument("--acknowledgement", required=True)
    execute = sub.add_parser("execute-development-trial")
    _common(execute, result=True)
    execute.add_argument("--acknowledgement", required=True)
    verify = sub.add_parser("verify-development-result")
    _common(verify, result=True)
    inspect = sub.add_parser("inspect-development-results")
    inspect.add_argument("--result-runtime", required=True)
    return parser


def _descriptor(path: str) -> Any:
    return strict_json_load(Path(path))


def _run(arguments: argparse.Namespace) -> Any:
    registry = production_registry()
    if arguments.command == "show-contract":
        _autonomy, mission = load_contracts()
        return mission
    if arguments.command == "inspect-experiment-registry":
        return {**registry.snapshot_core(), "registry_snapshot_hash": registry.snapshot_hash, "production_family_count": registry.family_count, "writes_performed": False}
    if arguments.command == "init-development-results":
        return initialize_result_runtime(arguments.result_runtime, acknowledgement=arguments.acknowledgement)
    if arguments.command == "inspect-development-results":
        return inspect_development_results(arguments.result_runtime)
    common = {
        "trial_id": arguments.trial_id, "ledger_path": arguments.trial_ledger,
        "authority_root": arguments.authority_root,
        "descriptor": _descriptor(arguments.dataset_descriptor),
        "release_directory": arguments.release_directory,
        "custody_runtime_root": arguments.custody_runtime,
        "registry": registry,
    }
    if arguments.command == "plan-development-execution":
        return plan_development_execution(**common)
    if arguments.command == "execute-development-trial":
        return execute_development_trial(**common, result_runtime=arguments.result_runtime, acknowledgement=arguments.acknowledgement)
    if arguments.command == "verify-development-result":
        return verify_development_result(**common, result_runtime=arguments.result_runtime)
    raise DevelopmentRuntimeError("CLI_ARGUMENT_INVALID")


def main(argv: list[str] | None = None) -> int:
    try:
        result = _run(build_parser().parse_args(argv))
    except DevelopmentRuntimeError as error:
        print(json.dumps({"ok": False, "reason_token": error.reason}, sort_keys=True, separators=(",", ":")))
        return 2
    except Exception:
        print(json.dumps({"ok": False, "reason_token": "INTERNAL_INTEGRITY_FAILURE"}, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps({"ok": True, "result": result}, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
