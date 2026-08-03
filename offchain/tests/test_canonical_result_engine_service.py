from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import sqlite3
import subprocess
import threading

import pytest

from offchain.research.admission import (
    AdmissionDecision,
    AdmissionError,
    ControlRegistry,
    DatasetResolver,
    ResearchAdmissionService,
    TrialLedger,
    TrialResultLink,
    canonical_hash,
    canonical_json,
)
import offchain.research.engine_service as public_api
from offchain.research.engine_service import (
    CanonicalResultEngineService,
    EngineError,
    LinkedResult,
    MISSION_AUTHORIZATION_STAGE,
    MISSION_BASE_COMMIT,
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    ResultBundle,
    load_linked_result,
)
from offchain.research.engine_service.models import ExecutionPermit
from offchain.research.engine_service.result_bundle import (
    CODE_IDENTITY,
    COST_MODEL_IDENTITY,
    EXECUTION_MODEL_IDENTITY,
    MISSION93_GAP_05_FIELD_MAP,
    RISK_MODEL_IDENTITY,
    SIMULATOR_IDENTITY,
    _bundle_identity,
    _verify_candidate_result,
    reconstruct_decision_id,
)
from offchain.research.engine_service.strict_json import (
    MAX_ACCOUNTING_VALUE,
    MAX_EVENT_LEDGER_BYTES,
    MAX_EVENTS,
    MAX_FIXTURE_BYTES,
    MAX_RESULT_BYTES,
)


ROOT = Path(__file__).resolve().parents[2]
MISSION_93_CONTRACT_PATH = (
    ROOT / "contracts" / "DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json"
)
CONTRACT_PATH = (
    ROOT / "contracts" / "DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE_V1.json"
)
IMPLEMENTATION_COMMIT = "1" * 40
BOUNDARY_FIXTURE_BYTES = 125_592
BOUNDARY_EVENT_LEDGER_BYTES = 383_768
BOUNDARY_RESULT_BYTES = 12_230
GOLDEN_EVENT_LEDGER_HASH = (
    "ebd13d26c068f206e637e4a57e21f4f74f8a38ae1059df2bb487bdc7c67588f2"
)
GOLDEN_RESULT_HASH = (
    "b00871bdc3bc9ed874142b5d4205c4e9d334e112d8bf23a4ed2e5644a6fa61d8"
)
PRODUCTION_PATHS = {
    "offchain/research/engine_service/__init__.py",
    "offchain/research/engine_service/models.py",
    "offchain/research/engine_service/strict_json.py",
    "offchain/research/engine_service/synthetic_fixture.py",
    "offchain/research/engine_service/synthetic_controls.py",
    "offchain/research/engine_service/result_bundle.py",
    "offchain/research/engine_service/service.py",
}


def event_timestamp(index: int) -> str:
    value = datetime(2026, 8, 3, tzinfo=timezone.utc) + timedelta(seconds=index)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def fixture_value(
    *,
    count: int = 6,
    prices: tuple[int, ...] | None = None,
    fills: tuple[int, ...] | None = None,
    initial_cash_units: int = 1_000_000,
    trade_quantity_units: int = 10_000,
    fee_bps: int = 10,
    slippage_bps: int = 25,
    maximum_width_ids: bool = False,
    timestamps: tuple[str, ...] | None = None,
) -> dict:
    selected_prices = prices or tuple(
        (100_000, 110_000, 105_000, 120_000, 115_000, 125_000)[index % 6]
        for index in range(count)
    )
    selected_fills = fills or tuple(
        (5_000, 10_000, 10_000, 5_000, 10_000, 10_000)[index % 6]
        for index in range(count)
    )
    core = {
        "schema_version": "1.0",
        "fixture_id": "f" * 128 if maximum_width_ids else "synthetic-fixture-v1",
        "instrument_id": "i" * 128 if maximum_width_ids else "SYNTHETIC_INSTRUMENT_1",
        "currency_unit": "c" * 128 if maximum_width_ids else "INTEGER_CASH_UNIT",
        "initial_cash_units": initial_cash_units,
        "trade_quantity_units": trade_quantity_units,
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "events": [
            {
                "event_id": (
                    f"e{index:03d}" + "x" * 124
                    if maximum_width_ids
                    else f"event-{index + 1}"
                ),
                "timestamp": (
                    timestamps[index] if timestamps is not None else event_timestamp(index)
                ),
                "mid_price_units": selected_prices[index],
                "available_fill_bps": selected_fills[index],
            }
            for index in range(count)
        ],
    }
    return {**core, "canonical_fixture_hash": canonical_hash(core)}


def fixture_bytes(**updates) -> bytes:
    return canonical_json(fixture_value(**updates)).encode("utf-8")


def catalog_for(content_hash: str, *, artifact_path: str = "fixtures/synthetic.json") -> dict:
    record = {
        "schema_version": "1.0",
        "dataset_id": "synthetic-dataset-v1",
        "artifact_id": "synthetic-artifact-v1",
        "content_sha256": content_hash,
        "data_class": "SYNTHETIC_FIXTURE",
        "split_identity": "SYNTHETIC_DEVELOPMENT",
        "artifact_path": artifact_path,
        "allowed_authorization_stages": [MISSION_AUTHORIZATION_STAGE],
        "protected": False,
        "provenance_reference": "generated:mission-95-test",
    }
    record["metadata_sha256"] = canonical_hash(record)
    value = {"schema_version": "1.0", "records": [record]}
    value["catalog_hash_sha256"] = canonical_hash(value)
    return value


def request_value(
    content_hash: str,
    *,
    control_identifier: str = "NO_TRADE_CONTROL",
    control_parameters: dict | None = None,
    initiated_by: str = "OPERATOR",
) -> dict:
    core = {
        "schema_version": "1.0",
        "request_id": "request-mission-95-001",
        "controlling_contract_id": MISSION_CONTRACT_ID,
        "controlling_contract_hash": MISSION_CONTRACT_HASH,
        "repository_commit": IMPLEMENTATION_COMMIT,
        "repository_clean": True,
        "budget_id": "budget-mission-95",
        "declared_trial_number": 1,
        "dataset_id": "synthetic-dataset-v1",
        "dataset_hash": content_hash,
        "data_class": "SYNTHETIC_FIXTURE",
        "split_identity": "SYNTHETIC_DEVELOPMENT",
        "authorization_stage": MISSION_AUTHORIZATION_STAGE,
        "control_identifier": control_identifier,
        "control_parameters": control_parameters or {},
        "initiated_by": initiated_by,
        "created_at": "2026-08-03T00:10:00Z",
    }
    return {**core, "canonical_request_hash": canonical_hash(core)}


def make_decision(
    request: dict,
    *,
    trial_id: str,
    resolution_hash: str,
    control_hash: str,
    created_at: str | None = None,
    decision_id: str | None = None,
) -> AdmissionDecision:
    timestamp = created_at or request["created_at"]
    identity = {
        "operation": "admit",
        "request_id": request["request_id"],
        "trial_id": trial_id,
        "decision_token": "ADMITTED",
        "reason_token": "ADMISSION_GATES_PASSED",
        "dataset_resolution_hash": resolution_hash,
        "validated_control_hash": control_hash,
        "budget_id": request["budget_id"],
        "declared_trial_number": request["declared_trial_number"],
        "created_at": timestamp,
    }
    core = {
        "schema_version": "1.0",
        "decision_id": decision_id or f"decision-{canonical_hash(identity)[:32]}",
        "request_id": request["request_id"],
        "trial_id": trial_id,
        "decision_token": "ADMITTED",
        "reason_token": "ADMISSION_GATES_PASSED",
        "dataset_resolution_hash": resolution_hash,
        "validated_control_hash": control_hash,
        "budget_id": request["budget_id"],
        "declared_trial_number": request["declared_trial_number"],
        "created_at": timestamp,
    }
    return AdmissionDecision(**core, canonical_decision_hash=canonical_hash(core))


