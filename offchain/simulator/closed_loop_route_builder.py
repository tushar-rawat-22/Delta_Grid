import argparse
import json
import os
import sys
from decimal import Decimal, getcontext
from pathlib import Path

from dotenv import load_dotenv


getcontext().prec = 50

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from db.schema import (
    init_market_database,
    insert_route_candidate,
    list_latest_pool_price_snapshots,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")
DEFAULT_START_TOKEN = "0x4200000000000000000000000000000000000006"


def resolve_db_path(db_path: str) -> str:
    candidate = Path(db_path)

    if candidate.is_absolute():
        return str(candidate)

    return str(OFFCHAIN_ROOT / candidate)


def build_edges(snapshots: list[dict]) -> list[dict]:
    edges = []

    for snapshot in snapshots:
        base = {
            "pool_id": snapshot["pool_id"],
            "chain_id": snapshot["chain_id"],
            "protocol": snapshot["protocol"],
            "pool_address": snapshot["pool_address"],
            "liquidity_score": snapshot["liquidity_score"],
            "block_number": snapshot["block_number"],
        }

        edges.append({
            **base,
            "direction": "token0_to_token1",
            "token_in": snapshot["token0_address"].lower(),
            "token_out": snapshot["token1_address"].lower(),
            "price_out_per_in": snapshot["price_token1_per_token0"],
        })

        edges.append({
            **base,
            "direction": "token1_to_token0",
            "token_in": snapshot["token1_address"].lower(),
            "token_out": snapshot["token0_address"].lower(),
            "price_out_per_in": snapshot["price_token0_per_token1"],
        })

    return edges


def route_step(edge: dict, step_number: int) -> dict:
    return {
        "step": step_number,
        "protocol": edge["protocol"],
        "pool_address": edge["pool_address"],
        "direction": edge["direction"],
        "token_in": edge["token_in"],
        "token_out": edge["token_out"],
        "price_out_per_in": edge["price_out_per_in"],
    }


def build_closed_loop_routes(
    snapshots: list[dict],
    start_token_address: str,
) -> list[dict]:
    start = start_token_address.lower()
    edges = build_edges(snapshots)

    routes = []
    seen = set()

    for first in edges:
        if first["token_in"] != start:
            continue

        for second in edges:
            if first["pool_id"] == second["pool_id"]:
                continue

            if first["token_out"] != second["token_in"]:
                continue

            for third in edges:
                pool_ids = {
                    first["pool_id"],
                    second["pool_id"],
                    third["pool_id"],
                }

                if len(pool_ids) != 3:
                    continue

                if second["token_out"] != third["token_in"]:
                    continue

                if third["token_out"] != start:
                    continue

                signature = (
                    first["pool_id"],
                    first["direction"],
                    second["pool_id"],
                    second["direction"],
                    third["pool_id"],
                    third["direction"],
                )

                if signature in seen:
                    continue

                seen.add(signature)

                multiplier = (
                    Decimal(first["price_out_per_in"])
                    * Decimal(second["price_out_per_in"])
                    * Decimal(third["price_out_per_in"])
                )

                min_liquidity = min(
                    first["liquidity_score"],
                    second["liquidity_score"],
                    third["liquidity_score"],
                )

                route = [
                    route_step(first, 1),
                    route_step(second, 2),
                    route_step(third, 3),
                ]

                routes.append({
                    "chain_id": first["chain_id"],
                    "start_token_address": start,
                    "end_token_address": start,
                    "hops": 3,
                    "route": route,
                    "estimated_output_per_input": format(multiplier, "f"),
                    "min_liquidity_score": min_liquidity,
                    "block_number": first["block_number"] or second["block_number"] or third["block_number"],
                })

    return routes


def create_closed_loop_route_candidates(
    db_path: str,
    start_token_address: str = DEFAULT_START_TOKEN,
) -> dict:
    resolved_db_path = resolve_db_path(db_path)

    init_market_database(resolved_db_path)

    snapshots = list_latest_pool_price_snapshots(resolved_db_path)

    routes = build_closed_loop_routes(
        snapshots=snapshots,
        start_token_address=start_token_address,
    )

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
            source="closed_loop_route_builder_v1",
            block_number=route["block_number"],
        )

        route_ids.append(route_id)

    return {
        "snapshots_seen": len(snapshots),
        "closed_loop_routes_created": len(route_ids),
        "route_ids": route_ids,
        "start_token_address": start_token_address.lower(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DeltaGrid closed-loop route builder")

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--start-token-address", default=DEFAULT_START_TOKEN)

    args = parser.parse_args()

    print("DeltaGrid Closed-Loop Route Builder")
    print("Mode: research-only route generation")
    print("No private keys. No signing. No real trades.")

    result = create_closed_loop_route_candidates(
        db_path=args.db_path,
        start_token_address=args.start_token_address,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
