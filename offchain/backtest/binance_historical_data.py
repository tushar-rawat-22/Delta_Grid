import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from db.schema import (
    init_market_database,
    insert_historical_candle,
    upsert_chain,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")
DEFAULT_BASE_URL = "https://api.binance.com"
BINANCE_MARKET_ID = 0


INTERVAL_MS = {
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "2h": 2 * 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "6h": 6 * 60 * 60_000,
    "8h": 8 * 60 * 60_000,
    "12h": 12 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
    "3d": 3 * 24 * 60 * 60_000,
    "1w": 7 * 24 * 60 * 60_000,
}


def resolve_db_path(db_path: str) -> str:
    candidate = Path(db_path)

    if candidate.is_absolute():
        return str(candidate)

    return str(OFFCHAIN_ROOT / candidate)


def date_to_ms(date_value: str) -> int:
    dt = datetime.fromisoformat(date_value).replace(tzinfo=timezone.utc)

    return int(dt.timestamp() * 1000)


def ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def fetch_klines(
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    limit: int,
    base_url: str = DEFAULT_BASE_URL,
) -> list:
    url = f"{base_url}/api/v3/klines"

    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": limit,
    }

    response = requests.get(
        url,
        params=params,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    if isinstance(data, dict):
        raise RuntimeError(f"Binance API error: {data}")

    return data


def normalize_kline(row: list) -> dict:
    return {
        "timestamp_utc": ms_to_iso(int(row[0])),
        "open": str(row[1]),
        "high": str(row[2]),
        "low": str(row[3]),
        "close": str(row[4]),
        "volume": str(row[5]),
    }


def ingest_binance_klines(
    db_path: str,
    symbol: str,
    interval: str,
    start_date: str,
    end_date: str,
    limit: int = 1000,
    base_url: str = DEFAULT_BASE_URL,
) -> dict:
    if interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval: {interval}")

    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")

    resolved_db_path = resolve_db_path(db_path)

    init_market_database(resolved_db_path)

    upsert_chain(
        db_path=resolved_db_path,
        chain_id=BINANCE_MARKET_ID,
        name="Binance Spot",
        rpc_url=base_url,
    )

    start_ms = date_to_ms(start_date)
    end_ms = date_to_ms(end_date)
    interval_ms = INTERVAL_MS[interval]

    total_inserted = 0
    requests_made = 0

    current_start = start_ms

    while current_start <= end_ms:
        rows = fetch_klines(
            symbol=symbol,
            interval=interval,
            start_time_ms=current_start,
            end_time_ms=end_ms,
            limit=limit,
            base_url=base_url,
        )

        requests_made += 1

        if not rows:
            break

        for row in rows:
            candle = normalize_kline(row)

            insert_historical_candle(
                db_path=resolved_db_path,
                chain_id=BINANCE_MARKET_ID,
                symbol=symbol.upper(),
                timeframe=interval,
                timestamp_utc=candle["timestamp_utc"],
                open_price=candle["open"],
                high_price=candle["high"],
                low_price=candle["low"],
                close_price=candle["close"],
                volume=candle["volume"],
                source="binance_spot",
            )

            total_inserted += 1

        last_open_time = int(rows[-1][0])
        next_start = last_open_time + interval_ms

        if next_start <= current_start:
            break

        current_start = next_start

        if len(rows) < limit:
            break

    return {
        "source": "binance_spot",
        "symbol": symbol.upper(),
        "interval": interval,
        "start_date": start_date,
        "end_date": end_date,
        "candles_inserted_or_updated": total_inserted,
        "requests_made": requests_made,
        "chain_id": BINANCE_MARKET_ID,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DeltaGrid Binance historical candle ingestor")

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--start-date", default="2023-01-01")
    parser.add_argument("--end-date", default="2026-06-30")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)

    args = parser.parse_args()

    print("DeltaGrid Binance Historical Data Ingestor")
    print("Mode: real historical market data only")
    print("No private keys. No signing. No real trades.")

    result = ingest_binance_klines(
        db_path=args.db_path,
        symbol=args.symbol,
        interval=args.interval,
        start_date=args.start_date,
        end_date=args.end_date,
        limit=args.limit,
        base_url=args.base_url,
    )

    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
