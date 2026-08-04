from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import threading

import pytest

from offchain.orchestration import (
    MISSION_AUTHORIZATION_STAGE,
    MISSION_BASE_COMMIT,
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    RESEARCH_OBSERVATION_REFRESH_V1,
    OrchestrationError,
    TickOutcome,
    WorkflowLedger,
    WorkflowOrchestrator,
    WorkflowStatus,
)
import offchain.orchestration as public_api
import offchain.orchestration.actions as actions_module
import offchain.orchestration.ledger as ledger_module
import offchain.orchestration.service as service_module
from offchain.orchestration.strict_json import publish_canonical
from offchain.research.admission import canonical_hash, canonical_json
from offchain.tests.test_research_control_plane import make_ledger


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR_V1.json"
PACKAGE = ROOT / "offchain" / "orchestration"
PRODUCTION = {
    "__init__.py", "__main__.py", "models.py", "strict_json.py",
    "definitions.py", "ledger.py", "actions.py", "service.py",
}
PUBLIC = {
    "OrchestrationError", "WorkflowLedger", "WorkflowOrchestrator",
    "WorkflowDefinition", "WorkflowRunSnapshot", "WorkflowStatus",
    "TickOutcome", "MISSION_CONTRACT_ID", "MISSION_CONTRACT_HASH",
    "MISSION_BASE_COMMIT", "MISSION_AUTHORIZATION_STAGE",
    "RESEARCH_OBSERVATION_REFRESH_V1",
}
IMPLEMENTATION_COMMIT = "1" * 40
AS_OF = "2026-08-04T10:00:00Z"


def _value() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _environment(tmp_path: Path) -> tuple[WorkflowLedger, WorkflowOrchestrator, Path, Path]:
    source, source_path, _ = make_ledger(tmp_path / "source")
    del source
    results = tmp_path / "results"
    results.mkdir()
    parent = tmp_path / "orchestration"
    parent.mkdir()
    ledger = WorkflowLedger.initialize(
        database_path=parent / "workflow.sqlite3",
        output_root=parent / "artifacts",
        governance_repository_root=ROOT,
        created_at=AS_OF,
    )
    return ledger, WorkflowOrchestrator(ledger), source_path, results


def _create(
    service: WorkflowOrchestrator,
    source: Path,
    results: Path,
    *,
    run_key: str = "observation-1",
):
    return service.create_run(
        run_key=run_key,
        research_ledger_path=source,
        result_root=results,
        expected_repository_commit=IMPLEMENTATION_COMMIT,
        observation_as_of=AS_OF,
        requested_at=AS_OF,
        requested_by="LOCAL_OPERATOR",
    )


def _private_run(
    ledger: WorkflowLedger, run_id: str
) -> tuple[dict, list[dict], list[dict], dict | None]:
    with ledger._connection() as connection:
        return ledger._run_data(connection, run_id)


def _claim_action(
    ledger: WorkflowLedger,
    service: WorkflowOrchestrator,
    worker: str,
    now: str,
):
    claimed = service._claim_one(worker, now)
    assert claimed is not None
    run, receipts, claim = claimed
    result = actions_module._execute(
        step_id=claim["step_id"],
        output_root=ledger.output_root,
        governance_root=ledger.governance_repository_root,
        run=run,
        receipts=receipts,
        idempotency_key=service._idempotency_key(
            run, claim["step_id"], claim["action_input_hash"]
        ),
    )
    return run, receipts, claim, result


def test_contract_authority_package_and_public_boundary() -> None:
    value = _value()
    core = dict(value)
    supplied = core.pop("contract_hash_sha256")
    assert canonical_hash(core) == supplied == MISSION_CONTRACT_HASH
    assert value["contract_id"] == MISSION_CONTRACT_ID
    assert value["base_commit"] == MISSION_BASE_COMMIT
    assert value["authorization_stage"] == MISSION_AUTHORIZATION_STAGE
    assert value["preceding_contract_hash_sha256"] == (
        "13846c63a6fcd07b2a4603aadd388960e74282de486bddf39907a09aa053c8d3"
    )
    assert value["functional_dependency_hash_sha256"] == (
        "c1e0c8c55db90fe8a81d3afe2d243537c703dbee6a945596f4b37c5ee13e70a9"
    )
    assert all(value["implementation_authorization"].values())
    assert not any(value["authorization_state"].values())
    assert {path.name for path in PACKAGE.glob("*.py")} == PRODUCTION
    assert set(public_api.__all__) == PUBLIC


