"""Independent read-only Mission 102 binding to consumed Mission 101 authority."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import stat
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import quote

from offchain.research.admission.models import canonical_hash as m94_hash
from offchain.research.reopening import authority as m101_authority
from offchain.research.reopening.admission import _trial_ledger_path, _verify_trial_ledger_file

from .core import (
    AUTHORITY_SNAPSHOT_ID,
    AUTHORITY_HISTORICAL_PROOF_ID,
    CONSUMED_PERMIT_VERIFIER_ID,
    CROSS_STORE_GATE_ID,
    DATA_CLASS,
    M101_ADMISSION_STAGE,
    M94_BINDING_ID,
    MISSION101_HASH,
    MISSION101_ID,
    SECURE_BINDING_ID,
    DevelopmentRuntimeError,
    canonical_hash,
    canonical_json,
    get_repository_observation,
    parse_utc,
    private_absolute_root,
    require_hash,
    strict_json_load,
    trusted_utc_now,
)


MAX_AUTHORITY_BYTES = 16 * 1024 * 1024
MAX_LEDGER_BYTES = 64 * 1024 * 1024
ADMISSION_REASON = "M101_DEVELOPMENT_ADMISSION_GATES_PASSED"


def _schema_rows(conn: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in conn.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ).fetchall()]


@contextmanager
def _authority_snapshot_connection(root: str | Path) -> Iterator[sqlite3.Connection]:
    runtime = private_absolute_root(root, must_exist=True, label="AUTHORITY_ROOT")
    path = runtime / m101_authority.DATABASE_NAME
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise DevelopmentRuntimeError("AUTHORITY_DATABASE_FILE_INVALID")
    if path.stat().st_size > MAX_AUTHORITY_BYTES:
        raise DevelopmentRuntimeError("AUTHORITY_DATABASE_SIZE_LIMIT")
    conn = sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=ro", uri=True, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DevelopmentRuntimeError("AUTHORITY_DATABASE_INTEGRITY_INVALID")
        if int(conn.execute("PRAGMA application_id").fetchone()[0]) != m101_authority.APPLICATION_ID or int(conn.execute("PRAGMA user_version").fetchone()[0]) != m101_authority.USER_VERSION:
            raise DevelopmentRuntimeError("AUTHORITY_DATABASE_IDENTITY_INVALID")
        if _schema_rows(conn) != m101_authority.EXPECTED_SCHEMA_ROWS:
            raise DevelopmentRuntimeError("AUTHORITY_DATABASE_SCHEMA_INVALID")
        # This real table read occurs before the authority clock is sampled and
        # materially establishes the SQLite read snapshot.
        conn.execute("SELECT COUNT(*) FROM permits").fetchone()
        yield conn
        conn.rollback()
    except sqlite3.DatabaseError as error:
        raise DevelopmentRuntimeError("AUTHORITY_DATABASE_INTEGRITY_INVALID") from error
    finally:
        conn.close()


def _permit(conn: sqlite3.Connection, permit_id: str, decision_time: str, *, require_current: bool) -> tuple[dict[str, Any], list[sqlite3.Row]]:
    row = conn.execute("SELECT permit_hash,permit_json FROM permits WHERE permit_id=?", (permit_id,)).fetchone()
    if row is None:
        raise DevelopmentRuntimeError("PERMIT_UNKNOWN")
    try:
        permit = m101_authority._validate_permit(strict_json_load(row["permit_json"]))
    except Exception as error:
        raise DevelopmentRuntimeError(getattr(error, "reason", "PERMIT_SCHEMA_INVALID")) from error
    if canonical_json(permit) != row["permit_json"] or permit["canonical_permit_hash"] != row["permit_hash"]:
        raise DevelopmentRuntimeError("PERMIT_STORAGE_INTEGRITY_INVALID")
    events = list(conn.execute("SELECT * FROM permit_events WHERE permit_id=? ORDER BY sequence_number", (permit_id,)))
    if not events or len(events) > 2:
        raise DevelopmentRuntimeError("PERMIT_EVENT_HISTORY_INVALID")
    for index, event in enumerate(events, 1):
        core = {key: event[key] for key in ("permit_id", "sequence_number", "status", "reason_token", "event_at")}
        if event["sequence_number"] != index or event["event_hash"] != canonical_hash(core) or event["event_id"] != f"permit-event-{event['event_hash']}":
            raise DevelopmentRuntimeError("PERMIT_EVENT_HISTORY_INVALID")
    if events[0]["status"] != "ISSUED" or events[0]["reason_token"] != "FOUNDER_ACKNOWLEDGED_DEVELOPMENT_PERMIT" or events[0]["event_at"] != permit["issued_at"]:
        raise DevelopmentRuntimeError("PERMIT_EVENT_HISTORY_INVALID")
    if len(events) == 2 and (events[1]["status"] != "REVOKED" or events[1]["reason_token"] != "FOUNDER_REVOKED" or parse_utc(events[1]["event_at"], "revoked_at") < parse_utc(permit["issued_at"], "issued_at")):
        raise DevelopmentRuntimeError("PERMIT_EVENT_HISTORY_INVALID")
    now = parse_utc(decision_time, "authority_decision_time")
    issued = parse_utc(permit["issued_at"], "issued_at")
    expires = parse_utc(permit["expires_at"], "expires_at")
    if now < issued:
        raise DevelopmentRuntimeError("PERMIT_NOT_YET_ACTIVE")
    if now >= expires:
        raise DevelopmentRuntimeError("PERMIT_EXPIRED")
    if require_current:
        # A current-authority decision is linearized against the database
        # snapshot, not against a caller-supplied historical wall time.  Once
        # a valid revocation is visible in that snapshot, current authority is
        # gone even if ``decision_time`` predates the revocation event.
        if len(events) == 2:
            raise DevelopmentRuntimeError("PERMIT_REVOKED")
    elif len(events) == 2 and parse_utc(events[1]["event_at"], "revoked_at") <= now:
        raise DevelopmentRuntimeError("PERMIT_REVOKED_AT_EXECUTION")
    return permit, events


def _consumption(conn: sqlite3.Connection, trial_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = conn.execute("SELECT * FROM permit_consumptions WHERE trial_id=?", (trial_id,)).fetchall()
    if len(rows) != 1:
        raise DevelopmentRuntimeError("EXACT_PERMIT_CONSUMPTION_REQUIRED")
    row = rows[0]
    core = {key: row[key] for key in ("permit_id", "trial_id", "request_hash", "budget_id", "reserved_at")}
    expected = canonical_hash(core)
    if row["consumption_hash"] != expected or row["consumption_id"] != f"permit-consumption-{expected}":
        raise DevelopmentRuntimeError("PERMIT_CONSUMPTION_INTEGRITY_INVALID")
    return dict(row), core


def read_trial_binding(
    ledger_path: str | Path, trial_id: str, *, allow_completed: bool = False
) -> dict[str, Any]:
    try:
        path = _trial_ledger_path(ledger_path, must_exist=True)
        _verify_trial_ledger_file(path)
    except Exception as error:
        raise DevelopmentRuntimeError(getattr(error, "reason", "TRIAL_LEDGER_INVALID")) from error
    if path.stat().st_size > MAX_LEDGER_BYTES:
        raise DevelopmentRuntimeError("TRIAL_LEDGER_SIZE_LIMIT")
    conn = sqlite3.connect(
        "file:" + quote(str(path), safe="/") + "?mode=ro",
        uri=True, isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        reservation = conn.execute("SELECT * FROM trial_reservations WHERE trial_id=?", (trial_id,)).fetchone()
        if reservation is None:
            raise DevelopmentRuntimeError("TRIAL_RESERVATION_MISMATCH")
        events = conn.execute("SELECT * FROM trial_events WHERE trial_id=? ORDER BY sequence_number", (trial_id,)).fetchall()
        if not events or len(events) > 3:
            raise DevelopmentRuntimeError("TRIAL_EVENT_HISTORY_INVALID")
        previous_time = None
        for index, event in enumerate(events, 1):
            core = {key: event[key] for key in ("trial_id", "sequence_number", "status_token", "reason_token", "event_timestamp")}
            expected = m94_hash(core)
            if event["sequence_number"] != index or event["canonical_event_hash"] != expected or event["event_id"] != f"event-{expected[:32]}":
                raise DevelopmentRuntimeError("TRIAL_EVENT_INTEGRITY_INVALID")
            event_time = parse_utc(event["event_timestamp"], "trial_event_timestamp")
            if previous_time is not None and event_time < previous_time:
                raise DevelopmentRuntimeError("TRIAL_EVENT_TIME_REGRESSION")
            previous_time = event_time
        expected_statuses = ["RESERVED", "ADMITTED"] + (["COMPLETED"] if len(events) == 3 else [])
        if [row["status_token"] for row in events] != expected_statuses or events[0]["reason_token"] != "TRIAL_RESERVED" or events[1]["reason_token"] != ADMISSION_REASON:
            latest = events[-1]["status_token"]
            if latest in {"FAILED", "REJECTED", "STOPPED", "SUPERSEDED"}:
                raise DevelopmentRuntimeError("TRIAL_TERMINAL")
            raise DevelopmentRuntimeError("TRIAL_STATE_NOT_ADMITTED")
        if reservation["reserved_at"] != events[0]["event_timestamp"] or reservation["reserved_at"] != events[1]["event_timestamp"]:
            raise DevelopmentRuntimeError("M101_ADMISSION_TIMESTAMP_MISMATCH")
        if len(events) == 3 and events[2]["reason_token"] != "M102_DEVELOPMENT_RESULT_VERIFIED":
            raise DevelopmentRuntimeError("TRIAL_COMPLETION_INVALID")
        budget = conn.execute("SELECT * FROM trial_budgets WHERE budget_id=?", (reservation["budget_id"],)).fetchone()
        if budget is None:
            raise DevelopmentRuntimeError("BUDGET_UNKNOWN")
        budget_core = {key: budget[key] for key in ("budget_id", "controlling_contract_id", "controlling_contract_hash", "experiment_family", "total_trial_budget", "created_at")}
        if m94_hash(budget_core) != budget["canonical_budget_hash"] or budget["controlling_contract_id"] != MISSION101_ID or budget["controlling_contract_hash"] != MISSION101_HASH:
            raise DevelopmentRuntimeError("BUDGET_DEFINITION_MISMATCH")
        links = conn.execute("SELECT * FROM trial_result_links WHERE trial_id=?", (trial_id,)).fetchall()
        if len(links) > 1:
            raise DevelopmentRuntimeError("TRIAL_RESULT_LINK_INVALID")
        result_link = None if not links else dict(links[0])
        if result_link is not None:
            link_core = {key: result_link[key] for key in (
                "trial_id", "result_bundle_id", "result_bundle_hash",
                "result_bundle_path", "linked_at",
            )}
            if canonical_hash(link_core) != result_link["canonical_result_link_hash"]:
                raise DevelopmentRuntimeError("TRIAL_RESULT_LINK_INVALID")
        if len(events) == 2:
            if result_link is not None:
                raise DevelopmentRuntimeError("PREMATURE_RESULT_LINK")
            lifecycle_state = "ADMITTED"
        else:
            if not allow_completed:
                raise DevelopmentRuntimeError("TRIAL_ALREADY_COMPLETED")
            if result_link is None:
                raise DevelopmentRuntimeError("COMPLETED_RESULT_LINK_REQUIRED")
            lifecycle_state = "COMPLETED"
        binding_core = {
            "binding_schema": M94_BINDING_ID,
            "reservation": dict(reservation),
            "budget": dict(budget),
            "admission_event": dict(events[1]),
        }
        conn.rollback()
        return {
            "reservation": dict(reservation), "budget": dict(budget),
            "admission_event": dict(events[1]),
            "completion_event": None if len(events) == 2 else dict(events[2]),
            "result_link": result_link, "lifecycle_state": lifecycle_state,
            "m94_binding_core": binding_core,
            "m94_binding_hash": canonical_hash(binding_core),
        }
    except sqlite3.DatabaseError as error:
        raise DevelopmentRuntimeError("TRIAL_LEDGER_INTEGRITY_INVALID") from error
    finally:
        conn.close()


def capture_authority_snapshot(
    *,
    trial_id: str,
    ledger_path: str | Path,
    authority_root: str | Path,
    descriptor: Mapping[str, Any],
    time_provider: Callable[[], str] | None = None,
    authority_decision_time: str | None = None,
    repository_observer: Callable[[], Mapping[str, Any]] | None = None,
    require_current: bool = True,
    preliminary_trial: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Linearize execution authority without consuming a second permit slot."""

    if require_current and authority_decision_time is not None:
        raise DevelopmentRuntimeError("CURRENT_AUTHORITY_TIME_CALLER_SUPPLIED")
    if not require_current and authority_decision_time is None:
        raise DevelopmentRuntimeError("HISTORICAL_AUTHORITY_TIME_REQUIRED")
    trial = read_trial_binding(ledger_path, trial_id, allow_completed=not require_current)
    if preliminary_trial is not None and (
        preliminary_trial.get("m94_binding_hash") != trial["m94_binding_hash"]
        or preliminary_trial.get("lifecycle_state") != trial["lifecycle_state"]
        or preliminary_trial.get("result_link") != trial["result_link"]
    ):
        raise DevelopmentRuntimeError("M94_STATE_CHANGED_BEFORE_AUTHORITY_SNAPSHOT")
    observation = get_repository_observation(repository_observer)
    if not observation["clean"]:
        raise DevelopmentRuntimeError("DIRTY_REPOSITORY")
    with _authority_snapshot_connection(authority_root) as conn:
        try:
            decision = (time_provider or trusted_utc_now)() if require_current else authority_decision_time
        except Exception as error:
            raise DevelopmentRuntimeError("TRUSTED_AUTHORITY_TIME_INVALID") from error
        assert decision is not None
        parse_utc(decision, "authority_decision_time")
        consumption, consumption_core = _consumption(conn, trial_id)
        permit, events = _permit(conn, consumption["permit_id"], decision, require_current=require_current)
        if require_current:
            consumed_count = int(conn.execute(
                "SELECT COUNT(*) FROM permit_consumptions WHERE permit_id=?",
                (permit["permit_id"],),
            ).fetchone()[0])
            if consumed_count > permit["fixed_trial_budget"]:
                raise DevelopmentRuntimeError("PERMIT_CONSUMPTION_INTEGRITY_INVALID")
        reservation = trial["reservation"]
        budget = trial["budget"]
        if consumption["request_hash"] != reservation["request_hash"]:
            raise DevelopmentRuntimeError("PERMIT_CONSUMPTION_REQUEST_MISMATCH")
        if consumption["budget_id"] != reservation["budget_id"]:
            raise DevelopmentRuntimeError("PERMIT_CONSUMPTION_BUDGET_MISMATCH")
        if consumption["reserved_at"] != reservation["reserved_at"] or consumption["reserved_at"] != trial["admission_event"]["event_timestamp"]:
            raise DevelopmentRuntimeError("M101_ADMISSION_TIMESTAMP_MISMATCH")
        bindings = {
            "repository_commit": observation["head"],
            "dataset_id": descriptor.get("dataset_id"),
            "dataset_descriptor_hash": descriptor.get("canonical_descriptor_hash"),
            "source_custody_release_id": descriptor.get("source_forward_custody_release_id"),
            "source_custody_release_core_hash": descriptor.get("release_core_hash"),
            "source_custody_release_certificate_hash": descriptor.get("release_certificate_hash"),
            "experiment_family": budget["experiment_family"],
            "allowed_authorization_stage": M101_ADMISSION_STAGE,
        }
        for field, expected in bindings.items():
            if permit.get(field) != expected:
                if field == "repository_commit" and not require_current:
                    raise DevelopmentRuntimeError("HISTORICAL_EXECUTION_CODE_CONTEXT_REQUIRED")
                raise DevelopmentRuntimeError("PERMIT_BINDING_MISMATCH", field)
        if descriptor.get("data_class") != DATA_CLASS or descriptor.get("split_identity") != DATA_CLASS:
            raise DevelopmentRuntimeError("DATASET_CLASS_UNAUTHORIZED")
        if budget["total_trial_budget"] != permit["fixed_trial_budget"]:
            raise DevelopmentRuntimeError("BUDGET_DEFINITION_MISMATCH")
        # Final M94 gate is deliberately a second database snapshot while the
        # already-established M101 authority snapshot remains active.
        final_trial = read_trial_binding(ledger_path, trial_id, allow_completed=not require_current)
        if (
            final_trial["m94_binding_hash"] != trial["m94_binding_hash"]
            or final_trial["lifecycle_state"] != trial["lifecycle_state"]
            or final_trial["result_link"] != trial["result_link"]
        ):
            raise DevelopmentRuntimeError("M94_BINDING_CHANGED_DURING_AUTHORIZATION")
        if require_current and (final_trial["lifecycle_state"] != "ADMITTED" or final_trial["result_link"] is not None):
            raise DevelopmentRuntimeError("FINAL_M94_GATE_NOT_ADMITTED")
        core = {
            "snapshot_schema": AUTHORITY_SNAPSHOT_ID,
            "historical_proof_schema": AUTHORITY_HISTORICAL_PROOF_ID,
            "cross_store_gate": CROSS_STORE_GATE_ID,
            "secure_binding_profile": SECURE_BINDING_ID,
            "consumed_permit_verifier": CONSUMED_PERMIT_VERIFIER_ID,
            "authority_decision_time": decision,
            "trial_id": trial_id,
            "request_hash": reservation["request_hash"],
            "budget_id": reservation["budget_id"],
            "declared_trial_number": reservation["declared_trial_number"],
            "initiated_by": reservation["initiated_by"],
            "reserved_at": reservation["reserved_at"],
            "m94_binding_hash": final_trial["m94_binding_hash"],
            "experiment_family": budget["experiment_family"],
            "fixed_trial_budget": permit["fixed_trial_budget"],
            "permit_id": permit["permit_id"],
            "permit_hash": permit["canonical_permit_hash"],
            "permit_issued_at": permit["issued_at"],
            "permit_expires_at": permit["expires_at"],
            "effective_permit_state": "ISSUED",
            "consumption_id": consumption["consumption_id"],
            "consumption_hash": consumption["consumption_hash"],
            "dataset_id": permit["dataset_id"],
            "dataset_descriptor_hash": permit["dataset_descriptor_hash"],
            "release_id": permit["source_custody_release_id"],
            "release_core_hash": permit["source_custody_release_core_hash"],
            "release_certificate_hash": permit["source_custody_release_certificate_hash"],
            "repository_commit": observation["head"],
            "repository_clean": True,
        }
        return {**core, "authority_snapshot_hash": canonical_hash(core)}
