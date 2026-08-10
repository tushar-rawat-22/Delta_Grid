"""Foreground-only CLI for DeltaGrid public projection export and verification."""

from __future__ import annotations

import argparse
import sys

from offchain.market_data_acquisition.core import canonical_json

from .core import CONTRACT_HASH, CONTRACT_ID, ProjectionError, load_contracts
from .exporter import export_projection
from .verifier import verify_projection_package


def _print(value: object, *, stream: object = sys.stdout) -> None:
    print(canonical_json(value), file=stream)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m offchain.public_projection",
        description=(
            "Export or verify DeltaGrid's deterministic repository-only public projection. "
            "This CLI has no private-runtime, market-value, network, research, trading, order, or capital authority."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show-contract", help="Print the controlling public-projection contract identity.")

    export = sub.add_parser("export", help="Write one deterministic public projection package.")
    export.add_argument("--destination", required=True)

    verify = sub.add_parser("verify", help="Verify a projection package against the current clean repository.")
    verify.add_argument("--path", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "show-contract":
            load_contracts()
            _print({"contract_id": CONTRACT_ID, "contract_hash_sha256": CONTRACT_HASH, "authority_effect": "NONE"})
            return 0
        if args.command == "export":
            _print(export_projection(args.destination))
            return 0
        if args.command == "verify":
            _print(verify_projection_package(args.path))
            return 0
        raise ProjectionError("COMMAND_UNREACHABLE")
    except ProjectionError as error:
        _print({"verdict": "FAIL", "reason": error.reason}, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
