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

from backtest.strategy_candidate_lab import resolve_db_path
from backtest.walk_forward_candidate_lab import ensure_schema as ensure_walk_forward_schema


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS strategy_failure_diagnostics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        source TEXT NOT NULL,
        source_run_label TEXT NOT NULL,
        diagnostic_run_label TEXT NOT NULL,
        candidate_name TEXT NOT NULL,
        candidate_version TEXT NOT NULL,
        primary_failure TEXT NOT NULL,
        failure_reasons_json TEXT NOT NULL,
        go_splits INTEGER NOT NULL,
        splits_tested INTEGER NOT NULL,
        worst_drawdown_pct TEXT NOT NULL,
        avg_sharpe_ratio TEXT NOT NULL,
        avg_excess_return_pct TEXT NOT NULL,
        avg_profit_factor TEXT NOT NULL,
        total_trades INTEGER NOT NULL,
        severity_score TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def to_decimal(value):
    if value is None:
        return Decimal("0")

    return Decimal(str(value))


def diagnose_candidate(row, min_pass_ratio):
    splits_tested = int(row["splits_tested"])
    go_splits = int(row["go_splits"])
    rejected_splits = int(row["rejected_or_insufficient_splits"])
    worst_drawdown = to_decimal(row["worst_drawdown_pct"])
    avg_sharpe = to_decimal(row["avg_sharpe_ratio"])
    avg_excess = to_decimal(row["avg_excess_return_pct"])
    avg_profit_factor = to_decimal(row["avg_profit_factor"])
    total_trades = int(row["total_trades"])
    final_verdict = row["final_verdict"]

    pass_ratio = Decimal(go_splits) / Decimal(splits_tested) if splits_tested else Decimal("0")

    reasons = []

    if final_verdict != "GO_FOR_RESEARCH":
        reasons.append({
            "code": "FINAL_VERDICT_NOT_APPROVED",
            "detail": final_verdict,
            "severity": 25,
        })

    if pass_ratio < min_pass_ratio:
        reasons.append({
            "code": "WEAK_WALK_FORWARD_STABILITY",
            "detail": f"go_splits={go_splits}, splits_tested={splits_tested}",
            "severity": 35,
        })

    if worst_drawdown > Decimal("30"):
        reasons.append({
            "code": "DRAWDOWN_TOO_HIGH",
            "detail": f"worst_drawdown_pct={worst_drawdown}",
            "severity": 30,
        })

    if avg_sharpe < Decimal("0.75"):
        reasons.append({
            "code": "WEAK_RISK_ADJUSTED_RETURN",
            "detail": f"avg_sharpe_ratio={avg_sharpe}",
            "severity": 25,
        })

    if avg_excess <= Decimal("0"):
        reasons.append({
            "code": "UNDERPERFORMS_BENCHMARK",
            "detail": f"avg_excess_return_pct={avg_excess}",
            "severity": 25,
        })

    if avg_profit_factor < Decimal("1.30"):
        reasons.append({
            "code": "WEAK_PROFIT_FACTOR",
            "detail": f"avg_profit_factor={avg_profit_factor}",
            "severity": 15,
        })

    if total_trades < 10:
        reasons.append({
            "code": "INSUFFICIENT_TRADE_SAMPLE",
            "detail": f"total_trades={total_trades}",
            "severity": 20,
        })

    if avg_profit_factor > Decimal("100") and total_trades < 15:
        reasons.append({
            "code": "DISTORTED_PROFIT_FACTOR_LOW_SAMPLE",
            "detail": f"avg_profit_factor={avg_profit_factor}, total_trades={total_trades}",
            "severity": 20,
        })

    if rejected_splits > 0:
        reasons.append({
            "code": "SPLIT_REJECTION_CLUSTER",
            "detail": f"rejected_or_insufficient_splits={rejected_splits}",
            "severity": 10,
        })

    primary_failure = max(reasons, key=lambda item: item["severity"])["code"]
    severity_score = sum(Decimal(str(item["severity"])) for item in reasons)

    if primary_failure == "WEAK_WALK_FORWARD_STABILITY":
        action = "REWORK_FOR_STABILITY"
    elif primary_failure == "DRAWDOWN_TOO_HIGH":
        action = "ADD_STRONGER_RISK_CONTROLS"
    elif primary_failure == "UNDERPERFORMS_BENCHMARK":
        action = "REJECT_OR_REDESIGN_ALPHA"
    elif primary_failure == "INSUFFICIENT_TRADE_SAMPLE":
        action = "COLLECT_MORE_DATA_OR_CHANGE_TIMEFRAME"
    else:
        action = "REJECT_FOR_NOW"

    return {
        "primary_failure": primary_failure,
        "failure_reasons": reasons,
        "severity_score": severity_score,
        "recommended_action": action,
    }