def test_no_prohibited_capabilities() -> None:
    definition = RESEARCH_OBSERVATION_REFRESH_V1
    assert [step.step_id for step in definition.steps] == [
        "CAPTURE_CONTROL_PLANE_SNAPSHOT",
        "VERIFY_CONTROL_PLANE_SNAPSHOT",
        "PUBLISH_OBSERVATION_MANIFEST",
    ]
    assert [step.action_id for step in definition.steps] == [
        "CAPTURE_RESEARCH_CONTROL_PLANE_SNAPSHOT_V1",
        "VERIFY_RESEARCH_CONTROL_PLANE_SNAPSHOT_V1",
        "PUBLISH_RESEARCH_OBSERVATION_MANIFEST_V1",
    ]
    assert canonical_hash(definition.identity_core()) == (
        definition.canonical_workflow_definition_hash
    )
    assert definition.canonical_workflow_definition_hash == (
        _value()["workflow_definition"]["canonical_workflow_definition_hash"]
    )
    prohibited_imports = {"subprocess", "importlib", "requests", "socket"}
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            node.names[0].name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
        } | {
            (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert not imports & prohibited_imports
    combined = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py"))
    assert "scripts.mission_control" not in combined
    assert "scripts.mission_pack_runner" not in combined


def test_sqlite_delete_extra_and_integer_busy_timeout(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(OrchestrationError):
        WorkflowLedger(missing)
    assert not missing.exists()
    ledger, _, _, _ = _environment(tmp_path)
    assert ledger.output_root == (tmp_path / "orchestration" / "artifacts").resolve()
    assert ledger.governance_repository_root == ROOT
    with ledger._connection() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 3
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    for index, invalid in enumerate((True, 99, 30001, 5000.0)):
        parent = tmp_path / f"invalid-{index}"
        parent.mkdir()
        with pytest.raises(OrchestrationError) as caught:
            WorkflowLedger.initialize(
                database_path=parent / "workflow.sqlite3",
                output_root=parent / "artifacts",
                governance_repository_root=ROOT,
                created_at=AS_OF,
                busy_timeout_ms=invalid,
            )
        assert caught.value.reason_token == "WORKFLOW_INPUT_INVALID"
        assert not (parent / "workflow.sqlite3").exists()
        assert not (parent / "artifacts").exists()


def test_database_schema_indexes_triggers_foreign_keys_and_binding(
    tmp_path: Path,
) -> None:
    ledger, _, _, _ = _environment(tmp_path)
    assert ledger.output_root == (tmp_path / "orchestration" / "artifacts").resolve()
    assert ledger.governance_repository_root == ROOT
    with ledger._connection() as connection:
        assert {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )} == {
            "orchestration_metadata", "workflow_runs", "workflow_events",
            "workflow_claims", "workflow_receipts",
        }
        triggers = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )}
        assert triggers == {
            "orchestration_metadata_no_update", "orchestration_metadata_no_delete",
            "workflow_runs_no_update", "workflow_runs_no_delete",
            "workflow_events_no_update", "workflow_events_no_delete",
            "workflow_receipts_no_update", "workflow_receipts_no_delete",
        }
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        unique_indexes = {
            tuple(row[2] for row in connection.execute(
                f'PRAGMA index_info("{index[1]}")'
            ))
            for table in ("workflow_runs", "workflow_receipts")
            for index in connection.execute(f'PRAGMA index_list("{table}")')
            if index[2]
        }
        assert ("run_key",) in unique_indexes
        assert ("run_id", "step_id") in unique_indexes
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE orchestration_metadata SET created_at='x'")


def test_strict_input_and_deterministic_run_identity(tmp_path: Path) -> None:
    _, service, source, results = _environment(tmp_path)
    first = _create(service, source, results)
    second = _create(service, source, results)
    assert first.as_dict() == second.as_dict()
    assert first.event_count == 1
    with pytest.raises(OrchestrationError) as caught:
        service.create_run(
            run_key="observation-1",
            research_ledger_path=source,
            result_root=results,
            expected_repository_commit=IMPLEMENTATION_COMMIT,
            observation_as_of=AS_OF,
            requested_at="2026-08-04T10:00:01Z",
            requested_by="LOCAL_OPERATOR",
        )
    assert caught.value.reason_token == "RUN_KEY_CONFLICT"


def test_public_models_are_immutable_and_detached(tmp_path: Path) -> None:
    _, service, source, results = _environment(tmp_path)
    first = _create(service, source, results)
    detached = first.as_dict()
    detached["successful_step_ids"].append("BAD")
    assert first.successful_step_ids == ()
    with pytest.raises(FrozenInstanceError):
        first.run_id = "changed"
    for bad in (True, 0, 10001):
        with pytest.raises(OrchestrationError):
            service.run_until_idle("worker", lambda: AS_OF, bad)


