from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace

import pytest

from offchain.research.admission import (
    AdmissionError,
    TrialLedger,
    TrialResultLink,
    canonical_hash,
    canonical_json,
)
from offchain.research.admission.trial_ledger import SCHEMA_SQL
import offchain.research.control_plane as public_api
from offchain.research.control_plane import (
    MISSION_AUTHORIZATION_STAGE,
    MISSION_BASE_COMMIT,
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    ControlPlaneError,
    ControlPlaneSnapshot,
    ReadOnlyTrialLedger,
    ResearchControlPlaneService,
    TrialProjection,
)
from offchain.research.control_plane.models import AUTHORITY, INCIDENT_CATEGORIES
from offchain.research.engine_service import load_linked_result


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "contracts" / "DELTAGRID_RESEARCH_CONTROL_PLANE_V1.json"
PACKAGE = ROOT / "offchain" / "research" / "control_plane"
PRODUCTION_PATHS = {
    "offchain/research/control_plane/__init__.py",
    "offchain/research/control_plane/models.py",
    "offchain/research/control_plane/readonly_ledger.py",
    "offchain/research/control_plane/service.py",
}
PUBLIC_EXPORTS = {
    "ControlPlaneError",
    "ControlPlaneSnapshot",
    "IncidentProjection",
    "MISSION_AUTHORIZATION_STAGE",
    "MISSION_BASE_COMMIT",
    "MISSION_CONTRACT_HASH",
    "MISSION_CONTRACT_ID",
    "ReadOnlyTrialLedger",
    "ResearchControlPlaneService",
    "ResultProjection",
    "SystemProjection",
    "TrialProjection",
}
IMPLEMENTATION_COMMIT = "1" * 40
AS_OF = "2026-08-03T12:00:00Z"
GOVERNANCE_CONTRACTS = (
    "DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json",
    "DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json",
    "DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE_V1.json",
    "DELTAGRID_RESEARCH_CONTROL_PLANE_V1.json",
)


def contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def make_ledger(tmp_path: Path) -> tuple[TrialLedger, Path, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "trials.sqlite3"
    ledger = TrialLedger(path)
    ledger.register_budget(
        budget_id="budget-1",
        controlling_contract_id="contract-1",
        controlling_contract_hash="a" * 64,
        experiment_family="READ_ONLY_TEST",
        total_trial_budget=8,
        created_at="2026-08-03T00:00:00Z",
    )
    reservation = ledger.reserve(
        budget_id="budget-1",
        declared_trial_number=1,
        request_hash="b" * 64,
        initiated_by="OPERATOR",
        reserved_at="2026-08-03T00:01:00Z",
        controlling_contract_id="contract-1",
        controlling_contract_hash="a" * 64,
    )
    return ledger, path, reservation.trial_id


def service_for(
    ledger: ReadOnlyTrialLedger, tmp_path: Path, *, result_root: Path | None = None
) -> ResearchControlPlaneService:
    selected = result_root or tmp_path / "results"
    selected.mkdir(exist_ok=True)
    return ResearchControlPlaneService(
        ledger=ledger,
        result_root=selected,
        repository_root=ROOT,
        expected_repository_commit=IMPLEMENTATION_COMMIT,
    )


def mission95_environment(tmp_path: Path):
    from offchain.tests.test_canonical_result_engine_service import environment

    return environment(tmp_path)


def copy_contract_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    contracts = repository / "contracts"
    contracts.mkdir(parents=True)
    for name in GOVERNANCE_CONTRACTS:
        shutil.copyfile(ROOT / "contracts" / name, contracts / name)
    return repository


def test_contract_identity_hash_precedence_and_exact_authority() -> None:
    value = contract()
    core = dict(value)
    supplied = core.pop("contract_hash_sha256")
    assert value["contract_id"] == MISSION_CONTRACT_ID
    assert value["contract_version"] == 1
    assert value["base_commit"] == MISSION_BASE_COMMIT
    assert value["authorization_stage"] == MISSION_AUTHORIZATION_STAGE
    assert value["preceding_contract_hash_sha256"] == (
        "d8fcd1169e638b648f8b5fccb389dfd090b016beb80e9e13d7f0a0af3210aa6a"
    )
    assert canonical_hash(core) == supplied == MISSION_CONTRACT_HASH
    assert set(value["implementation_authorization"].values()) == {True}
    assert set(value["authorization_state"].values()) == {False}
    assert dict(AUTHORITY) == {
        "read_only_ledger_access_authorized": True,
        "linked_result_loading_authorized": True,
        "deterministic_projection_authorized": True,
        **{
            key: False
            for key in (
                "ledger_write_authorized",
                "trial_admission_authorized",
                "control_execution_authorized",
                "strategy_research_authorized",
                "market_data_access_authorized",
                "validation_access_authorized",
                "holdout_access_authorized",
                "protected_data_access_authorized",
                "model_training_authorized",
                "exchange_access_authorized",
                "paper_trading_authorized",
                "live_trading_authorized",
                "capital_deployment_authorized",
                "autonomous_research_authorized",
                "autonomous_promotion_authorized",
                "autonomous_execution_authorized",
                "cockpit_ui_authorized",
            )
        },
    }


def test_exact_package_inventory_and_public_exports() -> None:
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in PACKAGE.iterdir()
        if path.is_file() and path.suffix == ".py"
    }
    assert actual == PRODUCTION_PATHS
    assert set(public_api.__all__) == PUBLIC_EXPORTS
    assert {
        name
        for name in dir(ReadOnlyTrialLedger)
        if not name.startswith("_")
    } == {
        "database_path",
        "get_budget",
        "get_reservation",
        "get_result_link",
        "latest_event",
        "list_budgets",
        "list_events",
        "list_reservations",
        "list_result_links",
        "sqlite_uri",
        "timeout",
    }


