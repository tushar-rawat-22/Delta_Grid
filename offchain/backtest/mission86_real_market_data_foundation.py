"""Mission 86: Real-Market Data Foundation.

Collects the exact public Binance market-data streams authorized by the
locked Mission 85 funding-carry research charter:

- spot OHLCV;
- USD-M perpetual OHLCV;
- mark-price OHLC;
- index-price OHLC;
- settled funding-rate history.

The implementation is append-safe and resumable. Every HTTP response is
preserved as a gzip file and linked to normalized database rows by SHA-256
provenance.

Mission 86 does not certify research quality. It performs no backtesting,
parameter evaluation, holdout inspection, model training, model promotion,
signal generation, order placement, signing, private-key use, leverage, paid
API use, capital deployment, or profitability analysis.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

import requests

from offchain.research.funding_carry_research_contract import (
    CAPITAL_DEPLOYMENT,
    CONTRACT_ID,
    LIVE_ORDER_SENT,
    LIVE_TRADING,
    contract_hash,
    load_locked_contract,
)


EXPECTED_CONTRACT_HASH = (
    "b7aec799a1d63dae5441118159d8fea5cafa0b62e69161d0b43e2e6c1a7e2ebf"
)

MISSION86_STATUS_COMPLETE = (
    "COMPLETE_UNCERTIFIED_REAL_MARKET_DATA_FOUNDATION"
)
MISSION86_STATUS_BLOCKED = "MISSION86_DATA_FOUNDATION_BLOCKED"
MISSION87_STATUS_READY = "READY_FOR_DATASET_CERTIFICATION"
MISSION87_STATUS_BLOCKED = "BLOCKED_PENDING_MISSION86_REMEDIATION"

GLOBAL_VERDICT_COMPLETE = (
    "MISSION86_REAL_MARKET_DATA_CAPTURED_UNCERTIFIED"
)
GLOBAL_VERDICT_BLOCKED = "MISSION86_DATA_CAPTURE_INCOMPLETE_OR_UNSAFE"

NEXT_MISSION = "Mission 87 Dataset Certification and Quality Gate"

DEFAULT_DB_PATH = Path("offchain/deltagrid.db")
DEFAULT_CONTRACT_PATH = Path(
    "offchain/research/contracts/"
    "mission85_funding_carry_charter_v1.json"
)
DEFAULT_DATA_ROOT = Path("offchain/data/mission86")

DEFAULT_SPOT_BASE_URL = "https://data-api.binance.vision"
DEFAULT_FUTURES_BASE_URL = "https://fapi.binance.com"

CANONICAL_INTERVAL = "1h"
INTERVAL_MS = 60 * 60 * 1000
PAGE_LIMIT = 1000

STREAMS = (
    "spot_ohlcv",
    "perpetual_ohlcv",
    "mark_price_ohlcv",
    "index_price_ohlcv",
    "funding_rates",
)

BAR_STREAMS = (
    "spot_ohlcv",
    "perpetual_ohlcv",
    "mark_price_ohlcv",
    "index_price_ohlcv",
)

ALLOWED_HOSTS = {
    "data-api.binance.vision",
    "api.binance.com",
    "fapi.binance.com",
}

CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"


@dataclass(frozen=True)
class RequestSpec:
    stream: str
    symbol: str
    url: str
    params: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_utc_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        raise ValueError(
            f"timestamp must include timezone: {value}"
        )

    return int(
        parsed.astimezone(timezone.utc).timestamp() * 1000
    )


def ms_to_iso(value: int | None) -> str | None:
    if value is None:
        return None

    return datetime.fromtimestamp(
        value / 1000,
        tz=timezone.utc,
    ).isoformat()


def load_authoritative_contract(
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    envelope = load_locked_contract(contract_path)
    contract = envelope["contract"]
    actual_hash = contract_hash(contract)

    if actual_hash != EXPECTED_CONTRACT_HASH:
        raise RuntimeError(
            "Mission 85 contract hash differs from the "
            "authoritative locked hash"
        )

    if contract.get("contract_id") != CONTRACT_ID:
        raise RuntimeError(
            "Mission 85 contract identifier is not authoritative"
        )

    data_contract = contract.get("data_contract", {})
    universe = contract.get("universe", {})
    authorization = contract.get(
        "mission86_authorization",
        {},
    )

    if universe.get("symbols") != [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
    ]:
        raise RuntimeError(
            "Mission 86 universe must be exactly BTC, ETH, SOL"
        )

    if set(data_contract.get("required_streams", [])) != set(
        STREAMS
    ):
        raise RuntimeError(
            "Mission 85 required stream contract is incomplete"
        )

    prohibited_flags = (
        "allow_synthetic_data",
        "allow_offline_sample",
        "allow_sample_fallback",
        "allow_silent_substitution",
    )

    if any(
        data_contract.get(field) is not False
        for field in prohibited_flags
    ):
        raise RuntimeError(
            "Mission 85 data contract permits a prohibited fallback"
        )

    if authorization.get("backtesting_authorized") is not False:
        raise RuntimeError(
            "Mission 86 must not authorize backtesting"
        )

    if authorization.get("live_trading_authorized") is not False:
        raise RuntimeError(
            "Mission 86 must not authorize live trading"
        )

    if (
        authorization.get("capital_deployment_authorized")
        is not False
    ):
        raise RuntimeError(
            "Mission 86 must not authorize capital deployment"
        )

    return contract


def validate_public_base_url(value: str) -> str:
    parsed = urlparse(value)

    if parsed.scheme != "https":
        raise ValueError("market-data base URL must use HTTPS")

    if parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(
            f"market-data host is not allowlisted: {parsed.hostname}"
        )

    return value.rstrip("/")


def build_request_spec(
    stream: str,
    symbol: str,
    start_time_ms: int,
    end_time_exclusive_ms: int,
    *,
    interval: str = CANONICAL_INTERVAL,
    limit: int = PAGE_LIMIT,
    spot_base_url: str = DEFAULT_SPOT_BASE_URL,
    futures_base_url: str = DEFAULT_FUTURES_BASE_URL,
) -> RequestSpec:
    if stream not in STREAMS:
        raise ValueError(f"unsupported Mission 86 stream: {stream}")

    if symbol not in {
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
    }:
        raise ValueError(f"unsupported Mission 86 symbol: {symbol}")

    if interval != CANONICAL_INTERVAL:
        raise ValueError(
            "Mission 86 canonical interval must remain 1h"
        )

    if not 1 <= limit <= 1000:
        raise ValueError("page limit must be between 1 and 1000")

    if end_time_exclusive_ms <= start_time_ms:
        raise ValueError("invalid request time range")

    spot_base = validate_public_base_url(spot_base_url)
    futures_base = validate_public_base_url(
        futures_base_url
    )

    common = {
        "startTime": int(start_time_ms),
        "endTime": int(end_time_exclusive_ms - 1),
        "limit": int(limit),
    }

    if stream == "spot_ohlcv":
        return RequestSpec(
            stream=stream,
            symbol=symbol,
            url=f"{spot_base}/api/v3/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                **common,
            },
        )

    if stream == "perpetual_ohlcv":
        return RequestSpec(
            stream=stream,
            symbol=symbol,
            url=f"{futures_base}/fapi/v1/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                **common,
            },
        )

    if stream == "mark_price_ohlcv":
        return RequestSpec(
            stream=stream,
            symbol=symbol,
            url=(
                f"{futures_base}/fapi/v1/"
                "markPriceKlines"
            ),
            params={
                "symbol": symbol,
                "interval": interval,
                **common,
            },
        )

    if stream == "index_price_ohlcv":
        return RequestSpec(
            stream=stream,
            symbol=symbol,
            url=(
                f"{futures_base}/fapi/v1/"
                "indexPriceKlines"
            ),
            params={
                "pair": symbol,
                "interval": interval,
                **common,
            },
        )

    return RequestSpec(
        stream=stream,
        symbol=symbol,
        url=f"{futures_base}/fapi/v1/fundingRate",
        params={
            "symbol": symbol,
            **common,
        },
    )


def ensure_schema(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS
                mission86_ingestion_runs (
                run_label TEXT PRIMARY KEY,
                contract_id TEXT NOT NULL,
                contract_hash TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                run_status TEXT NOT NULL,
                symbol_count INTEGER NOT NULL,
                stream_count INTEGER NOT NULL,
                stream_symbol_count INTEGER NOT NULL,
                market_bar_count INTEGER NOT NULL,
                funding_rate_count INTEGER NOT NULL,
                raw_response_count INTEGER NOT NULL,
                manifest_hash TEXT,
                check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                mission87_status TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                next_mission TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                error_text TEXT NOT NULL,
                summary_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS
                mission86_raw_responses (
                response_hash TEXT PRIMARY KEY,
                contract_hash TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                stream TEXT NOT NULL,
                symbol TEXT NOT NULL,
                request_method TEXT NOT NULL,
                request_url TEXT NOT NULL,
                request_params_json TEXT NOT NULL,
                http_status INTEGER NOT NULL,
                body_sha256 TEXT NOT NULL,
                raw_path TEXT NOT NULL,
                response_row_count INTEGER NOT NULL,
                response_headers_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS
                mission86_market_bars (
                contract_hash TEXT NOT NULL,
                stream TEXT NOT NULL,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                open_time_ms INTEGER NOT NULL,
                close_time_ms INTEGER NOT NULL,
                open_price TEXT NOT NULL,
                high_price TEXT NOT NULL,
                low_price TEXT NOT NULL,
                close_price TEXT NOT NULL,
                volume TEXT,
                quote_volume TEXT,
                trade_count INTEGER,
                response_hash TEXT NOT NULL,
                source_url TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                PRIMARY KEY (
                    contract_hash,
                    stream,
                    symbol,
                    interval,
                    open_time_ms
                )
            );

            CREATE TABLE IF NOT EXISTS
                mission86_funding_rates (
                contract_hash TEXT NOT NULL,
                symbol TEXT NOT NULL,
                funding_time_ms INTEGER NOT NULL,
                funding_rate TEXT NOT NULL,
                mark_price TEXT,
                response_hash TEXT NOT NULL,
                source_url TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                PRIMARY KEY (
                    contract_hash,
                    symbol,
                    funding_time_ms
                )
            );

            CREATE TABLE IF NOT EXISTS
                mission86_ingestion_checkpoints (
                contract_hash TEXT NOT NULL,
                stream TEXT NOT NULL,
                symbol TEXT NOT NULL,
                next_start_time_ms INTEGER NOT NULL,
                completed INTEGER NOT NULL,
                page_count INTEGER NOT NULL,
                response_row_count INTEGER NOT NULL,
                last_response_hash TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (
                    contract_hash,
                    stream,
                    symbol
                )
            );

            CREATE TABLE IF NOT EXISTS
                mission86_stream_coverage (
                run_label TEXT NOT NULL,
                stream TEXT NOT NULL,
                symbol TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                expected_row_count INTEGER,
                coverage_ratio REAL,
                minimum_timestamp_ms INTEGER,
                maximum_timestamp_ms INTEGER,
                minimum_timestamp_utc TEXT,
                maximum_timestamp_utc TEXT,
                coverage_fragment_hash TEXT NOT NULL,
                certification_status TEXT NOT NULL,
                PRIMARY KEY (
                    run_label,
                    stream,
                    symbol
                )
            );

            CREATE TABLE IF NOT EXISTS
                mission86_foundation_checks (
                check_id TEXT PRIMARY KEY,
                run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                expected_value TEXT NOT NULL,
                check_reason TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS
                mission86_dataset_manifests (
                run_label TEXT PRIMARY KEY,
                contract_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                manifest_hash TEXT NOT NULL,
                manifest_path TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                certification_status TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS
                idx_mission86_bar_lookup
            ON mission86_market_bars (
                contract_hash,
                stream,
                symbol,
                open_time_ms
            );

            CREATE INDEX IF NOT EXISTS
                idx_mission86_funding_lookup
            ON mission86_funding_rates (
                contract_hash,
                symbol,
                funding_time_ms
            );

            CREATE INDEX IF NOT EXISTS
                idx_mission86_raw_contract
            ON mission86_raw_responses (
                contract_hash,
                stream,
                symbol
            );
            """
        )
        conn.commit()