def test_end_to_end_capture_verification_manifest_and_read_only_source(tmp_path: Path) -> None:
    ledger, service, source, results = _environment(tmp_path)
    before = source.read_bytes()
    created = _create(service, source, results)
    outcomes = [
        service.tick("worker-1", f"2026-08-04T10:00:0{index}Z")
        for index in range(1, 4)
    ]
    assert [item.outcome for item in outcomes] == [TickOutcome.STEP_SUCCEEDED] * 3
    final = outcomes[-1].run
    assert final is not None and final.status == WorkflowStatus.COMPLETED
    assert len(final.receipt_identities) == len(final.artifact_identities) == 3
    assert source.read_bytes() == before
    for identity in final.artifact_identities:
        path = ledger.output_root / identity["artifact_relative_path"]
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == identity["artifact_byte_hash"]
        assert "verified_at" not in json.loads(raw)
    manifest = json.loads(
        (
            ledger.output_root
            / final.artifact_identities[-1]["artifact_relative_path"]
        ).read_bytes()
    )
    assert manifest["authority_declaration"]["observation_only"] is True
    assert not any(
        value
        for key, value in manifest["authority_declaration"].items()
        if key != "observation_only"
    )
    assert manifest["warnings_by_trial"] == []
    assert service.tick("worker-1", "2026-08-04T10:00:04Z").outcome == TickOutcome.IDLE


def test_cancellation_retry_and_expired_claim_recovery(tmp_path: Path, monkeypatch) -> None:
    _, service, source, results = _environment(tmp_path)
    first = _create(service, source, results, run_key="cancel-before")
    cancelled = service.cancel_run(first.run_id, AS_OF, "operator stop")
    assert cancelled.status == WorkflowStatus.CANCELLED
    assert not cancelled.successful_step_ids

    retry_run = _create(service, source, results, run_key="retry")
    import offchain.orchestration.service as service_module

    def unavailable(**_: object) -> object:
        raise OrchestrationError("SNAPSHOT_TEMPORARILY_UNAVAILABLE")

    monkeypatch.setattr(service_module, "_execute", unavailable)
    retry = service.tick("worker-r", "2026-08-04T10:00:01Z")
    assert retry.outcome == TickOutcome.STEP_RETRY_SCHEDULED
    assert retry.run is not None
    assert retry.run.next_runnable_at == "2026-08-04T10:00:06Z"

    expiry_run = _create(service, source, results, run_key="expiry")
    claimed = service._claim_one("worker-e", "2026-08-04T10:00:01Z")
    assert claimed is not None and claimed[0]["run_id"] == expiry_run.run_id
    recovered = service.recover_expired_claims("2026-08-04T10:01:01Z")
    assert len(recovered) == 1
    assert recovered[0].status == WorkflowStatus.WAITING_RETRY
    assert recovered[0].next_attempt_number == 2


def test_each_operation_uses_and_closes_its_own_connection(
    tmp_path: Path, monkeypatch
) -> None:
    ledger, service, source, results = _environment(tmp_path)
    original_connect = ledger_module.sqlite3.connect
    opened: list[sqlite3.Connection] = []
    closed: list[sqlite3.Connection] = []

    class TrackingConnection(sqlite3.Connection):
        def close(self) -> None:
            closed.append(self)
            super().close()

    def tracking_connect(*args, **kwargs):
        kwargs["factory"] = TrackingConnection
        connection = original_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(ledger_module.sqlite3, "connect", tracking_connect)
    created = _create(service, source, results)
    service.get_run(created.run_id)
    service.list_runs()
    with pytest.raises(OrchestrationError):
        service.get_run("run-does-not-exist")
    assert len(opened) == 4
    assert len({id(item) for item in opened}) == len(opened)
    assert {id(item) for item in opened} == {id(item) for item in closed}


def test_busy_writer_returns_retryable_reason_without_partial_mutation(
    tmp_path: Path,
) -> None:
    ledger, _, source, results = _environment(tmp_path)
    service = WorkflowOrchestrator(
        WorkflowLedger(ledger.database_path, busy_timeout_ms=100)
    )
    created = _create(service, source, results)
    writer = sqlite3.connect(ledger.database_path, isolation_level=None)
    writer.execute("BEGIN IMMEDIATE")
    try:
        before = writer.execute(
            "SELECT COUNT(*) FROM workflow_events WHERE run_id=?",
            (created.run_id,),
        ).fetchone()[0]
        with pytest.raises(OrchestrationError) as caught:
            service.tick("busy-worker", "2026-08-04T10:00:01Z")
        assert caught.value.reason_token == "ORCHESTRATION_DATABASE_BUSY"
        after = writer.execute(
            "SELECT COUNT(*) FROM workflow_events WHERE run_id=?",
            (created.run_id,),
        ).fetchone()[0]
        assert after == before == 1
    finally:
        writer.execute("ROLLBACK")
        writer.close()