def test_production_imports_are_standard_library_or_existing_deltagrid() -> None:
    prohibited_roots = {
        "aiohttp",
        "ccxt",
        "dash",
        "flask",
        "keras",
        "matplotlib",
        "numpy",
        "pandas",
        "requests",
        "sklearn",
        "streamlit",
        "subprocess",
        "tensorflow",
        "torch",
    }
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            node.names[0].name.split(".")[0]
            if isinstance(node, ast.Import)
            else (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        }
        assert not imports & prohibited_roots


def test_production_sql_literals_are_read_only() -> None:
    prohibited = {
        "CREATE",
        "INSERT",
        "UPDATE",
        "DELETE",
        "REPLACE",
        "DROP",
        "ALTER",
        "VACUUM",
        "ATTACH",
    }
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        sql_literals = {
            node.value.strip().split(maxsplit=1)[0].upper()
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.strip()
        }
        assert not sql_literals & prohibited


def test_missing_ledger_rejected_without_creation(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(ControlPlaneError) as caught:
        ReadOnlyTrialLedger(path)
    assert caught.value.reason_token == "LEDGER_UNAVAILABLE"
    assert not path.exists()


def test_ledger_and_parent_symlinks_are_rejected(tmp_path: Path) -> None:
    _, path, _ = make_ledger(tmp_path)
    file_link = tmp_path / "ledger-link.sqlite3"
    file_link.symlink_to(path)
    with pytest.raises(ControlPlaneError) as caught:
        ReadOnlyTrialLedger(file_link)
    assert caught.value.reason_token == "LEDGER_PATH_UNSAFE"

    real_parent = tmp_path / "real"
    real_parent.mkdir()
    nested = real_parent / "nested.sqlite3"
    nested.write_bytes(path.read_bytes())
    parent_link = tmp_path / "linked-parent"
    parent_link.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ControlPlaneError) as caught:
        ReadOnlyTrialLedger(parent_link / nested.name)
    assert caught.value.reason_token == "LEDGER_PATH_UNSAFE"


def test_non_regular_ledgers_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ControlPlaneError):
        ReadOnlyTrialLedger(tmp_path)
    fifo = tmp_path / "ledger.pipe"
    os.mkfifo(fifo)
    with pytest.raises(ControlPlaneError):
        ReadOnlyTrialLedger(fifo)


