import json
import os
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]
if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from risk.risk_engine import RiskLimits, TradeSimulation, evaluate_trade


load_dotenv("config/.env")

DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS simulation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp_utc TEXT NOT NULL,
        gross_profit_wei INTEGER NOT NULL,
        gas_cost_wei INTEGER NOT NULL,
        flash_fee_wei INTEGER NOT NULL,
        slippage_cost_wei INTEGER NOT NULL,
        slippage_bps INTEGER NOT NULL,
        estimated_success_bps INTEGER NOT NULL,
        total_cost_wei INTEGER NOT NULL,
        net_profit_wei INTEGER NOT NULL,
        risk_score INTEGER NOT NULL,
        approved INTEGER NOT NULL,
        reasons_json TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def log_simulation(trade: TradeSimulation, decision) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO simulation_logs (
        timestamp_utc,
        gross_profit_wei,
        gas_cost_wei,
        flash_fee_wei,
        slippage_cost_wei,
        slippage_bps,
        estimated_success_bps,
        total_cost_wei,
        net_profit_wei,
        risk_score,
        approved,
        reasons_json
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now_utc(),
        trade.gross_profit_wei,
        trade.gas_cost_wei,
        trade.flash_fee_wei,
        trade.slippage_cost_wei,
        trade.slippage_bps,
        trade.estimated_success_bps,
        decision.total_cost_wei,
        decision.net_profit_wei,
        decision.score,
        1 if decision.approved else 0,
        json.dumps(decision.reasons),
    ))

    conn.commit()
    conn.close()


def run_case(name: str, trade: TradeSimulation, limits: RiskLimits) -> None:
    decision = evaluate_trade(trade, limits)
    log_simulation(trade, decision)

    print("=" * 70)
    print(f"Case: {name}")
    print(f"Gross Profit Wei: {trade.gross_profit_wei}")
    print(f"Gas Cost Wei: {trade.gas_cost_wei}")
    print(f"Flash Fee Wei: {trade.flash_fee_wei}")
    print(f"Slippage Cost Wei: {trade.slippage_cost_wei}")
    print(f"Total Cost Wei: {decision.total_cost_wei}")
    print(f"Net Profit Wei: {decision.net_profit_wei}")
    print(f"Risk Score: {decision.score}")
    print(f"Approved: {decision.approved}")

    if decision.reasons:
        print("Reject Reasons:")
        for reason in decision.reasons:
            print(f"- {reason}")
    else:
        print("Reject Reasons: none")


def main() -> None:
    print("DeltaGrid Local Profit Simulator")
    print("Mode: local simulation only")
    print("No private keys. No signing. No real trades.")
    print(f"DB_PATH: {DB_PATH}")

    init_db()

    limits = RiskLimits(
        min_net_profit_wei=1_000_000_000_000_000,
        max_slippage_bps=50,
        max_gas_to_gross_bps=3_000,
        min_success_bps=8_500,
        min_score=70,
    )

    safe_trade = TradeSimulation(
        gross_profit_wei=5_000_000_000_000_000,
        gas_cost_wei=1_000_000_000_000_000,
        flash_fee_wei=500_000_000_000_000,
        slippage_cost_wei=500_000_000_000_000,
        slippage_bps=20,
        estimated_success_bps=9_500,
    )

    bad_cost_trade = TradeSimulation(
        gross_profit_wei=2_000_000_000_000_000,
        gas_cost_wei=1_500_000_000_000_000,
        flash_fee_wei=400_000_000_000_000,
        slippage_cost_wei=300_000_000_000_000,
        slippage_bps=30,
        estimated_success_bps=9_000,
    )

    high_slippage_trade = TradeSimulation(
        gross_profit_wei=6_000_000_000_000_000,
        gas_cost_wei=1_000_000_000_000_000,
        flash_fee_wei=400_000_000_000_000,
        slippage_cost_wei=2_000_000_000_000_000,
        slippage_bps=120,
        estimated_success_bps=9_200,
    )

    low_confidence_trade = TradeSimulation(
        gross_profit_wei=8_000_000_000_000_000,
        gas_cost_wei=1_000_000_000_000_000,
        flash_fee_wei=500_000_000_000_000,
        slippage_cost_wei=500_000_000_000_000,
        slippage_bps=25,
        estimated_success_bps=6_500,
    )

    run_case("safe_trade", safe_trade, limits)
    run_case("bad_cost_trade", bad_cost_trade, limits)
    run_case("high_slippage_trade", high_slippage_trade, limits)
    run_case("low_confidence_trade", low_confidence_trade, limits)


if __name__ == "__main__":
    main()
