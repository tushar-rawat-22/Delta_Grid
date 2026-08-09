"""Foreground, canonical-JSON Mission 101 operator boundary."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from offchain.research.admission.models import AdmissionError

from .admission import (
    ACK_ADMIT_DEVELOPMENT,
    ACK_REGISTER_BUDGET,
    DevelopmentAdmissionService,
    build_admission_request,
    open_development_trial_ledger,
    register_development_budget,
)
from .authority import (
    ACK_INITIALIZE_AUTHORITY,
    ACK_ISSUE_PERMIT,
    ACK_REVOKE_PERMIT,
    initialize_authority_runtime,
    inspect_authority_runtime,
    issue_development_permit,
    revoke_development_permit,
    verify_development_permit,
)
from .bridge import inspect_backup_compatibility
from .core import (
    ReopeningError,
    canonical_json,
    deep_thaw,
    get_repository_observation,
    load_contracts,
)
from .custody import (
    ACK_BUILD_RELEASE,
    build_forward_release,
    certify_forward_release,
    plan_forward_release,
)
from .dataset import (
    ACK_WRITE_DESCRIPTOR,
    build_development_dataset_descriptor,
    verify_development_dataset_descriptor,
    write_development_dataset_descriptor,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ReopeningError("CLI_INPUT_INVALID", message)


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("positive integer required") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("positive integer required")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="python -m offchain.research.reopening",
        description=(
            "Operate Mission 101 custody, exact development datasets, finite permits, "
            "and metadata-only admission. Result-bearing research is unavailable."
        ),
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    commands.add_parser("show-contract", help="Show controlling identities and closed authority state.", allow_abbrev=False)

    verify_backup = commands.add_parser("verify-backup-source", help="Verify backup evidence and report compatibility metadata.", allow_abbrev=False)
    verify_backup.add_argument("--backup", required=True)

    plan = commands.add_parser("plan-forward-custody-release", help="Plan a deterministic release without publishing it.", allow_abbrev=False)
    plan.add_argument("--backup", required=True)

    certify = commands.add_parser("certify-forward-custody-release", help="Independently certify persisted release bytes.", allow_abbrev=False)
    certify.add_argument("--runtime-root", required=True)
    certify.add_argument("--release-directory", required=True)

    verify_dataset = commands.add_parser("verify-development-dataset", help="Verify an exact immutable development descriptor.", allow_abbrev=False)
    verify_dataset.add_argument("--descriptor", required=True)
    verify_dataset.add_argument("--custody-runtime-root", required=True)
    verify_dataset.add_argument("--release-directory", required=True)

    verify_permit = commands.add_parser("verify-development-permit", help="Read-only historical verification of one existing permit as of an explicit time.", allow_abbrev=False)
    verify_permit.add_argument("--authority-root", required=True)
    verify_permit.add_argument("--permit-id", required=True)
    verify_permit.add_argument("--descriptor", required=True)
    verify_permit.add_argument("--custody-runtime-root", required=True)
    verify_permit.add_argument("--release-directory", required=True)
    verify_permit.add_argument("--repository-commit", required=True)
    verify_permit.add_argument("--experiment-family", required=True)
    verify_permit.add_argument("--authorization-stage", required=True)
    verify_permit.add_argument("--as-of", required=True)

    inspect_authority = commands.add_parser("inspect-authority-runtime", help="Inspect bounded permit metadata and append-only status.", allow_abbrev=False)
    inspect_authority.add_argument("--authority-root", required=True)

    build = commands.add_parser("build-forward-custody-release", help="Publish from one immutable verified backup.", allow_abbrev=False)
    build.add_argument("--backup", required=True)
    build.add_argument("--runtime-root", required=True)
    build.add_argument("--acknowledge", required=True)

    create_dataset = commands.add_parser("create-development-dataset", help="Create one exact REAL_MARKET_DEVELOPMENT descriptor.", allow_abbrev=False)
    create_dataset.add_argument("--custody-runtime-root", required=True)
    create_dataset.add_argument("--release-directory", required=True)
    create_dataset.add_argument("--destination", required=True)
    create_dataset.add_argument("--symbol", action="append", required=True, choices=("BTCUSDT", "ETHUSDT", "SOLUSDT"))
    create_dataset.add_argument("--stream", action="append", required=True, choices=("spot_ohlcv", "perpetual_ohlcv", "mark_price_ohlcv", "index_price_ohlcv", "funding_rates"))
    create_dataset.add_argument("--temporal-start", required=True)
    create_dataset.add_argument("--temporal-end-as-of", required=True)
    create_dataset.add_argument("--causal-availability-cutoff", required=True)
    create_dataset.add_argument("--provenance-reference", required=True)
    create_dataset.add_argument("--acknowledge", required=True)

    init_authority = commands.add_parser("init-research-authority-runtime", help="Initialize an explicitly supplied private authority runtime.", allow_abbrev=False)
    init_authority.add_argument("--authority-root", required=True)
    init_authority.add_argument("--acknowledge", required=True)

    issue = commands.add_parser("issue-development-permit", help="Issue one finite exact development permit.", allow_abbrev=False)
    issue.add_argument("--authority-root", required=True)
    issue.add_argument("--descriptor", required=True)
    issue.add_argument("--custody-runtime-root", required=True)
    issue.add_argument("--release-directory", required=True)
    issue.add_argument("--experiment-family", required=True)
    issue.add_argument("--fixed-trial-budget", required=True, type=_positive_integer)
    issue.add_argument("--expires-at", required=True)
    issue.add_argument("--acknowledge", required=True)

    revoke = commands.add_parser("revoke-development-permit", help="Append one permanent founder permit revocation.", allow_abbrev=False)
    revoke.add_argument("--authority-root", required=True)
    revoke.add_argument("--permit-id", required=True)
    revoke.add_argument("--acknowledge", required=True)

    budget = commands.add_parser("register-development-budget", help="Register the Mission 94 ledger budget required by Admission V2.", allow_abbrev=False)
    budget.add_argument("--trial-ledger", required=True)
    budget.add_argument("--budget-id", required=True)
    budget.add_argument("--experiment-family", required=True)
    budget.add_argument("--total-trial-budget", required=True, type=_positive_integer)
    budget.add_argument("--created-at", required=True)
    budget.add_argument("--acknowledge", required=True)

    admit = commands.add_parser("admit-development", help="Reserve metadata-only Admission V2 and stop before execution.", allow_abbrev=False)
    admit.add_argument("--trial-ledger", required=True)
    admit.add_argument("--authority-root", required=True)
    admit.add_argument("--descriptor", required=True)
    admit.add_argument("--custody-runtime-root", required=True)
    admit.add_argument("--release-directory", required=True)
    admit.add_argument("--request-id", required=True)
    admit.add_argument("--budget-id", required=True)
    admit.add_argument("--declared-trial-number", required=True, type=_positive_integer)
    admit.add_argument("--dataset-id", required=True)
    admit.add_argument("--dataset-descriptor-hash", required=True)
    admit.add_argument("--data-class", required=True)
    admit.add_argument("--split-identity", required=True)
    admit.add_argument("--permit-id", required=True)
    admit.add_argument("--permit-hash", required=True)
    admit.add_argument("--experiment-family", required=True)
    admit.add_argument("--authorization-stage", required=True)
    admit.add_argument("--initiated-by", required=True)
    admit.add_argument("--created-at", required=True)
    admit.add_argument("--acknowledge", required=True)
    return parser


def _dataset_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": value["schema_version"],
        "dataset_id": value["dataset_id"],
        "canonical_descriptor_hash": value["canonical_descriptor_hash"],
        "source_forward_custody_release_id": value["source_forward_custody_release_id"],
        "release_core_hash": value["release_core_hash"],
        "release_certificate_hash": value["release_certificate_hash"],
        "data_class": value["data_class"],
        "split_identity": value["split_identity"],
        "provider": value["provider"],
        "allowed_symbols": value["allowed_symbols"],
        "allowed_streams": value["allowed_streams"],
        "stream_intervals": value["stream_intervals"],
        "temporal_start": value["temporal_start"],
        "temporal_end_as_of": value["temporal_end_as_of"],
        "causal_availability_cutoff": value["causal_availability_cutoff"],
        "selected_record_set_hash": value["selected_record_set_hash"],
        "selected_record_count": value["selected_record_count"],
        "metadata_safe": True,
    }


def _run(arguments: argparse.Namespace) -> Any:
    if arguments.command == "show-contract":
        autonomy, mission = load_contracts()
        authority = deep_thaw(mission["authority"])
        return {
            "schema_version": "1.0",
            "autonomy_v3": {"contract_id": autonomy["contract_id"], "contract_hash_sha256": autonomy["contract_hash_sha256"]},
            "mission101": {"contract_id": mission["contract_id"], "contract_hash_sha256": mission["contract_hash_sha256"]},
            "authority": authority,
        }
    if arguments.command == "verify-backup-source":
        return inspect_backup_compatibility(arguments.backup)
    if arguments.command == "plan-forward-custody-release":
        return plan_forward_release(arguments.backup)
    if arguments.command == "certify-forward-custody-release":
        return certify_forward_release(arguments.release_directory, runtime_root=arguments.runtime_root)
    if arguments.command == "verify-development-dataset":
        value = verify_development_dataset_descriptor(arguments.descriptor, release_directory=arguments.release_directory, runtime_root=arguments.custody_runtime_root)
        return _dataset_projection(value)
    if arguments.command == "verify-development-permit":
        return verify_development_permit(
            arguments.authority_root,
            arguments.permit_id,
            descriptor=arguments.descriptor,
            release_directory=arguments.release_directory,
            custody_runtime_root=arguments.custody_runtime_root,
            repository_commit=arguments.repository_commit,
            experiment_family=arguments.experiment_family,
            authorization_stage=arguments.authorization_stage,
            as_of=arguments.as_of,
        )
    if arguments.command == "inspect-authority-runtime":
        return inspect_authority_runtime(arguments.authority_root)
    if arguments.command == "build-forward-custody-release":
        return build_forward_release(arguments.backup, arguments.runtime_root, acknowledgement=arguments.acknowledge)
    if arguments.command == "create-development-dataset":
        descriptor = build_development_dataset_descriptor(
            arguments.release_directory,
            runtime_root=arguments.custody_runtime_root,
            provider="BINANCE_PUBLIC",
            symbols=arguments.symbol,
            streams=arguments.stream,
            temporal_start=arguments.temporal_start,
            temporal_end_as_of=arguments.temporal_end_as_of,
            causal_availability_cutoff=arguments.causal_availability_cutoff,
            provenance_reference=arguments.provenance_reference,
        )
        written = write_development_dataset_descriptor(descriptor, arguments.destination, acknowledgement=arguments.acknowledge)
        return {"status": "CREATED", "dataset_id": written["dataset_id"], "canonical_descriptor_hash": written["canonical_descriptor_hash"], "metadata_safe": True}
    if arguments.command == "init-research-authority-runtime":
        result = initialize_authority_runtime(arguments.authority_root, acknowledgement=arguments.acknowledge)
        return {"status": "INITIALIZED", "database": result["database"], "trust_boundary": result["trust_boundary"]}
    if arguments.command == "issue-development-permit":
        return issue_development_permit(
            arguments.authority_root,
            descriptor=arguments.descriptor,
            release_directory=arguments.release_directory,
            custody_runtime_root=arguments.custody_runtime_root,
            experiment_family=arguments.experiment_family,
            fixed_trial_budget=arguments.fixed_trial_budget,
            expires_at=arguments.expires_at,
            acknowledgement=arguments.acknowledge,
        )
    if arguments.command == "revoke-development-permit":
        if arguments.acknowledge != ACK_REVOKE_PERMIT:
            raise ReopeningError("PERMIT_REVOCATION_ACKNOWLEDGEMENT_REQUIRED")
        return revoke_development_permit(
            arguments.authority_root,
            arguments.permit_id,
            acknowledgement=arguments.acknowledge,
        )
    if arguments.command == "register-development-budget":
        return register_development_budget(
            arguments.trial_ledger,
            budget_id=arguments.budget_id,
            experiment_family=arguments.experiment_family,
            total_trial_budget=arguments.total_trial_budget,
            created_at=arguments.created_at,
            acknowledgement=arguments.acknowledge,
        )
    if arguments.command == "admit-development":
        if arguments.acknowledge != ACK_ADMIT_DEVELOPMENT:
            raise ReopeningError("ADMISSION_ACKNOWLEDGEMENT_REQUIRED")
        ledger = open_development_trial_ledger(arguments.trial_ledger)
        observation = get_repository_observation()
        if not observation["clean"]:
            raise ReopeningError("DIRTY_REPOSITORY")
        request = build_admission_request(
            request_id=arguments.request_id,
            repository_commit=observation["head"],
            repository_clean=observation["clean"],
            budget_id=arguments.budget_id,
            declared_trial_number=arguments.declared_trial_number,
            dataset_id=arguments.dataset_id,
            dataset_descriptor_hash=arguments.dataset_descriptor_hash,
            data_class=arguments.data_class,
            split_identity=arguments.split_identity,
            permit_id=arguments.permit_id,
            permit_hash=arguments.permit_hash,
            experiment_family=arguments.experiment_family,
            authorization_stage=arguments.authorization_stage,
            initiated_by=arguments.initiated_by,
            created_at=arguments.created_at,
        )
        service = DevelopmentAdmissionService(
            descriptor=arguments.descriptor,
            release_directory=arguments.release_directory,
            custody_runtime_root=arguments.custody_runtime_root,
            authority_root=arguments.authority_root,
            trial_ledger=ledger,
            repository_observer=lambda: observation,
        )
        return service.admit(request)
    raise ReopeningError("CLI_INPUT_INVALID")


def main(argv: list[str] | None = None) -> int:
    try:
        result = _run(build_parser().parse_args(argv))
    except ReopeningError as error:
        sys.stderr.write(canonical_json({"reason": error.reason, "status": "FAIL"}) + "\n")
        return 2
    except AdmissionError as error:
        sys.stderr.write(canonical_json({"reason": error.reason_token, "status": "FAIL"}) + "\n")
        return 2
    except Exception:
        sys.stderr.write(canonical_json({"reason": "INTERNAL_INTEGRITY_FAILURE", "status": "FAIL"}) + "\n")
        return 2
    sys.stdout.write(canonical_json(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
