from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import threading

import pytest

from offchain.research.admission import (
    AdmissionError,
    ControlRegistry,
    DatasetResolver,
    ResearchAdmissionRequest,
    ResearchAdmissionService,
    TrialLedger,
    ValidatedControl,
    canonical_hash,
)


ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = "7b1d7e035d006d5ec839486105b94e4a6b7d15bc"
CONTRACT_PATH = ROOT / "contracts" / "DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json"
CONTRACT_HASH = "e4070b52a0f2dbc8ce34ea00d0a732c2aed25c9c21e5acfccc3f9d791dba6193"
CONTRACT_ID = "deltagrid-research-admission-core-v1"
PRODUCTION_PATHS = {
    "offchain/research/admission/__init__.py",
    "offchain/research/admission/models.py",
    "offchain/research/admission/dataset_resolver.py",
    "offchain/research/admission/trial_ledger.py",
    "offchain/research/admission/control_registry.py",
    "offchain/research/admission/service.py",
}
FALSE_AUTHORITIES = {
    "research_reopened",
    "market_data_access_authorized",
    "real_market_backtest_authorized",
    "development_market_evaluation_authorized",
    "validation_access_authorized",
    "holdout_access_authorized",
    "control_execution_authorized",
    "strategy_execution_authorized",
    "model_training_authorized",
    "paper_trading_authorized",
    "live_trading_authorized",
    "exchange_access_authorized",
    "capital_deployment_authorized",
    "autonomous_research_authorized",
    "autonomous_promotion_authorized",
}
REQUIRED_REASONS = {
    "DIRTY_REPOSITORY",
    "CONTRACT_ID_MISMATCH",
    "CONTRACT_HASH_MISMATCH",
    "BUDGET_UNKNOWN",
    "BUDGET_DEFINITION_MISMATCH",
    "TRIAL_BUDGET_EXHAUSTED",
    "DECLARED_TRIAL_ALREADY_USED",
    "REQUEST_ALREADY_RESERVED",
    "DATASET_UNKNOWN",
    "DATASET_HASH_MISMATCH",
    "DATASET_CLASS_UNAUTHORIZED",
    "DATASET_PATH_UNSAFE",
    "AUTHORIZATION_STAGE_MISMATCH",
    "PROTECTED_DATA_FORBIDDEN",
    "VALIDATION_FORBIDDEN",
    "HOLDOUT_FORBIDDEN",
    "CONTROL_UNKNOWN",
    "CONTROL_PARAMETER_MISSING",
    "CONTROL_PARAMETER_EXTRA",
    "CONTROL_PARAMETER_TYPE_INVALID",
    "CONTROL_PARAMETER_VALUE_INVALID",
    "INTERNAL_INTEGRITY_FAILURE",
}
MISSION_PATHS = PRODUCTION_PATHS | {
    "contracts/DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json",
    "docs/DELTAGRID_RESEARCH_ADMISSION_CORE.md",
    "docs/README.md",
    "docs/documentation-status.json",
    "offchain/tests/test_research_admission_core.py",
    "offchain/tests/test_current_policy_docs.py",
    "offchain/tests/test_document_status_banners.py",
    "offchain/tests/test_documentation_status.py",
    "offchain/tests/test_human_cli_report_language.py",
    "offchain/tests/test_public_docstrings_operator_guidance.py",
    "offchain/tests/test_research_cockpit_v0_charter.py",
    "offchain/tests/test_research_evidence_summaries.py",
}


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def catalog_record(**updates) -> dict:
    record = {
        "schema_version": "1.0",
        "dataset_id": "synthetic-001",
        "artifact_id": "fixture-001",
        "content_sha256": "a" * 64,
        "data_class": "SYNTHETIC_FIXTURE",
        "split_identity": "SYNTHETIC_DEVELOPMENT",
        "artifact_path": "fixtures/synthetic.json",
        "allowed_authorization_stages": ["MISSION_94_SYNTHETIC_TEST"],
        "protected": False,
        "provenance_reference": "generated:test-fixture",
    }
    record.update(updates)
    record["metadata_sha256"] = canonical_hash(record)
    return record


