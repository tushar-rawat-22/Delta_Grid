"""Immutable recommendation inventory for the Mission 98 Research Director."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class ActionDefinition:
    """One non-executable recommendation token."""

    action_id: str
    recommendation_only: bool = True


ACTION_REGISTRY = (
    ActionDefinition("STOP_NO_ADMISSIBLE_ACTION"),
    ActionDefinition("REQUEST_OBSERVATION_REFRESH"),
    ActionDefinition("REQUEST_MISSING_INTAKE_EVIDENCE"),
    ActionDefinition("REJECT_PROPOSAL_OVERLAP"),
    ActionDefinition("REJECT_POLICY_CONFLICT"),
    ActionDefinition("DRAFT_RESEARCH_REOPENING_CONTRACT"),
    ActionDefinition("QUEUE_FOUNDER_REVIEW"),
)
ACTION_IDS = tuple(item.action_id for item in ACTION_REGISTRY)
ACTION_BY_ID = MappingProxyType({item.action_id: item for item in ACTION_REGISTRY})

POLICY_OUTCOMES = (
    (
        "RULE_1_UPSTREAM_INTEGRITY_STOP",
        "STOP_NO_ADMISSIBLE_ACTION",
        "UPSTREAM_INTEGRITY_STOP",
    ),
    (
        "RULE_2_POLICY_CONFLICT",
        "REJECT_POLICY_CONFLICT",
        "PROPOSAL_REQUESTS_UNAUTHORIZED_STAGE",
    ),
    (
        "RULE_3_OBSERVATION_REFRESH",
        "REQUEST_OBSERVATION_REFRESH",
        "OBSERVATION_REFRESH_REQUIRED",
    ),
    (
        "RULE_4_NO_PROPOSAL",
        "STOP_NO_ADMISSIBLE_ACTION",
        "NO_PROPOSAL_SUPPLIED",
    ),
    (
        "RULE_5_MATERIAL_OVERLAP",
        "REJECT_PROPOSAL_OVERLAP",
        "REJECTED_FAMILY_OVERLAP",
    ),
    (
        "RULE_6_INTAKE_EVIDENCE_INCOMPLETE",
        "REQUEST_MISSING_INTAKE_EVIDENCE",
        "INTAKE_EVIDENCE_INCOMPLETE",
    ),
    (
        "RULE_7_DRAFT_CONTRACT_REQUIRED",
        "DRAFT_RESEARCH_REOPENING_CONTRACT",
        "NOVEL_PROPOSAL_REQUIRES_VERSIONED_CONTRACT",
    ),
    (
        "RULE_8_FOUNDER_REVIEW",
        "QUEUE_FOUNDER_REVIEW",
        "DRAFT_CONTRACT_REQUIRES_FOUNDER_REVIEW",
    ),
)
POLICY_OUTCOME_BY_RULE = MappingProxyType(
    {rule: (action, reason) for rule, action, reason in POLICY_OUTCOMES}
)

EXPLANATIONS = MappingProxyType(
    {
        (
            "STOP_NO_ADMISSIBLE_ACTION",
            "UPSTREAM_INTEGRITY_STOP",
        ): "Verified upstream evidence reports an integrity failure; no further action is admissible.",
        (
            "REJECT_POLICY_CONFLICT",
            "PROPOSAL_REQUESTS_UNAUTHORIZED_STAGE",
        ): "The proposal requests a stage or authority that Mission 98 cannot recommend.",
        (
            "REQUEST_OBSERVATION_REFRESH",
            "OBSERVATION_REFRESH_REQUIRED",
        ): "The verified observation is unavailable, degraded, or older than the fixed freshness limit.",
        (
            "STOP_NO_ADMISSIBLE_ACTION",
            "NO_PROPOSAL_SUPPLIED",
        ): "No research-opportunity dossier was supplied, so there is no admissible proposal to advance.",
        (
            "REJECT_PROPOSAL_OVERLAP",
            "REJECTED_FAMILY_OVERLAP",
        ): "The proposal materially overlaps a rejected research family and must be rejected at intake.",
        (
            "REQUEST_MISSING_INTAKE_EVIDENCE",
            "INTAKE_EVIDENCE_INCOMPLETE",
        ): "The metadata-only intake dossier lacks one or more required evidence declarations.",
        (
            "DRAFT_RESEARCH_REOPENING_CONTRACT",
            "NOVEL_PROPOSAL_REQUIRES_VERSIONED_CONTRACT",
        ): "The proposal is novel enough for a draft reopening contract, but Mission 98 does not create or activate it.",
        (
            "QUEUE_FOUNDER_REVIEW",
            "DRAFT_CONTRACT_REQUIRES_FOUNDER_REVIEW",
        ): "The referenced draft reopening contract requires founder review and remains inactive.",
    }
)

WINNING_RULE_IDS = tuple(rule for rule, _, _ in POLICY_OUTCOMES)
