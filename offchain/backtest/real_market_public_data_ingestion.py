"""
Mission 49: Real Market Public Data Ingestion.

This module ingests Binance USDS-M Futures public market data for funding,
basis, ticker, and book-top analytics.

It is a public-data research ingestion layer, not an execution layer.

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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BINANCE_USDS_M_BASE_URL = "https://fapi.binance.com"
SOURCE_NAME = "BINANCE_USDS_M_FUTURES_PUBLIC_REST"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

SNAPSHOTS_TABLE = "real_market_public_data_snapshots"
REPORTS_TABLE = "real_market_public_data_reports"

DATA_MODE_ONLINE = "ONLINE_PUBLIC_API"
DATA_MODE_OFFLINE_SAMPLE = "OFFLINE_SAMPLE"
DATA_MODE_OFFLINE_SAMPLE_FALLBACK = "OFFLINE_SAMPLE_FALLBACK"
DATA_MODE_FAILED = "FAILED"

INGESTION_SUCCESS_VERDICT = "REAL_MARKET_PUBLIC_DATA_INGESTED_SHADOW_ONLY"
INGESTION_PARTIAL_VERDICT = "REAL_MARKET_PUBLIC_DATA_PARTIAL_INGESTION_SHADOW_ONLY"
INGESTION_FAILED_VERDICT = "REAL_MARKET_PUBLIC_DATA_INGESTION_FAILED"
INGESTION_SAFETY_BREACH_VERDICT = "REAL_MARKET_PUBLIC_DATA_SAFETY_BREACH_BLOCKED"

RECOMMEND_USE_FOR_ALPHA = "USE_PUBLIC_DATA_FOR_ALPHA_SCANNER_SHADOW_ONLY"
RECOMMEND_RETRY_PUBLIC_DATA = "RETRY_PUBLIC_DATA_INGESTION_OR_USE_OFFLINE_SAMPLE"
RECOMMEND_REVIEW_SAFETY = "STOP_AND_REVIEW_PUBLIC_DATA_INGESTION_SAFETY_STATE"

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_ingestion_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission49-public-data-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission49-report-{stamp}-{uuid.uuid4().hex[:8]}"


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

    if isinstance(value, str):
        raw_items = value.split(",")
    else:
        raw_items = list(value)

    symbols = []

    for item in raw_items:
        symbol = str(item).strip().upper()

        if not symbol:
            continue

        if not symbol.endswith("USDT"):
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 49: {symbol}")

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
            CREATE TABLE IF NOT EXISTS real_market_public_data_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                ingestion_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                source TEXT NOT NULL,
                data_mode TEXT NOT NULL,
                mark_price TEXT NOT NULL,
                index_price TEXT NOT NULL,
                basis_bps TEXT NOT NULL,
                last_funding_rate TEXT NOT NULL,
                last_funding_rate_bps TEXT NOT NULL,
                annualized_funding_rate TEXT NOT NULL,
                avg_funding_rate_history TEXT NOT NULL,
                funding_history_count INTEGER NOT NULL,
                bid_price TEXT NOT NULL,
                ask_price TEXT NOT NULL,
                spread_bps TEXT NOT NULL,
                quote_volume TEXT NOT NULL,
                price_change_percent TEXT NOT NULL,
                next_funding_time INTEGER,
                event_time INTEGER,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                error_message TEXT,
                raw_payload_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS real_market_public_data_reports (
                report_label TEXT PRIMARY KEY,
                ingestion_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                symbol_count INTEGER NOT NULL,
                successful_symbol_count INTEGER NOT NULL,
                failed_symbol_count INTEGER NOT NULL,
                online_public_api_count INTEGER NOT NULL,
                offline_sample_count INTEGER NOT NULL,
                fallback_count INTEGER NOT NULL,
                positive_funding_count INTEGER NOT NULL,
                negative_funding_count INTEGER NOT NULL,
                zero_funding_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                average_basis_bps TEXT NOT NULL,
                average_spread_bps TEXT NOT NULL,
                average_annualized_funding_rate TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


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
            "User-Agent": "DeltaGrid-Research-PublicData/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8")

    return json.loads(raw)


def fetch_online_symbol_payload(
    symbol: str,
    timeout_seconds: float = 10.0,
    funding_limit: int = 20,
) -> dict[str, Any]:
    premium_index = public_get_json(
        "/fapi/v1/premiumIndex",
        {"symbol": symbol},
        timeout_seconds=timeout_seconds,
    )
    ticker_24hr = public_get_json(
        "/fapi/v1/ticker/24hr",
        {"symbol": symbol},
        timeout_seconds=timeout_seconds,
    )
    book_ticker = public_get_json(
        "/fapi/v1/ticker/bookTicker",
        {"symbol": symbol},
        timeout_seconds=timeout_seconds,
    )
    funding_history = public_get_json(
        "/fapi/v1/fundingRate",
        {"symbol": symbol, "limit": funding_limit},
        timeout_seconds=timeout_seconds,
    )

    return {
        "symbol": symbol,
        "data_mode": DATA_MODE_ONLINE,
        "premium_index": premium_index,
        "ticker_24hr": ticker_24hr,
        "book_ticker": book_ticker,
        "funding_history": funding_history,
        "error_message": None,
    }


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


def sample_symbol_payload(
    symbol: str,
    data_mode: str = DATA_MODE_OFFLINE_SAMPLE,
    error_message: str | None = None,
) -> dict[str, Any]:
    base = sample_price_for_symbol(symbol)
    funding = sample_funding_for_symbol(symbol)
    now_ms = int(time.time() * 1000)

    premium_index = {
        "symbol": symbol,
        "markPrice": f"{base * 1.0002:.8f}",
        "indexPrice": f"{base:.8f}",
        "estimatedSettlePrice": f"{base:.8f}",
        "lastFundingRate": f"{funding:.8f}",
        "interestRate": "0.00010000",
        "nextFundingTime": now_ms + 8 * 60 * 60 * 1000,
        "time": now_ms,
    }
    ticker_24hr = {
        "symbol": symbol,
        "lastPrice": f"{base * 1.0001:.8f}",
        "priceChangePercent": "1.250",
        "volume": "100000.000",
        "quoteVolume": f"{base * 100000:.8f}",
        "closeTime": now_ms,
    }
    book_ticker = {
        "symbol": symbol,
        "bidPrice": f"{base * 1.00005:.8f}",
        "bidQty": "10.0",
        "askPrice": f"{base * 1.00015:.8f}",
        "askQty": "10.0",
        "time": now_ms,
    }
    funding_history = [
        {
            "symbol": symbol,
            "fundingTime": now_ms - 16 * 60 * 60 * 1000,
            "fundingRate": f"{funding * 0.9:.8f}",
            "markPrice": f"{base:.8f}",
        },
        {
            "symbol": symbol,
            "fundingTime": now_ms - 8 * 60 * 60 * 1000,
            "fundingRate": f"{funding:.8f}",
            "markPrice": f"{base:.8f}",
        },
    ]

    return {
        "symbol": symbol,
        "data_mode": data_mode,
        "premium_index": premium_index,
        "ticker_24hr": ticker_24hr,
        "book_ticker": book_ticker,
        "funding_history": funding_history,
        "error_message": error_message,
    }


def funding_history_average(payload: dict[str, Any]) -> float:
    history = payload.get("funding_history") or []
    rates = [safe_float(item.get("fundingRate")) for item in history if isinstance(item, dict)]

    if not rates:
        return 0.0

    return sum(rates) / len(rates)


def normalize_symbol_payload(
    payload: dict[str, Any],
    ingestion_label: str,
    created_at: str,
    funding_periods_per_year: float = 365.0 * 3.0,
) -> dict[str, Any]:
    symbol = str(payload["symbol"]).upper()
    premium = payload.get("premium_index") or {}
    ticker = payload.get("ticker_24hr") or {}
    book = payload.get("book_ticker") or {}
    history = payload.get("funding_history") or []

    mark_price = safe_float(premium.get("markPrice") or ticker.get("lastPrice"))
    index_price = safe_float(premium.get("indexPrice") or mark_price)

    basis_bps = 0.0

    if index_price != 0:
        basis_bps = round((mark_price - index_price) / index_price * 10000.0, 6)

    last_funding_rate = safe_float(premium.get("lastFundingRate"))

    if last_funding_rate == 0 and history:
        last_funding_rate = safe_float(history[-1].get("fundingRate"))

    last_funding_rate_bps = round(last_funding_rate * 10000.0, 8)
    annualized_funding_rate = round(last_funding_rate * funding_periods_per_year, 10)
    avg_funding_rate = round(funding_history_average(payload), 10)

    bid_price = safe_float(book.get("bidPrice"))
    ask_price = safe_float(book.get("askPrice"))

    spread_bps = 0.0

    if bid_price > 0 and ask_price > 0:
        mid = (bid_price + ask_price) / 2.0
        if mid != 0:
            spread_bps = round((ask_price - bid_price) / mid * 10000.0, 6)

    quote_volume = safe_float(ticker.get("quoteVolume"))
    price_change_percent = safe_float(ticker.get("priceChangePercent"))
    next_funding_time = premium.get("nextFundingTime")
    event_time = premium.get("time") or ticker.get("closeTime") or book.get("time")

    return {
        "snapshot_id": f"{ingestion_label}-{symbol}",
        "ingestion_label": ingestion_label,
        "created_at": created_at,
        "symbol": symbol,
        "source": SOURCE_NAME,
        "data_mode": payload.get("data_mode") or DATA_MODE_FAILED,
        "mark_price": round(mark_price, 8),
        "index_price": round(index_price, 8),
        "basis_bps": basis_bps,
        "last_funding_rate": round(last_funding_rate, 10),
        "last_funding_rate_bps": last_funding_rate_bps,
        "annualized_funding_rate": annualized_funding_rate,
        "avg_funding_rate_history": avg_funding_rate,
        "funding_history_count": len(history) if isinstance(history, list) else 0,
        "bid_price": round(bid_price, 8),
        "ask_price": round(ask_price, 8),
        "spread_bps": spread_bps,
        "quote_volume": round(quote_volume, 8),
        "price_change_percent": round(price_change_percent, 8),
        "next_funding_time": None if next_funding_time is None else safe_int(next_funding_time),
        "event_time": None if event_time is None else safe_int(event_time),
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "error_message": payload.get("error_message"),
        "raw_payload": payload,
        "metadata": {
            "base_url": BINANCE_USDS_M_BASE_URL,
            "funding_periods_per_year": funding_periods_per_year,
            "ingestion_role": "PUBLIC_MARKET_DATA_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
        },
    }


def failed_snapshot(
    symbol: str,
    ingestion_label: str,
    created_at: str,
    error_message: str,
) -> dict[str, Any]:
    return {
        "snapshot_id": f"{ingestion_label}-{symbol}",
        "ingestion_label": ingestion_label,
        "created_at": created_at,
        "symbol": symbol,
        "source": SOURCE_NAME,
        "data_mode": DATA_MODE_FAILED,
        "mark_price": 0.0,
        "index_price": 0.0,
        "basis_bps": 0.0,
        "last_funding_rate": 0.0,
        "last_funding_rate_bps": 0.0,
        "annualized_funding_rate": 0.0,
        "avg_funding_rate_history": 0.0,
        "funding_history_count": 0,
        "bid_price": 0.0,
        "ask_price": 0.0,
        "spread_bps": 0.0,
        "quote_volume": 0.0,
        "price_change_percent": 0.0,
        "next_funding_time": None,
        "event_time": None,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "error_message": error_message,
        "raw_payload": {
            "symbol": symbol,
            "data_mode": DATA_MODE_FAILED,
            "error_message": error_message,
        },
        "metadata": {
            "base_url": BINANCE_USDS_M_BASE_URL,
            "ingestion_role": "PUBLIC_MARKET_DATA_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
        },
    }


def fetch_and_normalize_symbol(
    symbol: str,
    ingestion_label: str,
    created_at: str,
    timeout_seconds: float,
    funding_limit: int,
    offline_sample: bool,
    allow_sample_fallback: bool,
) -> dict[str, Any]:
    if offline_sample:
        return normalize_symbol_payload(
            sample_symbol_payload(symbol, DATA_MODE_OFFLINE_SAMPLE),
            ingestion_label=ingestion_label,
            created_at=created_at,
        )

    try:
        payload = fetch_online_symbol_payload(
            symbol=symbol,
            timeout_seconds=timeout_seconds,
            funding_limit=funding_limit,
        )
        return normalize_symbol_payload(
            payload,
            ingestion_label=ingestion_label,
            created_at=created_at,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        message = f"{type(exc).__name__}: {exc}"

        if allow_sample_fallback:
            return normalize_symbol_payload(
                sample_symbol_payload(
                    symbol=symbol,
                    data_mode=DATA_MODE_OFFLINE_SAMPLE_FALLBACK,
                    error_message=message,
                ),
                ingestion_label=ingestion_label,
                created_at=created_at,
            )

        return failed_snapshot(
            symbol=symbol,
            ingestion_label=ingestion_label,
            created_at=created_at,
            error_message=message,
        )


def persist_snapshots(
    db_path: str | Path,
    snapshots: list[dict[str, Any]],
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for item in snapshots:
            conn.execute(
                """
                INSERT OR REPLACE INTO real_market_public_data_snapshots (
                    snapshot_id,
                    ingestion_label,
                    created_at,
                    symbol,
                    source,
                    data_mode,
                    mark_price,
                    index_price,
                    basis_bps,
                    last_funding_rate,
                    last_funding_rate_bps,
                    annualized_funding_rate,
                    avg_funding_rate_history,
                    funding_history_count,
                    bid_price,
                    ask_price,
                    spread_bps,
                    quote_volume,
                    price_change_percent,
                    next_funding_time,
                    event_time,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    error_message,
                    raw_payload_json,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["snapshot_id"],
                    item["ingestion_label"],
                    item["created_at"],
                    item["symbol"],
                    item["source"],
                    item["data_mode"],
                    str(item["mark_price"]),
                    str(item["index_price"]),
                    str(item["basis_bps"]),
                    str(item["last_funding_rate"]),
                    str(item["last_funding_rate_bps"]),
                    str(item["annualized_funding_rate"]),
                    str(item["avg_funding_rate_history"]),
                    item["funding_history_count"],
                    str(item["bid_price"]),
                    str(item["ask_price"]),
                    str(item["spread_bps"]),
                    str(item["quote_volume"]),
                    str(item["price_change_percent"]),
                    item["next_funding_time"],
                    item["event_time"],
                    item["live_trading"],
                    item["live_order_sent"],
                    item["capital_deployment"],
                    item["error_message"],
                    json.dumps(item["raw_payload"], sort_keys=True),
                    json.dumps(item["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_ingestion(
    db_path: str | Path,
    ingestion_label: str,
    report_label: str,
    created_at: str,
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    symbol_count = len(snapshots)
    successful = [item for item in snapshots if item["data_mode"] != DATA_MODE_FAILED]
    failed = [item for item in snapshots if item["data_mode"] == DATA_MODE_FAILED]

    data_mode_counts = dict(Counter(item["data_mode"] for item in snapshots))

    positive_funding_count = sum(1 for item in successful if safe_float(item["last_funding_rate"]) > 0)
    negative_funding_count = sum(1 for item in successful if safe_float(item["last_funding_rate"]) < 0)
    zero_funding_count = sum(1 for item in successful if safe_float(item["last_funding_rate"]) == 0)

    safety_breach_count = sum(
        1
        for item in snapshots
        if item["live_trading"] != LIVE_TRADING_STATUS
        or int(item["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or item["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
    )

    avg_basis = 0.0
    avg_spread = 0.0
    avg_annualized_funding = 0.0

    if successful:
        avg_basis = round(sum(safe_float(item["basis_bps"]) for item in successful) / len(successful), 8)
        avg_spread = round(sum(safe_float(item["spread_bps"]) for item in successful) / len(successful), 8)
        avg_annualized_funding = round(
            sum(safe_float(item["annualized_funding_rate"]) for item in successful) / len(successful),
            10,
        )

    if safety_breach_count > 0:
        global_verdict = INGESTION_SAFETY_BREACH_VERDICT
        recommended_action = RECOMMEND_REVIEW_SAFETY
    elif len(successful) == 0:
        global_verdict = INGESTION_FAILED_VERDICT
        recommended_action = RECOMMEND_RETRY_PUBLIC_DATA
    elif len(failed) > 0:
        global_verdict = INGESTION_PARTIAL_VERDICT
        recommended_action = RECOMMEND_RETRY_PUBLIC_DATA
    else:
        global_verdict = INGESTION_SUCCESS_VERDICT
        recommended_action = RECOMMEND_USE_FOR_ALPHA

    return {
        "report_label": report_label,
        "ingestion_label": ingestion_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source": SOURCE_NAME,
        "symbol_count": symbol_count,
        "successful_symbol_count": len(successful),
        "failed_symbol_count": len(failed),
        "online_public_api_count": data_mode_counts.get(DATA_MODE_ONLINE, 0),
        "offline_sample_count": data_mode_counts.get(DATA_MODE_OFFLINE_SAMPLE, 0),
        "fallback_count": data_mode_counts.get(DATA_MODE_OFFLINE_SAMPLE_FALLBACK, 0),
        "positive_funding_count": positive_funding_count,
        "negative_funding_count": negative_funding_count,
        "zero_funding_count": zero_funding_count,
        "safety_breach_count": safety_breach_count,
        "average_basis_bps": avg_basis,
        "average_spread_bps": avg_spread,
        "average_annualized_funding_rate": avg_annualized_funding,
        "data_mode_counts": data_mode_counts,
        "symbols": [item["symbol"] for item in snapshots],
        "snapshots": snapshots,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    snapshot_lines = []

    for item in summary["snapshots"]:
        snapshot_lines.append(
            "- "
            + item["symbol"]
            + ": "
            + f"mode={item['data_mode']}, "
            + f"mark={item['mark_price']}, "
            + f"index={item['index_price']}, "
            + f"basis_bps={item['basis_bps']}, "
            + f"funding_rate={item['last_funding_rate']}, "
            + f"annualized={item['annualized_funding_rate']}, "
            + f"spread_bps={item['spread_bps']}"
        )

    snapshot_markdown = "\n".join(snapshot_lines) or "- None"

    return f"""# DeltaGrid Mission 49 Real Market Public Data Ingestion Report

Report label: {summary['report_label']}
Ingestion label: {summary['ingestion_label']}
Created at: {summary['created_at']}
Source: {summary['source']}

## Ingestion Summary

Symbol count: {summary['symbol_count']}
Successful symbol count: {summary['successful_symbol_count']}
Failed symbol count: {summary['failed_symbol_count']}

Online public API count: {summary['online_public_api_count']}
Offline sample count: {summary['offline_sample_count']}
Fallback count: {summary['fallback_count']}

Positive funding count: {summary['positive_funding_count']}
Negative funding count: {summary['negative_funding_count']}
Zero funding count: {summary['zero_funding_count']}

Safety breach count: {summary['safety_breach_count']}

Average basis bps: {summary['average_basis_bps']}
Average spread bps: {summary['average_spread_bps']}
Average annualized funding rate: {summary['average_annualized_funding_rate']}

## Symbol Snapshots

{snapshot_markdown}

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
            INSERT OR REPLACE INTO real_market_public_data_reports (
                report_label,
                ingestion_label,
                created_at,
                source,
                symbol_count,
                successful_symbol_count,
                failed_symbol_count,
                online_public_api_count,
                offline_sample_count,
                fallback_count,
                positive_funding_count,
                negative_funding_count,
                zero_funding_count,
                safety_breach_count,
                average_basis_bps,
                average_spread_bps,
                average_annualized_funding_rate,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["ingestion_label"],
                summary["created_at"],
                summary["source"],
                summary["symbol_count"],
                summary["successful_symbol_count"],
                summary["failed_symbol_count"],
                summary["online_public_api_count"],
                summary["offline_sample_count"],
                summary["fallback_count"],
                summary["positive_funding_count"],
                summary["negative_funding_count"],
                summary["zero_funding_count"],
                summary["safety_breach_count"],
                str(summary["average_basis_bps"]),
                str(summary["average_spread_bps"]),
                str(summary["average_annualized_funding_rate"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_real_market_public_data_ingestion(
    db_path: str | Path = "offchain/deltagrid.db",
    ingestion_label: str | None = None,
    report_label: str | None = None,
    symbols: str | list[str] | tuple[str, ...] | None = None,
    timeout_seconds: float = 10.0,
    funding_limit: int = 20,
    offline_sample: bool = False,
    allow_sample_fallback: bool = False,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0")

    if funding_limit <= 0 or funding_limit > 1000:
        raise ValueError("funding_limit must be between 1 and 1000")

    resolved_symbols = parse_symbols(symbols)
    label = ingestion_label or new_ingestion_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    snapshots = [
        fetch_and_normalize_symbol(
            symbol=symbol,
            ingestion_label=label,
            created_at=created_at,
            timeout_seconds=timeout_seconds,
            funding_limit=funding_limit,
            offline_sample=offline_sample,
            allow_sample_fallback=allow_sample_fallback,
        )
        for symbol in resolved_symbols
    ]

    persist_snapshots(db_path, snapshots)

    summary = summarize_ingestion(
        db_path=db_path,
        ingestion_label=label,
        report_label=report,
        created_at=created_at,
        snapshots=snapshots,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db_path, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid real-market public data ingestion."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--ingestion-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--funding-limit", type=int, default=20)
    parser.add_argument("--offline-sample", action="store_true")
    parser.add_argument("--allow-sample-fallback", action="store_true")
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_real_market_public_data_ingestion(
        db_path=args.db,
        ingestion_label=args.ingestion_label,
        report_label=args.report_label,
        symbols=args.symbols,
        timeout_seconds=args.timeout_seconds,
        funding_limit=args.funding_limit,
        offline_sample=args.offline_sample,
        allow_sample_fallback=args.allow_sample_fallback,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