def catalog(records=None, **updates) -> dict:
    value = {
        "schema_version": "1.0",
        "records": records if records is not None else [catalog_record()],
    }
    value.update(updates)
    value["catalog_hash_sha256"] = canonical_hash(value)
    return value


def resolver(tmp_path: Path, records=None) -> DatasetResolver:
    return DatasetResolver(catalog(records), tmp_path / "artifacts")


def request(**updates) -> dict:
    value = {
        "schema_version": "1.0",
        "request_id": "request-001",
        "controlling_contract_id": CONTRACT_ID,
        "controlling_contract_hash": CONTRACT_HASH,
        "repository_commit": BASE_COMMIT,
        "repository_clean": True,
        "budget_id": "budget-001",
        "declared_trial_number": 1,
        "dataset_id": "synthetic-001",
        "dataset_hash": "a" * 64,
        "data_class": "SYNTHETIC_FIXTURE",
        "split_identity": "SYNTHETIC_DEVELOPMENT",
        "authorization_stage": "MISSION_94_SYNTHETIC_TEST",
        "control_identifier": "NO_TRADE_CONTROL",
        "control_parameters": {},
        "initiated_by": "OPERATOR",
        "created_at": "2026-08-02T00:00:00Z",
    }
    value.update(updates)
    value["canonical_request_hash"] = canonical_hash(value)
    return value


def ledger(tmp_path: Path, total: int = 3) -> TrialLedger:
    value = TrialLedger(tmp_path / "trials.sqlite3")
    value.register_budget(
        budget_id="budget-001",
        controlling_contract_id=CONTRACT_ID,
        controlling_contract_hash=CONTRACT_HASH,
        experiment_family="SYNTHETIC_CONTROL_VALIDATION",
        total_trial_budget=total,
        created_at="2026-08-02T00:00:00Z",
    )
    return value


def service(tmp_path: Path, total: int = 3) -> ResearchAdmissionService:
    return ResearchAdmissionService(
        controlling_contract_id=CONTRACT_ID,
        controlling_contract_hash=CONTRACT_HASH,
        repository_commit=BASE_COMMIT,
        dataset_resolver=resolver(tmp_path),
        trial_ledger=ledger(tmp_path, total),
    )


def reserve(
    value: TrialLedger,
    *,
    trial_number: int = 1,
    request_hash: str = "b" * 64,
    timestamp: str = "2026-08-02T00:00:00Z",
):
    return value.reserve(
        budget_id="budget-001",
        declared_trial_number=trial_number,
        request_hash=request_hash,
        initiated_by="OPERATOR",
        reserved_at=timestamp,
        controlling_contract_id=CONTRACT_ID,
        controlling_contract_hash=CONTRACT_HASH,
    )


def assert_reason(expected: str, operation) -> None:
    with pytest.raises(AdmissionError) as caught:
        operation()
    assert caught.value.reason_token == expected


def test_contract_identity_and_canonical_hash() -> None:
    contract = load_contract()
    core = dict(contract)
    assert core.pop("contract_hash_sha256") == CONTRACT_HASH
    assert canonical_hash(core) == CONTRACT_HASH
    assert contract["contract_id"] == CONTRACT_ID
    assert contract["contract_version"] == 1
    assert contract["base_commit"] == BASE_COMMIT


def test_every_research_and_trading_authority_remains_false() -> None:
    state = load_contract()["authorization_state"]
    assert set(state) == FALSE_AUTHORITIES
    assert all(state[field] is False for field in FALSE_AUTHORITIES)