def environment(
    tmp_path: Path,
    *,
    raw: bytes | None = None,
    control_identifier: str = "NO_TRADE_CONTROL",
    control_parameters: dict | None = None,
    experiment_family: str = "MISSION_95_SYNTHETIC_CONTROLS",
    admission: bool = True,
    reservation_initiated_by: str | None = None,
    reservation_reserved_at: str | None = None,
):
    fixture_raw = raw if raw is not None else fixture_bytes()
    content_hash = hashlib.sha256(fixture_raw).hexdigest()
    artifact_root = tmp_path / "artifacts"
    fixture_path = artifact_root / "fixtures" / "synthetic.json"
    fixture_path.parent.mkdir(parents=True)
    fixture_path.write_bytes(fixture_raw)
    resolver = DatasetResolver(catalog_for(content_hash), artifact_root)
    ledger = TrialLedger(tmp_path / "trials.sqlite3")
    ledger.register_budget(
        budget_id="budget-mission-95",
        controlling_contract_id=MISSION_CONTRACT_ID,
        controlling_contract_hash=MISSION_CONTRACT_HASH,
        experiment_family=experiment_family,
        total_trial_budget=8,
        created_at="2026-08-03T00:00:00Z",
    )
    request = request_value(
        content_hash,
        control_identifier=control_identifier,
        control_parameters=control_parameters,
    )
    if admission:
        admission_service = ResearchAdmissionService(
            controlling_contract_id=MISSION_CONTRACT_ID,
            controlling_contract_hash=MISSION_CONTRACT_HASH,
            repository_commit=IMPLEMENTATION_COMMIT,
            dataset_resolver=resolver,
            trial_ledger=ledger,
        )
        decision = admission_service.admit(request)
        assert decision.decision_token == "ADMITTED"
    else:
        reservation = ledger.reserve(
            budget_id=request["budget_id"],
            declared_trial_number=request["declared_trial_number"],
            request_hash=request["canonical_request_hash"],
            initiated_by=reservation_initiated_by or request["initiated_by"],
            reserved_at=reservation_reserved_at or request["created_at"],
            controlling_contract_id=MISSION_CONTRACT_ID,
            controlling_contract_hash=MISSION_CONTRACT_HASH,
        )
        resolution = resolver.resolve(
            dataset_id=request["dataset_id"],
            requested_hash=request["dataset_hash"],
            data_class=request["data_class"],
            split_identity=request["split_identity"],
            authorization_stage=request["authorization_stage"],
        )
        control = ControlRegistry().validate(
            request["control_identifier"],
            request["control_parameters"],
        )
        ledger.append_event(
            trial_id=reservation.trial_id,
            status_token="ADMITTED",
            reason_token="ADMISSION_GATES_PASSED",
            event_timestamp=request["created_at"],
        )
        decision = make_decision(
            request,
            trial_id=reservation.trial_id,
            resolution_hash=resolution.canonical_resolution_hash,
            control_hash=control.canonical_control_hash,
        )
    engine = CanonicalResultEngineService(
        expected_repository_commit=IMPLEMENTATION_COMMIT,
        dataset_resolver=resolver,
        trial_ledger=ledger,
        result_root=tmp_path / "results",
    )
    return request, decision, engine, ledger, resolver, fixture_path


def assert_engine_reason(expected: str, operation) -> EngineError:
    with pytest.raises(EngineError) as caught:
        operation()
    assert caught.value.reason_token == expected
    return caught.value


def rehash_decision(value: dict) -> dict:
    value["canonical_decision_hash"] = canonical_hash(
        {key: item for key, item in value.items() if key != "canonical_decision_hash"}
    )
    return value


def rehash_result_bundle(value: dict) -> dict:
    value["result_bundle_id"] = (
        f"result-bundle-{canonical_hash(_bundle_identity(value))[:32]}"
    )
    core = dict(value)
    core.pop("canonical_result_hash", None)
    value["canonical_result_hash"] = canonical_hash(core)
    return value


def rewrite_result_and_candidate(
    *,
    engine: CanonicalResultEngineService,
    decision: AdmissionDecision,
    value: dict,
) -> TrialResultLink:
    rehash_result_bundle(value)
    result_path = engine.result_root / decision.trial_id / "result.json"
    result_path.write_text(canonical_json(value), encoding="utf-8")
    return TrialResultLink.create(
        trial_id=decision.trial_id,
        result_bundle_id=value["result_bundle_id"],
        result_bundle_hash=value["canonical_result_hash"],
        result_bundle_path=f"{decision.trial_id}/result.json",
        linked_at=decision.created_at,
    )


def rewrite_event_ledger(value: dict, path: Path) -> bytes:
    core = dict(value)
    core.pop("canonical_event_ledger_hash", None)
    value["canonical_event_ledger_hash"] = canonical_hash(core)
    raw = canonical_json(value).encode("utf-8")
    path.write_bytes(raw)
    return raw


def replace_persisted_link(
    ledger: TrialLedger,
    link: TrialResultLink,
) -> None:
    with sqlite3.connect(ledger.database_path) as connection:
        connection.execute("DROP TRIGGER trial_result_links_no_update")
        connection.execute(
            """
            UPDATE trial_result_links
            SET result_bundle_id = ?, result_bundle_hash = ?,
                result_bundle_path = ?, linked_at = ?,
                canonical_result_link_hash = ?
            WHERE trial_id = ?
            """,
            (
                link.result_bundle_id,
                link.result_bundle_hash,
                link.result_bundle_path,
                link.linked_at,
                link.canonical_result_link_hash,
                link.trial_id,
            ),
        )


def test_contract_identity_hash_and_broad_authority_boundary() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    core = dict(contract)
    assert core.pop("contract_hash_sha256") == MISSION_CONTRACT_HASH
    assert canonical_hash(core) == MISSION_CONTRACT_HASH
    assert contract["contract_id"] == MISSION_CONTRACT_ID
    assert contract["base_commit"] == MISSION_BASE_COMMIT
    assert contract["authorization_stage"] == MISSION_AUTHORIZATION_STAGE
    assert all(value is False for value in contract["authorization_state"].values())


def test_implementation_commit_is_runtime_bound_and_distinct(tmp_path: Path) -> None:
    context = environment(tmp_path)
    linked = context[2].execute(context[0], context[1])
    bundle = linked.result_bundle.as_dict()
    assert IMPLEMENTATION_COMMIT != MISSION_BASE_COMMIT
    assert bundle["mission_contract"]["base_commit"] == MISSION_BASE_COMMIT
    assert (
        bundle["engine"]["implementation_repository_commit"]
        == IMPLEMENTATION_COMMIT
    )


@pytest.mark.parametrize(
    "invalid",
    ["", "A" * 40, "g" * 40, "1" * 39, "1" * 41, True, None],
)
def test_invalid_implementation_commit_format(tmp_path: Path, invalid) -> None:
    raw = fixture_bytes()
    resolver = DatasetResolver(
        catalog_for(hashlib.sha256(raw).hexdigest()),
        tmp_path / "artifacts",
    )
    ledger = TrialLedger(tmp_path / "trials.sqlite3")
    assert_engine_reason(
        "IMPLEMENTATION_REPOSITORY_COMMIT_INVALID",
        lambda: CanonicalResultEngineService(
            expected_repository_commit=invalid,
            dataset_resolver=resolver,
            trial_ledger=ledger,
            result_root=tmp_path / "results",
        ),
    )


