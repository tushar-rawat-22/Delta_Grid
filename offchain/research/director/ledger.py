"""Append-only SQLite decision ledger with immutable root binding."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
import sqlite3
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterator, Mapping
from urllib.parse import quote

from offchain.research.admission import canonical_hash, canonical_json

from .action_registry import EXPLANATIONS, POLICY_OUTCOME_BY_RULE
from .evidence import (
    MISSION_93_HASH,
    MISSION_93_ID,
    MISSION_94_HASH,
    MISSION_94_ID,
    MISSION_95_HASH,
    MISSION_95_ID,
    MISSION_96A_HASH,
    MISSION_96A_ID,
    MISSION_96B_HASH,
    MISSION_96B_ID,
    MISSION_97_HASH,
    MISSION_97_ID,
    decode_json,
    parse_request,
    parse_utc,
    resolve_root,
    validate_identifier,
    validate_database_path,
    verify_contract_chain,
)
from .models import (
    DATABASE_SCHEMA_VERSION,
    DECISION_FIELDS,
    DEFAULT_BUSY_TIMEOUT_MS,
    MAX_BUSY_TIMEOUT_MS,
    MAX_RECORDED_DECISIONS,
    MIN_BUSY_TIMEOUT_MS,
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    REQUEST_FIELDS,
    SCHEMA_VERSION,
    VERIFICATION_FIELDS,
    DecisionPackage,
    DirectorError,
    DirectorRequest,
    EvidenceView,
    ResearchDecision,
    ResearchOpportunityDossier,
    VerificationReceipt,
)
from .verifier import ResearchDirectorVerifier


_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_DECISION_ID_RE = re.compile(r"decision-[0-9a-f]{32}\Z")
_NO_PROPOSAL_RULES = frozenset(
    {
        "RULE_1_UPSTREAM_INTEGRITY_STOP",
        "RULE_3_OBSERVATION_REFRESH",
        "RULE_4_NO_PROPOSAL",
    }
)
_FRESH_OBSERVATION_RULES = frozenset(
    {
        "RULE_4_NO_PROPOSAL",
        "RULE_5_MATERIAL_OVERLAP",
        "RULE_6_INTAKE_EVIDENCE_INCOMPLETE",
        "RULE_7_DRAFT_CONTRACT_REQUIRED",
        "RULE_8_FOUNDER_REVIEW",
    }
)

_TABLE_COLUMNS = {
    "director_metadata": (
        "schema_version", "repository_root", "repository_root_path_identity",
        "observation_root", "observation_root_path_identity", "input_root",
        "input_root_path_identity", "expected_repository_commit", "contract_id",
        "contract_hash", "maximum_recorded_decisions", "busy_timeout_ms",
        "created_at", "canonical_metadata_hash",
    ),
    "director_requests": (
        "request_id", "canonical_request_json", "canonical_request_hash",
        "canonical_row_hash",
    ),
    "director_decisions": (
        "decision_id", "request_id", "canonical_decision_json",
        "canonical_decision_hash", "canonical_row_hash",
    ),
    "director_verifications": (
        "verification_id", "decision_id", "canonical_verification_json",
        "canonical_verification_hash", "canonical_row_hash",
    ),
}
_PRIMARY_KEYS = {
    "director_metadata": ("schema_version",),
    "director_requests": ("request_id",),
    "director_decisions": ("decision_id",),
    "director_verifications": ("verification_id",),
}
_REQUIRED_INDEXES = {
    "director_requests_hash_idx",
    "director_decisions_request_idx",
    "director_decisions_hash_idx",
    "director_verifications_decision_idx",
    "director_verifications_hash_idx",
}
_REQUIRED_TRIGGERS = {
    f"{table}_{operation}"
    for table in _TABLE_COLUMNS
    for operation in ("no_update", "no_delete")
}
_CONTRACT_IDENTITIES = MappingProxyType(
    {
        "mission_93": (MISSION_93_ID, MISSION_93_HASH),
        "mission_94": (MISSION_94_ID, MISSION_94_HASH),
        "mission_95": (MISSION_95_ID, MISSION_95_HASH),
        "mission_96a": (MISSION_96A_ID, MISSION_96A_HASH),
        "mission_96b": (MISSION_96B_ID, MISSION_96B_HASH),
        "mission_97": (MISSION_97_ID, MISSION_97_HASH),
        "mission_98": (MISSION_CONTRACT_ID, MISSION_CONTRACT_HASH),
    }
)

SCHEMA_SQL = """
CREATE TABLE director_metadata (
 schema_version INTEGER PRIMARY KEY NOT NULL,
 repository_root TEXT NOT NULL,
 repository_root_path_identity TEXT NOT NULL,
 observation_root TEXT NOT NULL,
 observation_root_path_identity TEXT NOT NULL,
 input_root TEXT NOT NULL,
 input_root_path_identity TEXT NOT NULL,
 expected_repository_commit TEXT NOT NULL,
 contract_id TEXT NOT NULL,
 contract_hash TEXT NOT NULL,
 maximum_recorded_decisions INTEGER NOT NULL,
 busy_timeout_ms INTEGER NOT NULL,
 created_at TEXT NOT NULL,
 canonical_metadata_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE director_requests (
 request_id TEXT PRIMARY KEY NOT NULL,
 canonical_request_json TEXT NOT NULL,
 canonical_request_hash TEXT NOT NULL,
 canonical_row_hash TEXT NOT NULL UNIQUE
);
CREATE UNIQUE INDEX director_requests_hash_idx
 ON director_requests(canonical_request_hash);
CREATE TABLE director_decisions (
 decision_id TEXT PRIMARY KEY NOT NULL,
 request_id TEXT NOT NULL REFERENCES director_requests(request_id),
 canonical_decision_json TEXT NOT NULL,
 canonical_decision_hash TEXT NOT NULL,
 canonical_row_hash TEXT NOT NULL UNIQUE
);
CREATE UNIQUE INDEX director_decisions_request_idx
 ON director_decisions(request_id);
CREATE UNIQUE INDEX director_decisions_hash_idx
 ON director_decisions(canonical_decision_hash);
CREATE TABLE director_verifications (
 verification_id TEXT PRIMARY KEY NOT NULL,
 decision_id TEXT NOT NULL REFERENCES director_decisions(decision_id),
 canonical_verification_json TEXT NOT NULL,
 canonical_verification_hash TEXT NOT NULL,
 canonical_row_hash TEXT NOT NULL UNIQUE
);
CREATE UNIQUE INDEX director_verifications_decision_idx
 ON director_verifications(decision_id);
CREATE UNIQUE INDEX director_verifications_hash_idx
 ON director_verifications(canonical_verification_hash);
CREATE TRIGGER director_metadata_no_update BEFORE UPDATE ON director_metadata
 BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER director_metadata_no_delete BEFORE DELETE ON director_metadata
 BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER director_requests_no_update BEFORE UPDATE ON director_requests
 BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER director_requests_no_delete BEFORE DELETE ON director_requests
 BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER director_decisions_no_update BEFORE UPDATE ON director_decisions
 BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER director_decisions_no_delete BEFORE DELETE ON director_decisions
 BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER director_verifications_no_update BEFORE UPDATE ON director_verifications
 BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER director_verifications_no_delete BEFORE DELETE ON director_verifications
 BEGIN SELECT RAISE(ABORT, 'immutable'); END;
PRAGMA user_version = 1;
"""


def _path_identity(path: Path) -> str:
    return f"sha256:{canonical_hash({'absolute_path': str(path)})}"


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _validate_busy_timeout(value: Any) -> int:
    if (
        type(value) is not int
        or not MIN_BUSY_TIMEOUT_MS <= value <= MAX_BUSY_TIMEOUT_MS
    ):
        raise DirectorError(
            "DIRECTOR_INPUT_INVALID",
            "busy_timeout_ms must be an integer from 100 through 30000.",
        )
    return value


def _schema_inventory(
    connection: sqlite3.Connection,
) -> tuple[tuple[str, str, str, str], ...]:
    """Return SQLite's stored SQL for every user-defined schema object."""

    rows = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_schema "
        "WHERE type IN ('table', 'index', 'trigger') "
        "AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type, name, tbl_name, sql"
    ).fetchall()
    if any(type(row["sql"]) is not str for row in rows):
        raise ValueError("schema SQL")
    return tuple(
        (
            str(row["type"]),
            str(row["name"]),
            str(row["tbl_name"]),
            str(row["sql"]),
        )
        for row in rows
    )


