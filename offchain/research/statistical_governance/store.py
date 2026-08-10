"""Single append-only SQLite state store for Mission 103 governance."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
import json
import os
from pathlib import Path
import sqlite3
import stat
from decimal import Decimal
from fractions import Fraction
from typing import Any, Iterator, Mapping
from urllib.parse import quote

from .core import (
    AUTONOMY_V5_HASH, AUTONOMY_V5_ID, DATABASE_NAME, MAX_JSON_BYTES,
    MISSION103_HASH, MISSION103_ID, STAGES, GovernanceError, canonical_hash,
    canonical_json, freeze_json, load_contracts, parse_utc, private_root,
    require_commit, require_decimal_text, require_hash, require_identifier,
    secure_nonce, trusted_utc_now,
)
from .protocol import (
    apply_measurement_gates, proposal_commitment, validate_campaign_proposal,
    _validate_program_protocol_at, validate_partition_spec, verify_development_binding,
)
from .integrations import (
    M102ResultSource, ProtectedCustodySource, _load_protected_input,
    _materialize_verified_custody, _verify_terminal_m102_source,
    _verify_repository_context, verify_materialization_integrity,
)
from .registry import _resolve_protected_evaluator, _resolve_statistical_adapter
from .statistics import build_randomization_plan, derive_null_seed, fraction_text, holm_step_down
from .protected import (
    PROTECTED_EXECUTOR_ID, execute_protected_candidate,
    validate_candidate_observable_scope,
)


ACK_INITIALIZE = "INITIALIZE_M103_STATISTICAL_GOVERNANCE"
ACK_ADMIT_CAMPAIGN = "FOUNDER_ADMIT_M103_RESEARCH_CAMPAIGN"
ACK_ACTIVATE_PROGRAM = "FOUNDER_ACTIVATE_EXACT_M103_RESEARCH_PROGRAM"
ACK_AUTHORIZE_STAGE = "FOUNDER_AUTHORIZE_M103_PROTECTED_STAGE"
ACK_REVOKE_STAGE = "FOUNDER_REVOKE_M103_PROTECTED_STAGE"
APPLICATION_ID = 0x44473103
USER_VERSION = 1
MAX_DATABASE_BYTES = 64 * 1024 * 1024
TERMINAL_CAMPAIGN_STATES = {"PROGRAM_REJECTED", "QUALIFIED_FOR_M104_OBSERVATION"}


SCHEMA = f"""
PRAGMA application_id={APPLICATION_ID};
PRAGMA user_version={USER_VERSION};
PRAGMA foreign_keys=ON;
CREATE TABLE proposals (
 proposal_hash TEXT PRIMARY KEY, proposal_id TEXT NOT NULL UNIQUE,
 anti_reset_key TEXT NOT NULL, proposal_json TEXT NOT NULL UNIQUE,
 committed_at TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE campaigns (
 campaign_id TEXT PRIMARY KEY, campaign_hash TEXT NOT NULL UNIQUE,
 proposal_hash TEXT NOT NULL UNIQUE REFERENCES proposals(proposal_hash),
 anti_reset_key TEXT NOT NULL UNIQUE, admission_json TEXT NOT NULL UNIQUE
) WITHOUT ROWID;
CREATE TABLE campaign_events (
 event_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
 sequence_number INTEGER NOT NULL, status TEXT NOT NULL, reason_token TEXT NOT NULL,
 event_at TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE,
 UNIQUE(campaign_id,sequence_number)
) WITHOUT ROWID;
CREATE TABLE programs (
 program_id TEXT PRIMARY KEY, program_hash TEXT NOT NULL UNIQUE,
 campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
 protocol_json TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
 UNIQUE(campaign_id,program_id)
) WITHOUT ROWID;
CREATE TABLE program_activations (
 activation_id TEXT PRIMARY KEY, activation_hash TEXT NOT NULL UNIQUE,
 campaign_id TEXT NOT NULL UNIQUE REFERENCES campaigns(campaign_id),
 program_id TEXT NOT NULL UNIQUE REFERENCES programs(program_id),
 proposal_hash TEXT NOT NULL UNIQUE REFERENCES proposals(proposal_hash),
 program_hash TEXT NOT NULL UNIQUE, nonce_hex TEXT NOT NULL UNIQUE,
 activation_json TEXT NOT NULL UNIQUE, activated_at TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE development_results (
 result_id TEXT PRIMARY KEY, program_id TEXT NOT NULL REFERENCES programs(program_id),
 hypothesis_id TEXT NOT NULL, hypothesis_hash TEXT NOT NULL,
 terminal_status TEXT NOT NULL CHECK(terminal_status IN ('SUCCESS','FAILED')),
 evidence_json TEXT NOT NULL, evidence_hash TEXT NOT NULL UNIQUE,
 recorded_at TEXT NOT NULL, UNIQUE(program_id,hypothesis_id), UNIQUE(program_id,hypothesis_hash)
) WITHOUT ROWID;
CREATE TABLE candidates (
 candidate_id TEXT PRIMARY KEY, candidate_hash TEXT NOT NULL UNIQUE,
 program_id TEXT NOT NULL UNIQUE REFERENCES programs(program_id),
 candidate_json TEXT NOT NULL UNIQUE, selected_at TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE materializations (
 materialization_id TEXT PRIMARY KEY, materialization_hash TEXT NOT NULL UNIQUE,
 program_id TEXT NOT NULL REFERENCES programs(program_id), stage TEXT NOT NULL,
 metadata_json TEXT NOT NULL UNIQUE, registered_at TEXT NOT NULL,
 UNIQUE(program_id,stage)
) WITHOUT ROWID;
CREATE TABLE stage_authorizations (
 authorization_id TEXT PRIMARY KEY, authorization_hash TEXT NOT NULL UNIQUE,
 program_id TEXT NOT NULL REFERENCES programs(program_id), stage TEXT NOT NULL,
 authorization_json TEXT NOT NULL UNIQUE,
 UNIQUE(program_id,stage)
) WITHOUT ROWID;
CREATE TABLE authorization_events (
 event_id TEXT PRIMARY KEY, authorization_id TEXT NOT NULL REFERENCES stage_authorizations(authorization_id),
 sequence_number INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('ISSUED','REVOKED')),
 reason_token TEXT NOT NULL, event_at TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE,
 UNIQUE(authorization_id,sequence_number)
) WITHOUT ROWID;
CREATE TABLE authorization_consumptions (
 consumption_id TEXT PRIMARY KEY, authorization_id TEXT NOT NULL UNIQUE REFERENCES stage_authorizations(authorization_id),
 stage_execution_id TEXT NOT NULL UNIQUE, consumed_at TEXT NOT NULL, consumption_hash TEXT NOT NULL UNIQUE
) WITHOUT ROWID;
CREATE TABLE stage_executions (
 stage_execution_id TEXT PRIMARY KEY, execution_hash TEXT NOT NULL UNIQUE,
 program_id TEXT NOT NULL REFERENCES programs(program_id), stage TEXT NOT NULL,
 authorization_id TEXT NOT NULL UNIQUE REFERENCES stage_authorizations(authorization_id),
 execution_json TEXT NOT NULL UNIQUE, opened_at TEXT NOT NULL,
 UNIQUE(program_id,stage)
) WITHOUT ROWID;
CREATE TABLE stage_decisions (
 decision_id TEXT PRIMARY KEY, decision_hash TEXT NOT NULL UNIQUE,
 stage_execution_id TEXT NOT NULL UNIQUE REFERENCES stage_executions(stage_execution_id),
 program_id TEXT NOT NULL REFERENCES programs(program_id), stage TEXT NOT NULL,
 passed INTEGER NOT NULL CHECK(passed IN (0,1)), decision_json TEXT NOT NULL UNIQUE,
 decided_at TEXT NOT NULL, UNIQUE(program_id,stage)
) WITHOUT ROWID;
CREATE TABLE final_artifacts (
 artifact_id TEXT PRIMARY KEY, artifact_hash TEXT NOT NULL UNIQUE,
 program_id TEXT NOT NULL UNIQUE REFERENCES programs(program_id),
 artifact_json TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
) WITHOUT ROWID;
CREATE TRIGGER proposals_no_update BEFORE UPDATE ON proposals BEGIN SELECT RAISE(ABORT,'IMMUTABLE_PROPOSAL'); END;
CREATE TRIGGER proposals_no_delete BEFORE DELETE ON proposals BEGIN SELECT RAISE(ABORT,'IMMUTABLE_PROPOSAL'); END;
CREATE TRIGGER campaigns_no_update BEFORE UPDATE ON campaigns BEGIN SELECT RAISE(ABORT,'IMMUTABLE_CAMPAIGN'); END;
CREATE TRIGGER campaigns_no_delete BEFORE DELETE ON campaigns BEGIN SELECT RAISE(ABORT,'IMMUTABLE_CAMPAIGN'); END;
CREATE TRIGGER campaign_events_no_update BEFORE UPDATE ON campaign_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_CAMPAIGN_EVENT'); END;
CREATE TRIGGER campaign_events_no_delete BEFORE DELETE ON campaign_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_CAMPAIGN_EVENT'); END;
CREATE TRIGGER programs_no_update BEFORE UPDATE ON programs BEGIN SELECT RAISE(ABORT,'IMMUTABLE_PROGRAM'); END;
CREATE TRIGGER programs_no_delete BEFORE DELETE ON programs BEGIN SELECT RAISE(ABORT,'IMMUTABLE_PROGRAM'); END;
CREATE TRIGGER program_activations_no_update BEFORE UPDATE ON program_activations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_PROGRAM_ACTIVATION'); END;
CREATE TRIGGER program_activations_no_delete BEFORE DELETE ON program_activations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_PROGRAM_ACTIVATION'); END;
CREATE TRIGGER development_results_no_update BEFORE UPDATE ON development_results BEGIN SELECT RAISE(ABORT,'IMMUTABLE_DEVELOPMENT_RESULT'); END;
CREATE TRIGGER development_results_no_delete BEFORE DELETE ON development_results BEGIN SELECT RAISE(ABORT,'IMMUTABLE_DEVELOPMENT_RESULT'); END;
CREATE TRIGGER candidates_no_update BEFORE UPDATE ON candidates BEGIN SELECT RAISE(ABORT,'IMMUTABLE_CANDIDATE'); END;
CREATE TRIGGER candidates_no_delete BEFORE DELETE ON candidates BEGIN SELECT RAISE(ABORT,'IMMUTABLE_CANDIDATE'); END;
CREATE TRIGGER materializations_no_update BEFORE UPDATE ON materializations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_MATERIALIZATION'); END;
CREATE TRIGGER materializations_no_delete BEFORE DELETE ON materializations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_MATERIALIZATION'); END;
CREATE TRIGGER stage_authorizations_no_update BEFORE UPDATE ON stage_authorizations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_AUTHORIZATION'); END;
CREATE TRIGGER stage_authorizations_no_delete BEFORE DELETE ON stage_authorizations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_AUTHORIZATION'); END;
CREATE TRIGGER authorization_events_no_update BEFORE UPDATE ON authorization_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_AUTHORIZATION_EVENT'); END;
CREATE TRIGGER authorization_events_no_delete BEFORE DELETE ON authorization_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_AUTHORIZATION_EVENT'); END;
CREATE TRIGGER authorization_consumptions_no_update BEFORE UPDATE ON authorization_consumptions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_AUTHORIZATION_CONSUMPTION'); END;
CREATE TRIGGER authorization_consumptions_no_delete BEFORE DELETE ON authorization_consumptions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_AUTHORIZATION_CONSUMPTION'); END;
CREATE TRIGGER stage_executions_no_update BEFORE UPDATE ON stage_executions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_STAGE_EXECUTION'); END;
CREATE TRIGGER stage_executions_no_delete BEFORE DELETE ON stage_executions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_STAGE_EXECUTION'); END;
CREATE TRIGGER stage_decisions_no_update BEFORE UPDATE ON stage_decisions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_STAGE_DECISION'); END;
CREATE TRIGGER stage_decisions_no_delete BEFORE DELETE ON stage_decisions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_STAGE_DECISION'); END;
CREATE TRIGGER final_artifacts_no_update BEFORE UPDATE ON final_artifacts BEGIN SELECT RAISE(ABORT,'IMMUTABLE_FINAL_ARTIFACT'); END;
CREATE TRIGGER final_artifacts_no_delete BEFORE DELETE ON final_artifacts BEGIN SELECT RAISE(ABORT,'IMMUTABLE_FINAL_ARTIFACT'); END;
""".strip()


def _schema_rows(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    )]


def _expected_schema_rows() -> list[tuple[Any, ...]]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(SCHEMA)
        return _schema_rows(connection)
    finally:
        connection.close()


EXPECTED_SCHEMA_ROWS = _expected_schema_rows()


def initialize_governance(root: str | Path, *, acknowledgement: str) -> dict[str, Any]:
    if acknowledgement != ACK_INITIALIZE:
        raise GovernanceError("GOVERNANCE_INITIALIZATION_ACKNOWLEDGEMENT_REQUIRED")
    load_contracts()
    runtime = private_root(root, must_exist=False)
    if runtime.exists():
        if not runtime.is_dir() or runtime.is_symlink() or stat.S_IMODE(runtime.stat().st_mode) != 0o700:
            raise GovernanceError("GOVERNANCE_ROOT_INVALID")
        if any(runtime.iterdir()):
            raise GovernanceError("GOVERNANCE_ROOT_NOT_EMPTY")
    else:
        runtime.mkdir(parents=True, mode=0o700)
        os.chmod(runtime, 0o700)
    database = runtime / DATABASE_NAME
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(database, flags, 0o600)
    os.close(fd)
    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()
    os.chmod(database, 0o600, follow_symlinks=False)
    return {"status": "INITIALIZED", "database": DATABASE_NAME, "metadata_only": True}


def _verify_database(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise GovernanceError("GOVERNANCE_DATABASE_INTEGRITY_INVALID")
    if int(connection.execute("PRAGMA application_id").fetchone()[0]) != APPLICATION_ID or int(connection.execute("PRAGMA user_version").fetchone()[0]) != USER_VERSION:
        raise GovernanceError("GOVERNANCE_DATABASE_IDENTITY_INVALID")
    if _schema_rows(connection) != EXPECTED_SCHEMA_ROWS:
        raise GovernanceError("GOVERNANCE_DATABASE_SCHEMA_INVALID")
    _verify_rows(connection)


@contextmanager
def connection(root: str | Path, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    runtime = private_root(root, must_exist=True)
    path = runtime / DATABASE_NAME
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600 or path.stat().st_size > MAX_DATABASE_BYTES:
        raise GovernanceError("GOVERNANCE_DATABASE_FILE_INVALID")
    if readonly:
        database = sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=ro", uri=True)
        database.execute("PRAGMA query_only=ON")
        database.execute("BEGIN")
    else:
        database = sqlite3.connect(path, isolation_level=None)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys=ON")
    try:
        _verify_database(database)
        yield database
    finally:
        database.close()


def _json(value: Any) -> str:
    return canonical_json(freeze_json(value))


def _read_json(raw: str) -> dict[str, Any]:
    if len(raw.encode("utf-8")) > MAX_JSON_BYTES:
        raise GovernanceError("GOVERNANCE_JSON_SIZE_LIMIT")
    try:
        value = json.loads(raw, parse_constant=lambda _x: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError) as error:
        raise GovernanceError("GOVERNANCE_JSON_INVALID") from error
    if not isinstance(value, dict) or _json(value) != raw:
        raise GovernanceError("GOVERNANCE_JSON_NONCANONICAL")
    return value


def _identity(value: dict[str, Any], *, id_field: str, hash_field: str, prefix: str) -> str:
    copied = dict(value)
    identifier = copied.pop(id_field, None)
    supplied = copied.pop(hash_field, None)
    expected = canonical_hash(copied)
    if supplied != expected or identifier != prefix + expected:
        raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
    return expected


def _verify_rows(conn: sqlite3.Connection) -> None:
    """Recompute every append-only identity before exposing or mutating state."""

    for row in conn.execute("SELECT * FROM proposals ORDER BY proposal_hash"):
        value = validate_campaign_proposal(_read_json(row["proposal_json"]))
        committed = proposal_commitment(value)
        if committed["proposal_hash"] != row["proposal_hash"] or committed["anti_reset_key"] != row["anti_reset_key"] or value["proposal_id"] != row["proposal_id"]:
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
        parse_utc(row["committed_at"], "committed_at")
    for row in conn.execute("SELECT * FROM campaigns ORDER BY campaign_id"):
        value = _read_json(row["admission_json"])
        if _identity(value, id_field="campaign_id", hash_field="campaign_hash", prefix="m103-campaign-") != row["campaign_hash"]:
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
        if value["campaign_id"] != row["campaign_id"] or value["proposal_hash"] != row["proposal_hash"]:
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
    for row in conn.execute("SELECT * FROM campaign_events ORDER BY campaign_id,sequence_number"):
        core = {key: row[key] for key in ("campaign_id", "sequence_number", "status", "reason_token", "event_at")}
        expected = canonical_hash(core)
        if row["event_hash"] != expected or row["event_id"] != f"m103-event-{expected}":
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
        parse_utc(row["event_at"], "event_at")
    for row in conn.execute("SELECT * FROM programs ORDER BY program_id"):
        value = _read_json(row["protocol_json"])
        supplied = value.pop("program_hash", None)
        expected = canonical_hash(value)
        if supplied != expected or row["program_hash"] != expected or value["program_id"] != row["program_id"] or value["campaign_id"] != row["campaign_id"]:
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
        parse_utc(row["created_at"], "created_at")
    for row in conn.execute("SELECT * FROM program_activations ORDER BY activation_id"):
        value = _read_json(row["activation_json"])
        if (
            _identity(value, id_field="activation_id", hash_field="activation_hash", prefix="m103-program-activation-") != row["activation_hash"]
            or value["campaign_id"] != row["campaign_id"]
            or value["program_id"] != row["program_id"]
            or value["proposal_hash"] != row["proposal_hash"]
            or value["program_hash"] != row["program_hash"]
            or value["founder_nonce_hex"] != row["nonce_hex"]
            or value["activated_at"] != row["activated_at"]
        ):
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
        parse_utc(row["activated_at"], "activated_at")
    for row in conn.execute("SELECT * FROM development_results ORDER BY result_id"):
        evidence = _read_json(row["evidence_json"])
        core = {"program_id": row["program_id"], "hypothesis_id": row["hypothesis_id"], "hypothesis_hash": row["hypothesis_hash"], "evidence": evidence, "recorded_at": row["recorded_at"]}
        expected = canonical_hash(core)
        if row["evidence_hash"] != expected or row["result_id"] != f"m103-development-result-{expected}" or evidence.get("terminal_status") != row["terminal_status"]:
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
    for row in conn.execute("SELECT * FROM candidates ORDER BY candidate_id"):
        value = _read_json(row["candidate_json"])
        if _identity(value, id_field="candidate_id", hash_field="candidate_hash", prefix="m103-candidate-") != row["candidate_hash"] or value["program_id"] != row["program_id"]:
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
    for row in conn.execute("SELECT * FROM materializations ORDER BY materialization_id"):
        value = _read_json(row["metadata_json"])
        materialization_id = value.pop("materialization_id", None)
        commitment = value.pop("metadata_commitment", None)
        verify_materialization_integrity(value)
        expected = canonical_hash({"program_id": row["program_id"], **value})
        if commitment != expected or materialization_id != f"m103-materialization-{expected}" or row["materialization_id"] != materialization_id or value["materialization_hash"] != row["materialization_hash"] or value["stage"] != row["stage"]:
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
    for row in conn.execute("SELECT * FROM stage_authorizations ORDER BY authorization_id"):
        value = _read_json(row["authorization_json"])
        if _identity(value, id_field="authorization_id", hash_field="authorization_hash", prefix="m103-stage-authorization-") != row["authorization_hash"] or value["program_id"] != row["program_id"] or value["stage"] != row["stage"]:
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
    for row in conn.execute("SELECT * FROM authorization_events ORDER BY authorization_id,sequence_number"):
        core = {key: row[key] for key in ("authorization_id", "sequence_number", "status", "reason_token", "event_at")}
        expected = canonical_hash(core)
        if row["event_hash"] != expected or row["event_id"] != f"m103-authorization-event-{expected}":
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
    for row in conn.execute("SELECT * FROM authorization_consumptions ORDER BY consumption_id"):
        core = {key: row[key] for key in ("authorization_id", "stage_execution_id", "consumed_at")}
        expected = canonical_hash(core)
        if row["consumption_hash"] != expected or row["consumption_id"] != f"m103-authorization-consumption-{expected}":
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
    for row in conn.execute("SELECT * FROM stage_executions ORDER BY stage_execution_id"):
        value = _read_json(row["execution_json"])
        if _identity(value, id_field="stage_execution_id", hash_field="execution_hash", prefix="m103-stage-execution-") != row["execution_hash"] or value["program_id"] != row["program_id"] or value["stage"] != row["stage"] or value["authorization_id"] != row["authorization_id"]:
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
    for row in conn.execute("SELECT * FROM stage_decisions ORDER BY decision_id"):
        value = _read_json(row["decision_json"])
        if _identity(value, id_field="decision_id", hash_field="decision_hash", prefix="m103-stage-decision-") != row["decision_hash"] or value["stage_execution_id"] != row["stage_execution_id"] or bool(row["passed"]) is not value["passed"]:
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")
    for row in conn.execute("SELECT * FROM final_artifacts ORDER BY artifact_id"):
        value = _read_json(row["artifact_json"])
        if _identity(value, id_field="artifact_id", hash_field="artifact_hash", prefix="m103-final-artifact-") != row["artifact_hash"] or value["program_id"] != row["program_id"]:
            raise GovernanceError("GOVERNANCE_ROW_INTEGRITY_INVALID")


def _event(conn: sqlite3.Connection, campaign_id: str, status: str, reason: str, event_at: str) -> dict[str, Any]:
    parse_utc(event_at, "event_at")
    row = conn.execute("SELECT sequence_number FROM campaign_events WHERE campaign_id=? ORDER BY sequence_number DESC LIMIT 1", (campaign_id,)).fetchone()
    sequence = 1 if row is None else int(row[0]) + 1
    core = {"campaign_id": campaign_id, "sequence_number": sequence, "status": status, "reason_token": reason, "event_at": event_at}
    digest = canonical_hash(core)
    conn.execute("INSERT INTO campaign_events VALUES(?,?,?,?,?,?,?)", (f"m103-event-{digest}", campaign_id, sequence, status, reason, event_at, digest))
    return core


def _latest_campaign_status(conn: sqlite3.Connection, campaign_id: str) -> str:
    row = conn.execute("SELECT status FROM campaign_events WHERE campaign_id=? ORDER BY sequence_number DESC LIMIT 1", (campaign_id,)).fetchone()
    if row is None:
        raise GovernanceError("CAMPAIGN_NOT_FOUND")
    return str(row[0])


def commit_campaign_proposal(root: str | Path, proposal: Mapping[str, Any]) -> dict[str, Any]:
    committed = proposal_commitment(proposal)
    now = trusted_utc_now()
    parse_utc(now, "committed_at")
    with connection(root) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO proposals VALUES(?,?,?,?,?)", (
                committed["proposal_hash"], committed["proposal"]["proposal_id"], committed["anti_reset_key"], _json(committed["proposal"]), now,
            ))
            conn.commit()
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise GovernanceError("CAMPAIGN_PROPOSAL_ALREADY_COMMITTED") from error
    return {key: committed[key] for key in ("proposal_commitment_id", "proposal_hash", "anti_reset_key")}


def admit_campaign(root: str | Path, *, proposal_hash: str, acknowledgement: str, validity_seconds: int = 86400) -> dict[str, Any]:
    if acknowledgement != ACK_ADMIT_CAMPAIGN:
        raise GovernanceError("FOUNDER_CAMPAIGN_ADMISSION_REQUIRED")
    require_hash(proposal_hash, "proposal_hash")
    if type(validity_seconds) is not int or not 1 <= validity_seconds <= 31_536_000:
        raise GovernanceError("CAMPAIGN_VALIDITY_INVALID")
    now = trusted_utc_now()
    issued = parse_utc(now, "issued_at")
    with connection(root) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM proposals WHERE proposal_hash=?", (proposal_hash,)).fetchone()
            if row is None:
                raise GovernanceError("CAMPAIGN_PROPOSAL_NOT_COMMITTED")
            proposal = validate_campaign_proposal(_read_json(row["proposal_json"]))
            if issued >= parse_utc(proposal["valid_until"], "valid_until"):
                raise GovernanceError("CAMPAIGN_PROPOSAL_EXPIRED")
            if proposal["parent_campaign_hash"] is not None:
                parent = conn.execute("SELECT 1 FROM campaigns WHERE campaign_hash=?", (proposal["parent_campaign_hash"],)).fetchone()
                if parent is None:
                    raise GovernanceError("CAMPAIGN_PARENT_NOT_FOUND")
            expires_at = (issued + timedelta(seconds=validity_seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            core = {
                "schema_version": "1.0", "proposal_hash": proposal_hash,
                "repository_commit": proposal["repository_commit"], "economic_lineage_id": proposal["economic_lineage_id"],
                "parent_campaign_hash": proposal["parent_campaign_hash"], "maximum_program_count": proposal["maximum_program_count"],
                "issuer_role": "FOUNDER", "issued_at": now, "expires_at": expires_at,
                "autonomy_contract_id": AUTONOMY_V5_ID,
                "autonomy_contract_hash": AUTONOMY_V5_HASH, "mission103_contract_id": MISSION103_ID,
                "mission103_contract_hash": MISSION103_HASH,
            }
            digest = canonical_hash(core)
            campaign_id = f"m103-campaign-{digest}"
            admission = {**core, "campaign_id": campaign_id, "campaign_hash": digest}
            conn.execute("INSERT INTO campaigns VALUES(?,?,?,?,?)", (campaign_id, digest, proposal_hash, row["anti_reset_key"], _json(admission)))
            _event(conn, campaign_id, "ADMITTED", "FOUNDER_CAMPAIGN_ADMISSION", now)
            conn.commit()
        except GovernanceError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise GovernanceError("CAMPAIGN_RESET_OR_REPROPOSAL_FORBIDDEN") from error
    return {key: admission[key] for key in ("campaign_id", "campaign_hash", "proposal_hash", "issued_at", "expires_at")}


def create_program(root: str | Path, *, campaign_id: str, protocol: Mapping[str, Any]) -> dict[str, Any]:
    require_identifier(campaign_id, "campaign_id")
    now = trusted_utc_now()
    with connection(root) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            campaign_row = conn.execute("SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
            if campaign_row is None:
                raise GovernanceError("CAMPAIGN_NOT_FOUND")
            if _latest_campaign_status(conn, campaign_id) != "ADMITTED":
                raise GovernanceError("CAMPAIGN_PROGRAM_ALREADY_FROZEN")
            campaign = _read_json(campaign_row["admission_json"])
            if parse_utc(now, "now") >= parse_utc(campaign["expires_at"], "expires_at"):
                raise GovernanceError("CAMPAIGN_EXPIRED")
            proposal_row = conn.execute("SELECT proposal_json FROM proposals WHERE proposal_hash=?", (campaign["proposal_hash"],)).fetchone()
            proposal = _read_json(proposal_row[0])
            validated = _validate_program_protocol_at(protocol, proposal=proposal, decision_time=now)
            count = int(conn.execute("SELECT COUNT(*) FROM programs WHERE campaign_id=?", (campaign_id,)).fetchone()[0])
            if count != 0 or campaign["maximum_program_count"] != 1:
                raise GovernanceError("CAMPAIGN_PROGRAM_CAPACITY_EXHAUSTED")
            core = {**validated, "campaign_id": campaign_id, "campaign_hash": campaign["campaign_hash"]}
            digest = canonical_hash(core)
            program_id = validated["program_id"]
            stored = {**core, "program_hash": digest}
            conn.execute("INSERT INTO programs VALUES(?,?,?,?,?)", (program_id, digest, campaign_id, _json(stored), now))
            _event(conn, campaign_id, "PROGRAM_FROZEN", "IMMUTABLE_PROGRAM_PROTOCOL", now)
            conn.commit()
        except GovernanceError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise GovernanceError("PROGRAM_ALREADY_EXISTS") from error
    return {"program_id": program_id, "program_hash": digest, "m": len(validated["hypotheses"]), "status": "PROGRAM_FROZEN"}


def activate_program(
    root: str | Path, *, campaign_id: str, program_id: str, acknowledgement: str,
) -> dict[str, Any]:
    """Founder-activate the already frozen exact program and generate its sole nonce."""

    if acknowledgement != ACK_ACTIVATE_PROGRAM:
        raise GovernanceError("FOUNDER_PROGRAM_ACTIVATION_REQUIRED")
    require_identifier(campaign_id, "campaign_id"); require_identifier(program_id, "program_id")
    now = trusted_utc_now()
    with connection(root) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            campaign_row = conn.execute("SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
            program_row = conn.execute("SELECT * FROM programs WHERE program_id=? AND campaign_id=?", (program_id, campaign_id)).fetchone()
            if campaign_row is None or program_row is None:
                raise GovernanceError("EXACT_CAMPAIGN_PROGRAM_REQUIRED")
            if _latest_campaign_status(conn, campaign_id) != "PROGRAM_FROZEN":
                raise GovernanceError("PROGRAM_ACTIVATION_STATE_INVALID")
            campaign = _read_json(campaign_row["admission_json"])
            if parse_utc(now, "activated_at") >= parse_utc(campaign["expires_at"], "expires_at"):
                raise GovernanceError("CAMPAIGN_EXPIRED")
            if int(conn.execute("SELECT COUNT(*) FROM programs WHERE campaign_id=?", (campaign_id,)).fetchone()[0]) != 1:
                raise GovernanceError("EXACTLY_ONE_PROGRAM_REQUIRED")
            if conn.execute("SELECT 1 FROM program_activations WHERE campaign_id=? OR program_id=?", (campaign_id, program_id)).fetchone():
                raise GovernanceError("PROGRAM_ALREADY_ACTIVATED")
            stored_program = _read_json(program_row["protocol_json"])
            protocol = dict(stored_program)
            for field in ("campaign_id", "campaign_hash", "program_hash"):
                protocol.pop(field, None)
            proposal = _read_json(conn.execute(
                "SELECT proposal_json FROM proposals WHERE proposal_hash=?", (campaign["proposal_hash"],)
            ).fetchone()[0])
            _validate_program_protocol_at(protocol, proposal=proposal, decision_time=now)
            # Secure entropy is sampled only after the complete immutable program
            # exists and every trusted activation-time gate has passed.
            nonce = secure_nonce()
            if type(nonce) is not bytes or len(nonce) != 32:
                raise GovernanceError("NONCE_ENTROPY_FAILURE")
            core = {"schema_version": "1.0", "issuer_role": "FOUNDER",
                "campaign_id": campaign_id, "campaign_hash": campaign["campaign_hash"],
                "proposal_hash": campaign["proposal_hash"], "program_id": program_id,
                "program_hash": stored_program["program_hash"], "founder_nonce_hex": nonce.hex(),
                "activated_at": now, "one_use_capacity": 1,
                "autonomy_contract_hash": AUTONOMY_V5_HASH, "mission103_contract_hash": MISSION103_HASH}
            digest = canonical_hash(core)
            activation_id = f"m103-program-activation-{digest}"
            activation = {**core, "activation_id": activation_id, "activation_hash": digest}
            conn.execute("INSERT INTO program_activations VALUES(?,?,?,?,?,?,?,?,?)", (
                activation_id, digest, campaign_id, program_id, campaign["proposal_hash"],
                stored_program["program_hash"], nonce.hex(), _json(activation), now,
            ))
            _event(conn, campaign_id, "PROGRAM_ACTIVATED", "FOUNDER_EXACT_PROGRAM_ACTIVATION", now)
            conn.commit()
        except GovernanceError:
            conn.rollback(); raise
        except sqlite3.IntegrityError as error:
            conn.rollback(); raise GovernanceError("PROGRAM_ALREADY_ACTIVATED") from error
    return {"activation_id": activation_id, "activation_hash": digest,
        "campaign_id": campaign_id, "program_id": program_id, "activated_at": now,
        "status": "PROGRAM_ACTIVATED"}


def _program_context(conn: sqlite3.Connection, program_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    row = conn.execute("SELECT * FROM programs WHERE program_id=?", (program_id,)).fetchone()
    if row is None:
        raise GovernanceError("PROGRAM_NOT_FOUND")
    program = _read_json(row["protocol_json"])
    campaign_row = conn.execute("SELECT admission_json FROM campaigns WHERE campaign_id=?", (row["campaign_id"],)).fetchone()
    campaign = _read_json(campaign_row[0])
    proposal_row = conn.execute("SELECT proposal_json FROM proposals WHERE proposal_hash=?", (campaign["proposal_hash"],)).fetchone()
    proposal = _read_json(proposal_row[0])
    return program, campaign, proposal


def _program_activation(conn: sqlite3.Connection, program: Mapping[str, Any]) -> dict[str, Any]:
    row = conn.execute("SELECT activation_json FROM program_activations WHERE program_id=?", (program["program_id"],)).fetchone()
    if row is None:
        raise GovernanceError("PROGRAM_ACTIVATION_REQUIRED")
    activation = _read_json(row[0])
    if activation["program_hash"] != program["program_hash"]:
        raise GovernanceError("PROGRAM_ACTIVATION_BINDING_MISMATCH")
    return activation


def record_development_result(
    root: str | Path, *, program_id: str, hypothesis_id: str,
    result_source: M102ResultSource,
) -> dict[str, Any]:
    require_identifier(program_id, "program_id")
    require_identifier(hypothesis_id, "hypothesis_id")
    now = trusted_utc_now()
    with connection(root) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            program, campaign, _proposal = _program_context(conn, program_id)
            activation = _program_activation(conn, program)
            if _latest_campaign_status(conn, campaign["campaign_id"]) not in {"PROGRAM_ACTIVATED", "DEVELOPMENT_RESULTS_PARTIAL"}:
                raise GovernanceError("DEVELOPMENT_RESULT_STATE_INVALID")
            matches = [item for item in program["hypotheses"] if item["hypothesis_id"] == hypothesis_id]
            if len(matches) != 1:
                raise GovernanceError("UNDECLARED_DEVELOPMENT_RESULT")
            declared = matches[0]
            verified = verify_development_binding(declared, _verify_terminal_m102_source(result_source))
            terminal_status = verified["terminal_status"]
            proposal_time = parse_utc(conn.execute("SELECT committed_at FROM proposals WHERE proposal_hash=?", (campaign["proposal_hash"],)).fetchone()[0], "proposal_committed_at")
            admitted_time = parse_utc(campaign["issued_at"], "campaign_admitted_at")
            frozen_time = parse_utc(conn.execute("SELECT created_at FROM programs WHERE program_id=?", (program_id,)).fetchone()[0], "program_frozen_at")
            activated_time = parse_utc(activation["activated_at"], "program_activated_at")
            authority_time = parse_utc(verified["authority_decision_time"], "authority_decision_time")
            terminal_field = "completion_event_timestamp" if terminal_status == "SUCCESS" else "failure_timestamp"
            terminal_time = parse_utc(verified[terminal_field], terminal_field)
            if not proposal_time <= admitted_time <= frozen_time <= activated_time <= authority_time <= terminal_time:
                raise GovernanceError("DEVELOPMENT_CHRONOLOGY_INVALID")
            if terminal_status == "SUCCESS":
                if verified["result_linked_at"] != verified["completion_event_timestamp"]:
                    raise GovernanceError("DEVELOPMENT_CHRONOLOGY_INVALID")
                seed = derive_null_seed(
                    founder_nonce_hex=activation["founder_nonce_hex"], proposal_hash=campaign["proposal_hash"],
                    program_hash=program["program_hash"], hypothesis_hash=declared["hypothesis_hash"],
                    family_hash=declared["family_hash"], variant_hash=declared["variant_hash"],
                    adapter_hash=declared["statistical_adapter_hash"],
                    prng_algorithm_version=program["prng_algorithm_version"],
                )
                adapter = _resolve_statistical_adapter(declared["statistical_adapter_id"], declared["statistical_adapter_hash"])
                algorithm = dict(adapter.definition["null_algorithm"])
                if algorithm["algorithm_id"] != program["null_policy"]["algorithm"]:
                    raise GovernanceError("NULL_ALGORITHM_BINDING_MISMATCH")
                plan_commitment = None
                enumeration_commitment = None
                if program["null_policy"]["kind"] == "EMPIRICAL_MONTE_CARLO":
                    if algorithm["kind"] != "M103_SHA256_COUNTER_ORDINAL_PLAN_V1":
                        raise GovernanceError("NULL_ALGORITHM_BINDING_MISMATCH")
                    plan = build_randomization_plan(seed, program["null_repetitions"])
                    plan_commitment = plan["plan_commitment"]
                    null_input = {"randomization_plan": plan}
                else:
                    if algorithm["kind"] != "PREREGISTERED_EXACT_ENUMERATION_V1":
                        raise GovernanceError("NULL_ALGORITHM_BINDING_MISMATCH")
                    enumeration_core = {"algorithm_id": algorithm["algorithm_id"],
                        "configurations": algorithm["configurations"],
                        "observed_configuration_id": algorithm["observed_configuration_id"]}
                    enumeration_commitment = canonical_hash(enumeration_core)
                    null_input = {"enumeration_space": {**enumeration_core,
                        "enumeration_commitment": enumeration_commitment}}
                adapter_input = {"input_schema": "DELTAGRID_M103_STATISTICAL_INPUT_V1",
                    "verified_result": verified, "primary_statistic": program["primary_statistic"],
                    "direction": program["direction"], "null_policy": program["null_policy"],
                    **null_input}
                try:
                    output = freeze_json(dict(adapter.function(adapter_input)))
                except GovernanceError:
                    raise
                except Exception as error:
                    raise GovernanceError("STATISTICAL_ADAPTER_FAILURE") from error
                if set(output) != {"null_evidence", "measurements", "measurement_evidence_hash"}:
                    raise GovernanceError("STATISTICAL_ADAPTER_OUTPUT_INVALID")
                null = output["null_evidence"]
                measurements = output["measurements"]
                if not isinstance(null, dict) or not isinstance(measurements, dict):
                    raise GovernanceError("STATISTICAL_ADAPTER_OUTPUT_INVALID")
                expected_measurements = ({program["primary_statistic"]}
                    | {gate["measurement_id"] for gate in program["hard_gates"]}
                    | set(program["ranking_measurements"]))
                if set(measurements) != expected_measurements or output["measurement_evidence_hash"] != canonical_hash(measurements):
                    raise GovernanceError("STATISTICAL_MEASUREMENT_EVIDENCE_INVALID")
                primary_value = require_decimal_text(measurements[program["primary_statistic"]], program["primary_statistic"])
                observed = require_decimal_text(null.get("observed_statistic"), "observed_statistic")
                if observed != primary_value:
                    raise GovernanceError("PRIMARY_STATISTIC_BINDING_MISMATCH")
                ranking = []
                for identifier in program["ranking_measurements"]:
                    value = measurements[identifier]
                    if type(value) is not str: raise GovernanceError("STATISTICAL_ADAPTER_OUTPUT_INVALID")
                    try: parsed = Decimal(value)
                    except Exception as error: raise GovernanceError("STATISTICAL_ADAPTER_OUTPUT_INVALID") from error
                    if not parsed.is_finite(): raise GovernanceError("STATISTICAL_ADAPTER_OUTPUT_INVALID")
                    ranking.append(value)
                require_hash(output["measurement_evidence_hash"], "measurement_evidence_hash")
                if program["null_policy"]["kind"] == "EMPIRICAL_MONTE_CARLO":
                    if set(null) != {"kind", "plan_commitment", "observed_statistic", "results", "evidence_commitment"} or null["kind"] != "EMPIRICAL_PLAN_RESULTS_V1" or null["plan_commitment"] != plan_commitment or not isinstance(null["results"], list) or len(null["results"]) != program["null_repetitions"]:
                        raise GovernanceError("EMPIRICAL_NULL_EVIDENCE_INVALID")
                    outcomes = []
                    for expected_entry, result in zip(plan["entries"], null["results"], strict=True):
                        if not isinstance(result, dict) or set(result) != {"ordinal", "draw_u256_hex", "statistic"} or result["ordinal"] != expected_entry["ordinal"] or result["draw_u256_hex"] != expected_entry["draw_u256_hex"]:
                            raise GovernanceError("RANDOMIZATION_PLAN_TRANSCRIPT_MISMATCH")
                        outcomes.append(require_decimal_text(result["statistic"], "null_statistic"))
                    favorable = sum(value >= observed for value in outcomes) if program["direction"] == "GREATER" else sum(value <= observed for value in outcomes)
                    raw_p = Fraction(1 + favorable, len(outcomes) + 1)
                else:
                    if set(null) != {"kind", "enumeration_commitment", "observed_statistic", "results", "evidence_commitment"} or null["kind"] != "EXACT_ENUMERATION_RESULTS_V1" or null["enumeration_commitment"] != enumeration_commitment or not isinstance(null["results"], list):
                        raise GovernanceError("EXACT_NULL_EVIDENCE_INVALID")
                    expected_ids = [item["configuration_id"] for item in algorithm["configurations"]]
                    result_ids = [item.get("configuration_id") for item in null["results"] if isinstance(item, dict)]
                    if result_ids != expected_ids or any(set(item) != {"configuration_id", "statistic"} for item in null["results"]):
                        raise GovernanceError("EXACT_ENUMERATION_SPACE_SUBSTITUTION")
                    outcomes = [require_decimal_text(item["statistic"], "null_statistic") for item in null["results"]]
                    observed_index = expected_ids.index(algorithm["observed_configuration_id"])
                    if outcomes[observed_index] != observed:
                        raise GovernanceError("EXACT_OBSERVED_CONFIGURATION_MISMATCH")
                    favorable = sum(value >= observed for value in outcomes) if program["direction"] == "GREATER" else sum(value <= observed for value in outcomes)
                    if favorable < 1: raise GovernanceError("EXACT_OBSERVED_CONFIGURATION_MISSING")
                    raw_p = Fraction(favorable, len(outcomes))
                null_core = dict(null); commitment = null_core.pop("evidence_commitment")
                if commitment != canonical_hash(null_core): raise GovernanceError("NULL_EVIDENCE_COMMITMENT_INVALID")
                gates = apply_measurement_gates(
                    {gate["measurement_id"]: measurements[gate["measurement_id"]] for gate in program["hard_gates"]},
                    program["hard_gates"],
                )
                evidence = {"terminal_status": terminal_status, "verified_result_hash": canonical_hash(verified),
                    "program_activation_timestamp": activation["activated_at"],
                    "m102_authority_decision_time": verified["authority_decision_time"],
                    "m94_completion_event_timestamp": verified["completion_event_timestamp"],
                    "m94_result_linked_at": verified["result_linked_at"],
                    "final_result_identity": {"result_bundle_id": verified["result_bundle_id"],
                        "result_hash": verified["result_hash"], "m94_result_link_hash": verified["result_link_hash"],
                        "execution_spec_id": verified["execution_spec_id"],
                        "execution_spec_hash": verified["execution_spec_hash"]},
                    "raw_p_value": fraction_text(raw_p), "hard_gates": gates, "ranking_vector": ranking,
                    "primary_statistic_value": measurements[program["primary_statistic"]],
                    "null_evidence": null, "null_evidence_commitment": commitment,
                    "randomization_plan_commitment": plan_commitment,
                    "enumeration_commitment": enumeration_commitment,
                    "measurement_evidence_hash": output["measurement_evidence_hash"]}
            else:
                evidence = {"terminal_status": terminal_status, "verified_terminal_evidence_hash": canonical_hash(verified),
                    "program_activation_timestamp": activation["activated_at"],
                    "m102_authority_decision_time": verified["authority_decision_time"],
                    "m94_failure_timestamp": verified["failure_timestamp"],
                    "claimed_execution_spec_id": verified["execution_spec_id"],
                    "claimed_execution_spec_hash": verified["execution_spec_hash"],
                    "raw_p_value": "1",
                    "hard_gates": {gate["measurement_id"]: False for gate in program["hard_gates"]},
                    "ranking_vector": [], "measurement_evidence_hash": canonical_hash({"terminal_status": terminal_status, "hypothesis_hash": declared["hypothesis_hash"]})}
            core = {"program_id": program_id, "hypothesis_id": hypothesis_id, "hypothesis_hash": declared["hypothesis_hash"], "evidence": evidence, "recorded_at": now}
            digest = canonical_hash(core)
            conn.execute("INSERT INTO development_results VALUES(?,?,?,?,?,?,?,?)", (f"m103-development-result-{digest}", program_id, hypothesis_id, declared["hypothesis_hash"], terminal_status, _json(evidence), digest, now))
            count = int(conn.execute("SELECT COUNT(*) FROM development_results WHERE program_id=?", (program_id,)).fetchone()[0])
            if count < len(program["hypotheses"]):
                _event(conn, campaign["campaign_id"], "DEVELOPMENT_RESULTS_PARTIAL", "DECLARED_HYPOTHESIS_TERMINAL", now)
            else:
                _event(conn, campaign["campaign_id"], "DEVELOPMENT_RESULTS_COMPLETE", "ALL_DECLARED_HYPOTHESES_TERMINAL", now)
            conn.commit()
        except GovernanceError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise GovernanceError("DEVELOPMENT_RESULT_ALREADY_TERMINAL") from error
    return {"hypothesis_id": hypothesis_id, "terminal_status": terminal_status, "evidence_hash": digest}


def qualify_development(root: str | Path, *, program_id: str) -> dict[str, Any]:
    now = trusted_utc_now()
    with connection(root) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            program, campaign, _proposal = _program_context(conn, program_id)
            if _latest_campaign_status(conn, campaign["campaign_id"]) != "DEVELOPMENT_RESULTS_COMPLETE":
                raise GovernanceError("ALL_HYPOTHESES_NOT_TERMINAL")
            rows = list(conn.execute("SELECT * FROM development_results WHERE program_id=? ORDER BY hypothesis_id", (program_id,)))
            if len(rows) != len(program["hypotheses"]):
                raise GovernanceError("ALL_HYPOTHESES_NOT_TERMINAL")
            evidence = {row["hypothesis_id"]: _read_json(row["evidence_json"]) for row in rows}
            evidence_hashes = {row["hypothesis_id"]: row["evidence_hash"] for row in rows}
            holm = holm_step_down({key: value["raw_p_value"] for key, value in evidence.items()}, alpha=program["alpha"])
            holm_by_id = {row["hypothesis_id"]: row for row in holm["ordered_evidence"]}
            eligible = [
                hypothesis for hypothesis in program["hypotheses"]
                if all(evidence[hypothesis["hypothesis_id"]]["hard_gates"].values())
                and holm_by_id[hypothesis["hypothesis_id"]]["rejected"]
            ]
            if not eligible:
                _event(conn, campaign["campaign_id"], "PROGRAM_REJECTED", "NO_DEVELOPMENT_HYPOTHESIS_QUALIFIED", now)
                conn.commit()
                return {"program_id": program_id, "status": "PROGRAM_REJECTED", "qualified_count": 0, "holm_hash": holm["canonical_holm_hash"], "candidate": None}
            eligible.sort(key=lambda item: (
                tuple(Decimal(value) for value in evidence[item["hypothesis_id"]]["ranking_vector"]),
                item["hypothesis_hash"],
            ))
            selected = eligible[0]
            hypothesis_id = selected["hypothesis_id"]
            candidate_core = {
                "schema_version": "1.0", "campaign_id": campaign["campaign_id"], "campaign_hash": campaign["campaign_hash"],
                "program_id": program_id, "program_hash": program["program_hash"], "repository_commit": program["repository_commit"],
                "hypothesis_id": hypothesis_id, "hypothesis_hash": selected["hypothesis_hash"], "family_id": selected["economic_family_id"],
                "family_hash": selected["family_hash"], "variant_id": selected["variant_id"], "variant_hash": selected["variant_hash"],
                "parameters": selected["parameters"],
                "m94": {**selected["m94"], "result_link_hash": evidence[hypothesis_id]["final_result_identity"]["m94_result_link_hash"]},
                "m101": selected["m101"],
                "m102": {**selected["m102"], "result_bundle_id": evidence[hypothesis_id]["final_result_identity"]["result_bundle_id"],
                    "result_hash": evidence[hypothesis_id]["final_result_identity"]["result_hash"],
                    "execution_spec_id": evidence[hypothesis_id]["final_result_identity"]["execution_spec_id"],
                    "execution_spec_hash": evidence[hypothesis_id]["final_result_identity"]["execution_spec_hash"]},
                "statistical_adapter_id": selected["statistical_adapter_id"], "statistical_adapter_hash": selected["statistical_adapter_hash"],
                "development_result_evidence_hash": evidence_hashes[hypothesis_id],
                "verified_result_hash": evidence[hypothesis_id]["verified_result_hash"],
                "measurement_evidence_hash": evidence[hypothesis_id]["measurement_evidence_hash"],
                "primary_statistic": program["primary_statistic"],
                "primary_statistic_value": evidence[hypothesis_id]["primary_statistic_value"],
                "null_evidence_commitment": evidence[hypothesis_id]["null_evidence_commitment"],
                "randomization_plan_commitment": evidence[hypothesis_id]["randomization_plan_commitment"],
                "enumeration_commitment": evidence[hypothesis_id]["enumeration_commitment"],
                "raw_p_value": evidence[hypothesis_id]["raw_p_value"],
                "holm_evidence": holm_by_id[hypothesis_id], "holm_hash": holm["canonical_holm_hash"],
                "hard_gate_evidence": evidence[hypothesis_id]["hard_gates"], "ranking_evidence": evidence[hypothesis_id]["ranking_vector"],
                "cost_execution_identity": selected["execution_hash"], "execution_hash": selected["execution_hash"],
                "execution_id": selected["execution_id"],
                "risk_id": selected["risk_id"], "risk_identity": selected["risk_hash"],
                "no_second_best_fallback": True,
            }
            candidate_hash = canonical_hash(candidate_core)
            candidate_id = f"m103-candidate-{candidate_hash}"
            candidate = {**candidate_core, "candidate_id": candidate_id, "candidate_hash": candidate_hash}
            conn.execute("INSERT INTO candidates VALUES(?,?,?,?,?)", (candidate_id, candidate_hash, program_id, _json(candidate), now))
            _event(conn, campaign["campaign_id"], "DEVELOPMENT_QUALIFIED", "ONE_FIXED_CANDIDATE_SELECTED", now)
            _event(conn, campaign["campaign_id"], "REPLICATION_ELIGIBLE", "FOUNDER_AUTHORIZATION_REQUIRED", now)
            conn.commit()
            return {"program_id": program_id, "status": "REPLICATION_ELIGIBLE", "qualified_count": len(eligible), "holm_hash": holm["canonical_holm_hash"], "candidate": {"candidate_id": candidate_id, "candidate_hash": candidate_hash}}
        except GovernanceError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise GovernanceError("DEVELOPMENT_ALREADY_QUALIFIED") from error


def derive_program_null_seed(root: str | Path, *, program_id: str, hypothesis_id: str) -> int:
    with connection(root, readonly=True) as conn:
        program, campaign, _proposal = _program_context(conn, program_id)
        matches = [item for item in program["hypotheses"] if item["hypothesis_id"] == hypothesis_id]
        if len(matches) != 1:
            raise GovernanceError("HYPOTHESIS_NOT_FOUND")
        hypothesis = matches[0]
        activation = _program_activation(conn, program)
        return derive_null_seed(
            founder_nonce_hex=activation["founder_nonce_hex"], proposal_hash=campaign["proposal_hash"],
            program_hash=program["program_hash"], hypothesis_hash=hypothesis["hypothesis_hash"],
            family_hash=hypothesis["family_hash"], variant_hash=hypothesis["variant_hash"],
            adapter_hash=hypothesis["statistical_adapter_hash"], prng_algorithm_version=program["prng_algorithm_version"],
        )


def register_materialization(
    root: str | Path, *, program_id: str, stage: str, source: ProtectedCustodySource,
) -> dict[str, Any]:
    """Recertify custody and bind internally derived context/scored sets."""

    if stage not in STAGES:
        raise GovernanceError("PROTECTED_STAGE_INVALID")
    now = trusted_utc_now()
    with connection(root) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            program, _campaign, _proposal = _program_context(conn, program_id)
            spec = validate_partition_spec(program["protected_partition_specs"][STAGES.index(stage)])
            current = parse_utc(now, "now")
            if int(current.timestamp() * 1000) <= spec["scoring_end"] or current <= parse_utc(spec["availability_cutoff"], "availability_cutoff"):
                raise GovernanceError("PROTECTED_WINDOW_NOT_CLOSED")
            value = _materialize_verified_custody(source, spec, program["protected_custody_policy"])
            if not spec["minimum_samples"] <= value["scored_count"] <= spec["maximum_samples"]:
                raise GovernanceError("MATERIALIZATION_SPECIFICATION_MISMATCH")
            for prior_stage in STAGES[: STAGES.index(stage)]:
                prior = conn.execute("SELECT metadata_json FROM materializations WHERE program_id=? AND stage=?", (program_id, prior_stage)).fetchone()
                if prior is None:
                    raise GovernanceError("PRIOR_MATERIALIZATION_REQUIRED")
                previous = _read_json(prior[0])
                if set(previous["scored_record_hashes"]) & set(value["scored_record_hashes"]):
                    raise GovernanceError("PROTECTED_PARTITIONS_NOT_DISJOINT")
            if (
                len(set(value["context_record_hashes"])) != len(value["context_record_hashes"])
                or len(set(value["scored_record_hashes"])) != len(value["scored_record_hashes"])
                or set(value["context_record_hashes"]) & set(value["scored_record_hashes"])
            ):
                raise GovernanceError("PROTECTED_RECORD_PARTITION_INVALID")
            core = {"program_id": program_id, **value}
            identity = canonical_hash(core)
            materialization_id = f"m103-materialization-{identity}"
            stored = {**value, "materialization_id": materialization_id, "metadata_commitment": identity}
            conn.execute("INSERT INTO materializations VALUES(?,?,?,?,?,?)", (materialization_id, value["materialization_hash"], program_id, stage, _json(stored), now))
            conn.commit()
        except GovernanceError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise GovernanceError("MATERIALIZATION_ALREADY_BOUND") from error
    return {"materialization_id": materialization_id, "materialization_hash": value["materialization_hash"],
            "context_record_set_hash": value["context_record_set_hash"],
            "scored_record_set_hash": value["scored_record_set_hash"],
            "stage": stage, "status": "MATERIALIZED_METADATA_ONLY"}


def authorize_stage(
    root: str | Path, *, program_id: str, stage: str,
    acknowledgement: str, validity_seconds: int = 3600,
) -> dict[str, Any]:
    if acknowledgement != ACK_AUTHORIZE_STAGE:
        raise GovernanceError("FOUNDER_STAGE_AUTHORIZATION_REQUIRED")
    if stage not in STAGES:
        raise GovernanceError("PROTECTED_STAGE_INVALID")
    if type(validity_seconds) is not int or not 1 <= validity_seconds <= 86400:
        raise GovernanceError("AUTHORIZATION_VALIDITY_INVALID")
    now = trusted_utc_now()
    issued = parse_utc(now, "issued_at")
    expires = (issued + timedelta(seconds=validity_seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    with connection(root) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            program, campaign, _proposal = _program_context(conn, program_id)
            engine = program["protected_engines"][stage]
            if engine["executor_id"] != PROTECTED_EXECUTOR_ID:
                raise GovernanceError("PROTECTED_ENGINE_BINDING_MISMATCH")
            evaluator_id = engine["evaluator_id"]
            evaluator_hash = engine["evaluator_hash"]
            _resolve_protected_evaluator(evaluator_id, evaluator_hash)
            expected_status = f"{stage}_ELIGIBLE"
            if _latest_campaign_status(conn, campaign["campaign_id"]) != expected_status:
                raise GovernanceError("STAGE_NOT_ELIGIBLE")
            candidate_row = conn.execute("SELECT candidate_json FROM candidates WHERE program_id=?", (program_id,)).fetchone()
            materialization_row = conn.execute("SELECT * FROM materializations WHERE program_id=? AND stage=?", (program_id, stage)).fetchone()
            if candidate_row is None or materialization_row is None:
                raise GovernanceError("STAGE_EXACT_BINDINGS_MISSING")
            candidate = _read_json(candidate_row[0])
            materialization = _read_json(materialization_row["metadata_json"])
            validate_candidate_observable_scope(candidate, materialization)
            spec = validate_partition_spec(program["protected_partition_specs"][STAGES.index(stage)])
            previous_stage = STAGES[STAGES.index(stage) - 1] if stage != "REPLICATION" else None
            previous_decision_hash = None
            if previous_stage:
                prior = conn.execute("SELECT decision_hash,passed FROM stage_decisions WHERE program_id=? AND stage=?", (program_id, previous_stage)).fetchone()
                if prior is None or int(prior["passed"]) != 1:
                    raise GovernanceError("PREVIOUS_STAGE_PASS_REQUIRED")
                previous_decision_hash = prior["decision_hash"]
            core = {
                "schema_version": "1.0", "issuer_role": "FOUNDER", "campaign_id": campaign["campaign_id"],
                "campaign_hash": campaign["campaign_hash"], "program_id": program_id, "program_hash": program["program_hash"],
                "candidate_id": candidate["candidate_id"], "candidate_hash": candidate["candidate_hash"], "stage": stage,
                "specification_hash": spec["specification_hash"], "materialization_id": materialization_row["materialization_id"],
                "materialization_hash": materialization_row["materialization_hash"], "repository_commit": program["repository_commit"],
                "evaluator_id": evaluator_id, "evaluator_hash": evaluator_hash, "previous_stage_decision_hash": previous_decision_hash,
                "one_use_capacity": 1, "issued_at": now, "expires_at": expires,
                "autonomy_contract_hash": AUTONOMY_V5_HASH, "mission103_contract_hash": MISSION103_HASH,
            }
            digest = canonical_hash(core)
            authorization_id = f"m103-stage-authorization-{digest}"
            authorization = {**core, "authorization_id": authorization_id, "authorization_hash": digest}
            conn.execute("INSERT INTO stage_authorizations VALUES(?,?,?,?,?)", (authorization_id, digest, program_id, stage, _json(authorization)))
            event_core = {"authorization_id": authorization_id, "sequence_number": 1, "status": "ISSUED", "reason_token": "FOUNDER_EXACT_ONE_USE_STAGE_AUTHORIZATION", "event_at": now}
            event_hash = canonical_hash(event_core)
            conn.execute("INSERT INTO authorization_events VALUES(?,?,?,?,?,?,?)", (f"m103-authorization-event-{event_hash}", authorization_id, 1, "ISSUED", event_core["reason_token"], now, event_hash))
            conn.commit()
        except GovernanceError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise GovernanceError("STAGE_AUTHORIZATION_ALREADY_EXISTS") from error
    return {"authorization_id": authorization_id, "authorization_hash": digest, "stage": stage, "expires_at": expires, "one_use_capacity": 1}


def revoke_stage_authorization(root: str | Path, *, authorization_id: str, acknowledgement: str) -> dict[str, Any]:
    if acknowledgement != ACK_REVOKE_STAGE:
        raise GovernanceError("FOUNDER_STAGE_REVOCATION_REQUIRED")
    now = trusted_utc_now()
    with connection(root) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT authorization_id FROM stage_authorizations WHERE authorization_id=?", (authorization_id,)).fetchone()
            if row is None:
                raise GovernanceError("STAGE_AUTHORIZATION_NOT_FOUND")
            if conn.execute("SELECT 1 FROM authorization_consumptions WHERE authorization_id=?", (authorization_id,)).fetchone():
                raise GovernanceError("CONSUMED_AUTHORIZATION_CANNOT_BE_REVOKED")
            sequence = int(conn.execute("SELECT MAX(sequence_number) FROM authorization_events WHERE authorization_id=?", (authorization_id,)).fetchone()[0]) + 1
            core = {"authorization_id": authorization_id, "sequence_number": sequence, "status": "REVOKED", "reason_token": "FOUNDER_REVOCATION", "event_at": now}
            digest = canonical_hash(core)
            conn.execute("INSERT INTO authorization_events VALUES(?,?,?,?,?,?,?)", (f"m103-authorization-event-{digest}", authorization_id, sequence, "REVOKED", "FOUNDER_REVOCATION", now, digest))
            conn.commit()
        except GovernanceError:
            conn.rollback()
            raise
    return {"authorization_id": authorization_id, "status": "REVOKED"}


def _stage_execution_core(conn: sqlite3.Connection, authorization: Mapping[str, Any], program: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    stage = authorization["stage"]
    rule = program["protected_acceptance_rules"][stage]
    materialization = _read_json(conn.execute(
        "SELECT metadata_json FROM materializations WHERE materialization_id=?",
        (authorization["materialization_id"],),
    ).fetchone()[0])
    return {
        "campaign_id": authorization["campaign_id"], "campaign_hash": authorization["campaign_hash"],
        "program_id": authorization["program_id"], "program_hash": authorization["program_hash"],
        "candidate_id": candidate["candidate_id"], "candidate_hash": candidate["candidate_hash"],
        "stage": stage, "repository_commit": program["repository_commit"],
        "authorization_id": authorization["authorization_id"], "authorization_hash": authorization["authorization_hash"],
        "evaluator_id": authorization["evaluator_id"], "evaluator_hash": authorization["evaluator_hash"],
        "specification_hash": authorization["specification_hash"], "materialization_id": authorization["materialization_id"],
        "materialization_hash": authorization["materialization_hash"], "protocol_hash": program["program_hash"],
        "acceptance_rule_hash": canonical_hash(rule), "input_commitment": authorization["materialization_hash"],
        "context_record_set_hash": materialization["context_record_set_hash"],
        "scored_record_set_hash": materialization["scored_record_set_hash"],
        "ordered_context_hash": materialization["ordered_context_hash"],
        "ordered_scored_hash": materialization["ordered_scored_hash"],
        "candidate_execution_hash": candidate["execution_hash"],
        "deterministic_randomness": "NONE_UNLESS_PROTOCOL_BOUND", "protected_start_state": "FLAT_CASH",
    }


def open_protected_stage(
    root: str | Path, *, authorization_id: str, crash_point: str | None = None,
) -> dict[str, Any]:
    """Commit OPENED and consume capacity before invoking the protected value loader."""

    require_identifier(authorization_id, "authorization_id")
    if crash_point not in {None, "BEFORE_OPENED_COMMIT", "AFTER_OPENED_COMMIT"}:
        raise GovernanceError("CRASH_POINT_INVALID")
    now = trusted_utc_now()
    with connection(root) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            auth_row = conn.execute("SELECT authorization_json FROM stage_authorizations WHERE authorization_id=?", (authorization_id,)).fetchone()
            if auth_row is None:
                raise GovernanceError("STAGE_AUTHORIZATION_NOT_FOUND")
            authorization = _read_json(auth_row[0])
            program, campaign, _proposal = _program_context(conn, authorization["program_id"])
            candidate = _read_json(conn.execute("SELECT candidate_json FROM candidates WHERE program_id=?", (authorization["program_id"],)).fetchone()[0])
            materialization_row = conn.execute(
                "SELECT metadata_json FROM materializations WHERE materialization_id=?",
                (authorization["materialization_id"],),
            ).fetchone()
            if materialization_row is None:
                raise GovernanceError("STAGE_EXACT_BINDINGS_MISSING")
            validate_candidate_observable_scope(candidate, _read_json(materialization_row[0]))
            _verify_repository_context(program["repository_commit"])
            if _latest_campaign_status(conn, campaign["campaign_id"]) != f"{authorization['stage']}_ELIGIBLE":
                raise GovernanceError("STAGE_NOT_ELIGIBLE")
            latest = conn.execute("SELECT status FROM authorization_events WHERE authorization_id=? ORDER BY sequence_number DESC LIMIT 1", (authorization_id,)).fetchone()
            if latest is None or latest[0] != "ISSUED":
                raise GovernanceError("STAGE_AUTHORIZATION_REVOKED")
            if parse_utc(now, "now") >= parse_utc(authorization["expires_at"], "expires_at"):
                raise GovernanceError("STAGE_AUTHORIZATION_EXPIRED")
            _resolve_protected_evaluator(authorization["evaluator_id"], authorization["evaluator_hash"])
            if conn.execute("SELECT 1 FROM authorization_consumptions WHERE authorization_id=?", (authorization_id,)).fetchone():
                raise GovernanceError("STAGE_AUTHORIZATION_CONSUMED")
            execution_core = _stage_execution_core(conn, authorization, program, candidate)
            execution_hash = canonical_hash(execution_core)
            execution_id = f"m103-stage-execution-{execution_hash}"
            execution = {**execution_core, "stage_execution_id": execution_id, "execution_hash": execution_hash}
            consumption_core = {"authorization_id": authorization_id, "stage_execution_id": execution_id, "consumed_at": now}
            consumption_hash = canonical_hash(consumption_core)
            conn.execute("INSERT INTO authorization_consumptions VALUES(?,?,?,?,?)", (f"m103-authorization-consumption-{consumption_hash}", authorization_id, execution_id, now, consumption_hash))
            conn.execute("INSERT INTO stage_executions VALUES(?,?,?,?,?,?,?)", (execution_id, execution_hash, authorization["program_id"], authorization["stage"], authorization_id, _json(execution), now))
            _event(conn, campaign["campaign_id"], f"{authorization['stage']}_OPENED", "DURABLE_ONE_USE_OPENING", now)
            if crash_point == "BEFORE_OPENED_COMMIT":
                raise GovernanceError("INJECTED_CRASH_BEFORE_OPENED_COMMIT")
            conn.commit()
        except GovernanceError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise GovernanceError("PROTECTED_STAGE_ALREADY_OPENED") from error
    if crash_point == "AFTER_OPENED_COMMIT":
        raise GovernanceError("INJECTED_CRASH_AFTER_OPENED_COMMIT")
    return _evaluate_opened(root, execution_id=execution_id)


def recover_protected_stage(
    root: str | Path, *, stage_execution_id: str, expected_execution_hash: str,
) -> dict[str, Any]:
    require_identifier(stage_execution_id, "stage_execution_id")
    require_hash(expected_execution_hash, "expected_execution_hash")
    with connection(root, readonly=True) as conn:
        row = conn.execute("SELECT execution_hash FROM stage_executions WHERE stage_execution_id=?", (stage_execution_id,)).fetchone()
        if row is None or row["execution_hash"] != expected_execution_hash:
            raise GovernanceError("EXACT_STAGE_RECOVERY_IDENTITY_REQUIRED")
        existing = conn.execute("SELECT decision_json FROM stage_decisions WHERE stage_execution_id=?", (stage_execution_id,)).fetchone()
        if existing is not None:
            decision = _read_json(existing[0])
            return {"stage_execution_id": stage_execution_id, "stage": decision["stage"], "status": decision["status"], "recovered": True}
    return _evaluate_opened(root, execution_id=stage_execution_id, recovered=True)


def _measure_deterministically(evaluator: Any, evaluator_input: Mapping[str, Any]) -> dict[str, Any]:
    try:
        first = freeze_json(dict(evaluator.function(evaluator_input)))
        second = freeze_json(dict(evaluator.function(evaluator_input)))
    except GovernanceError:
        raise
    except Exception as error:
        raise GovernanceError("PROTECTED_EVALUATOR_FAILURE") from error
    if first != second:
        raise GovernanceError("NONDETERMINISTIC_PROTECTED_MEASUREMENT")
    return first


def _evaluate_opened(
    root: str | Path, *, execution_id: str, recovered: bool = False,
) -> dict[str, Any]:
    with connection(root, readonly=True) as conn:
        row = conn.execute("SELECT execution_json FROM stage_executions WHERE stage_execution_id=?", (execution_id,)).fetchone()
        if row is None:
            raise GovernanceError("DURABLE_OPENING_REQUIRED")
        execution = _read_json(row[0])
        _verify_repository_context(execution["repository_commit"])
        evaluator = _resolve_protected_evaluator(execution["evaluator_id"], execution["evaluator_hash"])
        candidate_row = conn.execute("SELECT candidate_json FROM candidates WHERE program_id=?", (execution["program_id"],)).fetchone()
        if candidate_row is None:
            raise GovernanceError("EXACT_PROTECTED_CANDIDATE_REQUIRED")
        candidate = _read_json(candidate_row[0])
        if candidate["candidate_hash"] != execution["candidate_hash"]:
            raise GovernanceError("EXACT_PROTECTED_CANDIDATE_REQUIRED")
        materialization_row = conn.execute(
            "SELECT metadata_json FROM materializations WHERE materialization_id=?",
            (execution["materialization_id"],),
        ).fetchone()
        if materialization_row is None:
            raise GovernanceError("EXACT_PROTECTED_INPUT_REQUIRED")
        materialization = _read_json(materialization_row[0])
    try:
        protected_payload = _load_protected_input(materialization, execution)
        authoritative = execute_protected_candidate(candidate, protected_payload)
        candidate_observable_scored_event_count = len(authoritative["ledger"]["event_rows"])
        if authoritative["execution_evidence"].get(
            "candidate_observable_scored_event_count"
        ) != candidate_observable_scored_event_count:
            raise GovernanceError("PROTECTED_EXECUTION_EVIDENCE_INVALID")
        evaluator_input = {"input_schema": "DELTAGRID_M103_POST_EXECUTION_MEASUREMENT_INPUT_V1",
            "candidate_hash": candidate["candidate_hash"], "stage": execution["stage"],
            "authoritative_metrics": authoritative["metrics"],
            "authoritative_ledger_hash": authoritative["ledger"]["canonical_event_ledger_hash"],
            "execution_evidence_hash": authoritative["execution_evidence_hash"]}
        output = _measure_deterministically(evaluator, evaluator_input)
    except GovernanceError:
        raise
    except Exception as error:
        raise GovernanceError("PROTECTED_EVALUATOR_FAILURE") from error
    expected_fields = {"measurements", "measurement_evidence_hash"}
    if set(output) != expected_fields:
        raise GovernanceError("PROTECTED_EVALUATOR_OUTPUT_INVALID")
    require_hash(output["measurement_evidence_hash"], "measurement_evidence_hash")
    if output["measurement_evidence_hash"] != canonical_hash(output["measurements"]):
        raise GovernanceError("PROTECTED_MEASUREMENT_EVIDENCE_INVALID")
    now = trusted_utc_now()
    with connection(root) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            execution_row = conn.execute("SELECT execution_json FROM stage_executions WHERE stage_execution_id=?", (execution_id,)).fetchone()
            execution = _read_json(execution_row[0])
            program, campaign, _proposal = _program_context(conn, execution["program_id"])
            if conn.execute("SELECT 1 FROM stage_decisions WHERE stage_execution_id=?", (execution_id,)).fetchone():
                raise GovernanceError("PROTECTED_STAGE_ALREADY_DECIDED")
            stage = execution["stage"]
            rule = program["protected_acceptance_rules"][stage]
            measurements = output["measurements"]
            if not isinstance(measurements, dict) or rule["statistic"] not in measurements:
                raise GovernanceError("PROTECTED_EVALUATOR_OUTPUT_INVALID")
            statistic = require_decimal_text(measurements[rule["statistic"]], rule["statistic"])
            gate_ids = {gate["measurement_id"] for gate in rule["measurement_gates"]}
            if set(measurements) != gate_ids | {rule["statistic"]}:
                raise GovernanceError("PROTECTED_MEASUREMENT_SET_MISMATCH")
            for identifier, value in measurements.items():
                if identifier not in authoritative["metrics"] or require_decimal_text(value, identifier) != require_decimal_text(authoritative["metrics"][identifier], identifier):
                    raise GovernanceError("PROTECTED_MEASUREMENT_NOT_AUTHORITATIVE")
            gate_outcomes = apply_measurement_gates(
                {key: measurements[key] for key in gate_ids}, rule["measurement_gates"]
            ) if gate_ids else {}
            threshold = Decimal(rule["threshold"])
            statistic_passed = statistic > threshold if rule["direction"] == "GREATER" else statistic < threshold
            candidate_observable_scored_event_count = len(authoritative["ledger"]["event_rows"])
            if authoritative["execution_evidence"].get(
                "candidate_observable_scored_event_count"
            ) != candidate_observable_scored_event_count:
                raise GovernanceError("PROTECTED_EXECUTION_EVIDENCE_INVALID")
            sample_passed = candidate_observable_scored_event_count >= rule["minimum_scored_samples"]
            passed = statistic_passed and sample_passed and all(gate_outcomes.values())
            status = f"{stage}_PASSED" if passed else "PROGRAM_REJECTED"
            decision_core = {
                "stage_execution_id": execution_id, "execution_hash": execution["execution_hash"],
                "program_id": execution["program_id"], "stage": stage, "passed": passed,
                "measurement_evidence_hash": output["measurement_evidence_hash"],
                "authoritative_ledger_hash": authoritative["ledger"]["canonical_event_ledger_hash"],
                "authoritative_metrics_hash": canonical_hash(authoritative["metrics"]),
                "protected_execution_evidence_hash": authoritative["execution_evidence_hash"],
                "measurement_commitment": canonical_hash(measurements), "gate_outcomes": gate_outcomes,
                "statistic_passed": statistic_passed, "sample_passed": sample_passed,
                "candidate_observable_scored_event_count": candidate_observable_scored_event_count,
                "status": status, "decided_at": now,
            }
            decision_hash = canonical_hash(decision_core)
            decision_id = f"m103-stage-decision-{decision_hash}"
            decision = {**decision_core, "decision_id": decision_id, "decision_hash": decision_hash}
            conn.execute("INSERT INTO stage_decisions VALUES(?,?,?,?,?,?,?,?)", (decision_id, decision_hash, execution_id, execution["program_id"], stage, int(passed), _json(decision), now))
            _event(conn, campaign["campaign_id"], status, "FIXED_PROTECTED_STAGE_DECISION", now)
            next_status = status
            if passed:
                index = STAGES.index(stage)
                if index < len(STAGES) - 1:
                    next_status = f"{STAGES[index + 1]}_ELIGIBLE"
                    _event(conn, campaign["campaign_id"], next_status, "FOUNDER_AUTHORIZATION_REQUIRED", now)
                else:
                    next_status = "QUALIFIED_FOR_M104_OBSERVATION"
                    artifact_core = {
                        "verdict": next_status, "authority_effect": "NONE", "campaign_id": campaign["campaign_id"],
                        "campaign_hash": campaign["campaign_hash"], "program_id": execution["program_id"], "program_hash": program["program_hash"],
                        "candidate_hash": execution["candidate_hash"], "holdout_decision_hash": decision_hash,
                        "authority": {"model_training": False, "paper_trading": False, "live_trading": False, "exchange_access": False,
                            "credentials": False, "signed_requests": False, "orders": False, "portfolio_allocation": False,
                            "leverage_or_risk_enlargement": False, "capital_deployment": False, "self_authorization": False},
                    }
                    artifact_hash = canonical_hash(artifact_core)
                    artifact_id = f"m103-final-artifact-{artifact_hash}"
                    artifact = {**artifact_core, "artifact_id": artifact_id, "artifact_hash": artifact_hash}
                    conn.execute("INSERT INTO final_artifacts VALUES(?,?,?,?,?)", (artifact_id, artifact_hash, execution["program_id"], _json(artifact), now))
                    _event(conn, campaign["campaign_id"], next_status, "AUTHORITY_EFFECT_NONE", now)
            conn.commit()
        except GovernanceError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise GovernanceError("PROTECTED_STAGE_ALREADY_DECIDED") from error
    return {"stage_execution_id": execution_id, "execution_hash": execution["execution_hash"], "stage": stage, "status": next_status, "recovered": recovered, "authority_effect": "NONE"}


def inspect_governance(root: str | Path) -> dict[str, Any]:
    """Metadata-only status. No nonce, result metrics, or protected values are returned."""

    with connection(root, readonly=True) as conn:
        campaigns = []
        for row in conn.execute("SELECT campaign_id,campaign_hash FROM campaigns ORDER BY campaign_id"):
            status = _latest_campaign_status(conn, row["campaign_id"])
            program_count = int(conn.execute("SELECT COUNT(*) FROM programs WHERE campaign_id=?", (row["campaign_id"],)).fetchone()[0])
            campaigns.append({"campaign_id": row["campaign_id"], "campaign_hash": row["campaign_hash"], "status": status, "program_count": program_count})
        counts = {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in (
            "proposals", "campaigns", "programs", "program_activations", "development_results", "candidates", "materializations", "stage_authorizations", "stage_executions", "stage_decisions", "final_artifacts"
        )}
    return {"metadata_only": True, "campaigns": campaigns, "counts": counts, "protected_values_exposed": False}


__all__ = [
    "ACK_INITIALIZE", "ACK_ADMIT_CAMPAIGN", "ACK_ACTIVATE_PROGRAM", "ACK_AUTHORIZE_STAGE", "ACK_REVOKE_STAGE",
    "initialize_governance", "commit_campaign_proposal", "admit_campaign", "create_program", "activate_program",
    "record_development_result", "qualify_development", "derive_program_null_seed",
    "register_materialization", "authorize_stage", "revoke_stage_authorization",
    "open_protected_stage", "recover_protected_stage", "inspect_governance", "connection",
]