def test_exact_decision_id_reconstruction_and_mismatch(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    admission = {
        "request_id": request["request_id"],
        "trial_id": decision.trial_id,
        "budget_id": request["budget_id"],
        "declared_trial_number": request["declared_trial_number"],
        "request_created_at": request["created_at"],
        "dataset_resolution_hash": decision.dataset_resolution_hash,
        "validated_control_hash": decision.validated_control_hash,
    }
    assert reconstruct_decision_id(admission) == decision.decision_id
    forged = decision.as_dict()
    forged["decision_id"] = "decision-" + "f" * 32
    rehash_decision(forged)
    assert_engine_reason(
        "ADMISSION_IDENTITY_MISMATCH",
        lambda: engine.execute(request, forged),
    )
    assert ledger.latest_status(decision.trial_id) == "ADMITTED"


def test_decision_timestamp_mismatch_writes_nothing(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    forged = make_decision(
        request,
        trial_id=decision.trial_id,
        resolution_hash=decision.dataset_resolution_hash,
        control_hash=decision.validated_control_hash,
        created_at="2026-08-03T00:10:01Z",
    )
    assert_engine_reason(
        "ADMISSION_IDENTITY_MISMATCH",
        lambda: engine.execute(request, forged),
    )
    assert ledger.latest_status(decision.trial_id) == "ADMITTED"


@pytest.mark.parametrize(
    ("origin", "reserved_at"),
    [
        ("MANUAL_RECONSTRUCTION", None),
        (None, "2026-08-03T00:10:01Z"),
    ],
)
def test_reservation_origin_and_timestamp_mismatch(
    tmp_path: Path,
    origin: str | None,
    reserved_at: str | None,
) -> None:
    request, decision, engine, ledger, _, _ = environment(
        tmp_path,
        admission=False,
        reservation_initiated_by=origin,
        reservation_reserved_at=reserved_at,
    )
    assert_engine_reason(
        "TRIAL_RESERVATION_MISMATCH",
        lambda: engine.execute(request, decision),
    )
    assert ledger.latest_status(decision.trial_id) == "ADMITTED"


def test_deterministic_trial_id_mismatch_writes_nothing(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    forged = decision.as_dict()
    forged["trial_id"] = "trial-" + "f" * 32
    identity = {
        "operation": "admit",
        "request_id": request["request_id"],
        "trial_id": forged["trial_id"],
        "decision_token": "ADMITTED",
        "reason_token": "ADMISSION_GATES_PASSED",
        "dataset_resolution_hash": forged["dataset_resolution_hash"],
        "validated_control_hash": forged["validated_control_hash"],
        "budget_id": request["budget_id"],
        "declared_trial_number": request["declared_trial_number"],
        "created_at": request["created_at"],
    }
    forged["decision_id"] = f"decision-{canonical_hash(identity)[:32]}"
    rehash_decision(forged)
    assert_engine_reason(
        "TRIAL_RESERVATION_MISMATCH",
        lambda: engine.execute(request, forged),
    )
    assert ledger.latest_status(decision.trial_id) == "ADMITTED"


def test_wrong_mission_95_experiment_family_writes_nothing(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(
        tmp_path,
        experiment_family="OTHER_SYNTHETIC_FAMILY",
    )
    assert_engine_reason(
        "TRIAL_RESERVATION_MISMATCH",
        lambda: engine.execute(request, decision),
    )
    assert ledger.latest_status(decision.trial_id) == "ADMITTED"


@pytest.mark.parametrize(
    "field",
    ["dataset_resolution_hash", "validated_control_hash"],
)
def test_forged_resolution_and_control_hashes_do_not_burn_trial(
    tmp_path: Path,
    field: str,
) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    forged = decision.as_dict()
    forged[field] = "f" * 64
    identity = {
        "operation": "admit",
        "request_id": request["request_id"],
        "trial_id": decision.trial_id,
        "decision_token": "ADMITTED",
        "reason_token": "ADMISSION_GATES_PASSED",
        "dataset_resolution_hash": forged["dataset_resolution_hash"],
        "validated_control_hash": forged["validated_control_hash"],
        "budget_id": request["budget_id"],
        "declared_trial_number": request["declared_trial_number"],
        "created_at": request["created_at"],
    }
    forged["decision_id"] = f"decision-{canonical_hash(identity)[:32]}"
    rehash_decision(forged)
    assert_engine_reason(
        "ADMISSION_IDENTITY_MISMATCH",
        lambda: engine.execute(request, forged),
    )
    assert ledger.latest_status(decision.trial_id) == "ADMITTED"


def test_post_binding_fixture_failure_produces_failed(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, fixture_path = environment(tmp_path)
    fixture_path.write_bytes(fixture_bytes(prices=(100_001,) * 6))
    assert_engine_reason(
        "SYNTHETIC_FIXTURE_HASH_MISMATCH",
        lambda: engine.execute(request, decision),
    )
    assert ledger.event_statuses(decision.trial_id) == (
        "RESERVED",
        "ADMITTED",
        "FAILED",
    )


@pytest.mark.parametrize(
    ("identifier", "parameters"),
    [
        ("NO_TRADE_CONTROL", {}),
        ("BUY_AND_HOLD_CONTROL", {}),
        ("SEEDED_RANDOM_CONTROL", {"seed": 17}),
        ("SIMULATOR_STATE_MACHINE_CONTROL", {"scenario_id": "ROUND_TRIP"}),
        ("SIMULATOR_STATE_MACHINE_CONTROL", {"scenario_id": "STOP_AND_COOLDOWN"}),
        (
            "SIMULATOR_STATE_MACHINE_CONTROL",
            {"scenario_id": "PARTIAL_FILL_SEQUENCE"},
        ),
    ],
)
def test_all_controls_scenarios_and_final_flat_state(
    tmp_path: Path,
    identifier: str,
    parameters: dict,
) -> None:
    request, decision, engine, _, _, _ = environment(
        tmp_path,
        control_identifier=identifier,
        control_parameters=parameters,
    )
    linked = engine.execute(request, decision)
    bundle = linked.result_bundle.as_dict()
    assert bundle["execution"]["final_state"] == "FLAT"
    assert bundle["metrics"]["trial"]["final_position_units"] == 0


def test_integer_rounding_fees_slippage_and_golden_hashes(tmp_path: Path) -> None:
    request, decision, engine, _, _, _ = environment(
        tmp_path,
        control_identifier="BUY_AND_HOLD_CONTROL",
    )
    linked = engine.execute(request, decision)
    bundle = linked.result_bundle.as_dict()
    metrics = bundle["metrics"]["trial"]
    assert metrics["fee_cost_units"] == 232
    assert metrics["slippage_cost_units"] == 575
    assert metrics["gross_result_units"] == 20_000
    assert metrics["net_result_units"] == 19_193
    ledger = json.loads(
        (
            engine.result_root / decision.trial_id / "event-ledger.json"
        ).read_text(encoding="utf-8")
    )
    assert ledger["rows"][0]["executed_delta_units"] == 5_000
    assert ledger["rows"][0]["execution_price_units"] == 100_250
    assert ledger["rows"][0]["fee_cost_units"] == 51
    assert ledger["canonical_event_ledger_hash"] == GOLDEN_EVENT_LEDGER_HASH
    assert bundle["canonical_result_hash"] == GOLDEN_RESULT_HASH


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":"1.0","schema_version":"1.0"}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b"\xef\xbb\xbf{}",
        json.dumps(fixture_value(), indent=2).encode(),
    ],
)
def test_strict_json_rejections(tmp_path: Path, raw: bytes) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path, raw=raw)
    assert_engine_reason(
        "SYNTHETIC_FIXTURE_SCHEMA_INVALID",
        lambda: engine.execute(request, decision),
    )
    assert ledger.latest_status(decision.trial_id) == "FAILED"


def test_symlink_and_path_escape_rejection(tmp_path: Path) -> None:
    raw = fixture_bytes()
    content_hash = hashlib.sha256(raw).hexdigest()
    resolver = DatasetResolver(
        catalog_for(content_hash, artifact_path="../synthetic.json"),
        tmp_path,
    )
    with pytest.raises(AdmissionError):
        resolver.resolve(
            dataset_id="synthetic-dataset-v1",
            requested_hash=content_hash,
            data_class="SYNTHETIC_FIXTURE",
            split_identity="SYNTHETIC_DEVELOPMENT",
            authorization_stage=MISSION_AUTHORIZATION_STAGE,
        )

    request, decision, engine, ledger, _, fixture_path = environment(tmp_path / "link")
    actual = fixture_path.with_name("actual.json")
    fixture_path.rename(actual)
    fixture_path.symlink_to(actual)
    assert_engine_reason(
        "SYNTHETIC_FIXTURE_PATH_UNSAFE",
        lambda: engine.execute(request, decision),
    )
    assert ledger.latest_status(decision.trial_id) == "FAILED"


def test_link_anchored_fresh_process_loading(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    produced = engine.execute(request, decision)
    fresh_ledger = TrialLedger(ledger.database_path)
    loaded = load_linked_result(
        result_root=engine.result_root,
        trial_ledger=fresh_ledger,
        trial_id=decision.trial_id,
    )
    assert loaded == produced
    signature = inspect.signature(load_linked_result)
    assert tuple(signature.parameters) == ("result_root", "trial_ledger", "trial_id")
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )


def test_completed_replay_succeeds_after_fixture_deletion(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, fixture_path = environment(tmp_path)
    first = engine.execute(request, decision)
    fixture_path.unlink()
    second = engine.execute(request, decision)
    assert second == first
    assert ledger.event_statuses(decision.trial_id).count("COMPLETED") == 1


@pytest.mark.parametrize("artifact_name", ["result.json", "event-ledger.json"])
def test_tampering_fails_against_persisted_link(
    tmp_path: Path,
    artifact_name: str,
) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    engine.execute(request, decision)
    path = engine.result_root / decision.trial_id / artifact_name
    value = json.loads(path.read_text(encoding="utf-8"))
    if artifact_name == "result.json":
        value["metrics"]["trial"]["net_result_units"] += 1
    else:
        value["rows"][0]["net_cash_units"] += 1
    path.write_text(canonical_json(value), encoding="utf-8")
    assert_engine_reason(
        "RESULT_HASH_MISMATCH",
        lambda: load_linked_result(
            result_root=engine.result_root,
            trial_ledger=ledger,
            trial_id=decision.trial_id,
        ),
    )


def test_permit_control_target_and_artifact_relationships(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(
        tmp_path,
        control_identifier="SEEDED_RANDOM_CONTROL",
        control_parameters={"seed": 17},
    )
    linked = engine.execute(request, decision)
    bundle = linked.result_bundle.as_dict()
    event_ledger = json.loads(
        (
            engine.result_root / decision.trial_id / "event-ledger.json"
        ).read_text(encoding="utf-8")
    )
    control = ControlRegistry().validate("SEEDED_RANDOM_CONTROL", {"seed": 17})
    permit = ExecutionPermit.issue(
        request_hash=request["canonical_request_hash"],
        decision_hash=decision.canonical_decision_hash,
        trial_id=decision.trial_id,
        dataset_resolution_hash=decision.dataset_resolution_hash,
        validated_control_hash=control.canonical_control_hash,
    )
    targets_hash = canonical_hash(
        [row["target_position_units"] for row in event_ledger["rows"]]
    )
    assert bundle["control"]["validated_control_hash"] == control.canonical_control_hash
    assert bundle["engine"]["permit_hash"] == permit.canonical_permit_hash
    assert bundle["execution"]["targets_hash"] == targets_hash
    assert (
        bundle["artifacts"][0]["canonical_artifact_hash"]
        == event_ledger["canonical_event_ledger_hash"]
    )
    assert load_linked_result(
        result_root=engine.result_root,
        trial_ledger=ledger,
        trial_id=decision.trial_id,
    ) == linked


def test_result_verified_bundle_and_completed_linked_lifecycle(tmp_path: Path) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    linked = engine.execute(request, decision)
    bundle = linked.result_bundle.as_dict()
    assert bundle["result"] == {
        "status_token": "RESULT_VERIFIED",
        "reason_token": "SYNTHETIC_CONTROL_RESULT_VERIFIED",
        "human_explanation": (
            "The synthetic control calculation and canonical artifacts were verified."
        ),
        "recorded_at": request["created_at"],
        "data_start_at": "2026-08-03T00:00:00Z",
        "data_end_at": "2026-08-03T00:00:05Z",
        "failure_stop_or_rejection_reason": None,
    }
    assert linked.trial_status_token == "COMPLETED"
    assert linked.trial_reason_token == "SYNTHETIC_CONTROL_COMPLETED"
    assert linked.trial_linked_at == request["created_at"]


def test_generic_completed_trial_is_not_a_loadable_mission_95_result(
    tmp_path: Path,
) -> None:
    _, decision, engine, ledger, _, _ = environment(tmp_path)
    ledger.append_event(
        trial_id=decision.trial_id,
        status_token="COMPLETED",
        reason_token="GENERIC_MISSION_94_COMPLETION",
        event_timestamp=decision.created_at,
    )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: load_linked_result(
            result_root=engine.result_root,
            trial_ledger=ledger,
            trial_id=decision.trial_id,
        ),
    )


def test_public_result_completion_bypass_is_absent(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    assert not hasattr(TrialLedger, "complete_with_result")
    public_result_methods = {
        name
        for name, member in inspect.getmembers(TrialLedger, inspect.isfunction)
        if not name.startswith("_") and "result" in name
    }
    assert public_result_methods == {"get_result_link"}
    assert engine.execute(request, decision).trial_status_token == "COMPLETED"
    assert ledger.get_result_link(decision.trial_id) is not None


def test_required_fixture_display_and_accounting_identities(tmp_path: Path) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    dataset = engine.execute(request, decision).result_bundle.as_dict()["dataset"]
    assert dataset["instrument_id"] == "SYNTHETIC_INSTRUMENT_1"
    assert dataset["currency_unit"] == "INTEGER_CASH_UNIT"
    assert dataset["initial_cash_units"] == 1_000_000
    assert dataset["trade_quantity_units"] == 10_000
    assert dataset["fee_bps"] == 10
    assert dataset["slippage_bps"] == 25


def test_full_service_concurrent_idempotency(tmp_path: Path) -> None:
    request, decision, engine, ledger, resolver, _ = environment(tmp_path)
    second_engine = CanonicalResultEngineService(
        expected_repository_commit=IMPLEMENTATION_COMMIT,
        dataset_resolver=resolver,
        trial_ledger=TrialLedger(ledger.database_path),
        result_root=engine.result_root,
    )
    barrier = threading.Barrier(3)
    outcomes: list[LinkedResult | EngineError] = []
    lock = threading.Lock()

    def execute(instance: CanonicalResultEngineService) -> None:
        barrier.wait()
        try:
            outcome: LinkedResult | EngineError = instance.execute(request, decision)
        except EngineError as error:
            outcome = error
        with lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=execute, args=(engine,)),
        threading.Thread(target=execute, args=(second_engine,)),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert len(outcomes) == 2
    assert all(isinstance(outcome, LinkedResult) for outcome in outcomes)
    assert outcomes[0] == outcomes[1]
    assert ledger.event_statuses(decision.trial_id).count("COMPLETED") == 1
    assert ledger.get_result_link(decision.trial_id) is not None


def test_bounded_sqlite_contention_and_exact_retry(tmp_path: Path) -> None:
    request, decision, engine, ledger, resolver, _ = environment(tmp_path)
    bounded_ledger = TrialLedger(ledger.database_path, timeout=0.01)
    bounded_engine = CanonicalResultEngineService(
        expected_repository_commit=IMPLEMENTATION_COMMIT,
        dataset_resolver=resolver,
        trial_ledger=bounded_ledger,
        result_root=engine.result_root,
    )
    blocker = sqlite3.connect(ledger.database_path, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        assert_engine_reason(
            "SQLITE_CONTENTION",
            lambda: bounded_engine.execute(request, decision),
        )
    finally:
        blocker.rollback()
        blocker.close()
    assert ledger.latest_status(decision.trial_id) == "ADMITTED"
    assert bounded_engine.execute(request, decision).trial_status_token == "COMPLETED"


def boundary_fixture_bytes(count: int) -> bytes:
    return fixture_bytes(
        count=count,
        prices=(MAX_ACCOUNTING_VALUE,) * count,
        fills=(10_000,) * count,
        initial_cash_units=MAX_ACCOUNTING_VALUE,
        trade_quantity_units=10_000,
        fee_bps=0,
        slippage_bps=0,
        maximum_width_ids=True,
    )


def test_max_events_worst_case_values_and_artifact_limits(tmp_path: Path) -> None:
    raw = boundary_fixture_bytes(MAX_EVENTS)
    assert len(raw) == BOUNDARY_FIXTURE_BYTES <= MAX_FIXTURE_BYTES
    request, decision, engine, ledger, _, _ = environment(
        tmp_path,
        raw=raw,
        control_identifier="NO_TRADE_CONTROL",
    )
    linked = engine.execute(request, decision)
    event_size = (
        engine.result_root / decision.trial_id / "event-ledger.json"
    ).stat().st_size
    result_size = (
        engine.result_root / decision.trial_id / "result.json"
    ).stat().st_size
    assert event_size == BOUNDARY_EVENT_LEDGER_BYTES <= MAX_EVENT_LEDGER_BYTES
    assert result_size == BOUNDARY_RESULT_BYTES <= MAX_RESULT_BYTES
    assert linked.result_bundle.as_dict()["execution"]["event_count"] == MAX_EVENTS
    assert load_linked_result(
        result_root=engine.result_root,
        trial_ledger=ledger,
        trial_id=decision.trial_id,
    ) == linked


def test_max_events_plus_one_is_rejected(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(
        tmp_path,
        raw=boundary_fixture_bytes(MAX_EVENTS + 1),
    )
    assert_engine_reason(
        "SYNTHETIC_FIXTURE_SCHEMA_INVALID",
        lambda: engine.execute(request, decision),
    )
    assert ledger.latest_status(decision.trial_id) == "FAILED"


def test_accounting_value_above_limit_is_rejected(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(
        tmp_path,
        raw=fixture_bytes(initial_cash_units=MAX_ACCOUNTING_VALUE + 1),
    )
    assert_engine_reason(
        "SYNTHETIC_FIXTURE_SCHEMA_INVALID",
        lambda: engine.execute(request, decision),
    )
    assert ledger.latest_status(decision.trial_id) == "FAILED"


class FailureInjectingLedger(TrialLedger):
    def append_event(self, **kwargs) -> None:
        if kwargs.get("status_token") == "FAILED":
            raise AdmissionError("INJECTED_SQLITE_FAILURE")
        super().append_event(**kwargs)


def test_terminalization_failure_is_visible(tmp_path: Path) -> None:
    request, decision, engine, ledger, resolver, fixture_path = environment(tmp_path)
    fixture_path.write_bytes(fixture_bytes(prices=(100_001,) * 6))
    failing_engine = CanonicalResultEngineService(
        expected_repository_commit=IMPLEMENTATION_COMMIT,
        dataset_resolver=resolver,
        trial_ledger=FailureInjectingLedger(ledger.database_path),
        result_root=engine.result_root,
    )
    error = assert_engine_reason(
        "TRIAL_TERMINALIZATION_FAILED",
        lambda: failing_engine.execute(request, decision),
    )
    assert error.original_reason_token == "SYNTHETIC_FIXTURE_HASH_MISMATCH"
    assert error.__cause__ is not None
    assert ledger.latest_status(decision.trial_id) == "ADMITTED"


def test_result_bundle_deep_immutability_and_detachment(tmp_path: Path) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    linked = engine.execute(request, decision)
    assert isinstance(linked.result_bundle, ResultBundle)
    detached = linked.result_bundle.as_dict()
    detached["dataset"]["instrument_id"] = "MUTATED"
    detached["warnings"].append("MUTATED")
    fresh = linked.result_bundle.as_dict()
    assert fresh["dataset"]["instrument_id"] == "SYNTHETIC_INSTRUMENT_1"
    assert "MUTATED" not in fresh["warnings"]
    second = linked.result_bundle.as_dict()
    assert second is not fresh
    assert second["dataset"] is not fresh["dataset"]
    with pytest.raises(FrozenInstanceError):
        linked.trial_status_token = "FAILED"  # type: ignore[misc]


def test_result_bundle_rejects_arbitrary_public_construction() -> None:
    with pytest.raises(TypeError):
        ResultBundle(b"{}")
    with pytest.raises(TypeError):
        ResultBundle(_canonical_bytes=b"{}")
    assert not hasattr(ResultBundle, "from_mapping")


def test_request_hash_is_independently_reconstructed(tmp_path: Path) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    request_core = {
        "schema_version": "1.0",
        "request_id": bundle["admission"]["request_id"],
        "controlling_contract_id": bundle["mission_contract"]["contract_id"],
        "controlling_contract_hash": bundle["mission_contract"]["contract_hash"],
        "repository_commit": bundle["engine"]["implementation_repository_commit"],
        "repository_clean": bundle["admission"]["repository_clean"],
        "budget_id": bundle["admission"]["budget_id"],
        "declared_trial_number": bundle["admission"]["declared_trial_number"],
        "dataset_id": bundle["dataset"]["dataset_id"],
        "dataset_hash": bundle["dataset"]["dataset_content_hash"],
        "data_class": bundle["dataset"]["data_class"],
        "split_identity": bundle["dataset"]["split_identity"],
        "authorization_stage": bundle["mission_contract"]["authorization_stage"],
        "control_identifier": bundle["control"]["control_identifier"],
        "control_parameters": bundle["control"]["control_parameters"],
        "initiated_by": bundle["admission"]["initiated_by"],
        "created_at": bundle["admission"]["request_created_at"],
    }
    assert canonical_hash(request_core) == bundle["admission"]["request_hash"]
    bundle["admission"]["initiated_by"] = "MANUAL_RECONSTRUCTION"
    candidate = rewrite_result_and_candidate(
        engine=engine,
        decision=decision,
        value=bundle,
    )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: _verify_candidate_result(
            result_root=engine.result_root,
            candidate_link=candidate,
        ),
    )


def test_fixture_hash_and_content_hash_are_reconstructed_without_source(
    tmp_path: Path,
) -> None:
    request, decision, engine, _, _, fixture_path = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    ledger = json.loads(
        (engine.result_root / decision.trial_id / "event-ledger.json").read_text()
    )
    fixture_path.unlink()
    fixture_core = {
        "schema_version": "1.0",
        "fixture_id": bundle["dataset"]["fixture_id"],
        "instrument_id": bundle["dataset"]["instrument_id"],
        "currency_unit": bundle["dataset"]["currency_unit"],
        "initial_cash_units": bundle["dataset"]["initial_cash_units"],
        "trade_quantity_units": bundle["dataset"]["trade_quantity_units"],
        "fee_bps": bundle["dataset"]["fee_bps"],
        "slippage_bps": bundle["dataset"]["slippage_bps"],
        "events": [
            {
                field: row[field]
                for field in (
                    "event_id",
                    "timestamp",
                    "mid_price_units",
                    "available_fill_bps",
                )
            }
            for row in ledger["rows"]
        ],
    }
    fixture_hash = canonical_hash(fixture_core)
    fixture_complete = {
        **fixture_core,
        "canonical_fixture_hash": fixture_hash,
    }
    assert fixture_hash == bundle["dataset"]["fixture_hash"]
    assert (
        hashlib.sha256(canonical_json(fixture_complete).encode()).hexdigest()
        == bundle["dataset"]["dataset_content_hash"]
    )
    assert engine.execute(request, decision).trial_status_token == "COMPLETED"


@pytest.mark.parametrize("rewrite_upstream_fixture_hashes", [False, True])
def test_fixture_tamper_fails_with_downstream_or_fixture_hashes_recomputed(
    tmp_path: Path,
    rewrite_upstream_fixture_hashes: bool,
) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    ledger_path = engine.result_root / decision.trial_id / "event-ledger.json"
    ledger = json.loads(ledger_path.read_text())
    ledger["rows"][0]["mid_price_units"] += 1
    if rewrite_upstream_fixture_hashes:
        fixture_core = {
            "schema_version": "1.0",
            "fixture_id": bundle["dataset"]["fixture_id"],
            "instrument_id": bundle["dataset"]["instrument_id"],
            "currency_unit": bundle["dataset"]["currency_unit"],
            "initial_cash_units": bundle["dataset"]["initial_cash_units"],
            "trade_quantity_units": bundle["dataset"]["trade_quantity_units"],
            "fee_bps": bundle["dataset"]["fee_bps"],
            "slippage_bps": bundle["dataset"]["slippage_bps"],
            "events": [
                {
                    field: row[field]
                    for field in (
                        "event_id",
                        "timestamp",
                        "mid_price_units",
                        "available_fill_bps",
                    )
                }
                for row in ledger["rows"]
            ],
        }
        fixture_hash = canonical_hash(fixture_core)
        bundle["dataset"]["fixture_hash"] = fixture_hash
        ledger["fixture_hash"] = fixture_hash
        bundle["dataset"]["dataset_content_hash"] = hashlib.sha256(
            canonical_json(
                {**fixture_core, "canonical_fixture_hash": fixture_hash}
            ).encode()
        ).hexdigest()
    ledger_raw = rewrite_event_ledger(ledger, ledger_path)
    bundle["artifacts"][0]["byte_sha256"] = hashlib.sha256(ledger_raw).hexdigest()
    bundle["artifacts"][0]["canonical_artifact_hash"] = ledger[
        "canonical_event_ledger_hash"
    ]
    candidate = rewrite_result_and_candidate(
        engine=engine,
        decision=decision,
        value=bundle,
    )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: _verify_candidate_result(
            result_root=engine.result_root,
            candidate_link=candidate,
        ),
    )


@pytest.mark.parametrize(
    ("mutation", "wrong_value"),
    [
        ("schema_version", "2.0"),
        ("artifact_type", "ARBITRARY_MATCHING_LEDGER_TYPE"),
    ],
)
def test_rehashed_ledger_schema_and_artifact_type_tampering_fails(
    tmp_path: Path,
    mutation: str,
    wrong_value: str,
) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    ledger_path = engine.result_root / decision.trial_id / "event-ledger.json"
    ledger = json.loads(ledger_path.read_text())
    ledger[mutation] = wrong_value
    if mutation == "artifact_type":
        bundle["artifacts"][0]["artifact_type"] = wrong_value
    ledger_raw = rewrite_event_ledger(ledger, ledger_path)
    bundle["artifacts"][0]["byte_sha256"] = hashlib.sha256(ledger_raw).hexdigest()
    bundle["artifacts"][0]["canonical_artifact_hash"] = ledger[
        "canonical_event_ledger_hash"
    ]
    candidate = rewrite_result_and_candidate(
        engine=engine,
        decision=decision,
        value=bundle,
    )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: _verify_candidate_result(
            result_root=engine.result_root,
            candidate_link=candidate,
        ),
    )


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [
        ("baseline_id", "ARBITRARY_BASELINE"),
        ("baseline_role", "TRIAL"),
    ],
)
def test_rehashed_benchmark_identity_and_role_tampering_fails(
    tmp_path: Path,
    field: str,
    wrong_value: str,
) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    bundle["metrics"]["benchmark"][field] = wrong_value
    candidate = rewrite_result_and_candidate(
        engine=engine,
        decision=decision,
        value=bundle,
    )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: _verify_candidate_result(
            result_root=engine.result_root,
            candidate_link=candidate,
        ),
    )


@pytest.mark.parametrize("metric_group", ["trial", "benchmark"])
def test_rehashed_contradictory_final_position_tampering_fails(
    tmp_path: Path,
    metric_group: str,
) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    metrics = (
        bundle["metrics"]["trial"]
        if metric_group == "trial"
        else bundle["metrics"]["benchmark"]["metrics"]
    )
    metrics["final_position_units"] = 10_000
    candidate = rewrite_result_and_candidate(
        engine=engine,
        decision=decision,
        value=bundle,
    )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: _verify_candidate_result(
            result_root=engine.result_root,
            candidate_link=candidate,
        ),
    )


