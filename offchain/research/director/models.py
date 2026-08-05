"""Strict immutable models and canonical identities for Mission 98."""

from __future__ import annotations

from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Any, Mapping

from offchain.research.admission import canonical_hash, canonical_json


SCHEMA_VERSION = "1.0"
DATABASE_SCHEMA_VERSION = 1
MISSION_CONTRACT_ID = "deltagrid-autonomous-research-director-v1"
MISSION_CONTRACT_HASH = (
    "3fcf4460762af5c45d2351c10652947f87d2f200e2d9e058b39feb10e5615a55"
)
MISSION_BASE_COMMIT = "eab9ed19a2f77f31eb57daf5929aed479d43c540"
MISSION_AUTHORIZATION_STAGE = "MISSION_98_DECISION_ONLY_RESEARCH_DIRECTION"
MAX_RECORDED_DECISIONS = 10_000
DEFAULT_BUSY_TIMEOUT_MS = 5_000
MIN_BUSY_TIMEOUT_MS = 100
MAX_BUSY_TIMEOUT_MS = 30_000

MAX_REQUEST_BYTES = 65_536
MAX_DOSSIER_BYTES = 65_536
MAX_SNAPSHOT_BYTES = 4_194_304
MAX_VERIFICATION_BYTES = 1_048_576
MAX_MANIFEST_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
MAX_IDENTIFIER_LENGTH = 128
MAX_RELATIVE_PATH_LENGTH = 4_096
MAX_HUMAN_TEXT_LENGTH = 4_096
MAX_REASON_LENGTH = 1_024

REQUEST_FIELDS = (
    "schema_version",
    "request_id",
    "controlling_contract_id",
    "controlling_contract_hash",
    "repository_commit",
    "repository_clean",
    "observation_manifest_relative_path",
    "observation_manifest_sha256",
    "proposal_relative_path",
    "proposal_sha256",
    "decision_as_of",
    "requested_at",
    "requested_by",
    "canonical_request_hash",
)

DOSSIER_FIELDS = (
    "schema_version",
    "proposal_id",
    "proposal_kind",
    "economic_mechanism",
    "falsifiable_claim",
    "new_information_type",
    "new_information_reference",
    "provenance_status",
    "causal_availability_status",
    "overlap_audit_status",
    "compared_rejected_family_ids",
    "overlap_evidence_references",
    "requested_stage",
    "requested_authorities",
    "draft_reopening_contract_reference",
    "created_at",
    "canonical_dossier_hash",
)

REQUESTED_AUTHORITY_FIELDS = (
    "strategy_research_execution",
    "market_data_access",
    "development_market_evaluation",
    "validation_access",
    "holdout_access",
    "protected_data_access",
    "model_training",
    "model_promotion",
    "signal_generation",
    "portfolio_construction",
    "paper_trading",
    "live_trading",
    "exchange_access",
    "credential_access",
    "capital_deployment",
    "autonomous_promotion",
    "autonomous_trading_execution",
)

REJECTED_FAMILY_IDS = (
    "MISSION_89_FUNDING_BASIS_CARRY",
    "MISSION_90_DIRECTIONAL",
    "ALPHA_SEARCH_A_MACRO_REGIME",
    "ALPHA_SEARCH_B_TRADE_FLOW_LEAD_LAG",
)

NEW_INFORMATION_TYPES = frozenset(
    {
        "INDEPENDENT_ACADEMIC_EVIDENCE",
        "INDEPENDENT_PROFESSIONAL_EVIDENCE",
        "NEW_CAUSALLY_AVAILABLE_DATASET",
        "FORWARD_OBSERVED_EFFECT",
        "MATERIAL_MARKET_STRUCTURE_CHANGE",
        "DISTINCT_ASSET_CLASS_OR_INSTRUMENT",
        "EXTERNAL_AUDITABLE_STRATEGY",
    }
)
PROVENANCE_STATUSES = frozenset({"VERIFIED", "UNVERIFIED", "MISSING"})
CAUSAL_STATUSES = frozenset(
    {"SUPPORTED", "UNSUPPORTED", "INCONCLUSIVE", "NOT_ASSESSED"}
)
OVERLAP_STATUSES = frozenset(
    {"NO_MATERIAL_OVERLAP", "MATERIAL_OVERLAP", "INCONCLUSIVE", "NOT_PERFORMED"}
)
REQUESTED_STAGES = frozenset(
    {
        "DRAFT_REOPENING_CONTRACT_ONLY",
        "DEVELOPMENT_RESEARCH",
        "VALIDATION",
        "HOLDOUT",
        "PAPER_TRADING",
        "LIVE_TRADING",
        "CAPITAL_DEPLOYMENT",
    }
)
REQUESTED_BY_VALUES = frozenset({"FOUNDER", "OPERATOR", "FUTURE_AUTOMATION"})

DECISION_FIELDS = (
    "schema_version",
    "decision_id",
    "request_id",
    "proposal_id",
    "selected_action_id",
    "reason_token",
    "winning_rule_id",
    "observation_manifest_byte_hash",
    "observation_snapshot_canonical_hash",
    "proposal_byte_hash",
    "mission_93_contract_id",
    "mission_93_contract_hash",
    "mission_94_contract_id",
    "mission_94_contract_hash",
    "mission_95_contract_id",
    "mission_95_contract_hash",
    "mission_96a_contract_id",
    "mission_96a_contract_hash",
    "mission_96b_contract_id",
    "mission_96b_contract_hash",
    "mission_97_contract_id",
    "mission_97_contract_hash",
    "mission_98_contract_id",
    "mission_98_contract_hash",
    "repository_commit",
    "observation_as_of",
    "decision_as_of",
    "requested_by",
    "human_explanation",
    "canonical_decision_hash",
)