def test_read_only_uri_pragmas_writes_and_database_bytes(tmp_path: Path) -> None:
    _, path, _ = make_ledger(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    ledger = ReadOnlyTrialLedger(path)
    assert ledger.sqlite_uri == f"file:{path.resolve()}?mode=ro"
    with ledger._connection() as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        for statement in (
            "INSERT INTO trial_budgets VALUES ('x','x','x','x',1,'x','x')",
            "UPDATE trial_budgets SET budget_id = 'x'",
            "DELETE FROM trial_budgets",
        ):
            with pytest.raises(sqlite3.DatabaseError):
                connection.execute(statement)
    ledger.list_budgets()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert "immutable=1" not in inspect.getsource(ReadOnlyTrialLedger)


def test_ledger_and_service_public_identities_are_read_only(tmp_path: Path) -> None:
    _, path, _ = make_ledger(tmp_path)
    ledger = ReadOnlyTrialLedger(path, timeout=3.5)
    service = service_for(ledger, tmp_path)
    for target, name, value in (
        (ledger, "database_path", tmp_path / "other.sqlite3"),
        (ledger, "timeout", 10.0),
        (ledger, "sqlite_uri", "file:other?mode=ro"),
        (ledger, "_database_path", tmp_path / "other.sqlite3"),
        (service, "ledger", object()),
        (service, "result_root", tmp_path),
        (service, "repository_root", tmp_path),
        (service, "expected_repository_commit", "2" * 40),
        (service, "contract_verification", {}),
        (service, "_expected_repository_commit", "2" * 40),
    ):
        with pytest.raises(AttributeError):
            setattr(target, name, value)
    assert ledger.database_path == path.resolve()
    assert ledger.timeout == 3.5
    assert service.ledger is ledger
    with pytest.raises(TypeError):
        service.contract_verification["mission_93_verified"] = False


def test_schema_missing_table_column_and_type_are_rejected(tmp_path: Path) -> None:
    missing_table = tmp_path / "missing-table.sqlite3"
    sqlite3.connect(missing_table).close()
    with pytest.raises(ControlPlaneError) as caught:
        ReadOnlyTrialLedger(missing_table)
    assert caught.value.reason_token == "LEDGER_SCHEMA_INCOMPATIBLE"

    _, valid, _ = make_ledger(tmp_path / "valid")
    for name, statement in (
        (
            "missing-column",
            "CREATE TABLE trial_budgets (budget_id TEXT);",
        ),
        (
            "bad-type",
            "CREATE TABLE trial_budgets ("
            "budget_id BLOB, controlling_contract_id TEXT, "
            "controlling_contract_hash TEXT, experiment_family TEXT, "
            "total_trial_budget INTEGER, created_at TEXT, "
            "canonical_budget_hash TEXT);",
        ),
    ):
        path = tmp_path / f"{name}.sqlite3"
        connection = sqlite3.connect(path)
        connection.executescript(statement)
        for table in ("trial_reservations", "trial_events", "trial_result_links"):
            schema = sqlite3.connect(valid).execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()[0]
            connection.execute(schema)
        connection.close()
        with pytest.raises(ControlPlaneError) as caught:
            ReadOnlyTrialLedger(path)
        assert caught.value.reason_token == "LEDGER_SCHEMA_INCOMPATIBLE"


@pytest.mark.parametrize(
    ("name", "schema"),
    [
        (
            "missing-unique",
            SCHEMA_SQL.replace(
                "canonical_budget_hash TEXT NOT NULL UNIQUE",
                "canonical_budget_hash TEXT NOT NULL",
            ),
        ),
        (
            "missing-foreign-key",
            SCHEMA_SQL.replace(
                "budget_id TEXT NOT NULL REFERENCES trial_budgets(budget_id)",
                "budget_id TEXT NOT NULL",
                1,
            ),
        ),
    ],
)
def test_schema_requires_unique_and_foreign_key_identity(
    tmp_path: Path, name: str, schema: str
) -> None:
    path = tmp_path / f"{name}.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(schema)
    connection.close()
    with pytest.raises(ControlPlaneError) as caught:
        ReadOnlyTrialLedger(path)
    assert caught.value.reason_token == "LEDGER_SCHEMA_INCOMPATIBLE"


@pytest.mark.parametrize(
    "trigger",
    ["trial_events_no_update", "trial_reservations_budget_guard"],
)
def test_schema_requires_immutability_and_budget_guard_triggers(
    tmp_path: Path, trigger: str
) -> None:
    path = tmp_path / f"{trigger}.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA_SQL)
    connection.execute(f'DROP TRIGGER "{trigger}"')
    connection.close()
    with pytest.raises(ControlPlaneError) as caught:
        ReadOnlyTrialLedger(path)
    assert caught.value.reason_token == "LEDGER_SCHEMA_INCOMPATIBLE"


def test_foreign_key_violation_fails_captured_snapshot_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "foreign-key-violation.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA_SQL)
    core = {
        "budget_id": "missing-budget",
        "declared_trial_number": 1,
        "request_hash": "a" * 64,
        "initiated_by": "OPERATOR",
        "reserved_at": "2026-08-03T00:00:00Z",
    }
    trial_id = f"trial-{canonical_hash(core)[:32]}"
    connection.execute(
        "INSERT INTO trial_reservations VALUES (?, ?, ?, ?, ?, ?)",
        (trial_id, *core.values()),
    )
    connection.commit()
    connection.close()
    ledger = ReadOnlyTrialLedger(path)
    with pytest.raises(ControlPlaneError) as caught:
        ledger._snapshot()
    assert caught.value.reason_token == "LEDGER_ROW_INTEGRITY_FAILURE"


def test_all_ledger_identities_are_verified(tmp_path: Path) -> None:
    _, path, trial_id = make_ledger(tmp_path)
    readonly = ReadOnlyTrialLedger(path)
    budget = readonly.get_budget("budget-1")
    budget_core = budget.as_dict()
    budget_hash = budget_core.pop("canonical_budget_hash")
    assert canonical_hash(budget_core) == budget_hash
    reservation = readonly.get_reservation(trial_id)
    reservation_core = reservation.as_dict()
    reservation_core.pop("trial_id")
    assert trial_id == f"trial-{canonical_hash(reservation_core)[:32]}"
    event = readonly.latest_event(trial_id)
    event_core = event.as_dict()
    event_hash = event_core.pop("canonical_event_hash")
    event_core.pop("event_id")
    assert canonical_hash(event_core) == event_hash
    assert event.event_id == f"event-{event_hash[:32]}"


def test_timestamp_forms_and_parsed_reservation_ordering(tmp_path: Path) -> None:
    path = tmp_path / "timestamps.sqlite3"
    ledger = TrialLedger(path)
    ledger.register_budget(
        budget_id="budget-time",
        controlling_contract_id="contract-time",
        controlling_contract_hash="a" * 64,
        experiment_family="TIMESTAMP_TEST",
        total_trial_budget=3,
        created_at="2026-08-03T00:00:00.123456Z",
    )
    exact = ledger.reserve(
        budget_id="budget-time",
        declared_trial_number=1,
        request_hash="b" * 64,
        initiated_by="OPERATOR",
        reserved_at="2026-08-03T00:00:00Z",
        controlling_contract_id="contract-time",
        controlling_contract_hash="a" * 64,
    )
    fractional = ledger.reserve(
        budget_id="budget-time",
        declared_trial_number=2,
        request_hash="c" * 64,
        initiated_by="OPERATOR",
        reserved_at="2026-08-03T00:00:00.1Z",
        controlling_contract_id="contract-time",
        controlling_contract_hash="a" * 64,
    )
    readonly = ReadOnlyTrialLedger(path)
    assert [item.trial_id for item in readonly.list_reservations()] == [
        exact.trial_id,
        fractional.trial_id,
    ]
    service = service_for(readonly, tmp_path)
    for as_of in (
        "2026-08-03T12:00:00Z",
        "2026-08-03T12:00:00.1Z",
        "2026-08-03T12:00:00.123456Z",
    ):
        snapshot = service.build_snapshot(as_of=as_of)
        assert [item.trial_id for item in snapshot.trials] == [
            exact.trial_id,
            fractional.trial_id,
        ]


@pytest.mark.parametrize(
    "invalid",
    [
        "2026-02-30T00:00:00Z",
        "2026-08-03T00:00:00+00:00",
        "2026-08-03T00:00:00z",
        "2026-08-03 00:00:00Z",
        "2026-08-03T00:00:00.1234567Z",
    ],
)
def test_invalid_persisted_timestamps_become_row_incidents(
    tmp_path: Path, invalid: str
) -> None:
    path = tmp_path / "invalid-timestamp.sqlite3"
    ledger = TrialLedger(path)
    ledger.register_budget(
        budget_id="budget-invalid-time",
        controlling_contract_id="contract-time",
        controlling_contract_hash="a" * 64,
        experiment_family="TIMESTAMP_TEST",
        total_trial_budget=1,
        created_at=invalid,
    )
    snapshot = service_for(ReadOnlyTrialLedger(path), tmp_path).build_snapshot(
        as_of=AS_OF
    )
    assert "LEDGER_ROW_INTEGRITY_FAILURE" in {
        item.category for item in snapshot.incidents
    }


def test_parsed_timestamp_detects_backward_lifecycle_hidden_by_lexical_order(
    tmp_path: Path,
) -> None:
    path = tmp_path / "backward-time.sqlite3"
    ledger = TrialLedger(path)
    ledger.register_budget(
        budget_id="budget-time",
        controlling_contract_id="contract-time",
        controlling_contract_hash="a" * 64,
        experiment_family="TIMESTAMP_TEST",
        total_trial_budget=1,
        created_at="2026-08-03T00:00:00Z",
    )
    reservation = ledger.reserve(
        budget_id="budget-time",
        declared_trial_number=1,
        request_hash="b" * 64,
        initiated_by="OPERATOR",
        reserved_at="2026-08-03T00:00:00.1Z",
        controlling_contract_id="contract-time",
        controlling_contract_hash="a" * 64,
    )
    ledger.append_event(
        trial_id=reservation.trial_id,
        status_token="ADMITTED",
        reason_token="ADMISSION_GATES_PASSED",
        event_timestamp="2026-08-03T00:00:00Z",
    )
    snapshot = service_for(ReadOnlyTrialLedger(path), tmp_path).build_snapshot(
        as_of=AS_OF
    )
    assert "INVALID_LIFECYCLE" in {
        item.category for item in snapshot.incidents
    }


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("ADMITTED", "ADMISSION_GATES_PASSED"),
        ("FAILED", "TEST_FAILURE"),
        ("STOPPED", "TEST_STOP"),
        ("REJECTED", "TEST_REJECTION"),
        ("SUPERSEDED", "TEST_SUPERSEDED"),
    ],
)
def test_chronological_lifecycle_projections(
    tmp_path: Path, status: str, reason: str
) -> None:
    ledger, path, trial_id = make_ledger(tmp_path)
    if status == "ADMITTED":
        ledger.append_event(
            trial_id=trial_id,
            status_token=status,
            reason_token=reason,
            event_timestamp="2026-08-03T00:02:00Z",
        )
    else:
        if status in {"FAILED", "SUPERSEDED"}:
            ledger.append_event(
                trial_id=trial_id,
                status_token="ADMITTED",
                reason_token="ADMISSION_GATES_PASSED",
                event_timestamp="2026-08-03T00:02:00Z",
            )
        ledger.append_event(
            trial_id=trial_id,
            status_token=status,
            reason_token=reason,
            event_timestamp="2026-08-03T00:03:00Z",
        )
    snapshot = service_for(ReadOnlyTrialLedger(path), tmp_path).build_snapshot(
        as_of=AS_OF
    )
    assert snapshot.trials[0].latest_status_token == status
    assert snapshot.system.lifecycle_counts[status] == 1
    assert snapshot.trials[0].result_verification_token == "NOT_LINKED"


