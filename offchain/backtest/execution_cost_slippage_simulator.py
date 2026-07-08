import argparse
import json
import os
import sqlite3
import sys
from decimal import Decimal, getcontext
from pathlib import Path

from dotenv import load_dotenv


getcontext().prec = 40

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from db.schema import init_market_database, utc_now

from backtest.funding_basis_model import (
    ensure_schema as ensure_funding_basis_schema,
    resolve_db_path,
    to_decimal,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS execution_cost_slippage_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_run_label TEXT NOT NULL,
        symbol TEXT NOT NULL,
        scenario_name TEXT NOT NULL,
        scenario_version TEXT NOT NULL,
        spot_price TEXT NOT NULL,
        perp_mark_price TEXT NOT NULL,
        basis_pct TEXT NOT NULL,
        annualized_funding_rate_pct TEXT NOT NULL,
        holding_days INTEGER NOT NULL,
        spot_order_notional_usd TEXT NOT NULL,
        perp_order_notional_usd TEXT NOT NULL,
        gross_notional_usd TEXT NOT NULL,
        spot_liquidity_notional_usd TEXT NOT NULL,
        perp_liquidity_notional_usd TEXT NOT NULL,
        spot_participation_rate_pct TEXT NOT NULL,
        perp_participation_rate_pct TEXT NOT NULL,
        spot_fee_bps TEXT NOT NULL,
        perp_fee_bps TEXT NOT NULL,
        spot_spread_bps TEXT NOT NULL,
        perp_spread_bps TEXT NOT NULL,
        spot_slippage_bps TEXT NOT NULL,
        perp_slippage_bps TEXT NOT NULL,
        spot_leg_cost_pct TEXT NOT NULL,
        perp_leg_cost_pct TEXT NOT NULL,
        combined_cost_pct TEXT NOT NULL,
        expected_funding_edge_pct TEXT NOT NULL,
        net_expected_edge_pct TEXT NOT NULL,
        edge_to_cost_ratio TEXT NOT NULL,
        liquidity_penalty_pct TEXT NOT NULL,
        final_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS execution_cost_slippage_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_run_label TEXT NOT NULL,
        symbol TEXT NOT NULL,
        scenarios_tested INTEGER NOT NULL,
        go_count INTEGER NOT NULL,
        no_go_count INTEGER NOT NULL,
        best_result_id INTEGER,
        best_scenario_version TEXT,
        best_net_expected_edge_pct TEXT NOT NULL,
        lowest_combined_cost_pct TEXT NOT NULL,
        highest_combined_cost_pct TEXT NOT NULL,
        global_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def prepare_database(db_path):
    db_path = resolve_db_path(db_path)

    init_market_database(db_path)
    ensure_funding_basis_schema(db_path)
    ensure_schema(db_path)

    return db_path


def bps_to_pct(bps):
    return to_decimal(bps) / Decimal("100")


def safe_div(numerator, denominator):
    numerator = to_decimal(numerator)
    denominator = to_decimal(denominator)

    if denominator == 0:
        return Decimal("0")

    return numerator / denominator


def scenario_specs():
    return [
        {
            "name": "execution_cost_slippage",
            "version": "small_10k_liquid_low_impact",
            "spot_order_notional_usd": Decimal("10000"),
            "perp_order_notional_usd": Decimal("10000"),
            "spot_liquidity_notional_usd": Decimal("5000000"),
            "perp_liquidity_notional_usd": Decimal("10000000"),
            "spot_fee_bps": Decimal("2"),
            "perp_fee_bps": Decimal("2"),
            "spot_spread_bps": Decimal("1.5"),
            "perp_spread_bps": Decimal("1"),
            "base_slippage_bps": Decimal("1"),
            "impact_slope_bps": Decimal("2"),
            "max_participation_rate_pct": Decimal("2"),
            "liquidity_penalty_multiplier": Decimal("1.5"),
            "holding_days": 7,
            "max_combined_cost_pct": Decimal("0.25"),
            "min_edge_to_cost_ratio": Decimal("1.50"),
            "min_net_expected_edge_pct": Decimal("0.05"),
        },
        {
            "name": "execution_cost_slippage",
            "version": "medium_50k_balanced_impact",
            "spot_order_notional_usd": Decimal("50000"),
            "perp_order_notional_usd": Decimal("50000"),
            "spot_liquidity_notional_usd": Decimal("5000000"),
            "perp_liquidity_notional_usd": Decimal("10000000"),
            "spot_fee_bps": Decimal("3"),
            "perp_fee_bps": Decimal("3"),
            "spot_spread_bps": Decimal("2.5"),
            "perp_spread_bps": Decimal("1.5"),
            "base_slippage_bps": Decimal("1.5"),
            "impact_slope_bps": Decimal("4"),
            "max_participation_rate_pct": Decimal("2"),
            "liquidity_penalty_multiplier": Decimal("1.5"),
            "holding_days": 7,
            "max_combined_cost_pct": Decimal("0.40"),
            "min_edge_to_cost_ratio": Decimal("1.50"),
            "min_net_expected_edge_pct": Decimal("0.05"),
        },
        {
            "name": "execution_cost_slippage",
            "version": "large_250k_stress_impact",
            "spot_order_notional_usd": Decimal("250000"),
            "perp_order_notional_usd": Decimal("250000"),
            "spot_liquidity_notional_usd": Decimal("5000000"),
            "perp_liquidity_notional_usd": Decimal("10000000"),
            "spot_fee_bps": Decimal("4"),
            "perp_fee_bps": Decimal("4"),
            "spot_spread_bps": Decimal("4"),
            "perp_spread_bps": Decimal("2.5"),
            "base_slippage_bps": Decimal("2"),
            "impact_slope_bps": Decimal("8"),
            "max_participation_rate_pct": Decimal("2"),
            "liquidity_penalty_multiplier": Decimal("2"),
            "holding_days": 7,
            "max_combined_cost_pct": Decimal("0.70"),
            "min_edge_to_cost_ratio": Decimal("1.50"),
            "min_net_expected_edge_pct": Decimal("0.05"),
        },
    ]


def calculate_participation_rate_pct(order_notional_usd, liquidity_notional_usd):
    order_notional_usd = to_decimal(order_notional_usd)
    liquidity_notional_usd = to_decimal(liquidity_notional_usd)

    if order_notional_usd < 0:
        raise ValueError("order_notional_usd cannot be negative")

    if liquidity_notional_usd <= 0:
        raise ValueError("liquidity_notional_usd must be positive")

    return order_notional_usd / liquidity_notional_usd * Decimal("100")


def estimate_slippage_bps(
    participation_rate_pct,
    base_slippage_bps,
    impact_slope_bps,
    max_participation_rate_pct,
):
    participation_rate_pct = to_decimal(participation_rate_pct)
    base_slippage_bps = to_decimal(base_slippage_bps)
    impact_slope_bps = to_decimal(impact_slope_bps)
    max_participation_rate_pct = to_decimal(max_participation_rate_pct)

    if max_participation_rate_pct <= 0:
        raise ValueError("max_participation_rate_pct must be positive")

    relative_participation = participation_rate_pct / max_participation_rate_pct

    if relative_participation < 0:
        relative_participation = Decimal("0")

    return base_slippage_bps + impact_slope_bps * relative_participation


def calculate_liquidity_penalty_pct(
    participation_rate_pct,
    max_participation_rate_pct,
    liquidity_penalty_multiplier,
):
    participation_rate_pct = to_decimal(participation_rate_pct)
    max_participation_rate_pct = to_decimal(max_participation_rate_pct)
    liquidity_penalty_multiplier = to_decimal(liquidity_penalty_multiplier)

    if participation_rate_pct <= max_participation_rate_pct:
        return Decimal("0")

    excess_participation = participation_rate_pct - max_participation_rate_pct

    return excess_participation * liquidity_penalty_multiplier


def calculate_leg_execution_cost_pct(
    fee_bps,
    spread_bps,
    slippage_bps,
    participation_rate_pct,
    max_participation_rate_pct,
    liquidity_penalty_multiplier,
):
    fee_round_trip_pct = bps_to_pct(fee_bps) * Decimal("2")
    spread_round_trip_pct = bps_to_pct(spread_bps)
    slippage_round_trip_pct = bps_to_pct(slippage_bps) * Decimal("2")

    liquidity_penalty_pct = calculate_liquidity_penalty_pct(
        participation_rate_pct=participation_rate_pct,
        max_participation_rate_pct=max_participation_rate_pct,
        liquidity_penalty_multiplier=liquidity_penalty_multiplier,
    )

    total_cost_pct = (
        fee_round_trip_pct
        + spread_round_trip_pct
        + slippage_round_trip_pct
        + liquidity_penalty_pct
    )

    return total_cost_pct, liquidity_penalty_pct


def calculate_expected_funding_edge_pct(
    annualized_funding_rate_pct,
    holding_days,
    perp_order_notional_usd,
    gross_notional_usd,
):
    annualized_funding_rate_pct = to_decimal(annualized_funding_rate_pct)
    holding_days = int(holding_days)
    perp_weight = safe_div(
        perp_order_notional_usd,
        gross_notional_usd,
    )

    return annualized_funding_rate_pct * Decimal(holding_days) / Decimal("365") * perp_weight


def cost_verdict(
    spot_participation_rate_pct,
    perp_participation_rate_pct,
    max_participation_rate_pct,
    combined_cost_pct,
    max_combined_cost_pct,
    expected_funding_edge_pct,
    edge_to_cost_ratio,
    min_edge_to_cost_ratio,
    net_expected_edge_pct,
    min_net_expected_edge_pct,
):
    if spot_participation_rate_pct > max_participation_rate_pct:
        return "NO_GO_SPOT_ORDER_TOO_LARGE"

    if perp_participation_rate_pct > max_participation_rate_pct:
        return "NO_GO_PERP_ORDER_TOO_LARGE"

    if combined_cost_pct > max_combined_cost_pct:
        return "NO_GO_EXECUTION_COST_TOO_HIGH"

    if expected_funding_edge_pct <= 0:
        return "NO_GO_NO_POSITIVE_EDGE"

    if edge_to_cost_ratio < min_edge_to_cost_ratio:
        return "NO_GO_EDGE_BELOW_COST"

    if net_expected_edge_pct < min_net_expected_edge_pct:
        return "NO_GO_NET_EDGE_TOO_SMALL"

    return "GO_FOR_RESEARCH"


def recommended_action(verdict):
    if verdict == "GO_FOR_RESEARCH":
        return "PROMOTE_TO_MULTI_SYMBOL_SCANNER"

    if verdict == "NO_GO_SPOT_ORDER_TOO_LARGE":
        return "REDUCE_SPOT_ORDER_SIZE_OR_REQUIRE_MORE_DEPTH"

    if verdict == "NO_GO_PERP_ORDER_TOO_LARGE":
        return "REDUCE_PERP_ORDER_SIZE_OR_REQUIRE_MORE_DEPTH"

    if verdict == "NO_GO_EXECUTION_COST_TOO_HIGH":
        return "REJECT_UNTIL_COSTS_COMPRESS"

    if verdict == "NO_GO_NO_POSITIVE_EDGE":
        return "IGNORE_UNTIL_FUNDING_EDGE_EXPANDS"

    if verdict == "NO_GO_EDGE_BELOW_COST":
        return "WAIT_FOR_BETTER_EDGE_TO_COST_RATIO"

    if verdict == "NO_GO_NET_EDGE_TOO_SMALL":
        return "REJECT_WEAK_AFTER_COST_EDGE"

    return "OBSERVE_ONLY"


def load_latest_market_context(db_path, symbol, source_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    row = cur.execute("""
    SELECT
        timestamp_utc,
        spot_price,
        perp_mark_price,
        basis_pct,
        annualized_funding_rate_pct,
        open_interest
    FROM spot_perp_basis_snapshots
    WHERE symbol = ?
    AND source = ?
    ORDER BY id DESC
    LIMIT 1
    """, (
        symbol.upper(),
        source_run_label,
    )).fetchone()

    conn.close()

    if row is None:
        raise ValueError("No basis snapshot found for source run")

    return {
        "timestamp_utc": row[0],
        "spot_price": to_decimal(row[1]),
        "perp_mark_price": to_decimal(row[2]),
        "basis_pct": to_decimal(row[3]),
        "annualized_funding_rate_pct": to_decimal(row[4]),
        "open_interest": None if row[5] is None else to_decimal(row[5]),
    }


def evaluate_execution_scenario(context, spec):
    spot_order_notional = to_decimal(spec["spot_order_notional_usd"])
    perp_order_notional = to_decimal(spec["perp_order_notional_usd"])
    gross_notional = spot_order_notional + perp_order_notional

    if gross_notional <= 0:
        raise ValueError("gross_notional must be positive")

    spot_participation = calculate_participation_rate_pct(
        order_notional_usd=spot_order_notional,
        liquidity_notional_usd=spec["spot_liquidity_notional_usd"],
    )

    perp_participation = calculate_participation_rate_pct(
        order_notional_usd=perp_order_notional,
        liquidity_notional_usd=spec["perp_liquidity_notional_usd"],
    )

    spot_slippage_bps = estimate_slippage_bps(
        participation_rate_pct=spot_participation,
        base_slippage_bps=spec["base_slippage_bps"],
        impact_slope_bps=spec["impact_slope_bps"],
        max_participation_rate_pct=spec["max_participation_rate_pct"],
    )

    perp_slippage_bps = estimate_slippage_bps(
        participation_rate_pct=perp_participation,
        base_slippage_bps=spec["base_slippage_bps"],
        impact_slope_bps=spec["impact_slope_bps"],
        max_participation_rate_pct=spec["max_participation_rate_pct"],
    )

    spot_leg_cost_pct, spot_liquidity_penalty_pct = calculate_leg_execution_cost_pct(
        fee_bps=spec["spot_fee_bps"],
        spread_bps=spec["spot_spread_bps"],
        slippage_bps=spot_slippage_bps,
        participation_rate_pct=spot_participation,
        max_participation_rate_pct=spec["max_participation_rate_pct"],
        liquidity_penalty_multiplier=spec["liquidity_penalty_multiplier"],
    )

    perp_leg_cost_pct, perp_liquidity_penalty_pct = calculate_leg_execution_cost_pct(
        fee_bps=spec["perp_fee_bps"],
        spread_bps=spec["perp_spread_bps"],
        slippage_bps=perp_slippage_bps,
        participation_rate_pct=perp_participation,
        max_participation_rate_pct=spec["max_participation_rate_pct"],
        liquidity_penalty_multiplier=spec["liquidity_penalty_multiplier"],
    )

    spot_cost_usd = spot_order_notional * spot_leg_cost_pct / Decimal("100")
    perp_cost_usd = perp_order_notional * perp_leg_cost_pct / Decimal("100")

    combined_cost_pct = (
        spot_cost_usd + perp_cost_usd
    ) / gross_notional * Decimal("100")

    expected_funding_edge_pct = calculate_expected_funding_edge_pct(
        annualized_funding_rate_pct=context["annualized_funding_rate_pct"],
        holding_days=spec["holding_days"],
        perp_order_notional_usd=perp_order_notional,
        gross_notional_usd=gross_notional,
    )

    net_expected_edge_pct = expected_funding_edge_pct - combined_cost_pct

    edge_to_cost_ratio = safe_div(
        expected_funding_edge_pct,
        combined_cost_pct,
    )

    liquidity_penalty_pct = (
        spot_liquidity_penalty_pct * safe_div(spot_order_notional, gross_notional)
        + perp_liquidity_penalty_pct * safe_div(perp_order_notional, gross_notional)
    )

    verdict = cost_verdict(
        spot_participation_rate_pct=spot_participation,
        perp_participation_rate_pct=perp_participation,
        max_participation_rate_pct=spec["max_participation_rate_pct"],
        combined_cost_pct=combined_cost_pct,
        max_combined_cost_pct=spec["max_combined_cost_pct"],
        expected_funding_edge_pct=expected_funding_edge_pct,
        edge_to_cost_ratio=edge_to_cost_ratio,
        min_edge_to_cost_ratio=spec["min_edge_to_cost_ratio"],
        net_expected_edge_pct=net_expected_edge_pct,
        min_net_expected_edge_pct=spec["min_net_expected_edge_pct"],
    )

    return {
        "spot_price": context["spot_price"],
        "perp_mark_price": context["perp_mark_price"],
        "basis_pct": context["basis_pct"],
        "annualized_funding_rate_pct": context["annualized_funding_rate_pct"],
        "holding_days": int(spec["holding_days"]),
        "spot_order_notional_usd": spot_order_notional,
        "perp_order_notional_usd": perp_order_notional,
        "gross_notional_usd": gross_notional,
        "spot_liquidity_notional_usd": to_decimal(spec["spot_liquidity_notional_usd"]),
        "perp_liquidity_notional_usd": to_decimal(spec["perp_liquidity_notional_usd"]),
        "spot_participation_rate_pct": spot_participation,
        "perp_participation_rate_pct": perp_participation,
        "spot_fee_bps": to_decimal(spec["spot_fee_bps"]),
        "perp_fee_bps": to_decimal(spec["perp_fee_bps"]),
        "spot_spread_bps": to_decimal(spec["spot_spread_bps"]),
        "perp_spread_bps": to_decimal(spec["perp_spread_bps"]),
        "spot_slippage_bps": spot_slippage_bps,
        "perp_slippage_bps": perp_slippage_bps,
        "spot_leg_cost_pct": spot_leg_cost_pct,
        "perp_leg_cost_pct": perp_leg_cost_pct,
        "combined_cost_pct": combined_cost_pct,
        "expected_funding_edge_pct": expected_funding_edge_pct,
        "net_expected_edge_pct": net_expected_edge_pct,
        "edge_to_cost_ratio": edge_to_cost_ratio,
        "liquidity_penalty_pct": liquidity_penalty_pct,
        "final_verdict": verdict,
        "recommended_action": recommended_action(verdict),
    }


def insert_result(
    db_path,
    run_label,
    source_run_label,
    symbol,
    spec,
    result,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO execution_cost_slippage_results (
        run_label,
        source_run_label,
        symbol,
        scenario_name,
        scenario_version,
        spot_price,
        perp_mark_price,
        basis_pct,
        annualized_funding_rate_pct,
        holding_days,
        spot_order_notional_usd,
        perp_order_notional_usd,
        gross_notional_usd,
        spot_liquidity_notional_usd,
        perp_liquidity_notional_usd,
        spot_participation_rate_pct,
        perp_participation_rate_pct,
        spot_fee_bps,
        perp_fee_bps,
        spot_spread_bps,
        perp_spread_bps,
        spot_slippage_bps,
        perp_slippage_bps,
        spot_leg_cost_pct,
        perp_leg_cost_pct,
        combined_cost_pct,
        expected_funding_edge_pct,
        net_expected_edge_pct,
        edge_to_cost_ratio,
        liquidity_penalty_pct,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_run_label,
        symbol.upper(),
        spec["name"],
        spec["version"],
        format(result["spot_price"], "f"),
        format(result["perp_mark_price"], "f"),
        format(result["basis_pct"], "f"),
        format(result["annualized_funding_rate_pct"], "f"),
        result["holding_days"],
        format(result["spot_order_notional_usd"], "f"),
        format(result["perp_order_notional_usd"], "f"),
        format(result["gross_notional_usd"], "f"),
        format(result["spot_liquidity_notional_usd"], "f"),
        format(result["perp_liquidity_notional_usd"], "f"),
        format(result["spot_participation_rate_pct"], "f"),
        format(result["perp_participation_rate_pct"], "f"),
        format(result["spot_fee_bps"], "f"),
        format(result["perp_fee_bps"], "f"),
        format(result["spot_spread_bps"], "f"),
        format(result["perp_spread_bps"], "f"),
        format(result["spot_slippage_bps"], "f"),
        format(result["perp_slippage_bps"], "f"),
        format(result["spot_leg_cost_pct"], "f"),
        format(result["perp_leg_cost_pct"], "f"),
        format(result["combined_cost_pct"], "f"),
        format(result["expected_funding_edge_pct"], "f"),
        format(result["net_expected_edge_pct"], "f"),
        format(result["edge_to_cost_ratio"], "f"),
        format(result["liquidity_penalty_pct"], "f"),
        result["final_verdict"],
        result["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def insert_summary(
    db_path,
    run_label,
    source_run_label,
    symbol,
    summary,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO execution_cost_slippage_summary (
        run_label,
        source_run_label,
        symbol,
        scenarios_tested,
        go_count,
        no_go_count,
        best_result_id,
        best_scenario_version,
        best_net_expected_edge_pct,
        lowest_combined_cost_pct,
        highest_combined_cost_pct,
        global_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_run_label,
        symbol.upper(),
        summary["scenarios_tested"],
        summary["go_count"],
        summary["no_go_count"],
        summary["best_result_id"],
        summary["best_scenario_version"],
        format(summary["best_net_expected_edge_pct"], "f"),
        format(summary["lowest_combined_cost_pct"], "f"),
        format(summary["highest_combined_cost_pct"], "f"),
        summary["global_verdict"],
        summary["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def summarize_results(results):
    go_results = [
        item
        for item in results
        if item["final_verdict"] == "GO_FOR_RESEARCH"
    ]

    ranked = sorted(
        results,
        key=lambda item: (
            item["final_verdict"] == "GO_FOR_RESEARCH",
            item["net_expected_edge_pct"],
            item["edge_to_cost_ratio"],
            -item["combined_cost_pct"],
        ),
        reverse=True,
    )

    best = ranked[0] if ranked else None

    if go_results:
        global_verdict = "EXECUTION_COST_ACCEPTABLE_NO_LIVE_TRADING"
        action = "PROMOTE_TO_MULTI_SYMBOL_SCANNER"
    else:
        global_verdict = "REJECT_ALL_EXECUTION_COST_SCENARIOS_NO_LIVE_TRADING"
        action = "WAIT_FOR_EDGE_OR_COST_IMPROVEMENT"

    return {
        "scenarios_tested": len(results),
        "go_count": len(go_results),
        "no_go_count": len(results) - len(go_results),
        "best_result_id": None if best is None else best["id"],
        "best_scenario_version": None if best is None else best["scenario_version"],
        "best_net_expected_edge_pct": Decimal("0") if best is None else best["net_expected_edge_pct"],
        "lowest_combined_cost_pct": min(
            [item["combined_cost_pct"] for item in results],
            default=Decimal("0"),
        ),
        "highest_combined_cost_pct": max(
            [item["combined_cost_pct"] for item in results],
            default=Decimal("0"),
        ),
        "global_verdict": global_verdict,
        "recommended_action": action,
    }


def clean_decimal_dict(item):
    cleaned = {}

    for key, value in item.items():
        if isinstance(value, Decimal):
            cleaned[key] = format(value, "f")
        else:
            cleaned[key] = value

    return cleaned


def run_execution_cost_slippage_simulator(
    db_path,
    symbol,
    source_run_label,
    run_label,
):
    db_path = prepare_database(db_path)
    symbol = symbol.upper()

    assumptions = {
        "research_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
        "no_order_execution": True,
        "strategy_context": "long_spot_short_perp_delta_neutral",
        "symbol": symbol,
        "source_run_label": source_run_label,
        "run_label": run_label,
        "cost_model_note": "Uses configurable fee, spread, slippage, participation, and liquidity assumptions. Does not represent broker-specific live quotes.",
    }

    context = load_latest_market_context(
        db_path=db_path,
        symbol=symbol,
        source_run_label=source_run_label,
    )

    results = []

    for spec in scenario_specs():
        result = evaluate_execution_scenario(
            context=context,
            spec=spec,
        )

        row_id = insert_result(
            db_path=db_path,
            run_label=run_label,
            source_run_label=source_run_label,
            symbol=symbol,
            spec=spec,
            result=result,
            assumptions={**assumptions, "scenario": spec["version"]},
        )

        results.append({
            "id": row_id,
            "scenario_name": spec["name"],
            "scenario_version": spec["version"],
            **result,
        })

    summary = summarize_results(results)

    summary_id = insert_summary(
        db_path=db_path,
        run_label=run_label,
        source_run_label=source_run_label,
        symbol=symbol,
        summary=summary,
        assumptions=assumptions,
    )

    ranked = sorted(
        results,
        key=lambda item: (
            item["final_verdict"] == "GO_FOR_RESEARCH",
            item["net_expected_edge_pct"],
            item["edge_to_cost_ratio"],
            -item["combined_cost_pct"],
        ),
        reverse=True,
    )

    return {
        "run_label": run_label,
        "source_run_label": source_run_label,
        "symbol": symbol,
        "summary_id": summary_id,
        "scenarios_tested": len(results),
        "results_created": len(results),
        "summary_results_created": 1,
        "go_count": summary["go_count"],
        "no_go_count": summary["no_go_count"],
        "best_scenario": None if not ranked else clean_decimal_dict(ranked[0]),
        "ranked_scenarios": [
            clean_decimal_dict(item)
            for item in ranked
        ],
        "global_verdict": summary["global_verdict"],
        "recommended_action": summary["recommended_action"],
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--source-run-label", default="mission_23_funding_basis_ingestion")
    parser.add_argument("--run-label", default="mission_28_execution_cost_slippage_simulator")

    args = parser.parse_args()

    print("DeltaGrid Execution Cost + Slippage Simulator")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_execution_cost_slippage_simulator(
        db_path=args.db_path,
        symbol=args.symbol,
        source_run_label=args.source_run_label,
        run_label=args.run_label,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
