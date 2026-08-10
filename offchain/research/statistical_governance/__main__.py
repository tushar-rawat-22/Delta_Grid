"""Metadata-safe Mission 103 command line interface."""

from __future__ import annotations

import argparse
import json
import sys

from .core import MISSION103_PATH, GovernanceError, load_contracts, strict_json_load
from .registry import production_protected_evaluator_registry, production_statistical_adapter_registry
from .store import initialize_governance, inspect_governance


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise GovernanceError("CLI_ARGUMENT_INVALID")


def parser() -> argparse.ArgumentParser:
    root = _Parser(prog="python -m offchain.research.statistical_governance")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("show-contract")
    commands.add_parser("inspect-registries")
    inspect = commands.add_parser("inspect-state")
    inspect.add_argument("--governance-root", required=True)
    initialize = commands.add_parser("init-state")
    initialize.add_argument("--governance-root", required=True)
    initialize.add_argument("--acknowledgement", required=True)
    return root


def _run(args: argparse.Namespace) -> dict:
    if args.command == "show-contract":
        load_contracts()
        return strict_json_load(MISSION103_PATH)
    if args.command == "inspect-registries":
        statistical = production_statistical_adapter_registry()
        protected = production_protected_evaluator_registry()
        return {
            "statistical_adapter_registry": {**statistical.snapshot_core(), "snapshot_hash": statistical.snapshot_hash, "production_entry_count": statistical.entry_count},
            "protected_evaluator_registry": {**protected.snapshot_core(), "snapshot_hash": protected.snapshot_hash, "production_entry_count": protected.entry_count},
            "writes_performed": False,
        }
    if args.command == "inspect-state":
        return inspect_governance(args.governance_root)
    if args.command == "init-state":
        return initialize_governance(args.governance_root, acknowledgement=args.acknowledgement)
    raise GovernanceError("CLI_ARGUMENT_INVALID")


def main(argv: list[str] | None = None) -> int:
    try:
        result = _run(parser().parse_args(argv))
    except GovernanceError as error:
        print(json.dumps({"ok": False, "reason_token": error.reason}, sort_keys=True, separators=(",", ":")))
        return 2
    except Exception:
        print(json.dumps({"ok": False, "reason_token": "INTERNAL_INTEGRITY_FAILURE"}, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps({"ok": True, "result": result}, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