def test_research_request_parameters_are_detached_immutable_and_hash_stable() -> None:
    source = request(
        control_identifier="SEEDED_RANDOM_CONTROL",
        control_parameters={"seed": 7},
    )
    direct = ResearchAdmissionRequest(**source)
    factory = ResearchAdmissionRequest.from_mapping(source)
    source["control_parameters"]["seed"] = 8

    for value in (direct, factory):
        before = canonical_hash(value.as_dict())
        with pytest.raises(TypeError):
            value.control_parameters["seed"] = 9  # type: ignore[index]
        detached = value.as_dict()
        assert type(detached) is dict
        assert type(detached["control_parameters"]) is dict
        detached["control_parameters"]["seed"] = 10
        assert value.control_parameters["seed"] == 7
        assert canonical_hash(value.as_dict()) == before
        request_core = value.as_dict()
        supplied_hash = request_core.pop("canonical_request_hash")
        assert canonical_hash(request_core) == supplied_hash


def test_validated_control_parameters_are_detached_immutable_and_hash_stable() -> None:
    source = {"seed": 7}
    control_core = {
        "schema_version": "1.0",
        "control_identifier": "SEEDED_RANDOM_CONTROL",
        "control_parameters": source,
        "non_alpha": True,
        "execution_authorized": False,
    }
    direct = ValidatedControl(
        **control_core,
        canonical_control_hash=canonical_hash(control_core),
    )
    factory = ControlRegistry().validate("SEEDED_RANDOM_CONTROL", source)
    source["seed"] = 8

    for value in (direct, factory):
        before = value.canonical_control_hash
        with pytest.raises(TypeError):
            value.control_parameters["seed"] = 9  # type: ignore[index]
        detached = value.as_dict()
        assert type(detached) is dict
        assert type(detached["control_parameters"]) is dict
        detached["control_parameters"]["seed"] = 10
        assert value.control_parameters["seed"] == 7
        control_value = value.as_dict()
        supplied_hash = control_value.pop("canonical_control_hash")
        assert canonical_hash(control_value) == supplied_hash == before


def test_exact_production_package_inventory() -> None:
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "offchain/research/admission").iterdir()
        if path.is_file()
    }
    assert actual == PRODUCTION_PATHS


def test_dataset_catalog_canonical_identity(tmp_path: Path) -> None:
    valid = catalog()
    assert DatasetResolver(valid, tmp_path).catalog_hash == valid["catalog_hash_sha256"]
    invalid = dict(valid)
    invalid["catalog_hash_sha256"] = "0" * 64
    assert_reason(
        "INTERNAL_INTEGRITY_FAILURE", lambda: DatasetResolver(invalid, tmp_path)
    )


def test_content_sha256_accepts_exact_lowercase_hex_identity(tmp_path: Path) -> None:
    identity = "0123456789abcdef" * 4
    record = catalog_record(content_sha256=identity)
    value = DatasetResolver(catalog([record]), tmp_path)
    result = value.resolve(
        dataset_id=record["dataset_id"],
        requested_hash=identity,
        data_class="SYNTHETIC_FIXTURE",
        split_identity="SYNTHETIC_DEVELOPMENT",
        authorization_stage="MISSION_94_SYNTHETIC_TEST",
    )
    assert result.content_sha256 == identity


@pytest.mark.parametrize(
    "malformed_identity",
    [
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        "0x" + "a" * 62,
        "a" * 63 + " ",
    ],
)
def test_content_sha256_rejects_malformed_identity(
    tmp_path: Path, malformed_identity: str
) -> None:
    record = catalog_record(content_sha256=malformed_identity)
    assert_reason(
        "INTERNAL_INTEGRITY_FAILURE",
        lambda: DatasetResolver(catalog([record]), tmp_path),
    )


def test_duplicate_dataset_rejection(tmp_path: Path) -> None:
    record = catalog_record()
    assert_reason(
        "INTERNAL_INTEGRITY_FAILURE",
        lambda: DatasetResolver(catalog([record, record]), tmp_path),
    )