def load_walk_forward_summaries(db_path, symbol, timeframe, source, source_run_label):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        chain_id,
        symbol,
        timeframe,
        source,
        run_label,
        candidate_name,
        candidate_version,
        splits_tested,
        go_splits,
        rejected_or_insufficient_splits,
        avg_net_return_pct,
        avg_excess_return_pct,
        worst_drawdown_pct,
        avg_sharpe_ratio,
        avg_profit_factor,
        total_trades,
        stability_score,
        final_verdict
    FROM walk_forward_candidate_summary
    WHERE symbol = ?
    AND timeframe = ?
    AND source = ?
    AND run_label = ?
    ORDER BY CAST(stability_score AS REAL) DESC
    """, (
        symbol.upper(),
        timeframe,
        source,
        source_run_label,
    )).fetchall()

    conn.close()

    return rows


def insert_diagnostic(db_path, row, diagnostic_run_label, diagnostic):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO strategy_failure_diagnostics (
        chain_id,
        symbol,
        timeframe,
        source,
        source_run_label,
        diagnostic_run_label,
        candidate_name,
        candidate_version,
        primary_failure,
        failure_reasons_json,
        go_splits,
        splits_tested,
        worst_drawdown_pct,
        avg_sharpe_ratio,
        avg_excess_return_pct,
        avg_profit_factor,
        total_trades,
        severity_score,
        recommended_action,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row["chain_id"],
        row["symbol"],
        row["timeframe"],
        row["source"],
        row["run_label"],
        diagnostic_run_label,
        row["candidate_name"],
        row["candidate_version"],
        diagnostic["primary_failure"],
        json.dumps(diagnostic["failure_reasons"]),
        int(row["go_splits"]),
        int(row["splits_tested"]),
        row["worst_drawdown_pct"],
        row["avg_sharpe_ratio"],
        row["avg_excess_return_pct"],
        row["avg_profit_factor"],
        int(row["total_trades"]),
        format(diagnostic["severity_score"], "f"),
        diagnostic["recommended_action"],
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def run_strategy_diagnostics(
    db_path,
    symbol,
    timeframe,
    source,
    source_run_label,
    diagnostic_run_label,
    min_pass_ratio,
):
    db_path = resolve_db_path(db_path)

    init_market_database(db_path)
    ensure_walk_forward_schema(db_path)
    ensure_schema(db_path)

    rows = load_walk_forward_summaries(
        db_path,
        symbol,
        timeframe,
        source,
        source_run_label,
    )

    if not rows:
        raise ValueError("No walk-forward summaries found for diagnostics")

    diagnostics = []

    for row in rows:
        diagnostic = diagnose_candidate(row, min_pass_ratio)
        row_id = insert_diagnostic(db_path, row, diagnostic_run_label, diagnostic)

        diagnostics.append({
            "id": row_id,
            "candidate_name": row["candidate_name"],
            "candidate_version": row["candidate_version"],
            "primary_failure": diagnostic["primary_failure"],
            "severity_score": format(diagnostic["severity_score"], "f"),
            "recommended_action": diagnostic["recommended_action"],
            "failure_reason_count": len(diagnostic["failure_reasons"]),
        })

    failure_counts = {}

    for item in diagnostics:
        key = item["primary_failure"]
        failure_counts[key] = failure_counts.get(key, 0) + 1

    ranked = sorted(
        diagnostics,
        key=lambda item: Decimal(item["severity_score"]),
        reverse=True,
    )

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "source": source,
        "source_run_label": source_run_label,
        "diagnostic_run_label": diagnostic_run_label,
        "candidates_diagnosed": len(diagnostics),
        "failure_counts": failure_counts,
        "highest_severity": ranked[0],
        "diagnostics": ranked,
        "global_verdict": "DIAGNOSE_ONLY_NO_LIVE_TRADING",
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--source", default="binance_spot")
    parser.add_argument("--source-run-label", default="mission_17_walk_forward_candidate_lab")
    parser.add_argument("--diagnostic-run-label", default="mission_18_strategy_diagnostics")
    parser.add_argument("--min-pass-ratio", default="0.60")

    args = parser.parse_args()

    print("DeltaGrid Strategy Diagnostics")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_strategy_diagnostics(
        db_path=args.db_path,
        symbol=args.symbol,
        timeframe=args.timeframe,
        source=args.source,
        source_run_label=args.source_run_label,
        diagnostic_run_label=args.diagnostic_run_label,
        min_pass_ratio=Decimal(args.min_pass_ratio),
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