def test_reserved_projection_and_deterministic_ordering(tmp_path: Path) -> None:
    ledger, path, first = make_ledger(tmp_path)
    second = ledger.reserve(
        budget_id="budget-1",
        declared_trial_number=2,
        request_hash="c" * 64,
        initiated_by="OPERATOR",
        reserved_at="2026-08-03T00:00:30Z",
        controlling_contract_id="contract-1",
        controlling_contract_hash="a" * 64,
    )
    snapshot = service_for(ReadOnlyTrialLedger(path), tmp_path).build_snapshot(
        as_of=AS_OF
    )
    assert [item.trial_id for item in snapshot.trials] == [second.trial_id, first]
    assert snapshot.system.lifecycle_counts["RESERVED"] == 2


def test_generic_completed_without_link_is_an_incident(tmp_path: Path) -> None:
    ledger, path, trial_id = make_ledger(tmp_path)
    ledger.append_event(
        trial_id=trial_id,
        status_token="ADMITTED",
        reason_token="ADMISSION_GATES_PASSED",
        event_timestamp="2026-08-03T00:02:00Z",
    )
    ledger.append_event(
        trial_id=trial_id,
        status_token="COMPLETED",
        reason_token="GENERIC_COMPLETION",
        event_timestamp="2026-08-03T00:03:00Z",
    )
    snapshot = service_for(ReadOnlyTrialLedger(path), tmp_path).build_snapshot(
        as_of=AS_OF
    )
    assert {item.category for item in snapshot.incidents} == {
        "COMPLETED_WITHOUT_RESULT_LINK"
    }
    assert snapshot.system.health_token == "DEGRADED"


