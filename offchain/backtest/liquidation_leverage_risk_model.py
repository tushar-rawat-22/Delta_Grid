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


def avg(values):
    if not values:
        return Decimal("0")

    return sum(values, Decimal("0")) / Decimal(len(values))


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS liquidation_leverage_risk_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_run_label TEXT NOT NULL,
        symbol TEXT NOT NULL,
        variant_name TEXT NOT NULL,
        variant_version TEXT NOT NULL,
        spot_price TEXT NOT NULL,
        perp_mark_price TEXT NOT NULL,
        basis_pct TEXT NOT NULL,
        leverage TEXT NOT NULL,
        maintenance_margin_rate_pct TEXT NOT NULL,
        short_liquidation_price TEXT NOT NULL,
        liquidation_buffer_pct TEXT NOT NULL,
        adverse_spot_shock_pct TEXT NOT NULL,
        adverse_basis_shock_pct TEXT NOT NULL,
        stressed_mark_price TEXT NOT NULL,
        stress_move_pct TEXT NOT NULL,
        buffer_after_stress_pct TEXT NOT NULL,
        funding_reversal_annualized_pct TEXT NOT NULL,
        holding_days INTEGER NOT NULL,
        funding_reversal_loss_pct TEXT NOT NULL,
        execution_cost_pct TEXT NOT NULL,
        total_stress_loss_pct TEXT NOT NULL,
        max_safe_leverage TEXT NOT NULL,
        final_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS liquidation_leverage_risk_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_run_label TEXT NOT NULL,
        symbol TEXT NOT NULL,
        scenarios_tested INTEGER NOT NULL,
        go_count INTEGER NOT NULL,
        no_go_count INTEGER NOT NULL,
        best_result_id INTEGER,
        best_variant_version TEXT,
        best_max_safe_leverage TEXT NOT NULL,
        worst_buffer_after_stress_pct TEXT NOT NULL,
        worst_total_stress_loss_pct TEXT NOT NULL,
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


def scenario_specs():
    return [
        {
            "name": "liq_leverage_risk",
            "version": "conservative_1_5x_spot20_basis1",
            "leverage": Decimal("1.5"),
            "maintenance_margin_rate_pct": Decimal("0.50"),
            "adverse_spot_shock_pct": Decimal("20"),
            "adverse_basis_shock_pct": Decimal("1.00"),
            "funding_reversal_annualized_pct": Decimal("10"),
            "holding_days": 30,
            "execution_cost_bps": Decimal("20"),
            "min_buffer_after_stress_pct": Decimal("5"),
            "max_total_stress_loss_pct": Decimal("5"),
        },
        {
            "name": "liq_leverage_risk",
            "version": "balanced_2x_spot25_basis1_5",
            "leverage": Decimal("2"),
            "maintenance_margin_rate_pct": Decimal("0.50"),
            "adverse_spot_shock_pct": Decimal("25"),
            "adverse_basis_shock_pct": Decimal("1.50"),
            "funding_reversal_annualized_pct": Decimal("15"),
            "holding_days": 30,
            "execution_cost_bps": Decimal("20"),
            "min_buffer_after_stress_pct": Decimal("5"),
            "max_total_stress_loss_pct": Decimal("7"),
        },
        {
            "name": "liq_leverage_risk",
            "version": "aggressive_3x_spot30_basis2",
            "leverage": Decimal("3"),
            "maintenance_margin_rate_pct": Decimal("0.50"),
            "adverse_spot_shock_pct": Decimal("30"),
            "adverse_basis_shock_pct": Decimal("2.00"),
            "funding_reversal_annualized_pct": Decimal("20"),
            "holding_days": 30,
            "execution_cost_bps": Decimal("20"),
            "min_buffer_after_stress_pct": Decimal("5"),
            "max_total_stress_loss_pct": Decimal("10"),
        },
    ]


def bps_to_pct(bps):
    return to_decimal(bps) / Decimal("100")


