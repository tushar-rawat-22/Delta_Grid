"""Immutable public models for Mission 97 durable observation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from offchain.research.admission import canonical_json


MISSION_CONTRACT_ID = "deltagrid-durable-workflow-orchestrator-v1"
MISSION_CONTRACT_HASH = (
    "c1840ed9f438f520401bbf24e501bb2a327f4718124745f275474ac76eeab272"
)
MISSION_BASE_COMMIT = "a9f21bffd1d581e96a947854b30a961af770d7f1"
MISSION_AUTHORIZATION_STAGE = "MISSION_97_BOUNDED_OBSERVATION_ORCHESTRATION"

_ERROR_EXPLANATIONS = {
    "ACTION_NOT_AUTHORIZED": "The requested action is not in the fixed Mission 97 inventory.",
    "ARTIFACT_CONFLICT": "A different artifact already occupies the derived immutable path.",
    "ARTIFACT_HASH_MISMATCH": "The artifact bytes do not match their accepted receipt.",
    "ARTIFACT_PATH_UNSAFE": "The derived local artifact path failed safety validation.",
    "ARTIFACT_TEMPORARILY_UNAVAILABLE": "The required local artifact is temporarily unavailable.",
    "CLOCK_REGRESSION": "An explicit operational timestamp moved backward.",
    "GOVERNANCE_CONTRACT_INTEGRITY_FAILURE": "The bound governance contract chain failed verification.",
    "INTERNAL_INTEGRITY_FAILURE": "An unexpected internal failure was classified fail-closed.",
    "INVALID_WORKFLOW_TRANSITION": "The persisted workflow history contains an invalid transition.",
    "LEASE_EXPIRED_BEFORE_FINALIZATION": "The accepted claim lease expired before finalization.",
    "ORCHESTRATION_DATABASE_BUSY": "The orchestration database is temporarily busy.",
    "ORCHESTRATION_ROW_INTEGRITY_FAILURE": "A persisted orchestration row failed integrity verification.",
    "ORCHESTRATION_SCHEMA_INCOMPATIBLE": "The orchestration database schema is incompatible.",
    "REPOSITORY_CONTRACT_INTEGRITY_FAILURE": "The snapshot repository identities failed verification.",
    "RESEARCH_LEDGER_INTEGRITY_FAILURE": "The read-only research ledger failed integrity verification.",
    "RESOURCE_LIMIT_EXCEEDED": "A fixed Mission 97 resource limit was exceeded.",
    "RUN_KEY_CONFLICT": "The run key already identifies different canonical input.",
    "SNAPSHOT_INTEGRITY_FAILURE": "The control-plane snapshot failed independent integrity verification.",
    "SNAPSHOT_SCHEMA_UNSUPPORTED": "The control-plane snapshot schema is unsupported.",
    "SNAPSHOT_TEMPORARILY_UNAVAILABLE": "The read-only control-plane snapshot is temporarily unavailable.",
    "SQLITE_BUSY": "The local SQLite database is temporarily busy.",
    "STALE_FENCING_TOKEN": "The private claim authorization is stale or expired.",
    "WORKFLOW_DEFINITION_MISMATCH": "The workflow definition does not match the compiled Mission 97 workflow.",
    "WORKFLOW_INPUT_INVALID": "The supplied Mission 97 input is invalid.",
}


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def detached(value: Any) -> Any:
    """Return a deep JSON-compatible copy without leaking stored containers."""

    def convert(item: Any) -> Any:
        if isinstance(item, Enum):
            return item.value
        if isinstance(item, Mapping):
            return {str(key): convert(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(child) for child in item]
        return item

    return json.loads(canonical_json(convert(value)))


class OrchestrationError(ValueError):
    """Fail-closed error with a stable machine-readable reason token."""

    def __init__(self, reason_token: str, explanation: str = "") -> None:
        super().__init__(reason_token)
        self.reason_token = reason_token
        self.explanation = _ERROR_EXPLANATIONS.get(
            reason_token, explanation or "The operation failed closed."
        )


class WorkflowStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_RETRY = "WAITING_RETRY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TickOutcome(str, Enum):
    STEP_SUCCEEDED = "STEP_SUCCEEDED"
    STEP_RETRY_SCHEDULED = "STEP_RETRY_SCHEDULED"
    STEP_TERMINALLY_FAILED = "STEP_TERMINALLY_FAILED"
    EXPIRED_CLAIM_RECOVERED = "EXPIRED_CLAIM_RECOVERED"
    RUN_CANCELLED = "RUN_CANCELLED"
    IDLE = "IDLE"
    MAX_TICKS_REACHED = "MAX_TICKS_REACHED"


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    action_id: str

    def as_dict(self) -> dict[str, str]:
        return {"step_id": self.step_id, "action_id": self.action_id}


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_definition_id: str
    workflow_definition_version: int
    steps: tuple[WorkflowStep, ...]
    maximum_attempts_per_step: int
    retry_delays_seconds: tuple[int, ...]
    canonical_workflow_definition_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.steps, (list, tuple)):
            raise TypeError("steps must be a sequence")
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(
            self, "retry_delays_seconds", tuple(self.retry_delays_seconds)
        )

    def identity_core(self) -> dict[str, Any]:
        return {
            "workflow_definition_id": self.workflow_definition_id,
            "workflow_definition_version": self.workflow_definition_version,
            "steps": [step.as_dict() for step in self.steps],
            "retry_policy": {
                "maximum_attempts_per_step": self.maximum_attempts_per_step,
                "retry_delays_seconds": list(self.retry_delays_seconds),
            },
        }

    def as_dict(self) -> dict[str, Any]:
        return detached(
            {
                **self.identity_core(),
                "canonical_workflow_definition_hash": (
                    self.canonical_workflow_definition_hash
                ),
            }
        )


@dataclass(frozen=True)
class WorkflowRunSnapshot:
    schema_version: str
    run_id: str
    run_key: str
    workflow_definition_id: str
    workflow_definition_version: int
    workflow_definition_hash: str
    canonical_input_hash: str
    status: WorkflowStatus
    current_step_id: str | None
    next_attempt_number: int | None
    next_runnable_at: str | None
    active_claim: Mapping[str, Any] | None
    successful_step_ids: tuple[str, ...]
    receipt_identities: tuple[Mapping[str, Any], ...]
    artifact_identities: tuple[Mapping[str, Any], ...]
    last_event: Mapping[str, Any] | None
    event_count: int
    retry_count: int
    requested_at: str
    requested_by: str
    completed_at: str | None
    terminal_reason_token: str | None
    canonical_run_snapshot_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_claim", _freeze(self.active_claim))
        object.__setattr__(
            self, "successful_step_ids", tuple(self.successful_step_ids)
        )
        object.__setattr__(
            self, "receipt_identities", tuple(_freeze(x) for x in self.receipt_identities)
        )
        object.__setattr__(
            self, "artifact_identities", tuple(_freeze(x) for x in self.artifact_identities)
        )
        object.__setattr__(self, "last_event", _freeze(self.last_event))

    def as_dict(self) -> dict[str, Any]:
        return detached(
            {
                field: getattr(self, field)
                for field in self.__dataclass_fields__
            }
        )


@dataclass(frozen=True)
class TickResult:
    outcome: TickOutcome
    run: WorkflowRunSnapshot | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "run": None if self.run is None else self.run.as_dict(),
        }


def freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return _freeze(value)
