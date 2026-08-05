"""Deterministic decision preview and recording for Mission 98."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from offchain.research.admission import canonical_hash

from .action_registry import EXPLANATIONS
from .evidence import parse_utc
from .models import (
    SCHEMA_VERSION,
    DecisionPackage,
    DirectorRequest,
    EvidenceView,
    ResearchDecision,
    ResearchOpportunityDossier,
)
from .verifier import ResearchDirectorVerifier


class ResearchDirectorService:
    """Evaluate the fixed policy without performing the recommended action."""

    def __init__(self, ledger: Any) -> None:
        from .ledger import ResearchDirectorLedger

        if not isinstance(ledger, ResearchDirectorLedger):
            from .models import DirectorError

            raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE")
        self._ledger = ledger

    @staticmethod
    def _select_policy(
        request: DirectorRequest,
        dossier: ResearchOpportunityDossier | None,
        evidence: EvidenceView,
    ) -> tuple[str, str, str]:
        request_value = request.as_dict()
        dossier_value = None if dossier is None else dossier.as_dict()
        if evidence.health_token == "INTEGRITY_FAILURE" or any(
            severity in {"ERROR", "CRITICAL"}
            for severity in evidence.incident_severities
        ):
            return (
                "STOP_NO_ADMISSIBLE_ACTION",
                "UPSTREAM_INTEGRITY_STOP",
                "RULE_1_UPSTREAM_INTEGRITY_STOP",
            )
        if dossier_value is not None and (
            dossier_value["requested_stage"] != "DRAFT_REOPENING_CONTRACT_ONLY"
            or any(dossier_value["requested_authorities"].values())
        ):
            return (
                "REJECT_POLICY_CONFLICT",
                "PROPOSAL_REQUESTS_UNAUTHORIZED_STAGE",
                "RULE_2_POLICY_CONFLICT",
            )
        observation = parse_utc(evidence.observation_as_of)
        decision_as_of = parse_utc(request_value["decision_as_of"])
        if (
            evidence.health_token in {"DEGRADED", "UNAVAILABLE"}
            or decision_as_of - observation > timedelta(seconds=86_400)
        ):
            return (
                "REQUEST_OBSERVATION_REFRESH",
                "OBSERVATION_REFRESH_REQUIRED",
                "RULE_3_OBSERVATION_REFRESH",
            )
        if dossier_value is None:
            return (
                "STOP_NO_ADMISSIBLE_ACTION",
                "NO_PROPOSAL_SUPPLIED",
                "RULE_4_NO_PROPOSAL",
            )
        if dossier_value["overlap_audit_status"] == "MATERIAL_OVERLAP":
            return (
                "REJECT_PROPOSAL_OVERLAP",
                "REJECTED_FAMILY_OVERLAP",
                "RULE_5_MATERIAL_OVERLAP",
            )
        incomplete = (
            len(dossier_value["compared_rejected_family_ids"]) != 4
            or dossier_value["overlap_audit_status"]
            in {"INCONCLUSIVE", "NOT_PERFORMED"}
            or dossier_value["provenance_status"] != "VERIFIED"
            or dossier_value["causal_availability_status"] != "SUPPORTED"
            or dossier_value["new_information_reference"] is None
            or not dossier_value["overlap_evidence_references"]
            or not dossier_value["economic_mechanism"].strip()
            or not dossier_value["falsifiable_claim"].strip()
        )
        if incomplete:
            return (
                "REQUEST_MISSING_INTAKE_EVIDENCE",
                "INTAKE_EVIDENCE_INCOMPLETE",
                "RULE_6_INTAKE_EVIDENCE_INCOMPLETE",
            )
        if dossier_value["draft_reopening_contract_reference"] is None:
            return (
                "DRAFT_RESEARCH_REOPENING_CONTRACT",
                "NOVEL_PROPOSAL_REQUIRES_VERSIONED_CONTRACT",
                "RULE_7_DRAFT_CONTRACT_REQUIRED",
            )
        return (
            "QUEUE_FOUNDER_REVIEW",
            "DRAFT_CONTRACT_REQUIRES_FOUNDER_REVIEW",
            "RULE_8_FOUNDER_REVIEW",
        )

    @staticmethod
    def _build_decision(
        request: DirectorRequest,
        dossier: ResearchOpportunityDossier | None,
        evidence: EvidenceView,
        selected_action_id: str,
        reason_token: str,
        winning_rule_id: str,
    ) -> ResearchDecision:
        request_value = request.as_dict()
        dossier_value = None if dossier is None else dossier.as_dict()
        identities = evidence.contract_identities
        core = {
            "schema_version": SCHEMA_VERSION,
            "request_id": request_value["request_id"],
            "proposal_id": (
                None if dossier_value is None else dossier_value["proposal_id"]
            ),
            "selected_action_id": selected_action_id,
            "reason_token": reason_token,
            "winning_rule_id": winning_rule_id,
            "observation_manifest_byte_hash": evidence.manifest_byte_hash,
            "observation_snapshot_canonical_hash": evidence.snapshot_canonical_hash,
            "proposal_byte_hash": None if dossier is None else dossier.byte_hash,
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
            "repository_commit": request_value["repository_commit"],
            "observation_as_of": evidence.observation_as_of,
            "decision_as_of": request_value["decision_as_of"],
            "requested_by": request_value["requested_by"],
            "human_explanation": EXPLANATIONS[(selected_action_id, reason_token)],
        }
        decision_id = f"decision-{canonical_hash(core)[:32]}"
        identified = {
            "schema_version": core.pop("schema_version"),
            "decision_id": decision_id,
            **core,
        }
        return ResearchDecision(
            {**identified, "canonical_decision_hash": canonical_hash(identified)}
        )

    def _evaluate(
        self, request_relative_path: str
    ) -> tuple[
        DirectorRequest,
        ResearchOpportunityDossier | None,
        EvidenceView,
        ResearchDecision,
    ]:
        loader = self._ledger.evidence_loader()
        request, dossier = loader.load_request(request_relative_path)
        evidence = loader.verify(request)
        action, reason, rule = self._select_policy(request, dossier, evidence)
        decision = self._build_decision(
            request, dossier, evidence, action, reason, rule
        )
        return request, dossier, evidence, decision

    def preview(self, request_relative_path: str) -> DecisionPackage:
        """Return a verified decision package without writing the ledger."""

        request, dossier, evidence, decision = self._evaluate(
            request_relative_path
        )
        receipt = ResearchDirectorVerifier().verify(
            request=request,
            dossier=dossier,
            evidence=evidence,
            decision=decision,
        )
        return DecisionPackage(request, decision, receipt)

    def record(self, request_relative_path: str) -> DecisionPackage:
        """Revalidate, verify, and atomically record one decision package."""

        request, dossier, evidence, decision = self._evaluate(
            request_relative_path
        )
        return self._ledger._record_verified_package(
            request=request,
            dossier=dossier,
            evidence=evidence,
            decision=decision,
        )