def test_two_workers_accept_at_most_one_claim(tmp_path: Path) -> None:
    ledger, service, source, results = _environment(tmp_path)
    created = _create(service, source, results)
    barrier = threading.Barrier(2)

    def claim(worker: str):
        barrier.wait()
        try:
            return service._claim_one(worker, "2026-08-04T10:00:01Z")
        except OrchestrationError as error:
            assert error.reason_token == "ORCHESTRATION_DATABASE_BUSY"
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ("worker-a", "worker-b")))
    accepted = [item for item in claims if item is not None]
    assert len(accepted) == 1
    assert accepted[0][0]["run_id"] == created.run_id
    with ledger._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM workflow_claims WHERE run_id=?",
            (created.run_id,),
        ).fetchone()[0] == 1


def test_fencing_epoch_increases_and_stale_token_fails(tmp_path: Path) -> None:
    _, service, source, results = _environment(tmp_path)
    _create(service, source, results)
    first = service._claim_one("worker-a", "2026-08-04T10:00:01Z")
    assert first is not None
    first_claim = first[2]
    service.recover_expired_claims("2026-08-04T10:01:01Z")
    second = service._claim_one("worker-b", "2026-08-04T10:01:06Z")
    assert second is not None
    second_claim = second[2]
    assert second_claim["fencing_epoch"] > first_claim["fencing_epoch"]
    with pytest.raises(OrchestrationError) as caught:
        service._verify_fencing(
            second_claim, first_claim, now="2026-08-04T10:01:07Z"
        )
    assert caught.value.reason_token == "STALE_FENCING_TOKEN"


def test_public_status_redacts_fencing_material(
    tmp_path: Path, capsys
) -> None:
    from offchain.orchestration.__main__ import main

    ledger, service, source, results = _environment(tmp_path)
    created = _create(service, source, results)
    private = service._claim_one("worker-private", "2026-08-04T10:00:01Z")
    assert private is not None
    snapshot = service.get_run(created.run_id)
    assert set(snapshot.active_claim or {}) == {
        "step_id", "attempt_number", "fencing_epoch", "worker_id",
        "claimed_at", "lease_expires_at",
    }
    serialized = canonical_json(snapshot.as_dict())
    representation = repr(snapshot)
    for secret in ("fencing_token", "canonical_claim_hash", "idempotency_key"):
        assert secret not in serialized
        assert secret not in representation
    assert main([
        "status", "--database", str(ledger.database_path),
        "--run-id", created.run_id,
    ]) == 0
    output = capsys.readouterr()
    assert not output.err
    assert "fencing_token" not in output.out
    assert "canonical_claim_hash" not in output.out
    assert "idempotency_key" not in output.out


def test_expired_claim_recovery_consumes_attempt(tmp_path: Path) -> None:
    _, service, source, results = _environment(tmp_path)
    created = _create(service, source, results)
    assert service._claim_one("worker", "2026-08-04T10:00:01Z") is not None
    recovered = service.recover_expired_claims("2026-08-04T10:01:01Z")
    assert len(recovered) == 1
    snapshot = recovered[0]
    assert snapshot.run_id == created.run_id
    assert snapshot.status == WorkflowStatus.WAITING_RETRY
    assert snapshot.next_attempt_number == 2
    assert snapshot.next_runnable_at == "2026-08-04T10:01:06Z"
    assert snapshot.last_event["event_type"] == "STEP_RETRY_SCHEDULED"


def test_retry_schedule_is_five_then_thirty_then_terminal(
    tmp_path: Path, monkeypatch
) -> None:
    _, service, source, results = _environment(tmp_path)
    _create(service, source, results)

    def unavailable(**_: object) -> object:
        raise OrchestrationError("SNAPSHOT_TEMPORARILY_UNAVAILABLE")

    monkeypatch.setattr(service_module, "_execute", unavailable)
    first = service.tick("worker", "2026-08-04T10:00:01Z")
    second = service.tick("worker", "2026-08-04T10:00:06Z")
    third = service.tick("worker", "2026-08-04T10:00:36Z")
    assert first.outcome == second.outcome == TickOutcome.STEP_RETRY_SCHEDULED
    assert first.run.next_runnable_at == "2026-08-04T10:00:06Z"
    assert second.run.next_runnable_at == "2026-08-04T10:00:36Z"
    assert third.outcome == TickOutcome.STEP_TERMINALLY_FAILED
    assert third.run.status == WorkflowStatus.FAILED
    assert third.run.retry_count == 2


def test_unknown_exception_is_not_retried(tmp_path: Path, monkeypatch) -> None:
    _, service, source, results = _environment(tmp_path)
    _create(service, source, results)

    def unexpected(**_: object) -> object:
        raise RuntimeError("private implementation detail")

    monkeypatch.setattr(service_module, "_execute", unexpected)
    result = service.tick("worker", "2026-08-04T10:00:01Z")
    assert result.outcome == TickOutcome.STEP_TERMINALLY_FAILED
    assert result.run.status == WorkflowStatus.FAILED
    assert result.run.retry_count == 0
    assert result.run.terminal_reason_token == "INTERNAL_INTEGRITY_FAILURE"