def test_result_link_without_completed_event_and_missing_artifact(
    tmp_path: Path,
) -> None:
    request, decision, engine, ledger, _, _ = mission95_environment(tmp_path)
    linked = engine.execute(request, decision)
    result_path = engine.result_root / decision.trial_id / "result.json"
    result_path.unlink()
    readonly = ReadOnlyTrialLedger(ledger.database_path)
    snapshot = service_for(
        readonly, tmp_path, result_root=engine.result_root
    ).build_snapshot(as_of=AS_OF)
    assert {item.category for item in snapshot.incidents} == {
        "RESULT_ARTIFACT_MISSING"
    }
    assert snapshot.trials[0].has_result_link is True
    assert linked.result_bundle_id

    other = tmp_path / "unmatched"
    _, other_path, other_trial = make_ledger(other)
    candidate = TrialResultLink.create(
        trial_id=other_trial,
        result_bundle_id="result-bundle-" + "c" * 32,
        result_bundle_hash="d" * 64,
        result_bundle_path=f"{other_trial}/result.json",
        linked_at="2026-08-03T00:02:00Z",
    )
    connection = sqlite3.connect(other_path)
    connection.execute(
        "INSERT INTO trial_result_links VALUES (?, ?, ?, ?, ?, ?)",
        tuple(candidate.as_dict().values()),
    )
    connection.commit()
    connection.close()
    unmatched = service_for(ReadOnlyTrialLedger(other_path), other).build_snapshot(
        as_of=AS_OF
    )
    assert "RESULT_LINK_WITHOUT_COMPLETED_EVENT" in {
        item.category for item in unmatched.incidents
    }


def test_valid_completed_replay_loader_compatibility_and_metric_copy(
    tmp_path: Path,
) -> None:
    request, decision, engine, ledger, _, fixture_path = mission95_environment(
        tmp_path
    )
    original = engine.execute(request, decision)
    fixture_path.unlink()
    before = hashlib.sha256(ledger.database_path.read_bytes()).hexdigest()
    readonly = ReadOnlyTrialLedger(ledger.database_path)
    replay = load_linked_result(
        result_root=engine.result_root,
        trial_ledger=readonly,
        trial_id=decision.trial_id,
    )
    snapshot = service_for(
        readonly, tmp_path, result_root=engine.result_root
    ).build_snapshot(as_of=AS_OF)
    result = snapshot.results[0]
    authoritative = original.result_bundle.as_dict()
    trial_metrics = authoritative["metrics"]["trial"]
    assert replay.canonical_result_hash == original.canonical_result_hash
    assert result.gross_result == trial_metrics["gross_result_units"]
    assert result.net_result == trial_metrics["net_result_units"]
    assert result.turnover == trial_metrics["turnover_units"]
    assert result.trade_count == trial_metrics["trade_count"]
    assert result.benchmark == authoritative["metrics"]["benchmark"]
    assert hashlib.sha256(ledger.database_path.read_bytes()).hexdigest() == before
    assert snapshot.system.verified_linked_result_count == 1
    assert snapshot.system.health_token == "HEALTHY"


def test_complete_snapshot_uses_one_captured_ledger_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, decision, engine, ledger, _, _ = mission95_environment(tmp_path)
    engine.execute(request, decision)
    readonly = ReadOnlyTrialLedger(ledger.database_path)
    original_snapshot = readonly._snapshot
    captures = 0

    def forbidden_connection(*args, **kwargs):
        raise AssertionError("ledger was reopened after snapshot capture")

    def capture_once():
        nonlocal captures
        captures += 1
        captured = original_snapshot()
        monkeypatch.setattr(readonly, "_connection", forbidden_connection)
        return captured

    monkeypatch.setattr(readonly, "_snapshot", capture_once)
    snapshot = service_for(
        readonly, tmp_path, result_root=engine.result_root
    ).build_snapshot(as_of=AS_OF)
    assert captures == 1
    assert snapshot.system.total_reservation_count == 1
    assert snapshot.system.total_event_count == 3
    assert snapshot.system.total_result_link_count == 1
    assert snapshot.trials[0].latest_status_token == "COMPLETED"
    assert snapshot.results[0].trial_id == decision.trial_id
    for operation in (
        lambda: readonly.get_reservation(decision.trial_id),
        lambda: readonly.latest_event(decision.trial_id),
        lambda: readonly.get_result_link(decision.trial_id),
        lambda: readonly._connection(),
    ):
        with pytest.raises(AssertionError):
            operation()


