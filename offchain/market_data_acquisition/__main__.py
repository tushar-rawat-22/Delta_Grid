"""Foreground-only Mission 100 operator CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .backup import ACK_BACKUP, export_backup, verify_backup
from .core import (
    AcquisitionError,
    AUTONOMY_V2_HASH,
    MISSION100_HASH,
    MISSION100_REMEDIATION_HASH,
    load_contracts,
)
from .journal import initialize_runtime, verify_journal
from .service import ACK_CAPTURE, capture_once


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m offchain.market_data_acquisition",
        description=(
            "Operate DeltaGrid Mission 100 forward public-market acquisition. "
            "This CLI has no strategy, account, credential, order, paper/live trading, or capital authority."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show-contract", help="Print controlling contract identities only.")

    init = sub.add_parser("init-runtime", help="Initialize a private Mission 100 runtime outside the checkout.")
    init.add_argument("--runtime-root", required=True)
    init.add_argument("--acknowledge", required=True)

    verify = sub.add_parser("verify-journal", help="Verify the acquisition journal and raw-object evidence.")
    verify.add_argument("--runtime-root", required=True)
    verify.add_argument("--skip-object-scan", action="store_true")

    capture = sub.add_parser("capture-once", help="Run one bounded public-market capture cycle and exit.")
    capture.add_argument("--runtime-root", required=True)
    capture.add_argument("--acknowledge", required=True)

    backup = sub.add_parser("export-backup", help="Export a verified local backup ZIP.")
    backup.add_argument("--runtime-root", required=True)
    backup.add_argument("--destination", required=True)
    backup.add_argument("--acknowledge", required=True)

    verify_backup_parser = sub.add_parser("verify-backup", help="Verify a Mission 100 backup ZIP.")
    verify_backup_parser.add_argument("--path", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "show-contract":
            load_contracts()
            print(
                _json(
                    {
                        "autonomy_v2_hash": AUTONOMY_V2_HASH,
                        "mission100_hash": MISSION100_HASH,
                        "mission100_activation_remediation_hash": MISSION100_REMEDIATION_HASH,
                    }
                )
            )
            return 0
        if args.command == "init-runtime":
            if args.acknowledge != "INITIALIZE_FORWARD_ACQUISITION_RUNTIME":
                raise AcquisitionError("INIT_ACKNOWLEDGEMENT_REQUIRED")
            print(_json(initialize_runtime(Path(args.runtime_root))))
            return 0
        if args.command == "verify-journal":
            print(_json(verify_journal(Path(args.runtime_root), scan_objects=not args.skip_object_scan)))
            return 0
        if args.command == "capture-once":
            result = capture_once(
                Path(args.runtime_root),
                acknowledgement=args.acknowledge,
            )
            print(_json(result.as_dict()))
            return 0
        if args.command == "export-backup":
            print(
                _json(
                    export_backup(
                        Path(args.runtime_root),
                        Path(args.destination),
                        acknowledgement=args.acknowledge,
                    )
                )
            )
            return 0
        if args.command == "verify-backup":
            print(_json(verify_backup(Path(args.path))))
            return 0
        raise AcquisitionError("COMMAND_UNREACHABLE")
    except AcquisitionError as error:
        print(_json({"status": "FAIL", "reason": error.reason}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