def test_unknown_dataset_rejection(tmp_path: Path) -> None:
    value = resolver(tmp_path)
    assert_reason(
        "DATASET_UNKNOWN",
        lambda: value.resolve(
            dataset_id="missing",
            requested_hash="a" * 64,
            data_class="SYNTHETIC_FIXTURE",
            split_identity="SYNTHETIC_DEVELOPMENT",
            authorization_stage="MISSION_94_SYNTHETIC_TEST",
        ),
    )


def test_dataset_hash_mismatch_rejection(tmp_path: Path) -> None:
    value = resolver(tmp_path)
    assert_reason(
        "DATASET_HASH_MISMATCH",
        lambda: value.resolve(
            dataset_id="synthetic-001",
            requested_hash="f" * 64,
            data_class="SYNTHETIC_FIXTURE",
            split_identity="SYNTHETIC_DEVELOPMENT",
            authorization_stage="MISSION_94_SYNTHETIC_TEST",
        ),
    )


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (catalog_record(protected=True), "PROTECTED_DATA_FORBIDDEN"),
        (
            catalog_record(
                data_class="REAL_MARKET_VALIDATION",
                split_identity="MARKET_VALIDATION",
            ),
            "VALIDATION_FORBIDDEN",
        ),
        (
            catalog_record(
                data_class="REAL_MARKET_HOLDOUT",
                split_identity="MARKET_HOLDOUT",
            ),
            "HOLDOUT_FORBIDDEN",
        ),
    ],
)
def test_protected_validation_and_holdout_rejection(
    tmp_path: Path, record: dict, expected: str
) -> None:
    value = resolver(tmp_path, [record])
    assert_reason(
        expected,
        lambda: value.resolve(
            dataset_id=record["dataset_id"],
            requested_hash=record["content_sha256"],
            data_class=record["data_class"],
            split_identity=record["split_identity"],
            authorization_stage="MISSION_94_SYNTHETIC_TEST",
        ),
    )


@pytest.mark.parametrize("unsafe_path", ["../secret.bin", "/absolute/secret.bin"])
def test_unsafe_dataset_path_rejection(
    tmp_path: Path, unsafe_path: str
) -> None:
    record = catalog_record(artifact_path=unsafe_path)
    value = resolver(tmp_path, [record])
    assert_reason(
        "DATASET_PATH_UNSAFE",
        lambda: value.resolve(
            dataset_id=record["dataset_id"],
            requested_hash=record["content_sha256"],
            data_class=record["data_class"],
            split_identity=record["split_identity"],
            authorization_stage="MISSION_94_SYNTHETIC_TEST",
        ),
    )


def test_authorization_stage_mismatch_rejection(tmp_path: Path) -> None:
    value = resolver(tmp_path)
    assert_reason(
        "AUTHORIZATION_STAGE_MISMATCH",
        lambda: value.resolve(
            dataset_id="synthetic-001",
            requested_hash="a" * 64,
            data_class="SYNTHETIC_FIXTURE",
            split_identity="SYNTHETIC_DEVELOPMENT",
            authorization_stage="OTHER_STAGE",
        ),
    )


def test_artifact_bytes_are_never_opened(tmp_path: Path, monkeypatch) -> None:
    value = resolver(tmp_path)

    def forbidden_open(*args, **kwargs):
        raise AssertionError("artifact bytes were opened")

    monkeypatch.setattr(Path, "open", forbidden_open)
    result = value.resolve(
        dataset_id="synthetic-001",
        requested_hash="a" * 64,
        data_class="SYNTHETIC_FIXTURE",
        split_identity="SYNTHETIC_DEVELOPMENT",
        authorization_stage="MISSION_94_SYNTHETIC_TEST",
    )
    assert result.reason_token == "DATASET_AUTHORIZED"