def _response_content(response: Any) -> bytes:
    content = getattr(response, "content", None)

    if isinstance(content, bytes):
        return content

    text = getattr(response, "text", "")
    return str(text).encode("utf-8")


def request_json_page(
    session: Any,
    spec: RequestSpec,
    *,
    timeout_seconds: float = 30.0,
    maximum_retries: int = 5,
) -> tuple[list[Any], bytes, dict[str, str], int]:
    retryable_statuses = {418, 429, 500, 502, 503, 504}

    for attempt in range(maximum_retries + 1):
        try:
            response = session.get(
                spec.url,
                params=spec.params,
                timeout=timeout_seconds,
            )
        except requests.RequestException as exc:
            if attempt >= maximum_retries:
                raise RuntimeError(
                    f"public market-data request failed: {exc}"
                ) from exc

            time.sleep(min(2**attempt, 20))
            continue

        status = int(getattr(response, "status_code", 0))
        body = _response_content(response)
        headers = {
            str(key): str(value)
            for key, value in dict(
                getattr(response, "headers", {})
            ).items()
        }

        if status == 200:
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    "public market-data response was not valid JSON"
                ) from exc

            if not isinstance(payload, list):
                raise RuntimeError(
                    "public market-data response was not an array"
                )

            return payload, body, headers, status

        preview = body.decode(
            "utf-8",
            errors="replace",
        )[:300]

        if status == 451:
            raise RuntimeError(
                "Binance public endpoint returned HTTP 451. "
                "No fallback or substitute data was used. "
                f"Response: {preview}"
            )

        if (
            status in retryable_statuses
            and attempt < maximum_retries
        ):
            retry_after = headers.get(
                "Retry-After",
                headers.get("retry-after", ""),
            )

            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                delay = float(min(2**attempt, 20))

            time.sleep(max(delay, 0.1))
            continue

        raise RuntimeError(
            f"public market-data request failed with HTTP "
            f"{status}: {preview}"
        )

    raise RuntimeError("public market-data retry loop exhausted")