def test_cancel_before_claim_and_during_active_claim(tmp_path: Path) -> None:
    _, service, source, results = _environment(tmp_path)
    before = _create(service, source, results, run_key="cancel-before")
    cancelled = service.cancel_run(before.run_id, AS_OF, "stop")
    assert cancelled.status == WorkflowStatus.CANCELLED
    assert cancelled.receipt_identities == ()

    active = _create(service, source, results, run_key="cancel-active")
    claimed = service._claim_one("worker", "2026-08-04T10:00:01Z")
    assert claimed is not None and claimed[0]["run_id"] == active.run_id
    pending = service.cancel_run(
        active.run_id, "2026-08-04T10:00:02Z", "stop after claim"
    )
    assert pending.status == WorkflowStatus.RUNNING
    outcome, final = service._finalize_failure(
        active.run_id,
        claimed[2],
        "SNAPSHOT_TEMPORARILY_UNAVAILABLE",
        "2026-08-04T10:00:02Z",
    )
    assert outcome == TickOutcome.RUN_CANCELLED
    assert final.status == WorkflowStatus.CANCELLED
    assert final.retry_count == 0


def test_tick_and_recovery_order_are_deterministic(tmp_path: Path) -> None:
    ledger, service, source, results = _environment(tmp_path)

    def create_at(run_key: str, requested_at: str):
        return service.create_run(
            run_key=run_key,
            research_ledger_path=source,
            result_root=results,
            expected_repository_commit=IMPLEMENTATION_COMMIT,
            observation_as_of=AS_OF,
            requested_at=requested_at,
            requested_by="LOCAL_OPERATOR",
        )

    late = create_at("inserted-first", "2026-08-04T10:00:02Z")
    early = create_at("inserted-second", "2026-08-04T10:00:01Z")
    assert [item.run_id for item in service.list_runs()] == [
        early.run_id, late.run_id
    ]
    first = service._claim_one("worker-a", "2026-08-04T10:00:03Z")
    second = service._claim_one("worker-b", "2026-08-04T10:00:03Z")
    assert first is not None and first[0]["run_id"] == early.run_id
    assert second is not None and second[0]["run_id"] == late.run_id
    recovered = service.recover_expired_claims("2026-08-04T10:01:03Z")
    assert [item.run_id for item in recovered] == [early.run_id, late.run_id]
    with ledger._connection() as connection:
        rows = connection.execute(
            "SELECT run_id,event_type FROM workflow_events "
            "WHERE event_type='STEP_LEASE_EXPIRED' ORDER BY event_id"
        ).fetchall()
        assert {row["run_id"] for row in rows} == {early.run_id, late.run_id}


def test_clock_regression_fails_closed(tmp_path: Path) -> None:
    def setup(name: str):
        _, service, source, results = _environment(tmp_path / name)
        created = _create(service, source, results)
        return service, created

    service, _ = setup("claim")
    with pytest.raises(OrchestrationError) as claim_error:
        service._claim_one("worker", "2026-08-04T09:59:59Z")
    assert claim_error.value.reason_token == "CLOCK_REGRESSION"

    service, created = setup("finalize")
    claimed = service._claim_one("worker", "2026-08-04T10:00:01Z")
    assert claimed is not None
    with pytest.raises(OrchestrationError) as finalization_error:
        service._finalize_failure(
            created.run_id, claimed[2], "SNAPSHOT_TEMPORARILY_UNAVAILABLE", AS_OF
        )
    assert finalization_error.value.reason_token == "CLOCK_REGRESSION"

    service, _ = setup("recovery")
    assert service._claim_one("worker", "2026-08-04T10:00:01Z") is not None
    with pytest.raises(OrchestrationError) as recovery_error:
        service.recover_expired_claims(AS_OF)
    assert recovery_error.value.reason_token == "CLOCK_REGRESSION"

    service, created = setup("cancel")
    with pytest.raises(OrchestrationError) as cancellation_error:
        service.cancel_run(created.run_id, "2026-08-04T09:59:59Z", "stop")
    assert cancellation_error.value.reason_token == "CLOCK_REGRESSION"

    service, _ = setup("provider")
    values = iter(("2026-08-04T10:00:01Z", AS_OF))
    with pytest.raises(OrchestrationError) as provider_error:
        service.run_until_idle("worker", lambda: next(values), 2)
    assert provider_error.value.reason_token == "CLOCK_REGRESSION"


