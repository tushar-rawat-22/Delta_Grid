import argparse
import os
import sys
from decimal import Decimal, getcontext
from pathlib import Path

from dotenv import load_dotenv


getcontext().prec = 40

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from db.schema import (
    init_market_database,
    insert_pool_price_snapshot,
    list_pools,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def resolve_db_path(db_path: str) -> str:
    candidate = Path(db_path)

    if candidate.is_absolute():
        return str(candidate)

    return str(OFFCHAIN_ROOT / candidate)


def simulated_price_for_pool(pool: dict) -> tuple[str, str, int]:
    token0 = pool["token0_address"].lower()
    token1 = pool["token1_address"].lower()

    weth = "0x4200000000000000000000000000000000000006"
    usdc_demo = "0x0000000000000000000000000000000000000001"
    dai_demo = "0x0000000000000000000000000000000000000002"

    if token0 == weth and token1 == usdc_demo:
        price_1_per_0 = Decimal("3000")
        liquidity_score = 90

    elif token0 == usdc_demo and token1 == dai_demo:
        price_1_per_0 = Decimal("1")
        liquidity_score = 80

    else:
        price_1_per_0 = Decimal("1")
        liquidity_score = 50

    price_0_per_1 = Decimal("1") / price_1_per_0

    return (
        format(price_1_per_0, "f"),
        format(price_0_per_1, "f"),
        liquidity_score,
    )


def generate_pool_price_snapshots(
    db_path: str,
    block_number: int | None = None,
) -> dict:
    resolved_db_path = resolve_db_path(db_path)

    init_market_database(resolved_db_path)

    pools = list_pools(resolved_db_path)

    snapshot_ids = []

    for pool in pools:
        price_1_per_0, price_0_per_1, liquidity_score = simulated_price_for_pool(pool)

        snapshot_id = insert_pool_price_snapshot(
            db_path=resolved_db_path,
            pool_id=pool["id"],
            chain_id=pool["chain_id"],
            protocol=pool["protocol"],
            pool_address=pool["pool_address"],
            token0_address=pool["token0_address"],
            token1_address=pool["token1_address"],
            price_token1_per_token0=price_1_per_0,
            price_token0_per_token1=price_0_per_1,
            liquidity_score=liquidity_score,
            source="local_simulator",
            block_number=block_number,
        )

        snapshot_ids.append(snapshot_id)

    return {
        "pools_seen": len(pools),
        "snapshots_created": len(snapshot_ids),
        "snapshot_ids": snapshot_ids,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DeltaGrid pool price snapshot simulator")

    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help="SQLite database path",
    )

    parser.add_argument(
        "--block-number",
        type=int,
        default=None,
        help="Optional block number to attach to snapshots",
    )

    args = parser.parse_args()

    print("DeltaGrid Pool Price Snapshot Simulator")
    print("Mode: local simulated prices only")
    print("No private keys. No signing. No real trades.")

    result = generate_pool_price_snapshots(
        db_path=args.db_path,
        block_number=args.block_number,
    )

    print(f"Pools seen: {result['pools_seen']}")
    print(f"Snapshots created: {result['snapshots_created']}")
    print(f"Snapshot IDs: {result['snapshot_ids']}")


if __name__ == "__main__":
    main()
