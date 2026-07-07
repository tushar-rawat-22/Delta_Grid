import argparse
import json
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
    insert_opportunity_detection,
    list_route_candidates,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def resolve_db_path(db_path: str) -> str:
    candidate = Path(db_path)

    if candidate.is_absolute():
        return str(candidate)

    return str(OFFCHAIN_ROOT / candidate)


def is_closed_loop(route: dict) -> bool:
    return route["start_token_address"].lower() == route["end_token_address"].lower()


def classify_opportunity_type(route: dict) -> str:
    if is_closed_loop(route):
        return "closed_loop_arbitrage"

    return "conversion_route_not_profit_valid"


def calculate_gross_edge_bps(route: dict) -> Decimal:
    if not is_closed_loop(route):
        return Decimal("0")

    multiplier = Decimal(route["estimated_output_per_input"])

    return (multiplier - Decimal("1")) * Decimal("10000")


def build_rejection_reasons(
    route: dict,
    gross_edge_bps: Decimal,
    net_edge_bps: Decimal,
    min_net_edge_bps: int,
    min_liquidity_score: int,
) -> list[str]:
    reasons = []

    if not is_closed_loop(route):
        reasons.append("not_closed_loop_route")

    if route["min_liquidity_score"] < min_liquidity_score:
        reasons.append("liquidity_score_too_low")

    if is_closed_loop(route) and gross_edge_bps <= 0:
        reasons.append("gross_edge_not_positive")

    if is_closed_loop(route) and net_edge_bps < Decimal(min_net_edge_bps):
        reasons.append("net_edge_below_minimum")

    return reasons


def calculate_risk_score(
    status: str,
    min_liquidity_score: int,
    net_edge_bps: Decimal,
    min_net_edge_bps: int,
) -> int:
    if status != "APPROVED":
        return 0

    liquidity_component = min(60, max(0, int(min_liquidity_score * 0.6)))

    edge_bonus = min(
        40,
        max(0, int((net_edge_bps / Decimal(max(min_net_edge_bps, 1))) * Decimal(20))),
    )

    return min(100, liquidity_component + edge_bonus)


def evaluate_route_candidate(
    route: dict,
    fee_bps: int,
    slippage_bps: int,
    gas_cost_bps: int,
    safety_buffer_bps: int,
    min_net_edge_bps: int,
    min_liquidity_score: int,
) -> dict:
    gross_edge_bps = calculate_gross_edge_bps(route)

    total_cost_bps = Decimal(
        fee_bps
        + slippage_bps
        + gas_cost_bps
        + safety_buffer_bps
    )

    net_edge_bps = gross_edge_bps - total_cost_bps

    rejection_reasons = build_rejection_reasons(
        route=route,
        gross_edge_bps=gross_edge_bps,
        net_edge_bps=net_edge_bps,
        min_net_edge_bps=min_net_edge_bps,
        min_liquidity_score=min_liquidity_score,
    )

    status = "APPROVED" if not rejection_reasons else "REJECTED"

    risk_score = calculate_risk_score(
        status=status,
        min_liquidity_score=route["min_liquidity_score"],
        net_edge_bps=net_edge_bps,
        min_net_edge_bps=min_net_edge_bps,
    )

    assumptions = {
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "gas_cost_bps": gas_cost_bps,
        "safety_buffer_bps": safety_buffer_bps,
        "min_net_edge_bps": min_net_edge_bps,
        "min_liquidity_score": min_liquidity_score,
        "closed_loop_required": True,
        "research_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
    }

    return {
        "route_candidate_id": route["id"],
        "chain_id": route["chain_id"],
        "opportunity_type": classify_opportunity_type(route),
        "start_token_address": route["start_token_address"],
        "end_token_address": route["end_token_address"],
        "estimated_output_per_input": route["estimated_output_per_input"],
        "gross_edge_bps": format(gross_edge_bps, "f"),
        "fee_bps": str(fee_bps),
        "slippage_bps": str(slippage_bps),
        "gas_cost_bps": str(gas_cost_bps),
        "safety_buffer_bps": str(safety_buffer_bps),
        "total_cost_bps": format(total_cost_bps, "f"),
        "net_edge_bps": format(net_edge_bps, "f"),
        "min_liquidity_score": route["min_liquidity_score"],
        "risk_score": risk_score,
        "status": status,
        "rejection_reasons": rejection_reasons,
        "assumptions": assumptions,
        "source": "optimized_opportunity_detector_v1",
        "block_number": route["block_number"],
    }


def detect_opportunities(
    db_path: str,
    fee_bps: int = 10,
    slippage_bps: int = 10,
    gas_cost_bps: int = 10,
    safety_buffer_bps: int = 20,
    min_net_edge_bps: int = 50,
    min_liquidity_score: int = 70,
) -> dict:
    resolved_db_path = resolve_db_path(db_path)

    init_market_database(resolved_db_path)

    routes = list_route_candidates(resolved_db_path)

    detections = []

    for route in routes:
        detection = evaluate_route_candidate(
            route=route,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            gas_cost_bps=gas_cost_bps,
            safety_buffer_bps=safety_buffer_bps,
            min_net_edge_bps=min_net_edge_bps,
            min_liquidity_score=min_liquidity_score,
        )

        detection_id = insert_opportunity_detection(
            db_path=resolved_db_path,
            route_candidate_id=detection["route_candidate_id"],
            chain_id=detection["chain_id"],
            opportunity_type=detection["opportunity_type"],
            start_token_address=detection["start_token_address"],
            end_token_address=detection["end_token_address"],
            estimated_output_per_input=detection["estimated_output_per_input"],
            gross_edge_bps=detection["gross_edge_bps"],
            fee_bps=detection["fee_bps"],
            slippage_bps=detection["slippage_bps"],
            gas_cost_bps=detection["gas_cost_bps"],
            safety_buffer_bps=detection["safety_buffer_bps"],
            total_cost_bps=detection["total_cost_bps"],
            net_edge_bps=detection["net_edge_bps"],
            min_liquidity_score=detection["min_liquidity_score"],
            risk_score=detection["risk_score"],
            status=detection["status"],
            rejection_reasons_json=json.dumps(detection["rejection_reasons"]),
            assumptions_json=json.dumps(detection["assumptions"]),
            source=detection["source"],
            block_number=detection["block_number"],
        )

        detection["id"] = detection_id
        detections.append(detection)

    approved = sum(1 for item in detections if item["status"] == "APPROVED")
    rejected = sum(1 for item in detections if item["status"] == "REJECTED")

    return {
        "routes_seen": len(routes),
        "detections_created": len(detections),
        "approved": approved,
        "rejected": rejected,
        "detections": detections,
        "global_verdict": "RESEARCH_ONLY_NO_LIVE_TRADING",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DeltaGrid optimized opportunity detector")

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--fee-bps", type=int, default=10)
    parser.add_argument("--slippage-bps", type=int, default=10)
    parser.add_argument("--gas-cost-bps", type=int, default=10)
    parser.add_argument("--safety-buffer-bps", type=int, default=20)
    parser.add_argument("--min-net-edge-bps", type=int, default=50)
    parser.add_argument("--min-liquidity-score", type=int, default=70)

    args = parser.parse_args()

    print("DeltaGrid Optimized Opportunity Detector")
    print("Mode: research-only opportunity validation")
    print("No private keys. No signing. No real trades.")

    result = detect_opportunities(
        db_path=args.db_path,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
        gas_cost_bps=args.gas_cost_bps,
        safety_buffer_bps=args.safety_buffer_bps,
        min_net_edge_bps=args.min_net_edge_bps,
        min_liquidity_score=args.min_liquidity_score,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
