"""Causal selected-value loader for certified Mission 101 release evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from offchain.market_data_acquisition.core import ResponseReceipt
from offchain.market_data_acquisition.journal import Journal, _validate_receipt_semantics
from offchain.research.reopening.bridge import _verified_materialization
from offchain.research.reopening import custody as m101_custody
from offchain.research.reopening.bridge import MAX_ARCHIVE_BYTES
from offchain.research.reopening.core import MISSION100_HASH, sha256_bytes, sha256_file
from offchain.research.reopening.dataset import (
    _latest_causally_available_records,
    verify_development_dataset_descriptor,
)

from .core import (
    CAUSAL_LOADER_ID,
    EVENT_ORDERING_ID,
    DevelopmentRuntimeError,
    canonical_hash,
    canonical_json,
    decimal_text,
    parse_utc,
    strict_json_load,
)
from .registry import canonical_instrument_id, parse_instrument_id


MAX_SELECTED_RECORDS = 300_000
MAX_PAYLOAD_BYTES = 256 * 1024
BAR_FIELDS = {
    "open_time_ms", "close_time_ms", "open", "high", "low", "close",
    "normalizer_id", "availability_policy_id",
}
TRADE_BAR_FIELDS = BAR_FIELDS | {"volume", "quote_volume", "trade_count"}
FUNDING_FIELDS = {
    "funding_time_ms", "funding_rate", "mark_price", "rate_type",
    "normalizer_id", "availability_policy_id",
}


def verify_release_envelope_without_values(
    release_directory: str | Path, *, custody_runtime_root: str | Path
) -> dict[str, Any]:
    """Verify release/certificate/backup identities without parsing market values."""

    try:
        root = m101_custody._runtime_root(custody_runtime_root, create=False)
        lexical = Path(release_directory)
        if not lexical.is_absolute():
            lexical = Path.cwd() / lexical
        m101_custody._reject_symlink_components(lexical)
        directory = lexical.resolve(strict=True)
        if directory.parent != root / "releases" or directory.is_symlink() or not directory.is_dir():
            raise DevelopmentRuntimeError("RELEASE_DIRECTORY_LOCATION_INVALID")
        if directory.stat().st_mode & 0o777 != 0o700:
            raise DevelopmentRuntimeError("RELEASE_DIRECTORY_MODE_INVALID")
        expected_files = {"source-backup.zip", "release.json", "certificate.json"}
        if {item.name for item in directory.iterdir()} != expected_files:
            raise DevelopmentRuntimeError("RELEASE_FILE_SET_INVALID")
        for item in directory.iterdir():
            if item.is_symlink() or not item.is_file() or item.stat().st_mode & 0o777 != 0o600:
                raise DevelopmentRuntimeError("RELEASE_FILE_INVALID", item.name)
        release_path = directory / "release.json"
        release_raw = release_path.read_bytes()
        release_doc = strict_json_load(release_raw, maximum_bytes=m101_custody.MAX_RELEASE_JSON_BYTES)
        if not isinstance(release_doc, dict) or set(release_doc) != {"schema_version", "release_id", "release_core_hash", "release_core"} or (canonical_json(release_doc) + "\n").encode() != release_raw:
            raise DevelopmentRuntimeError("RELEASE_DOCUMENT_INVALID")
        release_core = release_doc["release_core"]
        if not isinstance(release_core, dict) or canonical_hash(release_core) != release_doc["release_core_hash"] or release_doc["release_id"] != f"m101-forward-{release_doc['release_core_hash']}" or directory.name != release_doc["release_id"]:
            raise DevelopmentRuntimeError("RELEASE_CORE_HASH_MISMATCH")
        if release_core.get("profile_id") != "DELTAGRID_M100_FORWARD_CUSTODY_V1" or release_core.get("lineage_class") != "M100_FORWARD_OBSERVED":
            raise DevelopmentRuntimeError("RELEASE_PROFILE_INVALID")
        records = release_core.get("custody_records")
        if not isinstance(records, list) or len(records) > MAX_SELECTED_RECORDS:
            raise DevelopmentRuntimeError("RELEASE_RECORD_LIMIT")
        record_hashes = [item.get("custody_record_hash") for item in records if isinstance(item, dict)]
        if len(record_hashes) != len(records) or len(set(record_hashes)) != len(records) or canonical_hash(sorted(record_hashes)) != release_core.get("custody_record_set_hash"):
            raise DevelopmentRuntimeError("RELEASE_RECORD_SET_INVALID")
        backup = directory / "source-backup.zip"
        backup_hash = sha256_file(backup, maximum_bytes=MAX_ARCHIVE_BYTES)
        if backup_hash != release_core.get("source_backup_sha256"):
            raise DevelopmentRuntimeError("SOURCE_BACKUP_IDENTITY_MISMATCH")
        certificate_path = directory / "certificate.json"
        certificate_raw = certificate_path.read_bytes()
        certificate = strict_json_load(certificate_raw, maximum_bytes=m101_custody.MAX_CERTIFICATE_BYTES)
        if not isinstance(certificate, dict) or set(certificate) != {"certificate_core", "certificate_hash"} or (canonical_json(certificate) + "\n").encode() != certificate_raw:
            raise DevelopmentRuntimeError("CERTIFICATE_RECONSTRUCTION_MISMATCH")
        expected_certificate_core = {
            "schema_version": "1.0", "release_id": release_doc["release_id"],
            "release_core_hash": release_doc["release_core_hash"],
            "profile_id": "DELTAGRID_M100_FORWARD_CUSTODY_V1",
            "release_file_sha256": sha256_bytes(release_raw),
            "source_backup_sha256": backup_hash,
            "custody_record_set_hash": release_core["custody_record_set_hash"],
            "record_count": release_core["counts"]["admissible_observations"],
            "verdict": "CERTIFIED", "metadata_safe": True,
        }
        if certificate["certificate_core"] != expected_certificate_core or certificate["certificate_hash"] != canonical_hash(expected_certificate_core):
            raise DevelopmentRuntimeError("CERTIFICATE_RECONSTRUCTION_MISMATCH")
        return {
            "release_id": release_doc["release_id"],
            "release_core_hash": release_doc["release_core_hash"],
            "certificate_hash": certificate["certificate_hash"],
            "custody_record_hashes": frozenset(record_hashes),
            "release_core": release_core,
            "market_values_opened": False,
        }
    except DevelopmentRuntimeError:
        raise
    except Exception as error:
        raise DevelopmentRuntimeError(getattr(error, "reason", "RELEASE_ENVELOPE_INVALID")) from error


@dataclass(frozen=True)
class MarketEvent:
    event_id: str
    custody_record_hash: str
    source_m100_record_hash: str
    stream: str
    symbol: str
    interval: str | None
    event_time_ms: int
    available_at: str
    revision: int
    payload_hash: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    def identity(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "custody_record_hash": self.custody_record_hash,
            "source_m100_record_hash": self.source_m100_record_hash,
            "stream": self.stream,
            "symbol": self.symbol,
            "interval": self.interval,
            "event_time_ms": self.event_time_ms,
            "available_at": self.available_at,
            "revision": self.revision,
            "payload_hash": self.payload_hash,
        }


def _strict_payload(stream: str, raw: str, expected_hash: str) -> dict[str, Any]:
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise DevelopmentRuntimeError("PAYLOAD_SIZE_LIMIT")
    payload = strict_json_load(raw, maximum_bytes=MAX_PAYLOAD_BYTES)
    if not isinstance(payload, dict) or canonical_hash(payload) != expected_hash or canonical_json(payload) != raw:
        raise DevelopmentRuntimeError("PAYLOAD_HASH_MISMATCH")
    if stream in {"spot_ohlcv", "perpetual_ohlcv"}:
        expected = TRADE_BAR_FIELDS
    elif stream in {"mark_price_ohlcv", "index_price_ohlcv"}:
        expected = BAR_FIELDS
    elif stream == "funding_rates":
        expected = FUNDING_FIELDS
    else:
        raise DevelopmentRuntimeError("STREAM_UNAUTHORIZED")
    if set(payload) != expected:
        raise DevelopmentRuntimeError("PAYLOAD_SCHEMA_INVALID")
    if stream == "funding_rates":
        if type(payload["funding_time_ms"]) is not int:
            raise DevelopmentRuntimeError("PAYLOAD_SCHEMA_INVALID")
        decimal_text(payload["funding_rate"], "funding_rate")
        decimal_text(payload["mark_price"], "mark_price", positive=True)
        if payload["rate_type"] not in {None, "Regular", "Special"}:
            raise DevelopmentRuntimeError("PAYLOAD_SCHEMA_INVALID")
    else:
        if type(payload["open_time_ms"]) is not int or type(payload["close_time_ms"]) is not int or payload["close_time_ms"] < payload["open_time_ms"]:
            raise DevelopmentRuntimeError("PAYLOAD_SCHEMA_INVALID")
        for field in ("open", "high", "low", "close"):
            decimal_text(payload[field], field, positive=True)
        low, high = Decimal(payload["low"]), Decimal(payload["high"])
        if high < low or not low <= Decimal(payload["open"]) <= high or not low <= Decimal(payload["close"]) <= high:
            raise DevelopmentRuntimeError("PAYLOAD_PRICE_RELATION_INVALID")
        if stream in {"spot_ohlcv", "perpetual_ohlcv"}:
            decimal_text(payload["volume"], "volume", nonnegative=True)
            decimal_text(payload["quote_volume"], "quote_volume", nonnegative=True)
            if type(payload["trade_count"]) is not int or payload["trade_count"] < 0:
                raise DevelopmentRuntimeError("PAYLOAD_SCHEMA_INVALID")
    return payload


def _load_exact_custody_events(
    envelope: Mapping[str, Any], *, release_directory: str | Path,
    custody_record_hashes: tuple[str, ...],
) -> tuple[MarketEvent, ...]:
    """Open and verify payload JSON for exactly the supplied custody hashes."""

    if (
        not custody_record_hashes
        or len(custody_record_hashes) > MAX_SELECTED_RECORDS
        or len(custody_record_hashes) != len(set(custody_record_hashes))
    ):
        raise DevelopmentRuntimeError("SELECTED_RECORD_SET_INVALID")
    custody = {
        item["custody_record_hash"]: item
        for item in envelope["release_core"]["custody_records"]
    }
    if set(custody_record_hashes) - set(custody):
        raise DevelopmentRuntimeError("SELECTED_CUSTODY_RECORD_MISSING")
    backup = Path(release_directory) / "source-backup.zip"
    events: list[MarketEvent] = []
    try:
        materialization = _verified_materialization(backup)
        with materialization as (runtime, _manifest, _manifest_hash):
            with Journal.open(runtime, readonly=True) as journal:
                conn = journal.conn
                source_hashes = [custody[item]["source_m100_record_hash"] for item in custody_record_hashes]
                rows: dict[str, Any] = {}
                # Bounded one-at-a-time lookup avoids SQLite parameter limits and
                # never parses an excluded observation's payload_json.
                for source_hash in source_hashes:
                    row = conn.execute("SELECT * FROM observations WHERE record_hash=?", (source_hash,)).fetchone()
                    if row is None or source_hash in rows:
                        raise DevelopmentRuntimeError("SOURCE_RECORD_MISSING_OR_DUPLICATE")
                    rows[source_hash] = row
                for custody_hash in custody_record_hashes:
                    metadata = custody[custody_hash]
                    row = rows[metadata["source_m100_record_hash"]]
                    source_core = {
                        "logical_id": row["logical_id"],
                        "revision_number": row["revision_number"],
                        "supersedes_record_hash": row["supersedes_record_hash"],
                        "batch_id": row["batch_id"],
                        "receipt_hash": row["receipt_hash"],
                        "stream": row["stream"],
                        "symbol": row["symbol"],
                        "interval": row["interval"],
                        "event_time_ms": row["event_time_ms"],
                        "available_at": row["available_at"],
                        "response_hash": row["response_hash"],
                        "payload_hash": row["payload_hash"],
                    }
                    if canonical_hash(source_core) != row["record_hash"]:
                        raise DevelopmentRuntimeError("SOURCE_RECORD_HASH_MISMATCH")
                    receipt = conn.execute("SELECT * FROM receipts WHERE receipt_hash=?", (row["receipt_hash"],)).fetchone()
                    if receipt is None:
                        raise DevelopmentRuntimeError("SOURCE_RECEIPT_MISSING")
                    raw_object = conn.execute("SELECT * FROM raw_objects WHERE object_sha256=?", (receipt["object_sha256"],)).fetchone()
                    if raw_object is None:
                        raise DevelopmentRuntimeError("SOURCE_RAW_OBJECT_MISSING")
                    batch = conn.execute("SELECT * FROM capture_batches WHERE batch_id=?", (row["batch_id"],)).fetchone()
                    if batch is None or batch["status"] != "COMPLETE" or batch["contract_hash"] != MISSION100_HASH:
                        raise DevelopmentRuntimeError("SOURCE_BATCH_NOT_COMPLETE")
                    receipt_value = ResponseReceipt(
                        request_id=receipt["request_id"], host=receipt["host"], path=receipt["path"],
                        params=strict_json_load(receipt["params_json"]), requested_at=receipt["requested_at"],
                        received_at=receipt["received_at"], wall_start_ms=receipt["wall_start_ms"],
                        wall_end_ms=receipt["wall_end_ms"], monotonic_duration_ms=receipt["monotonic_duration_ms"],
                        clock_status=receipt["clock_status"], http_status=receipt["http_status"],
                        headers=strict_json_load(receipt["headers_json"]), attempt_number=receipt["attempt_number"],
                        retry_exhausted=bool(receipt["retry_exhausted"]), body_sha256=receipt["body_sha256"],
                        object_sha256=receipt["object_sha256"], response_hash=receipt["response_hash"],
                        receipt_hash=receipt["receipt_hash"],
                    )
                    if _validate_receipt_semantics(receipt_value) != row["stream"]:
                        raise DevelopmentRuntimeError("OBSERVATION_ENDPOINT_MISMATCH")
                    bindings = {
                        "source_m100_record_hash": row["record_hash"],
                        "source_m100_logical_id": row["logical_id"],
                        "source_m100_batch_id": row["batch_id"],
                        "source_m100_receipt_hash": row["receipt_hash"],
                        "source_m100_response_hash": row["response_hash"],
                        "source_m100_payload_hash": row["payload_hash"],
                        "stream": row["stream"], "symbol": row["symbol"],
                        "interval": row["interval"], "event_time_ms": row["event_time_ms"],
                        "available_at": row["available_at"], "revision_number": row["revision_number"],
                        "source_m100_code_commit": batch["code_commit"],
                    }
                    if any(metadata.get(field) != value for field, value in bindings.items()):
                        raise DevelopmentRuntimeError("CUSTODY_SOURCE_BINDING_MISMATCH")
                    receipt_bindings = {
                        "source_m100_object_sha256": receipt["object_sha256"],
                        "source_m100_body_sha256": receipt["body_sha256"],
                        "source_m100_response_hash": receipt["response_hash"],
                        "first_observed_at": receipt["received_at"],
                        "available_at": receipt["received_at"],
                        "clock_health": receipt["clock_status"],
                    }
                    if any(metadata.get(field) != value for field, value in receipt_bindings.items()):
                        raise DevelopmentRuntimeError("CUSTODY_RECEIPT_BINDING_MISMATCH")
                    if raw_object["body_sha256"] != receipt["body_sha256"] or raw_object["object_sha256"] != receipt["object_sha256"]:
                        raise DevelopmentRuntimeError("SOURCE_RAW_OBJECT_BINDING_MISMATCH")
                    payload = _strict_payload(row["stream"], row["payload_json"], row["payload_hash"])
                    event_core = {
                        "loader": CAUSAL_LOADER_ID,
                        "custody_record_hash": custody_hash,
                        "source_m100_record_hash": row["record_hash"],
                        "payload_hash": row["payload_hash"],
                    }
                    event_id = f"m102-event-{canonical_hash(event_core)}"
                    events.append(MarketEvent(
                        event_id=event_id, custody_record_hash=custody_hash,
                        source_m100_record_hash=row["record_hash"], stream=row["stream"],
                        symbol=row["symbol"], interval=row["interval"],
                        event_time_ms=row["event_time_ms"], available_at=row["available_at"],
                        revision=row["revision_number"], payload_hash=row["payload_hash"], payload=payload,
                    ))
    except DevelopmentRuntimeError:
        raise
    except Exception as error:
        raise DevelopmentRuntimeError(getattr(error, "reason", "CAUSAL_SOURCE_VERIFICATION_FAILED")) from error
    events.sort(key=lambda item: (parse_utc(item.available_at, "available_at"), item.custody_record_hash))
    if len({item.event_id for item in events}) != len(events):
        raise DevelopmentRuntimeError("EVENT_IDENTITY_COLLISION")
    return tuple(events)


def load_causal_events_by_custody_hashes(
    *, release_directory: str | Path, custody_runtime_root: str | Path,
    custody_record_hashes: tuple[str, ...], exact_observable_inputs: tuple[str, ...],
    expected_release_id: str, expected_release_core_hash: str,
    expected_release_certificate_hash: str,
) -> tuple[MarketEvent, ...]:
    """Recertify a release and open no payload outside an exact committed hash set."""

    envelope = verify_release_envelope_without_values(
        release_directory, custody_runtime_root=custody_runtime_root
    )
    if (
        envelope["release_id"] != expected_release_id
        or envelope["release_core_hash"] != expected_release_core_hash
        or envelope["certificate_hash"] != expected_release_certificate_hash
    ):
        raise DevelopmentRuntimeError("DATASET_RELEASE_BINDING_MISMATCH")
    scope = tuple(exact_observable_inputs)
    if not scope or len(scope) != len(set(scope)):
        raise DevelopmentRuntimeError("VARIANT_OBSERVABLE_SCOPE_INVALID")
    for instrument_id in scope:
        parse_instrument_id(instrument_id)
    custody = {
        item["custody_record_hash"]: item
        for item in envelope["release_core"]["custody_records"]
    }
    if set(custody_record_hashes) - set(custody):
        raise DevelopmentRuntimeError("SELECTED_CUSTODY_RECORD_MISSING")
    if any(
        canonical_instrument_id(custody[item]["stream"], custody[item]["symbol"]) not in set(scope)
        for item in custody_record_hashes
    ):
        raise DevelopmentRuntimeError("EXACT_OBSERVABLE_SCOPE_MISMATCH")
    return _load_exact_custody_events(
        envelope, release_directory=release_directory,
        custody_record_hashes=custody_record_hashes,
    )


def load_causal_events(
    descriptor: Mapping[str, Any] | str | Path,
    *,
    release_directory: str | Path,
    custody_runtime_root: str | Path,
    observable_inputs: tuple[str, ...] | None = None,
) -> tuple[MarketEvent, ...]:
    """Recertify upstream bytes and open only descriptor-selected payload JSON."""

    envelope = verify_release_envelope_without_values(
        release_directory, custody_runtime_root=custody_runtime_root
    )
    selected_descriptor = verify_development_dataset_descriptor(descriptor)
    if (
        selected_descriptor["source_forward_custody_release_id"] != envelope["release_id"]
        or selected_descriptor["release_core_hash"] != envelope["release_core_hash"]
        or selected_descriptor["release_certificate_hash"] != envelope["certificate_hash"]
    ):
        raise DevelopmentRuntimeError("DATASET_RELEASE_BINDING_MISMATCH")
    selected = selected_descriptor["selected_custody_record_hashes"]
    if len(selected) > MAX_SELECTED_RECORDS:
        raise DevelopmentRuntimeError("SELECTED_RECORD_COUNT_LIMIT")
    release = envelope["release_core"]
    expected_selected = _latest_causally_available_records(
        release["custody_records"], provider=selected_descriptor["provider"],
        symbols=selected_descriptor["allowed_symbols"], streams=selected_descriptor["allowed_streams"],
        stream_intervals=selected_descriptor["stream_intervals"],
        start=parse_utc(selected_descriptor["temporal_start"], "temporal_start"),
        end=parse_utc(selected_descriptor["temporal_end_as_of"], "temporal_end_as_of"),
        cutoff=parse_utc(selected_descriptor["causal_availability_cutoff"], "causal_availability_cutoff"),
    )
    if expected_selected != selected:
        raise DevelopmentRuntimeError("DATASET_RECORD_SET_RECONSTRUCTION_MISMATCH")
    custody = {item["custody_record_hash"]: item for item in release["custody_records"]}
    if set(selected) - set(custody):
        raise DevelopmentRuntimeError("SELECTED_CUSTODY_RECORD_MISSING")
    opened_selected = list(selected)
    if observable_inputs is not None:
        scope = tuple(observable_inputs)
        if not scope or len(scope) != len(set(scope)):
            raise DevelopmentRuntimeError("VARIANT_OBSERVABLE_SCOPE_INVALID")
        for instrument_id in scope:
            parse_instrument_id(instrument_id)
        scoped = set(scope)
        opened_selected = [
            custody_hash for custody_hash in selected
            if canonical_instrument_id(
                custody[custody_hash]["stream"], custody[custody_hash]["symbol"]
            ) in scoped
        ]
        present = {
            canonical_instrument_id(custody[item]["stream"], custody[item]["symbol"])
            for item in opened_selected
        }
        if present != scoped:
            raise DevelopmentRuntimeError("VARIANT_OBSERVABLE_INPUT_MISSING")
    return _load_exact_custody_events(
        envelope, release_directory=release_directory,
        custody_record_hashes=tuple(opened_selected),
    )