def calculate_short_liquidation_price(entry_mark_price, leverage, maintenance_margin_rate_pct):
    entry_mark_price = to_decimal(entry_mark_price)
    leverage = to_decimal(leverage)
    maintenance_margin_rate_pct = to_decimal(maintenance_margin_rate_pct)

    if entry_mark_price <= 0:
        raise ValueError("entry_mark_price must be positive")

    if leverage <= 0:
        raise ValueError("leverage must be positive")

    liquidation_buffer_pct = Decimal("100") / leverage - maintenance_margin_rate_pct

    if liquidation_buffer_pct <= 0:
        raise ValueError("leverage too high for maintenance margin")

    liquidation_price = entry_mark_price * (
        Decimal("1") + liquidation_buffer_pct / Decimal("100")
    )

    return liquidation_price, liquidation_buffer_pct


def calculate_stressed_mark_price(
    entry_mark_price,
    adverse_spot_shock_pct,
    adverse_basis_shock_pct,
):
    entry_mark_price = to_decimal(entry_mark_price)
    adverse_spot_shock_pct = to_decimal(adverse_spot_shock_pct)
    adverse_basis_shock_pct = to_decimal(adverse_basis_shock_pct)

    if entry_mark_price <= 0:
        raise ValueError("entry_mark_price must be positive")

    stress_move_pct = adverse_spot_shock_pct + adverse_basis_shock_pct

    stressed_mark_price = entry_mark_price * (
        Decimal("1") + stress_move_pct / Decimal("100")
    )

    return stressed_mark_price, stress_move_pct


def calculate_buffer_after_stress_pct(short_liquidation_price, stressed_mark_price):
    short_liquidation_price = to_decimal(short_liquidation_price)
    stressed_mark_price = to_decimal(stressed_mark_price)

    if stressed_mark_price <= 0:
        raise ValueError("stressed_mark_price must be positive")

    return (
        short_liquidation_price - stressed_mark_price
    ) / stressed_mark_price * Decimal("100")


def calculate_funding_reversal_loss_pct(funding_reversal_annualized_pct, holding_days):
    funding_reversal_annualized_pct = abs(to_decimal(funding_reversal_annualized_pct))

    return funding_reversal_annualized_pct * Decimal(holding_days) / Decimal("365")


def calculate_total_stress_loss_pct(
    adverse_basis_shock_pct,
    funding_reversal_loss_pct,
    execution_cost_pct,
):
    adverse_basis_shock_pct = max(to_decimal(adverse_basis_shock_pct), Decimal("0"))

    return (
        adverse_basis_shock_pct
        + to_decimal(funding_reversal_loss_pct)
        + to_decimal(execution_cost_pct)
    )


def calculate_max_safe_leverage(
    maintenance_margin_rate_pct,
    adverse_spot_shock_pct,
    adverse_basis_shock_pct,
    required_buffer_after_stress_pct,
):
    maintenance_margin_rate_pct = to_decimal(maintenance_margin_rate_pct)
    adverse_spot_shock_pct = to_decimal(adverse_spot_shock_pct)
    adverse_basis_shock_pct = to_decimal(adverse_basis_shock_pct)
    required_buffer_after_stress_pct = to_decimal(required_buffer_after_stress_pct)

    stress_move_pct = adverse_spot_shock_pct + adverse_basis_shock_pct

    required_liquidation_buffer_pct = (
        (
            Decimal("1") + stress_move_pct / Decimal("100")
        )
        * (
            Decimal("1") + required_buffer_after_stress_pct / Decimal("100")
        )
        - Decimal("1")
    ) * Decimal("100")

    denominator = maintenance_margin_rate_pct + required_liquidation_buffer_pct

    if denominator <= 0:
        return Decimal("999")

    return Decimal("100") / denominator


def risk_verdict(
    liquidation_hit,
    leverage,
    max_safe_leverage,
    buffer_after_stress_pct,
    min_buffer_after_stress_pct,
    total_stress_loss_pct,
    max_total_stress_loss_pct,
):
    if liquidation_hit:
        return "NO_GO_LIQUIDATION_HIT"

    if leverage > max_safe_leverage:
        return "NO_GO_LEVERAGE_TOO_HIGH"

    if buffer_after_stress_pct < min_buffer_after_stress_pct:
        return "NO_GO_BUFFER_TOO_SMALL"

    if total_stress_loss_pct > max_total_stress_loss_pct:
        return "NO_GO_STRESS_LOSS_TOO_HIGH"

    return "GO_FOR_RESEARCH"