def test_exact_four_control_inventory_and_immutability() -> None:
    registry = ControlRegistry()
    assert tuple(registry.controls) == (
        "NO_TRADE_CONTROL",
        "BUY_AND_HOLD_CONTROL",
        "SEEDED_RANDOM_CONTROL",
        "SIMULATOR_STATE_MACHINE_CONTROL",
    )
    with pytest.raises(TypeError):
        registry.controls["NEW_CONTROL"] = {}  # type: ignore[index]
    assert not hasattr(registry, "register")


@pytest.mark.parametrize(
    ("identifier", "parameters", "expected"),
    [
        ("UNKNOWN", {}, "CONTROL_UNKNOWN"),
        ("SEEDED_RANDOM_CONTROL", {}, "CONTROL_PARAMETER_MISSING"),
        ("NO_TRADE_CONTROL", {"seed": 1}, "CONTROL_PARAMETER_EXTRA"),
        (
            "SEEDED_RANDOM_CONTROL",
            {"seed": True},
            "CONTROL_PARAMETER_TYPE_INVALID",
        ),
        (
            "SEEDED_RANDOM_CONTROL",
            {"seed": -1},
            "CONTROL_PARAMETER_VALUE_INVALID",
        ),
        (
            "SEEDED_RANDOM_CONTROL",
            {"seed": 9223372036854775808},
            "CONTROL_PARAMETER_VALUE_INVALID",
        ),
        (
            "SIMULATOR_STATE_MACHINE_CONTROL",
            {"scenario_id": "UNAUTHORIZED"},
            "CONTROL_PARAMETER_VALUE_INVALID",
        ),
    ],
)
def test_control_fail_closed_reasons(
    identifier: str, parameters: dict, expected: str
) -> None:
    assert_reason(expected, lambda: ControlRegistry().validate(identifier, parameters))


def test_control_validated_specification_hash() -> None:
    result = ControlRegistry().validate("SEEDED_RANDOM_CONTROL", {"seed": 0})
    core = result.as_dict()
    supplied = core.pop("canonical_control_hash")
    assert canonical_hash(core) == supplied
    assert result.non_alpha is True
    assert result.execution_authorized is False


def test_immutable_budget_registration(tmp_path: Path) -> None:
    value = ledger(tmp_path)
    same = value.register_budget(
        budget_id="budget-001",
        controlling_contract_id=CONTRACT_ID,
        controlling_contract_hash=CONTRACT_HASH,
        experiment_family="SYNTHETIC_CONTROL_VALIDATION",
        total_trial_budget=3,
        created_at="2026-08-02T00:00:00Z",
    )
    assert same.total_trial_budget == 3
    assert_reason(
        "BUDGET_DEFINITION_MISMATCH",
        lambda: value.register_budget(
            budget_id="budget-001",
            controlling_contract_id=CONTRACT_ID,
            controlling_contract_hash=CONTRACT_HASH,
            experiment_family="SYNTHETIC_CONTROL_VALIDATION",
            total_trial_budget=4,
            created_at="2026-08-02T00:00:00Z",
        ),
    )


def test_unique_trial_numbers_and_request_hashes(tmp_path: Path) -> None:
    value = ledger(tmp_path)
    reserve(value)
    assert_reason(
        "DECLARED_TRIAL_ALREADY_USED",
        lambda: reserve(value, trial_number=1, request_hash="c" * 64),
    )
    assert_reason(
        "REQUEST_ALREADY_RESERVED",
        lambda: reserve(value, trial_number=2, request_hash="b" * 64),
    )


def test_budget_exhaustion_and_all_reservations_count(tmp_path: Path) -> None:
    value = ledger(tmp_path, total=1)
    first = reserve(value)
    value.append_event(
        trial_id=first.trial_id,
        status_token="FAILED",
        reason_token="SYNTHETIC_FAILURE",
        event_timestamp="2026-08-02T00:00:01Z",
    )
    assert_reason(
        "TRIAL_BUDGET_EXHAUSTED",
        lambda: reserve(value, trial_number=2, request_hash="c" * 64),
    )
    assert value.reservation_count("budget-001") == 1