@pytest.mark.parametrize("metric_group", ["trial", "benchmark"])
def test_rehashed_contradictory_initial_cash_tampering_fails(
    tmp_path: Path,
    metric_group: str,
) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    metrics = (
        bundle["metrics"]["trial"]
        if metric_group == "trial"
        else bundle["metrics"]["benchmark"]["metrics"]
    )
    metrics["initial_cash_units"] += 1
    candidate = rewrite_result_and_candidate(
        engine=engine,
        decision=decision,
        value=bundle,
    )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: _verify_candidate_result(
            result_root=engine.result_root,
            candidate_link=candidate,
        ),
    )


def test_dataset_resolution_is_independently_reconstructed(tmp_path: Path) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    dataset = engine.execute(request, decision).result_bundle.as_dict()["dataset"]
    core = {
        "schema_version": "1.0",
        "dataset_id": dataset["dataset_id"],
        "artifact_id": dataset["artifact_id"],
        "content_sha256": dataset["dataset_content_hash"],
        "metadata_sha256": dataset["metadata_hash"],
        "data_class": dataset["data_class"],
        "split_identity": dataset["split_identity"],
        "artifact_path": dataset["artifact_path"],
        "authorization_stage": dataset["resolution_authorization_stage"],
        "provenance_reference": dataset["provenance_reference"],
        "reason_token": dataset["resolution_reason_token"],
    }
    assert canonical_hash(core) == dataset["resolution_hash"]


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("provenance_reference", "generated:changed"),
        ("artifact_path", "fixtures/changed.json"),
        ("metadata_hash", "f" * 64),
        ("resolution_authorization_stage", "OTHER_STAGE"),
        ("resolution_reason_token", "OTHER_REASON"),
    ],
)
def test_dataset_resolution_field_tampering_fails(
    tmp_path: Path,
    field: str,
    replacement: str,
) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    bundle["dataset"][field] = replacement
    candidate = rewrite_result_and_candidate(
        engine=engine,
        decision=decision,
        value=bundle,
    )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: _verify_candidate_result(
            result_root=engine.result_root,
            candidate_link=candidate,
        ),
    )