def _reference_schema_inventory() -> tuple[
    tuple[str, str, str, str], ...
]:
    reference = sqlite3.connect(":memory:", isolation_level=None)
    reference.row_factory = sqlite3.Row
    try:
        reference.executescript(SCHEMA_SQL)
        return _schema_inventory(reference)
    finally:
        reference.close()


class ResearchDirectorLedger:
    """Verified local append-only storage for complete decision packages."""

    def __init__(self, database_path: Path | str) -> None:
        self._database_path = validate_database_path(
            database_path, permit_missing=False
        )
        self._busy_timeout_ms = DEFAULT_BUSY_TIMEOUT_MS
        with self._connection(configure_from_metadata=False) as connection:
            self._verify_schema(connection)
            preliminary = connection.execute(
                "SELECT * FROM director_metadata"
            ).fetchall()
            if len(preliminary) != 1:
                raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE")
            busy_timeout = preliminary[0]["busy_timeout_ms"]
            if (
                type(busy_timeout) is not int
                or not MIN_BUSY_TIMEOUT_MS
                <= busy_timeout
                <= MAX_BUSY_TIMEOUT_MS
            ):
                raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
            self._busy_timeout_ms = busy_timeout
        with self._connection() as connection:
            self._metadata = self._load_metadata(connection)
        self._repository_root = resolve_root(
            self._metadata["repository_root"],
            reason="GOVERNANCE_CONTRACT_INTEGRITY_FAILURE",
        )
        self._observation_root = resolve_root(
            self._metadata["observation_root"],
            reason="DIRECTOR_PATH_UNSAFE",
        )
        self._input_root = resolve_root(
            self._metadata["input_root"],
            reason="DIRECTOR_PATH_UNSAFE",
        )
        if (
            self._metadata["repository_root_path_identity"]
            != _path_identity(self._repository_root)
            or self._metadata["observation_root_path_identity"]
            != _path_identity(self._observation_root)
            or self._metadata["input_root_path_identity"]
            != _path_identity(self._input_root)
        ):
            raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
        verify_contract_chain(self._repository_root)

    @classmethod
    def initialize(
        cls,
        *,
        database_path: Path | str,
        observation_root: Path | str,
        input_root: Path | str,
        repository_root: Path | str,
        expected_repository_commit: str,
        created_at: str,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> ResearchDirectorLedger:
        _validate_busy_timeout(busy_timeout_ms)
        parse_utc(created_at)
        if (
            type(expected_repository_commit) is not str
            or _COMMIT_RE.fullmatch(expected_repository_commit) is None
        ):
            raise DirectorError("DIRECTOR_INPUT_INVALID")
        repository = resolve_root(
            repository_root, reason="GOVERNANCE_CONTRACT_INTEGRITY_FAILURE"
        )
        observation = resolve_root(
            observation_root, reason="DIRECTOR_PATH_UNSAFE"
        )
        inputs = resolve_root(input_root, reason="DIRECTOR_PATH_UNSAFE")
        verify_contract_chain(repository)
        database = validate_database_path(database_path, permit_missing=True)
        core = {
            "schema_version": DATABASE_SCHEMA_VERSION,
            "repository_root": str(repository),
            "repository_root_path_identity": _path_identity(repository),
            "observation_root": str(observation),
            "observation_root_path_identity": _path_identity(observation),
            "input_root": str(inputs),
            "input_root_path_identity": _path_identity(inputs),
            "expected_repository_commit": expected_repository_commit,
            "contract_id": MISSION_CONTRACT_ID,
            "contract_hash": MISSION_CONTRACT_HASH,
            "maximum_recorded_decisions": MAX_RECORDED_DECISIONS,
            "busy_timeout_ms": busy_timeout_ms,
            "created_at": created_at,
        }
        expected_metadata = {**core, "canonical_metadata_hash": canonical_hash(core)}
        if database.exists():
            existing = cls(database)
            if dict(existing.metadata) != expected_metadata:
                raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE")
            return existing
        try:
            connection = sqlite3.connect(
                str(database), isolation_level=None, timeout=0
            )
            connection.row_factory = sqlite3.Row
            try:
                if (
                    str(
                        connection.execute(
                            "PRAGMA journal_mode = DELETE"
                        ).fetchone()[0]
                    ).lower()
                    != "delete"
                ):
                    raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE")
                connection.execute("PRAGMA synchronous = EXTRA")
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
                if (
                    int(connection.execute("PRAGMA synchronous").fetchone()[0]) != 3
                    or int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
                    != 1
                    or int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
                    != busy_timeout_ms
                ):
                    raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE")
                connection.executescript(SCHEMA_SQL)
                columns = ",".join(expected_metadata)
                placeholders = ",".join("?" for _ in expected_metadata)
                connection.execute(
                    f"INSERT INTO director_metadata ({columns}) VALUES ({placeholders})",
                    tuple(expected_metadata.values()),
                )
            finally:
                connection.close()
        except DirectorError:
            raise
        except (OSError, sqlite3.DatabaseError) as error:
            raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE") from error
        return cls(database)

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def metadata(self) -> Mapping[str, Any]:
        return MappingProxyType(dict(self._metadata))

    def evidence_loader(self) -> Any:
        from .evidence import ResearchDirectorEvidenceLoader

        return ResearchDirectorEvidenceLoader(
            repository_root=self._repository_root,
            observation_root=self._observation_root,
            input_root=self._input_root,
            expected_repository_commit=self._metadata[
                "expected_repository_commit"
            ],
        )

    @contextmanager
    def _connection(
        self, *, configure_from_metadata: bool = True
    ) -> Iterator[sqlite3.Connection]:
        encoded = quote(str(self._database_path), safe="/")
        try:
            connection = sqlite3.connect(
                f"file:{encoded}?mode=rw",
                uri=True,
                isolation_level=None,
                timeout=0,
            )
        except sqlite3.DatabaseError as error:
            raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE") from error
        connection.row_factory = sqlite3.Row
        timeout = (
            self._busy_timeout_ms
            if configure_from_metadata
            else DEFAULT_BUSY_TIMEOUT_MS
        )
        try:
            if (
                str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
                != "delete"
            ):
                raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE")
            connection.execute("PRAGMA synchronous = EXTRA")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {timeout}")
            if (
                int(connection.execute("PRAGMA synchronous").fetchone()[0]) != 3
                or int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) != 1
                or int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
                != timeout
            ):
                raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE")
            yield connection
        except sqlite3.OperationalError as error:
            if "locked" in str(error).lower() or "busy" in str(error).lower():
                raise DirectorError("DIRECTOR_DATABASE_BUSY") from error
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
            except Exception:
                connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        try:
            if (
                int(connection.execute("PRAGMA user_version").fetchone()[0])
                != DATABASE_SCHEMA_VERSION
            ):
                raise ValueError("schema version")
            if _schema_inventory(connection) != _reference_schema_inventory():
                raise ValueError("schema definition inventory")
            tables = {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if tables != set(_TABLE_COLUMNS):
                raise ValueError("table inventory")
            integer_fields = {
                "schema_version", "maximum_recorded_decisions", "busy_timeout_ms"
            }
            for table, expected_columns in _TABLE_COLUMNS.items():
                rows = connection.execute(
                    f'PRAGMA table_xinfo("{table}")'
                ).fetchall()
                if tuple(str(row["name"]) for row in rows) != expected_columns:
                    raise ValueError("column inventory")
                if any(
                    str(row["type"]).upper()
                    != (
                        "INTEGER"
                        if str(row["name"]) in integer_fields
                        else "TEXT"
                    )
                    or int(row["notnull"]) != 1
                    or int(row["hidden"]) != 0
                    for row in rows
                ):
                    raise ValueError("column declaration")
                primary = tuple(
                    str(row["name"])
                    for row in sorted(rows, key=lambda item: int(item["pk"]))
                    if int(row["pk"]) > 0
                )
                if primary != _PRIMARY_KEYS[table]:
                    raise ValueError("primary key")
            indexes = {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema "
                    "WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
                )
            }
            triggers = {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema WHERE type='trigger'"
                )
            }
            if indexes != _REQUIRED_INDEXES or triggers != _REQUIRED_TRIGGERS:
                raise ValueError("index or trigger inventory")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("foreign key")
            expected_foreign = {
                ("director_decisions", "request_id", "director_requests", "request_id"),
                (
                    "director_verifications",
                    "decision_id",
                    "director_decisions",
                    "decision_id",
                ),
            }
            actual_foreign = {
                (table, str(row["from"]), str(row["table"]), str(row["to"]))
                for table in _TABLE_COLUMNS
                for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')
            }
            if actual_foreign != expected_foreign:
                raise ValueError("foreign key schema")
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise DirectorError("DIRECTOR_SCHEMA_INCOMPATIBLE") from error

    @staticmethod
    def _load_metadata(connection: sqlite3.Connection) -> dict[str, Any]:
        try:
            rows = connection.execute(
                "SELECT * FROM director_metadata"
            ).fetchall()
            if len(rows) != 1:
                raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
            value = _row_dict(rows[0])
            supplied = value.pop("canonical_metadata_hash")
            if (
                canonical_hash(value) != supplied
                or value["schema_version"] != DATABASE_SCHEMA_VERSION
                or value["contract_id"] != MISSION_CONTRACT_ID
                or value["contract_hash"] != MISSION_CONTRACT_HASH
                or value["maximum_recorded_decisions"]
                != MAX_RECORDED_DECISIONS
                or type(value["busy_timeout_ms"]) is not int
                or not MIN_BUSY_TIMEOUT_MS
                <= value["busy_timeout_ms"]
                <= MAX_BUSY_TIMEOUT_MS
                or type(value["expected_repository_commit"]) is not str
                or _COMMIT_RE.fullmatch(
                    value["expected_repository_commit"]
                )
                is None
            ):
                raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
            _validate_busy_timeout(value["busy_timeout_ms"])
            parse_utc(
                value["created_at"],
                reason="DIRECTOR_ROW_INTEGRITY_FAILURE",
            )
            value["canonical_metadata_hash"] = supplied
            return value
        except DirectorError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise DirectorError(
                "DIRECTOR_ROW_INTEGRITY_FAILURE"
            ) from error

    @staticmethod
    def _request_row(request: DirectorRequest) -> dict[str, Any]:
        value = request.as_dict()
        core = {
            "request_id": value["request_id"],
            "canonical_request_json": canonical_json(value),
            "canonical_request_hash": value["canonical_request_hash"],
        }
        return {**core, "canonical_row_hash": canonical_hash(core)}

    @staticmethod
    def _decision_row(decision: ResearchDecision) -> dict[str, Any]:
        value = decision.as_dict()
        core = {
            "decision_id": value["decision_id"],
            "request_id": value["request_id"],
            "canonical_decision_json": canonical_json(value),
            "canonical_decision_hash": value["canonical_decision_hash"],
        }
        return {**core, "canonical_row_hash": canonical_hash(core)}

    @staticmethod
    def _verification_row(receipt: VerificationReceipt) -> dict[str, Any]:
        value = receipt.as_dict()
        core = {
            "verification_id": value["verification_id"],
            "decision_id": value["decision_id"],
            "canonical_verification_json": canonical_json(value),
            "canonical_verification_hash": value["canonical_verification_hash"],
        }
        return {**core, "canonical_row_hash": canonical_hash(core)}

    @staticmethod
    def _insert(connection: sqlite3.Connection, table: str, value: Mapping[str, Any]) -> None:
        columns = ",".join(value)
        placeholders = ",".join("?" for _ in value)
        connection.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
            tuple(value.values()),
        )

    def _validate_package_semantics(
        self,
        request: DirectorRequest,
        decision: ResearchDecision,
        receipt: VerificationReceipt,
        *,
        reason: str,
    ) -> None:
        try:
            if (
                not isinstance(request, DirectorRequest)
                or not isinstance(decision, ResearchDecision)
                or not isinstance(receipt, VerificationReceipt)
            ):
                raise ValueError("model type")
            request_value = request.as_dict()
            decision_value = decision.as_dict()
            receipt_value = receipt.as_dict()
            strict_request = parse_request(
                canonical_json(request_value).encode("utf-8"),
                expected_commit=self._metadata[
                    "expected_repository_commit"
                ],
            ).as_dict()
            if (
                strict_request != request_value
                or request_value["repository_commit"]
                != self._metadata["expected_repository_commit"]
                or request_value["controlling_contract_id"]
                != MISSION_CONTRACT_ID
                or request_value["controlling_contract_hash"]
                != MISSION_CONTRACT_HASH
            ):
                raise ValueError("request semantics")

            if (
                set(decision_value) != set(DECISION_FIELDS)
                or decision_value["schema_version"] != SCHEMA_VERSION
            ):
                raise ValueError("decision schema")
            decision_hash_core = dict(decision_value)
            supplied_decision_hash = decision_hash_core.pop(
                "canonical_decision_hash", None
            )
            if (
                type(supplied_decision_hash) is not str
                or _HASH_RE.fullmatch(supplied_decision_hash) is None
                or canonical_hash(decision_hash_core)
                != supplied_decision_hash
            ):
                raise ValueError("decision hash")
            if (
                decision_value["request_id"] != request_value["request_id"]
                or decision_value["repository_commit"]
                != request_value["repository_commit"]
                or decision_value["repository_commit"]
                != self._metadata["expected_repository_commit"]
                or decision_value["requested_by"]
                != request_value["requested_by"]
                or decision_value["decision_as_of"]
                != request_value["decision_as_of"]
                or decision_value["observation_manifest_byte_hash"]
                != request_value["observation_manifest_sha256"]
            ):
                raise ValueError("decision relationship")
            if (
                type(
                    decision_value["observation_snapshot_canonical_hash"]
                )
                is not str
                or _HASH_RE.fullmatch(
                    decision_value["observation_snapshot_canonical_hash"]
                )
                is None
            ):
                raise ValueError("observation snapshot hash")
            observation_as_of = parse_utc(
                decision_value["observation_as_of"],
                reason=reason,
            )
            requested_at = parse_utc(
                request_value["requested_at"],
                reason=reason,
            )
            decision_as_of = parse_utc(
                request_value["decision_as_of"],
                reason=reason,
            )
            if not (
                observation_as_of <= requested_at <= decision_as_of
            ):
                raise ValueError("observation timestamp order")

            rule = decision_value["winning_rule_id"]
            action = decision_value["selected_action_id"]
            policy_reason = decision_value["reason_token"]
            if (
                type(rule) is not str
                or POLICY_OUTCOME_BY_RULE.get(rule)
                != (action, policy_reason)
                or EXPLANATIONS.get((action, policy_reason))
                != decision_value["human_explanation"]
            ):
                raise ValueError("policy outcome")
            for mission, identity in _CONTRACT_IDENTITIES.items():
                if (
                    decision_value[f"{mission}_contract_id"],
                    decision_value[f"{mission}_contract_hash"],
                ) != identity:
                    raise ValueError("contract identity")

            proposal_path = request_value["proposal_relative_path"]
            proposal_hash = request_value["proposal_sha256"]
            if proposal_path is None and proposal_hash is None:
                if (
                    decision_value["proposal_id"] is not None
                    or decision_value["proposal_byte_hash"] is not None
                    or rule not in _NO_PROPOSAL_RULES
                ):
                    raise ValueError("proposal compatibility")
            elif proposal_path is not None and proposal_hash is not None:
                validate_identifier(decision_value["proposal_id"])
                if (
                    decision_value["proposal_byte_hash"] != proposal_hash
                    or rule == "RULE_4_NO_PROPOSAL"
                ):
                    raise ValueError("proposal compatibility")
            else:
                raise ValueError("request proposal pairing")
            if (
                rule in _FRESH_OBSERVATION_RULES
                and decision_as_of - observation_as_of
                > timedelta(seconds=86_400)
            ):
                raise ValueError("freshness precedence")

            decision_identity_core = dict(decision_value)
            decision_identity_core.pop("decision_id")
            decision_identity_core.pop("canonical_decision_hash")
            if decision_value["decision_id"] != (
                f"decision-{canonical_hash(decision_identity_core)[:32]}"
            ):
                raise ValueError("decision identity")

            if (
                set(receipt_value) != set(VERIFICATION_FIELDS)
                or receipt_value["schema_version"] != SCHEMA_VERSION
            ):
                raise ValueError("verification schema")
            receipt_hash_core = dict(receipt_value)
            supplied_receipt_hash = receipt_hash_core.pop(
                "canonical_verification_hash", None
            )
            if (
                type(supplied_receipt_hash) is not str
                or _HASH_RE.fullmatch(supplied_receipt_hash) is None
                or canonical_hash(receipt_hash_core)
                != supplied_receipt_hash
                or receipt_value["decision_id"]
                != decision_value["decision_id"]
                or receipt_value["decision_hash"]
                != decision_value["canonical_decision_hash"]
                or receipt_value["verification_token"] != "VERIFIED"
                or type(receipt_value["verifier_version"]) is not int
                or receipt_value["verifier_version"] != 1
                or receipt_value["verified_at"]
                != decision_value["decision_as_of"]
                or receipt_value["independently_recomputed_action_id"]
                != action
                or receipt_value["independently_recomputed_reason_token"]
                != policy_reason
                or receipt_value["independently_recomputed_rule_id"] != rule
            ):
                raise ValueError("verification semantics")
            receipt_identity_core = dict(receipt_value)
            receipt_identity_core.pop("verification_id")
            receipt_identity_core.pop("canonical_verification_hash")
            if receipt_value["verification_id"] != (
                f"verification-{canonical_hash(receipt_identity_core)[:32]}"
            ):
                raise ValueError("verification identity")
        except (DirectorError, KeyError, TypeError, ValueError) as error:
            raise DirectorError(reason) from error

    def _record_verified_package(
        self,
        request: DirectorRequest,
        dossier: ResearchOpportunityDossier | None,
        evidence: EvidenceView,
        decision: ResearchDecision,
    ) -> DecisionPackage:
        receipt = ResearchDirectorVerifier().verify(
            request=request,
            dossier=dossier,
            evidence=evidence,
            decision=decision,
        )
        try:
            with self._mutation() as connection:
                self._validate_package_semantics(
                    request,
                    decision,
                    receipt,
                    reason="DECISION_INTEGRITY_FAILURE",
                )
                request_row = self._request_row(request)
                decision_row = self._decision_row(decision)
                verification_row = self._verification_row(receipt)
                expected_package = DecisionPackage(
                    request, decision, receipt
                )
                existing = connection.execute(
                    "SELECT d.decision_id FROM director_requests AS r "
                    "LEFT JOIN director_decisions AS d ON d.request_id=r.request_id "
                    "WHERE r.request_id=?",
                    (request_row["request_id"],),
                ).fetchone()
                if existing is not None:
                    existing_package = self._package_from_connection(
                        connection, decision_id=existing["decision_id"]
                    )
                    if (
                        existing_package.as_dict()
                        != expected_package.as_dict()
                    ):
                        raise DirectorError("REQUEST_ID_CONFLICT")
                    return existing_package
                conflict = connection.execute(
                    "SELECT canonical_decision_json FROM director_decisions "
                    "WHERE decision_id=?",
                    (decision_row["decision_id"],),
                ).fetchone()
                if conflict is not None:
                    raise DirectorError("DECISION_ID_CONFLICT")
                count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM director_decisions"
                    ).fetchone()[0]
                )
                if count >= MAX_RECORDED_DECISIONS:
                    raise DirectorError("DECISION_BUDGET_EXHAUSTED")
                self._insert(connection, "director_requests", request_row)
                self._insert(connection, "director_decisions", decision_row)
                self._insert(
                    connection, "director_verifications", verification_row
                )
        except sqlite3.IntegrityError as error:
            raise DirectorError("DECISION_ID_CONFLICT") from error
        return DecisionPackage(request, decision, receipt)

    @staticmethod
    def _verify_json_hash(
        raw_text: Any,
        *,
        expected_fields: tuple[str, ...],
        hash_field: str,
    ) -> dict[str, Any]:
        if type(raw_text) is not str:
            raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
        value = decode_json(
            raw_text.encode("utf-8"),
            max_bytes=1_048_576,
            reason="DIRECTOR_ROW_INTEGRITY_FAILURE",
        )
        if type(value) is not dict or set(value) != set(expected_fields):
            raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
        core = dict(value)
        supplied = core.pop(hash_field, None)
        if (
            type(supplied) is not str
            or _HASH_RE.fullmatch(supplied) is None
            or canonical_hash(core) != supplied
        ):
            raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
        return value

    def _package_from_connection(
        self, connection: sqlite3.Connection, *, decision_id: str
    ) -> DecisionPackage:
        try:
            return self._package_from_connection_unchecked(
                connection,
                decision_id=decision_id,
            )
        except DirectorError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise DirectorError(
                "DIRECTOR_ROW_INTEGRITY_FAILURE"
            ) from error

    def _package_from_connection_unchecked(
        self, connection: sqlite3.Connection, *, decision_id: str
    ) -> DecisionPackage:
        decision_rows = connection.execute(
            "SELECT * FROM director_decisions WHERE decision_id=?",
            (decision_id,),
        ).fetchall()
        if not decision_rows:
            raise DirectorError("DECISION_NOT_FOUND")
        if len(decision_rows) != 1:
            raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
        decision_row = _row_dict(decision_rows[0])
        request_rows = connection.execute(
            "SELECT * FROM director_requests WHERE request_id=?",
            (decision_row["request_id"],),
        ).fetchall()
        verification_rows = connection.execute(
            "SELECT * FROM director_verifications WHERE decision_id=?",
            (decision_id,),
        ).fetchall()
        if len(request_rows) != 1 or len(verification_rows) != 1:
            raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
        request_row = _row_dict(request_rows[0])
        verification_row = _row_dict(verification_rows[0])

        request = self._verify_json_hash(
            request_row["canonical_request_json"],
            expected_fields=REQUEST_FIELDS,
            hash_field="canonical_request_hash",
        )
        decision = self._verify_json_hash(
            decision_row["canonical_decision_json"],
            expected_fields=DECISION_FIELDS,
            hash_field="canonical_decision_hash",
        )
        verification = self._verify_json_hash(
            verification_row["canonical_verification_json"],
            expected_fields=VERIFICATION_FIELDS,
            hash_field="canonical_verification_hash",
        )

        for stored_row in (
            request_row,
            decision_row,
            verification_row,
        ):
            row_hash_core = dict(stored_row)
            supplied_row_hash = row_hash_core.pop("canonical_row_hash")
            if (
                type(supplied_row_hash) is not str
                or _HASH_RE.fullmatch(supplied_row_hash) is None
                or canonical_hash(row_hash_core) != supplied_row_hash
            ):
                raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
        if (
            request["request_id"] != request_row["request_id"]
            or request["canonical_request_hash"]
            != request_row["canonical_request_hash"]
            or decision["decision_id"] != decision_row["decision_id"]
            or decision["request_id"] != decision_row["request_id"]
            or decision["canonical_decision_hash"]
            != decision_row["canonical_decision_hash"]
            or verification["verification_id"]
            != verification_row["verification_id"]
            or verification["decision_id"]
            != verification_row["decision_id"]
            or verification["canonical_verification_hash"]
            != verification_row["canonical_verification_hash"]
        ):
            raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
        package = DecisionPackage(
            request=DirectorRequest(request),
            decision=ResearchDecision(decision),
            verification_receipt=VerificationReceipt(verification),
        )
        self._validate_package_semantics(
            package.request,
            package.decision,
            package.verification_receipt,
            reason="DIRECTOR_ROW_INTEGRITY_FAILURE",
        )
        return package

    def get_package(self, decision_id: str) -> DecisionPackage:
        if (
            type(decision_id) is not str
            or _DECISION_ID_RE.fullmatch(decision_id) is None
        ):
            raise DirectorError("DIRECTOR_INPUT_INVALID")
        with self._connection() as connection:
            return self._package_from_connection(
                connection, decision_id=decision_id
            )

    def list_packages(self) -> tuple[DecisionPackage, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT decision_id FROM director_decisions"
            ).fetchall()
            if len(rows) > MAX_RECORDED_DECISIONS:
                raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
            decision_ids = []
            for row in rows:
                if type(row["decision_id"]) is not str:
                    raise DirectorError(
                        "DIRECTOR_ROW_INTEGRITY_FAILURE"
                    )
                decision_ids.append(row["decision_id"])
            packages = [
                self._package_from_connection(
                    connection, decision_id=decision_id
                )
                for decision_id in decision_ids
            ]
        packages.sort(
            key=lambda item: (
                item.decision.as_dict()["decision_as_of"],
                item.decision.as_dict()["decision_id"],
            )
        )
        return tuple(packages)

    def _verify_bound_metadata(self, metadata: Mapping[str, Any]) -> None:
        if (
            dict(metadata) != self._metadata
            or metadata["schema_version"] != DATABASE_SCHEMA_VERSION
            or metadata["expected_repository_commit"]
            != self._metadata["expected_repository_commit"]
            or metadata["contract_id"] != MISSION_CONTRACT_ID
            or metadata["contract_hash"] != MISSION_CONTRACT_HASH
            or metadata["maximum_recorded_decisions"]
            != MAX_RECORDED_DECISIONS
            or metadata["busy_timeout_ms"] != self._busy_timeout_ms
        ):
            raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
        parse_utc(
            metadata["created_at"],
            reason="DIRECTOR_ROW_INTEGRITY_FAILURE",
        )
        repository_root = resolve_root(
            metadata["repository_root"],
            reason="DIRECTOR_ROW_INTEGRITY_FAILURE",
        )
        observation_root = resolve_root(
            metadata["observation_root"],
            reason="DIRECTOR_ROW_INTEGRITY_FAILURE",
        )
        input_root = resolve_root(
            metadata["input_root"],
            reason="DIRECTOR_ROW_INTEGRITY_FAILURE",
        )
        if (
            repository_root != self._repository_root
            or observation_root != self._observation_root
            or input_root != self._input_root
            or metadata["repository_root_path_identity"]
            != _path_identity(repository_root)
            or metadata["observation_root_path_identity"]
            != _path_identity(observation_root)
            or metadata["input_root_path_identity"]
            != _path_identity(input_root)
        ):
            raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
        identities = verify_contract_chain(repository_root)
        if dict(identities) != dict(_CONTRACT_IDENTITIES):
            raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")

    def verify_full_ledger(self) -> Mapping[str, Any]:
        with self._connection() as connection:
            self._verify_schema(connection)
            metadata = self._load_metadata(connection)
            self._verify_bound_metadata(metadata)
            counts = {
                table: int(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
                for table in (
                    "director_requests",
                    "director_decisions",
                    "director_verifications",
                )
            }
            if (
                len(set(counts.values())) != 1
                or counts["director_decisions"] > MAX_RECORDED_DECISIONS
                or connection.execute("PRAGMA foreign_key_check").fetchall()
            ):
                raise DirectorError("DIRECTOR_ROW_INTEGRITY_FAILURE")
            decision_ids = []
            for row in connection.execute(
                "SELECT decision_id FROM director_decisions"
            ):
                if type(row["decision_id"]) is not str:
                    raise DirectorError(
                        "DIRECTOR_ROW_INTEGRITY_FAILURE"
                    )
                decision_ids.append(row["decision_id"])
            for decision_id in decision_ids:
                self._package_from_connection(
                    connection, decision_id=decision_id
                )
        return MappingProxyType(
            {
                "status": "LEDGER_VERIFIED",
                "decision_count": counts["director_decisions"],
                "maximum_recorded_decisions": MAX_RECORDED_DECISIONS,
                "canonical_metadata_hash": metadata[
                    "canonical_metadata_hash"
                ],
            }
        )
