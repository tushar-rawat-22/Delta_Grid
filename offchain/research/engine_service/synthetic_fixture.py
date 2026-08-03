"""Strict loading of hash-bound synthetic fixture version 1."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from offchain.research.admission import DatasetResolution, canonical_hash

from .models import EngineError, SyntheticEvent, SyntheticFixture
from .strict_json import decode_canonical_json, resolve_existing_regular_file, sha256_bytes
from .strict_json import (
    MAX_ACCOUNTING_VALUE,
    MAX_EVENTS,
    MAX_FIXTURE_BYTES,
)


FIXTURE_FIELDS = frozenset(
    {
        "schema_version",
        "fixture_id",
        "instrument_id",
        "currency_unit",
        "initial_cash_units",
        "trade_quantity_units",
        "fee_bps",
        "slippage_bps",
        "events",
        "canonical_fixture_hash",
    }
)
EVENT_FIELDS = frozenset(
    {"event_id", "timestamp", "mid_price_units", "available_fill_bps"}
)
UTC_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z"
)
SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


def _string(value: Any) -> bool:
    return isinstance(value, str) and SAFE_ID_RE.fullmatch(value) is not None


def _positive_int(value: Any) -> bool:
    return type(value) is int and 0 < value <= MAX_ACCOUNTING_VALUE


def _bps(value: Any) -> bool:
    return type(value) is int and 0 <= value <= 10_000


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID") from error
    if parsed.tzinfo != timezone.utc:
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
    normalized = parsed.strftime("%Y-%m-%dT%H:%M:%S")
    if parsed.microsecond:
        normalized += f".{parsed.microsecond:06d}".rstrip("0")
    normalized += "Z"
    if value != normalized:
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
    return parsed


def _validate_fixture_mapping(
    value: Any,
    *,
    includes_canonical_hash: bool,
) -> SyntheticFixture:
    """Validate an already-decoded fixture without accessing external state."""

    expected_fields = FIXTURE_FIELDS if includes_canonical_hash else (
        FIXTURE_FIELDS - {"canonical_fixture_hash"}
    )
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
    if value["schema_version"] != "1.0":
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
    identity_fields = ("fixture_id", "instrument_id", "currency_unit")
    if not all(_string(value[field]) for field in identity_fields):
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
    forbidden_references = (
        "http",
        "www.",
        "exchange",
        "venue",
        "symbol",
        "market",
        "protected",
    )
    if any(
        forbidden in value[field].casefold()
        for field in identity_fields
        for forbidden in forbidden_references
    ):
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
    if not _positive_int(value["initial_cash_units"]) or not _positive_int(
        value["trade_quantity_units"]
    ):
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
    if value["trade_quantity_units"] % 10_000:
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
    if not _bps(value["fee_bps"]) or not _bps(value["slippage_bps"]):
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
    raw_events = value["events"]
    if not isinstance(raw_events, list) or not 2 <= len(raw_events) <= MAX_EVENTS:
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
    events: list[SyntheticEvent] = []
    seen: set[str] = set()
    previous: datetime | None = None
    for raw_event in raw_events:
        if not isinstance(raw_event, dict) or set(raw_event) != EVENT_FIELDS:
            raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
        if not _string(raw_event["event_id"]) or raw_event["event_id"] in seen:
            raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
        if any(
            forbidden in raw_event["event_id"].casefold()
            for forbidden in forbidden_references
        ):
            raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
        timestamp = _timestamp(raw_event["timestamp"])
        if previous is not None and timestamp <= previous:
            raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
        if not _positive_int(raw_event["mid_price_units"]) or not _bps(
            raw_event["available_fill_bps"]
        ):
            raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
        seen.add(raw_event["event_id"])
        previous = timestamp
        events.append(SyntheticEvent(**raw_event))
    core = dict(value)
    supplied = (
        core.pop("canonical_fixture_hash")
        if includes_canonical_hash
        else canonical_hash(core)
    )
    if not isinstance(supplied, str) or canonical_hash(core) != supplied:
        raise EngineError("SYNTHETIC_FIXTURE_SCHEMA_INVALID")
    return SyntheticFixture(
        schema_version=value["schema_version"],
        fixture_id=value["fixture_id"],
        instrument_id=value["instrument_id"],
        currency_unit=value["currency_unit"],
        initial_cash_units=value["initial_cash_units"],
        trade_quantity_units=value["trade_quantity_units"],
        fee_bps=value["fee_bps"],
        slippage_bps=value["slippage_bps"],
        events=tuple(events),
        canonical_fixture_hash=supplied,
    )


def _microseconds(delta: Any) -> int:
    return (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )


def _timing_diagnostics(timestamps: list[str] | tuple[str, ...]) -> dict[str, Any]:
    parsed = [_timestamp(timestamp) for timestamp in timestamps]
    intervals = [
        _microseconds(current - previous)
        for previous, current in zip(parsed, parsed[1:])
    ]
    return {
        "event_count": len(parsed),
        "interval_count": max(len(parsed) - 1, 0),
        "data_start_at": timestamps[0],
        "data_end_at": timestamps[-1],
        "duration_microseconds": _microseconds(parsed[-1] - parsed[0]),
        "minimum_interval_microseconds": min(intervals) if intervals else 0,
        "maximum_interval_microseconds": max(intervals) if intervals else 0,
        "nonpositive_interval_count": sum(interval <= 0 for interval in intervals),
    }


def load_synthetic_fixture(
    *,
    artifact_root: Path,
    resolution: DatasetResolution,
) -> SyntheticFixture:
    """Open the resolved artifact once, byte-verify it, then strictly parse it."""

    path = resolve_existing_regular_file(
        artifact_root,
        resolution.artifact_path,
        unsafe_reason="SYNTHETIC_FIXTURE_PATH_UNSAFE",
        missing_reason="SYNTHETIC_FIXTURE_MISSING",
    )
    try:
        with path.open("rb") as fixture_file:
            raw = fixture_file.read(MAX_FIXTURE_BYTES + 1)
    except OSError as error:
        raise EngineError("SYNTHETIC_FIXTURE_MISSING") from error
    if sha256_bytes(raw) != resolution.content_sha256:
        raise EngineError("SYNTHETIC_FIXTURE_HASH_MISMATCH")
    value = decode_canonical_json(
        raw,
        invalid_reason="SYNTHETIC_FIXTURE_SCHEMA_INVALID",
        max_bytes=MAX_FIXTURE_BYTES,
    )
    return _validate_fixture_mapping(value, includes_canonical_hash=True)