def recommended_action(verdict):
    if verdict == "GO_FOR_RESEARCH":
        return "PROMOTE_TO_FUNDING_RISK_INTEGRATION"

    if verdict == "NO_GO_LIQUIDATION_HIT":
        return "LOWER_LEVERAGE_IMMEDIATELY"

    if verdict == "NO_GO_LEVERAGE_TOO_HIGH":
        return "REDUCE_TO_MAX_SAFE_LEVERAGE"

    if verdict == "NO_GO_BUFFER_TOO_SMALL":
        return "INCREASE_MARGIN_BUFFER"

    if verdict == "NO_GO_STRESS_LOSS_TOO_HIGH":
        return "REDUCE_BASIS_AND_FUNDING_REVERSAL_EXPOSURE"

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


def evaluate_liquidation_scenario(context, spec):
    short_liquidation_price, liquidation_buffer_pct = calculate_short_liquidation_price(
        entry_mark_price=context["perp_mark_price"],
        leverage=spec["leverage"],
        maintenance_margin_rate_pct=spec["maintenance_margin_rate_pct"],
    )

    stressed_mark_price, stress_move_pct = calculate_stressed_mark_price(
        entry_mark_price=context["perp_mark_price"],
        adverse_spot_shock_pct=spec["adverse_spot_shock_pct"],
        adverse_basis_shock_pct=spec["adverse_basis_shock_pct"],
    )

    buffer_after_stress_pct = calculate_buffer_after_stress_pct(
        short_liquidation_price=short_liquidation_price,
        stressed_mark_price=stressed_mark_price,
    )

    funding_reversal_loss_pct = calculate_funding_reversal_loss_pct(
        funding_reversal_annualized_pct=spec["funding_reversal_annualized_pct"],
        holding_days=spec["holding_days"],
    )

    execution_cost_pct = bps_to_pct(spec["execution_cost_bps"])

    total_stress_loss_pct = calculate_total_stress_loss_pct(
        adverse_basis_shock_pct=spec["adverse_basis_shock_pct"],
        funding_reversal_loss_pct=funding_reversal_loss_pct,
        execution_cost_pct=execution_cost_pct,
    )

    max_safe_leverage = calculate_max_safe_leverage(
        maintenance_margin_rate_pct=spec["maintenance_margin_rate_pct"],
        adverse_spot_shock_pct=spec["adverse_spot_shock_pct"],
        adverse_basis_shock_pct=spec["adverse_basis_shock_pct"],
        required_buffer_after_stress_pct=spec["min_buffer_after_stress_pct"],
    )

    liquidation_hit = stressed_mark_price >= short_liquidation_price

    verdict = risk_verdict(
        liquidation_hit=liquidation_hit,
        leverage=spec["leverage"],
        max_safe_leverage=max_safe_leverage,
        buffer_after_stress_pct=buffer_after_stress_pct,
        min_buffer_after_stress_pct=spec["min_buffer_after_stress_pct"],
        total_stress_loss_pct=total_stress_loss_pct,
        max_total_stress_loss_pct=spec["max_total_stress_loss_pct"],
    )

    return {
        "spot_price": context["spot_price"],
        "perp_mark_price": context["perp_mark_price"],
        "basis_pct": context["basis_pct"],
        "leverage": spec["leverage"],
        "maintenance_margin_rate_pct": spec["maintenance_margin_rate_pct"],
        "short_liquidation_price": short_liquidation_price,
        "liquidation_buffer_pct": liquidation_buffer_pct,
        "adverse_spot_shock_pct": spec["adverse_spot_shock_pct"],
        "adverse_basis_shock_pct": spec["adverse_basis_shock_pct"],
        "stressed_mark_price": stressed_mark_price,
        "stress_move_pct": stress_move_pct,
        "buffer_after_stress_pct": buffer_after_stress_pct,
        "funding_reversal_annualized_pct": spec["funding_reversal_annualized_pct"],
        "holding_days": spec["holding_days"],
        "funding_reversal_loss_pct": funding_reversal_loss_pct,
        "execution_cost_pct": execution_cost_pct,
        "total_stress_loss_pct": total_stress_loss_pct,
        "max_safe_leverage": max_safe_leverage,
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
    INSERT INTO liquidation_leverage_risk_results (
        run_label,
        source_run_label,
        symbol,
        variant_name,
        variant_version,
        spot_price,
        perp_mark_price,
        basis_pct,
        leverage,
        maintenance_margin_rate_pct,
        short_liquidation_price,
        liquidation_buffer_pct,
        adverse_spot_shock_pct,
        adverse_basis_shock_pct,
        stressed_mark_price,
        stress_move_pct,
        buffer_after_stress_pct,
        funding_reversal_annualized_pct,
        holding_days,
        funding_reversal_loss_pct,
        execution_cost_pct,
        total_stress_loss_pct,
        max_safe_leverage,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_run_label,
        symbol.upper(),
        spec["name"],
        spec["version"],
        format(result["spot_price"], "f"),
        format(result["perp_mark_price"], "f"),
        format(result["basis_pct"], "f"),
        format(result["leverage"], "f"),
        format(result["maintenance_margin_rate_pct"], "f"),
        format(result["short_liquidation_price"], "f"),
        format(result["liquidation_buffer_pct"], "f"),
        format(result["adverse_spot_shock_pct"], "f"),
        format(result["adverse_basis_shock_pct"], "f"),
        format(result["stressed_mark_price"], "f"),
        format(result["stress_move_pct"], "f"),
        format(result["buffer_after_stress_pct"], "f"),
        format(result["funding_reversal_annualized_pct"], "f"),
        int(result["holding_days"]),
        format(result["funding_reversal_loss_pct"], "f"),
        format(result["execution_cost_pct"], "f"),
        format(result["total_stress_loss_pct"], "f"),
        format(result["max_safe_leverage"], "f"),
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
    INSERT INTO liquidation_leverage_risk_summary (
        run_label,
        source_run_label,
        symbol,
        scenarios_tested,
        go_count,
        no_go_count,
        best_result_id,
        best_variant_version,
        best_max_safe_leverage,
        worst_buffer_after_stress_pct,
        worst_total_stress_loss_pct,
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
        summary["best_variant_version"],
        format(summary["best_max_safe_leverage"], "f"),
        format(summary["worst_buffer_after_stress_pct"], "f"),
        format(summary["worst_total_stress_loss_pct"], "f"),
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

    no_go_count = len(results) - len(go_results)

    ranked = sorted(
        results,
        key=lambda item: (
            item["final_verdict"] == "GO_FOR_RESEARCH",
            item["buffer_after_stress_pct"],
            item["max_safe_leverage"],
        ),
        reverse=True,
    )

    best = ranked[0] if ranked else None

    if go_results:
        global_verdict = "LIQUIDATION_LEVERAGE_RISK_ACCEPTABLE_NO_LIVE_TRADING"
        action = "PROMOTE_TO_FUNDING_RISK_INTEGRATION"
    else:
        global_verdict = "REJECT_ALL_LEVERAGE_SCENARIOS_NO_LIVE_TRADING"
        action = "LOWER_LEVERAGE_AND_REWORK_RISK_ASSUMPTIONS"

    return {
        "scenarios_tested": len(results),
        "go_count": len(go_results),
        "no_go_count": no_go_count,
        "best_result_id": None if best is None else best["id"],
        "best_variant_version": None if best is None else best["variant_version"],
        "best_max_safe_leverage": Decimal("0") if best is None else best["max_safe_leverage"],
        "worst_buffer_after_stress_pct": min(
            [item["buffer_after_stress_pct"] for item in results],
            default=Decimal("0"),
        ),
        "worst_total_stress_loss_pct": max(
            [item["total_stress_loss_pct"] for item in results],
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


def run_liquidation_leverage_risk_model(
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
    }

    context = load_latest_market_context(
        db_path=db_path,
        symbol=symbol,
        source_run_label=source_run_label,
    )

    results = []

    for spec in scenario_specs():
        result = evaluate_liquidation_scenario(
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
            assumptions={**assumptions, "variant": spec["version"]},
        )

        results.append({
            "id": row_id,
            "variant_name": spec["name"],
            "variant_version": spec["version"],
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
            item["buffer_after_stress_pct"],
            item["max_safe_leverage"],
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
        "best_variant": None if not ranked else clean_decimal_dict(ranked[0]),
        "ranked_variants": [
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
    parser.add_argument("--run-label", default="mission_27_liquidation_leverage_risk_model")

    args = parser.parse_args()

    print("DeltaGrid Liquidation + Leverage Risk Model")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_liquidation_leverage_risk_model(
        db_path=args.db_path,
        symbol=args.symbol,
        source_run_label=args.source_run_label,
        run_label=args.run_label,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