VERIFICATION_FIELDS = (
    "schema_version",
    "verification_id",
    "decision_id",
    "decision_hash",
    "independently_recomputed_action_id",
    "independently_recomputed_reason_token",
    "independently_recomputed_rule_id",
    "verification_token",
    "verified_at",
    "verifier_version",
    "canonical_verification_hash",
)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def detached(value: Any) -> Any:
    """Return a deterministic deep JSON copy."""

    return json.loads(canonical_json(_json_value(value)))


def frozen(value: Any) -> Any:
    """Return recursively immutable containers."""

    if isinstance(value, Mapping):
        return MappingProxyType({str(key): frozen(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(frozen(item) for item in value)
    return value


_ERROR_EXPLANATIONS = MappingProxyType(
    {
        "DIRECTOR_INPUT_INVALID": "The supplied Director input is invalid.",
        "DIRECTOR_PATH_UNSAFE": "A required path is missing, unsafe, or outside its bound root.",
        "DIRECTOR_RESOURCE_LIMIT_EXCEEDED": "A fixed Mission 98 resource limit was exceeded.",
        "GOVERNANCE_CONTRACT_INTEGRITY_FAILURE": "The required Mission 93–98 governance chain did not verify.",
        "OBSERVATION_EVIDENCE_INTEGRITY_FAILURE": "The Mission 97 observation evidence did not verify independently.",
        "CLOCK_REGRESSION": "An input timestamp precedes the evidence or request timestamp it must follow.",
        "DIRECTOR_SCHEMA_INCOMPATIBLE": "The Director database schema or immutable metadata is incompatible.",
        "DIRECTOR_ROW_INTEGRITY_FAILURE": "A persisted Director row failed deterministic integrity verification.",
        "DIRECTOR_DATABASE_BUSY": "The Director database is busy; no mutation was committed.",
        "DECISION_INTEGRITY_FAILURE": "The independently recomputed decision disagrees with the supplied decision.",
        "DECISION_ID_CONFLICT": "A deterministic decision identity conflicts with persisted content.",
        "REQUEST_ID_CONFLICT": "The request identity already exists with different canonical content.",
        "DECISION_BUDGET_EXHAUSTED": "The fixed 10,000-decision recording capacity is exhausted.",
        "DECISION_NOT_FOUND": "The requested recorded decision package does not exist.",
        "INTERNAL_INTEGRITY_FAILURE": "Mission 98 stopped because of an unexpected internal integrity failure.",
    }
)


class DirectorError(ValueError):
    """Fail-closed error with a stable reason token and bounded explanation."""

    def __init__(self, reason_token: str, explanation: str = "") -> None:
        if not explanation:
            explanation = _ERROR_EXPLANATIONS.get(
                reason_token, "Mission 98 rejected the operation."
            )
        super().__init__(reason_token)
        self.reason_token = reason_token
        self.explanation = explanation[:MAX_REASON_LENGTH]


@dataclass(frozen=True)
class DirectorRequest:
    """Canonical validated decision request."""

    value: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", frozen(self.value))

    def as_dict(self) -> dict[str, Any]:
        return detached(self.value)


@dataclass(frozen=True)
class ResearchOpportunityDossier:
    """Canonical validated metadata-only intake dossier."""

    value: Mapping[str, Any]
    byte_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", frozen(self.value))

    def as_dict(self) -> dict[str, Any]:
        return detached(self.value)


@dataclass(frozen=True)
class EvidenceView:
    """Independently verified, policy-relevant Mission 97 evidence."""

    manifest_byte_hash: str
    snapshot_canonical_hash: str
    observation_as_of: str
    health_token: str
    incident_severities: tuple[str, ...]
    contract_identities: Mapping[str, tuple[str, str]]
    manifest_id: str
    snapshot_id: str
    verification_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "incident_severities", tuple(self.incident_severities))
        object.__setattr__(self, "contract_identities", frozen(self.contract_identities))


@dataclass(frozen=True)
class ResearchDecision:
    """One canonical, non-executable Mission 98 recommendation."""

    value: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", frozen(self.value))

    def as_dict(self) -> dict[str, Any]:
        return detached(self.value)


@dataclass(frozen=True)
class VerificationReceipt:
    """Canonical independent verification of one recommendation."""

    value: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", frozen(self.value))

    def as_dict(self) -> dict[str, Any]:
        return detached(self.value)


@dataclass(frozen=True)
class DecisionPackage:
    """Complete request, decision, and verification receipt."""

    request: DirectorRequest
    decision: ResearchDecision
    verification_receipt: VerificationReceipt

    def as_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.as_dict(),
            "decision": self.decision.as_dict(),
            "verification_receipt": self.verification_receipt.as_dict(),
        }


def with_canonical_hash(
    core: Mapping[str, Any], hash_field: str
) -> dict[str, Any]:
    value = detached(core)
    value[hash_field] = canonical_hash(value)
    return value
