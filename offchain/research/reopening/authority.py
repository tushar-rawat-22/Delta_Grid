"""Private append-only Mission 101 development-permit authority runtime."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import quote

from .core import (
    AUTONOMY_V3_HASH,
    AUTONOMY_V3_ID,
    DATA_CLASS,
    DEVELOPMENT_STAGE,
    MISSION101_HASH,
    MISSION101_ID,
    REPOSITORY_ROOT,
    SPLIT_IDENTITY,
    ReopeningError,
    canonical_hash,
    canonical_json,
    get_repository_observation,
    load_contracts,
    parse_utc,
    require_commit,
    require_hash,
    require_identifier,
    strict_json_load,
    trusted_utc_now,
)
from .dataset import verify_development_dataset_descriptor


ACK_INITIALIZE_AUTHORITY = "INITIALIZE_M101_RESEARCH_AUTHORITY_RUNTIME"
ACK_ISSUE_PERMIT = "ISSUE_M101_DEVELOPMENT_PERMIT"
ACK_REVOKE_PERMIT = "REVOKE_M101_DEVELOPMENT_PERMIT"
DATABASE_NAME = "authority.sqlite3"
APPLICATION_ID = 0x44474131
USER_VERSION = 2
MAX_PERMITS = 1000
MAX_EVENTS = 2000
MAX_CONSUMPTIONS = 10_000
MAX_DATABASE_BYTES = 16 * 1024 * 1024
PERMIT_FIELDS = {
    "schema_version", "permit_id", "autonomy_contract_id", "autonomy_contract_hash",
    "mission101_contract_id", "mission101_contract_hash", "repository_commit",
    "issuer_role", "trust_boundary", "dataset_id", "dataset_descriptor_hash",
    "source_custody_release_id", "source_custody_release_core_hash",
    "source_custody_release_certificate_hash", "data_class", "split_identity",
    "experiment_family", "fixed_trial_budget", "allowed_authorization_stage",
    "issued_at", "expires_at", "canonical_permit_hash",
}

SCHEMA = f"""
PRAGMA application_id={APPLICATION_ID};
PRAGMA user_version={USER_VERSION};
PRAGMA foreign_keys=ON;
CREATE TABLE permits (
    permit_id TEXT PRIMARY KEY,
    permit_hash TEXT NOT NULL UNIQUE,
    permit_json TEXT NOT NULL UNIQUE
) WITHOUT ROWID;
CREATE TABLE permit_events (
    event_id TEXT PRIMARY KEY,
    permit_id TEXT NOT NULL REFERENCES permits(permit_id),
    sequence_number INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ISSUED','REVOKED')),
    reason_token TEXT NOT NULL,
    event_at TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE,
    UNIQUE(permit_id,sequence_number)
) WITHOUT ROWID;
CREATE TABLE permit_consumptions (
    consumption_id TEXT PRIMARY KEY,
    permit_id TEXT NOT NULL REFERENCES permits(permit_id),
    trial_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    budget_id TEXT NOT NULL,
    reserved_at TEXT NOT NULL,
    consumption_hash TEXT NOT NULL UNIQUE,
    UNIQUE(permit_id,trial_id),
    UNIQUE(permit_id,request_hash)
) WITHOUT ROWID;
CREATE TRIGGER permits_no_update BEFORE UPDATE ON permits BEGIN SELECT RAISE(ABORT,'IMMUTABLE_PERMIT'); END;
CREATE TRIGGER permits_no_delete BEFORE DELETE ON permits BEGIN SELECT RAISE(ABORT,'IMMUTABLE_PERMIT'); END;
CREATE TRIGGER permit_events_no_update BEFORE UPDATE ON permit_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_PERMIT_EVENT'); END;
CREATE TRIGGER permit_events_no_delete BEFORE DELETE ON permit_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_PERMIT_EVENT'); END;
CREATE TRIGGER permit_consumptions_no_update BEFORE UPDATE ON permit_consumptions BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_PERMIT_CONSUMPTION'); END;
CREATE TRIGGER permit_consumptions_no_delete BEFORE DELETE ON permit_consumptions BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_PERMIT_CONSUMPTION'); END;
""".strip()


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_authority_root(root: str | Path, *, require_exists: bool = True) -> Path:
    lexical = Path(root).expanduser()
    if not lexical.is_absolute():
        raise ReopeningError("AUTHORITY_ROOT_NOT_ABSOLUTE")
    current = lexical
    while True:
        if current.is_symlink():
            raise ReopeningError("AUTHORITY_ROOT_SYMLINK")
        if current == current.parent:
            break
        current = current.parent
    resolved = lexical.resolve(strict=False)
    if _inside(resolved, REPOSITORY_ROOT.resolve(strict=True)):
        raise ReopeningError("AUTHORITY_ROOT_INSIDE_REPOSITORY")
    if require_exists:
        if resolved.is_symlink() or not resolved.is_dir():
            raise ReopeningError("AUTHORITY_ROOT_INVALID")
        if stat.S_IMODE(resolved.stat().st_mode) != 0o700:
            raise ReopeningError("AUTHORITY_ROOT_MODE_INVALID")
    return resolved


def _schema_rows(conn: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
    ]


def _expected_schema_rows() -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA)
        return _schema_rows(conn)
    finally:
        conn.close()


EXPECTED_SCHEMA_ROWS = _expected_schema_rows()


def _verify_schema(conn: sqlite3.Connection) -> None:
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ReopeningError("AUTHORITY_DATABASE_INTEGRITY_INVALID")
    if int(conn.execute("PRAGMA application_id").fetchone()[0]) != APPLICATION_ID or int(conn.execute("PRAGMA user_version").fetchone()[0]) != USER_VERSION:
        raise ReopeningError("AUTHORITY_DATABASE_IDENTITY_INVALID")
    if _schema_rows(conn) != EXPECTED_SCHEMA_ROWS:
        raise ReopeningError("AUTHORITY_DATABASE_SCHEMA_INVALID")
    consumption_count = int(conn.execute("SELECT COUNT(*) FROM permit_consumptions").fetchone()[0])
    if consumption_count > MAX_CONSUMPTIONS:
        raise ReopeningError("PERMIT_CONSUMPTION_COUNT_LIMIT")
    permit_budgets: dict[str, int] = {}
    permit_counts: dict[str, int] = {}
    for row in conn.execute(
        "SELECT consumption_id,permit_id,trial_id,request_hash,budget_id,reserved_at,consumption_hash "
        "FROM permit_consumptions ORDER BY consumption_id"
    ):
        require_identifier(row["trial_id"], "trial_id")
        require_hash(row["request_hash"], "request_hash")
        require_identifier(row["budget_id"], "budget_id")
        parse_utc(row["reserved_at"], "reserved_at")
        core = {
            "permit_id": row["permit_id"],
            "trial_id": row["trial_id"],
            "request_hash": row["request_hash"],
            "budget_id": row["budget_id"],
            "reserved_at": row["reserved_at"],
        }
        expected = canonical_hash(core)
        if row["consumption_hash"] != expected or row["consumption_id"] != f"permit-consumption-{expected}":
            raise ReopeningError("PERMIT_CONSUMPTION_INTEGRITY_INVALID")
        if row["permit_id"] not in permit_budgets:
            permit_row = conn.execute(
                "SELECT permit_json FROM permits WHERE permit_id=?", (row["permit_id"],)
            ).fetchone()
            if permit_row is None:
                raise ReopeningError("PERMIT_CONSUMPTION_INTEGRITY_INVALID")
            permit_budgets[row["permit_id"]] = _validate_permit(
                strict_json_load(permit_row["permit_json"])
            )["fixed_trial_budget"]
        permit_counts[row["permit_id"]] = permit_counts.get(row["permit_id"], 0) + 1
        if permit_counts[row["permit_id"]] > permit_budgets[row["permit_id"]]:
            raise ReopeningError("PERMIT_CONSUMPTION_INTEGRITY_INVALID")


@contextmanager
def _connection(root: str | Path, *, readonly: bool) -> Iterator[sqlite3.Connection]:
    runtime = validate_authority_root(root)
    path = runtime / DATABASE_NAME
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ReopeningError("AUTHORITY_DATABASE_FILE_INVALID")
    if path.stat().st_size > MAX_DATABASE_BYTES:
        raise ReopeningError("AUTHORITY_DATABASE_SIZE_LIMIT")
    if readonly:
        conn = sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=ro", uri=True)
        conn.execute("PRAGMA query_only=ON")
    else:
        conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        _verify_schema(conn)
        yield conn
    finally:
        conn.close()


def initialize_authority_runtime(root: str | Path, *, acknowledgement: str) -> dict[str, Any]:
    if acknowledgement != ACK_INITIALIZE_AUTHORITY:
        raise ReopeningError("AUTHORITY_INITIALIZATION_ACKNOWLEDGEMENT_REQUIRED")
    load_contracts()
    runtime = validate_authority_root(root, require_exists=False)
    if runtime.exists():
        if not runtime.is_dir() or stat.S_IMODE(runtime.stat().st_mode) != 0o700:
            raise ReopeningError("AUTHORITY_ROOT_MODE_INVALID")
        if any(runtime.iterdir()):
            raise ReopeningError("AUTHORITY_RUNTIME_NOT_EMPTY")
    else:
        runtime.mkdir(parents=True, mode=0o700)
        os.chmod(runtime, 0o700)
    database = runtime / DATABASE_NAME
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(database, flags, 0o600)
    os.close(fd)
    conn = sqlite3.connect(database)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        _verify_schema(conn)
    finally:
        conn.close()
    os.chmod(database, 0o600, follow_symlinks=False)
    return {"runtime_root": str(runtime), "database": DATABASE_NAME, "trust_boundary": "SINGLE_OS_USER_PRIVATE_RUNTIME_AND_EXPLICIT_ACKNOWLEDGEMENT"}


def _validate_permit(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != PERMIT_FIELDS:
        raise ReopeningError("PERMIT_SCHEMA_INVALID")
    permit = dict(value)
    if (
        permit["schema_version"] != "1.0"
        or permit["autonomy_contract_id"] != AUTONOMY_V3_ID
        or permit["autonomy_contract_hash"] != AUTONOMY_V3_HASH
        or permit["mission101_contract_id"] != MISSION101_ID
        or permit["mission101_contract_hash"] != MISSION101_HASH
        or permit["issuer_role"] != "FOUNDER"
        or permit["trust_boundary"] != "SINGLE_OS_USER_PRIVATE_RUNTIME_AND_EXPLICIT_ACKNOWLEDGEMENT"
        or permit["data_class"] != DATA_CLASS
        or permit["split_identity"] != SPLIT_IDENTITY
        or permit["allowed_authorization_stage"] != DEVELOPMENT_STAGE
    ):
        raise ReopeningError("PERMIT_AUTHORITY_INVALID")
    require_commit(permit["repository_commit"], "repository_commit")
    require_identifier(permit["experiment_family"], "experiment_family")
    for field in ("dataset_descriptor_hash", "source_custody_release_core_hash", "source_custody_release_certificate_hash", "canonical_permit_hash"):
        require_hash(permit[field], field)
    if type(permit["fixed_trial_budget"]) is not int or not 1 <= permit["fixed_trial_budget"] <= 10_000:
        raise ReopeningError("PERMIT_TRIAL_BUDGET_INVALID")
    issued = parse_utc(permit["issued_at"], "issued_at")
    expires = parse_utc(permit["expires_at"], "expires_at")
    if expires <= issued:
        raise ReopeningError("PERMIT_VALIDITY_INVALID")
    core = dict(permit)
    permit_id = core.pop("permit_id")
    supplied = core.pop("canonical_permit_hash")
    expected = canonical_hash(core)
    if supplied != expected or permit_id != f"m101-permit-{expected}":
        raise ReopeningError("PERMIT_HASH_MISMATCH")
    return permit


def issue_development_permit(
    root: str | Path,
    *,
    descriptor: Mapping[str, Any] | str | Path,
    release_directory: str | Path,
    custody_runtime_root: str | Path,
    experiment_family: str,
    fixed_trial_budget: int,
    expires_at: str,
    acknowledgement: str,
    repository_observer: Callable[[], Mapping[str, Any]] | None = None,
    time_provider: Callable[[], str] | None = None,
) -> dict[str, Any]:
    if acknowledgement != ACK_ISSUE_PERMIT:
        raise ReopeningError("PERMIT_ISSUANCE_ACKNOWLEDGEMENT_REQUIRED")
    load_contracts()
    dataset = verify_development_dataset_descriptor(
        descriptor,
        release_directory=release_directory,
        runtime_root=custody_runtime_root,
    )
    observation = get_repository_observation(repository_observer)
    if not observation["clean"]:
        raise ReopeningError("DIRTY_REPOSITORY")
    try:
        issued_at = (time_provider or trusted_utc_now)()
    except Exception as error:
        raise ReopeningError("TRUSTED_ISSUED_AT_INVALID") from error
    parse_utc(issued_at, "trusted_issued_at")
    core = {
        "schema_version": "1.0",
        "autonomy_contract_id": AUTONOMY_V3_ID,
        "autonomy_contract_hash": AUTONOMY_V3_HASH,
        "mission101_contract_id": MISSION101_ID,
        "mission101_contract_hash": MISSION101_HASH,
        "repository_commit": observation["head"],
        "issuer_role": "FOUNDER",
        "trust_boundary": "SINGLE_OS_USER_PRIVATE_RUNTIME_AND_EXPLICIT_ACKNOWLEDGEMENT",
        "dataset_id": dataset["dataset_id"],
        "dataset_descriptor_hash": dataset["canonical_descriptor_hash"],
        "source_custody_release_id": dataset["source_forward_custody_release_id"],
        "source_custody_release_core_hash": dataset["release_core_hash"],
        "source_custody_release_certificate_hash": dataset["release_certificate_hash"],
        "data_class": DATA_CLASS,
        "split_identity": SPLIT_IDENTITY,
        "experiment_family": experiment_family,
        "fixed_trial_budget": fixed_trial_budget,
        "allowed_authorization_stage": DEVELOPMENT_STAGE,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    permit_hash = canonical_hash(core)
    permit = _validate_permit({**core, "permit_id": f"m101-permit-{permit_hash}", "canonical_permit_hash": permit_hash})
    with _connection(root, readonly=False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = conn.execute("SELECT permit_json FROM permits WHERE permit_id=?", (permit["permit_id"],)).fetchone()
            if existing is not None:
                parsed = strict_json_load(existing["permit_json"])
                if parsed != permit:
                    raise ReopeningError("PERMIT_IDENTITY_COLLISION")
                conn.commit()
                return permit
            if int(conn.execute("SELECT COUNT(*) FROM permits").fetchone()[0]) >= MAX_PERMITS:
                raise ReopeningError("PERMIT_COUNT_LIMIT")
            permit_json = canonical_json(permit)
            conn.execute("INSERT INTO permits(permit_id,permit_hash,permit_json) VALUES (?,?,?)", (permit["permit_id"], permit_hash, permit_json))
            event_core = {"permit_id": permit["permit_id"], "sequence_number": 1, "status": "ISSUED", "reason_token": "FOUNDER_ACKNOWLEDGED_DEVELOPMENT_PERMIT", "event_at": issued_at}
            event_hash = canonical_hash(event_core)
            conn.execute("INSERT INTO permit_events(event_id,permit_id,sequence_number,status,reason_token,event_at,event_hash) VALUES (?,?,?,?,?,?,?)", (f"permit-event-{event_hash}", permit["permit_id"], 1, "ISSUED", event_core["reason_token"], issued_at, event_hash))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return permit


def _permit_and_events(
    conn: sqlite3.Connection, permit_id: str
) -> tuple[dict[str, Any], list[sqlite3.Row]]:
    row = conn.execute(
        "SELECT permit_hash,permit_json FROM permits WHERE permit_id=?", (permit_id,)
    ).fetchone()
    if row is None:
        raise ReopeningError("PERMIT_UNKNOWN")
    permit = _validate_permit(strict_json_load(row["permit_json"]))
    if canonical_json(permit) != row["permit_json"] or permit["canonical_permit_hash"] != row["permit_hash"]:
        raise ReopeningError("PERMIT_STORAGE_INTEGRITY_INVALID")
    events = conn.execute(
        "SELECT * FROM permit_events WHERE permit_id=? ORDER BY sequence_number", (permit_id,)
    ).fetchall()
    if not events or len(events) > 2:
        raise ReopeningError("PERMIT_EVENT_HISTORY_INVALID")
    for index, event in enumerate(events, start=1):
        core = {
            "permit_id": event["permit_id"],
            "sequence_number": event["sequence_number"],
            "status": event["status"],
            "reason_token": event["reason_token"],
            "event_at": event["event_at"],
        }
        if (
            event["sequence_number"] != index
            or event["event_hash"] != canonical_hash(core)
            or event["event_id"] != f"permit-event-{event['event_hash']}"
        ):
            raise ReopeningError("PERMIT_EVENT_HISTORY_INVALID")
    issued = events[0]
    if (
        issued["sequence_number"] != 1
        or issued["status"] != "ISSUED"
        or issued["reason_token"] != "FOUNDER_ACKNOWLEDGED_DEVELOPMENT_PERMIT"
        or issued["event_at"] != permit["issued_at"]
    ):
        raise ReopeningError("PERMIT_EVENT_HISTORY_INVALID")
    if len(events) == 2:
        revoked = events[1]
        try:
            time_regressed = parse_utc(revoked["event_at"], "revoked_at") < parse_utc(
                permit["issued_at"], "issued_at"
            )
        except ReopeningError as error:
            raise ReopeningError("PERMIT_EVENT_HISTORY_INVALID") from error
        if (
            revoked["sequence_number"] != 2
            or revoked["status"] != "REVOKED"
            or revoked["reason_token"] != "FOUNDER_REVOKED"
            or time_regressed
        ):
            raise ReopeningError("PERMIT_EVENT_HISTORY_INVALID")
    return permit, list(events)


def _assert_permit_current(
    permit: Mapping[str, Any], events: list[sqlite3.Row], decision_time: str
) -> None:
    now = parse_utc(decision_time, "as_of")
    if now < parse_utc(permit["issued_at"], "issued_at"):
        raise ReopeningError("PERMIT_NOT_YET_ACTIVE")
    if len(events) == 2 and now >= parse_utc(events[1]["event_at"], "revoked_at"):
        raise ReopeningError("PERMIT_REVOKED")
    if now >= parse_utc(permit["expires_at"], "expires_at"):
        raise ReopeningError("PERMIT_EXPIRED")


def revoke_development_permit(
    root: str | Path,
    permit_id: str,
    *,
    acknowledgement: str,
    time_provider: Callable[[], str] | None = None,
) -> dict[str, Any]:
    if acknowledgement != ACK_REVOKE_PERMIT:
        raise ReopeningError("PERMIT_REVOCATION_ACKNOWLEDGEMENT_REQUIRED")
    try:
        revoked_at = (time_provider or trusted_utc_now)()
    except Exception as error:
        raise ReopeningError("TRUSTED_REVOKED_AT_INVALID") from error
    parse_utc(revoked_at, "trusted_revoked_at")
    with _connection(root, readonly=False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        permit, events = _permit_and_events(conn, permit_id)
        if len(events) != 1 or events[0]["status"] != "ISSUED":
            conn.rollback()
            raise ReopeningError("PERMIT_NOT_REVOCABLE")
        if parse_utc(revoked_at, "revoked_at") < parse_utc(permit["issued_at"], "issued_at"):
            conn.rollback()
            raise ReopeningError("PERMIT_EVENT_TIME_REGRESSION")
        core = {"permit_id": permit_id, "sequence_number": 2, "status": "REVOKED", "reason_token": "FOUNDER_REVOKED", "event_at": revoked_at}
        event_hash = canonical_hash(core)
        conn.execute("INSERT INTO permit_events(event_id,permit_id,sequence_number,status,reason_token,event_at,event_hash) VALUES (?,?,?,?,?,?,?)", (f"permit-event-{event_hash}", permit_id, 2, "REVOKED", core["reason_token"], revoked_at, event_hash))
        conn.commit()
    return {
        "status": "REVOKED",
        "permit_id": permit_id,
        "event_hash": event_hash,
        "metadata_safe": True,
    }


def _reserve_permit_capacity(
    root: str | Path,
    *,
    permit_id: str,
    trial_id: str,
    request_hash: str,
    budget_id: str,
    reserved_at: str,
) -> dict[str, Any]:
    """Atomically reserve one global, append-only capacity slot for a permit."""

    require_identifier(permit_id, "permit_id")
    require_identifier(trial_id, "trial_id")
    require_hash(request_hash, "request_hash")
    require_identifier(budget_id, "budget_id")
    parse_utc(reserved_at, "reserved_at")
    with _connection(root, readonly=False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            permit, events = _permit_and_events(conn, permit_id)
            if events[-1]["status"] == "REVOKED":
                raise ReopeningError("PERMIT_REVOKED")
            _assert_permit_current(permit, events, reserved_at)
            used = int(
                conn.execute(
                    "SELECT COUNT(*) FROM permit_consumptions WHERE permit_id=?",
                    (permit_id,),
                ).fetchone()[0]
            )
            if used >= permit["fixed_trial_budget"]:
                raise ReopeningError("PERMIT_EXHAUSTED")
            if int(conn.execute("SELECT COUNT(*) FROM permit_consumptions").fetchone()[0]) >= MAX_CONSUMPTIONS:
                raise ReopeningError("PERMIT_CONSUMPTION_COUNT_LIMIT")
            core = {
                "permit_id": permit_id,
                "trial_id": trial_id,
                "request_hash": request_hash,
                "budget_id": budget_id,
                "reserved_at": reserved_at,
            }
            consumption_hash = canonical_hash(core)
            consumption_id = f"permit-consumption-{consumption_hash}"
            conn.execute(
                "INSERT INTO permit_consumptions("
                "consumption_id,permit_id,trial_id,request_hash,budget_id,reserved_at,consumption_hash"
                ") VALUES (?,?,?,?,?,?,?)",
                (
                    consumption_id,
                    permit_id,
                    trial_id,
                    request_hash,
                    budget_id,
                    reserved_at,
                    consumption_hash,
                ),
            )
            conn.commit()
        except ReopeningError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise ReopeningError("PERMIT_CAPACITY_RESERVATION_CONFLICT") from error
        except sqlite3.DatabaseError as error:
            conn.rollback()
            raise ReopeningError("AUTHORITY_DATABASE_INTEGRITY_INVALID") from error
    return {
        "consumption_id": consumption_id,
        "consumption_hash": consumption_hash,
        "permit_id": permit_id,
        "consumed_trials": used + 1,
        "remaining_trials": permit["fixed_trial_budget"] - used - 1,
    }


def verify_development_permit(
    root: str | Path,
    permit_id: str,
    *,
    descriptor: Mapping[str, Any] | str | Path,
    release_directory: str | Path,
    custody_runtime_root: str | Path,
    repository_commit: str,
    experiment_family: str,
    authorization_stage: str,
    as_of: str,
) -> dict[str, Any]:
    dataset = verify_development_dataset_descriptor(
        descriptor,
        release_directory=release_directory,
        runtime_root=custody_runtime_root,
    )
    with _connection(root, readonly=True) as conn:
        permit, events = _permit_and_events(conn, permit_id)
        _assert_permit_current(permit, events, as_of)
        consumed_trials = int(
            conn.execute(
                "SELECT COUNT(*) FROM permit_consumptions WHERE permit_id=?", (permit_id,)
            ).fetchone()[0]
        )
    bindings = {
        "repository_commit": repository_commit,
        "dataset_id": dataset["dataset_id"],
        "dataset_descriptor_hash": dataset["canonical_descriptor_hash"],
        "source_custody_release_id": dataset["source_forward_custody_release_id"],
        "source_custody_release_core_hash": dataset["release_core_hash"],
        "source_custody_release_certificate_hash": dataset["release_certificate_hash"],
        "experiment_family": experiment_family,
        "allowed_authorization_stage": authorization_stage,
    }
    for field, expected in bindings.items():
        if permit[field] != expected:
            raise ReopeningError("PERMIT_BINDING_MISMATCH", field)
    if consumed_trials >= permit["fixed_trial_budget"]:
        raise ReopeningError("PERMIT_EXHAUSTED")
    return {
        "permit_id": permit_id,
        "permit_hash": permit["canonical_permit_hash"],
        "state": "ACTIVE",
        "fixed_trial_budget": permit["fixed_trial_budget"],
        "consumed_trials": consumed_trials,
        "remaining_trials": permit["fixed_trial_budget"] - consumed_trials,
        "trust_boundary": permit["trust_boundary"],
    }


def inspect_authority_runtime(root: str | Path) -> dict[str, Any]:
    """Return a bounded metadata-only view without mutating authority state."""

    with _connection(root, readonly=True) as conn:
        permit_count = int(conn.execute("SELECT COUNT(*) FROM permits").fetchone()[0])
        event_count = int(conn.execute("SELECT COUNT(*) FROM permit_events").fetchone()[0])
        consumption_count = int(conn.execute("SELECT COUNT(*) FROM permit_consumptions").fetchone()[0])
        if permit_count > MAX_PERMITS or event_count > MAX_EVENTS:
            raise ReopeningError("AUTHORITY_RECORD_COUNT_LIMIT")
        permits = []
        for row in conn.execute("SELECT permit_id,permit_hash,permit_json FROM permits ORDER BY permit_id"):
            permit, events = _permit_and_events(conn, row["permit_id"])
            if canonical_json(permit) != row["permit_json"] or permit["canonical_permit_hash"] != row["permit_hash"]:
                raise ReopeningError("PERMIT_STORAGE_INTEGRITY_INVALID")
            latest = events[-1]
            consumed = int(
                conn.execute(
                    "SELECT COUNT(*) FROM permit_consumptions WHERE permit_id=?",
                    (permit["permit_id"],),
                ).fetchone()[0]
            )
            permits.append(
                {
                    "permit_id": permit["permit_id"],
                    "permit_hash": permit["canonical_permit_hash"],
                    "repository_commit": permit["repository_commit"],
                    "dataset_id": permit["dataset_id"],
                    "dataset_descriptor_hash": permit["dataset_descriptor_hash"],
                    "source_custody_release_id": permit["source_custody_release_id"],
                    "experiment_family": permit["experiment_family"],
                    "fixed_trial_budget": permit["fixed_trial_budget"],
                    "consumed_trials": consumed,
                    "remaining_trials": permit["fixed_trial_budget"] - consumed,
                    "authorization_stage": permit["allowed_authorization_stage"],
                    "issued_at": permit["issued_at"],
                    "expires_at": permit["expires_at"],
                    "latest_status": latest["status"],
                    "latest_reason_token": latest["reason_token"],
                    "latest_event_at": latest["event_at"],
                    "event_count": latest["sequence_number"],
                }
            )
    return {
        "schema_version": "1.0",
        "permit_count": permit_count,
        "event_count": event_count,
        "permit_consumption_count": consumption_count,
        "permits": permits,
        "trust_boundary": "SINGLE_OS_USER_PRIVATE_RUNTIME_AND_EXPLICIT_ACKNOWLEDGEMENT",
        "metadata_safe": True,
        "writes_performed": False,
    }