def test_no_clobber_artifact_conflict(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    first = publish_canonical(path, {"value": 1}, max_bytes=1024)
    with pytest.raises(OrchestrationError) as caught:
        publish_canonical(path, {"value": 2}, max_bytes=1024)
    assert caught.value.reason_token == "ARTIFACT_CONFLICT"
    assert path.read_bytes() == first


def test_crash_after_artifact_publication_is_adopted_once(
    tmp_path: Path, monkeypatch
) -> None:
    ledger, service, source, results = _environment(tmp_path)
    created = _create(service, source, results)
    run, _, claim, action_result = _claim_action(
        ledger, service, "worker-a", "2026-08-04T10:00:01Z"
    )
    artifact = ledger.output_root / action_result.artifact_relative_path
    initial_bytes = artifact.read_bytes()
    _, events, receipts, _ = _private_run(ledger, created.run_id)
    assert artifact.is_file()
    assert receipts == []
    assert len(events) == 2

    service.recover_expired_claims("2026-08-04T10:01:01Z")

    class MustNotReopenSource:
        def __init__(self, *_: object, **__: object) -> None:
            raise AssertionError("capture side effect reran")

    monkeypatch.setattr(actions_module, "ReadOnlyTrialLedger", MustNotReopenSource)
    accepted = service.tick("worker-b", "2026-08-04T10:01:06Z")
    assert accepted.outcome == TickOutcome.STEP_SUCCEEDED
    private_run, private_events, private_receipts, _ = _private_run(
        ledger, created.run_id
    )
    assert len(private_receipts) == 1
    assert private_receipts[0]["completed_at"] == "2026-08-04T10:01:06Z"
    assert sum(
        event["event_type"] == "STEP_SUCCEEDED" for event in private_events
    ) == 1
    assert artifact.read_bytes() == initial_bytes
    idempotency = service._idempotency_key(
        private_run,
        claim["step_id"],
        claim["action_input_hash"],
    )
    replay = actions_module._capture(
        output_root=ledger.output_root,
        governance_root=ledger.governance_repository_root,
        run=private_run,
        idempotency_key=idempotency,
    )
    assert replay.artifact_id == action_result.artifact_id
    assert replay.raw == initial_bytes
    _, after_events, after_receipts, _ = _private_run(ledger, created.run_id)
    assert len(after_events) == len(private_events)
    assert len(after_receipts) == len(private_receipts)


def test_step_finalization_is_transactional(tmp_path: Path) -> None:
    ledger, service, source, results = _environment(tmp_path)
    created = _create(service, source, results)
    _, _, claim, result = _claim_action(
        ledger, service, "worker", "2026-08-04T10:00:01Z"
    )
    connection = sqlite3.connect(ledger.database_path)
    connection.execute(
        "CREATE TRIGGER reject_step_success BEFORE INSERT ON workflow_events "
        "WHEN NEW.event_type='STEP_SUCCEEDED' "
        "BEGIN SELECT RAISE(ABORT, 'injected'); END"
    )
    connection.commit()
    connection.close()
    with pytest.raises(sqlite3.IntegrityError):
        service._finalize_success(
            created.run_id, claim, result, "2026-08-04T10:00:02Z"
        )
    connection = sqlite3.connect(ledger.database_path)
    assert connection.execute("SELECT COUNT(*) FROM workflow_receipts").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM workflow_claims").fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM workflow_events WHERE event_type='STEP_SUCCEEDED'"
    ).fetchone()[0] == 0
    connection.close()


def test_step_three_success_and_terminal_event_are_transactional(
    tmp_path: Path,
) -> None:
    ledger, service, source, results = _environment(tmp_path)
    created = _create(service, source, results)
    assert service.tick("worker", "2026-08-04T10:00:01Z").outcome == TickOutcome.STEP_SUCCEEDED
    assert service.tick("worker", "2026-08-04T10:00:02Z").outcome == TickOutcome.STEP_SUCCEEDED
    _, _, claim, result = _claim_action(
        ledger, service, "worker", "2026-08-04T10:00:03Z"
    )
    connection = sqlite3.connect(ledger.database_path)
    connection.execute(
        "CREATE TRIGGER reject_run_completed BEFORE INSERT ON workflow_events "
        "WHEN NEW.event_type='RUN_COMPLETED' "
        "BEGIN SELECT RAISE(ABORT, 'injected'); END"
    )
    connection.commit()
    connection.close()
    with pytest.raises(sqlite3.IntegrityError):
        service._finalize_success(
            created.run_id, claim, result, "2026-08-04T10:00:04Z"
        )
    connection = sqlite3.connect(ledger.database_path)
    assert connection.execute("SELECT COUNT(*) FROM workflow_receipts").fetchone()[0] == 2
    assert connection.execute("SELECT COUNT(*) FROM workflow_claims").fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM workflow_events "
        "WHERE event_type='STEP_SUCCEEDED'"
    ).fetchone()[0] == 2
    assert connection.execute(
        "SELECT COUNT(*) FROM workflow_events WHERE event_type='RUN_COMPLETED'"
    ).fetchone()[0] == 0
    connection.close()


