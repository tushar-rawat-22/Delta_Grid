#!/usr/bin/env python3
"""Append-only, fixed-endpoint private SEC and Treasury pilot collector."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

import deltagrid_agent as agent


USER_AGENT = "DeltaGrid-PrivatePilot/1.0 (+https://github.com/tushar-rawat-22/Delta_Grid)"
SEC_USER_AGENT_SERVICE = "deltagrid-sec-user-agent"
SEC_USER_AGENT_ACCOUNT = "deltagrid-founder-agent"
AUTHORITY_STATE = "NONE"
PROVIDERS = (
    {
        "provider_id": "SEC_EDGAR_PRIVATE_PILOT",
        "instrument_id": "US_EQUITY_AAPL_PRIVATE_PILOT",
        "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        "max_bytes": 8_388_608,
        "validator": "SEC",
    },
    {
        "provider_id": "US_TREASURY_FISCALDATA_PRIVATE_PILOT",
        "instrument_id": "US_MACRO_TREASURY_DEBT_PRIVATE_PILOT",
        "url": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?sort=-record_date&page%5Bsize%5D=1",
        "max_bytes": 262_144,
        "validator": "TREASURY",
    },
)


class CollectorError(RuntimeError):
    """Stable fail-closed collector error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def open_database(runtime_root: Path) -> sqlite3.Connection:
    runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    database_path = runtime_root / "private-provider-pilot.sqlite3"
    connection = sqlite3.connect(database_path)
    os.chmod(database_path, 0o600)
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS provider_daily_reservations (
          provider_id TEXT NOT NULL,
          capture_day TEXT NOT NULL,
          attempt_id TEXT NOT NULL UNIQUE,
          reserved_at TEXT NOT NULL,
          PRIMARY KEY(provider_id, capture_day)
        );
        CREATE TABLE IF NOT EXISTS provider_captures (
          capture_id TEXT PRIMARY KEY,
          provider_id TEXT NOT NULL,
          instrument_id TEXT NOT NULL,
          capture_day TEXT NOT NULL,
          observed_at TEXT NOT NULL,
          available_at TEXT NOT NULL,
          provider_record_date TEXT NOT NULL,
          payload_sha256 TEXT NOT NULL,
          content_length INTEGER NOT NULL,
          object_path TEXT NOT NULL,
          previous_payload_sha256 TEXT,
          local_receipt_sha256 TEXT NOT NULL,
          authority_effect TEXT NOT NULL CHECK(authority_effect='NONE')
        );
        CREATE TABLE IF NOT EXISTS provider_events (
          event_id TEXT PRIMARY KEY,
          provider_id TEXT NOT NULL,
          occurred_at TEXT NOT NULL,
          event_type TEXT NOT NULL,
          detail_code TEXT NOT NULL,
          payload_sha256 TEXT,
          authority_effect TEXT NOT NULL CHECK(authority_effect='NONE')
        );
        CREATE TRIGGER IF NOT EXISTS provider_reservations_no_update
          BEFORE UPDATE ON provider_daily_reservations BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY'); END;
        CREATE TRIGGER IF NOT EXISTS provider_reservations_no_delete
          BEFORE DELETE ON provider_daily_reservations BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY'); END;
        CREATE TRIGGER IF NOT EXISTS provider_captures_no_update
          BEFORE UPDATE ON provider_captures BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY'); END;
        CREATE TRIGGER IF NOT EXISTS provider_captures_no_delete
          BEFORE DELETE ON provider_captures BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY'); END;
        CREATE TRIGGER IF NOT EXISTS provider_events_no_update
          BEFORE UPDATE ON provider_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY'); END;
        CREATE TRIGGER IF NOT EXISTS provider_events_no_delete
          BEFORE DELETE ON provider_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY'); END;
        """
    )
    return connection


def reserve_daily_request(connection: sqlite3.Connection, provider_id: str, capture_day: str) -> bool:
    try:
        connection.execute(
            "INSERT INTO provider_daily_reservations VALUES (?, ?, ?, ?)",
            (provider_id, capture_day, str(uuid.uuid4()), utc_now()),
        )
        connection.commit()
        return True
    except sqlite3.IntegrityError:
        connection.rollback()
        return False


def sec_user_agent() -> str:
    result = subprocess.run(
        [
            "/usr/bin/security", "find-generic-password", "-s", SEC_USER_AGENT_SERVICE,
            "-a", SEC_USER_AGENT_ACCOUNT, "-w",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    value = result.stdout.rstrip("\n")
    if result.returncode != 0 or not re.fullmatch(r"DeltaGrid/[0-9.]+ [^\s@]+@[^\s@]+", value):
        raise CollectorError("SEC_IDENTIFIED_USER_AGENT_MISSING")
    if len(value.encode("ascii", errors="ignore")) != len(value) or len(value) > 256:
        raise CollectorError("SEC_IDENTIFIED_USER_AGENT_INVALID")
    return value


def fetch_provider(provider: dict[str, Any]) -> bytes:
    user_agent = sec_user_agent() if provider["validator"] == "SEC" else USER_AGENT
    request = Request(
        provider["url"],
        headers={"Accept": "application/json", "User-Agent": user_agent},
        method="GET",
    )
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - URL is a frozen registry constant
            content_type = response.headers.get_content_type()
            if content_type not in {"application/json", "application/vnd.api+json"}:
                raise CollectorError("PROVIDER_CONTENT_TYPE_INVALID")
            raw = response.read(provider["max_bytes"] + 1)
    except HTTPError as error:
        raise CollectorError(f"PROVIDER_HTTP_{error.code}") from None
    except (URLError, TimeoutError):
        raise CollectorError("PROVIDER_UNAVAILABLE") from None
    if len(raw) > provider["max_bytes"]:
        raise CollectorError("PROVIDER_RESPONSE_TOO_LARGE")
    if len(raw) < 2:
        raise CollectorError("PROVIDER_RESPONSE_EMPTY")
    return raw


def validate_payload(provider: dict[str, Any], raw: bytes) -> tuple[dict[str, Any], str]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CollectorError("PROVIDER_JSON_INVALID") from None
    if not isinstance(value, dict):
        raise CollectorError("PROVIDER_SCHEMA_INVALID")
    if provider["validator"] == "SEC":
        cik = str(value.get("cik", "")).zfill(10)
        if cik != "0000320193" or not isinstance(value.get("entityName"), str):
            raise CollectorError("SEC_COMPANY_IDENTITY_INVALID")
        facts = value.get("facts")
        if not isinstance(facts, dict) or not isinstance(facts.get("us-gaap"), dict) or not isinstance(facts.get("dei"), dict):
            raise CollectorError("SEC_COMPANY_FACTS_SCHEMA_INVALID")
        filed_dates: list[str] = []
        for taxonomy in facts.values():
            if not isinstance(taxonomy, dict):
                raise CollectorError("SEC_TAXONOMY_SCHEMA_INVALID")
            for fact in taxonomy.values():
                if not isinstance(fact, dict) or not isinstance(fact.get("units"), dict):
                    raise CollectorError("SEC_FACT_SCHEMA_INVALID")
                for entries in fact["units"].values():
                    if not isinstance(entries, list):
                        raise CollectorError("SEC_UNIT_SCHEMA_INVALID")
                    for entry in entries:
                        if not isinstance(entry, dict):
                            raise CollectorError("SEC_ENTRY_SCHEMA_INVALID")
                        filed = entry.get("filed")
                        if isinstance(filed, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", filed):
                            filed_dates.append(filed)
        if not filed_dates:
            raise CollectorError("SEC_FILED_DATE_MISSING")
        return value, max(filed_dates)

    data = value.get("data")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise CollectorError("TREASURY_DATA_SCHEMA_INVALID")
    if not isinstance(value.get("meta"), dict) or not isinstance(value.get("links"), dict):
        raise CollectorError("TREASURY_ENVELOPE_SCHEMA_INVALID")
    row = data[0]
    required = {"record_date", "debt_held_public_amt", "intragov_hold_amt", "tot_pub_debt_out_amt"}
    if not required.issubset(row):
        raise CollectorError("TREASURY_FIELDS_MISSING")
    record_date = row["record_date"]
    if not isinstance(record_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", record_date):
        raise CollectorError("TREASURY_RECORD_DATE_INVALID")
    for field in required - {"record_date"}:
        if not isinstance(row[field], str):
            raise CollectorError("TREASURY_DECIMAL_INVALID")
        try:
            Decimal(row[field])
        except InvalidOperation:
            raise CollectorError("TREASURY_DECIMAL_INVALID") from None
    return value, record_date


def write_object(runtime_root: Path, payload_sha256: str, raw: bytes) -> Path:
    directory = runtime_root / "raw-objects" / payload_sha256[:2]
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = directory / f"{payload_sha256}.json"
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if destination.read_bytes() != raw:
            raise CollectorError("RAW_OBJECT_HASH_COLLISION") from None
        return destination
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return destination


def verify_replay(provider: dict[str, Any], path: Path, expected_hash: str, expected_date: str) -> None:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise CollectorError("RAW_OBJECT_REPLAY_HASH_INVALID")
    _, record_date = validate_payload(provider, raw)
    if record_date != expected_date:
        raise CollectorError("RAW_OBJECT_REPLAY_SCHEMA_INVALID")


def verify_rollback(connection: sqlite3.Connection, provider_id: str) -> None:
    marker = f"rollback-{uuid.uuid4()}"
    connection.execute("BEGIN IMMEDIATE")
    connection.execute(
        "INSERT INTO provider_events VALUES (?, ?, ?, ?, ?, ?, 'NONE')",
        (marker, provider_id, utc_now(), "ROLLBACK_PROBE", "MUST_NOT_COMMIT", None),
    )
    connection.rollback()
    row = connection.execute("SELECT 1 FROM provider_events WHERE event_id=?", (marker,)).fetchone()
    if row is not None:
        raise CollectorError("LOCAL_ROLLBACK_VERIFICATION_FAILED")


def local_receipt(runtime_root: Path, metadata: dict[str, Any]) -> str:
    raw = (canonical_json(metadata) + "\n").encode()
    digest = hashlib.sha256(raw).hexdigest()
    directory = runtime_root / "receipts"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = directory / f"{metadata['capture_id']}.json"
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return digest


def remote_credentials() -> dict[str, str]:
    return {name: agent.keychain_secret(name) for name in agent.KEYCHAIN_SERVICES}


def record_failure(
    provider: dict[str, Any], config: dict[str, Any], connection: sqlite3.Connection,
    credentials: dict[str, str], error: CollectorError,
) -> dict[str, str]:
    event_id = str(uuid.uuid4())
    occurred_at = utc_now()
    detail_code = str(error)
    metadata = {
        "authority_state": AUTHORITY_STATE,
        "capture_id": event_id,
        "detail_code": detail_code,
        "occurred_at": occurred_at,
        "provider_id": provider["provider_id"],
        "status": "FAILED",
    }
    receipt_sha256 = local_receipt(Path(config["provider_runtime_root"]), metadata)
    connection.execute(
        "INSERT INTO provider_events VALUES (?, ?, ?, ?, ?, ?, 'NONE')",
        (event_id, provider["provider_id"], occurred_at, "FAILED", detail_code, None),
    )
    connection.commit()
    status = {
        "authority_state": AUTHORITY_STATE,
        "detail_code": detail_code,
        "latest_envelope_id": None,
        "local_receipt_sha256": receipt_sha256,
        "payload_sha256": None,
        "provider_id": provider["provider_id"],
        "receipt_id": str(uuid.uuid4()),
        "recorded_at": occurred_at,
        "status": "FAILED",
    }
    try:
        remote = agent.signed_request(config["endpoint"], "/agent/v1/status", status, credentials)
        if remote.get("status") != "PROVIDER_STATUS_RECORDED":
            raise CollectorError("REMOTE_FAILURE_STATUS_REJECTED")
    except (agent.AgentError, CollectorError):
        connection.execute(
            "INSERT INTO provider_events VALUES (?, ?, ?, ?, ?, ?, 'NONE')",
            (str(uuid.uuid4()), provider["provider_id"], utc_now(), "FAILED", "REMOTE_FAILURE_STATUS_REJECTED", None),
        )
        connection.commit()
    return {"provider_id": provider["provider_id"], "status": "FAILED", "code": detail_code}


def capture_provider(
    provider: dict[str, Any], config: dict[str, Any], connection: sqlite3.Connection,
    credentials: dict[str, str], capture_day: str,
) -> dict[str, str]:
    provider_id = provider["provider_id"]
    if not reserve_daily_request(connection, provider_id, capture_day):
        return {"provider_id": provider_id, "status": "ALREADY_ATTEMPTED_TODAY"}
    observed_at = utc_now()
    raw = fetch_provider(provider)
    _, provider_record_date = validate_payload(provider, raw)
    payload_sha256 = hashlib.sha256(raw).hexdigest()
    runtime_root = Path(config["provider_runtime_root"])
    object_path = write_object(runtime_root, payload_sha256, raw)
    verify_replay(provider, object_path, payload_sha256, provider_record_date)
    verify_rollback(connection, provider_id)
    capture_id = str(uuid.uuid4())
    available_at = utc_now()
    previous = connection.execute(
        "SELECT payload_sha256 FROM provider_captures WHERE provider_id=? ORDER BY observed_at DESC LIMIT 1",
        (provider_id,),
    ).fetchone()
    receipt_metadata = {
        "authority_state": AUTHORITY_STATE,
        "available_at": available_at,
        "capture_id": capture_id,
        "content_length": len(raw),
        "instrument_id": provider["instrument_id"],
        "observed_at": observed_at,
        "payload_sha256": payload_sha256,
        "private_only": True,
        "provider_id": provider_id,
        "provider_record_date": provider_record_date,
        "replay_verified": True,
        "rollback_verified": True,
        "schema_version": 1,
    }
    receipt_sha256 = local_receipt(runtime_root, receipt_metadata)
    connection.execute(
        "INSERT INTO provider_captures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'NONE')",
        (
            capture_id, provider_id, provider["instrument_id"], capture_day, observed_at,
            available_at, provider_record_date, payload_sha256, len(raw), str(object_path),
            previous[0] if previous else None, receipt_sha256,
        ),
    )
    connection.commit()
    envelope = {
        "authority_state": AUTHORITY_STATE,
        "available_at": available_at,
        "content_length": len(raw),
        "envelope_id": capture_id,
        "instrument_id": provider["instrument_id"],
        "local_receipt_sha256": receipt_sha256,
        "observed_at": observed_at,
        "payload_sha256": payload_sha256,
        "private_only": True,
        "provider_id": provider_id,
        "provider_record_date": provider_record_date,
        "schema_version": 1,
    }
    remote = agent.signed_request(config["endpoint"], "/agent/v1/evidence", envelope, credentials)
    if remote.get("status") != "EVIDENCE_RECORDED" or remote.get("envelope_id") != capture_id:
        raise CollectorError("REMOTE_EVIDENCE_REJECTED")
    try:
        agent.signed_request(config["endpoint"], "/agent/v1/evidence", envelope, credentials)
    except agent.AgentError as error:
        if str(error) != "REMOTE_HTTP_409":
            raise CollectorError("REMOTE_REPLAY_VERIFICATION_FAILED") from None
    else:
        raise CollectorError("REMOTE_EVIDENCE_REPLAY_ACCEPTED")
    status_receipt = str(uuid.uuid4())
    status = {
        "authority_state": AUTHORITY_STATE,
        "detail_code": "CAPTURE_REPLAY_AND_ROLLBACK_VERIFIED",
        "latest_envelope_id": capture_id,
        "local_receipt_sha256": receipt_sha256,
        "payload_sha256": payload_sha256,
        "provider_id": provider_id,
        "receipt_id": status_receipt,
        "recorded_at": utc_now(),
        "status": "OPERATIONAL",
    }
    remote_status = agent.signed_request(config["endpoint"], "/agent/v1/status", status, credentials)
    if remote_status.get("status") != "PROVIDER_STATUS_RECORDED":
        raise CollectorError("REMOTE_STATUS_REJECTED")
    connection.execute(
        "INSERT INTO provider_events VALUES (?, ?, ?, ?, ?, ?, 'NONE')",
        (str(uuid.uuid4()), provider_id, utc_now(), "OPERATIONAL", status["detail_code"], payload_sha256),
    )
    connection.commit()
    return {"provider_id": provider_id, "status": "OPERATIONAL"}


def run_daily(config_path: Path, *, capture_day: str | None = None) -> list[dict[str, str]]:
    config = agent.load_config(config_path)
    runtime_root = Path(config["provider_runtime_root"])
    connection = open_database(runtime_root)
    credentials = remote_credentials()
    day = capture_day or datetime.now(timezone.utc).date().isoformat()
    results: list[dict[str, str]] = []
    try:
        for provider in PROVIDERS:
            try:
                results.append(capture_provider(provider, config, connection, credentials, day))
            except CollectorError as error:
                results.append(record_failure(provider, config, connection, credentials, error))
    finally:
        connection.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        results = run_daily(args.config)
    except (agent.AgentError, CollectorError, OSError, sqlite3.Error, json.JSONDecodeError):
        print('{"authority_state":"NONE","status":"FAILED_CLOSED"}')
        return 2
    print(canonical_json({"authority_state": "NONE", "providers": results}))
    return 0 if all(result["status"] in {"OPERATIONAL", "ALREADY_ATTEMPTED_TODAY"} for result in results) else 2


if __name__ == "__main__":
    sys.exit(main())