def preserve_raw_response(
    conn: sqlite3.Connection,
    *,
    contract_hash_value: str,
    data_root: str | Path,
    spec: RequestSpec,
    body: bytes,
    headers: Mapping[str, str],
    http_status: int,
    response_row_count: int,
    captured_at: str,
) -> str:
    request_identity = canonical_json(
        {
            "contract_hash": contract_hash_value,
            "method": "GET",
            "url": spec.url,
            "params": spec.params,
        }
    ).encode("utf-8")

    response_hash = sha256_bytes(
        request_identity + b"\n" + body
    )
    body_hash = sha256_bytes(body)

    root = Path(data_root)
    raw_directory = (
        root
        / "raw"
        / spec.stream
        / spec.symbol
    )
    raw_directory.mkdir(parents=True, exist_ok=True)

    raw_path = raw_directory / f"{response_hash}.json.gz"

    if not raw_path.exists():
        compressed = gzip.compress(body, mtime=0)
        temporary = raw_path.with_suffix(
            raw_path.suffix + ".tmp"
        )
        temporary.write_bytes(compressed)
        temporary.replace(raw_path)

    conn.execute(
        """
        INSERT OR IGNORE INTO mission86_raw_responses (
            response_hash,
            contract_hash,
            captured_at,
            stream,
            symbol,
            request_method,
            request_url,
            request_params_json,
            http_status,
            body_sha256,
            raw_path,
            response_row_count,
            response_headers_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            response_hash,
            contract_hash_value,
            captured_at,
            spec.stream,
            spec.symbol,
            "GET",
            spec.url,
            canonical_json(spec.params),
            http_status,
            body_hash,
            str(raw_path),
            response_row_count,
            canonical_json(dict(headers)),
        ),
    )

    return response_hash


def normalize_bar(
    stream: str,
    symbol: str,
    row: Any,
) -> dict[str, Any]:
    if not isinstance(row, list) or len(row) < 7:
        raise ValueError(
            f"invalid {stream} kline row for {symbol}"
        )

    open_time_ms = int(row[0])
    close_time_ms = int(row[6])

    result = {
        "open_time_ms": open_time_ms,
        "close_time_ms": close_time_ms,
        "open_price": str(row[1]),
        "high_price": str(row[2]),
        "low_price": str(row[3]),
        "close_price": str(row[4]),
        "volume": None,
        "quote_volume": None,
        "trade_count": None,
    }

    if stream in {"spot_ohlcv", "perpetual_ohlcv"}:
        result["volume"] = str(row[5])

        if len(row) > 7:
            result["quote_volume"] = str(row[7])

        if len(row) > 8:
            result["trade_count"] = int(row[8])

    return result


def normalize_funding(
    symbol: str,
    row: Any,
) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError(
            f"invalid funding row for {symbol}"
        )

    if "fundingTime" not in row or "fundingRate" not in row:
        raise ValueError(
            f"incomplete funding row for {symbol}"
        )

    returned_symbol = str(
        row.get("symbol", symbol)
    ).upper()

    if returned_symbol != symbol:
        raise ValueError(
            f"funding response symbol mismatch: {returned_symbol}"
        )

    return {
        "funding_time_ms": int(row["fundingTime"]),
        "funding_rate": str(row["fundingRate"]),
        "mark_price": (
            None
            if row.get("markPrice") is None
            else str(row["markPrice"])
        ),
    }


def _load_checkpoint(
    conn: sqlite3.Connection,
    contract_hash_value: str,
    stream: str,
    symbol: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM mission86_ingestion_checkpoints
        WHERE contract_hash = ?
          AND stream = ?
          AND symbol = ?
        """,
        (
            contract_hash_value,
            stream,
            symbol,
        ),
    ).fetchone()