def test_capture_uses_only_mission96a_public_boundary() -> None:
    tree = ast.parse((PACKAGE / "actions.py").read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    text = (PACKAGE / "actions.py").read_text(encoding="utf-8")
    assert "offchain.research.control_plane" in imported_modules
    assert not any(
        module.startswith("offchain.research.engine_service")
        for module in imported_modules
    )
    assert {"ReadOnlyTrialLedger", "ResearchControlPlaneService"} <= names
    assert "TrialLedger" not in names
    assert "CanonicalResultEngineService" not in text
    assert "execute_control" not in text


def test_snapshot_identity_and_projection_hashes(tmp_path: Path) -> None:
    ledger, service, source, results = _environment(tmp_path)
    created = _create(service, source, results)
    first = service.tick("worker", "2026-08-04T10:00:01Z")
    identity = first.run.artifact_identities[0]
    raw = (
        ledger.output_root / identity["artifact_relative_path"]
    ).read_bytes()
    snapshot = json.loads(raw)
    for collection, hash_field in (
        ("trials", "canonical_trial_projection_hash"),
        ("results", "canonical_result_projection_hash"),
        ("incidents", "canonical_incident_hash"),
    ):
        for item in snapshot[collection]:
            core = dict(item)
            supplied = core.pop(hash_field)
            assert canonical_hash(core) == supplied
    system = dict(snapshot["system"])
    assert system.pop("snapshot_id") == snapshot["snapshot_id"]
    identity_core = {
        "schema_version": snapshot["schema_version"],
        "snapshot_version": snapshot["snapshot_version"],
        "system": system,
        "trials": snapshot["trials"],
        "results": snapshot["results"],
        "incidents": snapshot["incidents"],
    }
    assert snapshot["snapshot_id"] == f"snapshot-{canonical_hash(identity_core)[:32]}"
    snapshot_core = dict(snapshot)
    supplied_hash = snapshot_core.pop("canonical_snapshot_hash")
    assert canonical_hash(snapshot_core) == supplied_hash
    assert hashlib.sha256(raw).hexdigest() == identity["artifact_byte_hash"]
    assert created.run_id == first.run.run_id


@pytest.mark.parametrize(
    "field",
    [
        "research_ledger_path",
        "result_root",
        "governance_root",
        "observation_as_of",
        "expected_repository_commit",
    ],
)
def test_snapshot_is_bound_to_all_run_paths_and_as_of(
    tmp_path: Path, field: str
) -> None:
    ledger, service, source, results = _environment(tmp_path)
    _create(service, source, results)
    first = service.tick("worker", "2026-08-04T10:00:01Z")
    raw = (
        ledger.output_root
        / first.run.artifact_identities[0]["artifact_relative_path"]
    ).read_bytes()
    arguments = {
        "research_ledger_path": str(source.resolve()),
        "result_root": str(results.resolve()),
        "governance_root": ROOT,
        "observation_as_of": AS_OF,
        "expected_repository_commit": IMPLEMENTATION_COMMIT,
    }
    replacements = {
        "research_ledger_path": str(tmp_path / "different.sqlite3"),
        "result_root": str(tmp_path / "different-results"),
        "governance_root": tmp_path / "different-governance",
        "observation_as_of": "2026-08-04T10:00:01Z",
        "expected_repository_commit": "2" * 40,
    }
    actions_module._verify_snapshot(raw, **arguments)
    arguments[field] = replacements[field]
    with pytest.raises(OrchestrationError) as caught:
        actions_module._verify_snapshot(raw, **arguments)
    assert caught.value.reason_token in {
        "SNAPSHOT_INTEGRITY_FAILURE",
        "REPOSITORY_CONTRACT_INTEGRITY_FAILURE",
    }
    assert len(first.run.receipt_identities) == 1


def test_verification_and_manifest_are_deterministic(tmp_path: Path) -> None:
    ledger, service, source, results = _environment(tmp_path)
    _create(service, source, results)
    final = None
    for second in (1, 2, 3):
        final = service.tick("worker", f"2026-08-04T10:00:0{second}Z").run
    assert final is not None and final.status == WorkflowStatus.COMPLETED
    verification_identity, manifest_identity = final.artifact_identities[1:]
    verification_raw = (
        ledger.output_root / verification_identity["artifact_relative_path"]
    ).read_bytes()
    manifest_raw = (
        ledger.output_root / manifest_identity["artifact_relative_path"]
    ).read_bytes()
    verification = json.loads(verification_raw)
    manifest = json.loads(manifest_raw)
    verification_core = dict(verification)
    verification_hash = verification_core.pop("canonical_verification_hash")
    assert canonical_hash(verification_core) == verification_hash
    identified = dict(verification_core)
    verification_id = identified.pop("verification_id")
    assert verification_id == f"verification-{canonical_hash(identified)[:32]}"
    manifest_core = dict(manifest)
    manifest_hash = manifest_core.pop("canonical_manifest_hash")
    assert canonical_hash(manifest_core) == manifest_hash
    identified = dict(manifest_core)
    manifest_id = identified.pop("manifest_id")
    assert manifest_id == f"manifest-{canonical_hash(identified)[:32]}"
    assert "verified_at" not in verification
    assert "published_at" not in manifest
    assert hashlib.sha256(verification_raw).hexdigest() == verification_identity[
        "artifact_byte_hash"
    ]
    assert hashlib.sha256(manifest_raw).hexdigest() == manifest_identity[
        "artifact_byte_hash"
    ]


def test_cli_has_only_exact_foreground_commands(
    tmp_path: Path, capsys
) -> None:
    from offchain.orchestration.__main__ import _parser, main

    parser = _parser()
    subparsers = next(
        action for action in parser._actions if hasattr(action, "choices")
        and action.choices
    )
    assert tuple(subparsers.choices) == (
        "init", "create-observation-run", "tick", "recover",
        "run-until-idle", "status", "cancel",
    )
    assert main(["tick", "--shell", "id"]) == 2
    error = capsys.readouterr()
    payload = json.loads(error.err)
    assert payload["reason_token"] == "WORKFLOW_INPUT_INVALID"
    assert set(payload) == {"explanation", "reason_token"}
    assert "Traceback" not in error.err
    assert "fencing_token" not in error.err


def test_resource_limits_fail_before_expensive_work(tmp_path: Path) -> None:
    _, service, _, _ = _environment(tmp_path)
    with pytest.raises(OrchestrationError) as input_error:
        service.create_run(
            run_key="bounded",
            research_ledger_path=tmp_path / "missing.sqlite3",
            result_root=tmp_path / "missing-results",
            expected_repository_commit="not-a-commit",
            observation_as_of=AS_OF,
            requested_at=AS_OF,
            requested_by="LOCAL_OPERATOR",
        )
    assert input_error.value.reason_token == "WORKFLOW_INPUT_INVALID"
    assert not (tmp_path / "missing.sqlite3").exists()
    with pytest.raises(OrchestrationError) as artifact_error:
        publish_canonical(
            tmp_path / "oversized.json",
            {"value": "x" * 100},
            max_bytes=10,
        )
    assert artifact_error.value.reason_token == "RESOURCE_LIMIT_EXCEEDED"
    assert not (tmp_path / "oversized.json").exists()
    for invalid in (True, 0, 10001):
        with pytest.raises(OrchestrationError) as ticks_error:
            service.run_until_idle("worker", lambda: AS_OF, invalid)
        assert ticks_error.value.reason_token == "WORKFLOW_INPUT_INVALID"


def test_immutable_event_state_derivation(tmp_path: Path) -> None:
    ledger, service, source, results = _environment(tmp_path)
    created = _create(service, source, results)
    initial = service.get_run(created.run_id)
    assert initial.status == WorkflowStatus.PENDING
    claimed = service._claim_one("worker", "2026-08-04T10:00:01Z")
    assert claimed is not None
    running = service.get_run(created.run_id)
    assert running.status == WorkflowStatus.RUNNING
    service.recover_expired_claims("2026-08-04T10:01:01Z")
    waiting = service.get_run(created.run_id)
    assert waiting.status == WorkflowStatus.WAITING_RETRY
    with ledger._connection() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE workflow_events SET reason_token='changed' "
                "WHERE run_id=?",
                (created.run_id,),
            )


