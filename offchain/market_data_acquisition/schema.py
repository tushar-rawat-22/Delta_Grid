"""Exact SQLite schema for the Mission 100 acquisition journal."""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Iterable

from .core import AcquisitionError


APPLICATION_ID = 100100
USER_VERSION = 1
JOURNAL_DDL = f"""
PRAGMA application_id={APPLICATION_ID};
PRAGMA user_version={USER_VERSION};
PRAGMA foreign_keys=ON;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE capture_batches (
    batch_id TEXT PRIMARY KEY,
    contract_hash TEXT NOT NULL,
    code_commit TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('RUNNING','COMPLETE','FAILED')),
    environment_json TEXT NOT NULL,
    environment_hash TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0 CHECK(request_count >= 0),
    receipt_count INTEGER NOT NULL DEFAULT 0 CHECK(receipt_count >= 0),
    observation_count INTEGER NOT NULL DEFAULT 0 CHECK(observation_count >= 0),
    error_reason TEXT
);

CREATE TABLE raw_objects (
    object_sha256 TEXT PRIMARY KEY,
    body_sha256 TEXT NOT NULL,
    compressed_bytes INTEGER NOT NULL CHECK(compressed_bytes >= 0),
    decompressed_bytes INTEGER NOT NULL CHECK(decompressed_bytes >= 0),
    relative_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE receipts (
    receipt_hash TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES capture_batches(batch_id),
    request_id TEXT NOT NULL,
    host TEXT NOT NULL,
    path TEXT NOT NULL,
    params_json TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    wall_start_ms INTEGER NOT NULL,
    wall_end_ms INTEGER NOT NULL,
    monotonic_duration_ms INTEGER NOT NULL,
    clock_status TEXT NOT NULL,
    http_status INTEGER NOT NULL,
    headers_json TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    retry_exhausted INTEGER NOT NULL CHECK(retry_exhausted IN (0,1)),
    body_sha256 TEXT NOT NULL,
    object_sha256 TEXT NOT NULL REFERENCES raw_objects(object_sha256),
    response_hash TEXT NOT NULL,
    UNIQUE(batch_id, request_id, attempt_number)
) WITHOUT ROWID;

CREATE INDEX idx_receipts_batch ON receipts(batch_id);
CREATE INDEX idx_receipts_response ON receipts(response_hash);

CREATE TABLE observations (
    record_hash TEXT PRIMARY KEY,
    logical_id TEXT NOT NULL,
    revision_number INTEGER NOT NULL CHECK(revision_number >= 1),
    supersedes_record_hash TEXT REFERENCES observations(record_hash),
    batch_id TEXT NOT NULL REFERENCES capture_batches(batch_id),
    receipt_hash TEXT NOT NULL REFERENCES receipts(receipt_hash),
    stream TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT,
    event_time_ms INTEGER NOT NULL,
    available_at TEXT NOT NULL,
    response_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(logical_id, revision_number)
) WITHOUT ROWID;

CREATE INDEX idx_observations_lookup
ON observations(stream, symbol, event_time_ms, revision_number);
CREATE INDEX idx_observations_batch ON observations(batch_id);

CREATE TABLE checkpoints (
    stream TEXT NOT NULL,
    symbol TEXT NOT NULL,
    next_event_time_ms INTEGER NOT NULL,
    last_success_batch_id TEXT NOT NULL REFERENCES capture_batches(batch_id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(stream, symbol)
) WITHOUT ROWID;

CREATE TABLE funding_configs (
    symbol TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    funding_interval_hours INTEGER,
    funding_rate_cap TEXT,
    funding_rate_floor TEXT,
    receipt_hash TEXT NOT NULL REFERENCES receipts(receipt_hash),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    PRIMARY KEY(symbol, observed_at, receipt_hash)
) WITHOUT ROWID;
""".strip()

EXPECTED_TABLES = {
    "metadata",
    "capture_batches",
    "raw_objects",
    "receipts",
    "observations",
    "checkpoints",
    "funding_configs",
}
EXPECTED_INDEXES = {
    "idx_receipts_batch",
    "idx_receipts_response",
    "idx_observations_lookup",
    "idx_observations_batch",
}


def _normalize_sql(sql: str | None) -> str:
    if not sql:
        return ""
    return " ".join(sql.strip().split())


def schema_fingerprint(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ).fetchall()
    payload = "\n".join(
        "|".join((str(row[0]), str(row[1]), str(row[2]), _normalize_sql(row[3])))
        for row in rows
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _compute_expected_fingerprint() -> str:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(JOURNAL_DDL)
        return schema_fingerprint(conn)
    finally:
        conn.close()


EXPECTED_SCHEMA_FINGERPRINT = _compute_expected_fingerprint()


def initialize_schema(conn: sqlite3.Connection) -> str:
    conn.executescript(JOURNAL_DDL)
    conn.commit()
    fingerprint = schema_fingerprint(conn)
    if fingerprint != EXPECTED_SCHEMA_FINGERPRINT:
        raise AcquisitionError("JOURNAL_SCHEMA_BUILD_MISMATCH")
    return fingerprint


def verify_schema(conn: sqlite3.Connection, expected_fingerprint: str | None = None) -> str:
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise AcquisitionError("JOURNAL_INTEGRITY_FAILED")
    app_id = int(conn.execute("PRAGMA application_id").fetchone()[0])
    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if app_id != APPLICATION_ID:
        raise AcquisitionError("JOURNAL_APPLICATION_ID_MISMATCH")
    if user_version != USER_VERSION:
        raise AcquisitionError("JOURNAL_USER_VERSION_MISMATCH")
    rows = conn.execute(
        "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
    ).fetchall()
    tables = {name for kind, name in rows if kind == "table"}
    indexes = {name for kind, name in rows if kind == "index"}
    forbidden = {(kind, name) for kind, name in rows if kind not in {"table", "index"}}
    if forbidden:
        raise AcquisitionError("JOURNAL_UNEXPECTED_SCHEMA_OBJECT", repr(sorted(forbidden)))
    if tables != EXPECTED_TABLES:
        raise AcquisitionError("JOURNAL_TABLE_SET_MISMATCH", repr(sorted(tables)))
    if indexes != EXPECTED_INDEXES:
        raise AcquisitionError("JOURNAL_INDEX_SET_MISMATCH", repr(sorted(indexes)))
    fingerprint = schema_fingerprint(conn)
    if fingerprint != EXPECTED_SCHEMA_FINGERPRINT:
        raise AcquisitionError("JOURNAL_SCHEMA_FINGERPRINT_MISMATCH")
    if expected_fingerprint is not None and expected_fingerprint != EXPECTED_SCHEMA_FINGERPRINT:
        raise AcquisitionError("JOURNAL_METADATA_SCHEMA_FINGERPRINT_MISMATCH")
    return fingerprint
