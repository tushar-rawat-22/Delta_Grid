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


def percent_ratio(part, total):
    if total == 0:
        return Decimal("0")

    return Decimal(part) / Decimal(total) * Decimal("100")


def bps_to_pct(bps):
    return to_decimal(bps) / Decimal("100")


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS delta_neutral_funding_lab_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_run_label TEXT NOT NULL,
        symbol TEXT NOT NULL,
        funding_observations INTEGER NOT NULL,
        avg_funding_rate TEXT NOT NULL,
        avg_annualized_rate_pct TEXT NOT NULL,
        latest_funding_rate TEXT NOT NULL,
        latest_annualized_rate_pct TEXT NOT NULL,
        min_annualized_rate_pct TEXT NOT NULL,
        max_annualized_rate_pct TEXT NOT NULL,
        positive_funding_ratio_pct TEXT NOT NULL,
        basis_pct TEXT NOT NULL,
        basis_penalty_pct TEXT NOT NULL,
        open_interest TEXT,
        execution_cost_pct TEXT NOT NULL,
        expected_edge_pct TEXT NOT NULL,
        stress_edge_pct TEXT NOT NULL,
        estimated_carry_30d_pct TEXT NOT NULL,
        final_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS delta_neutral_funding_lab_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_run_label TEXT NOT NULL,
        symbol TEXT NOT NULL,
        results_created INTEGER NOT NULL,
        go_count INTEGER NOT NULL,
        no_go_count INTEGER NOT NULL,
        best_result_id INTEGER,
        best_expected_edge_pct TEXT NOT NULL,
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