def test_self_rehashed_resolution_still_fails_admitted_identity(tmp_path: Path) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    dataset = bundle["dataset"]
    dataset["provenance_reference"] = "generated:self-rehashed"
    resolution_core = {
        "schema_version": "1.0",
        "dataset_id": dataset["dataset_id"],
        "artifact_id": dataset["artifact_id"],
        "content_sha256": dataset["dataset_content_hash"],
        "metadata_sha256": dataset["metadata_hash"],
        "data_class": dataset["data_class"],
        "split_identity": dataset["split_identity"],
        "artifact_path": dataset["artifact_path"],
        "authorization_stage": dataset["resolution_authorization_stage"],
        "provenance_reference": dataset["provenance_reference"],
        "reason_token": dataset["resolution_reason_token"],
    }
    dataset["resolution_hash"] = canonical_hash(resolution_core)
    candidate = rewrite_result_and_candidate(
        engine=engine,
        decision=decision,
        value=bundle,
    )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: _verify_candidate_result(
            result_root=engine.result_root,
            candidate_link=candidate,
        ),
    )


def test_exact_component_identities_and_wrong_identity_rejection(tmp_path: Path) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    expected = {
        "code_identity": CODE_IDENTITY,
        "simulator_identity": SIMULATOR_IDENTITY,
        "execution_model_identity": EXECUTION_MODEL_IDENTITY,
        "cost_model_identity": COST_MODEL_IDENTITY,
        "risk_model_identity": RISK_MODEL_IDENTITY,
    }
    assert {field: bundle["engine"][field] for field in expected} == expected
    bundle["engine"]["risk_model_identity"] = "WRONG"
    candidate = rewrite_result_and_candidate(
        engine=engine,
        decision=decision,
        value=bundle,
    )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: _verify_candidate_result(
            result_root=engine.result_root,
            candidate_link=candidate,
        ),
    )


