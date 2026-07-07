import argparse
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path

from dotenv import load_dotenv


getcontext().prec = 40

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
DEFAULT_CHAIN_ID = 84532


def resolve_db_path(db_path: str) -> str:
    candidate = Path(db_path)

    if candidate.is_absolute():
        return str(candidate)

    return str(OFFCHAIN_ROOT / candidate)


def synthetic_daily_candles(
    symbol: str,
    start_price: str = "2000",
    days: int = 720,
    start_date: str = "2024-01-01",
) -> list[dict]:
    candles = []

    price = Decimal(start_price)
    current_date = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)

    for i in range(days):
        if i < days * 0.25:
            drift = 0.0018
            volatility = 0.010
        elif i < days * 0.50:
            drift = -0.0015
            volatility = 0.018
        elif i < days * 0.75:
            drift = 0.0001
            volatility = 0.006
        else:
            drift = 0.0006
            volatility = 0.025

        wave = math.sin(i / 6) * volatility
        shock = math.sin(i / 17) * volatility * 0.5
        change = Decimal(str(drift + wave + shock))

        open_price = price
        close_price = max(Decimal("1"), open_price * (Decimal("1") + change))

        wick = Decimal(str(abs(math.sin(i / 4)) * volatility * 0.6 + 0.002))
        high_price = max(open_price, close_price) * (Decimal("1") + wick)
        low_price = min(open_price, close_price) * (Decimal("1") - wick)

        volume = Decimal("1000") + Decimal(str(abs(math.sin(i / 9)) * 5000))

        candles.append({
            "symbol": symbol,
            "timestamp_utc": current_date.isoformat(),
            "open": format(open_price, "f"),
            "high": format(high_price, "f"),
            "low": format(low_price, "f"),
            "close": format(close_price, "f"),
            "volume": format(volume, "f"),
        })

        price = close_price
        current_date += timedelta(days=1)

    return candles


def seed_synthetic_history(
    db_path: str,
    chain_id: int,
    symbol: str,
    timeframe: str,
    days: int,
    source: str = "synthetic_regime_v1",
) -> int:
    resolved_db_path = resolve_db_path(db_path)

    init_market_database(resolved_db_path)

    upsert_chain(
        db_path=resolved_db_path,
        chain_id=chain_id,
        name="Base Sepolia",
        rpc_url="https://sepolia.base.org",
    )

    candles = synthetic_daily_candles(
        symbol=symbol,
        days=days,
    )

    for candle in candles:
        insert_historical_candle(
            db_path=resolved_db_path,
            chain_id=chain_id,
            symbol=symbol,
            timeframe=timeframe,
            timestamp_utc=candle["timestamp_utc"],
            open_price=candle["open"],
            high_price=candle["high"],
            low_price=candle["low"],
            close_price=candle["close"],
            volume=candle["volume"],
            source=source,
        )

    return len(candles)


def main() -> None:
    parser = argparse.ArgumentParser(description="DeltaGrid synthetic historical data loader")

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--chain-id", type=int, default=DEFAULT_CHAIN_ID)
    parser.add_argument("--symbol", default="WETH_USDC_DEMO")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--days", type=int, default=720)

    args = parser.parse_args()

    print("DeltaGrid Historical Data Loader")
    print("Mode: synthetic local data only")
    print("No private keys. No signing. No real trades.")

    count = seed_synthetic_history(
        db_path=args.db_path,
        chain_id=args.chain_id,
        symbol=args.symbol,
        timeframe=args.timeframe,
        days=args.days,
    )

    print(f"Seeded candles: {count}")


if __name__ == "__main__":
    main()
