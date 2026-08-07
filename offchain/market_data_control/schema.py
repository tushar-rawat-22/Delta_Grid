"""Exact SQLite schemas and deterministic schema fingerprints for Mission 99."""

from __future__ import annotations

import sqlite3
from typing import Any

from .core import ControlPlaneError, canonical_hash


CATALOGUE_APPLICATION_ID = 0x44474339  # DGC9
RELEASE_APPLICATION_ID = 0x44475239  # DGR9
CATALOGUE_USER_VERSION = 1
RELEASE_USER_VERSION = 1
JOURNAL_MODE = "DELETE"

CATALOGUE_DDL = """
CREATE TABLE catalogue_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE releases (
    release_id TEXT PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE,
    release_core_hash TEXT NOT NULL UNIQUE,
    certificate_core_hash TEXT NOT NULL,
    parent_release_id TEXT,
    synthetic_fixture INTEGER NOT NULL CHECK (synthetic_fixture IN (0, 1)),
    certified INTEGER NOT NULL CHECK (certified = 1),
    release_kind TEXT NOT NULL CHECK (release_kind = 'FULL_SNAPSHOT_V1'),
    legacy_proof_hash TEXT,
    FOREIGN KEY (parent_release_id) REFERENCES releases(release_id)
) WITHOUT ROWID;
CREATE TABLE incidents (
    incident_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    release_id TEXT,
    relative_path TEXT NOT NULL,
    evidence_hash TEXT NOT NULL
) WITHOUT ROWID;
"""

RELEASE_DDL = """
CREATE TABLE release_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE observations (
    record_hash TEXT PRIMARY KEY,
    logical_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    stream TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT,
    event_time TEXT NOT NULL,
    source_time TEXT,
    available_at TEXT,
    availability_class TEXT NOT NULL,
    availability_policy_id TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_verified_at TEXT NOT NULL,
    revision_number INTEGER NOT NULL,
    supersedes_record_hash TEXT,
    source_response_hash TEXT NOT NULL,
    receipt_hash TEXT NOT NULL,
    normalizer_id TEXT NOT NULL,
    normalized_payload_json TEXT NOT NULL,
    clock_health TEXT NOT NULL,
    UNIQUE (logical_id, revision_number)
) WITHOUT ROWID;
CREATE TABLE acquisition_receipts (
    receipt_hash TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    receipt_kind TEXT NOT NULL,
    source_response_hash TEXT NOT NULL UNIQUE,
    body_sha256 TEXT NOT NULL,
    compressed_object_sha256 TEXT NOT NULL,
    receipt_json TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE raw_object_refs (
    receipt_hash TEXT PRIMARY KEY,
    compressed_object_sha256 TEXT NOT NULL,
    body_sha256 TEXT NOT NULL,
    source_response_hash TEXT NOT NULL UNIQUE,
    FOREIGN KEY (receipt_hash) REFERENCES acquisition_receipts(receipt_hash)
) WITHOUT ROWID;
CREATE TABLE warnings (
    warning TEXT PRIMARY KEY
) WITHOUT ROWID;
CREATE TABLE quarantine (
    quarantine_hash TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    evidence_identity TEXT NOT NULL
) WITHOUT ROWID;
"""


def _apply_pragmas(conn: sqlite3.Connection, *, application_id: int, user_version: int) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = FULL")
    mode = str(conn.execute(f"PRAGMA journal_mode = {JOURNAL_MODE}").fetchone()[0]).upper()
    if mode not in {JOURNAL_MODE, "MEMORY"}:
        raise ControlPlaneError("SQLITE_JOURNAL_MODE_UNSUPPORTED", mode)
    conn.execute(f"PRAGMA application_id = {application_id}")
    conn.execute(f"PRAGMA user_version = {user_version}")