def test_exact_golden_and_irregular_timing_diagnostics(tmp_path: Path) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path / "golden")
    timing = engine.execute(request, decision).result_bundle.as_dict()["execution"][
        "timing_diagnostics"
    ]
    assert timing == {
        "event_count": 6,
        "interval_count": 5,
        "data_start_at": "2026-08-03T00:00:00Z",
        "data_end_at": "2026-08-03T00:00:05Z",
        "duration_microseconds": 5_000_000,
        "minimum_interval_microseconds": 1_000_000,
        "maximum_interval_microseconds": 1_000_000,
        "nonpositive_interval_count": 0,
    }
    timestamps = (
        "2026-08-03T00:00:00Z",
        "2026-08-03T00:00:00.000001Z",
        "2026-08-03T00:00:00.250001Z",
        "2026-08-03T00:00:01.250001Z",
        "2026-08-03T00:00:03.250001Z",
        "2026-08-03T00:00:05.000001Z",
    )
    context = environment(
        tmp_path / "irregular",
        raw=fixture_bytes(timestamps=timestamps),
    )
    irregular = context[2].execute(context[0], context[1]).result_bundle.as_dict()[
        "execution"
    ]["timing_diagnostics"]
    assert irregular["duration_microseconds"] == 5_000_001
    assert irregular["minimum_interval_microseconds"] == 1
    assert irregular["maximum_interval_microseconds"] == 2_000_000
    assert irregular["nonpositive_interval_count"] == 0