def test_live_database_change_after_capture_does_not_change_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, decision, engine, ledger, _, _ = mission95_environment(tmp_path)
    engine.execute(request, decision)
    readonly = ReadOnlyTrialLedger(ledger.database_path)
    original_snapshot = readonly._snapshot
    added_trial_id = None

    def capture_then_mutate():
        nonlocal added_trial_id
        captured = original_snapshot()
        added = ledger.reserve(
            budget_id=request["budget_id"],
            declared_trial_number=2,
            request_hash="e" * 64,
            initiated_by="OPERATOR",
            reserved_at="2026-08-03T00:20:00Z",
            controlling_contract_id=request["controlling_contract_id"],
            controlling_contract_hash=request["controlling_contract_hash"],
        )
        added_trial_id = added.trial_id
        return captured

    monkeypatch.setattr(readonly, "_snapshot", capture_then_mutate)
    snapshot = service_for(
        readonly, tmp_path, result_root=engine.result_root
    ).build_snapshot(as_of=AS_OF)
    assert snapshot.system.total_reservation_count == 1
    assert snapshot.system.total_event_count == 3
    assert [item.trial_id for item in snapshot.trials] == [decision.trial_id]
    assert [item.trial_id for item in snapshot.results] == [decision.trial_id]
    assert ledger.get_reservation(added_trial_id).trial_id == added_trial_id


def test_result_order_follows_parsed_trial_chronology_not_bundle_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, decision, source_engine, _, _, _ = mission95_environment(
        tmp_path / "source"
    )
    template = source_engine.execute(request, decision).result_bundle.as_dict()

    target = tmp_path / "target"
    target.mkdir()
    path = target / "trials.sqlite3"
    ledger = TrialLedger(path)
    ledger.register_budget(
        budget_id="budget-order",
        controlling_contract_id="contract-order",
        controlling_contract_hash="a" * 64,
        experiment_family="ORDER_TEST",
        total_trial_budget=2,
        created_at="2026-08-03T00:00:00Z",
    )
    reservations = []
    for number, request_hash, reserved_at in (
        (1, "b" * 64, "2026-08-03T00:00:00Z"),
        (2, "c" * 64, "2026-08-03T00:00:00.1Z"),
    ):
        reservation = ledger.reserve(
            budget_id="budget-order",
            declared_trial_number=number,
            request_hash=request_hash,
            initiated_by="OPERATOR",
            reserved_at=reserved_at,
            controlling_contract_id="contract-order",
            controlling_contract_hash="a" * 64,
        )
        ledger.append_event(
            trial_id=reservation.trial_id,
            status_token="ADMITTED",
            reason_token="ADMISSION_GATES_PASSED",
            event_timestamp="2026-08-03T00:01:00Z",
        )
        reservations.append(reservation)
    result_ids = (
        "result-bundle-" + "f" * 32,
        "result-bundle-" + "0" * 32,
    )
    result_hashes = ("d" * 64, "e" * 64)
    result_root = target / "results"
    for index, reservation in enumerate(reservations):
        linked_at = f"2026-08-03T00:02:0{index}Z"
        ledger.append_event(
            trial_id=reservation.trial_id,
            status_token="COMPLETED",
            reason_token="SYNTHETIC_CONTROL_COMPLETED",
            event_timestamp=linked_at,
        )
        link = TrialResultLink.create(
            trial_id=reservation.trial_id,
            result_bundle_id=result_ids[index],
            result_bundle_hash=result_hashes[index],
            result_bundle_path=f"{reservation.trial_id}/result.json",
            linked_at=linked_at,
        )
        connection = sqlite3.connect(path)
        connection.execute(
            "INSERT INTO trial_result_links VALUES (?, ?, ?, ?, ?, ?)",
            tuple(link.as_dict().values()),
        )
        connection.commit()
        connection.close()
        artifact_directory = result_root / reservation.trial_id
        artifact_directory.mkdir(parents=True)
        (artifact_directory / "result.json").write_text("{}", encoding="utf-8")
        (artifact_directory / "event-ledger.json").write_text(
            "{}", encoding="utf-8"
        )

    by_trial = {
        reservation.trial_id: (result_ids[index], result_hashes[index])
        for index, reservation in enumerate(reservations)
    }

    def captured_loader(*, result_root, trial_ledger, trial_id):
        result_id, result_hash = by_trial[trial_id]
        return SimpleNamespace(
            result_bundle=SimpleNamespace(as_dict=lambda: template),
            trial_id=trial_id,
            result_bundle_id=result_id,
            canonical_result_hash=result_hash,
            trial_status_token="COMPLETED",
            trial_reason_token="SYNTHETIC_CONTROL_COMPLETED",
        )

    monkeypatch.setattr(
        "offchain.research.control_plane.service.load_linked_result",
        captured_loader,
    )
    snapshot = service_for(
        ReadOnlyTrialLedger(path), target, result_root=result_root
    ).build_snapshot(as_of=AS_OF)
    assert [item.trial_id for item in snapshot.results] == [
        item.trial_id for item in snapshot.trials
    ]
    assert [item.result_bundle_id for item in snapshot.results] == list(result_ids)
    assert list(result_ids) != sorted(result_ids)


