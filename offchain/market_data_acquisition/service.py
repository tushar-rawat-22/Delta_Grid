"""Bounded forward public-market capture service for Mission 100."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import time
from typing import Any, Iterable, Mapping

from .core import (
    AcquisitionError,
    AVAILABILITY_POLICY_ID,
    BAR_STREAMS,
    ClockStatus,
    FUTURES_HOST,
    INTERVAL,
    INTERVAL_MS,
    MISSION100_HASH,
    NORMALIZER_ID,
    ObservationCandidate,
    ResponseReceipt,
    SPOT_HOST,
    STREAMS,
    SYMBOLS,
    canonical_hash,
    canonical_json,
    deep_thaw,
    load_contracts,
    ms_to_utc,
    sha256_bytes,
    utc_now_ms,
)
from .journal import Journal, acquisition_lock, repository_identity, validate_runtime_root
from .network import NetworkAttempt, RequestFailed, decode_json, perform_request


ACK_CAPTURE = "CAPTURE_PUBLIC_MARKET_DATA"
MAX_LOGICAL_REQUESTS = 18
MAX_CATCHUP_HOURS = 168
REVISION_SWEEP_HOURS = 24
CLOSE_SAFETY_MARGIN_MS = 5_000
MAX_CLOCK_OFFSET_MS = 5_000
MAX_WALL_MONOTONIC_DRIFT_MS = 1_000
PAGE_LIMIT = 1000


@dataclass(frozen=True)
class CaptureSummary:
    batch_id: str
    status: str
    requests: int
    receipts: int
    observations_inserted: int
    exact_duplicates: int
    clock_status: str
    start_event_time_ms: int
    end_event_time_exclusive_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "status": self.status,
            "requests": self.requests,
            "receipts": self.receipts,
            "observations_inserted": self.observations_inserted,
            "exact_duplicates": self.exact_duplicates,
            "clock_status": self.clock_status,
            "start_event_time_ms": self.start_event_time_ms,
            "end_event_time_exclusive_ms": self.end_event_time_exclusive_ms,
        }


def _clock_status(server_time_ms: int, receipt: ResponseReceipt) -> ClockStatus:
    local_midpoint = (receipt.wall_start_ms + receipt.wall_end_ms) // 2
    offset = server_time_ms - local_midpoint
    wall_elapsed = receipt.wall_end_ms - receipt.wall_start_ms
    if abs(offset) > MAX_CLOCK_OFFSET_MS:
        return ClockStatus.DEGRADED
    if abs(wall_elapsed - receipt.monotonic_duration_ms) > MAX_WALL_MONOTONIC_DRIFT_MS:
        return ClockStatus.DEGRADED
    return ClockStatus.HEALTHY


def _bind_receipt(receipt: ResponseReceipt, *, object_sha256: str) -> ResponseReceipt:
    core = receipt.as_dict()
    core.pop("receipt_hash")
    core["object_sha256"] = object_sha256
    return ResponseReceipt.create(**core)


def _persist_attempts(
    journal: Journal,
    batch_id: str,
    attempts: tuple[NetworkAttempt, ...],
) -> tuple[ResponseReceipt, ...]:
    bound: list[ResponseReceipt] = []
    for attempt in attempts:
        provisional = attempt.receipt
        body_hash, object_hash, _ = journal.store_raw_body(
            attempt.body, created_at=provisional.received_at
        )
        if body_hash != provisional.body_sha256:
            raise AcquisitionError("RECEIPT_BODY_HASH_MISMATCH")
        receipt = _bind_receipt(provisional, object_sha256=object_hash)
        journal.add_receipt(batch_id, receipt)
        bound.append(receipt)
    journal.conn.commit()
    return tuple(bound)


def _request_and_persist(
    journal: Journal,
    batch_id: str,
    endpoint: str,
    params: Mapping[str, Any],
    *,
    request_id: str,
    clock_status: ClockStatus,
    opener: Any | None,
) -> tuple[Any, ResponseReceipt, bytes, int]:
    try:
        body, _provisional, _headers, attempts = perform_request(
            endpoint,
            params,
            opener=opener,
            request_id=request_id,
            clock_status=clock_status,
        )
    except RequestFailed as error:
        if error.attempts:
            _persist_attempts(journal, batch_id, error.attempts)
        raise
    bound = _persist_attempts(journal, batch_id, attempts)
    if not bound:
        raise AcquisitionError("NETWORK_ATTEMPT_EVIDENCE_MISSING")
    return decode_json(body), bound[-1], body, len(bound)


def _decimal_text(value: Any, field: str, *, nonnegative: bool = False, positive: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise AcquisitionError("PROVIDER_DECIMAL_INVALID", field)
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise AcquisitionError("PROVIDER_DECIMAL_INVALID", field) from error
    if not number.is_finite():
        raise AcquisitionError("PROVIDER_DECIMAL_INVALID", field)
    if nonnegative and number < 0:
        raise AcquisitionError("PROVIDER_DECIMAL_NEGATIVE", field)
    if positive and number <= 0:
        raise AcquisitionError("PROVIDER_DECIMAL_NONPOSITIVE", field)
    return value


def _normalize_bar(
    stream: str,
    symbol: str,
    row: Any,
    *,
    receipt: ResponseReceipt,
    provider_as_of_ms: int,
) -> ObservationCandidate | None:
    if not isinstance(row, list) or len(row) != 12:
        raise AcquisitionError("BAR_SCHEMA_INVALID", f"{stream}/{symbol}")
    if type(row[0]) is not int or type(row[6]) is not int:
        raise AcquisitionError("BAR_TIMESTAMP_INVALID")
    open_time = row[0]
    close_time = row[6]
    if close_time >= provider_as_of_ms - CLOSE_SAFETY_MARGIN_MS:
        return None
    if close_time < open_time or close_time - open_time > INTERVAL_MS + 10_000:
        raise AcquisitionError("BAR_INTERVAL_INVALID")
    open_text = _decimal_text(row[1], "open", positive=True)
    high_text = _decimal_text(row[2], "high", positive=True)
    low_text = _decimal_text(row[3], "low", positive=True)
    close_text = _decimal_text(row[4], "close", positive=True)
    open_value, high_value, low_value, close_value = map(Decimal, (open_text, high_text, low_text, close_text))
    if high_value < low_value or not (low_value <= open_value <= high_value) or not (low_value <= close_value <= high_value):
        raise AcquisitionError("BAR_PRICE_RELATION_INVALID")
    payload: dict[str, Any] = {
        "open_time_ms": open_time,
        "close_time_ms": close_time,
        "open": open_text,
        "high": high_text,
        "low": low_text,
        "close": close_text,
        "normalizer_id": NORMALIZER_ID,
        "availability_policy_id": AVAILABILITY_POLICY_ID,
    }
    if stream in {"spot_ohlcv", "perpetual_ohlcv"}:
        payload["volume"] = _decimal_text(row[5], "volume", nonnegative=True)
        payload["quote_volume"] = _decimal_text(row[7], "quote_volume", nonnegative=True)
        if type(row[8]) is not int or row[8] < 0:
            raise AcquisitionError("BAR_TRADE_COUNT_INVALID")
        payload["trade_count"] = row[8]
    return ObservationCandidate(
        stream=stream,
        symbol=symbol,
        interval=INTERVAL,
        event_time_ms=close_time,
        available_at=receipt.received_at,
        receipt_hash=receipt.receipt_hash,
        response_hash=receipt.response_hash,
        payload=payload,
    )


def _normalize_funding(
    symbol: str,
    row: Any,
    *,
    receipt: ResponseReceipt,
    provider_as_of_ms: int,
) -> ObservationCandidate | None:
    if not isinstance(row, dict):
        raise AcquisitionError("FUNDING_SCHEMA_INVALID")
    allowed = {"symbol", "fundingTime", "fundingRate", "markPrice", "rateType"}
    if set(row) - allowed or not {"symbol", "fundingTime", "fundingRate", "markPrice"} <= set(row):
        raise AcquisitionError("FUNDING_SCHEMA_INVALID")
    returned = row["symbol"]
    if not isinstance(returned, str) or returned.upper() != symbol:
        raise AcquisitionError("FUNDING_SYMBOL_MISMATCH")
    if type(row["fundingTime"]) is not int:
        raise AcquisitionError("FUNDING_TIMESTAMP_INVALID")
    event_time = row["fundingTime"]
    if event_time > provider_as_of_ms:
        return None
    rate_type = row.get("rateType")
    if rate_type is not None and rate_type not in {"Regular", "Special"}:
        raise AcquisitionError("FUNDING_RATE_TYPE_UNKNOWN", str(rate_type))
    payload = {
        "funding_time_ms": event_time,
        "funding_rate": _decimal_text(row["fundingRate"], "funding_rate"),
        "mark_price": _decimal_text(row["markPrice"], "mark_price", positive=True),
        "rate_type": rate_type,
        "normalizer_id": NORMALIZER_ID,
        "availability_policy_id": AVAILABILITY_POLICY_ID,
    }
    return ObservationCandidate(
        stream="funding_rates",
        symbol=symbol,
        interval=None,
        event_time_ms=event_time,
        available_at=receipt.received_at,
        receipt_hash=receipt.receipt_hash,
        response_hash=receipt.response_hash,
        payload=payload,
    )


def _funding_config_rows(payload: Any, symbol: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        rows = [payload]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise AcquisitionError("FUNDING_INFO_SCHEMA_INVALID")
    selected: list[dict[str, Any]] = []
    allowed = {
        "symbol",
        "adjustedFundingRateCap",
        "adjustedFundingRateFloor",
        "fundingIntervalHours",
        "disclaimer",
        "updateTime",
    }
    for row in rows:
        if not isinstance(row, dict) or set(row) - allowed:
            raise AcquisitionError("FUNDING_INFO_SCHEMA_INVALID")
        returned = row.get("symbol")
        if not isinstance(returned, str):
            raise AcquisitionError("FUNDING_INFO_SCHEMA_INVALID")
        if returned.upper() != symbol:
            continue
        interval = row.get("fundingIntervalHours")
        if type(interval) is not int or interval <= 0 or interval > 24:
            raise AcquisitionError("FUNDING_INTERVAL_INVALID")
        disclaimer = row.get("disclaimer")
        if disclaimer is not None and type(disclaimer) is not bool:
            raise AcquisitionError("FUNDING_INFO_DISCLAIMER_INVALID")
        update_time = row.get("updateTime")
        if update_time is not None and (type(update_time) is not int or update_time < 0):
            raise AcquisitionError("FUNDING_INFO_UPDATE_TIME_INVALID")
        cap = row.get("adjustedFundingRateCap")
        floor = row.get("adjustedFundingRateFloor")
        selected.append(
            {
                "symbol": symbol,
                "funding_interval_hours": interval,
                "funding_rate_cap": None if cap is None else _decimal_text(cap, "funding_rate_cap"),
                "funding_rate_floor": None if floor is None else _decimal_text(floor, "funding_rate_floor"),
                "disclaimer": disclaimer,
                "provider_update_time_ms": update_time,
            }
        )
    return selected


def _initial_window(provider_as_of_ms: int) -> tuple[int, int]:
    last_closed_start = ((provider_as_of_ms - CLOSE_SAFETY_MARGIN_MS) // INTERVAL_MS - 1) * INTERVAL_MS
    start = max(0, last_closed_start)
    return start, start + INTERVAL_MS


def _capture_window(journal: Journal, provider_as_of_ms: int) -> tuple[int, int]:
    checkpoints = [journal.checkpoint(stream, symbol) for stream in STREAMS for symbol in SYMBOLS]
    present = [value for value in checkpoints if value is not None]
    if not present:
        return _initial_window(provider_as_of_ms)
    earliest = min(present)
    latest_closed_exclusive = ((provider_as_of_ms - CLOSE_SAFETY_MARGIN_MS) // INTERVAL_MS) * INTERVAL_MS
    first_row = journal.conn.execute(
        "SELECT MIN(o.event_time_ms) FROM observations o "
        "JOIN capture_batches b ON b.batch_id=o.batch_id WHERE b.status='COMPLETE'"
    ).fetchone()
    first_event = None if first_row is None or first_row[0] is None else int(first_row[0])
    origin_floor = 0 if first_event is None else max(0, (first_event // INTERVAL_MS) * INTERVAL_MS)
    if latest_closed_exclusive <= earliest:
        sweep_start = max(origin_floor, latest_closed_exclusive - REVISION_SWEEP_HOURS * INTERVAL_MS)
        return sweep_start, latest_closed_exclusive
    if latest_closed_exclusive - earliest > MAX_CATCHUP_HOURS * INTERVAL_MS:
        raise AcquisitionError("CAPTURE_GAP_EXCEEDS_CONTRACT")
    sweep_start = max(origin_floor, earliest - REVISION_SWEEP_HOURS * INTERVAL_MS)
    return sweep_start, latest_closed_exclusive


def _data_params(stream: str, symbol: str, start_ms: int, end_exclusive_ms: int) -> dict[str, Any]:
    common = {
        "startTime": start_ms,
        "endTime": max(start_ms, end_exclusive_ms - 1),
        "limit": PAGE_LIMIT,
    }
    if stream == "spot_ohlcv":
        return {"symbol": symbol, "interval": INTERVAL, **common}
    if stream in {"perpetual_ohlcv", "mark_price_ohlcv"}:
        return {"symbol": symbol, "interval": INTERVAL, **common}
    if stream == "index_price_ohlcv":
        return {"pair": symbol, "interval": INTERVAL, **common}
    return {"symbol": symbol, **common}


def _capture_once_with_transport(
    runtime_root: str | Path,
    *,
    acknowledgement: str,
    opener: Any | None,
) -> CaptureSummary:
    if acknowledgement != ACK_CAPTURE:
        raise AcquisitionError("CAPTURE_ACKNOWLEDGEMENT_REQUIRED")
    _, _, _, contract = load_contracts()
    code_commit = repository_identity()
    runtime = validate_runtime_root(runtime_root)
    with acquisition_lock(runtime):
        batch_started, _ = utc_now_ms()
        batch_id = "m100-" + canonical_hash(
            {
                "commit": code_commit,
                "started_at": batch_started,
                "monotonic_ns": time.monotonic_ns(),
                "pid": os.getpid(),
            }
        )[:32]
        with Journal.open(runtime) as journal:
            if journal.conn.execute(
                "SELECT 1 FROM capture_batches WHERE status='RUNNING' LIMIT 1"
            ).fetchone() is not None:
                raise AcquisitionError("INCOMPLETE_CAPTURE_BATCH_PRESENT")
            journal.begin_batch(batch_id, str(contract["contract_hash_sha256"]), code_commit)
            request_count = 0
            receipt_count = 0
            inserted = 0
            duplicates = 0
            checkpoint_updates: dict[tuple[str, str], int] = {}
            pending_candidates: dict[str, ObservationCandidate] = {}
            try:
                # Provider clock responses are captured through the same evidence path
                # as every other request, including retry attempts.
                spot_payload, spot_receipt, _spot_body, spot_attempts = _request_and_persist(
                    journal,
                    batch_id,
                    "spot_time",
                    {},
                    request_id=f"{batch_id}:clock:spot",
                    clock_status=ClockStatus.UNKNOWN,
                    opener=opener,
                )
                request_count += 1
                receipt_count += spot_attempts
                if not isinstance(spot_payload, dict) or type(spot_payload.get("serverTime")) is not int:
                    raise AcquisitionError("SERVER_TIME_SCHEMA_INVALID", "spot")
                spot_server = int(spot_payload["serverTime"])

                futures_payload, fut_receipt, _fut_body, fut_attempts = _request_and_persist(
                    journal,
                    batch_id,
                    "futures_time",
                    {},
                    request_id=f"{batch_id}:clock:futures",
                    clock_status=ClockStatus.UNKNOWN,
                    opener=opener,
                )
                request_count += 1
                receipt_count += fut_attempts
                if not isinstance(futures_payload, dict) or type(futures_payload.get("serverTime")) is not int:
                    raise AcquisitionError("SERVER_TIME_SCHEMA_INVALID", "futures")
                futures_server = int(futures_payload["serverTime"])

                spot_status = _clock_status(spot_server, spot_receipt)
                futures_status = _clock_status(futures_server, fut_receipt)
                if spot_status is not ClockStatus.HEALTHY or futures_status is not ClockStatus.HEALTHY:
                    raise AcquisitionError("PROVIDER_CLOCK_UNHEALTHY")
                provider_as_of = min(spot_server, futures_server)
                start_ms, end_exclusive_ms = _capture_window(journal, provider_as_of)
                if end_exclusive_ms < start_ms:
                    raise AcquisitionError("CAPTURE_WINDOW_INVALID")

                # Binance documents fundingInfo as a zero-parameter endpoint that
                # returns only symbols with adjusted funding configuration. Capture it
                # once per cycle, then retain only entries in our frozen universe.
                payload, receipt, _, attempts_used = _request_and_persist(
                    journal,
                    batch_id,
                    "funding_info",
                    {},
                    request_id=f"{batch_id}:funding-info",
                    clock_status=ClockStatus.HEALTHY,
                    opener=opener,
                )
                request_count += 1
                receipt_count += attempts_used
                for symbol in SYMBOLS:
                    for config in _funding_config_rows(payload, symbol):
                        payload_json = canonical_json(config)
                        journal.conn.execute(
                            "INSERT OR IGNORE INTO funding_configs(symbol,observed_at,funding_interval_hours,funding_rate_cap,funding_rate_floor,receipt_hash,payload_json,payload_hash) "
                            "VALUES (?,?,?,?,?,?,?,?)",
                            (
                                symbol,
                                receipt.received_at,
                                config["funding_interval_hours"],
                                config["funding_rate_cap"],
                                config["funding_rate_floor"],
                                receipt.receipt_hash,
                                payload_json,
                                canonical_hash(config),
                            ),
                        )

                for stream in STREAMS:
                    for symbol in SYMBOLS:
                        if request_count >= MAX_LOGICAL_REQUESTS:
                            raise AcquisitionError("CAPTURE_REQUEST_BUDGET_EXHAUSTED")
                        params = _data_params(stream, symbol, start_ms, end_exclusive_ms)
                        payload, receipt, _, attempts_used = _request_and_persist(
                            journal,
                            batch_id,
                            stream,
                            params,
                            request_id=f"{batch_id}:{stream}:{symbol}",
                            clock_status=ClockStatus.HEALTHY,
                            opener=opener,
                        )
                        request_count += 1
                        receipt_count += attempts_used
                        if not isinstance(payload, list):
                            raise AcquisitionError("PROVIDER_RESPONSE_NOT_ARRAY", stream)
                        for row in payload:
                            candidate = (
                                _normalize_bar(stream, symbol, row, receipt=receipt, provider_as_of_ms=provider_as_of)
                                if stream in BAR_STREAMS
                                else _normalize_funding(symbol, row, receipt=receipt, provider_as_of_ms=provider_as_of)
                            )
                            if candidate is None:
                                continue
                            if not (start_ms <= candidate.event_time_ms < end_exclusive_ms + INTERVAL_MS):
                                continue
                            existing = pending_candidates.get(candidate.logical_id)
                            if existing is None:
                                pending_candidates[candidate.logical_id] = candidate
                            elif existing.payload_hash == candidate.payload_hash:
                                duplicates += 1
                            else:
                                raise AcquisitionError("CONFLICTING_DUPLICATE_IN_BATCH")
                        checkpoint_updates[(stream, symbol)] = end_exclusive_ms

                # Only after every bounded network request and schema check succeeds do
                # observations enter the authoritative revision chain. Receipts and raw
                # objects from a failed batch remain preserved, but cannot poison later
                # revision numbers.
                for candidate in sorted(
                    pending_candidates.values(),
                    key=lambda item: (item.stream, item.symbol, item.event_time_ms, item.logical_id),
                ):
                    _, was_inserted = journal.add_observation(batch_id, candidate)
                    if was_inserted:
                        inserted += 1
                    else:
                        duplicates += 1
                journal.finish_batch(
                    batch_id,
                    checkpoint_updates=checkpoint_updates,
                    request_count=request_count,
                    receipt_count=receipt_count,
                    observation_count=inserted,
                )
                return CaptureSummary(
                    batch_id=batch_id,
                    status="COMPLETE",
                    requests=request_count,
                    receipts=receipt_count,
                    observations_inserted=inserted,
                    exact_duplicates=duplicates,
                    clock_status="HEALTHY",
                    start_event_time_ms=start_ms,
                    end_event_time_exclusive_ms=end_exclusive_ms,
                )
            except Exception as error:
                reason = error.reason if isinstance(error, AcquisitionError) else type(error).__name__
                # Observation/checkpoint writes are intentionally deferred to the
                # final transaction. Roll them back before sealing a failed batch so
                # partial authoritative state can never survive an application error.
                journal.conn.rollback()
                persisted_receipts = int(
                    journal.conn.execute(
                        "SELECT COUNT(*) FROM receipts WHERE batch_id=?", (batch_id,)
                    ).fetchone()[0]
                )
                journal.mark_failed(
                    batch_id,
                    reason,
                    request_count=request_count,
                    receipt_count=persisted_receipts,
                )
                raise


def capture_once(
    runtime_root: str | Path,
    *,
    acknowledgement: str,
) -> CaptureSummary:
    """Run one bounded production capture using the fixed verified HTTPS transport."""
    return _capture_once_with_transport(
        runtime_root,
        acknowledgement=acknowledgement,
        opener=None,
    )
