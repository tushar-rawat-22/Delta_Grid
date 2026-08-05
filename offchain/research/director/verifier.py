"""Independent policy and decision verifier for Mission 98."""

from __future__ import annotations

from datetime import timedelta

from offchain.research.admission import canonical_hash

from .action_registry import ACTION_BY_ID, EXPLANATIONS, WINNING_RULE_IDS
from .evidence import parse_utc
from .models import (
    DECISION_FIELDS,
    SCHEMA_VERSION,
    VERIFICATION_FIELDS,
    DirectorError,
    DirectorRequest,
    EvidenceView,
    ResearchDecision,
    ResearchOpportunityDossier,
    VerificationReceipt,
)


class ResearchDirectorVerifier:
    """Recompute a recommendation without invoking the decision service."""

    @staticmethod
    def _independent_policy(
        request: DirectorRequest,
        dossier: ResearchOpportunityDossier | None,
        evidence: EvidenceView,
    ) -> tuple[str, str, str]:
        request_data = request.as_dict()
        dossier_data = dossier.as_dict() if dossier is not None else None
        integrity_stop = evidence.health_token == "INTEGRITY_FAILURE" or any(
            item == "ERROR" or item == "CRITICAL"
            for item in evidence.incident_severities
        )
        if integrity_stop:
            action = "STOP_NO_ADMISSIBLE_ACTION"
            reason = "UPSTREAM_INTEGRITY_STOP"
            rule = "RULE_1_UPSTREAM_INTEGRITY_STOP"
        elif dossier_data is not None and (
            dossier_data["requested_stage"] != "DRAFT_REOPENING_CONTRACT_ONLY"
            or any(
                flag is True
                for flag in dossier_data["requested_authorities"].values()
            )
        ):
            action = "REJECT_POLICY_CONFLICT"
            reason = "PROPOSAL_REQUESTS_UNAUTHORIZED_STAGE"
            rule = "RULE_2_POLICY_CONFLICT"
        else:
            age = (
                parse_utc(request_data["decision_as_of"])
                - parse_utc(evidence.observation_as_of)
            )
            if (
                evidence.health_token == "DEGRADED"
                or evidence.health_token == "UNAVAILABLE"
                or age > timedelta(days=1)
            ):
                action = "REQUEST_OBSERVATION_REFRESH"
                reason = "OBSERVATION_REFRESH_REQUIRED"
                rule = "RULE_3_OBSERVATION_REFRESH"
            elif dossier_data is None:
                action = "STOP_NO_ADMISSIBLE_ACTION"
                reason = "NO_PROPOSAL_SUPPLIED"
                rule = "RULE_4_NO_PROPOSAL"
            elif dossier_data["overlap_audit_status"] == "MATERIAL_OVERLAP":
                action = "REJECT_PROPOSAL_OVERLAP"
                reason = "REJECTED_FAMILY_OVERLAP"
                rule = "RULE_5_MATERIAL_OVERLAP"
            elif (
                len(dossier_data["compared_rejected_family_ids"]) < 4
                or dossier_data["overlap_audit_status"]
                in ("INCONCLUSIVE", "NOT_PERFORMED")
                or dossier_data["provenance_status"] != "VERIFIED"
                or dossier_data["causal_availability_status"] != "SUPPORTED"
                or dossier_data["new_information_reference"] is None
                or len(dossier_data["overlap_evidence_references"]) == 0
                or dossier_data["economic_mechanism"].strip() == ""
                or dossier_data["falsifiable_claim"].strip() == ""
            ):
                action = "REQUEST_MISSING_INTAKE_EVIDENCE"
                reason = "INTAKE_EVIDENCE_INCOMPLETE"
                rule = "RULE_6_INTAKE_EVIDENCE_INCOMPLETE"
            elif dossier_data["draft_reopening_contract_reference"] is None:
                action = "DRAFT_RESEARCH_REOPENING_CONTRACT"
                reason = "NOVEL_PROPOSAL_REQUIRES_VERSIONED_CONTRACT"
                rule = "RULE_7_DRAFT_CONTRACT_REQUIRED"
            else:
                action = "QUEUE_FOUNDER_REVIEW"
                reason = "DRAFT_CONTRACT_REQUIRES_FOUNDER_REVIEW"
                rule = "RULE_8_FOUNDER_REVIEW"
        if action not in ACTION_BY_ID or rule not in WINNING_RULE_IDS:
            raise DirectorError("DECISION_INTEGRITY_FAILURE")
        return action, reason, rule

    @staticmethod
    def _expected_decision(
        request: DirectorRequest,
        dossier: ResearchOpportunityDossier | None,
        evidence: EvidenceView,
        action: str,
        reason: str,
        rule: str,
    ) -> dict:
        request_data = request.as_dict()
        dossier_data = dossier.as_dict() if dossier is not None else None
        identities = evidence.contract_identities
        decision_core = {
            "schema_version": SCHEMA_VERSION,
            "request_id": request_data["request_id"],
            "proposal_id": (
                dossier_data["proposal_id"] if dossier_data is not None else None
            ),
            "selected_action_id": action,
            "reason_token": reason,
            "winning_rule_id": rule,
            "observation_manifest_byte_hash": evidence.manifest_byte_hash,
            "observation_snapshot_canonical_hash": evidence.snapshot_canonical_hash,
            "proposal_byte_hash": dossier.byte_hash if dossier is not None else None,
            "mission_93_contract_id": identities["mission_93"][0],
            "mission_93_contract_hash": identities["mission_93"][1],
            "mission_94_contract_id": identities["mission_94"][0],
            "mission_94_contract_hash": identities["mission_94"][1],
            "mission_95_contract_id": identities["mission_95"][0],
            "mission_95_contract_hash": identities["mission_95"][1],
            "mission_96a_contract_id": identities["mission_96a"][0],
            "mission_96a_contract_hash": identities["mission_96a"][1],
            "mission_96b_contract_id": identities["mission_96b"][0],
            "mission_96b_contract_hash": identities["mission_96b"][1],
            "mission_97_contract_id": identities["mission_97"][0],
            "mission_97_contract_hash": identities["mission_97"][1],
            "mission_98_contract_id": identities["mission_98"][0],
            "mission_98_contract_hash": identities["mission_98"][1],
            "repository_commit": request_data["repository_commit"],
            "observation_as_of": evidence.observation_as_of,
            "decision_as_of": request_data["decision_as_of"],
            "requested_by": request_data["requested_by"],
            "human_explanation": EXPLANATIONS[(action, reason)],
        }
        expected_id = f"decision-{canonical_hash(decision_core)[:32]}"
        identified = {
            "schema_version": decision_core.pop("schema_version"),
            "decision_id": expected_id,
            **decision_core,
        }
        return {
            **identified,
            "canonical_decision_hash": canonical_hash(identified),
        }

    def verify(
        self,
        *,
        request: DirectorRequest,
        dossier: ResearchOpportunityDossier | None,
        evidence: EvidenceView,
        decision: ResearchDecision,
    ) -> VerificationReceipt:
        """Verify every field and return one canonical receipt."""

        if (
            not isinstance(request, DirectorRequest)
            or (
                dossier is not None
                and not isinstance(dossier, ResearchOpportunityDossier)
            )
            or not isinstance(evidence, EvidenceView)
            or not isinstance(decision, ResearchDecision)
        ):
            raise DirectorError("DECISION_INTEGRITY_FAILURE")
        action, reason, rule = self._independent_policy(request, dossier, evidence)
        expected = self._expected_decision(
            request, dossier, evidence, action, reason, rule
        )
        actual = decision.as_dict()
        if set(actual) != set(DECISION_FIELDS) or actual != expected:
            raise DirectorError("DECISION_INTEGRITY_FAILURE")
        receipt_core = {
            "schema_version": SCHEMA_VERSION,
            "decision_id": expected["decision_id"],
            "decision_hash": expected["canonical_decision_hash"],
            "independently_recomputed_action_id": action,
            "independently_recomputed_reason_token": reason,
            "independently_recomputed_rule_id": rule,
            "verification_token": "VERIFIED",
            "verified_at": expected["decision_as_of"],
            "verifier_version": 1,
        }
        verification_id = f"verification-{canonical_hash(receipt_core)[:32]}"
        identified = {
            "schema_version": receipt_core.pop("schema_version"),
            "verification_id": verification_id,
            **receipt_core,
        }
        receipt = {
            **identified,
            "canonical_verification_hash": canonical_hash(identified),
        }
        if set(receipt) != set(VERIFICATION_FIELDS):
            raise DirectorError("DECISION_INTEGRITY_FAILURE")
        return VerificationReceipt(receipt)