def test_tampered_result_is_incident_and_other_trial_survives(tmp_path: Path) -> None:
    request, decision, engine, ledger, _, _ = mission95_environment(tmp_path)
    engine.execute(request, decision)
    result_path = engine.result_root / decision.trial_id / "result.json"
    value = json.loads(result_path.read_text(encoding="utf-8"))
    value["metrics"]["trial"]["net_result_units"] += 1
    result_path.write_text(canonical_json(value), encoding="utf-8")
    snapshot = service_for(
        ReadOnlyTrialLedger(ledger.database_path),
        tmp_path,
        result_root=engine.result_root,
    ).build_snapshot(as_of=AS_OF)
    assert snapshot.results == ()
    assert {item.category for item in snapshot.incidents} & {
        "RESULT_ARTIFACT_TAMPERED",
        "RESULT_VERIFICATION_FAILED",
    }
    assert snapshot.trials[0].trial_id == decision.trial_id
    assert snapshot.system.health_token == "INTEGRITY_FAILURE"


def test_corrupt_event_row_becomes_incident_without_hiding_trial(
    tmp_path: Path,
) -> None:
    _, path, trial_id = make_ledger(tmp_path)
    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO trial_events VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "event-" + "0" * 32,
            trial_id,
            2,
            "ADMITTED",
            "ADMISSION_GATES_PASSED",
            "2026-08-03T00:02:00Z",
            "0" * 64,
        ),
    )
    connection.commit()
    connection.close()
    snapshot = service_for(ReadOnlyTrialLedger(path), tmp_path).build_snapshot(
        as_of=AS_OF
    )
    assert len(snapshot.trials) == 1
    assert snapshot.trials[0].trial_id == trial_id
    assert "LEDGER_ROW_INTEGRITY_FAILURE" in {
        item.category for item in snapshot.incidents
    }
    assert snapshot.system.health_token == "INTEGRITY_FAILURE"


def test_explicit_as_of_snapshot_hash_id_and_deep_detachment(
    tmp_path: Path,
) -> None:
    _, path, _ = make_ledger(tmp_path)
    service = service_for(ReadOnlyTrialLedger(path), tmp_path)
    first = service.build_snapshot(as_of=AS_OF)
    second = service.build_snapshot(as_of=AS_OF)
    assert first.as_dict() == second.as_dict()
    assert canonical_json(first.as_dict()) == canonical_json(second.as_dict())
    core = first.as_dict()
    supplied = core.pop("canonical_snapshot_hash")
    assert canonical_hash(core) == supplied
    assert first.snapshot_id.startswith("snapshot-")
    detached = first.as_dict()
    detached["system"]["authority_projection"]["ledger_write_authorized"] = True
    detached["trials"].clear()
    fresh = first.as_dict()
    assert fresh["system"]["authority_projection"]["ledger_write_authorized"] is False
    assert fresh["trials"]
    with pytest.raises(TypeError):
        first.system.authority_projection["ledger_write_authorized"] = True
    with pytest.raises(FrozenInstanceError):
        first.snapshot_id = "changed"
    with pytest.raises(ControlPlaneError):
        service.build_snapshot(as_of="2026-08-03T12:00:00+00:00")


def test_caller_model_lists_are_detached_and_frozen(tmp_path: Path) -> None:
    _, path, _ = make_ledger(tmp_path)
    snapshot = service_for(ReadOnlyTrialLedger(path), tmp_path).build_snapshot(
        as_of=AS_OF
    )
    trial_value = snapshot.trials[0].as_dict()
    original_incident_ids = ["incident-example"]
    trial_value["incident_ids"] = original_incident_ids
    trial = TrialProjection(**trial_value)
    original_incident_ids.append("incident-later")
    assert trial.incident_ids == ("incident-example",)
    with pytest.raises(TypeError):
        TrialProjection(**{**trial_value, "incident_ids": [1]})

    original_trials = [trial]
    original_results = list(snapshot.results)
    original_incidents = list(snapshot.incidents)
    rebuilt = ControlPlaneSnapshot(
        schema_version=snapshot.schema_version,
        snapshot_id=snapshot.snapshot_id,
        snapshot_version=snapshot.snapshot_version,
        system=snapshot.system,
        trials=original_trials,
        results=original_results,
        incidents=original_incidents,
        canonical_snapshot_hash=snapshot.canonical_snapshot_hash,
    )
    original_trials.clear()
    original_results.clear()
    original_incidents.clear()
    assert rebuilt.trials == (trial,)
    assert isinstance(rebuilt.results, tuple)
    assert isinstance(rebuilt.incidents, tuple)


