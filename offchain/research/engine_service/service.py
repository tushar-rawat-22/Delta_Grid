"""Deterministic Mission 95 orchestration for admitted synthetic controls."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping

from offchain.research.admission import (
    AdmissionDecision,
    AdmissionError,
    ControlRegistry,
    DatasetResolver,
    ResearchAdmissionRequest,
    TrialLedger,
    TrialResultLink,
    canonical_hash,
)

from .models import (
    EngineError,
    ExecutionPermit,
    LinkedResult,
    MISSION_AUTHORIZATION_STAGE,
    MISSION_BASE_COMMIT,
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    PRECEDING_CONTRACT_HASH,
    PRECEDING_CONTRACT_PATH,
)
from .result_bundle import (
    CODE_IDENTITY,
    COST_MODEL_IDENTITY,
    EXECUTION_MODEL_IDENTITY,
    RISK_MODEL_IDENTITY,
    SIMULATOR_IDENTITY,
    _verify_candidate_result,
    build_event_ledger,
    build_result_bundle,
    load_linked_result,
    publish_event_ledger,
    publish_result,
    validate_trial_id,
)
from .strict_json import prepare_result_directory, sha256_bytes
from .synthetic_controls import (
    ENGINE_ID,
    ENGINE_VERSION,
    KERNEL_ID,
    KERNEL_VERSION,
    execute_benchmark,
    execute_control,
)
from .synthetic_fixture import load_synthetic_fixture


COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


class CanonicalResultEngineService:
    """Execute and terminalize one exactly admitted synthetic control trial."""

    def __init__(
        self,
        *,
        expected_repository_commit: str,
        dataset_resolver: DatasetResolver,
        trial_ledger: TrialLedger,
        result_root: Path | str,
        control_registry: ControlRegistry | None = None,
    ) -> None:
        if (
            not isinstance(expected_repository_commit, str)
            or COMMIT_RE.fullmatch(expected_repository_commit) is None
        ):
            raise EngineError("IMPLEMENTATION_REPOSITORY_COMMIT_INVALID")
        self._expected_repository_commit = expected_repository_commit
        self._resolver = dataset_resolver
        self._ledger = trial_ledger
        configured_root = Path(result_root)
        self._result_root = (
            configured_root
            if configured_root.is_absolute()
            else Path.cwd() / configured_root
        )
        self._controls = control_registry or ControlRegistry()

    @property
    def result_root(self) -> Path:
        return self._result_root

    @property
    def expected_repository_commit(self) -> str:
        return self._expected_repository_commit

    def execute(
        self,
        request: Mapping[str, Any],
        decision: AdmissionDecision | Mapping[str, Any],
    ) -> LinkedResult:
        """Securely bind, execute, link, and load one synthetic result."""

        securely_bound = False
        trial_id: str | None = None
        request_created_at: str | None = None
        request_hash: str | None = None
        decision_hash: str | None = None
        candidate_link: TrialResultLink | None = None
        try:
            parsed_request = self._parse_request(request)
            request_created_at = parsed_request.created_at
            request_hash = parsed_request.canonical_request_hash
            self._validate_request(parsed_request)

            parsed_decision = self._parse_decision(decision)
            decision_hash = parsed_decision.canonical_decision_hash
            self._validate_decision(parsed_request, parsed_decision)
            trial_id = parsed_decision.trial_id
            if trial_id is None:
                raise EngineError("ADMISSION_IDENTITY_MISMATCH")
            validate_trial_id(trial_id)

            try:
                reservation = self._ledger.get_reservation(trial_id)
                budget = self._ledger.get_budget(parsed_request.budget_id)
            except AdmissionError as error:
                raise EngineError("TRIAL_RESERVATION_MISMATCH") from error
            self._validate_reservation_and_budget(
                parsed_request,
                parsed_decision,
                reservation,
                budget,
            )

            try:
                status = self._ledger.latest_status(trial_id)
            except AdmissionError as error:
                raise EngineError("TRIAL_STATE_NOT_ADMITTED") from error
            if status == "COMPLETED":
                linked = load_linked_result(
                    result_root=self._result_root,
                    trial_ledger=self._ledger,
                    trial_id=trial_id,
                )
                self._verify_replay_hashes(
                    linked,
                    parsed_request.canonical_request_hash,
                    parsed_decision.canonical_decision_hash,
                )
                return linked
            if status != "ADMITTED":
                raise EngineError("TRIAL_STATE_NOT_ADMITTED")
            if self._ledger.get_result_link(trial_id) is not None:
                raise EngineError("INTERNAL_INTEGRITY_FAILURE")

            try:
                resolution = self._resolver.resolve(
                    dataset_id=parsed_request.dataset_id,
                    requested_hash=parsed_request.dataset_hash,
                    data_class=parsed_request.data_class,
                    split_identity=parsed_request.split_identity,
                    authorization_stage=parsed_request.authorization_stage,
                )
                control = self._controls.validate(
                    parsed_request.control_identifier,
                    parsed_request.control_parameters,
                )
            except AdmissionError as error:
                raise EngineError("ADMISSION_IDENTITY_MISMATCH") from error
            if (
                resolution.canonical_resolution_hash
                != parsed_decision.dataset_resolution_hash
                or control.canonical_control_hash
                != parsed_decision.validated_control_hash
                or resolution.data_class != "SYNTHETIC_FIXTURE"
                or resolution.split_identity != "SYNTHETIC_DEVELOPMENT"
                or control.non_alpha is not True
                or control.execution_authorized is not False
            ):
                raise EngineError("ADMISSION_IDENTITY_MISMATCH")

            securely_bound = True
            fixture = load_synthetic_fixture(
                artifact_root=self._resolver.artifact_root,
                resolution=resolution,
            )
            permit = ExecutionPermit.issue(
                request_hash=parsed_request.canonical_request_hash,
                decision_hash=parsed_decision.canonical_decision_hash,
                trial_id=trial_id,
                dataset_resolution_hash=resolution.canonical_resolution_hash,
                validated_control_hash=control.canonical_control_hash,
            )
            outcome = execute_control(
                fixture=fixture,
                control_identifier=control.control_identifier,
                control_parameters=control.control_parameters,
                permit=permit,
            )
            benchmark = execute_benchmark(fixture)
            identities = self._identities(
                parsed_request,
                parsed_decision,
                reservation,
                budget,
                resolution,
                control,
                fixture,
                permit,
            )
            event_ledger = build_event_ledger(
                identity={
                    "trial_id": trial_id,
                    "engine_id": ENGINE_ID,
                    "engine_version": ENGINE_VERSION,
                    "kernel_id": KERNEL_ID,
                    "kernel_version": KERNEL_VERSION,
                    "fixture_id": fixture.fixture_id,
                    "fixture_hash": fixture.canonical_fixture_hash,
                    "control_identifier": control.control_identifier,
                    "validated_control_hash": control.canonical_control_hash,
                    "permit_hash": permit.canonical_permit_hash,
                },
                outcome=outcome,
            )
            directory = prepare_result_directory(self._result_root, trial_id)
            event_path = directory / "event-ledger.json"
            event_bytes = publish_event_ledger(event_path, event_ledger)
            artifact = {
                "artifact_id": event_ledger["artifact_id"],
                "artifact_type": event_ledger["artifact_type"],
                "relative_path": f"{trial_id}/event-ledger.json",
                "byte_sha256": sha256_bytes(event_bytes),
                "canonical_artifact_hash": event_ledger[
                    "canonical_event_ledger_hash"
                ],
            }
            bundle_value = build_result_bundle(
                mission_contract=identities["mission_contract"],
                admission=identities["admission"],
                engine=identities["engine"],
                dataset=identities["dataset"],
                control=identities["control"],
                outcome=outcome,
                benchmark=benchmark,
                artifact=artifact,
                recorded_at=parsed_request.created_at,
                data_start_at=fixture.events[0].timestamp,
                data_end_at=fixture.events[-1].timestamp,
                event_timestamps=tuple(event.timestamp for event in fixture.events),
            )
            result_path = directory / "result.json"
            publish_result(result_path, bundle_value)
            candidate_link = TrialResultLink.create(
                trial_id=trial_id,
                result_bundle_id=bundle_value["result_bundle_id"],
                result_bundle_hash=bundle_value["canonical_result_hash"],
                result_bundle_path=f"{trial_id}/result.json",
                linked_at=parsed_request.created_at,
            )
            _verify_candidate_result(
                result_root=self._result_root,
                candidate_link=candidate_link,
            )
            try:
                persisted_link = self._ledger._complete_with_verified_result(
                    candidate_link
                )
            except AdmissionError as error:
                if error.reason_token == "SQLITE_CONTENTION":
                    recovered = self._completed_replay(
                        trial_id,
                        request_hash,
                        decision_hash,
                        candidate_link,
                    )
                    if recovered is not None:
                        return recovered
                    raise EngineError("SQLITE_CONTENTION") from error
                raise EngineError(error.reason_token) from error
            if persisted_link != candidate_link:
                raise EngineError("RESULT_ARTIFACT_MISMATCH")
            linked = load_linked_result(
                result_root=self._result_root,
                trial_ledger=self._ledger,
                trial_id=trial_id,
            )
            self._verify_replay_hashes(linked, request_hash, decision_hash)
            return linked
        except EngineError as error:
            if not securely_bound or error.reason_token == "SQLITE_CONTENTION":
                raise
            recovered = self._terminalize_bound_failure(
                trial_id=trial_id,
                event_timestamp=request_created_at,
                original_error=error,
                request_hash=request_hash,
                decision_hash=decision_hash,
                candidate_link=candidate_link,
            )
            if recovered is not None:
                return recovered
            raise
        except AdmissionError as error:
            engine_error = EngineError("INTERNAL_INTEGRITY_FAILURE")
            if not securely_bound:
                raise engine_error from error
            recovered = self._terminalize_bound_failure(
                trial_id=trial_id,
                event_timestamp=request_created_at,
                original_error=engine_error,
                request_hash=request_hash,
                decision_hash=decision_hash,
                candidate_link=candidate_link,
            )
            if recovered is not None:
                return recovered
            raise engine_error from error
        except Exception as error:
            engine_error = EngineError("INTERNAL_INTEGRITY_FAILURE")
            if not securely_bound:
                raise engine_error from error
            recovered = self._terminalize_bound_failure(
                trial_id=trial_id,
                event_timestamp=request_created_at,
                original_error=engine_error,
                request_hash=request_hash,
                decision_hash=decision_hash,
                candidate_link=candidate_link,
            )
            if recovered is not None:
                return recovered
            raise engine_error from error

    @staticmethod
    def _parse_request(value: Mapping[str, Any]) -> ResearchAdmissionRequest:
        try:
            return ResearchAdmissionRequest.from_mapping(value)
        except AdmissionError as error:
            raise EngineError("ADMISSION_IDENTITY_MISMATCH") from error

    @staticmethod
    def _parse_decision(
        value: AdmissionDecision | Mapping[str, Any],
    ) -> AdmissionDecision:
        mapping = value.as_dict() if isinstance(value, AdmissionDecision) else value
        try:
            parsed = AdmissionDecision.from_mapping(mapping)
        except AdmissionError as error:
            raise EngineError("ADMISSION_DECISION_HASH_MISMATCH") from error
        if (
            parsed.decision_token != "ADMITTED"
            or parsed.reason_token != "ADMISSION_GATES_PASSED"
        ):
            raise EngineError("ADMISSION_DECISION_NOT_ADMITTED")
        return parsed

    def _validate_request(self, request: ResearchAdmissionRequest) -> None:
        if (
            request.controlling_contract_id != MISSION_CONTRACT_ID
            or request.controlling_contract_hash != MISSION_CONTRACT_HASH
            or request.authorization_stage != MISSION_AUTHORIZATION_STAGE
            or request.repository_commit != self._expected_repository_commit
            or request.repository_clean is not True
            or request.data_class != "SYNTHETIC_FIXTURE"
            or request.split_identity != "SYNTHETIC_DEVELOPMENT"
        ):
            raise EngineError("ADMISSION_IDENTITY_MISMATCH")

    @staticmethod
    def _validate_decision(
        request: ResearchAdmissionRequest,
        decision: AdmissionDecision,
    ) -> None:
        identity = {
            "operation": "admit",
            "request_id": request.request_id,
            "trial_id": decision.trial_id,
            "decision_token": "ADMITTED",
            "reason_token": "ADMISSION_GATES_PASSED",
            "dataset_resolution_hash": decision.dataset_resolution_hash,
            "validated_control_hash": decision.validated_control_hash,
            "budget_id": request.budget_id,
            "declared_trial_number": request.declared_trial_number,
            "created_at": request.created_at,
        }
        expected_id = f"decision-{canonical_hash(identity)[:32]}"
        if (
            decision.request_id != request.request_id
            or decision.budget_id != request.budget_id
            or decision.declared_trial_number != request.declared_trial_number
            or decision.created_at != request.created_at
            or not decision.trial_id
            or not decision.dataset_resolution_hash
            or not decision.validated_control_hash
            or decision.decision_id != expected_id
        ):
            raise EngineError("ADMISSION_IDENTITY_MISMATCH")

    @staticmethod
    def _validate_reservation_and_budget(
        request: ResearchAdmissionRequest,
        decision: AdmissionDecision,
        reservation: Any,
        budget: Any,
    ) -> None:
        reservation_core = {
            "budget_id": reservation.budget_id,
            "declared_trial_number": reservation.declared_trial_number,
            "request_hash": reservation.request_hash,
            "initiated_by": reservation.initiated_by,
            "reserved_at": reservation.reserved_at,
        }
        expected_trial_id = f"trial-{canonical_hash(reservation_core)[:32]}"
        budget_core = budget.as_dict()
        supplied_budget_hash = budget_core.pop("canonical_budget_hash")
        if (
            decision.trial_id != expected_trial_id
            or reservation.trial_id != expected_trial_id
            or reservation.request_hash != request.canonical_request_hash
            or reservation.budget_id != request.budget_id
            or reservation.declared_trial_number != request.declared_trial_number
            or reservation.initiated_by != request.initiated_by
            or reservation.reserved_at != request.created_at
            or canonical_hash(budget_core) != supplied_budget_hash
            or budget.controlling_contract_id != MISSION_CONTRACT_ID
            or budget.controlling_contract_hash != MISSION_CONTRACT_HASH
            or budget.experiment_family != "MISSION_95_SYNTHETIC_CONTROLS"
        ):
            raise EngineError("TRIAL_RESERVATION_MISMATCH")

    def _identities(
        self,
        request: ResearchAdmissionRequest,
        decision: AdmissionDecision,
        reservation: Any,
        budget: Any,
        resolution: Any,
        control: Any,
        fixture: Any,
        permit: ExecutionPermit,
    ) -> dict[str, dict[str, Any]]:
        return {
            "mission_contract": {
                "contract_id": MISSION_CONTRACT_ID,
                "contract_hash": MISSION_CONTRACT_HASH,
                "authorization_stage": MISSION_AUTHORIZATION_STAGE,
                "base_commit": MISSION_BASE_COMMIT,
                "preceding_contract_path": PRECEDING_CONTRACT_PATH,
                "preceding_contract_hash": PRECEDING_CONTRACT_HASH,
            },
            "admission": {
                "request_id": request.request_id,
                "request_hash": request.canonical_request_hash,
                "request_created_at": request.created_at,
                "decision_id": decision.decision_id,
                "decision_hash": decision.canonical_decision_hash,
                "decision_token": decision.decision_token,
                "reason_token": decision.reason_token,
                "trial_id": decision.trial_id,
                "budget_id": request.budget_id,
                "budget_hash": budget.canonical_budget_hash,
                "declared_trial_number": request.declared_trial_number,
                "reservation_reserved_at": reservation.reserved_at,
                "initiated_by": reservation.initiated_by,
                "experiment_family": budget.experiment_family,
                "total_trial_budget": budget.total_trial_budget,
                "repository_clean": request.repository_clean,
                "dataset_resolution_hash": decision.dataset_resolution_hash,
                "validated_control_hash": decision.validated_control_hash,
            },
            "engine": {
                "engine_id": ENGINE_ID,
                "engine_version": ENGINE_VERSION,
                "kernel_id": KERNEL_ID,
                "kernel_version": KERNEL_VERSION,
                "implementation_repository_commit": self._expected_repository_commit,
                "permit_scope": permit.scope,
                "permit_hash": permit.canonical_permit_hash,
                "code_identity": CODE_IDENTITY,
                "simulator_identity": SIMULATOR_IDENTITY,
                "execution_model_identity": EXECUTION_MODEL_IDENTITY,
                "cost_model_identity": COST_MODEL_IDENTITY,
                "risk_model_identity": RISK_MODEL_IDENTITY,
            },
            "dataset": {
                "dataset_id": resolution.dataset_id,
                "dataset_content_hash": resolution.content_sha256,
                "artifact_id": resolution.artifact_id,
                "artifact_path": resolution.artifact_path,
                "metadata_hash": resolution.metadata_sha256,
                "resolution_hash": resolution.canonical_resolution_hash,
                "fixture_id": fixture.fixture_id,
                "fixture_hash": fixture.canonical_fixture_hash,
                "data_class": resolution.data_class,
                "split_identity": resolution.split_identity,
                "instrument_id": fixture.instrument_id,
                "currency_unit": fixture.currency_unit,
                "initial_cash_units": fixture.initial_cash_units,
                "trade_quantity_units": fixture.trade_quantity_units,
                "fee_bps": fixture.fee_bps,
                "slippage_bps": fixture.slippage_bps,
                "provenance_reference": resolution.provenance_reference,
                "resolution_authorization_stage": resolution.authorization_stage,
                "resolution_reason_token": resolution.reason_token,
            },
            "control": {
                "control_identifier": control.control_identifier,
                "control_parameters": dict(control.control_parameters),
                "validated_control_hash": control.canonical_control_hash,
                "non_alpha": control.non_alpha,
                "registry_execution_authorized": control.execution_authorized,
            },
        }

    @staticmethod
    def _verify_replay_hashes(
        linked: LinkedResult,
        request_hash: str | None,
        decision_hash: str | None,
    ) -> None:
        bundle = linked.result_bundle.as_dict()
        if (
            bundle["admission"]["request_hash"] != request_hash
            or bundle["admission"]["decision_hash"] != decision_hash
        ):
            raise EngineError("RESULT_ARTIFACT_MISMATCH")

    def _completed_replay(
        self,
        trial_id: str,
        request_hash: str | None,
        decision_hash: str | None,
        candidate_link: TrialResultLink | None,
    ) -> LinkedResult | None:
        try:
            if self._ledger.latest_status(trial_id) != "COMPLETED":
                return None
            linked = load_linked_result(
                result_root=self._result_root,
                trial_ledger=self._ledger,
                trial_id=trial_id,
            )
            self._verify_replay_hashes(linked, request_hash, decision_hash)
            if (
                candidate_link is not None
                and (
                    linked.result_bundle_id != candidate_link.result_bundle_id
                    or linked.canonical_result_hash
                    != candidate_link.result_bundle_hash
                )
            ):
                return None
            return linked
        except (AdmissionError, EngineError):
            return None

    def _terminalize_bound_failure(
        self,
        *,
        trial_id: str | None,
        event_timestamp: str | None,
        original_error: EngineError,
        request_hash: str | None,
        decision_hash: str | None,
        candidate_link: TrialResultLink | None,
    ) -> LinkedResult | None:
        if trial_id is None or event_timestamp is None:
            raise EngineError(
                "TRIAL_TERMINALIZATION_FAILED",
                original_reason_token=original_error.reason_token,
            ) from original_error
        recovered = self._completed_replay(
            trial_id,
            request_hash,
            decision_hash,
            candidate_link,
        )
        if recovered is not None:
            return recovered
        try:
            latest = self._ledger.latest_event(trial_id)
            if latest.status_token == "FAILED":
                return None
            if latest.status_token != "ADMITTED":
                return None
            self._ledger.append_event(
                trial_id=trial_id,
                status_token="FAILED",
                reason_token=original_error.reason_token,
                event_timestamp=event_timestamp,
            )
            persisted = self._ledger.latest_event(trial_id)
            if (
                persisted.status_token == "FAILED"
                and persisted.reason_token == original_error.reason_token
                and persisted.event_timestamp == event_timestamp
            ):
                return None
        except Exception as persistence_error:
            try:
                current = self._ledger.latest_event(trial_id)
                if (
                    current.status_token == "FAILED"
                    and current.reason_token == original_error.reason_token
                ):
                    return None
                recovered = self._completed_replay(
                    trial_id,
                    request_hash,
                    decision_hash,
                    candidate_link,
                )
                if recovered is not None:
                    return recovered
            except Exception:
                pass
            raise EngineError(
                "TRIAL_TERMINALIZATION_FAILED",
                original_reason_token=original_error.reason_token,
            ) from persistence_error
        raise EngineError(
            "TRIAL_TERMINALIZATION_FAILED",
            original_reason_token=original_error.reason_token,
        ) from original_error
