"""Durable SQLite ledger for the single Mission 97 observation workflow."""

from __future__ import annotations

from contextlib import contextmanager
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator, Mapping
from urllib.parse import quote

from offchain.research.admission import canonical_hash, canonical_json

from .definitions import RESEARCH_OBSERVATION_REFRESH_V1, STEP_INDEX
from .models import (
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    OrchestrationError,
    WorkflowRunSnapshot,
    WorkflowStatus,
)
from .strict_json import (
    add_seconds,
    decode_json,
    parse_utc,
    resolve_existing,
    validate_identifier,
    validate_missing_path,
)


SCHEMA_VERSION = 1
MAX_EVENTS_PER_RUN = 1000
MAX_RUNS = 10000

_CONTRACT_SPECS = (
    (
        "contracts/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json",
        "deltagrid-research-cockpit-v0-charter-v1",
        "b4064f4651730618bf6497e631e913ebde7d6c9db926943d46aa11b3bc223bc1",
        None,
        None,
    ),
    (
        "contracts/DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json",
        "deltagrid-research-admission-core-v1",
        "e4070b52a0f2dbc8ce34ea00d0a732c2aed25c9c21e5acfccc3f9d791dba6193",
        "contracts/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json",
        None,
    ),
    (
        "contracts/DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE_V1.json",
        "deltagrid-canonical-result-engine-service-v1",
        "d8fcd1169e638b648f8b5fccb389dfd090b016beb80e9e13d7f0a0af3210aa6a",
        "contracts/DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json",
        "e4070b52a0f2dbc8ce34ea00d0a732c2aed25c9c21e5acfccc3f9d791dba6193",
    ),
    (
        "contracts/DELTAGRID_RESEARCH_CONTROL_PLANE_V1.json",
        "deltagrid-research-control-plane-v1",
        "c1e0c8c55db90fe8a81d3afe2d243537c703dbee6a945596f4b37c5ee13e70a9",
        "contracts/DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE_V1.json",
        "d8fcd1169e638b648f8b5fccb389dfd090b016beb80e9e13d7f0a0af3210aa6a",
    ),
    (
        "contracts/DELTAGRID_RESEARCH_COCKPIT_UI_V1.json",
        "deltagrid-research-cockpit-ui-v1",
        "13846c63a6fcd07b2a4603aadd388960e74282de486bddf39907a09aa053c8d3",
        "contracts/DELTAGRID_RESEARCH_CONTROL_PLANE_V1.json",
        "c1e0c8c55db90fe8a81d3afe2d243537c703dbee6a945596f4b37c5ee13e70a9",
    ),
    (
        "contracts/DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR_V1.json",
        MISSION_CONTRACT_ID,
        MISSION_CONTRACT_HASH,
        "contracts/DELTAGRID_RESEARCH_COCKPIT_UI_V1.json",
        "13846c63a6fcd07b2a4603aadd388960e74282de486bddf39907a09aa053c8d3",
    ),
)

_TABLE_COLUMNS = {
    "orchestration_metadata": (
        "schema_version", "contract_id", "contract_hash", "workflow_definition_id",
        "workflow_definition_hash", "output_root", "output_root_path_identity",
        "governance_repository_root", "governance_repository_root_path_identity",
        "created_at", "canonical_metadata_hash",
    ),
    "workflow_runs": (
        "run_id", "workflow_definition_id", "workflow_definition_version",
        "workflow_definition_hash", "run_key", "canonical_input_json",
        "canonical_input_hash", "requested_at", "requested_by", "canonical_run_hash",
    ),
    "workflow_events": (
        "event_id", "run_id", "sequence_number", "event_type", "reason_token",
        "event_timestamp", "step_id", "attempt_number", "not_before_at",
        "evidence_hash", "canonical_event_hash",
    ),
    "workflow_claims": (
        "run_id", "step_id", "attempt_number", "fencing_epoch", "worker_id",
        "fencing_token", "claimed_at", "lease_expires_at", "canonical_claim_hash",
    ),
    "workflow_receipts": (
        "receipt_id", "idempotency_key", "run_id", "step_id", "action_id",
        "canonical_action_input_hash", "artifact_id", "artifact_relative_path",
        "artifact_byte_hash", "artifact_canonical_hash", "completed_at",
        "canonical_receipt_hash",
    ),
}

_IMMUTABLE_TRIGGERS = {
    "orchestration_metadata_no_update", "orchestration_metadata_no_delete",
    "workflow_runs_no_update", "workflow_runs_no_delete",
    "workflow_events_no_update", "workflow_events_no_delete",
    "workflow_receipts_no_update", "workflow_receipts_no_delete",
}
_PRIMARY_KEYS = {
    "orchestration_metadata": ("schema_version",),
    "workflow_runs": ("run_id",),
    "workflow_events": ("event_id",),
    "workflow_claims": ("run_id",),
    "workflow_receipts": ("receipt_id",),
}
_FOREIGN_KEYS = {
    "orchestration_metadata": frozenset(),
    "workflow_runs": frozenset(),
    "workflow_events": frozenset({("run_id", "workflow_runs", "run_id")}),
    "workflow_claims": frozenset({("run_id", "workflow_runs", "run_id")}),
    "workflow_receipts": frozenset({("run_id", "workflow_runs", "run_id")}),
}
_UNIQUES = {
    "orchestration_metadata": frozenset({("canonical_metadata_hash",)}),
    "workflow_runs": frozenset({("run_key",), ("canonical_run_hash",)}),
    "workflow_events": frozenset(
        {("canonical_event_hash",), ("run_id", "sequence_number")}
    ),
    "workflow_claims": frozenset(
        {("fencing_token",), ("canonical_claim_hash",)}
    ),
    "workflow_receipts": frozenset(
        {
            ("idempotency_key",), ("artifact_id",), ("artifact_relative_path",),
            ("canonical_receipt_hash",), ("run_id", "step_id"),
        }
    ),
}

