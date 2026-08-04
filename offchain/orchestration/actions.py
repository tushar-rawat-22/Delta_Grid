"""The three private, compiled Mission 97 observation actions."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from offchain.research.admission import canonical_hash
from offchain.research.control_plane import (
    ControlPlaneError,
    ReadOnlyTrialLedger,
    ResearchControlPlaneService,
)

from .definitions import (
    CAPTURE_ACTION_ID,
    CAPTURE_STEP_ID,
    PUBLISH_ACTION_ID,
    PUBLISH_STEP_ID,
    RESEARCH_OBSERVATION_REFRESH_V1,
    VERIFY_ACTION_ID,
    VERIFY_STEP_ID,
)
from .models import MISSION_CONTRACT_HASH, OrchestrationError
from .strict_json import (
    decode_json,
    prepare_artifact_path,
    publish_canonical,
    sha256_bytes,
)


MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024
MAX_VERIFICATION_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024

MISSION_93_CONTRACT_ID = "deltagrid-research-cockpit-v0-charter-v1"
MISSION_93_CONTRACT_HASH = (
    "b4064f4651730618bf6497e631e913ebde7d6c9db926943d46aa11b3bc223bc1"
)
MISSION_94_CONTRACT_ID = "deltagrid-research-admission-core-v1"
MISSION_94_CONTRACT_HASH = (
    "e4070b52a0f2dbc8ce34ea00d0a732c2aed25c9c21e5acfccc3f9d791dba6193"
)
MISSION_95_CONTRACT_ID = "deltagrid-canonical-result-engine-service-v1"
MISSION_95_CONTRACT_HASH = (
    "d8fcd1169e638b648f8b5fccb389dfd090b016beb80e9e13d7f0a0af3210aa6a"
)
MISSION_96A_ID = "deltagrid-research-control-plane-v1"
MISSION_96A_HASH = (
    "c1e0c8c55db90fe8a81d3afe2d243537c703dbee6a945596f4b37c5ee13e70a9"
)
CONTROL_PLANE_AUTHORITY = {
    "read_only_ledger_access_authorized": True,
    "linked_result_loading_authorized": True,
    "deterministic_projection_authorized": True,
    "ledger_write_authorized": False,
    "trial_admission_authorized": False,
    "control_execution_authorized": False,
    "strategy_research_authorized": False,
    "market_data_access_authorized": False,
    "validation_access_authorized": False,
    "holdout_access_authorized": False,
    "protected_data_access_authorized": False,
    "model_training_authorized": False,
    "exchange_access_authorized": False,
    "paper_trading_authorized": False,
    "live_trading_authorized": False,
    "capital_deployment_authorized": False,
    "autonomous_research_authorized": False,
    "autonomous_promotion_authorized": False,
    "autonomous_execution_authorized": False,
    "cockpit_ui_authorized": False,
}
HEALTH_TOKENS = {"HEALTHY", "DEGRADED", "INTEGRITY_FAILURE", "UNAVAILABLE"}
INCIDENT_CATEGORIES = {
    "LEDGER_UNAVAILABLE",
    "LEDGER_SCHEMA_INCOMPATIBLE",
    "LEDGER_ROW_INTEGRITY_FAILURE",
    "INVALID_LIFECYCLE",
    "COMPLETED_WITHOUT_RESULT_LINK",
    "RESULT_LINK_WITHOUT_COMPLETED_EVENT",
    "RESULT_ARTIFACT_MISSING",
    "RESULT_ARTIFACT_TAMPERED",
    "RESULT_SCHEMA_UNSUPPORTED",
    "RESULT_VERIFICATION_FAILED",
    "DUPLICATE_OR_CONFLICTING_IDENTITY",
}
INCIDENT_SEVERITIES = {"INFO", "WARNING", "ERROR", "CRITICAL"}

AUTHORITY_DECLARATION = {
    "observation_only": True,
    "research_authorized": False,
    "market_access_authorized": False,
    "validation_access_authorized": False,
    "holdout_access_authorized": False,
    "model_training_authorized": False,
    "signal_generation_authorized": False,
    "exchange_access_authorized": False,
    "paper_trading_authorized": False,
    "live_trading_authorized": False,
    "capital_deployment_authorized": False,
    "autonomous_trading_execution_authorized": False,
}


@dataclass(frozen=True)
class _ActionResult:
    artifact_id: str
    artifact_relative_path: str
    artifact_byte_hash: str
    artifact_canonical_hash: str
    raw: bytes


def _artifact_result(
    *,
    output_root: Path,
    run_id: str,
    step_id: str,
    idempotency_key: str,
    payload: dict[str, Any],
    canonical_hash_field: str,
    max_bytes: int,
    validate_existing: Any = None,
) -> _ActionResult:
    path = prepare_artifact_path(output_root, run_id, step_id)
    raw = publish_canonical(
        path,
        payload,
        max_bytes=max_bytes,
        validate_existing=validate_existing,
    )
    relative = path.relative_to(output_root).as_posix()
    artifact_canonical_hash = str(payload[canonical_hash_field])
    identity = canonical_hash(
        {
            "mission_97_contract_hash": MISSION_CONTRACT_HASH,
            "run_id": run_id,
            "step_id": step_id,
            "idempotency_key": idempotency_key,
            "artifact_relative_path": relative,
            "artifact_byte_hash": sha256_bytes(raw),
            "artifact_canonical_hash": artifact_canonical_hash,
        }
    )
    return _ActionResult(
        artifact_id=f"artifact-{identity[:32]}",
        artifact_relative_path=relative,
        artifact_byte_hash=sha256_bytes(raw),
        artifact_canonical_hash=artifact_canonical_hash,
        raw=raw,
    )


def _read_receipt_artifact(
    output_root: Path,
    receipt: Mapping[str, Any],
    *,
    max_bytes: int,
    integrity_reason: str,
) -> tuple[dict[str, Any], bytes]:
    expected = (
        Path("runs")
        / str(receipt["run_id"])
        / str(receipt["step_id"])
        / "result.json"
    ).as_posix()
    if receipt["artifact_relative_path"] != expected:
        raise OrchestrationError("ARTIFACT_PATH_UNSAFE")
    path = output_root.joinpath(*Path(expected).parts)
    try:
        current = output_root
        for part in Path(expected).parts:
            current = current / part
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode):
                raise OrchestrationError("ARTIFACT_PATH_UNSAFE")
        resolved = path.resolve(strict=True)
    except OrchestrationError:
        raise
    except FileNotFoundError as error:
        raise OrchestrationError("ARTIFACT_TEMPORARILY_UNAVAILABLE") from error
    except OSError as error:
        raise OrchestrationError("ARTIFACT_PATH_UNSAFE") from error
    if resolved != path or not resolved.is_relative_to(output_root):
        raise OrchestrationError("ARTIFACT_PATH_UNSAFE")
    try:
        if path.stat().st_size > max_bytes:
            raise OrchestrationError("RESOURCE_LIMIT_EXCEEDED")
        raw = path.read_bytes()
    except OSError as error:
        raise OrchestrationError("ARTIFACT_TEMPORARILY_UNAVAILABLE") from error
    if sha256_bytes(raw) != receipt["artifact_byte_hash"]:
        raise OrchestrationError("ARTIFACT_HASH_MISMATCH")
    value = decode_json(raw, max_bytes=max_bytes, reason=integrity_reason)
    if type(value) is not dict:
        raise OrchestrationError(integrity_reason)
    return value, raw


def _validate_projection_hashes(snapshot: dict[str, Any]) -> None:
    inventories = (
        ("trials", "trial_id", "canonical_trial_projection_hash"),
        ("results", "result_bundle_id", "canonical_result_projection_hash"),
        ("incidents", "incident_id", "canonical_incident_hash"),
    )
    for field, identity_field, hash_field in inventories:
        values = snapshot[field]
        if type(values) is not list:
            raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
        identities: set[str] = set()
        for item in values:
            if type(item) is not dict or hash_field not in item:
                raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
            identity = item.get(identity_field)
            if type(identity) is not str or identity in identities:
                raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
            identities.add(identity)
            core = dict(item)
            supplied = core.pop(hash_field)
            if canonical_hash(core) != supplied:
                raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
    trials = {item["trial_id"] for item in snapshot["trials"]}
    if any(item.get("trial_id") not in trials for item in snapshot["results"]):
        raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")


def _verify_snapshot(
    raw: bytes,
    *,
    expected_repository_commit: str,
    observation_as_of: str,
    research_ledger_path: str,
    result_root: str,
    governance_root: Path,
) -> dict[str, Any]:
    snapshot = decode_json(
        raw,
        max_bytes=MAX_SNAPSHOT_BYTES,
        reason="SNAPSHOT_INTEGRITY_FAILURE",
    )
    exact = {
        "schema_version", "snapshot_id", "snapshot_version", "system",
        "trials", "results", "incidents", "canonical_snapshot_hash",
    }
    if type(snapshot) is not dict or set(snapshot) != exact:
        raise OrchestrationError("SNAPSHOT_SCHEMA_UNSUPPORTED")
    if snapshot["schema_version"] != "1.0" or snapshot["snapshot_version"] != 1:
        raise OrchestrationError("SNAPSHOT_SCHEMA_UNSUPPORTED")
    if type(snapshot["system"]) is not dict:
        raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
    _validate_projection_hashes(snapshot)
    system = dict(snapshot["system"])
    if system.get("snapshot_id") != snapshot["snapshot_id"]:
        raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
    system.pop("snapshot_id")
    identity_core = {
        "schema_version": snapshot["schema_version"],
        "snapshot_version": snapshot["snapshot_version"],
        "system": system,
        "trials": snapshot["trials"],
        "results": snapshot["results"],
        "incidents": snapshot["incidents"],
    }
    if snapshot["snapshot_id"] != f"snapshot-{canonical_hash(identity_core)[:32]}":
        raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
    snapshot_core = dict(snapshot)
    supplied = snapshot_core.pop("canonical_snapshot_hash")
    if canonical_hash(snapshot_core) != supplied:
        raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
    system_original = snapshot["system"]
    if (
        system_original.get("schema_version") != snapshot["schema_version"]
        or system_original.get("snapshot_version") != snapshot["snapshot_version"]
        or system_original.get("as_of") != observation_as_of
    ):
        raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
    required_identities = {
        "mission_93_contract_id": MISSION_93_CONTRACT_ID,
        "mission_93_contract_hash": MISSION_93_CONTRACT_HASH,
        "mission_94_contract_id": MISSION_94_CONTRACT_ID,
        "mission_94_contract_hash": MISSION_94_CONTRACT_HASH,
        "mission_95_contract_id": MISSION_95_CONTRACT_ID,
        "mission_95_contract_hash": MISSION_95_CONTRACT_HASH,
        "mission_96a_contract_id": MISSION_96A_ID,
        "mission_96a_contract_hash": MISSION_96A_HASH,
    }
    if any(system_original.get(key) != value for key, value in required_identities.items()):
        raise OrchestrationError("REPOSITORY_CONTRACT_INTEGRITY_FAILURE")
    if (
        system_original.get("repository_commit") != expected_repository_commit
        or system_original.get("as_of") != observation_as_of
    ):
        raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
    expected_path_identities = {
        "ledger_path_identity": (
            "sha256:"
            + canonical_hash({"absolute_path": str(Path(research_ledger_path))})
        ),
        "result_root_path_identity": (
            "sha256:" + canonical_hash({"absolute_path": str(Path(result_root))})
        ),
        "repository_root_path_identity": (
            "sha256:" + canonical_hash({"absolute_path": str(governance_root)})
        ),
    }
    if any(
        system_original.get(field) != expected
        for field, expected in expected_path_identities.items()
    ):
        raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
    if (
        system_original.get("incident_count") != len(snapshot["incidents"])
        or system_original.get("verified_linked_result_count")
        != len(snapshot["results"])
        or system_original.get("health_token") not in HEALTH_TOKENS
        or any(
            incident.get("category") not in INCIDENT_CATEGORIES
            or incident.get("severity") not in INCIDENT_SEVERITIES
            for incident in snapshot["incidents"]
        )
    ):
        raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
    expected_verification = {
        "mission_93_verified": True,
        "mission_94_verified": True,
        "mission_95_verified": True,
        "mission_96a_verified": True,
        "predecessor_chain_verified": True,
    }
    if system_original.get("contract_verification") != expected_verification:
        raise OrchestrationError("REPOSITORY_CONTRACT_INTEGRITY_FAILURE")
    if system_original.get("authority_projection") != CONTROL_PLANE_AUTHORITY:
        raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
    for name in (
        "ledger_write_authorized", "strategy_research_authorized",
        "market_data_access_authorized", "validation_access_authorized",
        "holdout_access_authorized", "model_training_authorized",
        "exchange_access_authorized", "paper_trading_authorized",
        "live_trading_authorized", "capital_deployment_authorized",
        "autonomous_execution_authorized",
    ):
        if system_original["authority_projection"].get(name) is not False:
            raise OrchestrationError("SNAPSHOT_INTEGRITY_FAILURE")
    return snapshot


def _capture(
    *,
    output_root: Path,
    governance_root: Path,
    run: Mapping[str, Any],
    idempotency_key: str,
) -> _ActionResult:
    path = prepare_artifact_path(output_root, run["run_id"], CAPTURE_STEP_ID)
    if path.exists():
        if path.stat().st_size > MAX_SNAPSHOT_BYTES:
            raise OrchestrationError("RESOURCE_LIMIT_EXCEEDED")
        raw = path.read_bytes()
        snapshot = _verify_snapshot(
            raw,
            expected_repository_commit=run["input"]["expected_repository_commit"],
            observation_as_of=run["input"]["observation_as_of"],
            research_ledger_path=run["input"]["research_ledger_path"],
            result_root=run["input"]["result_root"],
            governance_root=governance_root,
        )
        return _artifact_result(
            output_root=output_root,
            run_id=run["run_id"],
            step_id=CAPTURE_STEP_ID,
            idempotency_key=idempotency_key,
            payload=snapshot,
            canonical_hash_field="canonical_snapshot_hash",
            max_bytes=MAX_SNAPSHOT_BYTES,
            validate_existing=lambda existing: _verify_snapshot(
                existing,
                expected_repository_commit=run["input"]["expected_repository_commit"],
                observation_as_of=run["input"]["observation_as_of"],
                research_ledger_path=run["input"]["research_ledger_path"],
                result_root=run["input"]["result_root"],
                governance_root=governance_root,
            ),
        )
    try:
        ledger = ReadOnlyTrialLedger(run["input"]["research_ledger_path"])
        service = ResearchControlPlaneService(
            ledger=ledger,
            result_root=run["input"]["result_root"],
            repository_root=governance_root,
            expected_repository_commit=run["input"]["expected_repository_commit"],
        )
        payload = service.build_snapshot(
            as_of=run["input"]["observation_as_of"]
        ).as_dict()
    except ControlPlaneError as error:
        mapping = {
            "LEDGER_UNAVAILABLE": "SNAPSHOT_TEMPORARILY_UNAVAILABLE",
            "REPOSITORY_CONTRACT_INTEGRITY_FAILURE": (
                "REPOSITORY_CONTRACT_INTEGRITY_FAILURE"
            ),
        }
        raise OrchestrationError(
            mapping.get(error.reason_token, "RESEARCH_LEDGER_INTEGRITY_FAILURE"),
            error.explanation,
        ) from error
    return _artifact_result(
        output_root=output_root,
        run_id=run["run_id"],
        step_id=CAPTURE_STEP_ID,
        idempotency_key=idempotency_key,
        payload=payload,
        canonical_hash_field="canonical_snapshot_hash",
        max_bytes=MAX_SNAPSHOT_BYTES,
        validate_existing=lambda existing: _verify_snapshot(
            existing,
            expected_repository_commit=run["input"]["expected_repository_commit"],
            observation_as_of=run["input"]["observation_as_of"],
            research_ledger_path=run["input"]["research_ledger_path"],
            result_root=run["input"]["result_root"],
            governance_root=governance_root,
        ),
    )


def _verify(
    *,
    output_root: Path,
    governance_root: Path,
    run: Mapping[str, Any],
    receipts: list[Mapping[str, Any]],
    idempotency_key: str,
) -> _ActionResult:
    if len(receipts) < 1 or receipts[0]["step_id"] != CAPTURE_STEP_ID:
        raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
    snapshot, raw = _read_receipt_artifact(
        output_root,
        receipts[0],
        max_bytes=MAX_SNAPSHOT_BYTES,
        integrity_reason="SNAPSHOT_INTEGRITY_FAILURE",
    )
    snapshot = _verify_snapshot(
        raw,
        expected_repository_commit=run["input"]["expected_repository_commit"],
        observation_as_of=run["input"]["observation_as_of"],
        research_ledger_path=run["input"]["research_ledger_path"],
        result_root=run["input"]["result_root"],
        governance_root=governance_root,
    )
    core = {
        "schema_version": "1.0",
        "verification_version": 1,
        "source_snapshot_artifact_id": receipts[0]["artifact_id"],
        "source_snapshot_byte_hash": receipts[0]["artifact_byte_hash"],
        "source_snapshot_canonical_hash": snapshot["canonical_snapshot_hash"],
        "source_snapshot_id": snapshot["snapshot_id"],
        "repository_commit": snapshot["system"]["repository_commit"],
        "observation_as_of": run["input"]["observation_as_of"],
        "verification_token": "CONTROL_PLANE_SNAPSHOT_VERIFIED",
    }
    verification_id = f"verification-{canonical_hash(core)[:32]}"
    identified = {"verification_id": verification_id, **core}
    payload = {
        **identified,
        "canonical_verification_hash": canonical_hash(identified),
    }
    return _artifact_result(
        output_root=output_root,
        run_id=run["run_id"],
        step_id=VERIFY_STEP_ID,
        idempotency_key=idempotency_key,
        payload=payload,
        canonical_hash_field="canonical_verification_hash",
        max_bytes=MAX_VERIFICATION_BYTES,
    )


def _publish(
    *,
    output_root: Path,
    governance_root: Path,
    run: Mapping[str, Any],
    receipts: list[Mapping[str, Any]],
    idempotency_key: str,
) -> _ActionResult:
    if [item["step_id"] for item in receipts] != [CAPTURE_STEP_ID, VERIFY_STEP_ID]:
        raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
    snapshot, snapshot_raw = _read_receipt_artifact(
        output_root,
        receipts[0],
        max_bytes=MAX_SNAPSHOT_BYTES,
        integrity_reason="SNAPSHOT_INTEGRITY_FAILURE",
    )
    snapshot = _verify_snapshot(
        snapshot_raw,
        expected_repository_commit=run["input"]["expected_repository_commit"],
        observation_as_of=run["input"]["observation_as_of"],
        research_ledger_path=run["input"]["research_ledger_path"],
        result_root=run["input"]["result_root"],
        governance_root=governance_root,
    )
    verification, _ = _read_receipt_artifact(
        output_root,
        receipts[1],
        max_bytes=MAX_VERIFICATION_BYTES,
        integrity_reason="ARTIFACT_HASH_MISMATCH",
    )
    verification_core = dict(verification)
    supplied_verification_hash = verification_core.pop(
        "canonical_verification_hash", None
    )
    if (
        canonical_hash(verification_core) != supplied_verification_hash
        or verification.get("verification_token")
        != "CONTROL_PLANE_SNAPSHOT_VERIFIED"
        or verification.get("source_snapshot_artifact_id")
        != receipts[0]["artifact_id"]
        or verification.get("source_snapshot_byte_hash")
        != receipts[0]["artifact_byte_hash"]
    ):
        raise OrchestrationError("ARTIFACT_HASH_MISMATCH")
    core = {
        "schema_version": "1.0",
        "manifest_version": 1,
        "run_id": run["run_id"],
        "workflow_definition_id": RESEARCH_OBSERVATION_REFRESH_V1.workflow_definition_id,
        "workflow_definition_version": 1,
        "workflow_definition_hash": RESEARCH_OBSERVATION_REFRESH_V1.canonical_workflow_definition_hash,
        "source_snapshot_artifact_id": receipts[0]["artifact_id"],
        "source_snapshot_byte_hash": receipts[0]["artifact_byte_hash"],
        "source_snapshot_id": snapshot["snapshot_id"],
        "source_canonical_snapshot_hash": snapshot["canonical_snapshot_hash"],
        "verification_artifact_id": receipts[1]["artifact_id"],
        "verification_artifact_byte_hash": receipts[1]["artifact_byte_hash"],
        "verification_token": verification["verification_token"],
        "repository_commit": snapshot["system"]["repository_commit"],
        "observation_as_of": run["input"]["observation_as_of"],
        "system_health_token": snapshot["system"]["health_token"],
        "incident_count": snapshot["system"]["incident_count"],
        "completed_step_ids": [CAPTURE_STEP_ID, VERIFY_STEP_ID, PUBLISH_STEP_ID],
        "warnings_by_trial": [
            {
                "trial_id": result["trial_id"],
                "result_bundle_id": result["result_bundle_id"],
                "warnings": result["warnings"],
            }
            for result in snapshot["results"]
        ],
        "authority_declaration": AUTHORITY_DECLARATION,
    }
    manifest_id = f"manifest-{canonical_hash(core)[:32]}"
    identified = {"manifest_id": manifest_id, **core}
    payload = {**identified, "canonical_manifest_hash": canonical_hash(identified)}
    return _artifact_result(
        output_root=output_root,
        run_id=run["run_id"],
        step_id=PUBLISH_STEP_ID,
        idempotency_key=idempotency_key,
        payload=payload,
        canonical_hash_field="canonical_manifest_hash",
        max_bytes=MAX_MANIFEST_BYTES,
    )


def _execute(
    *,
    step_id: str,
    output_root: Path,
    governance_root: Path,
    run: Mapping[str, Any],
    receipts: list[Mapping[str, Any]],
    idempotency_key: str,
) -> _ActionResult:
    if step_id == CAPTURE_STEP_ID:
        return _capture(
            output_root=output_root,
            governance_root=governance_root,
            run=run,
            idempotency_key=idempotency_key,
        )
    if step_id == VERIFY_STEP_ID:
        return _verify(
            output_root=output_root,
            governance_root=governance_root,
            run=run,
            receipts=receipts,
            idempotency_key=idempotency_key,
        )
    if step_id == PUBLISH_STEP_ID:
        return _publish(
            output_root=output_root,
            governance_root=governance_root,
            run=run,
            receipts=receipts,
            idempotency_key=idempotency_key,
        )
    raise OrchestrationError("ACTION_NOT_AUTHORIZED")