def test_timing_uses_only_integer_microsecond_arithmetic() -> None:
    from offchain.research.engine_service import synthetic_fixture

    source = inspect.getsource(synthetic_fixture._microseconds)
    assert "total_seconds" not in source
    assert ".timestamp" not in source
    assert "*" in source
    diagnostics = synthetic_fixture._timing_diagnostics(
        ("2026-08-03T00:00:00Z", "2026-08-04T00:00:00.000001Z")
    )
    assert diagnostics["duration_microseconds"] == 86_400_000_001
    assert all(
        type(value) is int
        for key, value in diagnostics.items()
        if key not in {"data_start_at", "data_end_at"}
    )


def test_nonpositive_fixture_interval_is_rejected(tmp_path: Path) -> None:
    timestamps = tuple(event_timestamp(index) for index in range(6))
    timestamps = (timestamps[0], timestamps[0], *timestamps[2:])
    request, decision, engine, ledger, _, _ = environment(
        tmp_path,
        raw=fixture_bytes(timestamps=timestamps),
    )
    assert_engine_reason(
        "SYNTHETIC_FIXTURE_SCHEMA_INVALID",
        lambda: engine.execute(request, decision),
    )
    assert ledger.latest_status(decision.trial_id) == "FAILED"


def test_mission93_gap_05_exact_ordered_field_map_resolves(tmp_path: Path) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    required = json.loads(MISSION_93_CONTRACT_PATH.read_text())[
        "future_result_bundle_contract"
    ]["required_fields"]
    mapping = bundle["mission93_gap_05_field_map"]
    contract_mapping = json.loads(CONTRACT_PATH.read_text())[
        "mission93_gap_05_field_map"
    ]
    assert len(mapping) == len(required) == 33
    assert [entry["mission93_field"] for entry in mapping] == required
    assert len({entry["mission93_field"] for entry in mapping}) == len(required)
    assert mapping == [
        {
            "mission93_field": field,
            "mission95_paths": list(paths),
            "cardinality": cardinality,
            "transformation": transformation,
        }
        for field, paths, cardinality, transformation in MISSION93_GAP_05_FIELD_MAP
    ]
    assert contract_mapping == mapping
    for entry in mapping:
        assert set(entry) == {
            "mission93_field",
            "mission95_paths",
            "cardinality",
            "transformation",
        }
        assert entry["cardinality"] in {
            "SCALAR",
            "SINGLETON_LIST",
            "OBJECT",
            "ARRAY",
        }
        assert entry["transformation"] in {
            "DIRECT",
            "SINGLETON_PROJECTION",
            "FIELD_GROUP",
        }
        for path in entry["mission95_paths"]:
            if path == "$.artifacts[].relative_path":
                assert all("relative_path" in artifact for artifact in bundle["artifacts"])
                continue
            value = bundle
            for part in path.removeprefix("$.").split("."):
                value = value[part]
    serialized = canonical_json(mapping).casefold()
    assert not any(
        forbidden in serialized
        for forbidden in ("executable", "expression", "ui logic", "fallback")
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("event_id", "event-" + "f" * 32),
        ("canonical_event_hash", "f" * 64),
        ("event_timestamp", "2026-08-03T00:10:01Z"),
        ("reason_token", "OTHER_COMPLETION"),
        ("sequence_number", 99),
    ],
)
def test_trial_event_identity_tampering_fails_closed(
    tmp_path: Path,
    field: str,
    replacement,
) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    engine.execute(request, decision)
    with sqlite3.connect(ledger.database_path) as connection:
        connection.execute("DROP TRIGGER trial_events_no_update")
        connection.execute(
            f"UPDATE trial_events SET {field} = ? WHERE trial_id = ? AND status_token = 'COMPLETED'",
            (replacement, decision.trial_id),
        )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: load_linked_result(
            result_root=engine.result_root,
            trial_ledger=ledger,
            trial_id=decision.trial_id,
        ),
    )


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_result_link_update_and_delete_triggers_preserve_original(
    tmp_path: Path,
    operation: str,
) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    engine.execute(request, decision)
    original = ledger.get_result_link(decision.trial_id)
    assert original is not None
    with sqlite3.connect(ledger.database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            if operation == "UPDATE":
                connection.execute(
                    "UPDATE trial_result_links SET linked_at = ? WHERE trial_id = ?",
                    ("2026-08-03T00:10:01Z", decision.trial_id),
                )
            else:
                connection.execute(
                    "DELETE FROM trial_result_links WHERE trial_id = ?",
                    (decision.trial_id,),
                )
    assert ledger.get_result_link(decision.trial_id) == original


def test_persisted_link_remains_trust_anchor_after_self_rehash(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    bundle["metrics"]["trial"]["net_result_units"] += 1
    rehash_result_bundle(bundle)
    (engine.result_root / decision.trial_id / "result.json").write_text(
        canonical_json(bundle),
        encoding="utf-8",
    )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: load_linked_result(
            result_root=engine.result_root,
            trial_ledger=ledger,
            trial_id=decision.trial_id,
        ),
    )


@pytest.mark.parametrize(
    ("artifact_name", "target_location"),
    [
        ("result.json", "inside"),
        ("result.json", "outside"),
        ("event-ledger.json", "inside"),
        ("event-ledger.json", "outside"),
    ],
)
def test_result_artifact_symlinks_are_rejected(
    tmp_path: Path,
    artifact_name: str,
    target_location: str,
) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    engine.execute(request, decision)
    path = engine.result_root / decision.trial_id / artifact_name
    target = (
        path.with_name(f"{artifact_name}.real")
        if target_location == "inside"
        else tmp_path / f"outside-{artifact_name}"
    )
    path.replace(target)
    path.symlink_to(target)
    assert_engine_reason(
        "RESULT_PATH_UNSAFE",
        lambda: load_linked_result(
            result_root=engine.result_root,
            trial_ledger=ledger,
            trial_id=decision.trial_id,
        ),
    )


def test_result_directory_and_root_symlinks_are_rejected(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path / "directory")
    engine.execute(request, decision)
    directory = engine.result_root / decision.trial_id
    backing = engine.result_root / f"{decision.trial_id}-real"
    directory.replace(backing)
    directory.symlink_to(backing, target_is_directory=True)
    assert_engine_reason(
        "RESULT_PATH_UNSAFE",
        lambda: load_linked_result(
            result_root=engine.result_root,
            trial_ledger=ledger,
            trial_id=decision.trial_id,
        ),
    )

    second = environment(tmp_path / "root")
    second[2].execute(second[0], second[1])
    root_link = tmp_path / "result-root-link"
    root_link.symlink_to(second[2].result_root, target_is_directory=True)
    assert_engine_reason(
        "RESULT_PATH_UNSAFE",
        lambda: load_linked_result(
            result_root=root_link,
            trial_ledger=second[3],
            trial_id=second[1].trial_id,
        ),
    )


@pytest.mark.parametrize("relative_path", ["../event-ledger.json", "/tmp/event-ledger.json"])
def test_invalid_artifact_paths_are_rejected(
    tmp_path: Path,
    relative_path: str,
) -> None:
    request, decision, engine, _, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    bundle["artifacts"][0]["relative_path"] = relative_path
    candidate = rewrite_result_and_candidate(
        engine=engine,
        decision=decision,
        value=bundle,
    )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: _verify_candidate_result(
            result_root=engine.result_root,
            candidate_link=candidate,
        ),
    )