_EVENT_TYPES = frozenset(
    {
        "RUN_CREATED", "RUN_CANCEL_REQUESTED", "STEP_CLAIMED",
        "STEP_LEASE_EXPIRED", "STEP_ATTEMPT_FAILED", "STEP_RETRY_SCHEDULED",
        "STEP_SUCCEEDED", "RUN_COMPLETED", "RUN_FAILED", "RUN_CANCELLED",
    }
)
_TERMINAL_EVENTS = {
    "RUN_COMPLETED": WorkflowStatus.COMPLETED,
    "RUN_FAILED": WorkflowStatus.FAILED,
    "RUN_CANCELLED": WorkflowStatus.CANCELLED,
}
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


def _is_hash(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


SCHEMA_SQL = """
CREATE TABLE orchestration_metadata (
 schema_version INTEGER PRIMARY KEY NOT NULL,
 contract_id TEXT NOT NULL,
 contract_hash TEXT NOT NULL,
 workflow_definition_id TEXT NOT NULL,
 workflow_definition_hash TEXT NOT NULL,
 output_root TEXT NOT NULL,
 output_root_path_identity TEXT NOT NULL,
 governance_repository_root TEXT NOT NULL,
 governance_repository_root_path_identity TEXT NOT NULL,
 created_at TEXT NOT NULL,
 canonical_metadata_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE workflow_runs (
 run_id TEXT PRIMARY KEY NOT NULL,
 workflow_definition_id TEXT NOT NULL,
 workflow_definition_version INTEGER NOT NULL,
 workflow_definition_hash TEXT NOT NULL,
 run_key TEXT NOT NULL UNIQUE,
 canonical_input_json TEXT NOT NULL,
 canonical_input_hash TEXT NOT NULL,
 requested_at TEXT NOT NULL,
 requested_by TEXT NOT NULL,
 canonical_run_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE workflow_events (
 event_id TEXT PRIMARY KEY NOT NULL,
 run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
 sequence_number INTEGER NOT NULL,
 event_type TEXT NOT NULL,
 reason_token TEXT NOT NULL,
 event_timestamp TEXT NOT NULL,
 step_id TEXT,
 attempt_number INTEGER,
 not_before_at TEXT,
 evidence_hash TEXT,
 canonical_event_hash TEXT NOT NULL UNIQUE,
 UNIQUE(run_id, sequence_number)
);
CREATE TABLE workflow_claims (
 run_id TEXT PRIMARY KEY NOT NULL REFERENCES workflow_runs(run_id),
 step_id TEXT NOT NULL,
 attempt_number INTEGER NOT NULL,
 fencing_epoch INTEGER NOT NULL,
 worker_id TEXT NOT NULL,
 fencing_token TEXT NOT NULL UNIQUE,
 claimed_at TEXT NOT NULL,
 lease_expires_at TEXT NOT NULL,
 canonical_claim_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE workflow_receipts (
 receipt_id TEXT PRIMARY KEY NOT NULL,
 idempotency_key TEXT NOT NULL UNIQUE,
 run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
 step_id TEXT NOT NULL,
 action_id TEXT NOT NULL,
 canonical_action_input_hash TEXT NOT NULL,
 artifact_id TEXT NOT NULL UNIQUE,
 artifact_relative_path TEXT NOT NULL UNIQUE,
 artifact_byte_hash TEXT NOT NULL,
 artifact_canonical_hash TEXT NOT NULL,
 completed_at TEXT NOT NULL,
 canonical_receipt_hash TEXT NOT NULL UNIQUE,
 UNIQUE(run_id, step_id)
);
CREATE TRIGGER orchestration_metadata_no_update BEFORE UPDATE ON orchestration_metadata BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER orchestration_metadata_no_delete BEFORE DELETE ON orchestration_metadata BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER workflow_runs_no_update BEFORE UPDATE ON workflow_runs BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER workflow_runs_no_delete BEFORE DELETE ON workflow_runs BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER workflow_events_no_update BEFORE UPDATE ON workflow_events BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER workflow_events_no_delete BEFORE DELETE ON workflow_events BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER workflow_receipts_no_update BEFORE UPDATE ON workflow_receipts BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER workflow_receipts_no_delete BEFORE DELETE ON workflow_receipts BEGIN SELECT RAISE(ABORT, 'immutable'); END;
PRAGMA user_version = 1;
"""


def _path_identity(path: Path) -> str:
    return f"sha256:{canonical_hash({'absolute_path': str(path)})}"


def _verify_governance(root: Path) -> None:
    try:
        for relative, expected_id, expected_hash, predecessor, predecessor_hash in _CONTRACT_SPECS:
            path = resolve_existing(
                root / relative,
                directory=False,
                reason="GOVERNANCE_CONTRACT_INTEGRITY_FAILURE",
            )
            value = decode_json(
                path.read_bytes(),
                max_bytes=1_048_576,
                reason="GOVERNANCE_CONTRACT_INTEGRITY_FAILURE",
                require_canonical=False,
                reject_floats=False,
            )
            if type(value) is not dict or value.get("contract_id") != expected_id:
                raise ValueError("contract identity mismatch")
            core = dict(value)
            supplied = core.pop("contract_hash_sha256", None)
            if supplied != expected_hash or canonical_hash(core) != expected_hash:
                raise ValueError("contract hash mismatch")
            if predecessor is not None and value.get("preceding_contract") != predecessor:
                raise ValueError("predecessor mismatch")
            if (
                predecessor_hash is not None
                and value.get("preceding_contract_hash_sha256") != predecessor_hash
            ):
                raise ValueError("predecessor hash mismatch")
            if expected_id == MISSION_CONTRACT_ID and (
                value.get("functional_dependency")
                != "contracts/DELTAGRID_RESEARCH_CONTROL_PLANE_V1.json"
                or value.get("functional_dependency_hash_sha256")
                != "c1e0c8c55db90fe8a81d3afe2d243537c703dbee6a945596f4b37c5ee13e70a9"
            ):
                raise ValueError("functional dependency mismatch")
    except OrchestrationError as error:
        if error.reason_token == "GOVERNANCE_CONTRACT_INTEGRITY_FAILURE":
            raise
        raise OrchestrationError("GOVERNANCE_CONTRACT_INTEGRITY_FAILURE") from error
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        raise OrchestrationError(
            "GOVERNANCE_CONTRACT_INTEGRITY_FAILURE",
            "required governance contract verification failed",
        ) from error


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


class WorkflowLedger:
    """Verified durable ledger; public operations never expose SQL or connections."""

    def __init__(
        self, database_path: Path | str, *, busy_timeout_ms: int = 5_000
    ) -> None:
        self._validate_busy_timeout_ms(busy_timeout_ms)
        self._database_path = resolve_existing(
            database_path,
            directory=False,
            reason="ORCHESTRATION_SCHEMA_INCOMPATIBLE",
        )
        self._busy_timeout_ms = busy_timeout_ms
        with self._connection() as connection:
            self._verify_schema(connection)
            self._metadata = self._load_metadata(connection)
        self._output_root = resolve_existing(
            self._metadata["output_root"],
            directory=True,
            reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE",
        )
        self._governance_repository_root = resolve_existing(
            self._metadata["governance_repository_root"],
            directory=True,
            reason="GOVERNANCE_CONTRACT_INTEGRITY_FAILURE",
        )
        if (
            _path_identity(self._output_root)
            != self._metadata["output_root_path_identity"]
            or _path_identity(self._governance_repository_root)
            != self._metadata["governance_repository_root_path_identity"]
        ):
            raise OrchestrationError("ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        _verify_governance(self._governance_repository_root)

    @staticmethod
    def _validate_busy_timeout_ms(busy_timeout_ms: int) -> None:
        if (
            type(busy_timeout_ms) is not int
            or not 100 <= busy_timeout_ms <= 30_000
        ):
            raise OrchestrationError(
                "WORKFLOW_INPUT_INVALID",
                "busy_timeout_ms must be an integer from 100 through 30000",
            )

    @classmethod
    def initialize(
        cls,
        *,
        database_path: Path | str,
        output_root: Path | str,
        governance_repository_root: Path | str,
        created_at: str,
        busy_timeout_ms: int = 5_000,
    ) -> WorkflowLedger:
        cls._validate_busy_timeout_ms(busy_timeout_ms)
        parse_utc(created_at)
        database, _ = validate_missing_path(
            database_path, reason="ORCHESTRATION_SCHEMA_INCOMPATIBLE"
        )
        output = Path(output_root)
        if not output.is_absolute() or len(str(output)) > 4096:
            raise OrchestrationError("ARTIFACT_PATH_UNSAFE")
        if output.exists() or output.is_symlink():
            raise OrchestrationError("ARTIFACT_PATH_UNSAFE")
        resolve_existing(
            output.parent, directory=True, reason="ARTIFACT_PATH_UNSAFE"
        )
        governance = resolve_existing(
            governance_repository_root,
            directory=True,
            reason="GOVERNANCE_CONTRACT_INTEGRITY_FAILURE",
        )
        if database.is_relative_to(governance):
            raise OrchestrationError(
                "ORCHESTRATION_SCHEMA_INCOMPATIBLE",
                "the orchestration database must be outside the governance repository",
            )
        if output.is_relative_to(governance):
            raise OrchestrationError(
                "ARTIFACT_PATH_UNSAFE",
                "the output root must be outside the governance repository",
            )
        _verify_governance(governance)
        try:
            output.mkdir(mode=0o700)
            resolved_output = resolve_existing(
                output, directory=True, reason="ARTIFACT_PATH_UNSAFE"
            )
            connection = sqlite3.connect(
                str(database), isolation_level=None, timeout=0
            )
            connection.row_factory = sqlite3.Row
            try:
                if (
                    str(connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0])
                    .lower()
                    != "delete"
                ):
                    raise OrchestrationError("ORCHESTRATION_SCHEMA_INCOMPATIBLE")
                connection.execute("PRAGMA synchronous = EXTRA")
                if int(connection.execute("PRAGMA synchronous").fetchone()[0]) != 3:
                    raise OrchestrationError("ORCHESTRATION_SCHEMA_INCOMPATIBLE")
                connection.execute("PRAGMA foreign_keys = ON")
                if int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) != 1:
                    raise OrchestrationError("ORCHESTRATION_SCHEMA_INCOMPATIBLE")
                connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
                if (
                    int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
                    != busy_timeout_ms
                ):
                    raise OrchestrationError("ORCHESTRATION_SCHEMA_INCOMPATIBLE")
                connection.executescript(SCHEMA_SQL)
                if int(connection.execute("PRAGMA user_version").fetchone()[0]) != 1:
                    raise OrchestrationError("ORCHESTRATION_SCHEMA_INCOMPATIBLE")
                core = {
                    "schema_version": SCHEMA_VERSION,
                    "contract_id": MISSION_CONTRACT_ID,
                    "contract_hash": MISSION_CONTRACT_HASH,
                    "workflow_definition_id": (
                        RESEARCH_OBSERVATION_REFRESH_V1.workflow_definition_id
                    ),
                    "workflow_definition_hash": (
                        RESEARCH_OBSERVATION_REFRESH_V1.canonical_workflow_definition_hash
                    ),
                    "output_root": str(resolved_output),
                    "output_root_path_identity": _path_identity(resolved_output),
                    "governance_repository_root": str(governance),
                    "governance_repository_root_path_identity": _path_identity(governance),
                    "created_at": created_at,
                }
                connection.execute(
                    f"INSERT INTO orchestration_metadata ({','.join(core)},canonical_metadata_hash) "
                    f"VALUES ({','.join('?' for _ in range(len(core) + 1))})",
                    (*core.values(), canonical_hash(core)),
                )
            finally:
                connection.close()
        except OrchestrationError:
            raise
        except (OSError, sqlite3.DatabaseError) as error:
            raise OrchestrationError("ORCHESTRATION_SCHEMA_INCOMPATIBLE") from error
        return cls(database, busy_timeout_ms=busy_timeout_ms)

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def output_root(self) -> Path:
        return self._output_root

    @property
    def governance_repository_root(self) -> Path:
        return self._governance_repository_root

    @property
    def metadata(self) -> Mapping[str, Any]:
        return dict(self._metadata)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        encoded = quote(str(self._database_path), safe="/")
        try:
            connection = sqlite3.connect(
                f"file:{encoded}?mode=rw",
                uri=True,
                isolation_level=None,
                timeout=0,
            )
        except sqlite3.DatabaseError as error:
            raise OrchestrationError("ORCHESTRATION_SCHEMA_INCOMPATIBLE") from error
        connection.row_factory = sqlite3.Row
        try:
            if (
                str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
                != "delete"
            ):
                raise OrchestrationError("ORCHESTRATION_SCHEMA_INCOMPATIBLE")
            connection.execute("PRAGMA synchronous = EXTRA")
            if int(connection.execute("PRAGMA synchronous").fetchone()[0]) != 3:
                raise OrchestrationError("ORCHESTRATION_SCHEMA_INCOMPATIBLE")
            connection.execute("PRAGMA foreign_keys = ON")
            if int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) != 1:
                raise OrchestrationError("ORCHESTRATION_SCHEMA_INCOMPATIBLE")
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            if (
                int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
                != self._busy_timeout_ms
            ):
                raise OrchestrationError("ORCHESTRATION_SCHEMA_INCOMPATIBLE")
            yield connection
        except sqlite3.OperationalError as error:
            if "locked" in str(error).lower() or "busy" in str(error).lower():
                raise OrchestrationError("ORCHESTRATION_DATABASE_BUSY") from error
            raise
        finally:
            connection.close()

    @contextmanager
    def _mutation(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        try:
            if int(connection.execute("PRAGMA user_version").fetchone()[0]) != SCHEMA_VERSION:
                raise ValueError("user_version")
            tables = {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if set(_TABLE_COLUMNS) != tables:
                raise ValueError("table identity")
            for table, expected in _TABLE_COLUMNS.items():
                rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
                if tuple(str(row["name"]) for row in rows) != expected:
                    raise ValueError("column identity")
                integer_fields = {
                    "schema_version", "workflow_definition_version",
                    "sequence_number", "attempt_number", "fencing_epoch",
                }
                if any(
                    str(row["type"]).upper()
                    != ("INTEGER" if str(row["name"]) in integer_fields else "TEXT")
                    for row in rows
                ):
                    raise ValueError("column type")
                nullable = (
                    {"step_id", "attempt_number", "not_before_at", "evidence_hash"}
                    if table == "workflow_events"
                    else set()
                )
                if any(
                    int(row["notnull"]) != 1
                    for row in rows
                    if str(row["name"]) not in nullable
                ):
                    raise ValueError("not null")
                primary_key = tuple(
                    str(row["name"])
                    for row in sorted(rows, key=lambda item: int(item["pk"]))
                    if int(row["pk"]) > 0
                )
                if primary_key != _PRIMARY_KEYS[table]:
                    raise ValueError("primary key")
                foreign_keys = frozenset(
                    (
                        str(row["from"]),
                        str(row["table"]),
                        str(row["to"]),
                    )
                    for row in connection.execute(
                        f'PRAGMA foreign_key_list("{table}")'
                    )
                )
                if foreign_keys != _FOREIGN_KEYS[table]:
                    raise ValueError("foreign key identity")
                unique_columns: set[tuple[str, ...]] = set()
                for index in connection.execute(f'PRAGMA index_list("{table}")'):
                    if int(index["unique"]) != 1 or str(index["origin"]) == "pk":
                        continue
                    escaped_index = str(index["name"]).replace('"', '""')
                    columns = tuple(
                        str(item["name"])
                        for item in connection.execute(
                            f'PRAGMA index_info("{escaped_index}")'
                        )
                    )
                    unique_columns.add(columns)
                if frozenset(unique_columns) != _UNIQUES[table]:
                    raise ValueError("unique identity")
            triggers = {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                )
            }
            if triggers != _IMMUTABLE_TRIGGERS:
                raise ValueError("immutable trigger identity")
            for name in triggers:
                row = connection.execute(
                    "SELECT tbl_name,sql FROM sqlite_master "
                    "WHERE type='trigger' AND name=?",
                    (name,),
                ).fetchone()
                operation = "UPDATE" if name.endswith("_no_update") else "DELETE"
                table = name[
                    : -len("_no_update")
                    if name.endswith("_no_update")
                    else -len("_no_delete")
                ]
                normalized = " ".join(str(row["sql"]).upper().split())
                if (
                    str(row["tbl_name"]) != table
                    or f"BEFORE {operation} ON {table.upper()}" not in normalized
                    or "RAISE(ABORT, 'IMMUTABLE')" not in normalized
                ):
                    raise ValueError("immutable trigger definition")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("foreign key check")
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise OrchestrationError("ORCHESTRATION_SCHEMA_INCOMPATIBLE") from error

    @staticmethod
    def _load_metadata(connection: sqlite3.Connection) -> dict[str, Any]:
        rows = connection.execute("SELECT * FROM orchestration_metadata").fetchall()
        if len(rows) != 1:
            raise OrchestrationError("ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        value = _row_dict(rows[0])
        supplied = value.pop("canonical_metadata_hash")
        if (
            canonical_hash(value) != supplied
            or value["schema_version"] != SCHEMA_VERSION
            or value["contract_id"] != MISSION_CONTRACT_ID
            or value["contract_hash"] != MISSION_CONTRACT_HASH
            or value["workflow_definition_id"]
            != RESEARCH_OBSERVATION_REFRESH_V1.workflow_definition_id
            or value["workflow_definition_hash"]
            != RESEARCH_OBSERVATION_REFRESH_V1.canonical_workflow_definition_hash
        ):
            raise OrchestrationError("ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        parse_utc(value["created_at"], reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        value["canonical_metadata_hash"] = supplied
        return value

    @staticmethod
    def _verify_run(row: sqlite3.Row) -> dict[str, Any]:
        value = _row_dict(row)
        try:
            inputs = decode_json(
                value["canonical_input_json"].encode("utf-8"),
                max_bytes=65536,
                reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE",
            )
            exact_input_fields = {
                "run_key", "research_ledger_path", "result_root",
                "expected_repository_commit", "observation_as_of",
                "requested_at", "requested_by",
            }
            if (
                type(inputs) is not dict
                or set(inputs) != exact_input_fields
                or inputs["run_key"] != value["run_key"]
                or inputs["requested_at"] != value["requested_at"]
                or inputs["requested_by"] != value["requested_by"]
                or type(inputs["expected_repository_commit"]) is not str
                or _COMMIT_RE.fullmatch(inputs["expected_repository_commit"]) is None
                or type(inputs["research_ledger_path"]) is not str
                or not Path(inputs["research_ledger_path"]).is_absolute()
                or type(inputs["result_root"]) is not str
                or not Path(inputs["result_root"]).is_absolute()
            ):
                raise ValueError("run input")
            validate_identifier(
                inputs["run_key"], reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE"
            )
            validate_identifier(
                inputs["requested_by"], reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE"
            )
            if parse_utc(
                inputs["observation_as_of"],
                reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE",
            ) > parse_utc(
                inputs["requested_at"],
                reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE",
            ):
                raise ValueError("run timestamp order")
            if (
                canonical_hash(inputs) != value["canonical_input_hash"]
                or value["workflow_definition_id"]
                != RESEARCH_OBSERVATION_REFRESH_V1.workflow_definition_id
                or value["workflow_definition_version"] != 1
                or value["workflow_definition_hash"]
                != RESEARCH_OBSERVATION_REFRESH_V1.canonical_workflow_definition_hash
            ):
                raise ValueError("run mismatch")
            identity_core = {
                "mission_97_contract_hash": MISSION_CONTRACT_HASH,
                "workflow_definition_hash": value["workflow_definition_hash"],
                "run_key": value["run_key"],
                "canonical_input_hash": value["canonical_input_hash"],
            }
            if value["run_id"] != f"run-{canonical_hash(identity_core)[:32]}":
                raise ValueError("run identity")
            core = {key: value[key] for key in _TABLE_COLUMNS["workflow_runs"][:-1]}
            if canonical_hash(core) != value["canonical_run_hash"]:
                raise ValueError("run hash")
            return {**value, "input": inputs}
        except (ValueError, TypeError, OrchestrationError) as error:
            raise OrchestrationError("ORCHESTRATION_ROW_INTEGRITY_FAILURE") from error

    @staticmethod
    def _verify_event(row: sqlite3.Row) -> dict[str, Any]:
        value = _row_dict(row)
        supplied = value.pop("canonical_event_hash")
        identity_core = {
            key: value[key]
            for key in _TABLE_COLUMNS["workflow_events"][1:-1]
        }
        if (
            value["event_type"] not in _EVENT_TYPES
            or canonical_hash(value) != supplied
            or value["event_id"] != f"event-{canonical_hash(identity_core)[:32]}"
            or type(value["reason_token"]) is not str
            or not value["reason_token"]
            or len(value["reason_token"]) > 1024
            or (value["evidence_hash"] is not None and not _is_hash(value["evidence_hash"]))
        ):
            raise OrchestrationError("ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        parse_utc(value["event_timestamp"], reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        if value["not_before_at"] is not None:
            parse_utc(value["not_before_at"], reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        value["canonical_event_hash"] = supplied
        return value

    @staticmethod
    def _verify_receipt(row: sqlite3.Row) -> dict[str, Any]:
        value = _row_dict(row)
        supplied = value.pop("canonical_receipt_hash")
        identity_core = {
            key: value[key]
            for key in _TABLE_COLUMNS["workflow_receipts"][1:-1]
        }
        artifact_identity = canonical_hash(
            {
                "mission_97_contract_hash": MISSION_CONTRACT_HASH,
                "run_id": value["run_id"],
                "step_id": value["step_id"],
                "idempotency_key": value["idempotency_key"],
                "artifact_relative_path": value["artifact_relative_path"],
                "artifact_byte_hash": value["artifact_byte_hash"],
                "artifact_canonical_hash": value["artifact_canonical_hash"],
            }
        )
        if (
            canonical_hash(value) != supplied
            or value["receipt_id"] != f"receipt-{canonical_hash(identity_core)[:32]}"
            or value["step_id"] not in STEP_INDEX
            or value["action_id"]
            != RESEARCH_OBSERVATION_REFRESH_V1.steps[
                STEP_INDEX[value["step_id"]]
            ].action_id
            or value["artifact_relative_path"]
            != (
                f"runs/{value['run_id']}/{value['step_id']}/result.json"
            )
            or not _is_hash(value["canonical_action_input_hash"])
            or not _is_hash(value["artifact_byte_hash"])
            or not _is_hash(value["artifact_canonical_hash"])
            or value["artifact_id"] != f"artifact-{artifact_identity[:32]}"
            or type(value["idempotency_key"]) is not str
            or not value["idempotency_key"].startswith("idempotency-")
            or not _is_hash(value["idempotency_key"][len("idempotency-"):])
        ):
            raise OrchestrationError("ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        parse_utc(value["completed_at"], reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        value["canonical_receipt_hash"] = supplied
        return value

    @staticmethod
    def _verify_claim(row: sqlite3.Row) -> dict[str, Any]:
        value = _row_dict(row)
        supplied = value.pop("canonical_claim_hash")
        token_core = {
            "mission_97_contract_hash": MISSION_CONTRACT_HASH,
            "run_id": value["run_id"],
            "step_id": value["step_id"],
            "attempt_number": value["attempt_number"],
            "fencing_epoch": value["fencing_epoch"],
            "worker_id": value["worker_id"],
            "claimed_at": value["claimed_at"],
        }
        if (
            canonical_hash(value) != supplied
            or value["step_id"] not in STEP_INDEX
            or type(value["attempt_number"]) is not int
            or not 1 <= value["attempt_number"] <= 3
            or type(value["fencing_epoch"]) is not int
            or value["fencing_epoch"] < 1
            or not hmac.compare_digest(
                str(value["fencing_token"]),
                f"fence-v1-{canonical_hash(token_core)}",
            )
            or parse_utc(
                value["lease_expires_at"],
                reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE",
            )
            <= parse_utc(
                value["claimed_at"],
                reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE",
            )
        ):
            raise OrchestrationError("ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        parse_utc(value["claimed_at"], reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        parse_utc(value["lease_expires_at"], reason="ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        value["canonical_claim_hash"] = supplied
        return value

    def _run_data(self, connection: sqlite3.Connection, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
        row = connection.execute(
            "SELECT * FROM workflow_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise OrchestrationError("WORKFLOW_INPUT_INVALID", "run does not exist")
        run = self._verify_run(row)
        events = [
            self._verify_event(item)
            for item in connection.execute(
                "SELECT * FROM workflow_events WHERE run_id=? ORDER BY sequence_number",
                (run_id,),
            )
        ]
        receipts = [
            self._verify_receipt(item)
            for item in connection.execute(
                "SELECT * FROM workflow_receipts WHERE run_id=?", (run_id,)
            )
        ]
        receipts.sort(key=lambda item: STEP_INDEX[item["step_id"]])
        claim_row = connection.execute(
            "SELECT * FROM workflow_claims WHERE run_id=?", (run_id,)
        ).fetchone()
        claim = None if claim_row is None else self._verify_claim(claim_row)
        self._validate_history(run, events, receipts, claim)
        return run, events, receipts, claim

    @staticmethod
    def _validate_history(
        run: dict[str, Any],
        events: list[dict[str, Any]],
        receipts: list[dict[str, Any]],
        claim: dict[str, Any] | None,
    ) -> None:
        if not events or len(events) > MAX_EVENTS_PER_RUN:
            raise OrchestrationError("ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        if [item["sequence_number"] for item in events] != list(range(1, len(events) + 1)):
            raise OrchestrationError("ORCHESTRATION_ROW_INTEGRITY_FAILURE")
        if any(
            parse_utc(events[index]["event_timestamp"], reason="INVALID_WORKFLOW_TRANSITION")
            < parse_utc(events[index - 1]["event_timestamp"], reason="INVALID_WORKFLOW_TRANSITION")
            for index in range(1, len(events))
        ):
            raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
        active: dict[str, Any] | None = None
        successful: list[str] = []
        attempt_counts = {step.step_id: 0 for step in RESEARCH_OBSERVATION_REFRESH_V1.steps}
        cancel_pending = False
        terminal = False
        receipt_by_step = {item["step_id"]: item for item in receipts}
        if len(receipt_by_step) != len(receipts):
            raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
        for index, event in enumerate(events):
            if event["run_id"] != run["run_id"] or terminal:
                raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
            event_type = event["event_type"]
            previous = None if index == 0 else events[index - 1]
            if event_type == "RUN_CREATED":
                if (
                    index != 0
                    or event["event_timestamp"] != run["requested_at"]
                    or event["evidence_hash"] != run["canonical_run_hash"]
                    or any(
                        event[name] is not None
                        for name in ("step_id", "attempt_number", "not_before_at")
                    )
                ):
                    raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
            elif event_type == "RUN_CANCEL_REQUESTED":
                if index == 0 or cancel_pending:
                    raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
                cancel_pending = True
            elif event_type == "STEP_CLAIMED":
                expected_step = RESEARCH_OBSERVATION_REFRESH_V1.steps[
                    len(successful)
                ].step_id if len(successful) < 3 else None
                step_id = event["step_id"]
                if (
                    active is not None
                    or cancel_pending
                    or step_id != expected_step
                    or type(event["attempt_number"]) is not int
                    or event["attempt_number"] != attempt_counts[step_id] + 1
                    or event["attempt_number"] > 3
                    or event["not_before_at"] is not None
                    or previous is None
                    or previous["event_type"] not in {
                        "RUN_CREATED", "STEP_RETRY_SCHEDULED", "STEP_SUCCEEDED"
                    }
                    or (
                        previous["event_type"] == "STEP_RETRY_SCHEDULED"
                        and parse_utc(event["event_timestamp"])
                        < parse_utc(previous["not_before_at"])
                    )
                ):
                    raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
                attempt_counts[step_id] += 1
                active = event
            elif event_type in {"STEP_ATTEMPT_FAILED", "STEP_LEASE_EXPIRED"}:
                if (
                    active is None
                    or event["step_id"] != active["step_id"]
                    or event["attempt_number"] != active["attempt_number"]
                    or event["not_before_at"] is not None
                ):
                    raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
                active = None
            elif event_type == "STEP_RETRY_SCHEDULED":
                if (
                    previous is None
                    or previous["event_type"]
                    not in {"STEP_ATTEMPT_FAILED", "STEP_LEASE_EXPIRED"}
                    or event["step_id"] != previous["step_id"]
                    or event["attempt_number"] != previous["attempt_number"]
                    or type(event["attempt_number"]) is not int
                    or not 1 <= event["attempt_number"] < 3
                    or event["not_before_at"]
                    != add_seconds(
                        event["event_timestamp"],
                        RESEARCH_OBSERVATION_REFRESH_V1.retry_delays_seconds[
                            event["attempt_number"] - 1
                        ],
                    )
                ):
                    raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
            elif event_type == "STEP_SUCCEEDED":
                receipt = receipt_by_step.get(str(event["step_id"]))
                if (
                    active is None
                    or event["step_id"] != active["step_id"]
                    or event["attempt_number"] != active["attempt_number"]
                    or event["not_before_at"] is not None
                    or receipt is None
                    or receipt["completed_at"] != event["event_timestamp"]
                    or receipt["canonical_receipt_hash"] != event["evidence_hash"]
                ):
                    raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
                successful.append(str(event["step_id"]))
                active = None
            elif event_type == "RUN_COMPLETED":
                if active is not None or cancel_pending or len(successful) != 3:
                    raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
                terminal = True
            elif event_type == "RUN_FAILED":
                if (
                    active is not None
                    or previous is None
                    or previous["event_type"]
                    not in {"STEP_ATTEMPT_FAILED", "STEP_LEASE_EXPIRED"}
                    or event["step_id"] != previous["step_id"]
                    or event["attempt_number"] != previous["attempt_number"]
                    or (
                        previous["event_type"] == "STEP_LEASE_EXPIRED"
                        and event["attempt_number"] != 3
                    )
                ):
                    raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
                terminal = True
            elif event_type == "RUN_CANCELLED":
                if active is not None or not cancel_pending:
                    raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
                terminal = True
            else:
                raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
            if cancel_pending and active is None and not terminal:
                next_type = events[index + 1]["event_type"] if index + 1 < len(events) else None
                if event_type not in {
                    "STEP_ATTEMPT_FAILED", "STEP_LEASE_EXPIRED", "STEP_SUCCEEDED"
                } and next_type != "RUN_CANCELLED":
                    raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
        expected_prefix = [
            step.step_id
            for step in RESEARCH_OBSERVATION_REFRESH_V1.steps[: len(successful)]
        ]
        if successful != expected_prefix or [item["step_id"] for item in receipts] != successful:
            raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
        if (active is None) != (claim is None):
            raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")
        if claim is not None and active is not None and (
            claim["step_id"] != active["step_id"]
            or claim["attempt_number"] != active["attempt_number"]
            or claim["claimed_at"] != active["event_timestamp"]
            or claim["fencing_epoch"] != active["sequence_number"]
            or claim["canonical_claim_hash"] != active["evidence_hash"]
        ):
            raise OrchestrationError("INVALID_WORKFLOW_TRANSITION")

    def _snapshot(self, run: dict[str, Any], events: list[dict[str, Any]], receipts: list[dict[str, Any]], claim: dict[str, Any] | None) -> WorkflowRunSnapshot:
        last = events[-1]
        terminal = _TERMINAL_EVENTS.get(last["event_type"])
        cancel_requested = any(x["event_type"] == "RUN_CANCEL_REQUESTED" for x in events)
        retry = last if last["event_type"] == "STEP_RETRY_SCHEDULED" else None
        if terminal is not None:
            status = terminal
        elif retry is not None:
            status = WorkflowStatus.WAITING_RETRY
        elif claim is not None:
            status = WorkflowStatus.RUNNING
        else:
            status = WorkflowStatus.PENDING
        successful = tuple(item["step_id"] for item in receipts)
        next_step = (
            None if len(successful) == 3 or terminal else
            RESEARCH_OBSERVATION_REFRESH_V1.steps[len(successful)].step_id
        )
        attempts = [
            int(item["attempt_number"])
            for item in events
            if item["step_id"] == next_step and item["event_type"] == "STEP_CLAIMED"
        ]
        next_attempt = (
            None
            if next_step is None or cancel_requested or claim is not None
            else len(attempts) + 1
        )
        receipt_identities = tuple(
            {
                "step_id": item["step_id"],
                "receipt_id": item["receipt_id"],
                "canonical_receipt_hash": item["canonical_receipt_hash"],
            }
            for item in receipts
        )
        artifacts = tuple(
            {
                "step_id": item["step_id"],
                "artifact_id": item["artifact_id"],
                "artifact_relative_path": item["artifact_relative_path"],
                "artifact_byte_hash": item["artifact_byte_hash"],
                "artifact_canonical_hash": item["artifact_canonical_hash"],
            }
            for item in receipts
        )
        active = None if claim is None else {
            key: claim[key]
            for key in (
                "step_id", "attempt_number", "fencing_epoch", "worker_id",
                "claimed_at", "lease_expires_at",
            )
        }
        public_last_event = {
            key: value
            for key, value in last.items()
            if key != "evidence_hash"
        }
        core = {
            "schema_version": "1.0",
            "run_id": run["run_id"],
            "run_key": run["run_key"],
            "workflow_definition_id": run["workflow_definition_id"],
            "workflow_definition_version": run["workflow_definition_version"],
            "workflow_definition_hash": run["workflow_definition_hash"],
            "canonical_input_hash": run["canonical_input_hash"],
            "status": status.value,
            "current_step_id": next_step,
            "next_attempt_number": next_attempt,
            "next_runnable_at": None if retry is None else retry["not_before_at"],
            "active_claim": active,
            "successful_step_ids": list(successful),
            "receipt_identities": list(receipt_identities),
            "artifact_identities": list(artifacts),
            "last_event": public_last_event,
            "event_count": len(events),
            "retry_count": sum(x["event_type"] == "STEP_RETRY_SCHEDULED" for x in events),
            "requested_at": run["requested_at"],
            "requested_by": run["requested_by"],
            "completed_at": (
                last["event_timestamp"] if last["event_type"] == "RUN_COMPLETED" else None
            ),
            "terminal_reason_token": last["reason_token"] if terminal is not None else None,
        }
        model_values = dict(core)
        model_values["status"] = status
        return WorkflowRunSnapshot(
            **model_values,
            canonical_run_snapshot_hash=canonical_hash(core),
        )

    def get_run(self, run_id: str) -> WorkflowRunSnapshot:
        with self._connection() as connection:
            return self._snapshot(*self._run_data(connection, run_id))

    def list_runs(self) -> tuple[WorkflowRunSnapshot, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT run_id FROM workflow_runs ORDER BY requested_at,run_id LIMIT ?",
                (MAX_RUNS + 1,),
            ).fetchall()
            if len(rows) > MAX_RUNS:
                raise OrchestrationError("RESOURCE_LIMIT_EXCEEDED")
            return tuple(
                self._snapshot(*self._run_data(connection, str(row["run_id"])))
                for row in rows
            )

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        *,
        run_id: str,
        event_type: str,
        reason_token: str,
        event_timestamp: str,
        step_id: str | None = None,
        attempt_number: int | None = None,
        not_before_at: str | None = None,
        evidence_hash: str | None = None,
    ) -> dict[str, Any]:
        parse_utc(event_timestamp)
        latest = connection.execute(
            "SELECT event_timestamp FROM workflow_events "
            "WHERE run_id=? ORDER BY sequence_number DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if (
            latest is not None
            and parse_utc(event_timestamp)
            < parse_utc(str(latest["event_timestamp"]))
        ):
            raise OrchestrationError(
                "CLOCK_REGRESSION",
                "the operational timestamp precedes the latest run event",
            )
        count = int(connection.execute(
            "SELECT COUNT(*) FROM workflow_events WHERE run_id=?", (run_id,)
        ).fetchone()[0])
        if count >= MAX_EVENTS_PER_RUN:
            raise OrchestrationError("RESOURCE_LIMIT_EXCEEDED")
        core = {
            "run_id": run_id,
            "sequence_number": count + 1,
            "event_type": event_type,
            "reason_token": reason_token,
            "event_timestamp": event_timestamp,
            "step_id": step_id,
            "attempt_number": attempt_number,
            "not_before_at": not_before_at,
            "evidence_hash": evidence_hash,
        }
        value = {"event_id": f"event-{canonical_hash(core)[:32]}", **core}
        value["canonical_event_hash"] = canonical_hash(value)
        connection.execute(
            f"INSERT INTO workflow_events ({','.join(value)}) VALUES ({','.join('?' for _ in value)})",
            tuple(value.values()),
        )
        return value

    def _insert_receipt(self, connection: sqlite3.Connection, core: dict[str, Any]) -> dict[str, Any]:
        value = {"receipt_id": f"receipt-{canonical_hash(core)[:32]}", **core}
        value["canonical_receipt_hash"] = canonical_hash(value)
        connection.execute(
            f"INSERT INTO workflow_receipts ({','.join(value)}) VALUES ({','.join('?' for _ in value)})",
            tuple(value.values()),
        )
        return value

    @staticmethod
    def _insert_claim(
        connection: sqlite3.Connection, value: Mapping[str, Any]
    ) -> None:
        connection.execute(
            f"INSERT INTO workflow_claims ({','.join(value)}) "
            f"VALUES ({','.join('?' for _ in value)})",
            tuple(value.values()),
        )

    @staticmethod
    def _delete_claim(connection: sqlite3.Connection, run_id: str) -> None:
        connection.execute("DELETE FROM workflow_claims WHERE run_id=?", (run_id,))

    def _claim_token_matches(self, supplied: str, expected: str) -> bool:
        return hmac.compare_digest(supplied, expected)
