"""Preflight and admission coordination with no execution capability."""

from __future__ import annotations

from typing import Any, Mapping

from .control_registry import ControlRegistry
from .dataset_resolver import DatasetResolver
from .models import (
    AdmissionDecision,
    AdmissionError,
    ResearchAdmissionRequest,
    canonical_hash,
)
from .trial_ledger import ORIGINS, TrialLedger


class ResearchAdmissionService:
    """Decide whether a future request is admitted or stopped."""

    def __init__(
        self,
        *,
        controlling_contract_id: str,
        controlling_contract_hash: str,
        repository_commit: str,
        dataset_resolver: DatasetResolver,
        trial_ledger: TrialLedger,
        control_registry: ControlRegistry | None = None,
    ) -> None:
        self._contract_id = controlling_contract_id
        self._contract_hash = controlling_contract_hash
        self._repository_commit = repository_commit
        self._resolver = dataset_resolver
        self._ledger = trial_ledger
        self._controls = control_registry or ControlRegistry()

    def preflight(self, request: Mapping[str, Any]) -> AdmissionDecision:
        """Validate all gates without writing to the trial ledger."""

        parsed: ResearchAdmissionRequest | None = None
        resolution_hash: str | None = None
        control_hash: str | None = None
        try:
            parsed = ResearchAdmissionRequest.from_mapping(request)
            self._validate_contract(parsed)
            self._validate_origin(parsed)
            self._validate_repository(parsed)
            self._ledger.check_reservable(
                budget_id=parsed.budget_id,
                declared_trial_number=parsed.declared_trial_number,
                request_hash=parsed.canonical_request_hash,
                controlling_contract_id=parsed.controlling_contract_id,
                controlling_contract_hash=parsed.controlling_contract_hash,
            )
            resolution = self._resolve_dataset(parsed)
            resolution_hash = resolution.canonical_resolution_hash
            control = self._controls.validate(
                parsed.control_identifier, parsed.control_parameters
            )
            control_hash = control.canonical_control_hash
            return self._decision(
                parsed,
                operation="preflight",
                trial_id=None,
                decision_token="PRECHECK_PASS",
                reason_token="PRECHECK_GATES_PASSED",
                resolution_hash=resolution_hash,
                control_hash=control_hash,
            )
        except AdmissionError as error:
            return self._decision(
                parsed or request,
                operation="preflight",
                trial_id=None,
                decision_token="PRECHECK_STOP",
                reason_token=error.reason_token,
                resolution_hash=resolution_hash,
                control_hash=control_hash,
            )
        except Exception:
            return self._decision(
                parsed or request,
                operation="preflight",
                trial_id=None,
                decision_token="PRECHECK_STOP",
                reason_token="INTERNAL_INTEGRITY_FAILURE",
                resolution_hash=resolution_hash,
                control_hash=control_hash,
            )

    def admit(self, request: Mapping[str, Any]) -> AdmissionDecision:
        """Reserve before substantive gates, then return ADMITTED or STOPPED."""

        parsed: ResearchAdmissionRequest | None = None
        reservation = None
        resolution_hash: str | None = None
        control_hash: str | None = None
        try:
            parsed = ResearchAdmissionRequest.from_mapping(request)
            self._validate_contract(parsed)
            self._validate_origin(parsed)
            reservation = self._ledger.reserve(
                budget_id=parsed.budget_id,
                declared_trial_number=parsed.declared_trial_number,
                request_hash=parsed.canonical_request_hash,
                initiated_by=parsed.initiated_by,
                reserved_at=parsed.created_at,
                controlling_contract_id=parsed.controlling_contract_id,
                controlling_contract_hash=parsed.controlling_contract_hash,
            )
            self._validate_repository(parsed)
            resolution = self._resolve_dataset(parsed)
            resolution_hash = resolution.canonical_resolution_hash
            control = self._controls.validate(
                parsed.control_identifier, parsed.control_parameters
            )
            control_hash = control.canonical_control_hash
            self._ledger.append_event(
                trial_id=reservation.trial_id,
                status_token="ADMITTED",
                reason_token="ADMISSION_GATES_PASSED",
                event_timestamp=parsed.created_at,
            )
            return self._decision(
                parsed,
                operation="admit",
                trial_id=reservation.trial_id,
                decision_token="ADMITTED",
                reason_token="ADMISSION_GATES_PASSED",
                resolution_hash=resolution_hash,
                control_hash=control_hash,
            )
        except AdmissionError as error:
            if reservation is not None and parsed is not None:
                try:
                    self._ledger.append_event(
                        trial_id=reservation.trial_id,
                        status_token="STOPPED",
                        reason_token=error.reason_token,
                        event_timestamp=parsed.created_at,
                    )
                except AdmissionError:
                    return self._decision(
                        parsed,
                        operation="admit",
                        trial_id=reservation.trial_id,
                        decision_token="STOPPED",
                        reason_token="INTERNAL_INTEGRITY_FAILURE",
                        resolution_hash=resolution_hash,
                        control_hash=control_hash,
                    )
            return self._decision(
                parsed or request,
                operation="admit",
                trial_id=reservation.trial_id if reservation else None,
                decision_token="STOPPED",
                reason_token=error.reason_token,
                resolution_hash=resolution_hash,
                control_hash=control_hash,
            )
        except Exception:
            if reservation is not None and parsed is not None:
                try:
                    self._ledger.append_event(
                        trial_id=reservation.trial_id,
                        status_token="STOPPED",
                        reason_token="INTERNAL_INTEGRITY_FAILURE",
                        event_timestamp=parsed.created_at,
                    )
                except AdmissionError:
                    pass
            return self._decision(
                parsed or request,
                operation="admit",
                trial_id=reservation.trial_id if reservation else None,
                decision_token="STOPPED",
                reason_token="INTERNAL_INTEGRITY_FAILURE",
                resolution_hash=resolution_hash,
                control_hash=control_hash,
            )

    def _validate_contract(self, request: ResearchAdmissionRequest) -> None:
        if request.controlling_contract_id != self._contract_id:
            raise AdmissionError("CONTRACT_ID_MISMATCH")
        if request.controlling_contract_hash != self._contract_hash:
            raise AdmissionError("CONTRACT_HASH_MISMATCH")

    def _validate_repository(self, request: ResearchAdmissionRequest) -> None:
        if request.repository_commit != self._repository_commit:
            raise AdmissionError("REPOSITORY_COMMIT_MISMATCH")
        if not request.repository_clean:
            raise AdmissionError("DIRTY_REPOSITORY")

    @staticmethod
    def _validate_origin(request: ResearchAdmissionRequest) -> None:
        if request.initiated_by not in ORIGINS:
            raise AdmissionError("INITIATED_BY_INVALID")

    def _resolve_dataset(self, request: ResearchAdmissionRequest):
        return self._resolver.resolve(
            dataset_id=request.dataset_id,
            requested_hash=request.dataset_hash,
            data_class=request.data_class,
            split_identity=request.split_identity,
            authorization_stage=request.authorization_stage,
        )

    @staticmethod
    def _decision(
        request: ResearchAdmissionRequest | Mapping[str, Any],
        *,
        operation: str,
        trial_id: str | None,
        decision_token: str,
        reason_token: str,
        resolution_hash: str | None,
        control_hash: str | None,
    ) -> AdmissionDecision:
        def safe(field: str, default: Any) -> Any:
            if isinstance(request, ResearchAdmissionRequest):
                return getattr(request, field)
            value = request.get(field, default) if isinstance(request, Mapping) else default
            return value if isinstance(value, type(default)) and type(value) is type(default) else default

        request_id = safe("request_id", "INVALID_REQUEST")
        budget_id = safe("budget_id", "UNKNOWN_BUDGET")
        declared_trial_number = safe("declared_trial_number", 0)
        created_at = safe("created_at", "UNSPECIFIED")
        identity = {
            "operation": operation,
            "request_id": request_id,
            "trial_id": trial_id,
            "decision_token": decision_token,
            "reason_token": reason_token,
            "dataset_resolution_hash": resolution_hash,
            "validated_control_hash": control_hash,
            "budget_id": budget_id,
            "declared_trial_number": declared_trial_number,
            "created_at": created_at,
        }
        decision_id = f"decision-{canonical_hash(identity)[:32]}"
        core = {
            "schema_version": "1.0",
            "decision_id": decision_id,
            "request_id": request_id,
            "trial_id": trial_id,
            "decision_token": decision_token,
            "reason_token": reason_token,
            "dataset_resolution_hash": resolution_hash,
            "validated_control_hash": control_hash,
            "budget_id": budget_id,
            "declared_trial_number": declared_trial_number,
            "created_at": created_at,
        }
        return AdmissionDecision(
            **core,
            canonical_decision_hash=canonical_hash(core),
        )
