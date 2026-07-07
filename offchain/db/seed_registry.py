import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from db.schema import (
    init_market_database,
    upsert_chain,
    upsert_pool,
    upsert_token,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")


DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")
DEFAULT_TOKENS_PATH = OFFCHAIN_ROOT / "config" / "seed_tokens.json"
DEFAULT_POOLS_PATH = OFFCHAIN_ROOT / "config" / "seed_pools.json"


def resolve_db_path(db_path: str) -> str:
    candidate = Path(db_path)

    if candidate.is_absolute():
        return str(candidate)

    return str(OFFCHAIN_ROOT / candidate)


def load_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Seed file not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise ValueError(f"Seed file must contain a JSON array: {path}")

    return data


def require_fields(item: dict[str, Any], fields: list[str], item_type: str) -> None:
    missing = [field for field in fields if field not in item]

    if missing:
        raise ValueError(f"{item_type} missing fields: {missing}")


def seed_tokens(db_path: str, tokens_path: Path = DEFAULT_TOKENS_PATH) -> int:
    tokens = load_json_array(tokens_path)

    for token in tokens:
        require_fields(
            token,
            [
                "chain_id",
                "chain_name",
                "rpc_url",
                "address",
                "symbol",
                "decimals",
            ],
            "token",
        )

        upsert_chain(
            db_path=db_path,
            chain_id=int(token["chain_id"]),
            name=str(token["chain_name"]),
            rpc_url=str(token["rpc_url"]),
        )

        upsert_token(
            db_path=db_path,
            chain_id=int(token["chain_id"]),
            address=str(token["address"]),
            symbol=str(token["symbol"]),
            decimals=int(token["decimals"]),
        )

    return len(tokens)


def seed_pools(db_path: str, pools_path: Path = DEFAULT_POOLS_PATH) -> int:
    pools = load_json_array(pools_path)

    for pool in pools:
        require_fields(
            pool,
            [
                "chain_id",
                "chain_name",
                "rpc_url",
                "protocol",
                "pool_address",
                "token0_address",
                "token1_address",
                "fee_bps",
            ],
            "pool",
        )

        upsert_chain(
            db_path=db_path,
            chain_id=int(pool["chain_id"]),
            name=str(pool["chain_name"]),
            rpc_url=str(pool["rpc_url"]),
        )

        upsert_pool(
            db_path=db_path,
            chain_id=int(pool["chain_id"]),
            protocol=str(pool["protocol"]),
            pool_address=str(pool["pool_address"]),
            token0_address=str(pool["token0_address"]),
            token1_address=str(pool["token1_address"]),
            fee_bps=int(pool["fee_bps"]),
        )

    return len(pools)


def seed_registry(
    db_path: str,
    tokens_path: Path = DEFAULT_TOKENS_PATH,
    pools_path: Path = DEFAULT_POOLS_PATH,
) -> dict[str, int]:
    resolved_db_path = resolve_db_path(db_path)

    init_market_database(resolved_db_path)

    token_count = seed_tokens(resolved_db_path, tokens_path)
    pool_count = seed_pools(resolved_db_path, pools_path)

    return {
        "tokens": token_count,
        "pools": pool_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DeltaGrid seed registry loader")

    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help="SQLite database path",
    )

    parser.add_argument(
        "--tokens-path",
        default=str(DEFAULT_TOKENS_PATH),
        help="Path to seed_tokens.json",
    )

    parser.add_argument(
        "--pools-path",
        default=str(DEFAULT_POOLS_PATH),
        help="Path to seed_pools.json",
    )

    args = parser.parse_args()

    print("DeltaGrid Seed Registry")
    print("Mode: local database seed only")
    print("No private keys. No signing. No real trades.")

    result = seed_registry(
        db_path=args.db_path,
        tokens_path=Path(args.tokens_path),
        pools_path=Path(args.pools_path),
    )

    print(f"Seeded tokens: {result['tokens']}")
    print(f"Seeded pools: {result['pools']}")


if __name__ == "__main__":
    main()