@pytest.mark.parametrize("mode", ["missing", "non_regular"])
def test_missing_and_nonregular_artifacts_are_rejected(
    tmp_path: Path,
    mode: str,
) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    engine.execute(request, decision)
    path = engine.result_root / decision.trial_id / "event-ledger.json"
    path.unlink()
    if mode == "non_regular":
        path.mkdir()
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: load_linked_result(
            result_root=engine.result_root,
            trial_ledger=ledger,
            trial_id=decision.trial_id,
        ),
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("control_identifier", "UNKNOWN_CONTROL"),
        ("control_parameters", {"unexpected": True}),
    ],
)
def test_malformed_control_content_returns_engine_error(
    tmp_path: Path,
    field: str,
    replacement,
) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    bundle["control"][field] = replacement
    candidate = rewrite_result_and_candidate(
        engine=engine,
        decision=decision,
        value=bundle,
    )
    replace_persisted_link(ledger, candidate)
    with pytest.raises(EngineError):
        load_linked_result(
            result_root=engine.result_root,
            trial_ledger=ledger,
            trial_id=decision.trial_id,
        )


def test_public_loader_normalizes_internal_admission_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    engine.execute(request, decision)

    def fail_validation(*args, **kwargs):
        raise AdmissionError("CONTROL_UNKNOWN")

    monkeypatch.setattr(ControlRegistry, "validate", fail_validation)
    error = assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: load_linked_result(
            result_root=engine.result_root,
            trial_ledger=ledger,
            trial_id=decision.trial_id,
        ),
    )
    assert isinstance(error.__cause__, AdmissionError)


def test_malformed_persisted_link_is_normalized_to_engine_error(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    engine.execute(request, decision)
    with sqlite3.connect(ledger.database_path) as connection:
        connection.execute("DROP TRIGGER trial_result_links_no_update")
        connection.execute(
            """
            UPDATE trial_result_links
            SET result_bundle_path = '../result.json'
            WHERE trial_id = ?
            """,
            (decision.trial_id,),
        )
    assert_engine_reason(
        "RESULT_ARTIFACT_MISMATCH",
        lambda: load_linked_result(
            result_root=engine.result_root,
            trial_ledger=ledger,
            trial_id=decision.trial_id,
        ),
    )


def test_malformed_bundle_fields_return_engine_error(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = environment(tmp_path)
    bundle = engine.execute(request, decision).result_bundle.as_dict()
    del bundle["dataset"]["instrument_id"]
    candidate = rewrite_result_and_candidate(
        engine=engine,
        decision=decision,
        value=bundle,
    )
    replace_persisted_link(ledger, candidate)
    assert_engine_reason(
        "RESULT_SCHEMA_INVALID",
        lambda: load_linked_result(
            result_root=engine.result_root,
            trial_ledger=ledger,
            trial_id=decision.trial_id,
        ),
    )


def test_service_verifies_candidate_before_internal_finalization() -> None:
    source = inspect.getsource(CanonicalResultEngineService.execute)
    assert source.index("_verify_candidate_result(") < source.index(
        "._complete_with_verified_result("
    )


def test_exact_narrow_public_exports() -> None:
    assert set(public_api.__all__) == {
        "CanonicalResultEngineService",
        "ENGINE_ID",
        "ENGINE_VERSION",
        "EngineError",
        "KERNEL_ID",
        "KERNEL_VERSION",
        "LinkedResult",
        "MISSION_AUTHORIZATION_STAGE",
        "MISSION_BASE_COMMIT",
        "MISSION_CONTRACT_HASH",
        "MISSION_CONTRACT_ID",
        "RESULT_BUNDLE_VERSION",
        "ResultBundle",
        "load_linked_result",
    }
    for forbidden in (
        "ExecutionPermit",
        "ExecutionOutcome",
        "SyntheticEvent",
        "SyntheticFixture",
        "load_result_bundle",
    ):
        assert not hasattr(public_api, forbidden)


def test_exact_package_inventory_standard_library_and_no_capabilities() -> None:
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "offchain/research/engine_service").iterdir()
        if path.is_file()
    }
    assert actual == PRODUCTION_PATHS
    forbidden_roots = {
        "requests",
        "urllib",
        "http",
        "socket",
        "subprocess",
        "ccxt",
        "freqtrade",
        "torch",
        "tensorflow",
        "sklearn",
        "random",
    }
    forbidden_fragments = (
        "market_data",
        "historical_backtest",
        "historical_simulator",
        "alpha_search",
        "strategy",
        "training",
        "dashboard",
        "exchange",
    )
    for relative in PRODUCTION_PATHS:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imports.append(node.module)
        assert not {name.split(".")[0] for name in imports} & forbidden_roots
        assert not any(
            fragment in name.casefold()
            for name in imports
            for fragment in forbidden_fragments
        )
    assert not hasattr(CanonicalResultEngineService, "register")
    assert not hasattr(CanonicalResultEngineService, "execute_strategy")


def test_no_dependency_changes() -> None:
    assert subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            MISSION_BASE_COMMIT,
            "--",
            "offchain/requirements.txt",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
    ).returncode == 0
