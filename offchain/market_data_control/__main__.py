"""Foreground, canonical-JSON operator CLI for Mission 99."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

from .certifier import certify_release
from .core import ControlPlaneError, canonical_json, deep_thaw, load_contracts
from .custody import (
    Catalogue,
    REPOSITORY_ROOT,
    audit_legacy,
    build_legacy_release,
    inspect_recovery,
    plan_legacy_release,
)
from .resolver import resolve_release


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ControlPlaneError("CLI_INPUT_INVALID", message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m offchain.market_data_control")
    commands = parser.add_subparsers(dest="command", required=True)

    show = commands.add_parser("show-contract")
    show.add_argument(
        "contract",
        choices=("autonomy", "mission99"),
        default="mission99",
        nargs="?",
    )

    init = commands.add_parser("init-runtime")
    init.add_argument("--runtime-root", required=True)
    init.add_argument("--acknowledge", required=True)

    audit = commands.add_parser("audit-legacy")
    audit.add_argument("--database", required=True)
    audit.add_argument("--mission86-root", required=True)
    audit.add_argument("--mission87-root", required=True)

    plan = commands.add_parser("plan-legacy-release")
    plan.add_argument("--database", required=True)
    plan.add_argument("--mission86-root", required=True)
    plan.add_argument("--mission87-root", required=True)

    build = commands.add_parser("build-legacy-release")
    build.add_argument("--runtime-root", required=True)
    build.add_argument("--database", required=True)
    build.add_argument("--mission86-root", required=True)
    build.add_argument("--mission87-root", required=True)
    build.add_argument("--acknowledge", required=True)

    certify = commands.add_parser("certify-release")
    certify.add_argument("--runtime-root", required=True)
    certify.add_argument("--release-id", required=True)

    recovery = commands.add_parser("inspect-recovery")
    recovery.add_argument("--runtime-root", required=True)

    resolve = commands.add_parser("resolve")
    resolve.add_argument("--runtime-root", required=True)
    resolve.add_argument("--release-id", required=True)
    resolve.add_argument("--decision-time", required=True)
    resolve.add_argument("--authorization-stage", required=True)
    return parser


def _catalogue(runtime_root: str) -> Catalogue:
    return Catalogue(runtime_root, repository_root=REPOSITORY_ROOT)


def _run(arguments: argparse.Namespace) -> Any:
    if arguments.command == "show-contract":
        autonomy, mission = load_contracts()
        return deep_thaw(autonomy if arguments.contract == "autonomy" else mission)
    if arguments.command == "init-runtime":
        catalogue = Catalogue.initialize(
            arguments.runtime_root,
            repository_root=REPOSITORY_ROOT,
            acknowledgement=arguments.acknowledge,
        )
        return {
            "status": "INITIALIZED",
            "runtime_root": str(catalogue.runtime_root),
            "catalogue": "catalogue.sqlite3",
        }
    if arguments.command == "audit-legacy":
        return audit_legacy(
            database_path=arguments.database,
            mission86_root=arguments.mission86_root,
            mission87_root=arguments.mission87_root,
        ).as_dict()
    if arguments.command == "plan-legacy-release":
        return deep_thaw(
            plan_legacy_release(
                database_path=arguments.database,
                mission86_root=arguments.mission86_root,
                mission87_root=arguments.mission87_root,
            )
        )
    if arguments.command == "build-legacy-release":
        return deep_thaw(
            build_legacy_release(
                catalogue=_catalogue(arguments.runtime_root),
                database_path=arguments.database,
                mission86_root=arguments.mission86_root,
                mission87_root=arguments.mission87_root,
                execution_acknowledgement=arguments.acknowledge,
            )
        )
    if arguments.command == "certify-release":
        catalogue = _catalogue(arguments.runtime_root)
        record = catalogue.release(arguments.release_id)
        certificate = certify_release(
            catalogue.runtime_root / record["relative_path"],
            runtime_root=catalogue.runtime_root,
        )
        if (
            certificate.release_id != arguments.release_id
            or certificate.release_core_hash != record["release_core_hash"]
            or certificate.certificate_core_hash != record["certificate_core_hash"]
        ):
            raise ControlPlaneError("CATALOGUE_RELEASE_DISAGREEMENT")
        return certificate.as_dict()
    if arguments.command == "inspect-recovery":
        return {
            "states": [deep_thaw(item) for item in inspect_recovery(arguments.runtime_root)]
        }
    if arguments.command == "resolve":
        return resolve_release(
            _catalogue(arguments.runtime_root),
            arguments.release_id,
            arguments.decision_time,
            arguments.authorization_stage,
        ).as_dict()
    raise ControlPlaneError("CLI_INPUT_INVALID")


def main(argv: list[str] | None = None) -> int:
    try:
        result = _run(_parser().parse_args(argv))
    except ControlPlaneError as error:
        # CLI failures expose stable reason codes only. Internal explanations may
        # contain local paths or evidence identities and are intentionally not
        # printed at the operator boundary.
        sys.stderr.write(canonical_json({"reason": error.reason}) + "\n")
        return 2
    except Exception:
        sys.stderr.write(
            canonical_json({"reason": "INTERNAL_INTEGRITY_FAILURE"}) + "\n"
        )
        return 2
    sys.stdout.write(canonical_json(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