def initialize_schema(conn: sqlite3.Connection, kind: str) -> None:
    if kind == "catalogue":
        _apply_pragmas(
            conn,
            application_id=CATALOGUE_APPLICATION_ID,
            user_version=CATALOGUE_USER_VERSION,
        )
        conn.executescript(CATALOGUE_DDL)
    elif kind == "release":
        _apply_pragmas(
            conn,
            application_id=RELEASE_APPLICATION_ID,
            user_version=RELEASE_USER_VERSION,
        )
        conn.executescript(RELEASE_DDL)
    else:
        raise ControlPlaneError("SQLITE_SCHEMA_KIND_INVALID")


def _quote_identifier(value: str) -> str:
    """Quote one SQLite identifier without permitting statement injection."""

    if type(value) is not str or "\x00" in value:
        raise ControlPlaneError("SQLITE_IDENTIFIER_INVALID")
    return '"' + value.replace('"', '""') + '"'


def _normalized_sql(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().split())


def schema_descriptor(conn: sqlite3.Connection) -> dict[str, Any]:
    master_rows = conn.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    ).fetchall()
    objects = [
        {
            "type": row[0],
            "name": row[1],
            "table": row[2],
            "sql": _normalized_sql(row[3]),
        }
        for row in master_rows
    ]
    table_names = [row[1] for row in master_rows if row[0] == "table"]
    tables: dict[str, Any] = {}
    for table in table_names:
        columns = [
            {
                "cid": row[0],
                "name": row[1],
                "type": row[2],
                "notnull": row[3],
                "default": row[4],
                "pk": row[5],
            }
            for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table)})")
        ]
        indexes = []
        for row in conn.execute(f"PRAGMA index_list({_quote_identifier(table)})"):
            index_name = row[1]
            indexes.append(
                {
                    "seq": row[0],
                    "name": index_name,
                    "unique": row[2],
                    "origin": row[3],
                    "partial": row[4],
                    "columns": [
                        {"seqno": col[0], "cid": col[1], "name": col[2]}
                        for col in conn.execute(
                            f"PRAGMA index_info({_quote_identifier(index_name)})"
                        )
                    ],
                }
            )
        foreign_keys = [
            {
                "id": row[0],
                "seq": row[1],
                "table": row[2],
                "from": row[3],
                "to": row[4],
                "on_update": row[5],
                "on_delete": row[6],
                "match": row[7],
            }
            for row in conn.execute(
                f"PRAGMA foreign_key_list({_quote_identifier(table)})"
            )
        ]
        tables[table] = {
            "columns": columns,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
        }
    return {
        "application_id": conn.execute("PRAGMA application_id").fetchone()[0],
        "user_version": conn.execute("PRAGMA user_version").fetchone()[0],
        "objects": objects,
        "tables": tables,
    }


def expected_schema_descriptor(kind: str) -> dict[str, Any]:
    conn = sqlite3.connect(":memory:")
    try:
        initialize_schema(conn, kind)
        return schema_descriptor(conn)
    finally:
        conn.close()


def schema_fingerprint(conn: sqlite3.Connection) -> str:
    return canonical_hash(schema_descriptor(conn))


def expected_schema_fingerprint(kind: str) -> str:
    return canonical_hash(expected_schema_descriptor(kind))


def verify_exact_schema(conn: sqlite3.Connection, kind: str) -> str:
    actual = schema_descriptor(conn)
    expected = expected_schema_descriptor(kind)
    if actual != expected:
        raise ControlPlaneError(f"{kind.upper()}_SQLITE_SCHEMA_INVALID")
    database_rows = conn.execute("PRAGMA database_list").fetchall()
    main_path = next((str(row[2]) for row in database_rows if row[1] == "main"), "")
    journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).upper()
    if main_path and journal_mode != JOURNAL_MODE:
        raise ControlPlaneError(f"{kind.upper()}_SQLITE_JOURNAL_MODE_INVALID")
    synchronous = int(conn.execute("PRAGMA synchronous").fetchone()[0])
    if main_path and synchronous != 2:
        raise ControlPlaneError(f"{kind.upper()}_SQLITE_SYNCHRONOUS_INVALID")
    return canonical_hash(actual)
