"""Immutable models for the synthetic-only canonical result engine."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from offchain.research.admission import canonical_hash


MISSION_CONTRACT_ID = "deltagrid-canonical-result-engine-service-v1"
MISSION_CONTRACT_HASH = (
    "d8fcd1169e638b648f8b5fccb389dfd090b016beb80e9e13d7f0a0af3210aa6a"
)
MISSION_BASE_COMMIT = "ac2440952d2b330344cbaef299c4378a7afd45af"
MISSION_AUTHORIZATION_STAGE = "MISSION_95_SYNTHETIC_CONTROL_EXECUTION"
PRECEDING_CONTRACT_PATH = "contracts/DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json"
PRECEDING_CONTRACT_HASH = (
    "e4070b52a0f2dbc8ce34ea00d0a732c2aed25c9c21e5acfccc3f9d791dba6193"
)
RESULT_BUNDLE_VERSION = 1


REASON_EXPLANATIONS = MappingProxyType(
    {
        "ADMISSION_DECISION_NOT_ADMITTED": "The decision does not admit this trial.",
        "ADMISSION_DECISION_HASH_MISMATCH": "The admission decision identity is invalid.",
        "ADMISSION_IDENTITY_MISMATCH": "The request and admission identities do not match.",
        "TRIAL_STATE_NOT_ADMITTED": "The trial is not in an executable admitted state.",
        "TRIAL_RESERVATION_MISMATCH": "The immutable trial reservation does not match the request.",
        "SYNTHETIC_FIXTURE_PATH_UNSAFE": "The fixture path is outside the configured artifact root or otherwise unsafe.",
        "SYNTHETIC_FIXTURE_MISSING": "The authorized synthetic fixture is not a regular file.",
        "SYNTHETIC_FIXTURE_HASH_MISMATCH": "The fixture bytes do not match the admitted content hash.",
        "SYNTHETIC_FIXTURE_SCHEMA_INVALID": "The synthetic fixture schema or canonical encoding is invalid.",
        "CONTROL_EXECUTION_FAILED": "The fixed synthetic control could not complete safely.",
        "RESULT_PATH_UNSAFE": "The derived result path is outside the configured result root or otherwise unsafe.",
        "RESULT_WRITE_FAILED": "A canonical result artifact could not be published safely.",
        "RESULT_SCHEMA_INVALID": "A result artifact does not have the exact canonical schema.",
        "RESULT_HASH_MISMATCH": "A canonical result identity does not match its content.",
        "RESULT_ARTIFACT_MISMATCH": "The event ledger or immutable result link does not match the bundle.",
        "SYNTHETIC_CONTROL_COMPLETED": "The admitted synthetic control completed and its result was linked.",
        "RESULT_VERIFIED": "The canonical result bundle and its declared artifacts were verified.",
        "SYNTHETIC_CONTROL_RESULT_VERIFIED": "The synthetic control calculation and canonical artifacts were verified.",
        "TRIAL_TERMINALIZATION_FAILED": "The securely bound trial failure could not be persisted.",
        "IMPLEMENTATION_REPOSITORY_COMMIT_INVALID": "The trusted implementation repository commit is invalid.",
        "SQLITE_CONTENTION": "The bounded SQLite transaction could not acquire its lock.",
        "INTERNAL_INTEGRITY_FAILURE": "An internal deterministic integrity check failed.",
    }
)


class EngineError(ValueError):
    """Fail-closed engine error with a stable machine reason."""

    def __init__(
        self,
        reason_token: str,
        *,
        original_reason_token: str | None = None,
    ) -> None:
        super().__init__(reason_token)
        self.reason_token = reason_token
        self.original_reason_token = original_reason_token
        self.explanation = REASON_EXPLANATIONS.get(
            reason_token,
            REASON_EXPLANATIONS["INTERNAL_INTEGRITY_FAILURE"],
        )


@dataclass(frozen=True)
class SyntheticEvent:
    event_id: str
    timestamp: str
    mid_price_units: int
    available_fill_bps: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "mid_price_units": self.mid_price_units,
            "available_fill_bps": self.available_fill_bps,
        }


@dataclass(frozen=True)
class SyntheticFixture:
    schema_version: str
    fixture_id: str
    instrument_id: str
    currency_unit: str
    initial_cash_units: int
    trade_quantity_units: int
    fee_bps: int
    slippage_bps: int
    events: tuple[SyntheticEvent, ...]
    canonical_fixture_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "fixture_id": self.fixture_id,
            "instrument_id": self.instrument_id,
            "currency_unit": self.currency_unit,
            "initial_cash_units": self.initial_cash_units,
            "trade_quantity_units": self.trade_quantity_units,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "events": [event.as_dict() for event in self.events],
            "canonical_fixture_hash": self.canonical_fixture_hash,
        }


@dataclass(frozen=True)
class ExecutionPermit:
    schema_version: str
    scope: str
    request_hash: str
    decision_hash: str
    trial_id: str
    dataset_resolution_hash: str
    validated_control_hash: str
    canonical_permit_hash: str

    @classmethod
    def issue(
        cls,
        *,
        request_hash: str,
        decision_hash: str,
        trial_id: str,
        dataset_resolution_hash: str,
        validated_control_hash: str,
    ) -> "ExecutionPermit":
        core = {
            "schema_version": "1.0",
            "scope": "MISSION_95_SYNTHETIC_CONTROL_ONLY",
            "request_hash": request_hash,
            "decision_hash": decision_hash,
            "trial_id": trial_id,
            "dataset_resolution_hash": dataset_resolution_hash,
            "validated_control_hash": validated_control_hash,
        }
        return cls(**core, canonical_permit_hash=canonical_hash(core))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scope": self.scope,
            "request_hash": self.request_hash,
            "decision_hash": self.decision_hash,
            "trial_id": self.trial_id,
            "dataset_resolution_hash": self.dataset_resolution_hash,
            "validated_control_hash": self.validated_control_hash,
            "canonical_permit_hash": self.canonical_permit_hash,
        }


@dataclass(frozen=True)
class ExecutionOutcome:
    rows: tuple[Mapping[str, Any], ...]
    metrics: Mapping[str, Any]
    final_state: str
    targets_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rows",
            tuple(MappingProxyType(dict(row)) for row in self.rows),
        )
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))


_RESULT_BUNDLE_CONSTRUCTION_TOKEN = object()


@dataclass(frozen=True, init=False)
class ResultBundle:
    """Deeply immutable canonical bytes for one verified result bundle."""

    _canonical_bytes: bytes

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("ResultBundle values are produced only by verified loading")

    @classmethod
    def _from_verified_bytes(
        cls,
        canonical_bytes: bytes,
        construction_token: object,
    ) -> "ResultBundle":
        if (
            construction_token is not _RESULT_BUNDLE_CONSTRUCTION_TOKEN
            or type(canonical_bytes) is not bytes
        ):
            raise TypeError("ResultBundle requires verified canonical bytes")
        instance = object.__new__(cls)
        object.__setattr__(instance, "_canonical_bytes", canonical_bytes)
        return instance

    @property
    def result_bundle_id(self) -> str:
        return str(self.as_dict()["result_bundle_id"])

    @property
    def canonical_result_hash(self) -> str:
        return str(self.as_dict()["canonical_result_hash"])

    @property
    def trial_id(self) -> str:
        return str(self.as_dict()["admission"]["trial_id"])

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON round-trip copy of the verified bundle."""

        from .strict_json import detached_json_value

        return detached_json_value(self._canonical_bytes)


@dataclass(frozen=True)
class LinkedResult:
    """Verified result bytes plus authoritative persisted trial lifecycle."""

    result_bundle: ResultBundle
    trial_status_token: str
    trial_reason_token: str
    trial_linked_at: str

    @property
    def result_bundle_id(self) -> str:
        return self.result_bundle.result_bundle_id

    @property
    def canonical_result_hash(self) -> str:
        return self.result_bundle.canonical_result_hash

    @property
    def trial_id(self) -> str:
        return self.result_bundle.trial_id