def test_append_only_database_guards_reject_updates_and_deletes(tmp_path: Path) -> None:
    value = ledger(tmp_path)
    trial = reserve(value)
    statements = [
        "UPDATE trial_budgets SET total_trial_budget = 9",
        "DELETE FROM trial_budgets",
        "UPDATE trial_reservations SET initiated_by = 'OPERATOR'",
        "DELETE FROM trial_reservations",
        "UPDATE trial_events SET reason_token = 'CHANGED'",
        "DELETE FROM trial_events",
    ]
    connection = sqlite3.connect(value.database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        for statement in statements:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)
            connection.rollback()
    finally:
        connection.close()
    assert value.event_statuses(trial.trial_id) == ("RESERVED",)


def test_allowed_status_transitions(tmp_path: Path) -> None:
    value = ledger(tmp_path)
    trial = reserve(value)
    value.append_event(
        trial_id=trial.trial_id,
        status_token="ADMITTED",
        reason_token="ADMISSION_GATES_PASSED",
        event_timestamp="2026-08-02T00:00:01Z",
    )
    value.append_event(
        trial_id=trial.trial_id,
        status_token="COMPLETED",
        reason_token="SYNTHETIC_COMPLETION",
        event_timestamp="2026-08-02T00:00:02Z",
    )
    assert value.event_statuses(trial.trial_id) == (
        "RESERVED",
        "ADMITTED",
        "COMPLETED",
    )


def test_terminal_status_cannot_reverse(tmp_path: Path) -> None:
    value = ledger(tmp_path)
    trial = reserve(value)
    value.append_event(
        trial_id=trial.trial_id,
        status_token="STOPPED",
        reason_token="CONTROL_UNKNOWN",
        event_timestamp="2026-08-02T00:00:01Z",
    )
    assert_reason(
        "INTERNAL_INTEGRITY_FAILURE",
        lambda: value.append_event(
            trial_id=trial.trial_id,
            status_token="ADMITTED",
            reason_token="INVALID_REVERSAL",
            event_timestamp="2026-08-02T00:00:02Z",
        ),
    )


def test_preflight_writes_nothing(tmp_path: Path) -> None:
    value = service(tmp_path)
    decision = value.preflight(request())
    assert decision.decision_token == "PRECHECK_PASS"
    assert decision.reason_token == "PRECHECK_GATES_PASSED"
    assert value._ledger.reservation_count() == 0


def test_admitted_request_reserves_one_trial(tmp_path: Path) -> None:
    value = service(tmp_path)
    decision = value.admit(request())
    assert decision.decision_token == "ADMITTED"
    assert decision.trial_id is not None
    assert value._ledger.reservation_count() == 1
    assert value._ledger.event_statuses(decision.trial_id) == ("RESERVED", "ADMITTED")


def test_post_reservation_stop_still_consumes_trial(tmp_path: Path) -> None:
    value = service(tmp_path)
    decision = value.admit(request(repository_clean=False))
    assert decision.decision_token == "STOPPED"
    assert decision.reason_token == "DIRTY_REPOSITORY"
    assert decision.trial_id is not None
    assert value._ledger.reservation_count() == 1
    assert value._ledger.event_statuses(decision.trial_id) == ("RESERVED", "STOPPED")


def test_pre_reservation_contract_stop_consumes_nothing(tmp_path: Path) -> None:
    value = service(tmp_path)
    decision = value.admit(request(controlling_contract_id="wrong-contract"))
    assert decision.reason_token == "CONTRACT_ID_MISMATCH"
    assert decision.trial_id is None
    assert value._ledger.reservation_count() == 0


def test_preflight_rejects_invalid_recorded_origin_without_reservation(
    tmp_path: Path,
) -> None:
    value = service(tmp_path)
    decision = value.preflight(request(initiated_by="AUTONOMOUS_AGENT"))
    assert decision.reason_token == "INITIATED_BY_INVALID"
    assert value._ledger.reservation_count() == 0


