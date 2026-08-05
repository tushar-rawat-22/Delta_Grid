"""Strict input parsing and independent Mission 97 evidence verification."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from types import MappingProxyType
from typing import Any, Mapping

from offchain.research.admission import canonical_hash, canonical_json

from .models import (
    CAUSAL_STATUSES,
    DOSSIER_FIELDS,
    MAX_DOSSIER_BYTES,
    MAX_HUMAN_TEXT_LENGTH,
    MAX_IDENTIFIER_LENGTH,
    MAX_JSON_DEPTH,
    MAX_MANIFEST_BYTES,
    MAX_RELATIVE_PATH_LENGTH,
    MAX_REQUEST_BYTES,
    MAX_SNAPSHOT_BYTES,
    MAX_VERIFICATION_BYTES,
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    NEW_INFORMATION_TYPES,
    OVERLAP_STATUSES,
    PROVENANCE_STATUSES,
    REJECTED_FAMILY_IDS,
    REQUESTED_AUTHORITY_FIELDS,
    REQUESTED_BY_VALUES,
    REQUESTED_STAGES,
    REQUEST_FIELDS,
    SCHEMA_VERSION,
    DirectorError,
    DirectorRequest,
    EvidenceView,
    ResearchOpportunityDossier,
)


_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}\Z")
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
_PATH_IDENTITY_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")

MISSION_93_ID = "deltagrid-research-cockpit-v0-charter-v1"
MISSION_93_HASH = "b4064f4651730618bf6497e631e913ebde7d6c9db926943d46aa11b3bc223bc1"
MISSION_94_ID = "deltagrid-research-admission-core-v1"
MISSION_94_HASH = "e4070b52a0f2dbc8ce34ea00d0a732c2aed25c9c21e5acfccc3f9d791dba6193"
MISSION_95_ID = "deltagrid-canonical-result-engine-service-v1"
MISSION_95_HASH = "d8fcd1169e638b648f8b5fccb389dfd090b016beb80e9e13d7f0a0af3210aa6a"
MISSION_96A_ID = "deltagrid-research-control-plane-v1"
MISSION_96A_HASH = "c1e0c8c55db90fe8a81d3afe2d243537c703dbee6a945596f4b37c5ee13e70a9"
MISSION_96B_ID = "deltagrid-research-cockpit-ui-v1"
MISSION_96B_HASH = "13846c63a6fcd07b2a4603aadd388960e74282de486bddf39907a09aa053c8d3"
MISSION_97_ID = "deltagrid-durable-workflow-orchestrator-v1"
MISSION_97_HASH = "c1840ed9f438f520401bbf24e501bb2a327f4718124745f275474ac76eeab272"
WORKFLOW_ID = "RESEARCH_OBSERVATION_REFRESH_V1"
WORKFLOW_HASH = "31c8ff6d912f1be046724330a4c5f49bc16925ac952d8db60d00a2e1c3c51f27"

CAPTURE_STEP = "CAPTURE_CONTROL_PLANE_SNAPSHOT"
VERIFY_STEP = "VERIFY_CONTROL_PLANE_SNAPSHOT"
PUBLISH_STEP = "PUBLISH_OBSERVATION_MANIFEST"

CONTROL_PLANE_AUTHORITY = MappingProxyType(
    {
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
)
MANIFEST_AUTHORITY = MappingProxyType(
    {
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
)
CONTRACT_VERIFICATION = MappingProxyType(
    {
        "mission_93_verified": True,
        "mission_94_verified": True,
        "mission_95_verified": True,
        "mission_96a_verified": True,
        "predecessor_chain_verified": True,
    }
)
HEALTH_TOKENS = frozenset({"HEALTHY", "DEGRADED", "INTEGRITY_FAILURE", "UNAVAILABLE"})
INCIDENT_SEVERITIES = frozenset({"INFO", "WARNING", "ERROR", "CRITICAL"})
INCIDENT_CATEGORIES = frozenset(
    {
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
)
_INTEGRITY_CATEGORIES = frozenset(
    {
        "LEDGER_ROW_INTEGRITY_FAILURE",
        "INVALID_LIFECYCLE",
        "RESULT_ARTIFACT_TAMPERED",
        "RESULT_SCHEMA_UNSUPPORTED",
        "RESULT_VERIFICATION_FAILED",
        "DUPLICATE_OR_CONFLICTING_IDENTITY",
    }
)

_CONTRACT_SPECS = (
    (
        "mission_93",
        "contracts/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json",
        MISSION_93_ID,
        MISSION_93_HASH,
        None,
        None,
    ),
    (
        "mission_94",
        "contracts/DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json",
        MISSION_94_ID,
        MISSION_94_HASH,
        "contracts/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json",
        None,
    ),
    (
        "mission_95",
        "contracts/DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE_V1.json",
        MISSION_95_ID,
        MISSION_95_HASH,
        "contracts/DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json",
        MISSION_94_HASH,
    ),
    (
        "mission_96a",
        "contracts/DELTAGRID_RESEARCH_CONTROL_PLANE_V1.json",
        MISSION_96A_ID,
        MISSION_96A_HASH,
        "contracts/DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE_V1.json",
        MISSION_95_HASH,
    ),
    (
        "mission_96b",
        "contracts/DELTAGRID_RESEARCH_COCKPIT_UI_V1.json",
        MISSION_96B_ID,
        MISSION_96B_HASH,
        "contracts/DELTAGRID_RESEARCH_CONTROL_PLANE_V1.json",
        MISSION_96A_HASH,
    ),
    (
        "mission_97",
        "contracts/DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR_V1.json",
        MISSION_97_ID,
        MISSION_97_HASH,
        "contracts/DELTAGRID_RESEARCH_COCKPIT_UI_V1.json",
        MISSION_96B_HASH,
    ),
    (
        "mission_98",
        "contracts/DELTAGRID_AUTONOMOUS_RESEARCH_DIRECTOR_V1.json",
        MISSION_CONTRACT_ID,
        MISSION_CONTRACT_HASH,
        "contracts/DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR_V1.json",
        MISSION_97_HASH,
    ),
)

_CONTRACT_KEY_SETS = (
    frozenset(
        {
            "contract_id", "contract_version", "contract_purpose", "base_commit",
            "final_freeze_contract", "current_authority", "interface_audit",
            "final_decision", "cockpit_implementation_authorized",
            "cockpit_research_authorized", "real_market_backtest_authorized",
            "validation_access_authorized", "holdout_access_authorized",
            "paper_trading_authorized", "live_trading_authorized",
            "capital_deployment_authorized", "model_training_authorized",
            "autonomous_research_authorized", "autonomous_promotion_authorized",
            "exchange_access_authorized", "cockpit_v0_boundary",
            "adapter_architecture", "non_alpha_controls",
            "control_execution_authorized", "future_experiment_manifest_contract",
            "future_result_bundle_contract", "trial_ledger",
            "anti_overfitting_support", "duplicate_logic_prohibitions",
            "dependency_decision", "implementation_path_budget",
            "implementation_acceptance_criteria", "stop_conditions",
            "next_authorized_action", "contract_hash_sha256",
        }
    ),
    frozenset(
        {
            "schema_version", "contract_id", "contract_version", "base_commit",
            "preceding_contract", "contract_hash_sha256",
            "implementation_authorization", "authorization_state",
            "controlling_state", "canonical_json", "package", "dataset_resolver",
            "control_registry", "trial_ledger", "admission_request",
            "admission_decision", "service_semantics", "reason_tokens",
            "no_execution_boundary", "implementation_acceptance_criteria",
            "next_authorized_action", "next_action_authorization",
        }
    ),
    frozenset(
        {
            "schema_version", "contract_id", "contract_version", "base_commit",
            "preceding_contract", "preceding_contract_hash_sha256",
            "authorization_stage", "contract_hash_sha256", "scope_explanation",
            "implementation_authorization", "authorization_state",
            "execution_scope", "repository_identity", "secure_binding",
            "canonical_json", "package", "public_api", "resource_limits",
            "fixture_v1", "persisted_identity_verification",
            "component_identities", "timing_diagnostics", "result_bundle_v1",
            "result_bundle_field_inventories", "result_status",
            "trial_result_link", "mission93_gap_05_field_map",
            "orphan_artifacts", "token_explanations", "reason_tokens",
        }
    ),
    frozenset(
        {
            "schema_version", "contract_id", "contract_version", "base_commit",
            "preceding_contract", "preceding_contract_hash_sha256",
            "authorization_stage", "contract_hash_sha256", "scope_explanation",
            "implementation_authorization", "authorization_state",
            "canonical_json", "package", "read_only_ledger",
            "repository_contract_verification", "supported_api_immutability",
            "required_ledger_schema", "snapshot", "health_tokens",
            "incident_severities", "incident_categories",
        }
    ),
    frozenset(
        {
            "schema_version", "contract_id", "contract_version", "base_commit",
            "preceding_contract", "preceding_contract_hash_sha256",
            "authorization_stage", "contract_hash_sha256", "scope_explanation",
            "implementation_authorization", "authorization_state",
            "canonical_json", "operating_modes", "package",
            "local_http_boundary", "api_integer_safety",
            "demonstration_snapshots", "permanent_declarations",
        }
    ),
    frozenset(
        {
            "schema_version", "contract_id", "contract_version", "base_commit",
            "preceding_contract", "preceding_contract_hash_sha256",
            "functional_dependency", "functional_dependency_hash_sha256",
            "authorization_stage", "contract_hash_sha256", "scope_explanation",
            "implementation_authorization", "authorization_state",
            "canonical_json", "workflow_definition", "retry_policy",
            "durability", "resource_limits", "observation_semantics",
            "non_retryable_error_inventory", "package",
        }
    ),
    frozenset(
        {
            "schema_version", "contract_id", "contract_version", "base_commit",
            "preceding_contract", "preceding_contract_hash_sha256",
            "authorization_stage", "contract_hash_sha256", "scope_explanation",
            "implementation_authorization", "authorization_state",
            "canonical_json", "package", "action_registry",
            "rejected_family_registry", "decision_policy", "root_binding",
            "strict_boundaries", "request_schema", "dossier_schema",
            "evidence_verification", "decision_schema", "independent_verifier",
            "ledger", "cli", "ci",
        }
    ),
)

_SYSTEM_FIELDS = frozenset(
    {
        "schema_version", "snapshot_id", "snapshot_version", "as_of",
        "repository_commit", "mission_93_contract_id", "mission_93_contract_hash",
        "mission_94_contract_id", "mission_94_contract_hash",
        "mission_95_contract_id", "mission_95_contract_hash",
        "mission_96a_contract_id", "mission_96a_contract_hash",
        "ledger_path_identity", "result_root_path_identity",
        "repository_root_path_identity", "contract_verification",
        "total_budget_count", "total_reservation_count", "total_event_count",
        "total_result_link_count", "lifecycle_counts",
        "verified_linked_result_count", "incident_count", "health_token",
        "authority_projection",
    }
)
_TRIAL_FIELDS = frozenset(
    {
        "trial_id", "budget_id", "experiment_family", "declared_trial_number",
        "initiated_by", "reserved_at", "request_hash", "latest_sequence_number",
        "latest_status_token", "latest_reason_token", "latest_event_timestamp",
        "event_count", "has_result_link", "result_verification_token",
        "result_bundle_id", "result_bundle_hash", "incident_ids",
        "canonical_trial_projection_hash",
    }
)
_RESULT_FIELDS = frozenset(
    {
        "trial_id", "result_bundle_id", "result_bundle_hash",
        "trial_status_token", "trial_reason_token", "result_status_token",
        "result_reason_token", "human_explanation", "control_identifier",
        "control_parameters", "dataset_identity", "code_identity",
        "simulator_identity", "execution_model_identity", "cost_model_identity",
        "risk_model_identity", "implementation_repository_commit",
        "gross_result", "net_result", "benchmark", "costs_by_component",
        "maximum_drawdown", "exposure", "turnover", "trade_count",
        "concentration", "timing_diagnostics", "protected_access_counts",
        "artifact_declarations", "warnings", "verification_declarations",
        "canonical_result_projection_hash",
    }
)
_INCIDENT_FIELDS = frozenset(
    {
        "incident_id", "severity", "category", "reason_token",
        "human_explanation", "trial_id", "detected_at", "evidence_identities",
        "canonical_incident_hash",
    }
)
_SNAPSHOT_FIELDS = frozenset(
    {
        "schema_version", "snapshot_id", "snapshot_version", "system",
        "trials", "results", "incidents", "canonical_snapshot_hash",
    }
)
_VERIFICATION_FIELDS = frozenset(
    {
        "verification_id", "schema_version", "verification_version",
        "source_snapshot_artifact_id", "source_snapshot_byte_hash",
        "source_snapshot_canonical_hash", "source_snapshot_id",
        "repository_commit", "observation_as_of", "verification_token",
        "canonical_verification_hash",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "manifest_id", "schema_version", "manifest_version", "run_id",
        "workflow_definition_id", "workflow_definition_version",
        "workflow_definition_hash", "source_snapshot_artifact_id",
        "source_snapshot_byte_hash", "source_snapshot_id",
        "source_canonical_snapshot_hash", "verification_artifact_id",
        "verification_artifact_byte_hash", "verification_token",
        "repository_commit", "observation_as_of", "system_health_token",
        "incident_count", "completed_step_ids", "warnings_by_trial",
        "authority_declaration", "canonical_manifest_hash",
    }
)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parse_utc(value: Any, *, reason: str = "DIRECTOR_INPUT_INVALID") -> datetime:
    if type(value) is not str or _UTC_RE.fullmatch(value) is None:
        raise DirectorError(reason, "A timestamp is not normalized UTC.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise DirectorError(reason, "A timestamp is invalid.") from error
    if parsed.tzinfo != timezone.utc:
        raise DirectorError(reason, "A timestamp is not UTC.")
    normalized = (
        f"{parsed.strftime('%Y-%m-%dT%H:%M:%S')}."
        f"{parsed.microsecond:06d}".rstrip("0") + "Z"
        if parsed.microsecond
        else parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    if value != normalized:
        raise DirectorError(reason, "A timestamp is not normalized.")
    return parsed


def validate_identifier(value: Any) -> str:
    if (
        type(value) is not str
        or len(value) > MAX_IDENTIFIER_LENGTH
        or _IDENTIFIER_RE.fullmatch(value) is None
    ):
        raise DirectorError("DIRECTOR_INPUT_INVALID", "An identifier is invalid.")
    return value


def _validate_hash(value: Any) -> str:
    if type(value) is not str or _HASH_RE.fullmatch(value) is None:
        raise DirectorError("DIRECTOR_INPUT_INVALID", "A SHA-256 value is invalid.")
    return value


def _evidence_hash(value: Any) -> str:
    if type(value) is not str or _HASH_RE.fullmatch(value) is None:
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    return value


def _enum_token(
    value: Any,
    allowed: frozenset[str],
    *,
    reason: str,
) -> str:
    if type(value) is not str or value not in allowed:
        raise DirectorError(reason)
    return value


def _evidence_path_identity(value: Any) -> str:
    if type(value) is not str or _PATH_IDENTITY_RE.fullmatch(value) is None:
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    return value


def _exact(value: Any, fields: tuple[str, ...] | frozenset[str], reason: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(fields):
        raise DirectorError(reason, "A JSON object does not have its exact required fields.")
    return value


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON number: {token}")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object name")
        result[key] = value
    return result


def _validate_tree(value: Any, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ValueError("maximum JSON depth exceeded")
    if type(value) not in (dict, list, str, int, bool, type(None)):
        raise ValueError("unsupported JSON type")
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("JSON object names must be strings")
            _validate_tree(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _validate_tree(item, depth + 1)


def decode_json(
    raw: bytes,
    *,
    max_bytes: int,
    reason: str,
    require_canonical: bool = True,
) -> Any:
    if type(raw) is not bytes:
        raise DirectorError(reason)
    if len(raw) > max_bytes:
        raise DirectorError("DIRECTOR_RESOURCE_LIMIT_EXCEEDED")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise DirectorError(reason, "UTF-8 BOMs are forbidden.")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
        _validate_tree(value)
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise DirectorError(reason, "Strict JSON decoding failed.") from error
    if require_canonical and canonical_json(value).encode("utf-8") != raw:
        raise DirectorError(reason, "JSON bytes are not canonical.")
    return value


def resolve_root(value: Path | str, *, reason: str) -> Path:
    if not isinstance(value, (str, Path)) or len(str(value)) > MAX_RELATIVE_PATH_LENGTH:
        raise DirectorError(reason, "A root path is invalid.")
    candidate = Path(value)
    if not candidate.is_absolute():
        raise DirectorError(reason, "A root path must be absolute.")
    current = Path(candidate.anchor)
    try:
        for part in candidate.parts[1:]:
            current = current / part
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode):
                raise DirectorError(reason, "A root path contains a symbolic link.")
        resolved = candidate.resolve(strict=True)
        metadata = resolved.stat()
    except DirectorError:
        raise
    except OSError as error:
        raise DirectorError(reason, "A root path does not exist.") from error
    if not stat.S_ISDIR(metadata.st_mode) or resolved != candidate:
        raise DirectorError(reason, "A root path is not an exact directory.")
    return resolved


def validate_database_path(value: Path | str, *, permit_missing: bool) -> Path:
    if not isinstance(value, (str, Path)) or len(str(value)) > MAX_RELATIVE_PATH_LENGTH:
        raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE")
    candidate = Path(value)
    if not candidate.is_absolute() or candidate.name in ("", ".", ".."):
        raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE")
    parent = resolve_root(candidate.parent, reason="DIRECTOR_SCHEMA_INCOMPATIBLE")
    exact = parent / candidate.name
    if candidate != exact:
        raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE")
    try:
        metadata = os.lstat(exact)
    except FileNotFoundError:
        if permit_missing:
            return exact
        raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE")
    except OSError as error:
        raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE")
    return exact


def _relative_parts(value: Any) -> tuple[str, ...]:
    if (
        type(value) is not str
        or not value
        or len(value) > MAX_RELATIVE_PATH_LENGTH
        or "\\" in value
        or value.startswith("/")
        or value.endswith("/")
    ):
        raise DirectorError("DIRECTOR_PATH_UNSAFE")
    raw_parts = value.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        raise DirectorError("DIRECTOR_PATH_UNSAFE")
    pure = PurePosixPath(value)
    if pure.is_absolute() or tuple(pure.parts) != tuple(raw_parts):
        raise DirectorError("DIRECTOR_PATH_UNSAFE")
    return tuple(raw_parts)


def _validate_observation_manifest_relative_path(
    value: Any,
) -> tuple[str, str, str, str]:
    parts = _relative_parts(value)
    if (
        len(parts) != 4
        or parts[0] != "runs"
        or parts[2] != "PUBLISH_OBSERVATION_MANIFEST"
        or parts[3] != "result.json"
    ):
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    validate_identifier(parts[1])
    return parts


def read_relative_file(
    root: Path,
    relative_path: Any,
    *,
    max_bytes: int,
    expected_hash: str | None = None,
) -> tuple[Path, bytes]:
    parts = _relative_parts(relative_path)
    current = root
    try:
        for part in parts:
            current = current / part
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode):
                raise DirectorError("DIRECTOR_PATH_UNSAFE")
        resolved = current.resolve(strict=True)
        if resolved != current or not resolved.is_relative_to(root):
            raise DirectorError("DIRECTOR_PATH_UNSAFE")
        metadata = os.lstat(current)
        if not stat.S_ISREG(metadata.st_mode):
            raise DirectorError("DIRECTOR_PATH_UNSAFE")
        if metadata.st_size > max_bytes:
            raise DirectorError("DIRECTOR_RESOURCE_LIMIT_EXCEEDED")
        with current.open("rb") as source:
            raw = source.read(max_bytes + 1)
    except DirectorError:
        raise
    except OSError as error:
        raise DirectorError("DIRECTOR_PATH_UNSAFE") from error
    if len(raw) > max_bytes:
        raise DirectorError("DIRECTOR_RESOURCE_LIMIT_EXCEEDED")
    if expected_hash is not None and sha256_bytes(raw) != expected_hash:
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    return current, raw


def _canonical_hash_matches(value: dict[str, Any], field: str, reason: str) -> None:
    core = dict(value)
    supplied = core.pop(field, None)
    if type(supplied) is not str or _HASH_RE.fullmatch(supplied) is None:
        raise DirectorError(reason)
    if canonical_hash(core) != supplied:
        raise DirectorError(reason)


def parse_request(raw: bytes, *, expected_commit: str) -> DirectorRequest:
    value = _exact(
        decode_json(
            raw, max_bytes=MAX_REQUEST_BYTES, reason="DIRECTOR_INPUT_INVALID"
        ),
        REQUEST_FIELDS,
        "DIRECTOR_INPUT_INVALID",
    )
    if value["schema_version"] != SCHEMA_VERSION:
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    validate_identifier(value["request_id"])
    if (
        value["controlling_contract_id"] != MISSION_CONTRACT_ID
        or value["controlling_contract_hash"] != MISSION_CONTRACT_HASH
        or type(value["repository_commit"]) is not str
        or _COMMIT_RE.fullmatch(value["repository_commit"]) is None
        or value["repository_commit"] != expected_commit
        or value["repository_clean"] is not True
    ):
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    _validate_observation_manifest_relative_path(
        value["observation_manifest_relative_path"]
    )
    _validate_hash(value["observation_manifest_sha256"])
    proposal_path = value["proposal_relative_path"]
    proposal_hash = value["proposal_sha256"]
    if (proposal_path is None) != (proposal_hash is None):
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    if proposal_path is not None:
        _relative_parts(proposal_path)
        _validate_hash(proposal_hash)
    requested_at = parse_utc(value["requested_at"])
    decision_as_of = parse_utc(value["decision_as_of"])
    if requested_at > decision_as_of:
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    _enum_token(
        value["requested_by"],
        REQUESTED_BY_VALUES,
        reason="DIRECTOR_INPUT_INVALID",
    )
    _canonical_hash_matches(value, "canonical_request_hash", "DIRECTOR_INPUT_INVALID")
    return DirectorRequest(value)


def _validate_reference(value: Any) -> None:
    item = _exact(
        value, frozenset({"reference_id", "sha256"}), "DIRECTOR_INPUT_INVALID"
    )
    validate_identifier(item["reference_id"])
    _validate_hash(item["sha256"])


def parse_dossier(
    raw: bytes,
    *,
    expected_byte_hash: str,
    requested_at: str,
) -> ResearchOpportunityDossier:
    if sha256_bytes(raw) != expected_byte_hash:
        raise DirectorError("DIRECTOR_INPUT_INVALID", "The dossier byte hash does not match.")
    value = _exact(
        decode_json(
            raw, max_bytes=MAX_DOSSIER_BYTES, reason="DIRECTOR_INPUT_INVALID"
        ),
        DOSSIER_FIELDS,
        "DIRECTOR_INPUT_INVALID",
    )
    if value["schema_version"] != SCHEMA_VERSION:
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    validate_identifier(value["proposal_id"])
    if value["proposal_kind"] != "RESEARCH_REOPENING_CANDIDATE":
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    for field in ("economic_mechanism", "falsifiable_claim"):
        if type(value[field]) is not str or len(value[field]) > MAX_HUMAN_TEXT_LENGTH:
            raise DirectorError("DIRECTOR_INPUT_INVALID")
    _enum_token(
        value["new_information_type"],
        NEW_INFORMATION_TYPES,
        reason="DIRECTOR_INPUT_INVALID",
    )
    if value["new_information_reference"] is not None:
        _validate_reference(value["new_information_reference"])
    _enum_token(
        value["provenance_status"],
        PROVENANCE_STATUSES,
        reason="DIRECTOR_INPUT_INVALID",
    )
    _enum_token(
        value["causal_availability_status"],
        CAUSAL_STATUSES,
        reason="DIRECTOR_INPUT_INVALID",
    )
    _enum_token(
        value["overlap_audit_status"],
        OVERLAP_STATUSES,
        reason="DIRECTOR_INPUT_INVALID",
    )
    families = value["compared_rejected_family_ids"]
    if type(families) is not list or any(type(item) is not str for item in families):
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    if (
        len(families) != len(set(families))
        or any(item not in REJECTED_FAMILY_IDS for item in families)
        or families
        != [item for item in REJECTED_FAMILY_IDS if item in set(families)]
    ):
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    references = value["overlap_evidence_references"]
    if type(references) is not list:
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    for item in references:
        _validate_reference(item)
    reference_ids = [item["reference_id"] for item in references]
    if len(reference_ids) != len(set(reference_ids)) or reference_ids != sorted(reference_ids):
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    _enum_token(
        value["requested_stage"],
        REQUESTED_STAGES,
        reason="DIRECTOR_INPUT_INVALID",
    )
    authorities = _exact(
        value["requested_authorities"],
        frozenset(REQUESTED_AUTHORITY_FIELDS),
        "DIRECTOR_INPUT_INVALID",
    )
    if any(type(item) is not bool for item in authorities.values()):
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    draft = value["draft_reopening_contract_reference"]
    if draft is not None:
        draft = _exact(
            draft,
            frozenset({"contract_id", "reference_id", "sha256"}),
            "DIRECTOR_INPUT_INVALID",
        )
        validate_identifier(draft["contract_id"])
        validate_identifier(draft["reference_id"])
        _validate_hash(draft["sha256"])
    if parse_utc(value["created_at"]) > parse_utc(requested_at):
        raise DirectorError("DIRECTOR_INPUT_INVALID")
    _canonical_hash_matches(value, "canonical_dossier_hash", "DIRECTOR_INPUT_INVALID")
    return ResearchOpportunityDossier(value, expected_byte_hash)


def verify_contract_chain(repository_root: Path) -> Mapping[str, tuple[str, str]]:
    identities: dict[str, tuple[str, str]] = {}
    try:
        for spec, expected_keys in zip(_CONTRACT_SPECS, _CONTRACT_KEY_SETS):
            mission, relative, expected_id, expected_hash, predecessor, predecessor_hash = spec
            _, raw = read_relative_file(
                repository_root, relative, max_bytes=1_048_576
            )
            value = _exact(
                decode_json(
                    raw,
                    max_bytes=1_048_576,
                    reason="GOVERNANCE_CONTRACT_INTEGRITY_FAILURE",
                    require_canonical=False,
                ),
                expected_keys,
                "GOVERNANCE_CONTRACT_INTEGRITY_FAILURE",
            )
            core = dict(value)
            supplied = core.pop("contract_hash_sha256", None)
            if (
                value.get("contract_id") != expected_id
                or type(value.get("contract_version")) is not int
                or value.get("contract_version") != 1
                or supplied != expected_hash
                or canonical_hash(core) != expected_hash
                or (
                    mission != "mission_93"
                    and value.get("schema_version") != SCHEMA_VERSION
                )
                or (
                    predecessor is not None
                    and value.get("preceding_contract") != predecessor
                )
                or (
                    predecessor_hash is not None
                    and value.get("preceding_contract_hash_sha256")
                    != predecessor_hash
                )
            ):
                raise DirectorError("GOVERNANCE_CONTRACT_INTEGRITY_FAILURE")
            if mission == "mission_97" and (
                value.get("functional_dependency")
                != "contracts/DELTAGRID_RESEARCH_CONTROL_PLANE_V1.json"
                or value.get("functional_dependency_hash_sha256") != MISSION_96A_HASH
            ):
                raise DirectorError("GOVERNANCE_CONTRACT_INTEGRITY_FAILURE")
            identities[mission] = (expected_id, expected_hash)
    except DirectorError as error:
        if error.reason_token == "GOVERNANCE_CONTRACT_INTEGRITY_FAILURE":
            raise
        raise DirectorError("GOVERNANCE_CONTRACT_INTEGRITY_FAILURE") from error
    return MappingProxyType(identities)


def _require_string(value: Any, *, identifier: bool = False) -> str:
    if type(value) is not str or len(value) > MAX_HUMAN_TEXT_LENGTH:
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    if identifier:
        validate_identifier(value)
    return value


def _require_int(value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    return value


def _validate_projection(
    item: Any,
    *,
    fields: frozenset[str],
    hash_field: str,
) -> dict[str, Any]:
    value = _exact(item, fields, "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    _canonical_hash_matches(
        value, hash_field, "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE"
    )
    return value


def _verify_snapshot(
    value: Any,
    *,
    expected_repository_commit: str,
    observation_as_of: str,
    repository_root: Path,
    contract_identities: Mapping[str, tuple[str, str]],
) -> dict[str, Any]:
    snapshot = _exact(
        value, _SNAPSHOT_FIELDS, "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE"
    )
    if (
        snapshot["schema_version"] != SCHEMA_VERSION
        or type(snapshot["snapshot_version"]) is not int
        or snapshot["snapshot_version"] != 1
    ):
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    system = _exact(
        snapshot["system"], _SYSTEM_FIELDS, "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE"
    )
    trials = snapshot["trials"]
    results = snapshot["results"]
    incidents = snapshot["incidents"]
    if any(type(items) is not list for items in (trials, results, incidents)):
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    for item in trials:
        trial = _validate_projection(
            item, fields=_TRIAL_FIELDS, hash_field="canonical_trial_projection_hash"
        )
        for field in ("trial_id", "budget_id", "experiment_family", "initiated_by"):
            _require_string(trial[field], identifier=True)
        _require_int(trial["declared_trial_number"], minimum=1)
        _require_int(trial["event_count"])
        if type(trial["has_result_link"]) is not bool:
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        parse_utc(trial["reserved_at"], reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        if trial["latest_event_timestamp"] is not None:
            parse_utc(
                trial["latest_event_timestamp"],
                reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
            )
        _evidence_hash(trial["request_hash"])
        if (
            type(trial["incident_ids"]) is not list
            or any(type(item) is not str for item in trial["incident_ids"])
            or len(trial["incident_ids"]) != len(set(trial["incident_ids"]))
        ):
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        for field in ("latest_sequence_number",):
            if trial[field] is not None and (
                type(trial[field]) is not int or trial[field] < 1
            ):
                raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        for field in (
            "latest_status_token", "latest_reason_token",
            "result_bundle_id", "result_bundle_hash",
        ):
            if trial[field] is not None and type(trial[field]) is not str:
                raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        if trial["result_bundle_hash"] is not None:
            _evidence_hash(trial["result_bundle_hash"])
    for item in results:
        result = _validate_projection(
            item, fields=_RESULT_FIELDS, hash_field="canonical_result_projection_hash"
        )
        for field in (
            "trial_id", "result_bundle_id", "trial_status_token",
            "trial_reason_token", "result_status_token", "result_reason_token",
            "control_identifier", "code_identity", "simulator_identity",
            "execution_model_identity", "cost_model_identity", "risk_model_identity",
        ):
            _require_string(result[field])
        _evidence_hash(result["result_bundle_hash"])
        if result["implementation_repository_commit"] != expected_repository_commit:
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        for field in (
            "gross_result", "net_result", "turnover", "trade_count", "concentration"
        ):
            if type(result[field]) is not int:
                raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        if (
            type(result["artifact_declarations"]) is not list
            or type(result["warnings"]) is not list
            or any(type(item) is not str for item in result["warnings"])
            or type(result["verification_declarations"]) is not dict
            or any(
                type(key) is not str or type(flag) is not bool
                for key, flag in result["verification_declarations"].items()
            )
        ):
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        for declaration in result["artifact_declarations"]:
            declaration = _exact(
                declaration,
                frozenset(
                    {
                        "artifact_id", "artifact_type", "relative_path",
                        "byte_sha256", "canonical_artifact_hash",
                    }
                ),
                "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
            )
            _require_string(declaration["artifact_id"], identifier=True)
            _require_string(declaration["artifact_type"], identifier=True)
            _relative_parts(declaration["relative_path"])
            _evidence_hash(declaration["byte_sha256"])
            _evidence_hash(declaration["canonical_artifact_hash"])
            if (
                declaration["artifact_type"]
                != "CANONICAL_SYNTHETIC_EVENT_LEDGER"
                or declaration["relative_path"]
                != f"{result['trial_id']}/event-ledger.json"
            ):
                raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    for item in incidents:
        incident = _validate_projection(
            item, fields=_INCIDENT_FIELDS, hash_field="canonical_incident_hash"
        )
        _require_string(incident["incident_id"], identifier=True)
        _enum_token(
            incident["severity"],
            INCIDENT_SEVERITIES,
            reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
        )
        _enum_token(
            incident["category"],
            INCIDENT_CATEGORIES,
            reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
        )
        if (
            type(incident["reason_token"]) is not str
            or not incident["reason_token"]
            or type(incident["human_explanation"]) is not str
            or len(incident["human_explanation"]) > MAX_HUMAN_TEXT_LENGTH
            or (
                incident["trial_id"] is not None
                and type(incident["trial_id"]) is not str
            )
            or type(incident["evidence_identities"]) is not dict
        ):
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        parse_utc(
            incident["detected_at"],
            reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
        )
        incident_core = dict(incident)
        incident_core.pop("canonical_incident_hash")
        identity_value = dict(incident_core)
        supplied_id = identity_value.pop("incident_id")
        if supplied_id != f"incident-{canonical_hash(identity_value)[:32]}":
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    identity_fields = {
        "mission_93_contract_id": contract_identities["mission_93"][0],
        "mission_93_contract_hash": contract_identities["mission_93"][1],
        "mission_94_contract_id": contract_identities["mission_94"][0],
        "mission_94_contract_hash": contract_identities["mission_94"][1],
        "mission_95_contract_id": contract_identities["mission_95"][0],
        "mission_95_contract_hash": contract_identities["mission_95"][1],
        "mission_96a_contract_id": contract_identities["mission_96a"][0],
        "mission_96a_contract_hash": contract_identities["mission_96a"][1],
    }
    expected_repository_identity = (
        "sha256:" + canonical_hash({"absolute_path": str(repository_root)})
    )
    _evidence_path_identity(system["ledger_path_identity"])
    _evidence_path_identity(system["result_root_path_identity"])
    _enum_token(
        system["health_token"],
        HEALTH_TOKENS,
        reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
    )
    if (
        system["schema_version"] != SCHEMA_VERSION
        or type(system["snapshot_version"]) is not int
        or system["snapshot_version"] != 1
        or system["snapshot_id"] != snapshot["snapshot_id"]
        or system["repository_commit"] != expected_repository_commit
        or system["as_of"] != observation_as_of
        or system["repository_root_path_identity"] != expected_repository_identity
        or system["contract_verification"] != dict(CONTRACT_VERIFICATION)
        or system["authority_projection"] != dict(CONTROL_PLANE_AUTHORITY)
        or any(system[field] != expected for field, expected in identity_fields.items())
        or any(
            type(system[field]) is not int or system[field] < 0
            for field in (
                "total_budget_count", "total_reservation_count",
                "total_event_count", "total_result_link_count",
                "verified_linked_result_count", "incident_count",
            )
        )
        or system["verified_linked_result_count"] != len(results)
        or system["incident_count"] != len(incidents)
    ):
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    if type(system["lifecycle_counts"]) is not dict or any(
        type(key) is not str or type(count) is not int or count < 0
        for key, count in system["lifecycle_counts"].items()
    ):
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    expected_health = (
        "UNAVAILABLE"
        if any(item["severity"] == "CRITICAL" for item in incidents)
        else "INTEGRITY_FAILURE"
        if any(item["category"] in _INTEGRITY_CATEGORIES for item in incidents)
        else "DEGRADED"
        if incidents
        else "HEALTHY"
    )
    if system["health_token"] != expected_health:
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    trial_ids = [item["trial_id"] for item in trials]
    result_trial_ids = [item["trial_id"] for item in results]
    incident_ids = [item["incident_id"] for item in incidents]
    if (
        len(trial_ids) != len(set(trial_ids))
        or len(result_trial_ids) != len(set(result_trial_ids))
        or not set(result_trial_ids).issubset(trial_ids)
        or len(incident_ids) != len(set(incident_ids))
    ):
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    incident_by_id = {item["incident_id"]: item for item in incidents}
    if any(
        incident_id not in incident_by_id
        or incident_by_id[incident_id]["trial_id"] != trial["trial_id"]
        for trial in trials
        for incident_id in trial["incident_ids"]
    ):
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    expected_trial_order = sorted(
        trials,
        key=lambda item: (
            parse_utc(
                item["reserved_at"],
                reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
            ),
            item["trial_id"],
        ),
    )
    result_order = [
        trial_id for trial_id in trial_ids if trial_id in set(result_trial_ids)
    ]
    expected_incident_order = sorted(
        incidents,
        key=lambda item: (
            item["trial_id"] or "", item["category"], item["incident_id"]
        ),
    )
    lifecycle_counts = {
        key: sum(item["latest_status_token"] == key for item in trials)
        for key in system["lifecycle_counts"]
    }
    if (
        trials != expected_trial_order
        or result_trial_ids != result_order
        or incidents != expected_incident_order
        or system["total_reservation_count"] != len(trials)
        or system["total_event_count"]
        != sum(item["event_count"] for item in trials)
        or system["total_result_link_count"]
        != sum(item["has_result_link"] for item in trials)
        or system["lifecycle_counts"] != lifecycle_counts
    ):
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    identity_system = dict(system)
    identity_system.pop("snapshot_id")
    identity_core = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_version": 1,
        "system": identity_system,
        "trials": trials,
        "results": results,
        "incidents": incidents,
    }
    if snapshot["snapshot_id"] != f"snapshot-{canonical_hash(identity_core)[:32]}":
        raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
    _canonical_hash_matches(
        snapshot,
        "canonical_snapshot_hash",
        "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
    )
    return snapshot


class ResearchDirectorEvidenceLoader:
    """Load only the bounded files authorized by Mission 98."""

    def __init__(
        self,
        *,
        repository_root: Path,
        observation_root: Path,
        input_root: Path,
        expected_repository_commit: str,
    ) -> None:
        self.repository_root = repository_root
        self.observation_root = observation_root
        self.input_root = input_root
        self.expected_repository_commit = expected_repository_commit

    def load_request(
        self, request_relative_path: str
    ) -> tuple[DirectorRequest, ResearchOpportunityDossier | None]:
        _, raw = read_relative_file(
            self.input_root,
            request_relative_path,
            max_bytes=MAX_REQUEST_BYTES,
        )
        request = parse_request(raw, expected_commit=self.expected_repository_commit)
        request_value = request.as_dict()
        dossier = None
        if request_value["proposal_relative_path"] is not None:
            _, dossier_raw = read_relative_file(
                self.input_root,
                request_value["proposal_relative_path"],
                max_bytes=MAX_DOSSIER_BYTES,
            )
            dossier = parse_dossier(
                dossier_raw,
                expected_byte_hash=request_value["proposal_sha256"],
                requested_at=request_value["requested_at"],
            )
        return request, dossier

    def verify(
        self, request: DirectorRequest
    ) -> EvidenceView:
        request_value = request.as_dict()
        contracts = verify_contract_chain(self.repository_root)
        manifest_path = request_value["observation_manifest_relative_path"]
        _, manifest_raw = read_relative_file(
            self.observation_root,
            manifest_path,
            max_bytes=MAX_MANIFEST_BYTES,
            expected_hash=request_value["observation_manifest_sha256"],
        )
        manifest = _exact(
            decode_json(
                manifest_raw,
                max_bytes=MAX_MANIFEST_BYTES,
                reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
            ),
            _MANIFEST_FIELDS,
            "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
        )
        for field in ("manifest_id", "run_id", "source_snapshot_artifact_id", "verification_artifact_id"):
            _require_string(manifest[field], identifier=True)
        _enum_token(
            manifest["system_health_token"],
            HEALTH_TOKENS,
            reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
        )
        if (
            manifest["schema_version"] != SCHEMA_VERSION
            or type(manifest["manifest_version"]) is not int
            or manifest["manifest_version"] != 1
            or manifest["workflow_definition_id"] != WORKFLOW_ID
            or type(manifest["workflow_definition_version"]) is not int
            or manifest["workflow_definition_version"] != 1
            or manifest["workflow_definition_hash"] != WORKFLOW_HASH
            or manifest["repository_commit"] != self.expected_repository_commit
            or manifest["verification_token"] != "CONTROL_PLANE_SNAPSHOT_VERIFIED"
            or manifest["authority_declaration"] != dict(MANIFEST_AUTHORITY)
            or manifest["completed_step_ids"] != [CAPTURE_STEP, VERIFY_STEP, PUBLISH_STEP]
            or type(manifest["incident_count"]) is not int
            or manifest["incident_count"] < 0
        ):
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        for field in (
            "source_snapshot_byte_hash", "source_canonical_snapshot_hash",
            "verification_artifact_byte_hash",
        ):
            _evidence_hash(manifest[field])
        parse_utc(
            manifest["observation_as_of"],
            reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
        )
        expected_manifest_path = (
            f"runs/{manifest['run_id']}/{PUBLISH_STEP}/result.json"
        )
        if manifest_path != expected_manifest_path:
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        manifest_core = dict(manifest)
        supplied_manifest_hash = manifest_core.pop("canonical_manifest_hash", None)
        if canonical_hash(manifest_core) != supplied_manifest_hash:
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        identified = dict(manifest_core)
        manifest_id = identified.pop("manifest_id")
        if manifest_id != f"manifest-{canonical_hash(identified)[:32]}":
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")

        snapshot_relative = f"runs/{manifest['run_id']}/{CAPTURE_STEP}/result.json"
        _, snapshot_raw = read_relative_file(
            self.observation_root,
            snapshot_relative,
            max_bytes=MAX_SNAPSHOT_BYTES,
            expected_hash=manifest["source_snapshot_byte_hash"],
        )
        snapshot = _verify_snapshot(
            decode_json(
                snapshot_raw,
                max_bytes=MAX_SNAPSHOT_BYTES,
                reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
            ),
            expected_repository_commit=self.expected_repository_commit,
            observation_as_of=manifest["observation_as_of"],
            repository_root=self.repository_root,
            contract_identities=contracts,
        )
        if (
            snapshot["snapshot_id"] != manifest["source_snapshot_id"]
            or snapshot["canonical_snapshot_hash"]
            != manifest["source_canonical_snapshot_hash"]
            or snapshot["system"]["health_token"] != manifest["system_health_token"]
            or len(snapshot["incidents"]) != manifest["incident_count"]
        ):
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")

        verification_relative = f"runs/{manifest['run_id']}/{VERIFY_STEP}/result.json"
        _, verification_raw = read_relative_file(
            self.observation_root,
            verification_relative,
            max_bytes=MAX_VERIFICATION_BYTES,
            expected_hash=manifest["verification_artifact_byte_hash"],
        )
        verification = _exact(
            decode_json(
                verification_raw,
                max_bytes=MAX_VERIFICATION_BYTES,
                reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
            ),
            _VERIFICATION_FIELDS,
            "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
        )
        _require_string(verification["verification_id"], identifier=True)
        verification_core = dict(verification)
        supplied_verification_hash = verification_core.pop(
            "canonical_verification_hash", None
        )
        identified_verification = dict(verification_core)
        verification_id = identified_verification.pop("verification_id")
        if (
            canonical_hash(verification_core) != supplied_verification_hash
            or verification_id
            != f"verification-{canonical_hash(identified_verification)[:32]}"
            or verification["schema_version"] != SCHEMA_VERSION
            or type(verification["verification_version"]) is not int
            or verification["verification_version"] != 1
            or verification["source_snapshot_artifact_id"]
            != manifest["source_snapshot_artifact_id"]
            or verification["source_snapshot_byte_hash"]
            != manifest["source_snapshot_byte_hash"]
            or verification["source_snapshot_canonical_hash"]
            != snapshot["canonical_snapshot_hash"]
            or verification["source_snapshot_id"] != snapshot["snapshot_id"]
            or verification["repository_commit"] != self.expected_repository_commit
            or verification["observation_as_of"] != manifest["observation_as_of"]
            or verification["verification_token"]
            != "CONTROL_PLANE_SNAPSHOT_VERIFIED"
        ):
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        expected_warnings = [
            {
                "trial_id": result["trial_id"],
                "result_bundle_id": result["result_bundle_id"],
                "warnings": result["warnings"],
            }
            for result in snapshot["results"]
        ]
        if manifest["warnings_by_trial"] != expected_warnings:
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        observation_time = parse_utc(
            manifest["observation_as_of"],
            reason="OBSERVATION_EVIDENCE_INTEGRITY_FAILURE",
        )
        requested_time = parse_utc(request_value["requested_at"])
        decision_time = parse_utc(request_value["decision_as_of"])
        if observation_time > requested_time:
            raise DirectorError("OBSERVATION_EVIDENCE_INTEGRITY_FAILURE")
        if decision_time < observation_time:
            raise DirectorError("CLOCK_REGRESSION")
        return EvidenceView(
            manifest_byte_hash=sha256_bytes(manifest_raw),
            snapshot_canonical_hash=snapshot["canonical_snapshot_hash"],
            observation_as_of=manifest["observation_as_of"],
            health_token=snapshot["system"]["health_token"],
            incident_severities=tuple(
                item["severity"] for item in snapshot["incidents"]
            ),
            contract_identities=contracts,
            manifest_id=manifest["manifest_id"],
            snapshot_id=snapshot["snapshot_id"],
            verification_id=verification["verification_id"],
        )
