"""
Mission 50: Historical Public Funding and Basis Dataset Builder.

This module builds a historical public-data dataset from Binance USDS-M
Futures public funding history plus latest public basis observations.

It is a public-data research dataset layer, not an execution layer.

It never:
- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- requires paid APIs
- requires real capital
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BINANCE_USDS_M_BASE_URL = "https://fapi.binance.com"
SOURCE_NAME = "BINANCE_USDS_M_FUTURES_PUBLIC_REST"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

FUNDING_TABLE = "historical_public_funding_rates"
BASIS_TABLE = "historical_public_basis_observations"
DATASET_REPORTS_TABLE = "historical_public_funding_basis_dataset_reports"
MISSION49_SNAPSHOTS_TABLE = "real_market_public_data_snapshots"

DATA_MODE_ONLINE = "ONLINE_PUBLIC_API"
DATA_MODE_OFFLINE_SAMPLE = "OFFLINE_SAMPLE"
DATA_MODE_OFFLINE_SAMPLE_FALLBACK = "OFFLINE_SAMPLE_FALLBACK"
DATA_MODE_FAILED = "FAILED"

DATASET_READY_VERDICT = "HISTORICAL_PUBLIC_DATASET_READY_SHADOW_ONLY"
DATASET_PARTIAL_VERDICT = "HISTORICAL_PUBLIC_DATASET_PARTIAL_SHADOW_ONLY"
DATASET_FAILED_VERDICT = "HISTORICAL_PUBLIC_DATASET_FAILED"
DATASET_SAFETY_BREACH_VERDICT = "HISTORICAL_PUBLIC_DATASET_SAFETY_BREACH_BLOCKED"

RECOMMEND_BUILD_SCANNER = "BUILD_FUNDING_BASIS_ALPHA_SCANNER_SHADOW_ONLY"
RECOMMEND_RETRY_DATASET = "RETRY_PUBLIC_DATASET_BUILD_OR_USE_SAMPLE_FALLBACK"
RECOMMEND_REVIEW_SAFETY = "STOP_AND_REVIEW_HISTORICAL_DATASET_SAFETY_STATE"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_dataset_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission50-historical-dataset-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission50-report-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def parse_symbols(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return list(DEFAULT_SYMBOLS)

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    symbols: list[str] = []

    for item in raw_items:
        symbol = str(item).strip().upper()

        if not symbol:
            continue

        if not symbol.endswith("USDT"):
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 50: {symbol}")

        if not symbol.replace("_", "").isalnum():
            raise ValueError(f"Invalid symbol: {symbol}")

        if symbol not in symbols:
            symbols.append(symbol)

    if not symbols:
        raise ValueError("At least one symbol is required")

    return symbols


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historical_public_funding_rates (
                dataset_label TEXT NOT NULL,
                symbol TEXT NOT NULL,
                funding_time INTEGER NOT NULL,
                funding_time_iso TEXT NOT NULL,
                funding_rate TEXT NOT NULL,
                funding_rate_bps TEXT NOT NULL,
                annualized_funding_rate TEXT NOT NULL,
                mark_price TEXT NOT NULL,
                source TEXT NOT NULL,
                data_mode TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                raw_payload_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                PRIMARY KEY (dataset_label, symbol, funding_time)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historical_public_basis_observations (
                basis_id TEXT PRIMARY KEY,
                dataset_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                source_snapshot_id TEXT,
                source_ingestion_label TEXT,
                source TEXT NOT NULL,
                data_mode TEXT NOT NULL,
                mark_price TEXT NOT NULL,
                index_price TEXT NOT NULL,
                basis_bps TEXT NOT NULL,
                spread_bps TEXT NOT NULL,
                quote_volume TEXT NOT NULL,
                last_funding_rate TEXT NOT NULL,
                annualized_funding_rate TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                raw_payload_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historical_public_funding_basis_dataset_reports (
                report_label TEXT PRIMARY KEY,
                dataset_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                symbol_count INTEGER NOT NULL,
                funding_record_count INTEGER NOT NULL,
                basis_observation_count INTEGER NOT NULL,
                successful_symbol_count INTEGER NOT NULL,
                failed_symbol_count INTEGER NOT NULL,
                online_public_api_count INTEGER NOT NULL,
                offline_sample_count INTEGER NOT NULL,
                fallback_count INTEGER NOT NULL,
                positive_funding_record_count INTEGER NOT NULL,
                negative_funding_record_count INTEGER NOT NULL,
                zero_funding_record_count INTEGER NOT NULL,
                average_funding_rate_bps TEXT NOT NULL,
                average_annualized_funding_rate TEXT NOT NULL,
                average_basis_bps TEXT NOT NULL,
                average_spread_bps TEXT NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def public_get_json(
    path: str,
    params: dict[str, Any] | None = None,
    timeout_seconds: float = 10.0,
    base_url: str = BINANCE_USDS_M_BASE_URL,
) -> Any:
    query = urllib.parse.urlencode(params or {})
    url = base_url.rstrip("/") + path

    if query:
        url += "?" + query

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "DeltaGrid-Research-HistoricalPublicData/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8")

    return json.loads(raw)


def fetch_online_funding_history(
    symbol: str,
    timeout_seconds: float = 10.0,
    funding_limit: int = 100,
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "symbol": symbol,
        "limit": funding_limit,
    }

    if start_time is not None:
        params["startTime"] = start_time

    if end_time is not None:
        params["endTime"] = end_time

    payload = public_get_json(
        "/fapi/v1/fundingRate",
        params,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(payload, list):
        raise ValueError(f"Unexpected funding history payload for {symbol}")

    return payload


def sample_price_for_symbol(symbol: str) -> float:
    samples = {
        "BTCUSDT": 62000.0,
        "ETHUSDT": 3400.0,
        "SOLUSDT": 145.0,
    }

    return samples.get(symbol, 100.0)


def sample_funding_for_symbol(symbol: str) -> float:
    samples = {
        "BTCUSDT": 0.00010,
        "ETHUSDT": 0.00008,
        "SOLUSDT": 0.00012,
    }

    return samples.get(symbol, 0.00005)


def sample_funding_history(symbol: str, limit: int, data_mode: str) -> list[dict[str, Any]]:
    base = sample_price_for_symbol(symbol)
    base_rate = sample_funding_for_symbol(symbol)
    now_ms = int(time.time() * 1000)
    rows = []

    count = max(1, min(limit, 100))

    for index in range(count):
        offset = count - index
        funding_time = now_ms - offset * 8 * 60 * 60 * 1000
        drift = ((index % 5) - 2) * 0.000005
        rate = base_rate + drift

        rows.append(
            {
                "symbol": symbol,
                "fundingTime": funding_time,
                "fundingRate": f"{rate:.8f}",
                "markPrice": f"{base * (1.0 + index * 0.0002):.8f}",
                "data_mode": data_mode,
            }
        )

    return rows


def funding_time_iso(funding_time_ms: int) -> str:
    return datetime.fromtimestamp(funding_time_ms / 1000.0, tz=timezone.utc).replace(microsecond=0).isoformat()


def normalize_funding_record(
    dataset_label: str,
    symbol: str,
    row: dict[str, Any],
    data_mode: str,
) -> dict[str, Any]:
    funding_time = safe_int(row.get("fundingTime"))
    funding_rate = safe_float(row.get("fundingRate"))
    mark_price = safe_float(row.get("markPrice"))

    return {
        "dataset_label": dataset_label,
        "symbol": symbol,
        "funding_time": funding_time,
        "funding_time_iso": funding_time_iso(funding_time),
        "funding_rate": round(funding_rate, 10),
        "funding_rate_bps": round(funding_rate * 10000.0, 8),
        "annualized_funding_rate": round(funding_rate * 365.0 * 3.0, 10),
        "mark_price": round(mark_price, 8),
        "source": SOURCE_NAME,
        "data_mode": data_mode,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "raw_payload": row,
        "metadata": {
            "funding_periods_per_year": 365.0 * 3.0,
            "ingestion_role": "PUBLIC_HISTORICAL_FUNDING_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
        },
    }


def fetch_and_normalize_funding_history(
    symbol: str,
    dataset_label: str,
    timeout_seconds: float,
    funding_limit: int,
    offline_sample: bool,
    allow_sample_fallback: bool,
    start_time: int | None,
    end_time: int | None,
) -> tuple[list[dict[str, Any]], str, str | None]:
    if offline_sample:
        rows = sample_funding_history(symbol, funding_limit, DATA_MODE_OFFLINE_SAMPLE)
        return (
            [
                normalize_funding_record(dataset_label, symbol, row, DATA_MODE_OFFLINE_SAMPLE)
                for row in rows
            ],
            DATA_MODE_OFFLINE_SAMPLE,
            None,
        )

    try:
        rows = fetch_online_funding_history(
            symbol=symbol,
            timeout_seconds=timeout_seconds,
            funding_limit=funding_limit,
            start_time=start_time,
            end_time=end_time,
        )
        return (
            [
                normalize_funding_record(dataset_label, symbol, row, DATA_MODE_ONLINE)
                for row in rows
            ],
            DATA_MODE_ONLINE,
            None,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
        message = f"{type(exc).__name__}: {exc}"

        if allow_sample_fallback:
            rows = sample_funding_history(symbol, funding_limit, DATA_MODE_OFFLINE_SAMPLE_FALLBACK)
            return (
                [
                    normalize_funding_record(dataset_label, symbol, row, DATA_MODE_OFFLINE_SAMPLE_FALLBACK)
                    for row in rows
                ],
                DATA_MODE_OFFLINE_SAMPLE_FALLBACK,
                message,
            )

        return ([], DATA_MODE_FAILED, message)


def load_latest_basis_snapshot(
    conn: sqlite3.Connection,
    symbol: str,
    preferred_ingestion_label: str | None,
) -> sqlite3.Row | None:
    if not table_exists(conn, MISSION49_SNAPSHOTS_TABLE):
        return None

    if preferred_ingestion_label:
        row = conn.execute(
            """
            SELECT *
            FROM real_market_public_data_snapshots
            WHERE symbol = ?
            AND ingestion_label = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (symbol, preferred_ingestion_label),
        ).fetchone()

        if row is not None:
            return row

    return conn.execute(
        """
        SELECT *
        FROM real_market_public_data_snapshots
        WHERE symbol = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (symbol,),
    ).fetchone()


def sample_basis_observation(
    dataset_label: str,
    symbol: str,
    created_at: str,
    data_mode: str,
) -> dict[str, Any]:
    base = sample_price_for_symbol(symbol)
    funding = sample_funding_for_symbol(symbol)

    return {
        "basis_id": f"{dataset_label}-{symbol}-basis",
        "dataset_label": dataset_label,
        "created_at": created_at,
        "symbol": symbol,
        "source_snapshot_id": None,
        "source_ingestion_label": None,
        "source": SOURCE_NAME,
        "data_mode": data_mode,
        "mark_price": round(base * 1.0002, 8),
        "index_price": round(base, 8),
        "basis_bps": 2.0,
        "spread_bps": 1.0,
        "quote_volume": round(base * 100000.0, 8),
        "last_funding_rate": round(funding, 10),
        "annualized_funding_rate": round(funding * 365.0 * 3.0, 10),
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "raw_payload": {"symbol": symbol, "data_mode": data_mode, "sample": True},
        "metadata": {
            "basis_role": "SAMPLE_CURRENT_BASIS_OBSERVATION",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
        },
    }


def normalize_basis_from_snapshot(
    dataset_label: str,
    created_at: str,
    row: sqlite3.Row,
) -> dict[str, Any]:
    symbol = str(row["symbol"])

    return {
        "basis_id": f"{dataset_label}-{symbol}-basis",
        "dataset_label": dataset_label,
        "created_at": created_at,
        "symbol": symbol,
        "source_snapshot_id": row["snapshot_id"],
        "source_ingestion_label": row["ingestion_label"],
        "source": row["source"],
        "data_mode": row["data_mode"],
        "mark_price": safe_float(row["mark_price"]),
        "index_price": safe_float(row["index_price"]),
        "basis_bps": safe_float(row["basis_bps"]),
        "spread_bps": safe_float(row["spread_bps"]),
        "quote_volume": safe_float(row["quote_volume"]),
        "last_funding_rate": safe_float(row["last_funding_rate"]),
        "annualized_funding_rate": safe_float(row["annualized_funding_rate"]),
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "raw_payload": {
            "source_snapshot_id": row["snapshot_id"],
            "source_ingestion_label": row["ingestion_label"],
            "symbol": symbol,
            "mark_price": row["mark_price"],
            "index_price": row["index_price"],
            "basis_bps": row["basis_bps"],
            "spread_bps": row["spread_bps"],
            "quote_volume": row["quote_volume"],
            "last_funding_rate": row["last_funding_rate"],
        },
        "metadata": {
            "basis_role": "LATEST_PUBLIC_BASIS_FROM_MISSION49_SNAPSHOT",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
        },
    }


def build_basis_observations(
    db_path: str | Path,
    dataset_label: str,
    symbols: list[str],
    created_at: str,
    preferred_ingestion_label: str | None,
    offline_sample: bool,
    allow_sample_fallback: bool,
) -> list[dict[str, Any]]:
    if offline_sample:
        return [
            sample_basis_observation(dataset_label, symbol, created_at, DATA_MODE_OFFLINE_SAMPLE)
            for symbol in symbols
        ]

    basis_rows = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        for symbol in symbols:
            row = load_latest_basis_snapshot(conn, symbol, preferred_ingestion_label)

            if row is not None:
                basis_rows.append(
                    normalize_basis_from_snapshot(
                        dataset_label=dataset_label,
                        created_at=created_at,
                        row=row,
                    )
                )
            elif allow_sample_fallback:
                basis_rows.append(
                    sample_basis_observation(
                        dataset_label=dataset_label,
                        symbol=symbol,
                        created_at=created_at,
                        data_mode=DATA_MODE_OFFLINE_SAMPLE_FALLBACK,
                    )
                )

    return basis_rows


def persist_dataset(
    db_path: str | Path,
    funding_records: list[dict[str, Any]],
    basis_observations: list[dict[str, Any]],
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for row in funding_records:
            conn.execute(
                """
                INSERT OR REPLACE INTO historical_public_funding_rates (
                    dataset_label,
                    symbol,
                    funding_time,
                    funding_time_iso,
                    funding_rate,
                    funding_rate_bps,
                    annualized_funding_rate,
                    mark_price,
                    source,
                    data_mode,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    raw_payload_json,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["dataset_label"],
                    row["symbol"],
                    row["funding_time"],
                    row["funding_time_iso"],
                    str(row["funding_rate"]),
                    str(row["funding_rate_bps"]),
                    str(row["annualized_funding_rate"]),
                    str(row["mark_price"]),
                    row["source"],
                    row["data_mode"],
                    row["live_trading"],
                    row["live_order_sent"],
                    row["capital_deployment"],
                    json.dumps(row["raw_payload"], sort_keys=True),
                    json.dumps(row["metadata"], sort_keys=True),
                ),
            )

        for item in basis_observations:
            conn.execute(
                """
                INSERT OR REPLACE INTO historical_public_basis_observations (
                    basis_id,
                    dataset_label,
                    created_at,
                    symbol,
                    source_snapshot_id,
                    source_ingestion_label,
                    source,
                    data_mode,
                    mark_price,
                    index_price,
                    basis_bps,
                    spread_bps,
                    quote_volume,
                    last_funding_rate,
                    annualized_funding_rate,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    raw_payload_json,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["basis_id"],
                    item["dataset_label"],
                    item["created_at"],
                    item["symbol"],
                    item["source_snapshot_id"],
                    item["source_ingestion_label"],
                    item["source"],
                    item["data_mode"],
                    str(item["mark_price"]),
                    str(item["index_price"]),
                    str(item["basis_bps"]),
                    str(item["spread_bps"]),
                    str(item["quote_volume"]),
                    str(item["last_funding_rate"]),
                    str(item["annualized_funding_rate"]),
                    item["live_trading"],
                    item["live_order_sent"],
                    item["capital_deployment"],
                    json.dumps(item["raw_payload"], sort_keys=True),
                    json.dumps(item["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_dataset(
    db_path: str | Path,
    dataset_label: str,
    report_label: str,
    created_at: str,
    symbols: list[str],
    funding_records: list[dict[str, Any]],
    basis_observations: list[dict[str, Any]],
    symbol_errors: dict[str, str | None],
) -> dict[str, Any]:
    funding_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in funding_records:
        funding_by_symbol[row["symbol"]].append(row)

    successful_symbols = [
        symbol for symbol in symbols
        if len(funding_by_symbol.get(symbol, [])) > 0
    ]
    failed_symbols = [
        symbol for symbol in symbols
        if len(funding_by_symbol.get(symbol, [])) == 0
    ]

    data_mode_counts = Counter(row["data_mode"] for row in funding_records)
    basis_data_mode_counts = Counter(row["data_mode"] for row in basis_observations)

    positive = sum(1 for row in funding_records if safe_float(row["funding_rate"]) > 0)
    negative = sum(1 for row in funding_records if safe_float(row["funding_rate"]) < 0)
    zero = sum(1 for row in funding_records if safe_float(row["funding_rate"]) == 0)

    safety_breach_count = 0

    for row in funding_records:
        if (
            row["live_trading"] != LIVE_TRADING_STATUS
            or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
            or row["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
        ):
            safety_breach_count += 1

    for row in basis_observations:
        if (
            row["live_trading"] != LIVE_TRADING_STATUS
            or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
            or row["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
        ):
            safety_breach_count += 1

    avg_funding_bps = 0.0
    avg_annualized = 0.0

    if funding_records:
        avg_funding_bps = round(
            sum(safe_float(row["funding_rate_bps"]) for row in funding_records) / len(funding_records),
            8,
        )
        avg_annualized = round(
            sum(safe_float(row["annualized_funding_rate"]) for row in funding_records) / len(funding_records),
            10,
        )

    avg_basis = 0.0
    avg_spread = 0.0

    if basis_observations:
        avg_basis = round(
            sum(safe_float(row["basis_bps"]) for row in basis_observations) / len(basis_observations),
            8,
        )
        avg_spread = round(
            sum(safe_float(row["spread_bps"]) for row in basis_observations) / len(basis_observations),
            8,
        )

    symbol_summary: dict[str, Any] = {}

    for symbol in symbols:
        rows = funding_by_symbol.get(symbol, [])
        basis = next((item for item in basis_observations if item["symbol"] == symbol), None)

        symbol_summary[symbol] = {
            "funding_record_count": len(rows),
            "average_funding_rate_bps": round(
                sum(safe_float(row["funding_rate_bps"]) for row in rows) / len(rows),
                8,
            ) if rows else 0.0,
            "latest_basis_bps": safe_float(basis["basis_bps"]) if basis else 0.0,
            "latest_spread_bps": safe_float(basis["spread_bps"]) if basis else 0.0,
            "data_modes": sorted(set(row["data_mode"] for row in rows)),
            "error": symbol_errors.get(symbol),
        }

    if safety_breach_count > 0:
        global_verdict = DATASET_SAFETY_BREACH_VERDICT
        recommended_action = RECOMMEND_REVIEW_SAFETY
    elif not funding_records:
        global_verdict = DATASET_FAILED_VERDICT
        recommended_action = RECOMMEND_RETRY_DATASET
    elif failed_symbols or len(basis_observations) < len(symbols):
        global_verdict = DATASET_PARTIAL_VERDICT
        recommended_action = RECOMMEND_RETRY_DATASET
    else:
        global_verdict = DATASET_READY_VERDICT
        recommended_action = RECOMMEND_BUILD_SCANNER

    return {
        "report_label": report_label,
        "dataset_label": dataset_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source": SOURCE_NAME,
        "symbol_count": len(symbols),
        "symbols": symbols,
        "funding_record_count": len(funding_records),
        "basis_observation_count": len(basis_observations),
        "successful_symbol_count": len(successful_symbols),
        "failed_symbol_count": len(failed_symbols),
        "successful_symbols": successful_symbols,
        "failed_symbols": failed_symbols,
        "online_public_api_count": data_mode_counts.get(DATA_MODE_ONLINE, 0),
        "offline_sample_count": data_mode_counts.get(DATA_MODE_OFFLINE_SAMPLE, 0),
        "fallback_count": data_mode_counts.get(DATA_MODE_OFFLINE_SAMPLE_FALLBACK, 0),
        "basis_data_mode_counts": dict(basis_data_mode_counts),
        "positive_funding_record_count": positive,
        "negative_funding_record_count": negative,
        "zero_funding_record_count": zero,
        "average_funding_rate_bps": avg_funding_bps,
        "average_annualized_funding_rate": avg_annualized,
        "average_basis_bps": avg_basis,
        "average_spread_bps": avg_spread,
        "safety_breach_count": safety_breach_count,
        "symbol_summary": symbol_summary,
        "symbol_errors": symbol_errors,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    symbol_lines = []

    for symbol, data in summary["symbol_summary"].items():
        symbol_lines.append(
            "- "
            + symbol
            + ": "
            + f"funding_records={data['funding_record_count']}, "
            + f"avg_funding_bps={data['average_funding_rate_bps']}, "
            + f"latest_basis_bps={data['latest_basis_bps']}, "
            + f"latest_spread_bps={data['latest_spread_bps']}, "
            + f"modes={data['data_modes']}"
        )

    symbol_markdown = "\n".join(symbol_lines) or "- None"

    return f"""# DeltaGrid Mission 50 Historical Public Funding and Basis Dataset Report

Report label: {summary['report_label']}
Dataset label: {summary['dataset_label']}
Created at: {summary['created_at']}
Source: {summary['source']}

## Dataset Summary

Symbol count: {summary['symbol_count']}
Funding record count: {summary['funding_record_count']}
Basis observation count: {summary['basis_observation_count']}

Successful symbol count: {summary['successful_symbol_count']}
Failed symbol count: {summary['failed_symbol_count']}

Online public API count: {summary['online_public_api_count']}
Offline sample count: {summary['offline_sample_count']}
Fallback count: {summary['fallback_count']}

Positive funding record count: {summary['positive_funding_record_count']}
Negative funding record count: {summary['negative_funding_record_count']}
Zero funding record count: {summary['zero_funding_record_count']}

Average funding rate bps: {summary['average_funding_rate_bps']}
Average annualized funding rate: {summary['average_annualized_funding_rate']}
Average basis bps: {summary['average_basis_bps']}
Average spread bps: {summary['average_spread_bps']}

Safety breach count: {summary['safety_breach_count']}

## Symbol Summary

{symbol_markdown}

## Verdict

Global verdict: {summary['global_verdict']}
Recommended action: {summary['recommended_action']}

## Safety Statement

Live trading remains disabled.
Capital deployment remains blocked.
No private keys were read.
No signatures were produced.
No exchange orders were sent.
No real capital was used.
No paid APIs were used.
"""


def persist_report(
    db_path: str | Path,
    summary: dict[str, Any],
    markdown_report: str,
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO historical_public_funding_basis_dataset_reports (
                report_label,
                dataset_label,
                created_at,
                source,
                symbol_count,
                funding_record_count,
                basis_observation_count,
                successful_symbol_count,
                failed_symbol_count,
                online_public_api_count,
                offline_sample_count,
                fallback_count,
                positive_funding_record_count,
                negative_funding_record_count,
                zero_funding_record_count,
                average_funding_rate_bps,
                average_annualized_funding_rate,
                average_basis_bps,
                average_spread_bps,
                safety_breach_count,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["dataset_label"],
                summary["created_at"],
                summary["source"],
                summary["symbol_count"],
                summary["funding_record_count"],
                summary["basis_observation_count"],
                summary["successful_symbol_count"],
                summary["failed_symbol_count"],
                summary["online_public_api_count"],
                summary["offline_sample_count"],
                summary["fallback_count"],
                summary["positive_funding_record_count"],
                summary["negative_funding_record_count"],
                summary["zero_funding_record_count"],
                str(summary["average_funding_rate_bps"]),
                str(summary["average_annualized_funding_rate"]),
                str(summary["average_basis_bps"]),
                str(summary["average_spread_bps"]),
                summary["safety_breach_count"],
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_historical_public_funding_basis_dataset_builder(
    db_path: str | Path = "offchain/deltagrid.db",
    dataset_label: str | None = None,
    report_label: str | None = None,
    symbols: str | list[str] | tuple[str, ...] | None = None,
    timeout_seconds: float = 10.0,
    funding_limit: int = 100,
    start_time: int | None = None,
    end_time: int | None = None,
    source_ingestion_label: str | None = None,
    offline_sample: bool = False,
    allow_sample_fallback: bool = False,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0")

    if funding_limit <= 0 or funding_limit > 1000:
        raise ValueError("funding_limit must be between 1 and 1000")

    resolved_symbols = parse_symbols(symbols)
    label = dataset_label or new_dataset_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    ensure_schema(db_path)

    funding_records: list[dict[str, Any]] = []
    symbol_errors: dict[str, str | None] = {}

    for symbol in resolved_symbols:
        records, data_mode, error_message = fetch_and_normalize_funding_history(
            symbol=symbol,
            dataset_label=label,
            timeout_seconds=timeout_seconds,
            funding_limit=funding_limit,
            offline_sample=offline_sample,
            allow_sample_fallback=allow_sample_fallback,
            start_time=start_time,
            end_time=end_time,
        )

        symbol_errors[symbol] = error_message
        funding_records.extend(records)

    basis_observations = build_basis_observations(
        db_path=db_path,
        dataset_label=label,
        symbols=resolved_symbols,
        created_at=created_at,
        preferred_ingestion_label=source_ingestion_label,
        offline_sample=offline_sample,
        allow_sample_fallback=allow_sample_fallback,
    )

    persist_dataset(db_path, funding_records, basis_observations)

    summary = summarize_dataset(
        db_path=db_path,
        dataset_label=label,
        report_label=report,
        created_at=created_at,
        symbols=resolved_symbols,
        funding_records=funding_records,
        basis_observations=basis_observations,
        symbol_errors=symbol_errors,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db_path, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build DeltaGrid historical public funding and basis dataset."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--dataset-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--funding-limit", type=int, default=100)
    parser.add_argument("--start-time", type=int, default=None)
    parser.add_argument("--end-time", type=int, default=None)
    parser.add_argument("--source-ingestion-label", default=None)
    parser.add_argument("--offline-sample", action="store_true")
    parser.add_argument("--allow-sample-fallback", action="store_true")
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_historical_public_funding_basis_dataset_builder(
        db_path=args.db,
        dataset_label=args.dataset_label,
        report_label=args.report_label,
        symbols=args.symbols,
        timeout_seconds=args.timeout_seconds,
        funding_limit=args.funding_limit,
        start_time=args.start_time,
        end_time=args.end_time,
        source_ingestion_label=args.source_ingestion_label,
        offline_sample=args.offline_sample,
        allow_sample_fallback=args.allow_sample_fallback,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
