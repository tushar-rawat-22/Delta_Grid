import argparse
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path

from dotenv import load_dotenv


getcontext().prec = 40

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from db.schema import init_market_database, utc_now

from backtest.funding_basis_model import (
    annualize_funding_rate_pct,
    basis_pct,
    ensure_schema as ensure_funding_basis_schema,
    evaluate_delta_neutral_candidate,
    insert_basis_snapshot,
    insert_delta_neutral_candidate,
    resolve_db_path,
    table_count,
    to_decimal,
    upsert_funding_rate,
    upsert_perp_mark_price,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")
BINANCE_USDM_BASE_URL = "https://fapi.binance.com"


def milliseconds_to_utc(milliseconds):
    return (
        datetime
        .fromtimestamp(int(milliseconds) / 1000, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_url(base_url, endpoint, params):
    query = urllib.parse.urlencode(params)

    if query:
        return f"{base_url}{endpoint}?{query}"

    return f"{base_url}{endpoint}"


def binance_public_get(endpoint, params=None, timeout=10):
    params = params or {}

    url = build_url(
        BINANCE_USDM_BASE_URL,
        endpoint,
        params,
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "DeltaGrid-Research-Ingestion/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")

    return json.loads(body)


def fetch_binance_funding_rates(symbol, limit, client=binance_public_get, timeout=10):
    payload = client(
        "/fapi/v1/fundingRate",
        {
            "symbol": symbol.upper(),
            "limit": int(limit),
        },
        timeout,
    )

    if not isinstance(payload, list):
        raise ValueError("Expected Binance fundingRate response to be a list")

    return payload


def fetch_binance_premium_index(symbol, client=binance_public_get, timeout=10):
    payload = client(
        "/fapi/v1/premiumIndex",
        {
            "symbol": symbol.upper(),
        },
        timeout,
    )

    return extract_premium_index(payload, symbol)


def fetch_binance_open_interest(symbol, client=binance_public_get, timeout=10):
    payload = client(
        "/fapi/v1/openInterest",
        {
            "symbol": symbol.upper(),
        },
        timeout,
    )

    if not isinstance(payload, dict):
        raise ValueError("Expected Binance openInterest response to be an object")

    return payload


def extract_premium_index(payload, symbol):
    symbol = symbol.upper()

    if isinstance(payload, dict):
        if payload.get("symbol", symbol).upper() != symbol:
            raise ValueError("Premium index symbol mismatch")

        return payload

    if isinstance(payload, list):
        for item in payload:
            if item.get("symbol", "").upper() == symbol:
                return item

    raise ValueError("Could not find premium index payload for symbol")


def ensure_ingestion_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS funding_basis_ingestion_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        exchange TEXT NOT NULL,
        symbol TEXT NOT NULL,
        funding_rows_ingested INTEGER NOT NULL,
        mark_rows_ingested INTEGER NOT NULL,
        basis_snapshots_created INTEGER NOT NULL,
        candidates_created INTEGER NOT NULL,
        latest_funding_rate TEXT,
        latest_annualized_funding_rate_pct TEXT,
        latest_basis_pct TEXT,
        latest_expected_edge_pct TEXT,
        latest_candidate_verdict TEXT NOT NULL,
        status TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        error_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def insert_ingestion_run(
    db_path,
    run_label,
    exchange,
    symbol,
    funding_rows_ingested,
    mark_rows_ingested,
    basis_snapshots_created,
    candidates_created,
    latest_funding_rate,
    latest_annualized_funding_rate_pct,
    latest_basis_pct,
    latest_expected_edge_pct,
    latest_candidate_verdict,
    status,
    assumptions,
    error,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO funding_basis_ingestion_runs (
        run_label,
        exchange,
        symbol,
        funding_rows_ingested,
        mark_rows_ingested,
        basis_snapshots_created,
        candidates_created,
        latest_funding_rate,
        latest_annualized_funding_rate_pct,
        latest_basis_pct,
        latest_expected_edge_pct,
        latest_candidate_verdict,
        status,
        assumptions_json,
        error_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        exchange,
        symbol.upper(),
        int(funding_rows_ingested),
        int(mark_rows_ingested),
        int(basis_snapshots_created),
        int(candidates_created),
        None if latest_funding_rate is None else format(to_decimal(latest_funding_rate), "f"),
        None if latest_annualized_funding_rate_pct is None else format(to_decimal(latest_annualized_funding_rate_pct), "f"),
        None if latest_basis_pct is None else format(to_decimal(latest_basis_pct), "f"),
        None if latest_expected_edge_pct is None else format(to_decimal(latest_expected_edge_pct), "f"),
        latest_candidate_verdict,
        status,
        json.dumps(assumptions),
        json.dumps(error),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def prepare_database(db_path):
    db_path = resolve_db_path(db_path)

    init_market_database(db_path)
    ensure_funding_basis_schema(db_path)
    ensure_ingestion_schema(db_path)

    return db_path


def latest_funding_record(funding_records):
    if not funding_records:
        raise ValueError("Funding history is empty")

    return sorted(
        funding_records,
        key=lambda item: int(item["fundingTime"]),
    )[-1]


def ingest_binance_funding_basis(
    db_path,
    symbol,
    run_label,
    funding_limit=20,
    interval_hours=Decimal("8"),
    timeout=10,
    client=binance_public_get,
):
    db_path = prepare_database(db_path)

    symbol = symbol.upper()

    assumptions = {
        "research_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
        "no_order_execution": True,
        "exchange": "Binance Futures",
        "spot_exchange": "Binance Spot",
        "perp_exchange": "Binance Futures",
        "symbol": symbol,
        "funding_limit": int(funding_limit),
        "interval_hours": format(to_decimal(interval_hours), "f"),
        "run_label": run_label,
        "source": "binance_public_api",
    }

    funding_records = fetch_binance_funding_rates(
        symbol=symbol,
        limit=funding_limit,
        client=client,
        timeout=timeout,
    )

    if not funding_records:
        raise ValueError("No funding records returned")

    premium = fetch_binance_premium_index(
        symbol=symbol,
        client=client,
        timeout=timeout,
    )

    open_interest = fetch_binance_open_interest(
        symbol=symbol,
        client=client,
        timeout=timeout,
    )

    funding_ids = []

    for record in funding_records:
        funding_time_utc = milliseconds_to_utc(record["fundingTime"])

        funding_id = upsert_funding_rate(
            db_path=db_path,
            exchange="Binance Futures",
            symbol=symbol,
            funding_time_utc=funding_time_utc,
            funding_rate=record["fundingRate"],
            interval_hours=interval_hours,
            source=run_label,
        )

        funding_ids.append(funding_id)

    latest_funding = latest_funding_record(funding_records)

    current_funding_rate = premium.get(
        "lastFundingRate",
        latest_funding["fundingRate"],
    )

    mark_price = premium.get(
        "markPrice",
        latest_funding.get("markPrice"),
    )

    index_price = premium.get("indexPrice")

    if index_price is None:
        raise ValueError("Premium index payload missing indexPrice")

    if mark_price is None:
        raise ValueError("Premium index payload missing markPrice")

    timestamp_ms = premium.get(
        "time",
        open_interest.get(
            "time",
            latest_funding["fundingTime"],
        ),
    )

    timestamp_utc = milliseconds_to_utc(timestamp_ms)

    open_interest_value = open_interest.get("openInterest")

    mark_id = upsert_perp_mark_price(
        db_path=db_path,
        exchange="Binance Futures",
        symbol=symbol,
        timestamp_utc=timestamp_utc,
        mark_price=mark_price,
        index_price=index_price,
        open_interest=open_interest_value,
        source=run_label,
    )

    annualized = annualize_funding_rate_pct(
        current_funding_rate,
        interval_hours,
    )

    basis_value = basis_pct(
        index_price,
        mark_price,
    )

    basis_id = insert_basis_snapshot(
        db_path=db_path,
        spot_exchange="Binance Spot",
        perp_exchange="Binance Futures",
        symbol=symbol,
        timestamp_utc=timestamp_utc,
        spot_price=index_price,
        perp_mark_price=mark_price,
        annualized_funding_rate_pct=annualized,
        open_interest=open_interest_value,
        source=run_label,
        assumptions=assumptions,
    )

    candidate_eval = evaluate_delta_neutral_candidate(
        funding_rate=current_funding_rate,
        annualized_funding_rate_pct=annualized,
        basis_value_pct=basis_value,
        open_interest=open_interest_value,
    )

    candidate_id = insert_delta_neutral_candidate(
        db_path=db_path,
        symbol=symbol,
        timestamp_utc=timestamp_utc,
        spot_exchange="Binance Spot",
        perp_exchange="Binance Futures",
        funding_rate=current_funding_rate,
        annualized_funding_rate_pct=annualized,
        basis_value_pct=basis_value,
        open_interest=open_interest_value,
        assumptions=assumptions,
    )

    run_id = insert_ingestion_run(
        db_path=db_path,
        run_label=run_label,
        exchange="Binance Futures",
        symbol=symbol,
        funding_rows_ingested=len(funding_ids),
        mark_rows_ingested=1,
        basis_snapshots_created=1,
        candidates_created=1,
        latest_funding_rate=current_funding_rate,
        latest_annualized_funding_rate_pct=annualized,
        latest_basis_pct=basis_value,
        latest_expected_edge_pct=candidate_eval["expected_edge_pct"],
        latest_candidate_verdict=candidate_eval["verdict"],
        status="OK",
        assumptions=assumptions,
        error={},
    )

    return {
        "run_id": run_id,
        "run_label": run_label,
        "symbol": symbol,
        "exchange": "Binance Futures",
        "funding_rows_ingested": len(funding_ids),
        "mark_rows_ingested": 1,
        "basis_snapshots_created": 1,
        "candidates_created": 1,
        "latest_funding_rate": format(to_decimal(current_funding_rate), "f"),
        "latest_annualized_funding_rate_pct": format(annualized, "f"),
        "latest_basis_pct": format(basis_value, "f"),
        "latest_expected_edge_pct": format(candidate_eval["expected_edge_pct"], "f"),
        "latest_candidate_verdict": candidate_eval["verdict"],
        "latest_recommended_action": candidate_eval["recommended_action"],
        "funding_table_rows_for_run": table_count(db_path, "funding_rates", run_label),
        "mark_table_rows_for_run": table_count(db_path, "perp_mark_prices", run_label),
        "basis_table_rows_for_run": table_count(db_path, "spot_perp_basis_snapshots", run_label),
        "global_verdict": "REAL_INGESTION_READY_NO_LIVE_TRADING",
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--run-label", default="mission_23_funding_basis_ingestion")
    parser.add_argument("--funding-limit", type=int, default=20)
    parser.add_argument("--interval-hours", default="8")
    parser.add_argument("--timeout", type=int, default=10)

    args = parser.parse_args()

    print("DeltaGrid Funding / Basis Ingestion")
    print("Mode: research-only")
    print("Public market data only.")
    print("No private keys. No signing. No real trades.")

    result = ingest_binance_funding_basis(
        db_path=args.db_path,
        symbol=args.symbol,
        run_label=args.run_label,
        funding_limit=args.funding_limit,
        interval_hours=Decimal(args.interval_hours),
        timeout=args.timeout,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
