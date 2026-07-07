import argparse
import json
import os
import sys
from decimal import Decimal, getcontext
from pathlib import Path


getcontext().prec = 40

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from dotenv import load_dotenv

from db.schema import (
    init_market_database,
    insert_route_candidate,
    list_latest_pool_price_snapshots,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def resolve_db_path(db_path: str) -> str:
    candidate = Path(db_path)

    if candidate.is_absolute():
        return str(candidate)

    return str(OFFCHAIN_ROOT / candidate)


def make_edges(snapshot: dict) -> list[dict]:
    base = {
        "pool_id": snapshot["pool_id"],
        "chain_id": snapshot["chain_id"],
        "protocol": snapshot["protocol"],
        "pool_address": snapshot["pool_address"],
        "liquidity_score": snapshot["liquidity_score"],
        "block_number": snapshot["block_number"],
    }

    return [
        {
            **base,
            "token_in": snapshot["token0_address"],
            "token_out": snapshot["token1_address"],
            "price_out_per_in": snapshot["price_token1_per_token0"],
        },
        {
            **base,
            "token_in": snapshot["token1_address"],
            "token_out": snapshot["token0_address"],
            "price_out_per_in": snapshot["price_token0_per_token1"],
        },
    ]


def build_two_hop_routes(snapshots: list[dict]) -> list[dict]:
    edges = []

    for snapshot in snapshots:
        edges.extend(make_edges(snapshot))

    routes = []

    for first in edges:
        for second in edges:
            if first["pool_id"] == second["pool_id"]:
                continue

            if first["token_out"].lower() != second["token_in"].lower():
                continue

            if first["token_in"].lower() == second["token_out"].lower():
                continue

            output = Decimal(first["price_out_per_in"]) * Decimal(second["price_out_per_in"])
            min_liquidity = min(first["liquidity_score"], second["liquidity_score"])

            route_steps = [
                {
                    "step": 1,
                    "protocol": first["protocol"],
                    "pool_address": first["pool_address"],
                    "token_in": first["token_in"],
                    "token_out": first["token_out"],
                    "price_out_per_in": first["price_out_per_in"],
                },
                {
                    "step": 2,
                    "protocol": second["protocol"],
                    "pool_address": second["pool_address"],
                    "token_in": second["token_in"],
                    "token_out": second["token_out"],
                    "price_out_per_in": second["price_out_per_in"],
                },
            ]

            routes.append({
                "chain_id": first["chain_id"],
                "start_token_address": first["token_in"],
                "end_token_address": second["token_out"],
                "hops": 2,
                "route": route_steps,
                "estimated_output_per_input": format(output, "f"),
                "min_liquidity_score": min_liquidity,
                "block_number": first["block_number"] or second["block_number"],
            })

    return routes


def generate_route_candidates(db_path: str) -> dict:
    resolved_db_path = resolve_db_path(db_path)

    init_market_database(resolved_db_path)

    snapshots = list_latest_pool_price_snapshots(resolved_db_path)
    routes = build_two_hop_routes(snapshots)

    route_ids = []

    for route in routes:
        route_id = insert_route_candidate(
            db_path=resolved_db_path,
            chain_id=route["chain_id"],
            start_token_address=route["start_token_address"],
            end_token_address=route["end_token_address"],
            hops=route["hops"],
            route_json=json.dumps(route["route"]),
            estimated_output_per_input=route["estimated_output_per_input"],
            min_liquidity_score=route["min_liquidity_score"],
            source="local_route_builder",
            block_number=route["block_number"],
        )

        route_ids.append(route_id)

    return {
        "snapshots_seen": len(snapshots),
        "routes_created": len(route_ids),
        "route_ids": route_ids,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DeltaGrid local route builder")

    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help="SQLite database path",
    )

    args = parser.parse_args()

    print("DeltaGrid Route Builder")
    print("Mode: local route candidates only")
    print("No private keys. No signing. No real trades.")

    result = generate_route_candidates(db_path=args.db_path)

    print(f"Snapshots seen: {result['snapshots_seen']}")
    print(f"Routes created: {result['routes_created']}")
    print(f"Route IDs: {result['route_ids']}")


if __name__ == "__main__":
    main()