def load_funding_rows(db_path, symbol, source_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        funding_time_utc,
        funding_rate,
        annualized_rate_pct
    FROM funding_rates
    WHERE symbol = ?
    AND source = ?
    ORDER BY funding_time_utc ASC
    """, (
        symbol.upper(),
        source_run_label,
    )).fetchall()

    conn.close()

    return [
        {
            "funding_time_utc": row[0],
            "funding_rate": to_decimal(row[1]),
            "annualized_rate_pct": to_decimal(row[2]),
        }
        for row in rows
    ]


def load_latest_basis_snapshot(db_path, symbol, source_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    row = cur.execute("""
    SELECT
        timestamp_utc,
        basis_pct,
        annualized_funding_rate_pct,
        open_interest,
        verdict
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
        return None

    return {
        "timestamp_utc": row[0],
        "basis_pct": to_decimal(row[1]),
        "annualized_funding_rate_pct": to_decimal(row[2]),
        "open_interest": None if row[3] is None else to_decimal(row[3]),
        "basis_verdict": row[4],
    }


def funding_statistics(funding_rows):
    if not funding_rows:
        raise ValueError("No funding rows available")

    funding_rates = [
        row["funding_rate"]
        for row in funding_rows
    ]

    annualized_rates = [
        row["annualized_rate_pct"]
        for row in funding_rows
    ]

    positive_count = sum(
        1
        for rate in funding_rates
        if rate > 0
    )

    return {
        "funding_observations": len(funding_rows),
        "avg_funding_rate": avg(funding_rates),
        "avg_annualized_rate_pct": avg(annualized_rates),
        "latest_funding_rate": funding_rates[-1],
        "latest_annualized_rate_pct": annualized_rates[-1],
        "min_annualized_rate_pct": min(annualized_rates),
        "max_annualized_rate_pct": max(annualized_rates),
        "positive_funding_ratio_pct": percent_ratio(
            positive_count,
            len(funding_rows),
        ),
    }


def calculate_basis_penalty_pct(basis_value_pct, basis_penalty_factor):
    basis_value_pct = to_decimal(basis_value_pct)
    basis_penalty_factor = to_decimal(basis_penalty_factor)

    return abs(basis_value_pct) * basis_penalty_factor


def calculate_edges(
    avg_annualized_rate_pct,
    min_annualized_rate_pct,
    basis_penalty_pct,
    execution_cost_pct,
):
    expected_edge_pct = (
        avg_annualized_rate_pct
        - basis_penalty_pct
        - execution_cost_pct
    )

    stress_edge_pct = (
        min_annualized_rate_pct
        - basis_penalty_pct
        - execution_cost_pct
    )

    estimated_carry_30d_pct = (
        expected_edge_pct
        * Decimal("30")
        / Decimal("365")
    )

    return {
        "expected_edge_pct": expected_edge_pct,
        "stress_edge_pct": stress_edge_pct,
        "estimated_carry_30d_pct": estimated_carry_30d_pct,
    }


def final_verdict(
    funding_observations,
    avg_annualized_rate_pct,
    latest_annualized_rate_pct,
    min_annualized_rate_pct,
    positive_funding_ratio_pct,
    basis_value_pct,
    open_interest,
    expected_edge_pct,
    stress_edge_pct,
    min_observations,
    min_avg_annualized_pct,
    min_latest_annualized_pct,
    min_positive_ratio_pct,
    min_basis_pct,
    max_basis_pct,
    min_expected_edge_pct,
    min_stress_edge_pct,
):
    if funding_observations < min_observations:
        return "INSUFFICIENT_FUNDING_HISTORY"

    if open_interest is None or open_interest <= 0:
        return "NO_GO_MISSING_OPEN_INTEREST"

    if avg_annualized_rate_pct < min_avg_annualized_pct:
        return "NO_GO_LOW_AVG_FUNDING"

    if latest_annualized_rate_pct < min_latest_annualized_pct:
        return "NO_GO_LOW_CURRENT_FUNDING"

    if min_annualized_rate_pct < Decimal("0"):
        return "NO_GO_NEGATIVE_FUNDING_IN_SAMPLE"

    if positive_funding_ratio_pct < min_positive_ratio_pct:
        return "NO_GO_UNSTABLE_FUNDING"

    if basis_value_pct < min_basis_pct or basis_value_pct > max_basis_pct:
        return "NO_GO_BASIS_OUT_OF_RANGE"

    if expected_edge_pct < min_expected_edge_pct:
        return "NO_GO_EDGE_TOO_LOW"

    if stress_edge_pct < min_stress_edge_pct:
        return "NO_GO_NEGATIVE_STRESS_EDGE"

    return "GO_FOR_RESEARCH"


def recommended_action(verdict):
    if verdict == "GO_FOR_RESEARCH":
        return "PROMOTE_TO_DEEP_DELTA_NEUTRAL_BACKTEST"

    if verdict == "INSUFFICIENT_FUNDING_HISTORY":
        return "COLLECT_MORE_FUNDING_HISTORY"

    if verdict == "NO_GO_MISSING_OPEN_INTEREST":
        return "FIX_OPEN_INTEREST_INGESTION"

    if verdict == "NO_GO_LOW_AVG_FUNDING":
        return "WAIT_FOR_HIGHER_AVERAGE_FUNDING"

    if verdict == "NO_GO_LOW_CURRENT_FUNDING":
        return "IGNORE_UNTIL_FUNDING_EXPANDS"

    if verdict == "NO_GO_NEGATIVE_FUNDING_IN_SAMPLE":
        return "REJECT_UNSTABLE_CARRY"

    if verdict == "NO_GO_UNSTABLE_FUNDING":
        return "WAIT_FOR_STABLE_POSITIVE_FUNDING"

    if verdict == "NO_GO_BASIS_OUT_OF_RANGE":
        return "WAIT_FOR_BASIS_NORMALIZATION"

    if verdict == "NO_GO_EDGE_TOO_LOW":
        return "REJECT_WEAK_EDGE"

    if verdict == "NO_GO_NEGATIVE_STRESS_EDGE":
        return "REJECT_BAD_STRESS_CASE"

    return "OBSERVE_ONLY"


def build_lab_result(
    funding_rows,
    basis_snapshot,
    execution_cost_bps,
    basis_penalty_factor,
    min_observations,
    min_avg_annualized_pct,
    min_latest_annualized_pct,
    min_positive_ratio_pct,
    min_basis_pct,
    max_basis_pct,
    min_expected_edge_pct,
    min_stress_edge_pct,
):
    if basis_snapshot is None:
        raise ValueError("No basis snapshot available")

    stats = funding_statistics(funding_rows)

    execution_cost_pct = bps_to_pct(execution_cost_bps)

    basis_penalty = calculate_basis_penalty_pct(
        basis_snapshot["basis_pct"],
        basis_penalty_factor,
    )

    edges = calculate_edges(
        avg_annualized_rate_pct=stats["avg_annualized_rate_pct"],
        min_annualized_rate_pct=stats["min_annualized_rate_pct"],
        basis_penalty_pct=basis_penalty,
        execution_cost_pct=execution_cost_pct,
    )

    verdict = final_verdict(
        funding_observations=stats["funding_observations"],
        avg_annualized_rate_pct=stats["avg_annualized_rate_pct"],
        latest_annualized_rate_pct=stats["latest_annualized_rate_pct"],
        min_annualized_rate_pct=stats["min_annualized_rate_pct"],
        positive_funding_ratio_pct=stats["positive_funding_ratio_pct"],
        basis_value_pct=basis_snapshot["basis_pct"],
        open_interest=basis_snapshot["open_interest"],
        expected_edge_pct=edges["expected_edge_pct"],
        stress_edge_pct=edges["stress_edge_pct"],
        min_observations=min_observations,
        min_avg_annualized_pct=min_avg_annualized_pct,
        min_latest_annualized_pct=min_latest_annualized_pct,
        min_positive_ratio_pct=min_positive_ratio_pct,
        min_basis_pct=min_basis_pct,
        max_basis_pct=max_basis_pct,
        min_expected_edge_pct=min_expected_edge_pct,
        min_stress_edge_pct=min_stress_edge_pct,
    )

    return {
        **stats,
        "basis_pct": basis_snapshot["basis_pct"],
        "basis_penalty_pct": basis_penalty,
        "open_interest": basis_snapshot["open_interest"],
        "execution_cost_pct": execution_cost_pct,
        "expected_edge_pct": edges["expected_edge_pct"],
        "stress_edge_pct": edges["stress_edge_pct"],
        "estimated_carry_30d_pct": edges["estimated_carry_30d_pct"],
        "final_verdict": verdict,
        "recommended_action": recommended_action(verdict),
    }


def insert_lab_result(
    db_path,
    run_label,
    source_run_label,
    symbol,
    result,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO delta_neutral_funding_lab_results (
        run_label,
        source_run_label,
        symbol,
        funding_observations,
        avg_funding_rate,
        avg_annualized_rate_pct,
        latest_funding_rate,
        latest_annualized_rate_pct,
        min_annualized_rate_pct,
        max_annualized_rate_pct,
        positive_funding_ratio_pct,
        basis_pct,
        basis_penalty_pct,
        open_interest,
        execution_cost_pct,
        expected_edge_pct,
        stress_edge_pct,
        estimated_carry_30d_pct,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_run_label,
        symbol.upper(),
        result["funding_observations"],
        format(result["avg_funding_rate"], "f"),
        format(result["avg_annualized_rate_pct"], "f"),
        format(result["latest_funding_rate"], "f"),
        format(result["latest_annualized_rate_pct"], "f"),
        format(result["min_annualized_rate_pct"], "f"),
        format(result["max_annualized_rate_pct"], "f"),
        format(result["positive_funding_ratio_pct"], "f"),
        format(result["basis_pct"], "f"),
        format(result["basis_penalty_pct"], "f"),
        None if result["open_interest"] is None else format(result["open_interest"], "f"),
        format(result["execution_cost_pct"], "f"),
        format(result["expected_edge_pct"], "f"),
        format(result["stress_edge_pct"], "f"),
        format(result["estimated_carry_30d_pct"], "f"),
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
    result_id,
    result,
    assumptions,
):
    go_count = 1 if result["final_verdict"] == "GO_FOR_RESEARCH" else 0
    no_go_count = 1 - go_count

    if go_count:
        global_verdict = "DELTA_NEUTRAL_FUNDING_CANDIDATE_FOUND_NO_LIVE_TRADING"
        action = "PROMOTE_TO_DEEP_DELTA_NEUTRAL_BACKTEST"
    else:
        global_verdict = "REJECT_DELTA_NEUTRAL_FUNDING_CANDIDATE_NO_LIVE_TRADING"
        action = result["recommended_action"]

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO delta_neutral_funding_lab_summary (
        run_label,
        source_run_label,
        symbol,
        results_created,
        go_count,
        no_go_count,
        best_result_id,
        best_expected_edge_pct,
        global_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_run_label,
        symbol.upper(),
        1,
        go_count,
        no_go_count,
        result_id,
        format(result["expected_edge_pct"], "f"),
        global_verdict,
        action,
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id), global_verdict, action


def clean_result(item):
    cleaned = {}

    for key, value in item.items():
        if isinstance(value, Decimal):
            cleaned[key] = format(value, "f")
        else:
            cleaned[key] = value

    return cleaned


def run_delta_neutral_funding_lab(
    db_path,
    symbol,
    source_run_label,
    run_label,
    execution_cost_bps,
    basis_penalty_factor,
    min_observations,
    min_avg_annualized_pct,
    min_latest_annualized_pct,
    min_positive_ratio_pct,
    min_basis_pct,
    max_basis_pct,
    min_expected_edge_pct,
    min_stress_edge_pct,
):
    db_path = prepare_database(db_path)
    symbol = symbol.upper()

    assumptions = {
        "research_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
        "no_order_execution": True,
        "symbol": symbol,
        "source_run_label": source_run_label,
        "run_label": run_label,
        "execution_cost_bps": format(to_decimal(execution_cost_bps), "f"),
        "basis_penalty_factor": format(to_decimal(basis_penalty_factor), "f"),
        "min_observations": int(min_observations),
        "min_avg_annualized_pct": format(to_decimal(min_avg_annualized_pct), "f"),
        "min_latest_annualized_pct": format(to_decimal(min_latest_annualized_pct), "f"),
        "min_positive_ratio_pct": format(to_decimal(min_positive_ratio_pct), "f"),
        "min_basis_pct": format(to_decimal(min_basis_pct), "f"),
        "max_basis_pct": format(to_decimal(max_basis_pct), "f"),
        "min_expected_edge_pct": format(to_decimal(min_expected_edge_pct), "f"),
        "min_stress_edge_pct": format(to_decimal(min_stress_edge_pct), "f"),
    }

    funding_rows = load_funding_rows(
        db_path=db_path,
        symbol=symbol,
        source_run_label=source_run_label,
    )

    basis_snapshot = load_latest_basis_snapshot(
        db_path=db_path,
        symbol=symbol,
        source_run_label=source_run_label,
    )

    result = build_lab_result(
        funding_rows=funding_rows,
        basis_snapshot=basis_snapshot,
        execution_cost_bps=to_decimal(execution_cost_bps),
        basis_penalty_factor=to_decimal(basis_penalty_factor),
        min_observations=int(min_observations),
        min_avg_annualized_pct=to_decimal(min_avg_annualized_pct),
        min_latest_annualized_pct=to_decimal(min_latest_annualized_pct),
        min_positive_ratio_pct=to_decimal(min_positive_ratio_pct),
        min_basis_pct=to_decimal(min_basis_pct),
        max_basis_pct=to_decimal(max_basis_pct),
        min_expected_edge_pct=to_decimal(min_expected_edge_pct),
        min_stress_edge_pct=to_decimal(min_stress_edge_pct),
    )

    result_id = insert_lab_result(
        db_path=db_path,
        run_label=run_label,
        source_run_label=source_run_label,
        symbol=symbol,
        result=result,
        assumptions=assumptions,
    )

    summary_id, global_verdict, summary_action = insert_summary(
        db_path=db_path,
        run_label=run_label,
        source_run_label=source_run_label,
        symbol=symbol,
        result_id=result_id,
        result=result,
        assumptions=assumptions,
    )

    return {
        "run_label": run_label,
        "source_run_label": source_run_label,
        "symbol": symbol,
        "result_id": result_id,
        "summary_id": summary_id,
        "funding_observations": result["funding_observations"],
        "avg_annualized_rate_pct": format(result["avg_annualized_rate_pct"], "f"),
        "latest_annualized_rate_pct": format(result["latest_annualized_rate_pct"], "f"),
        "min_annualized_rate_pct": format(result["min_annualized_rate_pct"], "f"),
        "max_annualized_rate_pct": format(result["max_annualized_rate_pct"], "f"),
        "positive_funding_ratio_pct": format(result["positive_funding_ratio_pct"], "f"),
        "basis_pct": format(result["basis_pct"], "f"),
        "basis_penalty_pct": format(result["basis_penalty_pct"], "f"),
        "open_interest": None if result["open_interest"] is None else format(result["open_interest"], "f"),
        "execution_cost_pct": format(result["execution_cost_pct"], "f"),
        "expected_edge_pct": format(result["expected_edge_pct"], "f"),
        "stress_edge_pct": format(result["stress_edge_pct"], "f"),
        "estimated_carry_30d_pct": format(result["estimated_carry_30d_pct"], "f"),
        "final_verdict": result["final_verdict"],
        "recommended_action": result["recommended_action"],
        "results_created": 1,
        "summary_results_created": 1,
        "global_verdict": global_verdict,
        "summary_recommended_action": summary_action,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--source-run-label", default="mission_23_funding_basis_ingestion")
    parser.add_argument("--run-label", default="mission_24_delta_neutral_funding_lab")
    parser.add_argument("--execution-cost-bps", default="20")
    parser.add_argument("--basis-penalty-factor", default="0.25")
    parser.add_argument("--min-observations", type=int, default=10)
    parser.add_argument("--min-avg-annualized-pct", default="10")
    parser.add_argument("--min-latest-annualized-pct", default="8")
    parser.add_argument("--min-positive-ratio-pct", default="80")
    parser.add_argument("--min-basis-pct", default="-0.30")
    parser.add_argument("--max-basis-pct", default="2.00")
    parser.add_argument("--min-expected-edge-pct", default="7")
    parser.add_argument("--min-stress-edge-pct", default="0")

    args = parser.parse_args()

    print("DeltaGrid Delta-Neutral Funding Strategy Lab")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_delta_neutral_funding_lab(
        db_path=args.db_path,
        symbol=args.symbol,
        source_run_label=args.source_run_label,
        run_label=args.run_label,
        execution_cost_bps=Decimal(args.execution_cost_bps),
        basis_penalty_factor=Decimal(args.basis_penalty_factor),
        min_observations=args.min_observations,
        min_avg_annualized_pct=Decimal(args.min_avg_annualized_pct),
        min_latest_annualized_pct=Decimal(args.min_latest_annualized_pct),
        min_positive_ratio_pct=Decimal(args.min_positive_ratio_pct),
        min_basis_pct=Decimal(args.min_basis_pct),
        max_basis_pct=Decimal(args.max_basis_pct),
        min_expected_edge_pct=Decimal(args.min_expected_edge_pct),
        min_stress_edge_pct=Decimal(args.min_stress_edge_pct),
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
