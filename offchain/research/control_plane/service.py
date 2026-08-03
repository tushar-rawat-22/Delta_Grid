"""Deterministic read-only Mission 96A control-plane projection service."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping

from offchain.research.admission import AdmissionError, canonical_hash
from offchain.research.admission.trial_ledger import STATUSES, TRANSITIONS
from offchain.research.engine_service import EngineError, load_linked_result

from .models import (
    AUTHORITY,
    MISSION_93_CONTRACT_HASH,
    MISSION_93_CONTRACT_ID,
    MISSION_94_CONTRACT_HASH,
    MISSION_94_CONTRACT_ID,
    MISSION_95_CONTRACT_HASH,
    MISSION_95_CONTRACT_ID,
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    SNAPSHOT_SCHEMA_VERSION,
    SNAPSHOT_VERSION,
    ControlPlaneError,
    ControlPlaneSnapshot,
    IncidentProjection,
    ResultProjection,
    SystemProjection,
    TrialProjection,
)
from .readonly_ledger import (
    ReadOnlyTrialLedger,
    _LedgerSnapshot,
    _parse_normalized_utc,
    _resolve_existing_no_symlink,
)


_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_INTEGRITY_CATEGORIES = frozenset(
    {
        "LEDGER_ROW_INTEGRITY_FAILURE",
        "INVALID_LIFECYCLE",
        "RESULT_ARTIFACT_TAMPERED",
        "RESULT_SCHEMA_UNSUPPORTED",
        "RESULT_VERIFICATION_FAILED",
        "DUPLICATE_OR_CONFLICTING_IDENTITY",
    }
)
_CONTRACT_SPECS = (
    (
        "mission_93",
        "contracts/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json",
        MISSION_93_CONTRACT_ID,
        MISSION_93_CONTRACT_HASH,
        None,
        None,
    ),
    (
        "mission_94",
        "contracts/DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json",
        MISSION_94_CONTRACT_ID,
        MISSION_94_CONTRACT_HASH,
        "contracts/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json",
        None,
    ),
    (
        "mission_95",
        "contracts/DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE_V1.json",
        MISSION_95_CONTRACT_ID,
        MISSION_95_CONTRACT_HASH,
        "contracts/DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json",
        MISSION_94_CONTRACT_HASH,
    ),
    (
        "mission_96a",
        "contracts/DELTAGRID_RESEARCH_CONTROL_PLANE_V1.json",
        MISSION_CONTRACT_ID,
        MISSION_CONTRACT_HASH,
        "contracts/DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE_V1.json",
        MISSION_95_CONTRACT_HASH,
    ),
)


@dataclass(frozen=True)
class _SnapshotLedgerView:
    """In-memory Mission 95 ledger reads bound to one captured state."""

    _data: _LedgerSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self._data, _LedgerSnapshot):
            raise TypeError("snapshot ledger view requires a captured ledger state")

    @staticmethod
    def _one(matches: list[Any], reason_token: str) -> Any:
        if len(matches) != 1:
            raise AdmissionError(reason_token)
        return matches[0]

    def get_budget(self, budget_id: str) -> Any:
        return self._one(
            [item for item in self._data.budgets if item.budget_id == budget_id],
            "BUDGET_DEFINITION_MISMATCH",
        )

    def get_reservation(self, trial_id: str) -> Any:
        return self._one(
            [
                item
                for item in self._data.reservations
                if item.trial_id == trial_id
            ],
            "TRIAL_RESERVATION_MISMATCH",
        )

    def latest_event(self, trial_id: str) -> Any:
        events = sorted(
            (
                item
                for item in self._data.events
                if item.trial_id == trial_id
            ),
            key=lambda item: (item.sequence_number, item.event_id),
        )
        if (
            not events
            or [item.sequence_number for item in events]
            != list(range(1, len(events) + 1))
            or len({item.event_id for item in events}) != len(events)
        ):
            raise AdmissionError("TRIAL_STATE_NOT_ADMITTED")
        previous = None
        for event in events:
            if (
                (previous is None and event.status_token != "RESERVED")
                or (
                    previous is not None
                    and event.status_token
                    not in TRANSITIONS.get(previous.status_token, ())
                )
                or (
                    previous is not None
                    and _parse_normalized_utc(event.event_timestamp)
                    < _parse_normalized_utc(previous.event_timestamp)
                )
            ):
                raise AdmissionError("TRIAL_STATE_NOT_ADMITTED")
            previous = event
        return events[-1]

    def get_result_link(self, trial_id: str) -> Any:
        matches = [
            item for item in self._data.result_links if item.trial_id == trial_id
        ]
        if not matches:
            return None
        return self._one(matches, "RESULT_ARTIFACT_MISMATCH")


def _strict_json_object(raw: bytes) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is not permitted")

    def object_without_duplicates(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON object name")
            value[key] = item
        return value

    def reject_nonfinite(token: str) -> None:
        raise ValueError(f"non-finite JSON number: {token}")

    text = raw.decode("utf-8")
    value = json.loads(
        text,
        object_pairs_hook=object_without_duplicates,
        parse_constant=reject_nonfinite,
    )
    if type(value) is not dict:
        raise ValueError("contract must be a JSON object")
    return value


def _verify_repository_contracts(
    repository_root: Path,
) -> tuple[Mapping[str, str], Mapping[str, bool]]:
    identities: dict[str, str] = {}
    try:
        for (
            mission,
            relative_path,
            expected_id,
            expected_hash,
            predecessor_path,
            predecessor_hash,
        ) in _CONTRACT_SPECS:
            contract_path = _resolve_existing_no_symlink(
                repository_root / relative_path,
                require_directory=False,
                unavailable_reason="REPOSITORY_CONTRACT_INTEGRITY_FAILURE",
                unsafe_reason="REPOSITORY_CONTRACT_INTEGRITY_FAILURE",
            )
            with contract_path.open("rb") as contract_file:
                raw = contract_file.read()
            value = _strict_json_object(raw)
            if value.get("contract_id") != expected_id:
                raise ValueError("contract identity mismatch")
            core = dict(value)
            supplied_hash = core.pop("contract_hash_sha256", None)
            if (
                supplied_hash != expected_hash
                or canonical_hash(core) != expected_hash
            ):
                raise ValueError("contract hash mismatch")
            if predecessor_path is not None:
                if value.get("preceding_contract") != predecessor_path:
                    raise ValueError("contract predecessor mismatch")
                if (
                    predecessor_hash is not None
                    and value.get("preceding_contract_hash_sha256")
                    != predecessor_hash
                ):
                    raise ValueError("contract predecessor hash mismatch")
            identities[mission] = expected_hash
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, ControlPlaneError) as error:
        raise ControlPlaneError(
            "REPOSITORY_CONTRACT_INTEGRITY_FAILURE",
            "required governance contract verification failed",
        ) from error
    verification = {
        "mission_93_verified": True,
        "mission_94_verified": True,
        "mission_95_verified": True,
        "mission_96a_verified": True,
        "predecessor_chain_verified": True,
    }
    return MappingProxyType(identities), MappingProxyType(verification)


def _path_identity(path: Path) -> str:
    return f"sha256:{canonical_hash({'absolute_path': str(path)})}"


def _incident(
    *,
    severity: str,
    category: str,
    reason_token: str,
    explanation: str,
    trial_id: str | None,
    as_of: str,
    evidence: Mapping[str, Any],
) -> IncidentProjection:
    core = {
        "severity": severity,
        "category": category,
        "reason_token": reason_token,
        "human_explanation": explanation,
        "trial_id": trial_id,
        "detected_at": as_of,
        "evidence_identities": dict(evidence),
    }
    identity_hash = canonical_hash(core)
    identified = {"incident_id": f"incident-{identity_hash[:32]}", **core}
    return IncidentProjection(
        **identified, canonical_incident_hash=canonical_hash(identified)
    )


def _result_projection(linked: Any) -> ResultProjection:
    bundle = linked.result_bundle.as_dict()
    trial = bundle["metrics"]["trial"]
    engine = bundle["engine"]
    result = bundle["result"]
    core = {
        "trial_id": linked.trial_id,
        "result_bundle_id": linked.result_bundle_id,
        "result_bundle_hash": linked.canonical_result_hash,
        "trial_status_token": linked.trial_status_token,
        "trial_reason_token": linked.trial_reason_token,
        "result_status_token": result["status_token"],
        "result_reason_token": result["reason_token"],
        "human_explanation": result["human_explanation"],
        "control_identifier": bundle["control"]["control_identifier"],
        "control_parameters": bundle["control"]["control_parameters"],
        "dataset_identity": bundle["dataset"],
        "code_identity": engine["code_identity"],
        "simulator_identity": engine["simulator_identity"],
        "execution_model_identity": engine["execution_model_identity"],
        "cost_model_identity": engine["cost_model_identity"],
        "risk_model_identity": engine["risk_model_identity"],
        "implementation_repository_commit": engine[
            "implementation_repository_commit"
        ],
        "gross_result": trial["gross_result_units"],
        "net_result": trial["net_result_units"],
        "benchmark": bundle["metrics"]["benchmark"],
        "costs_by_component": {
            "fee_cost_units": trial["fee_cost_units"],
            "slippage_cost_units": trial["slippage_cost_units"],
            "funding_cost_units": trial["funding_cost_units"],
            "borrowing_cost_units": trial["borrowing_cost_units"],
            "impact_cost_units": trial["impact_cost_units"],
            "latency_cost_units": trial["latency_cost_units"],
        },
        "maximum_drawdown": {
            "maximum_drawdown_units": trial["maximum_drawdown_units"],
            "maximum_drawdown_bps": trial["maximum_drawdown_bps"],
        },
        "exposure": {
            "exposure_position_units_sum": trial["exposure_position_units_sum"],
            "exposure_event_count": trial["exposure_event_count"],
            "exposure_bps": trial["exposure_bps"],
        },
        "turnover": trial["turnover_units"],
        "trade_count": trial["trade_count"],
        "concentration": trial["concentration_bps"],
        "timing_diagnostics": bundle["execution"]["timing_diagnostics"],
        "protected_access_counts": bundle["protected_access_counts"],
        "artifact_declarations": bundle["artifacts"],
        "warnings": bundle["warnings"],
        "verification_declarations": bundle["verification"],
    }
    return ResultProjection(
        **core, canonical_result_projection_hash=canonical_hash(core)
    )


class ResearchControlPlaneService:
    """Build operator-facing snapshots without changing persisted state."""

    _IDENTITY_FIELDS = frozenset(
        {
            "_ledger",
            "_result_root",
            "_repository_root",
            "_expected_repository_commit",
            "_verified_contract_identities",
            "_contract_verification",
        }
    )

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self._IDENTITY_FIELDS and hasattr(self, name):
            raise AttributeError(f"{name} is read-only")
        object.__setattr__(self, name, value)

    def __init__(
        self,
        *,
        ledger: ReadOnlyTrialLedger,
        result_root: Path | str,
        repository_root: Path | str,
        expected_repository_commit: str,
    ) -> None:
        if not isinstance(ledger, ReadOnlyTrialLedger):
            raise ControlPlaneError(
                "LEDGER_ADAPTER_INVALID", "a ReadOnlyTrialLedger is required"
            )
        if (
            not isinstance(expected_repository_commit, str)
            or _COMMIT_RE.fullmatch(expected_repository_commit) is None
        ):
            raise ControlPlaneError(
                "REPOSITORY_COMMIT_INVALID",
                "expected repository commit must be 40 lowercase hexadecimal characters",
            )
        self._ledger = ledger
        self._result_root = self._existing_directory(
            result_root, "RESULT_ROOT_INVALID"
        )
        self._repository_root = _resolve_existing_no_symlink(
            repository_root,
            require_directory=True,
            unavailable_reason="REPOSITORY_ROOT_INVALID",
            unsafe_reason="REPOSITORY_ROOT_PATH_UNSAFE",
        )
        (
            self._verified_contract_identities,
            self._contract_verification,
        ) = _verify_repository_contracts(self._repository_root)
        self._expected_repository_commit = expected_repository_commit

    @property
    def ledger(self) -> ReadOnlyTrialLedger:
        return self._ledger

    @property
    def result_root(self) -> Path:
        return self._result_root

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    @property
    def expected_repository_commit(self) -> str:
        return self._expected_repository_commit

    @property
    def contract_verification(self) -> Mapping[str, bool]:
        return self._contract_verification

    @staticmethod
    def _existing_directory(value: Path | str, reason: str) -> Path:
        try:
            path = Path(value).resolve(strict=True)
        except OSError as error:
            raise ControlPlaneError(reason, "path must be an existing directory") from error
        if not path.is_dir():
            raise ControlPlaneError(reason, "path must be an existing directory")
        return path

    @staticmethod
    def _validate_as_of(as_of: str) -> Any:
        try:
            return _parse_normalized_utc(as_of)
        except AdmissionError as error:
            raise ControlPlaneError("AS_OF_INVALID", "as_of is not a timestamp") from error

    @staticmethod
    def _duplicate_incidents(
        data: _LedgerSnapshot, as_of: str
    ) -> list[IncidentProjection]:
        inventories = {
            "budget_id": [item.budget_id for item in data.budgets],
            "trial_id": [item.trial_id for item in data.reservations],
            "event_id": [item.event_id for item in data.events],
            "result_link_trial_id": [item.trial_id for item in data.result_links],
            "result_bundle_id": [
                item.result_bundle_id for item in data.result_links
            ],
            "result_bundle_hash": [
                item.result_bundle_hash for item in data.result_links
            ],
        }
        incidents = []
        for identity_type, values in inventories.items():
            for identity, count in sorted(Counter(values).items()):
                if count > 1:
                    trial_id = identity if identity_type.endswith("trial_id") else None
                    incidents.append(
                        _incident(
                            severity="ERROR",
                            category="DUPLICATE_OR_CONFLICTING_IDENTITY",
                            reason_token="DUPLICATE_IDENTITY",
                            explanation="A supposedly unique ledger identity is repeated.",
                            trial_id=trial_id,
                            as_of=as_of,
                            evidence={
                                "identity_type": identity_type,
                                "identity": identity,
                                "count": count,
                            },
                        )
                    )
        return incidents

    def build_snapshot(self, *, as_of: str) -> ControlPlaneSnapshot:
        self._validate_as_of(as_of)
        try:
            data = self._ledger._snapshot()
        except ControlPlaneError:
            raise
        snapshot_ledger = _SnapshotLedgerView(data)
        incidents: list[IncidentProjection] = [
            _incident(
                severity="ERROR",
                category="LEDGER_ROW_INTEGRITY_FAILURE",
                reason_token=failure.reason_token,
                explanation=f"A malformed row was found in {failure.table}.",
                trial_id=failure.trial_id,
                as_of=as_of,
                evidence={
                    "table": failure.table,
                    "row_identity": failure.identity,
                },
            )
            for failure in data.failures
        ]
        incidents.extend(self._duplicate_incidents(data, as_of))

        budgets: dict[str, Any] = {}
        for item in data.budgets:
            budgets.setdefault(item.budget_id, item)
        reservations: dict[str, Any] = {}
        for item in data.reservations:
            reservations.setdefault(item.trial_id, item)
        event_groups: dict[str, list[Any]] = defaultdict(list)
        for item in data.events:
            event_groups[item.trial_id].append(item)
        link_groups: dict[str, list[Any]] = defaultdict(list)
        for item in data.result_links:
            link_groups[item.trial_id].append(item)

        valid_results: dict[str, ResultProjection] = {}
        verification_tokens: dict[str, str] = {}
        for reservation in data.reservations:
            trial_id = reservation.trial_id
            events = event_groups.get(trial_id, [])
            links = link_groups.get(trial_id, [])
            if reservation.budget_id not in budgets:
                incidents.append(
                    _incident(
                        severity="ERROR",
                        category="LEDGER_ROW_INTEGRITY_FAILURE",
                        reason_token="BUDGET_RESERVATION_RELATIONSHIP_INVALID",
                        explanation="The reservation does not reference one valid budget.",
                        trial_id=trial_id,
                        as_of=as_of,
                        evidence={"budget_id": reservation.budget_id},
                    )
                )
            lifecycle_valid = True
            if not events:
                lifecycle_valid = False
            else:
                previous = None
                for expected_sequence, event in enumerate(events, start=1):
                    if (
                        event.sequence_number != expected_sequence
                        or (
                            previous is None
                            and event.status_token != "RESERVED"
                        )
                        or (
                            previous is not None
                            and event.status_token
                            not in TRANSITIONS.get(previous.status_token, ())
                        )
                        or (
                            previous is not None
                            and _parse_normalized_utc(event.event_timestamp)
                            < _parse_normalized_utc(previous.event_timestamp)
                        )
                    ):
                        lifecycle_valid = False
                    previous = event
            if not lifecycle_valid:
                incidents.append(
                    _incident(
                        severity="ERROR",
                        category="INVALID_LIFECYCLE",
                        reason_token="TRIAL_LIFECYCLE_INVALID",
                        explanation="The persisted lifecycle is missing, out of sequence, or has an invalid transition.",
                        trial_id=trial_id,
                        as_of=as_of,
                        evidence={
                            "event_ids": [event.event_id for event in events],
                            "event_count": len(events),
                        },
                    )
                )
            latest = events[-1] if events else None
            if len(links) > 1:
                verification_tokens[trial_id] = "CONFLICTING_LINKS"
                continue
            link = links[0] if links else None
            if latest is not None and latest.status_token == "COMPLETED" and link is None:
                verification_tokens[trial_id] = "MISSING_RESULT_LINK"
                incidents.append(
                    _incident(
                        severity="WARNING",
                        category="COMPLETED_WITHOUT_RESULT_LINK",
                        reason_token="COMPLETED_RESULT_LINK_MISSING",
                        explanation="The trial is completed but has no Mission 95 result link.",
                        trial_id=trial_id,
                        as_of=as_of,
                        evidence={"latest_event_id": latest.event_id},
                    )
                )
                continue
            if link is not None and (
                latest is None
                or latest.status_token != "COMPLETED"
                or latest.reason_token != "SYNTHETIC_CONTROL_COMPLETED"
                or latest.event_timestamp != link.linked_at
            ):
                verification_tokens[trial_id] = "LIFECYCLE_MISMATCH"
                incidents.append(
                    _incident(
                        severity="WARNING",
                        category="RESULT_LINK_WITHOUT_COMPLETED_EVENT",
                        reason_token="RESULT_LINK_LIFECYCLE_MISMATCH",
                        explanation="A result link exists without a matching completed lifecycle.",
                        trial_id=trial_id,
                        as_of=as_of,
                        evidence={
                            "result_link_hash": link.canonical_result_link_hash,
                            "latest_event_id": (
                                latest.event_id if latest is not None else None
                            ),
                        },
                    )
                )
                continue
            if link is None:
                verification_tokens[trial_id] = "NOT_LINKED"
                continue
            result_artifact = self._result_root / link.result_bundle_path
            event_artifact = result_artifact.with_name("event-ledger.json")
            missing_artifacts = [
                path.name
                for path in (result_artifact, event_artifact)
                if not path.is_file()
            ]
            if missing_artifacts:
                verification_tokens[trial_id] = "ARTIFACT_MISSING"
                incidents.append(
                    _incident(
                        severity="WARNING",
                        category="RESULT_ARTIFACT_MISSING",
                        reason_token="RESULT_ARTIFACT_MISSING",
                        explanation="The linked canonical result artifact is missing.",
                        trial_id=trial_id,
                        as_of=as_of,
                        evidence={
                            "result_bundle_id": link.result_bundle_id,
                            "result_bundle_hash": link.result_bundle_hash,
                            "missing_artifacts": missing_artifacts,
                        },
                    )
                )
                continue
            try:
                linked = load_linked_result(
                    result_root=self._result_root,
                    trial_ledger=snapshot_ledger,
                    trial_id=trial_id,
                )
                projection = _result_projection(linked)
                if (
                    projection.implementation_repository_commit
                    != self._expected_repository_commit
                ):
                    raise ControlPlaneError(
                        "IMPLEMENTATION_REPOSITORY_COMMIT_MISMATCH"
                    )
            except EngineError as error:
                if error.reason_token == "RESULT_SCHEMA_INVALID":
                    category = "RESULT_SCHEMA_UNSUPPORTED"
                    token = "SCHEMA_UNSUPPORTED"
                elif error.reason_token in {
                    "RESULT_HASH_MISMATCH",
                    "RESULT_ARTIFACT_MISMATCH",
                }:
                    category = "RESULT_ARTIFACT_TAMPERED"
                    token = "ARTIFACT_TAMPERED"
                else:
                    category = "RESULT_VERIFICATION_FAILED"
                    token = "VERIFICATION_FAILED"
                verification_tokens[trial_id] = token
                incidents.append(
                    _incident(
                        severity="ERROR",
                        category=category,
                        reason_token=error.reason_token,
                        explanation="Mission 95 rejected the linked canonical result.",
                        trial_id=trial_id,
                        as_of=as_of,
                        evidence={
                            "result_bundle_id": link.result_bundle_id,
                            "result_bundle_hash": link.result_bundle_hash,
                        },
                    )
                )
            except (ControlPlaneError, KeyError, TypeError, ValueError) as error:
                verification_tokens[trial_id] = "VERIFICATION_FAILED"
                incidents.append(
                    _incident(
                        severity="ERROR",
                        category="RESULT_VERIFICATION_FAILED",
                        reason_token=getattr(
                            error,
                            "reason_token",
                            "RESULT_PROJECTION_INVALID",
                        ),
                        explanation="The verified result could not be projected safely.",
                        trial_id=trial_id,
                        as_of=as_of,
                        evidence={
                            "result_bundle_id": link.result_bundle_id,
                            "result_bundle_hash": link.result_bundle_hash,
                        },
                    )
                )
            else:
                verification_tokens[trial_id] = "VERIFIED"
                valid_results[trial_id] = projection

        for trial_id, links in link_groups.items():
            if trial_id not in reservations:
                incidents.append(
                    _incident(
                        severity="ERROR",
                        category="DUPLICATE_OR_CONFLICTING_IDENTITY",
                        reason_token="ORPHAN_RESULT_LINK",
                        explanation="A result link has no valid reservation identity.",
                        trial_id=trial_id,
                        as_of=as_of,
                        evidence={
                            "result_link_hashes": [
                                item.canonical_result_link_hash for item in links
                            ]
                        },
                    )
                )

        for trial_id, events in event_groups.items():
            if trial_id not in reservations:
                incidents.append(
                    _incident(
                        severity="ERROR",
                        category="DUPLICATE_OR_CONFLICTING_IDENTITY",
                        reason_token="ORPHAN_TRIAL_EVENT",
                        explanation="A lifecycle event has no valid reservation identity.",
                        trial_id=trial_id,
                        as_of=as_of,
                        evidence={
                            "event_ids": [item.event_id for item in events]
                        },
                    )
                )

        incidents.sort(
            key=lambda item: (
                item.trial_id or "",
                item.category,
                item.incident_id,
            )
        )
        incident_ids: dict[str, list[str]] = defaultdict(list)
        for item in incidents:
            if item.trial_id is not None:
                incident_ids[item.trial_id].append(item.incident_id)

        trials = []
        for reservation in data.reservations:
            events = event_groups.get(reservation.trial_id, [])
            latest = events[-1] if events else None
            links = link_groups.get(reservation.trial_id, [])
            result = valid_results.get(reservation.trial_id)
            budget = budgets.get(reservation.budget_id)
            core = {
                "trial_id": reservation.trial_id,
                "budget_id": reservation.budget_id,
                "experiment_family": (
                    budget.experiment_family
                    if budget is not None
                    else "UNAVAILABLE"
                ),
                "declared_trial_number": reservation.declared_trial_number,
                "initiated_by": reservation.initiated_by,
                "reserved_at": reservation.reserved_at,
                "request_hash": reservation.request_hash,
                "latest_sequence_number": (
                    latest.sequence_number if latest is not None else None
                ),
                "latest_status_token": (
                    latest.status_token if latest is not None else None
                ),
                "latest_reason_token": (
                    latest.reason_token if latest is not None else None
                ),
                "latest_event_timestamp": (
                    latest.event_timestamp if latest is not None else None
                ),
                "event_count": len(events),
                "has_result_link": bool(links),
                "result_verification_token": verification_tokens.get(
                    reservation.trial_id, "NOT_LINKED"
                ),
                "result_bundle_id": (
                    result.result_bundle_id if result is not None else None
                ),
                "result_bundle_hash": (
                    result.result_bundle_hash if result is not None else None
                ),
                "incident_ids": tuple(incident_ids.get(reservation.trial_id, ())),
            }
            trials.append(
                TrialProjection(
                    **core, canonical_trial_projection_hash=canonical_hash(core)
                )
            )
        trials.sort(
            key=lambda item: (
                _parse_normalized_utc(item.reserved_at),
                item.trial_id,
            )
        )
        results = [
            valid_results[item.trial_id]
            for item in trials
            if item.trial_id in valid_results
        ]
        lifecycle = {status: 0 for status in sorted(STATUSES)}
        for trial in trials:
            if trial.latest_status_token in lifecycle:
                lifecycle[trial.latest_status_token] += 1

        if any(item.severity == "CRITICAL" for item in incidents):
            health = "UNAVAILABLE"
        elif any(item.category in _INTEGRITY_CATEGORIES for item in incidents):
            health = "INTEGRITY_FAILURE"
        elif incidents:
            health = "DEGRADED"
        else:
            health = "HEALTHY"
        system_core = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_version": SNAPSHOT_VERSION,
            "as_of": as_of,
            "repository_commit": self._expected_repository_commit,
            "mission_93_contract_id": MISSION_93_CONTRACT_ID,
            "mission_93_contract_hash": MISSION_93_CONTRACT_HASH,
            "mission_94_contract_id": MISSION_94_CONTRACT_ID,
            "mission_94_contract_hash": MISSION_94_CONTRACT_HASH,
            "mission_95_contract_id": MISSION_95_CONTRACT_ID,
            "mission_95_contract_hash": MISSION_95_CONTRACT_HASH,
            "mission_96a_contract_id": MISSION_CONTRACT_ID,
            "mission_96a_contract_hash": MISSION_CONTRACT_HASH,
            "ledger_path_identity": _path_identity(self._ledger.database_path),
            "result_root_path_identity": _path_identity(self._result_root),
            "repository_root_path_identity": _path_identity(
                self._repository_root
            ),
            "contract_verification": dict(self._contract_verification),
            "total_budget_count": data.raw_counts[0],
            "total_reservation_count": data.raw_counts[1],
            "total_event_count": data.raw_counts[2],
            "total_result_link_count": data.raw_counts[3],
            "lifecycle_counts": lifecycle,
            "verified_linked_result_count": len(results),
            "incident_count": len(incidents),
            "health_token": health,
            "authority_projection": dict(AUTHORITY),
        }
        identity_core = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_version": SNAPSHOT_VERSION,
            "system": system_core,
            "trials": [item.as_dict() for item in trials],
            "results": [item.as_dict() for item in results],
            "incidents": [item.as_dict() for item in incidents],
        }
        snapshot_id = f"snapshot-{canonical_hash(identity_core)[:32]}"
        system = SystemProjection(snapshot_id=snapshot_id, **system_core)
        snapshot_core = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "snapshot_version": SNAPSHOT_VERSION,
            "system": system.as_dict(),
            "trials": [item.as_dict() for item in trials],
            "results": [item.as_dict() for item in results],
            "incidents": [item.as_dict() for item in incidents],
        }
        return ControlPlaneSnapshot(
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            snapshot_id=snapshot_id,
            snapshot_version=SNAPSHOT_VERSION,
            system=system,
            trials=tuple(trials),
            results=tuple(results),
            incidents=tuple(incidents),
            canonical_snapshot_hash=canonical_hash(snapshot_core),
        )