def test_repository_contract_verification_and_path_identity(tmp_path: Path) -> None:
    _, path, _ = make_ledger(tmp_path)
    repository = copy_contract_repository(tmp_path)
    result_root = tmp_path / "results"
    result_root.mkdir()
    service = ResearchControlPlaneService(
        ledger=ReadOnlyTrialLedger(path),
        result_root=result_root,
        repository_root=repository,
        expected_repository_commit=IMPLEMENTATION_COMMIT,
    )
    expected_verification = {
        "mission_93_verified": True,
        "mission_94_verified": True,
        "mission_95_verified": True,
        "mission_96a_verified": True,
        "predecessor_chain_verified": True,
    }
    assert dict(service.contract_verification) == expected_verification
    snapshot = service.build_snapshot(as_of=AS_OF)
    assert snapshot.system.repository_root_path_identity == (
        f"sha256:{canonical_hash({'absolute_path': str(repository.resolve())})}"
    )
    assert dict(snapshot.system.contract_verification) == expected_verification
    with pytest.raises(TypeError):
        snapshot.system.contract_verification["mission_93_verified"] = False


def test_repository_root_rejects_symlinks_missing_and_non_directory(
    tmp_path: Path,
) -> None:
    _, path, _ = make_ledger(tmp_path)
    ledger = ReadOnlyTrialLedger(path)
    result_root = tmp_path / "results"
    result_root.mkdir()
    repository = copy_contract_repository(tmp_path / "real")
    repository_link = tmp_path / "repository-link"
    repository_link.symlink_to(repository, target_is_directory=True)
    parent_link = tmp_path / "parent-link"
    parent_link.symlink_to(repository.parent, target_is_directory=True)
    non_directory = tmp_path / "not-directory"
    non_directory.write_text("not a repository", encoding="utf-8")
    for candidate in (
        repository_link,
        parent_link / repository.name,
        tmp_path / "missing-repository",
        non_directory,
    ):
        with pytest.raises(ControlPlaneError):
            ResearchControlPlaneService(
                ledger=ledger,
                result_root=result_root,
                repository_root=candidate,
                expected_repository_commit=IMPLEMENTATION_COMMIT,
            )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "bom",
        "duplicate-name",
        "nonfinite",
        "non-object",
        "wrong-id",
        "wrong-hash",
        "predecessor",
    ],
)
def test_repository_contract_integrity_failures(
    tmp_path: Path, mutation: str
) -> None:
    _, path, _ = make_ledger(tmp_path)
    repository = copy_contract_repository(tmp_path)
    target = (
        repository
        / "contracts"
        / "DELTAGRID_RESEARCH_CONTROL_PLANE_V1.json"
    )
    raw = target.read_bytes()
    if mutation == "missing":
        target.unlink()
    elif mutation == "bom":
        target.write_bytes(b"\xef\xbb\xbf" + raw)
    elif mutation == "duplicate-name":
        target.write_bytes(raw.replace(b"{", b'{"contract_id":"duplicate",', 1))
    elif mutation == "nonfinite":
        target.write_bytes(raw.replace(b"{", b'{"nonfinite":NaN,', 1))
    elif mutation == "non-object":
        target.write_bytes(b"[]")
    else:
        value = json.loads(raw)
        if mutation == "wrong-id":
            value["contract_id"] = "wrong"
        elif mutation == "wrong-hash":
            value["contract_hash_sha256"] = "0" * 64
        else:
            value["preceding_contract_hash_sha256"] = "0" * 64
        target.write_text(json.dumps(value), encoding="utf-8")
    result_root = tmp_path / "results"
    result_root.mkdir()
    with pytest.raises(ControlPlaneError) as caught:
        ResearchControlPlaneService(
            ledger=ReadOnlyTrialLedger(path),
            result_root=result_root,
            repository_root=repository,
            expected_repository_commit=IMPLEMENTATION_COMMIT,
        )
    assert caught.value.reason_token == "REPOSITORY_CONTRACT_INTEGRITY_FAILURE"


def test_incident_inventory_snapshot_schema_and_authority_projection(
    tmp_path: Path,
) -> None:
    _, path, _ = make_ledger(tmp_path)
    snapshot = service_for(ReadOnlyTrialLedger(path), tmp_path).build_snapshot(
        as_of=AS_OF
    )
    assert set(snapshot.as_dict()) == {
        "schema_version",
        "snapshot_id",
        "snapshot_version",
        "system",
        "trials",
        "results",
        "incidents",
        "canonical_snapshot_hash",
    }
    assert INCIDENT_CATEGORIES == set(contract()["incident_categories"])
    assert snapshot.system.authority_projection == AUTHORITY


def test_no_dependency_ui_or_prohibited_capability_changes() -> None:
    changed = {
        line
        for line in os.popen(
            f"git -C {ROOT} diff --name-only {MISSION_BASE_COMMIT}"
        ).read().splitlines()
    }
    assert not changed & {
        "offchain/requirements.txt",
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "package-lock.json",
    }
    assert not any(
        path.startswith(("app/", "pages/", "ui/", "offchain/ui/"))
        for path in changed
    )
    production = "\n".join(
        path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py")
    ).casefold()
    for capability in (
        "ccxt",
        "streamlit",
        "tensorflow",
        "torch",
        "requests",
        "subprocess",
    ):
        assert capability not in production