def test_documentation_ownership_is_mission_specific() -> None:
    registry = json.loads(
        (ROOT / "docs" / "documentation-status.json").read_text(encoding="utf-8")
    )
    records = registry["documents"]
    matches = [
        record for record in records
        if record["path"] == "docs/DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR.md"
    ]
    assert len(matches) == 1
    assert matches[0]["classification"] == "CURRENT_INTERNAL"
    explanation = (
        ROOT / "docs" / "DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR.md"
    ).read_text(encoding="utf-8")
    assert "SQLite `DELETE` journal mode" in explanation
    assert "`EXTRA` synchronous durability" in explanation
    assert "fencing" in explanation
    assert "completed_at" in explanation


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.update(contract_hash_sha256="0" * 64),
        lambda value: value.update(contract_id="wrong"),
        lambda value: value.update(preceding_contract="wrong"),
    ],
)
def test_governance_integrity_fails_closed(
    tmp_path: Path, mutator
) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(ROOT / "contracts", repository / "contracts")
    contract_path = repository / "contracts" / CONTRACT.name
    value = json.loads(contract_path.read_text(encoding="utf-8"))
    mutator(value)
    contract_path.write_text(json.dumps(value), encoding="utf-8")
    parent = tmp_path / "db"
    parent.mkdir()
    with pytest.raises(OrchestrationError) as caught:
        WorkflowLedger.initialize(
            database_path=parent / "workflow.sqlite3",
            output_root=parent / "output",
            governance_repository_root=repository,
            created_at=AS_OF,
        )
    assert caught.value.reason_token == "GOVERNANCE_CONTRACT_INTEGRITY_FAILURE"
