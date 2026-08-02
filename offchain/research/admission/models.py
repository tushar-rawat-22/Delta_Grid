"""Immutable data models and canonical hashing for research admission."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping


REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "request_id",
        "controlling_contract_id",
        "controlling_contract_hash",
        "repository_commit",
        "repository_clean",
        "budget_id",
        "declared_trial_number",
        "dataset_id",
        "dataset_hash",
        "data_class",
        "split_identity",
        "authorization_stage",
        "control_identifier",
        "control_parameters",
        "initiated_by",
        "created_at",
        "canonical_request_hash",
    }
)


def canonical_json(value: Any) -> str:
    """Return the repository-approved compact canonical JSON representation."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_hash(value: Any) -> str:
    """Return the SHA-256 digest of canonical JSON."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class AdmissionError(ValueError):
    """A fail-closed validation error carrying a stable machine reason."""

    def __init__(self, reason_token: str, explanation: str = "") -> None:
        super().__init__(reason_token)
        self.reason_token = reason_token
        self.explanation = explanation


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AdmissionError("REQUEST_SCHEMA_INVALID", f"{field} must be non-empty")
    return value


@dataclass(frozen=True)
class ResearchAdmissionRequest:
    """The exact, hash-bound request envelope accepted by the service."""

    schema_version: str
    request_id: str
    controlling_contract_id: str
    controlling_contract_hash: str
    repository_commit: str
    repository_clean: bool
    budget_id: str
    declared_trial_number: int
    dataset_id: str
    dataset_hash: str
    data_class: str
    split_identity: str
    authorization_stage: str
    control_identifier: str
    control_parameters: Mapping[str, Any]
    initiated_by: str
    created_at: str
    canonical_request_hash: str

    def __post_init__(self) -> None:
        """Detach and freeze hash-bound control parameters."""

        object.__setattr__(
            self,
            "control_parameters",
            MappingProxyType(dict(self.control_parameters)),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ResearchAdmissionRequest":
        """Validate exact fields, basic types, and the canonical request hash."""

        if not isinstance(value, Mapping) or set(value) != REQUEST_FIELDS:
            raise AdmissionError("REQUEST_SCHEMA_INVALID", "request fields are not exact")
        if value["schema_version"] != "1.0":
            raise AdmissionError("REQUEST_SCHEMA_INVALID", "unsupported schema version")
        strings = {
            field: _nonempty_string(value[field], field)
            for field in REQUEST_FIELDS
            if field
            not in {
                "repository_clean",
                "declared_trial_number",
                "control_parameters",
            }
        }
        if type(value["repository_clean"]) is not bool:
            raise AdmissionError(
                "REQUEST_SCHEMA_INVALID", "repository_clean must be a boolean"
            )
        trial_number = value["declared_trial_number"]
        if type(trial_number) is not int or trial_number < 1:
            raise AdmissionError(
                "DECLARED_TRIAL_NUMBER_INVALID",
                "declared_trial_number must be a positive integer",
            )
        parameters = value["control_parameters"]
        if not isinstance(parameters, Mapping):
            raise AdmissionError(
                "CONTROL_PARAMETER_TYPE_INVALID",
                "control_parameters must be a mapping",
            )
        core = dict(value)
        supplied_hash = core.pop("canonical_request_hash")
        if canonical_hash(core) != supplied_hash:
            raise AdmissionError("REQUEST_HASH_MISMATCH", "request hash does not match")
        return cls(
            schema_version=strings["schema_version"],
            request_id=strings["request_id"],
            controlling_contract_id=strings["controlling_contract_id"],
            controlling_contract_hash=strings["controlling_contract_hash"],
            repository_commit=strings["repository_commit"],
            repository_clean=value["repository_clean"],
            budget_id=strings["budget_id"],
            declared_trial_number=trial_number,
            dataset_id=strings["dataset_id"],
            dataset_hash=strings["dataset_hash"],
            data_class=strings["data_class"],
            split_identity=strings["split_identity"],
            authorization_stage=strings["authorization_stage"],
            control_identifier=strings["control_identifier"],
            control_parameters=dict(parameters),
            initiated_by=strings["initiated_by"],
            created_at=strings["created_at"],
            canonical_request_hash=supplied_hash,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a detached dictionary suitable for canonical serialization."""

        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "controlling_contract_id": self.controlling_contract_id,
            "controlling_contract_hash": self.controlling_contract_hash,
            "repository_commit": self.repository_commit,
            "repository_clean": self.repository_clean,
            "budget_id": self.budget_id,
            "declared_trial_number": self.declared_trial_number,
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "data_class": self.data_class,
            "split_identity": self.split_identity,
            "authorization_stage": self.authorization_stage,
            "control_identifier": self.control_identifier,
            "control_parameters": dict(self.control_parameters),
            "initiated_by": self.initiated_by,
            "created_at": self.created_at,
            "canonical_request_hash": self.canonical_request_hash,
        }


@dataclass(frozen=True)
class DatasetResolution:
    """Metadata-only dataset authorization result."""

    schema_version: str
    dataset_id: str
    artifact_id: str
    content_sha256: str
    metadata_sha256: str
    data_class: str
    split_identity: str
    artifact_path: str
    authorization_stage: str
    provenance_reference: str
    reason_token: str
    canonical_resolution_hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidatedControl:
    """An exact non-executable control specification."""

    schema_version: str
    control_identifier: str
    control_parameters: Mapping[str, Any]
    non_alpha: bool
    execution_authorized: bool
    canonical_control_hash: str

    def __post_init__(self) -> None:
        """Detach and freeze hash-bound validated parameters."""

        object.__setattr__(
            self,
            "control_parameters",
            MappingProxyType(dict(self.control_parameters)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "control_identifier": self.control_identifier,
            "control_parameters": dict(self.control_parameters),
            "non_alpha": self.non_alpha,
            "execution_authorized": self.execution_authorized,
            "canonical_control_hash": self.canonical_control_hash,
        }


@dataclass(frozen=True)
class BudgetDefinition:
    """An immutable trial-budget definition."""

    budget_id: str
    controlling_contract_id: str
    controlling_contract_hash: str
    experiment_family: str
    total_trial_budget: int
    created_at: str
    canonical_budget_hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrialReservation:
    """An immutable successful trial reservation."""

    trial_id: str
    budget_id: str
    declared_trial_number: int
    request_hash: str
    initiated_by: str
    reserved_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdmissionDecision:
    """The deterministic terminal output of Mission 94."""

    schema_version: str
    decision_id: str
    request_id: str
    trial_id: str | None
    decision_token: str
    reason_token: str
    dataset_resolution_hash: str | None
    validated_control_hash: str | None
    budget_id: str
    declared_trial_number: int
    created_at: str
    canonical_decision_hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