def test_two_concurrent_final_slot_reservations_allow_at_most_one(
    tmp_path: Path,
) -> None:
    setup = ledger(tmp_path, total=1)
    first = TrialLedger(setup.database_path)
    second = TrialLedger(setup.database_path)
    barrier = threading.Barrier(3)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(instance: TrialLedger, request_hash: str) -> None:
        barrier.wait()
        try:
            reserve(instance, request_hash=request_hash)
            outcome = "SUCCESS"
        except AdmissionError as error:
            outcome = error.reason_token
        with lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=attempt, args=(first, "1" * 64)),
        threading.Thread(target=attempt, args=(second, "2" * 64)),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert outcomes.count("SUCCESS") == 1
    assert setup.reservation_count("budget-001") == 1


@pytest.mark.parametrize("operation", ["preflight", "admit"])
def test_decision_canonical_hashes(tmp_path: Path, operation: str) -> None:
    value = service(tmp_path)
    decision = getattr(value, operation)(request())
    core = decision.as_dict()
    supplied = core.pop("canonical_decision_hash")
    assert canonical_hash(core) == supplied


def test_exact_machine_reason_tokens_are_locked() -> None:
    assert REQUIRED_REASONS <= set(load_contract()["reason_tokens"])


def test_no_strategy_simulation_pnl_exchange_network_or_training_imports() -> None:
    forbidden_roots = {
        "requests",
        "urllib",
        "http",
        "socket",
        "freqtrade",
        "ccxt",
        "torch",
        "tensorflow",
        "sklearn",
    }
    forbidden_fragments = (
        "backtest",
        "simulator",
        "strategy",
        "pnl",
        "exchange",
        "cost_engine",
        "risk_engine",
    )
    for relative in PRODUCTION_PATHS:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not {name.split(".")[0] for name in imports} & forbidden_roots
        assert not any(fragment in name.casefold() for name in imports for fragment in forbidden_fragments)


def test_no_dependency_changes_or_dashboard_code() -> None:
    changed = set(subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "7b1d7e035d006d5ec839486105b94e4a6b7d15bc.."
            "ac2440952d2b330344cbaef299c4378a7afd45af",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines())
    assert "offchain/requirements.txt" not in changed
    assert not any(path.endswith((".html", ".css", ".js", ".ts", ".tsx")) for path in changed)
    assert changed == MISSION_PATHS


def test_base_contracts_evidence_and_checksums_remain_unchanged() -> None:
    changed = MISSION_PATHS
    assert not any(path.startswith("docs/evidence/") for path in changed)
    assert not any("SHA256SUMS" in path for path in changed)
    assert not any(
        path.startswith("contracts/")
        and path != "contracts/DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json"
        for path in changed
    )


def test_registry_and_navigation_updates() -> None:
    registry = json.loads(
        (ROOT / "docs/documentation-status.json").read_text(encoding="utf-8")
    )
    by_path = {item["path"]: item for item in registry["documents"]}
    assert by_path[
        "contracts/DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json"
    ]["authority_level"] == "CURRENT_CONTROLLING_STAGE_CONTRACT"
    assert by_path["docs/DELTAGRID_RESEARCH_ADMISSION_CORE.md"][
        "authority_level"
    ] == "CURRENT_CONTROLLING_STAGE_EXPLANATION"
    docs_home = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    assert (
        "[Research Admission Core](DELTAGRID_RESEARCH_ADMISSION_CORE.md)"
        in docs_home
    )


def test_contract_and_manifest_hash_constants_are_not_recomputed_from_artifacts() -> None:
    assert hashlib.sha256(
        json.dumps(
            {
                key: value
                for key, value in load_contract().items()
                if key != "contract_hash_sha256"
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest() == CONTRACT_HASH