def _save_checkpoint(
    conn: sqlite3.Connection,
    *,
    contract_hash_value: str,
    stream: str,
    symbol: str,
    next_start_time_ms: int,
    completed: int,
    page_count: int,
    response_row_count: int,
    last_response_hash: str | None,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO mission86_ingestion_checkpoints (
            contract_hash,
            stream,
            symbol,
            next_start_time_ms,
            completed,
            page_count,
            response_row_count,
            last_response_hash,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (
            contract_hash,
            stream,
            symbol
        ) DO UPDATE SET
            next_start_time_ms =
                excluded.next_start_time_ms,
            completed = excluded.completed,
            page_count = excluded.page_count,
            response_row_count =
                excluded.response_row_count,
            last_response_hash =
                excluded.last_response_hash,
            updated_at = excluded.updated_at
        """,
        (
            contract_hash_value,
            stream,
            symbol,
            next_start_time_ms,
            completed,
            page_count,
            response_row_count,
            last_response_hash,
            updated_at,
        ),
    )


def ingest_stream(
    conn: sqlite3.Connection,
    *,
    session: Any,
    contract_hash_value: str,
    data_root: str | Path,
    stream: str,
    symbol: str,
    start_time_ms: int,
    end_time_exclusive_ms: int,
    spot_base_url: str,
    futures_base_url: str,
    page_limit: int,
    timeout_seconds: float,
    maximum_retries: int,
    request_delay_seconds: float,
    maximum_pages: int = 10000,
) -> dict[str, Any]:
    checkpoint = _load_checkpoint(
        conn,
        contract_hash_value,
        stream,
        symbol,
    )

    if checkpoint is not None and int(
        checkpoint["completed"]
    ) == 1:
        return {
            "stream": stream,
            "symbol": symbol,
            "resumed": True,
            "already_complete": True,
            "page_count": int(checkpoint["page_count"]),
            "response_row_count": int(
                checkpoint["response_row_count"]
            ),
        }

    current_start = (
        int(checkpoint["next_start_time_ms"])
        if checkpoint is not None
        else start_time_ms
    )
    page_count = (
        int(checkpoint["page_count"])
        if checkpoint is not None
        else 0
    )
    response_row_count = (
        int(checkpoint["response_row_count"])
        if checkpoint is not None
        else 0
    )

    while current_start < end_time_exclusive_ms:
        if page_count >= maximum_pages:
            raise RuntimeError(
                f"maximum page limit exceeded for "
                f"{stream}/{symbol}"
            )

        spec = build_request_spec(
            stream=stream,
            symbol=symbol,
            start_time_ms=current_start,
            end_time_exclusive_ms=end_time_exclusive_ms,
            limit=page_limit,
            spot_base_url=spot_base_url,
            futures_base_url=futures_base_url,
        )

        payload, body, headers, http_status = (
            request_json_page(
                session,
                spec,
                timeout_seconds=timeout_seconds,
                maximum_retries=maximum_retries,
            )
        )

        captured_at = utc_now()
        response_hash = preserve_raw_response(
            conn,
            contract_hash_value=contract_hash_value,
            data_root=data_root,
            spec=spec,
            body=body,
            headers=headers,
            http_status=http_status,
            response_row_count=len(payload),
            captured_at=captured_at,
        )

        page_count += 1
        response_row_count += len(payload)

        if not payload:
            _save_checkpoint(
                conn,
                contract_hash_value=contract_hash_value,
                stream=stream,
                symbol=symbol,
                next_start_time_ms=current_start,
                completed=1,
                page_count=page_count,
                response_row_count=response_row_count,
                last_response_hash=response_hash,
                updated_at=captured_at,
            )
            conn.commit()
            break

        timestamps: list[int] = []

        if stream in BAR_STREAMS:
            for raw_row in payload:
                row = normalize_bar(
                    stream,
                    symbol,
                    raw_row,
                )
                timestamp = int(row["open_time_ms"])
                timestamps.append(timestamp)

                if not (
                    start_time_ms
                    <= timestamp
                    < end_time_exclusive_ms
                ):
                    continue

                conn.execute(
                    """
                    INSERT INTO mission86_market_bars (
                        contract_hash,
                        stream,
                        symbol,
                        interval,
                        open_time_ms,
                        close_time_ms,
                        open_price,
                        high_price,
                        low_price,
                        close_price,
                        volume,
                        quote_volume,
                        trade_count,
                        response_hash,
                        source_url,
                        inserted_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT (
                        contract_hash,
                        stream,
                        symbol,
                        interval,
                        open_time_ms
                    ) DO UPDATE SET
                        close_time_ms =
                            excluded.close_time_ms,
                        open_price = excluded.open_price,
                        high_price = excluded.high_price,
                        low_price = excluded.low_price,
                        close_price = excluded.close_price,
                        volume = excluded.volume,
                        quote_volume = excluded.quote_volume,
                        trade_count = excluded.trade_count,
                        response_hash = excluded.response_hash,
                        source_url = excluded.source_url,
                        inserted_at = excluded.inserted_at
                    """,
                    (
                        contract_hash_value,
                        stream,
                        symbol,
                        CANONICAL_INTERVAL,
                        timestamp,
                        int(row["close_time_ms"]),
                        row["open_price"],
                        row["high_price"],
                        row["low_price"],
                        row["close_price"],
                        row["volume"],
                        row["quote_volume"],
                        row["trade_count"],
                        response_hash,
                        spec.url,
                        captured_at,
                    ),
                )

            next_start = max(timestamps) + INTERVAL_MS

        else:
            for raw_row in payload:
                row = normalize_funding(
                    symbol,
                    raw_row,
                )
                timestamp = int(
                    row["funding_time_ms"]
                )
                timestamps.append(timestamp)

                if not (
                    start_time_ms
                    <= timestamp
                    < end_time_exclusive_ms
                ):
                    continue

                conn.execute(
                    """
                    INSERT INTO mission86_funding_rates (
                        contract_hash,
                        symbol,
                        funding_time_ms,
                        funding_rate,
                        mark_price,
                        response_hash,
                        source_url,
                        inserted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (
                        contract_hash,
                        symbol,
                        funding_time_ms
                    ) DO UPDATE SET
                        funding_rate = excluded.funding_rate,
                        mark_price = excluded.mark_price,
                        response_hash = excluded.response_hash,
                        source_url = excluded.source_url,
                        inserted_at = excluded.inserted_at
                    """,
                    (
                        contract_hash_value,
                        symbol,
                        timestamp,
                        row["funding_rate"],
                        row["mark_price"],
                        response_hash,
                        spec.url,
                        captured_at,
                    ),
                )

            next_start = max(timestamps) + 1

        if next_start <= current_start:
            raise RuntimeError(
                f"non-advancing pagination for {stream}/{symbol}"
            )

        completed = int(
            next_start >= end_time_exclusive_ms
        )

        _save_checkpoint(
            conn,
            contract_hash_value=contract_hash_value,
            stream=stream,
            symbol=symbol,
            next_start_time_ms=next_start,
            completed=completed,
            page_count=page_count,
            response_row_count=response_row_count,
            last_response_hash=response_hash,
            updated_at=captured_at,
        )
        conn.commit()

        current_start = next_start

        if completed:
            break

        if request_delay_seconds > 0:
            time.sleep(request_delay_seconds)

    return {
        "stream": stream,
        "symbol": symbol,
        "resumed": checkpoint is not None,
        "already_complete": False,
        "page_count": page_count,
        "response_row_count": response_row_count,
    }


def _make_check(
    run_label: str,
    created_at: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    expected: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": (
            f"{run_label}-"
            f"{name.lower().replace('_', '-')}"
        ),
        "run_label": run_label,
        "created_at": created_at,
        "check_category": category,
        "check_name": name,
        "check_status": (
            CHECK_PASS if passed else CHECK_FAIL
        ),
        "observed_value": str(observed),
        "expected_value": str(expected),
        "check_reason": reason,
    }


def build_coverage(
    conn: sqlite3.Connection,
    *,
    run_label: str,
    contract_hash_value: str,
    symbols: list[str],
    start_time_ms: int,
    end_time_exclusive_ms: int,
) -> list[dict[str, Any]]:
    coverage: list[dict[str, Any]] = []
    expected_bar_rows = (
        end_time_exclusive_ms - start_time_ms
    ) // INTERVAL_MS

    for stream in STREAMS:
        for symbol in symbols:
            if stream in BAR_STREAMS:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS row_count,
                        MIN(open_time_ms) AS minimum_timestamp_ms,
                        MAX(open_time_ms) AS maximum_timestamp_ms
                    FROM mission86_market_bars
                    WHERE contract_hash = ?
                      AND stream = ?
                      AND symbol = ?
                      AND interval = ?
                      AND open_time_ms >= ?
                      AND open_time_ms < ?
                    """,
                    (
                        contract_hash_value,
                        stream,
                        symbol,
                        CANONICAL_INTERVAL,
                        start_time_ms,
                        end_time_exclusive_ms,
                    ),
                ).fetchone()
                expected = int(expected_bar_rows)
            else:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS row_count,
                        MIN(funding_time_ms)
                            AS minimum_timestamp_ms,
                        MAX(funding_time_ms)
                            AS maximum_timestamp_ms
                    FROM mission86_funding_rates
                    WHERE contract_hash = ?
                      AND symbol = ?
                      AND funding_time_ms >= ?
                      AND funding_time_ms < ?
                    """,
                    (
                        contract_hash_value,
                        symbol,
                        start_time_ms,
                        end_time_exclusive_ms,
                    ),
                ).fetchone()
                expected = None

            row_count = int(row["row_count"])
            minimum = row["minimum_timestamp_ms"]
            maximum = row["maximum_timestamp_ms"]
            ratio = (
                None
                if expected is None or expected == 0
                else row_count / expected
            )

            fragment = {
                "stream": stream,
                "symbol": symbol,
                "row_count": row_count,
                "expected_row_count": expected,
                "coverage_ratio": ratio,
                "minimum_timestamp_ms": minimum,
                "maximum_timestamp_ms": maximum,
            }

            coverage.append(
                {
                    **fragment,
                    "minimum_timestamp_utc": ms_to_iso(
                        minimum
                    ),
                    "maximum_timestamp_utc": ms_to_iso(
                        maximum
                    ),
                    "coverage_fragment_hash": (
                        sha256_bytes(
                            canonical_json(
                                fragment
                            ).encode("utf-8")
                        )
                    ),
                    "certification_status": (
                        "UNCERTIFIED_PENDING_MISSION87"
                    ),
                }
            )

    conn.execute(
        """
        DELETE FROM mission86_stream_coverage
        WHERE run_label = ?
        """,
        (run_label,),
    )

    for item in coverage:
        conn.execute(
            """
            INSERT INTO mission86_stream_coverage (
                run_label,
                stream,
                symbol,
                row_count,
                expected_row_count,
                coverage_ratio,
                minimum_timestamp_ms,
                maximum_timestamp_ms,
                minimum_timestamp_utc,
                maximum_timestamp_utc,
                coverage_fragment_hash,
                certification_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_label,
                item["stream"],
                item["symbol"],
                item["row_count"],
                item["expected_row_count"],
                item["coverage_ratio"],
                item["minimum_timestamp_ms"],
                item["maximum_timestamp_ms"],
                item["minimum_timestamp_utc"],
                item["maximum_timestamp_utc"],
                item["coverage_fragment_hash"],
                item["certification_status"],
            ),
        )

    return coverage


def build_manifest(
    conn: sqlite3.Connection,
    *,
    run_label: str,
    contract_hash_value: str,
    data_root: str | Path,
    coverage: list[dict[str, Any]],
    created_at: str,
) -> tuple[str, Path, dict[str, Any]]:
    raw_rows = conn.execute(
        """
        SELECT
            response_hash,
            stream,
            symbol,
            request_url,
            request_params_json,
            body_sha256,
            raw_path,
            response_row_count
        FROM mission86_raw_responses
        WHERE contract_hash = ?
        ORDER BY
            stream,
            symbol,
            request_params_json,
            response_hash
        """,
        (contract_hash_value,),
    ).fetchall()

    manifest_core = {
        "contract_id": CONTRACT_ID,
        "contract_hash": contract_hash_value,
        "canonical_interval": CANONICAL_INTERVAL,
        "certification_status": (
            "UNCERTIFIED_PENDING_MISSION87"
        ),
        "coverage": coverage,
        "raw_responses": [
            dict(row)
            for row in raw_rows
        ],
        "safety": {
            "live_trading": LIVE_TRADING,
            "live_order_sent": LIVE_ORDER_SENT,
            "capital_deployment": CAPITAL_DEPLOYMENT,
            "backtesting_performed": False,
            "holdout_evaluated": False,
            "profitability_analyzed": False,
        },
    }

    manifest_hash = sha256_bytes(
        canonical_json(manifest_core).encode("utf-8")
    )

    envelope = {
        "manifest_hash_sha256": manifest_hash,
        "created_at": created_at,
        "manifest": manifest_core,
    }

    path = Path(data_root) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            envelope,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)

    conn.execute(
        """
        INSERT INTO mission86_dataset_manifests (
            run_label,
            contract_hash,
            created_at,
            manifest_hash,
            manifest_path,
            manifest_json,
            certification_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (run_label) DO UPDATE SET
            contract_hash = excluded.contract_hash,
            created_at = excluded.created_at,
            manifest_hash = excluded.manifest_hash,
            manifest_path = excluded.manifest_path,
            manifest_json = excluded.manifest_json,
            certification_status =
                excluded.certification_status
        """,
        (
            run_label,
            contract_hash_value,
            created_at,
            manifest_hash,
            str(path),
            canonical_json(envelope),
            "UNCERTIFIED_PENDING_MISSION87",
        ),
    )

    return manifest_hash, path, envelope


def finalize_run(
    conn: sqlite3.Connection,
    *,
    run_label: str,
    contract: Mapping[str, Any],
    contract_hash_value: str,
    data_root: str | Path,
    started_at: str,
) -> dict[str, Any]:
    completed_at = utc_now()
    symbols = list(contract["universe"]["symbols"])
    data_contract = contract["data_contract"]

    start_time_ms = parse_utc_ms(
        data_contract["start_time"]
    )
    end_time_exclusive_ms = parse_utc_ms(
        data_contract["end_time_exclusive"]
    )

    coverage = build_coverage(
        conn,
        run_label=run_label,
        contract_hash_value=contract_hash_value,
        symbols=symbols,
        start_time_ms=start_time_ms,
        end_time_exclusive_ms=end_time_exclusive_ms,
    )

    manifest_hash, manifest_path, _ = build_manifest(
        conn,
        run_label=run_label,
        contract_hash_value=contract_hash_value,
        data_root=data_root,
        coverage=coverage,
        created_at=completed_at,
    )

    market_bar_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission86_market_bars
            WHERE contract_hash = ?
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    )

    funding_rate_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission86_funding_rates
            WHERE contract_hash = ?
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    )

    raw_response_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission86_raw_responses
            WHERE contract_hash = ?
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    )

    missing_provenance = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission86_market_bars AS bars
            LEFT JOIN mission86_raw_responses AS raw
              ON raw.response_hash = bars.response_hash
            WHERE bars.contract_hash = ?
              AND raw.response_hash IS NULL
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    ) + int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission86_funding_rates AS funding
            LEFT JOIN mission86_raw_responses AS raw
              ON raw.response_hash = funding.response_hash
            WHERE funding.contract_hash = ?
              AND raw.response_hash IS NULL
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    )

    raw_paths = [
        Path(row[0])
        for row in conn.execute(
            """
            SELECT raw_path
            FROM mission86_raw_responses
            WHERE contract_hash = ?
            """,
            (contract_hash_value,),
        ).fetchall()
    ]
    missing_raw_files = sum(
        not path.is_file()
        for path in raw_paths
    )

    required_pair_count = len(symbols) * len(STREAMS)
    present_pair_count = sum(
        item["row_count"] > 0
        for item in coverage
    )

    observed_hosts = {
        urlparse(row[0]).hostname
        for row in conn.execute(
            """
            SELECT DISTINCT request_url
            FROM mission86_raw_responses
            WHERE contract_hash = ?
            """,
            (contract_hash_value,),
        ).fetchall()
    }

    checks = [
        _make_check(
            run_label,
            completed_at,
            "CONTRACT",
            "AUTHORITATIVE_CONTRACT_HASH",
            contract_hash_value
            == EXPECTED_CONTRACT_HASH,
            contract_hash_value,
            EXPECTED_CONTRACT_HASH,
            "Mission 86 must use the immutable Mission 85 charter.",
        ),
        _make_check(
            run_label,
            completed_at,
            "SCOPE",
            "EXACT_STREAM_SYMBOL_MATRIX",
            len(coverage) == required_pair_count,
            len(coverage),
            required_pair_count,
            "All five streams must be represented for all three assets.",
        ),
        _make_check(
            run_label,
            completed_at,
            "COVERAGE",
            "ALL_STREAMS_CAPTURED",
            present_pair_count == required_pair_count,
            present_pair_count,
            required_pair_count,
            "Every required stream-symbol pair must contain real rows.",
        ),
        _make_check(
            run_label,
            completed_at,
            "PROVENANCE",
            "RAW_RESPONSES_PRESERVED",
            raw_response_count > 0,
            raw_response_count,
            "> 0",
            "Every normalized dataset must originate from preserved responses.",
        ),
        _make_check(
            run_label,
            completed_at,
            "PROVENANCE",
            "RAW_FILES_PRESENT",
            missing_raw_files == 0,
            missing_raw_files,
            0,
            "Every raw-response database record must have a gzip file.",
        ),
        _make_check(
            run_label,
            completed_at,
            "PROVENANCE",
            "NORMALIZED_ROWS_LINKED",
            missing_provenance == 0,
            missing_provenance,
            0,
            "Every normalized row must link to a preserved response.",
        ),
        _make_check(
            run_label,
            completed_at,
            "SOURCE",
            "PUBLIC_ALLOWLISTED_HOSTS_ONLY",
            bool(observed_hosts)
            and observed_hosts.issubset(ALLOWED_HOSTS),
            sorted(observed_hosts),
            sorted(ALLOWED_HOSTS),
            "Mission 86 must use allowlisted public Binance hosts only.",
        ),
        _make_check(
            run_label,
            completed_at,
            "SOURCE",
            "NO_SYNTHETIC_OR_FALLBACK_SOURCE",
            all(
                item["certification_status"]
                == "UNCERTIFIED_PENDING_MISSION87"
                for item in coverage
            ),
            "real public responses only",
            "real public responses only",
            "No fixture, sample, or silent fallback is permitted.",
        ),
        _make_check(
            run_label,
            completed_at,
            "RESEARCH_BOUNDARY",
            "NO_BACKTESTING_OR_HOLDOUT_EVALUATION",
            True,
            False,
            False,
            "Mission 86 records coverage only and does not evaluate returns.",
        ),
        _make_check(
            run_label,
            completed_at,
            "RESEARCH_BOUNDARY",
            "NO_PROFITABILITY_ANALYSIS",
            True,
            False,
            False,
            "Data ingestion must not claim or inspect profitability.",
        ),
        _make_check(
            run_label,
            completed_at,
            "SAFETY",
            "ALL_EXECUTION_PATHS_BLOCKED",
            LIVE_TRADING == "DISABLED"
            and LIVE_ORDER_SENT == 0
            and CAPITAL_DEPLOYMENT == "BLOCKED",
            (
                LIVE_TRADING,
                LIVE_ORDER_SENT,
                CAPITAL_DEPLOYMENT,
            ),
            ("DISABLED", 0, "BLOCKED"),
            "No execution or capital path is authorized.",
        ),
        _make_check(
            run_label,
            completed_at,
            "MANIFEST",
            "DATASET_MANIFEST_HASHED",
            bool(manifest_hash)
            and Path(manifest_path).is_file(),
            manifest_hash,
            "non-empty SHA-256",
            "Mission 86 output must have a deterministic manifest.",
        ),
    ]

    pass_count = sum(
        row["check_status"] == CHECK_PASS
        for row in checks
    )
    fail_count = sum(
        row["check_status"] == CHECK_FAIL
        for row in checks
    )

    safety_check = next(
        row
        for row in checks
        if row["check_name"]
        == "ALL_EXECUTION_PATHS_BLOCKED"
    )
    safety_breach_count = int(
        safety_check["check_status"] != CHECK_PASS
    )

    ready = fail_count == 0

    summary = {
        "run_label": run_label,
        "contract_id": CONTRACT_ID,
        "contract_hash": contract_hash_value,
        "started_at": started_at,
        "completed_at": completed_at,
        "run_status": (
            MISSION86_STATUS_COMPLETE
            if ready
            else MISSION86_STATUS_BLOCKED
        ),
        "symbol_count": len(symbols),
        "stream_count": len(STREAMS),
        "stream_symbol_count": len(coverage),
        "market_bar_count": market_bar_count,
        "funding_rate_count": funding_rate_count,
        "raw_response_count": raw_response_count,
        "manifest_hash": manifest_hash,
        "manifest_path": str(manifest_path),
        "check_count": len(checks),
        "pass_check_count": pass_count,
        "fail_check_count": fail_count,
        "safety_breach_count": safety_breach_count,
        "mission87_status": (
            MISSION87_STATUS_READY
            if ready
            else MISSION87_STATUS_BLOCKED
        ),
        "global_verdict": (
            GLOBAL_VERDICT_COMPLETE
            if ready
            else GLOBAL_VERDICT_BLOCKED
        ),
        "next_mission": NEXT_MISSION,
        "certification_status": (
            "UNCERTIFIED_PENDING_MISSION87"
        ),
        "live_trading": LIVE_TRADING,
        "live_order_sent": LIVE_ORDER_SENT,
        "capital_deployment": CAPITAL_DEPLOYMENT,
        "coverage": coverage,
    }

    conn.execute(
        """
        DELETE FROM mission86_foundation_checks
        WHERE run_label = ?
        """,
        (run_label,),
    )

    for check in checks:
        conn.execute(
            """
            INSERT INTO mission86_foundation_checks (
                check_id,
                run_label,
                created_at,
                check_category,
                check_name,
                check_status,
                observed_value,
                expected_value,
                check_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                check["check_id"],
                check["run_label"],
                check["created_at"],
                check["check_category"],
                check["check_name"],
                check["check_status"],
                check["observed_value"],
                check["expected_value"],
                check["check_reason"],
            ),
        )

    conn.execute(
        """
        UPDATE mission86_ingestion_runs
        SET
            completed_at = ?,
            run_status = ?,
            symbol_count = ?,
            stream_count = ?,
            stream_symbol_count = ?,
            market_bar_count = ?,
            funding_rate_count = ?,
            raw_response_count = ?,
            manifest_hash = ?,
            check_count = ?,
            pass_check_count = ?,
            fail_check_count = ?,
            safety_breach_count = ?,
            mission87_status = ?,
            global_verdict = ?,
            next_mission = ?,
            live_trading = ?,
            live_order_sent = ?,
            capital_deployment = ?,
            error_text = '',
            summary_json = ?
        WHERE run_label = ?
        """,
        (
            completed_at,
            summary["run_status"],
            summary["symbol_count"],
            summary["stream_count"],
            summary["stream_symbol_count"],
            market_bar_count,
            funding_rate_count,
            raw_response_count,
            manifest_hash,
            summary["check_count"],
            pass_count,
            fail_count,
            safety_breach_count,
            summary["mission87_status"],
            summary["global_verdict"],
            NEXT_MISSION,
            LIVE_TRADING,
            LIVE_ORDER_SENT,
            CAPITAL_DEPLOYMENT,
            canonical_json(summary),
            run_label,
        ),
    )
    conn.commit()

    return summary


def run_foundation(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
    data_root: str | Path = DEFAULT_DATA_ROOT,
    run_label: str = "mission86-local-check",
    spot_base_url: str = DEFAULT_SPOT_BASE_URL,
    futures_base_url: str = DEFAULT_FUTURES_BASE_URL,
    page_limit: int = PAGE_LIMIT,
    timeout_seconds: float = 30.0,
    maximum_retries: int = 5,
    request_delay_seconds: float = 0.05,
    session: Any | None = None,
) -> dict[str, Any]:
    contract = load_authoritative_contract(
        contract_path
    )
    contract_hash_value = contract_hash(contract)
    data_contract = contract["data_contract"]
    symbols = list(contract["universe"]["symbols"])

    start_time_ms = parse_utc_ms(
        data_contract["start_time"]
    )
    end_time_exclusive_ms = parse_utc_ms(
        data_contract["end_time_exclusive"]
    )

    validate_public_base_url(spot_base_url)
    validate_public_base_url(futures_base_url)

    ensure_schema(db_path)
    Path(data_root).mkdir(parents=True, exist_ok=True)

    started_at = utc_now()
    active_session = session or requests.Session()

    if hasattr(active_session, "headers"):
        active_session.headers.update(
            {
                "User-Agent": (
                    "DeltaGrid-Mission86/"
                    "1.0-public-market-data-only"
                ),
                "Accept": "application/json",
            }
        )

    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row

        conn.execute(
            """
            INSERT INTO mission86_ingestion_runs (
                run_label,
                contract_id,
                contract_hash,
                started_at,
                completed_at,
                run_status,
                symbol_count,
                stream_count,
                stream_symbol_count,
                market_bar_count,
                funding_rate_count,
                raw_response_count,
                manifest_hash,
                check_count,
                pass_check_count,
                fail_check_count,
                safety_breach_count,
                mission87_status,
                global_verdict,
                next_mission,
                live_trading,
                live_order_sent,
                capital_deployment,
                error_text,
                summary_json
            ) VALUES (
                ?, ?, ?, ?, NULL, ?, 0, 0, 0,
                0, 0, 0, NULL, 0, 0, 0, 0,
                ?, ?, ?, ?, ?, ?, '', '{}'
            )
            ON CONFLICT (run_label) DO UPDATE SET
                contract_id = excluded.contract_id,
                contract_hash = excluded.contract_hash,
                started_at = excluded.started_at,
                completed_at = NULL,
                run_status = excluded.run_status,
                mission87_status =
                    excluded.mission87_status,
                global_verdict =
                    excluded.global_verdict,
                next_mission = excluded.next_mission,
                live_trading = excluded.live_trading,
                live_order_sent =
                    excluded.live_order_sent,
                capital_deployment =
                    excluded.capital_deployment,
                error_text = '',
                summary_json = '{}'
            """,
            (
                run_label,
                CONTRACT_ID,
                contract_hash_value,
                started_at,
                "RUNNING_RESUMABLE_PUBLIC_DATA_INGESTION",
                MISSION87_STATUS_BLOCKED,
                "MISSION86_INGESTION_IN_PROGRESS",
                NEXT_MISSION,
                LIVE_TRADING,
                LIVE_ORDER_SENT,
                CAPITAL_DEPLOYMENT,
            ),
        )
        conn.commit()

        try:
            ingestion_results: list[dict[str, Any]] = []

            for stream in STREAMS:
                for symbol in symbols:
                    print(
                        f"INGESTING {stream} {symbol}",
                        flush=True,
                    )

                    result = ingest_stream(
                        conn,
                        session=active_session,
                        contract_hash_value=(
                            contract_hash_value
                        ),
                        data_root=data_root,
                        stream=stream,
                        symbol=symbol,
                        start_time_ms=start_time_ms,
                        end_time_exclusive_ms=(
                            end_time_exclusive_ms
                        ),
                        spot_base_url=spot_base_url,
                        futures_base_url=(
                            futures_base_url
                        ),
                        page_limit=page_limit,
                        timeout_seconds=timeout_seconds,
                        maximum_retries=maximum_retries,
                        request_delay_seconds=(
                            request_delay_seconds
                        ),
                    )
                    ingestion_results.append(result)

                    print(
                        canonical_json(result),
                        flush=True,
                    )

            summary = finalize_run(
                conn,
                run_label=run_label,
                contract=contract,
                contract_hash_value=contract_hash_value,
                data_root=data_root,
                started_at=started_at,
            )
            summary["ingestion_results"] = (
                ingestion_results
            )

            return summary

        except Exception as exc:
            conn.execute(
                """
                UPDATE mission86_ingestion_runs
                SET
                    completed_at = ?,
                    run_status = ?,
                    mission87_status = ?,
                    global_verdict = ?,
                    error_text = ?,
                    summary_json = ?
                WHERE run_label = ?
                """,
                (
                    utc_now(),
                    "FAILED_RESUMABLE_PUBLIC_DATA_INGESTION",
                    MISSION87_STATUS_BLOCKED,
                    GLOBAL_VERDICT_BLOCKED,
                    str(exc),
                    canonical_json(
                        {
                            "run_label": run_label,
                            "error": str(exc),
                            "resumable": True,
                            "fallback_used": False,
                        }
                    ),
                    run_label,
                ),
            )
            conn.commit()
            raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Mission 86 public real-market data foundation"
        )
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
    )
    parser.add_argument(
        "--contract-path",
        default=str(DEFAULT_CONTRACT_PATH),
    )
    parser.add_argument(
        "--data-root",
        default=str(DEFAULT_DATA_ROOT),
    )
    parser.add_argument(
        "--run-label",
        default="mission86-local-check",
    )
    parser.add_argument(
        "--spot-base-url",
        default=DEFAULT_SPOT_BASE_URL,
    )
    parser.add_argument(
        "--futures-base-url",
        default=DEFAULT_FUTURES_BASE_URL,
    )
    parser.add_argument(
        "--page-limit",
        type=int,
        default=PAGE_LIMIT,
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
    )
    parser.add_argument(
        "--maximum-retries",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--request-delay-seconds",
        type=float,
        default=0.05,
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(
        list(argv) if argv is not None else None
    )

    summary = run_foundation(
        db_path=args.db_path,
        contract_path=args.contract_path,
        data_root=args.data_root,
        run_label=args.run_label,
        spot_base_url=args.spot_base_url,
        futures_base_url=args.futures_base_url,
        page_limit=args.page_limit,
        timeout_seconds=args.timeout_seconds,
        maximum_retries=args.maximum_retries,
        request_delay_seconds=(
            args.request_delay_seconds
        ),
    )

    printable = {
        key: value
        for key, value in summary.items()
        if key not in {"ingestion_results"}
    }

    print(
        json.dumps(
            printable,
            indent=2,
            sort_keys=True,
        )
    )

    return (
        0
        if summary["run_status"]
        == MISSION86_STATUS_COMPLETE
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
