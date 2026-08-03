"""Immutable models and fixed authority for the Mission 96A control plane."""

from __future__ import annotations

from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Any, Mapping

from offchain.research.admission import canonical_json


MISSION_CONTRACT_ID = "deltagrid-research-control-plane-v1"
MISSION_CONTRACT_HASH = (
    "c1e0c8c55db90fe8a81d3afe2d243537c703dbee6a945596f4b37c5ee13e70a9"
)
MISSION_BASE_COMMIT = "574e07d9d57cbddf53defc5e48510c96ed6fc58a"
MISSION_AUTHORIZATION_STAGE = "MISSION_96A_READ_ONLY_CONTROL_PLANE"
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
SNAPSHOT_SCHEMA_VERSION = "1.0"
SNAPSHOT_VERSION = 1

AUTHORITY = MappingProxyType(
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
INCIDENT_SEVERITIES = frozenset({"INFO", "WARNING", "ERROR", "CRITICAL"})
HEALTH_TOKENS = frozenset(
    {"HEALTHY", "DEGRADED", "INTEGRITY_FAILURE", "UNAVAILABLE"}
)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _detached(value: Any) -> Any:
    """Return a deep JSON-compatible copy without leaking stored containers."""

    def json_value(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {str(key): json_value(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [json_value(child) for child in item]
        return item

    return json.loads(canonical_json(json_value(value)))


class ControlPlaneError(ValueError):
    """A fail-closed error carrying a stable operator-facing reason."""

    def __init__(self, reason_token: str, explanation: str = "") -> None:
        super().__init__(reason_token)
        self.reason_token = reason_token
        self.explanation = explanation


@dataclass(frozen=True)
class SystemProjection:
    schema_version: str
    snapshot_id: str
    snapshot_version: int
    as_of: str
    repository_commit: str
    mission_93_contract_id: str
    mission_93_contract_hash: str
    mission_94_contract_id: str
    mission_94_contract_hash: str
    mission_95_contract_id: str
    mission_95_contract_hash: str
    mission_96a_contract_id: str
    mission_96a_contract_hash: str
    ledger_path_identity: str
    result_root_path_identity: str
    repository_root_path_identity: str
    contract_verification: Mapping[str, bool]
    total_budget_count: int
    total_reservation_count: int
    total_event_count: int
    total_result_link_count: int
    lifecycle_counts: Mapping[str, int]
    verified_linked_result_count: int
    incident_count: int
    health_token: str
    authority_projection: Mapping[str, bool]

    def __post_init__(self) -> None:
        object.__setattr__(self, "lifecycle_counts", _freeze(self.lifecycle_counts))
        object.__setattr__(
            self, "contract_verification", _freeze(self.contract_verification)
        )
        object.__setattr__(
            self, "authority_projection", _freeze(self.authority_projection)
        )

    def as_dict(self) -> dict[str, Any]:
        return _detached(
            {
                field: getattr(self, field)
                for field in self.__dataclass_fields__
            }
        )


@dataclass(frozen=True)
class TrialProjection:
    trial_id: str
    budget_id: str
    experiment_family: str
    declared_trial_number: int
    initiated_by: str
    reserved_at: str
    request_hash: str
    latest_sequence_number: int | None
    latest_status_token: str | None
    latest_reason_token: str | None
    latest_event_timestamp: str | None
    event_count: int
    has_result_link: bool
    result_verification_token: str
    result_bundle_id: str | None
    result_bundle_hash: str | None
    incident_ids: tuple[str, ...]
    canonical_trial_projection_hash: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.incident_ids, (list, tuple))
            or any(not isinstance(item, str) for item in self.incident_ids)
        ):
            raise TypeError("incident_ids must contain only strings")
        object.__setattr__(self, "incident_ids", tuple(self.incident_ids))

    def as_dict(self) -> dict[str, Any]:
        return _detached(
            {
                field: getattr(self, field)
                for field in self.__dataclass_fields__
            }
        )


@dataclass(frozen=True)
class ResultProjection:
    trial_id: str
    result_bundle_id: str
    result_bundle_hash: str
    trial_status_token: str
    trial_reason_token: str
    result_status_token: str
    result_reason_token: str
    human_explanation: str
    control_identifier: str
    control_parameters: Mapping[str, Any]
    dataset_identity: Mapping[str, Any]
    code_identity: str
    simulator_identity: str
    execution_model_identity: str
    cost_model_identity: str
    risk_model_identity: str
    implementation_repository_commit: str
    gross_result: int
    net_result: int
    benchmark: Mapping[str, Any]
    costs_by_component: Mapping[str, int]
    maximum_drawdown: Mapping[str, int]
    exposure: Mapping[str, int]
    turnover: int
    trade_count: int
    concentration: int
    timing_diagnostics: Mapping[str, Any]
    protected_access_counts: Mapping[str, int]
    artifact_declarations: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...]
    verification_declarations: Mapping[str, bool]
    canonical_result_projection_hash: str

    def __post_init__(self) -> None:
        for field in (
            "control_parameters",
            "dataset_identity",
            "benchmark",
            "costs_by_component",
            "maximum_drawdown",
            "exposure",
            "timing_diagnostics",
            "protected_access_counts",
            "artifact_declarations",
            "warnings",
            "verification_declarations",
        ):
            object.__setattr__(self, field, _freeze(getattr(self, field)))

    def as_dict(self) -> dict[str, Any]:
        return _detached(
            {
                field: getattr(self, field)
                for field in self.__dataclass_fields__
            }
        )


@dataclass(frozen=True)
class IncidentProjection:
    incident_id: str
    severity: str
    category: str
    reason_token: str
    human_explanation: str
    trial_id: str | None
    detected_at: str
    evidence_identities: Mapping[str, Any]
    canonical_incident_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "evidence_identities", _freeze(self.evidence_identities)
        )

    def as_dict(self) -> dict[str, Any]:
        return _detached(
            {
                field: getattr(self, field)
                for field in self.__dataclass_fields__
            }
        )


@dataclass(frozen=True)
class ControlPlaneSnapshot:
    schema_version: str
    snapshot_id: str
    snapshot_version: int
    system: SystemProjection
    trials: tuple[TrialProjection, ...]
    results: tuple[ResultProjection, ...]
    incidents: tuple[IncidentProjection, ...]
    canonical_snapshot_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.system, SystemProjection):
            raise TypeError("system must be a SystemProjection")
        inventories = (
            ("trials", self.trials, TrialProjection),
            ("results", self.results, ResultProjection),
            ("incidents", self.incidents, IncidentProjection),
        )
        for field, values, expected_type in inventories:
            if (
                not isinstance(values, (list, tuple))
                or any(not isinstance(item, expected_type) for item in values)
            ):
                raise TypeError(f"{field} contains an invalid model")
            object.__setattr__(self, field, tuple(values))

    def as_dict(self) -> dict[str, Any]:
        return _detached(
            {
                "schema_version": self.schema_version,
                "snapshot_id": self.snapshot_id,
                "snapshot_version": self.snapshot_version,
                "system": self.system.as_dict(),
                "trials": [item.as_dict() for item in self.trials],
                "results": [item.as_dict() for item in self.results],
                "incidents": [item.as_dict() for item in self.incidents],
                "canonical_snapshot_hash": self.canonical_snapshot_hash,
            }
        )
