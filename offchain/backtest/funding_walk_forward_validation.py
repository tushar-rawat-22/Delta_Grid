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

from backtest.delta_neutral_funding_backtest import (
    ensure_schema as ensure_backtest_schema,
    load_basis_rows,
    load_funding_rows,
    simulate_delta_neutral_backtest,
    summarize_backtest,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def avg(values):
    if not values:
        return Decimal("0")

    return sum(values, Decimal("0")) / Decimal(len(values))


def ceil_decimal(value):
    integer = int(value)

    if Decimal(integer) < value:
        return integer + 1

    return integer


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS funding_walk_forward_split_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_run_label TEXT NOT NULL,
        symbol TEXT NOT NULL,
        variant_name TEXT NOT NULL,
        variant_version TEXT NOT NULL,
        split_index INTEGER NOT NULL,
        train_start_utc TEXT NOT NULL,
        train_end_utc TEXT NOT NULL,
        test_start_utc TEXT NOT NULL,
        test_end_utc TEXT NOT NULL,
        funding_observations INTEGER NOT NULL,
        trades_count INTEGER NOT NULL,
        net_return_pct TEXT NOT NULL,
        avg_trade_return_pct TEXT NOT NULL,
        gross_funding_return_pct TEXT NOT NULL,
        basis_pnl_pct TEXT NOT NULL,
        execution_cost_pct TEXT NOT NULL,
        win_rate_pct TEXT NOT NULL,
        max_drawdown_pct TEXT NOT NULL,
        profit_factor TEXT NOT NULL,
        positive_funding_ratio_pct TEXT NOT NULL,
        avg_annualized_funding_pct TEXT NOT NULL,
        min_annualized_funding_pct TEXT NOT NULL,
        max_annualized_funding_pct TEXT NOT NULL,
        split_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS funding_walk_forward_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_run_label TEXT NOT NULL,
        symbol TEXT NOT NULL,
        variant_name TEXT NOT NULL,
        variant_version TEXT NOT NULL,
        splits_tested INTEGER NOT NULL,
        go_splits INTEGER NOT NULL,
        no_go_splits INTEGER NOT NULL,
        total_trades INTEGER NOT NULL,
        avg_net_return_pct TEXT NOT NULL,
        total_net_return_pct TEXT NOT NULL,
        avg_trade_return_pct TEXT NOT NULL,
        worst_drawdown_pct TEXT NOT NULL,
        avg_profit_factor TEXT NOT NULL,
        avg_positive_funding_ratio_pct TEXT NOT NULL,
        avg_annualized_funding_pct TEXT NOT NULL,
        stability_score TEXT NOT NULL,
        final_verdict TEXT NOT NULL,
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
    ensure_backtest_schema(db_path)
    ensure_schema(db_path)

    return db_path


def variant_specs():
    return [
        {
            "name": "funding_wf",
            "version": "strict_entry10_exit5_hold20_cost20",
            "entry_annualized_pct": Decimal("10"),
            "exit_annualized_pct": Decimal("5"),
            "min_basis_pct": Decimal("-0.30"),
            "max_basis_pct": Decimal("2.00"),
            "max_holding_windows": 20,
            "execution_cost_bps": Decimal("20"),
            "min_observations": 5,
            "min_trades": 1,
            "min_avg_annualized_pct": Decimal("8"),
            "min_net_return_pct": Decimal("0.10"),
            "max_drawdown_limit_pct": Decimal("5"),
            "min_profit_factor": Decimal("1.10"),
        },
        {
            "name": "funding_wf",
            "version": "balanced_entry8_exit4_hold20_cost20",
            "entry_annualized_pct": Decimal("8"),
            "exit_annualized_pct": Decimal("4"),
            "min_basis_pct": Decimal("-0.30"),
            "max_basis_pct": Decimal("2.00"),
            "max_holding_windows": 20,
            "execution_cost_bps": Decimal("20"),
            "min_observations": 5,
            "min_trades": 1,
            "min_avg_annualized_pct": Decimal("6"),
            "min_net_return_pct": Decimal("0.05"),
            "max_drawdown_limit_pct": Decimal("5"),
            "min_profit_factor": Decimal("1.05"),
        },
        {
            "name": "funding_wf",
            "version": "loose_entry5_exit2_hold20_cost20",
            "entry_annualized_pct": Decimal("5"),
            "exit_annualized_pct": Decimal("2"),
            "min_basis_pct": Decimal("-0.30"),
            "max_basis_pct": Decimal("2.00"),
            "max_holding_windows": 20,
            "execution_cost_bps": Decimal("20"),
            "min_observations": 5,
            "min_trades": 1,
            "min_avg_annualized_pct": Decimal("5"),
            "min_net_return_pct": Decimal("0.00"),
            "max_drawdown_limit_pct": Decimal("5"),
            "min_profit_factor": Decimal("1.00"),
        },
    ]


def build_walk_forward_splits(funding_rows, train_size, test_size, step_size):
    splits = []
    start = 0
    split_index = 0

    while start + train_size + test_size <= len(funding_rows):
        train = funding_rows[start:start + train_size]
        test = funding_rows[start + train_size:start + train_size + test_size]

        splits.append({
            "split_index": split_index,
            "train": train,
            "test": test,
            "train_start_utc": train[0]["funding_time_utc"],
            "train_end_utc": train[-1]["funding_time_utc"],
            "test_start_utc": test[0]["funding_time_utc"],
            "test_end_utc": test[-1]["funding_time_utc"],
        })

        split_index += 1
        start += step_size

    return splits


def final_summary_verdict(
    splits_tested,
    go_splits,
    total_trades,
    avg_net_return_pct,
    worst_drawdown_pct,
    avg_profit_factor,
    min_splits,
    min_pass_ratio,
    min_total_trades,
    min_avg_net_return_pct,
    max_drawdown_limit_pct,
    min_avg_profit_factor,
):
    if splits_tested < min_splits:
        return "INSUFFICIENT_SPLITS"

    if total_trades < min_total_trades:
        return "INSUFFICIENT_TOTAL_TRADES"

    required_go = ceil_decimal(
        Decimal(splits_tested) * min_pass_ratio
    )

    if go_splits < required_go:
        return "NO_GO_WALK_FORWARD_STABILITY"

    if avg_net_return_pct < min_avg_net_return_pct:
        return "NO_GO_WEAK_AVG_RETURN"

    if worst_drawdown_pct > max_drawdown_limit_pct:
        return "NO_GO_DRAWDOWN_TOO_HIGH"

    if avg_profit_factor < min_avg_profit_factor:
        return "NO_GO_WEAK_PROFIT_FACTOR"

    return "GO_FOR_RESEARCH"


def recommended_action(verdict):
    if verdict == "GO_FOR_RESEARCH":
        return "PROMOTE_TO_FUNDING_RISK_MODELING"

    if verdict == "INSUFFICIENT_SPLITS":
        return "COLLECT_MORE_FUNDING_HISTORY"

    if verdict == "INSUFFICIENT_TOTAL_TRADES":
        return "BROADEN_SAMPLE_OR_LOWER_THRESHOLDS"

    if verdict == "NO_GO_WALK_FORWARD_STABILITY":
        return "REWORK_FUNDING_ENTRY_EXIT_RULES"

    if verdict == "NO_GO_WEAK_AVG_RETURN":
        return "REJECT_WEAK_CARRY"

    if verdict == "NO_GO_DRAWDOWN_TOO_HIGH":
        return "TIGHTEN_BASIS_RISK_FILTERS"

    if verdict == "NO_GO_WEAK_PROFIT_FACTOR":
        return "REWORK_PROFITABILITY_FILTERS"

    return "OBSERVE_ONLY"


def stability_score(
    splits_tested,
    go_splits,
    no_go_splits,
    total_trades,
    avg_net_return_pct,
    total_net_return_pct,
    worst_drawdown_pct,
    avg_profit_factor,
    avg_positive_funding_ratio_pct,
    avg_annualized_funding_pct,
    final_verdict_value,
):
    capped_pf = min(avg_profit_factor, Decimal("5"))

    score = Decimal("0")
    score += Decimal(go_splits) * Decimal("45")
    score -= Decimal(no_go_splits) * Decimal("15")
    score += Decimal(total_trades) * Decimal("1.5")
    score += avg_net_return_pct * Decimal("3")
    score += total_net_return_pct
    score -= worst_drawdown_pct * Decimal("2")
    score += capped_pf * Decimal("8")
    score += avg_positive_funding_ratio_pct * Decimal("0.10")
    score += avg_annualized_funding_pct * Decimal("0.75")

    if final_verdict_value == "GO_FOR_RESEARCH":
        score += Decimal("100")
    else:
        score -= Decimal("50")

    if splits_tested == 0:
        score -= Decimal("100")

    return score


def insert_split_result(
    db_path,
    run_label,
    source_run_label,
    symbol,
    spec,
    split,
    result,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO funding_walk_forward_split_results (
        run_label,
        source_run_label,
        symbol,
        variant_name,
        variant_version,
        split_index,
        train_start_utc,
        train_end_utc,
        test_start_utc,
        test_end_utc,
        funding_observations,
        trades_count,
        net_return_pct,
        avg_trade_return_pct,
        gross_funding_return_pct,
        basis_pnl_pct,
        execution_cost_pct,
        win_rate_pct,
        max_drawdown_pct,
        profit_factor,
        positive_funding_ratio_pct,
        avg_annualized_funding_pct,
        min_annualized_funding_pct,
        max_annualized_funding_pct,
        split_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_run_label,
        symbol.upper(),
        spec["name"],
        spec["version"],
        split["split_index"],
        split["train_start_utc"],
        split["train_end_utc"],
        split["test_start_utc"],
        split["test_end_utc"],
        result["funding_observations"],
        result["trades_count"],
        format(result["net_return_pct"], "f"),
        format(result["avg_trade_return_pct"], "f"),
        format(result["gross_funding_return_pct"], "f"),
        format(result["basis_pnl_pct"], "f"),
        format(result["execution_cost_pct"], "f"),
        format(result["win_rate_pct"], "f"),
        format(result["max_drawdown_pct"], "f"),
        format(result["profit_factor"], "f"),
        format(result["positive_funding_ratio_pct"], "f"),
        format(result["avg_annualized_funding_pct"], "f"),
        format(result["min_annualized_funding_pct"], "f"),
        format(result["max_annualized_funding_pct"], "f"),
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
    spec,
    summary,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO funding_walk_forward_summary (
        run_label,
        source_run_label,
        symbol,
        variant_name,
        variant_version,
        splits_tested,
        go_splits,
        no_go_splits,
        total_trades,
        avg_net_return_pct,
        total_net_return_pct,
        avg_trade_return_pct,
        worst_drawdown_pct,
        avg_profit_factor,
        avg_positive_funding_ratio_pct,
        avg_annualized_funding_pct,
        stability_score,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_run_label,
        symbol.upper(),
        spec["name"],
        spec["version"],
        summary["splits_tested"],
        summary["go_splits"],
        summary["no_go_splits"],
        summary["total_trades"],
        format(summary["avg_net_return_pct"], "f"),
        format(summary["total_net_return_pct"], "f"),
        format(summary["avg_trade_return_pct"], "f"),
        format(summary["worst_drawdown_pct"], "f"),
        format(summary["avg_profit_factor"], "f"),
        format(summary["avg_positive_funding_ratio_pct"], "f"),
        format(summary["avg_annualized_funding_pct"], "f"),
        format(summary["stability_score"], "f"),
        summary["final_verdict"],
        summary["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def summarize_variant(
    rows,
    min_splits,
    min_pass_ratio,
    min_total_trades,
    min_avg_net_return_pct,
    max_drawdown_limit_pct,
    min_avg_profit_factor,
):
    splits_tested = len(rows)
    go_splits = sum(
        1
        for row in rows
        if row["final_verdict"] == "GO_FOR_RESEARCH"
    )
    no_go_splits = splits_tested - go_splits

    total_trades = sum(
        row["trades_count"]
        for row in rows
    )

    avg_net = avg([
        row["net_return_pct"]
        for row in rows
    ])

    total_net = sum(
        [
            row["net_return_pct"]
            for row in rows
        ],
        Decimal("0"),
    )

    avg_trade_return = avg([
        row["avg_trade_return_pct"]
        for row in rows
    ])

    worst_drawdown = max(
        [row["max_drawdown_pct"] for row in rows],
        default=Decimal("0"),
    )

    avg_pf = avg([
        row["profit_factor"]
        for row in rows
    ])

    avg_positive_ratio = avg([
        row["positive_funding_ratio_pct"]
        for row in rows
    ])

    avg_annualized = avg([
        row["avg_annualized_funding_pct"]
        for row in rows
    ])

    verdict = final_summary_verdict(
        splits_tested=splits_tested,
        go_splits=go_splits,
        total_trades=total_trades,
        avg_net_return_pct=avg_net,
        worst_drawdown_pct=worst_drawdown,
        avg_profit_factor=avg_pf,
        min_splits=min_splits,
        min_pass_ratio=min_pass_ratio,
        min_total_trades=min_total_trades,
        min_avg_net_return_pct=min_avg_net_return_pct,
        max_drawdown_limit_pct=max_drawdown_limit_pct,
        min_avg_profit_factor=min_avg_profit_factor,
    )

    score = stability_score(
        splits_tested=splits_tested,
        go_splits=go_splits,
        no_go_splits=no_go_splits,
        total_trades=total_trades,
        avg_net_return_pct=avg_net,
        total_net_return_pct=total_net,
        worst_drawdown_pct=worst_drawdown,
        avg_profit_factor=avg_pf,
        avg_positive_funding_ratio_pct=avg_positive_ratio,
        avg_annualized_funding_pct=avg_annualized,
        final_verdict_value=verdict,
    )

    return {
        "splits_tested": splits_tested,
        "go_splits": go_splits,
        "no_go_splits": no_go_splits,
        "total_trades": total_trades,
        "avg_net_return_pct": avg_net,
        "total_net_return_pct": total_net,
        "avg_trade_return_pct": avg_trade_return,
        "worst_drawdown_pct": worst_drawdown,
        "avg_profit_factor": avg_pf,
        "avg_positive_funding_ratio_pct": avg_positive_ratio,
        "avg_annualized_funding_pct": avg_annualized,
        "stability_score": score,
        "final_verdict": verdict,
        "recommended_action": recommended_action(verdict),
    }


def clean_decimal_dict(item):
    result = {}

    for key, value in item.items():
        if isinstance(value, Decimal):
            result[key] = format(value, "f")
        else:
            result[key] = value

    return result


def run_funding_walk_forward_validation(
    db_path,
    symbol,
    source_run_label,
    run_label,
    train_size,
    test_size,
    step_size,
    min_splits,
    min_pass_ratio,
    min_total_trades,
    min_avg_net_return_pct,
    max_drawdown_limit_pct,
    min_avg_profit_factor,
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
        "train_size": int(train_size),
        "test_size": int(test_size),
        "step_size": int(step_size),
        "min_splits": int(min_splits),
        "min_pass_ratio": format(to_decimal(min_pass_ratio), "f"),
        "min_total_trades": int(min_total_trades),
        "min_avg_net_return_pct": format(to_decimal(min_avg_net_return_pct), "f"),
        "max_drawdown_limit_pct": format(to_decimal(max_drawdown_limit_pct), "f"),
        "min_avg_profit_factor": format(to_decimal(min_avg_profit_factor), "f"),
        "basis_model_note": "Uses latest available basis snapshot at or before funding timestamp. If unavailable, first snapshot is used.",
    }

    funding_rows = load_funding_rows(
        db_path=db_path,
        symbol=symbol,
        source_run_label=source_run_label,
    )

    basis_rows = load_basis_rows(
        db_path=db_path,
        symbol=symbol,
        source_run_label=source_run_label,
    )

    splits = build_walk_forward_splits(
        funding_rows=funding_rows,
        train_size=int(train_size),
        test_size=int(test_size),
        step_size=int(step_size),
    )

    specs = variant_specs()

    split_results_by_variant = {
        f"{spec['name']}::{spec['version']}": []
        for spec in specs
    }

    split_rows_created = 0

    for split in splits:
        for spec in specs:
            trades = simulate_delta_neutral_backtest(
                funding_rows=split["test"],
                basis_rows=basis_rows,
                entry_annualized_pct=spec["entry_annualized_pct"],
                exit_annualized_pct=spec["exit_annualized_pct"],
                min_basis_pct=spec["min_basis_pct"],
                max_basis_pct=spec["max_basis_pct"],
                max_holding_windows=spec["max_holding_windows"],
                execution_cost_bps=spec["execution_cost_bps"],
            )

            result = summarize_backtest(
                funding_rows=split["test"],
                trades=trades,
                min_observations=spec["min_observations"],
                min_trades=spec["min_trades"],
                min_avg_annualized_pct=spec["min_avg_annualized_pct"],
                min_net_return_pct=spec["min_net_return_pct"],
                max_drawdown_limit_pct=spec["max_drawdown_limit_pct"],
                min_profit_factor=spec["min_profit_factor"],
            )

            insert_split_result(
                db_path=db_path,
                run_label=run_label,
                source_run_label=source_run_label,
                symbol=symbol,
                spec=spec,
                split=split,
                result=result,
                assumptions={**assumptions, "variant": spec["version"]},
            )

            key = f"{spec['name']}::{spec['version']}"
            split_results_by_variant[key].append(result)

            split_rows_created += 1

    summaries = []

    for spec in specs:
        key = f"{spec['name']}::{spec['version']}"

        summary = summarize_variant(
            rows=split_results_by_variant[key],
            min_splits=int(min_splits),
            min_pass_ratio=to_decimal(min_pass_ratio),
            min_total_trades=int(min_total_trades),
            min_avg_net_return_pct=to_decimal(min_avg_net_return_pct),
            max_drawdown_limit_pct=to_decimal(max_drawdown_limit_pct),
            min_avg_profit_factor=to_decimal(min_avg_profit_factor),
        )

        summary_id = insert_summary(
            db_path=db_path,
            run_label=run_label,
            source_run_label=source_run_label,
            symbol=symbol,
            spec=spec,
            summary=summary,
            assumptions={**assumptions, "variant": spec["version"]},
        )

        summaries.append({
            "id": summary_id,
            "variant_name": spec["name"],
            "variant_version": spec["version"],
            **summary,
        })

    ranked = sorted(
        summaries,
        key=lambda row: row["stability_score"],
        reverse=True,
    )

    approved = [
        row
        for row in ranked
        if row["final_verdict"] == "GO_FOR_RESEARCH"
    ]

    if approved:
        global_verdict = "FUNDING_WALK_FORWARD_CANDIDATE_FOUND_NO_LIVE_TRADING"
        best_variant = approved[0]
    else:
        global_verdict = "REJECT_ALL_FUNDING_WALK_FORWARD_VARIANTS_NO_LIVE_TRADING"
        best_variant = ranked[0] if ranked else None

    return {
        "run_label": run_label,
        "source_run_label": source_run_label,
        "symbol": symbol,
        "funding_observations": len(funding_rows),
        "basis_snapshots": len(basis_rows),
        "variant_count": len(specs),
        "splits_tested": len(splits),
        "split_results_created": split_rows_created,
        "summary_results_created": len(summaries),
        "approved_count": len(approved),
        "rejected_or_insufficient": len(ranked) - len(approved),
        "best_variant": None if best_variant is None else clean_decimal_dict(best_variant),
        "ranked_variants": [
            clean_decimal_dict(row)
            for row in ranked
        ],
        "global_verdict": global_verdict,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--source-run-label", default="mission_23_funding_basis_ingestion")
    parser.add_argument("--run-label", default="mission_26_funding_walk_forward_validation")
    parser.add_argument("--train-size", type=int, default=10)
    parser.add_argument("--test-size", type=int, default=5)
    parser.add_argument("--step-size", type=int, default=5)
    parser.add_argument("--min-splits", type=int, default=2)
    parser.add_argument("--min-pass-ratio", default="0.60")
    parser.add_argument("--min-total-trades", type=int, default=1)
    parser.add_argument("--min-avg-net-return-pct", default="0.00")
    parser.add_argument("--max-drawdown-limit-pct", default="5")
    parser.add_argument("--min-avg-profit-factor", default="1.00")

    args = parser.parse_args()

    print("DeltaGrid Funding Walk-Forward Validation")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_funding_walk_forward_validation(
        db_path=args.db_path,
        symbol=args.symbol,
        source_run_label=args.source_run_label,
        run_label=args.run_label,
        train_size=args.train_size,
        test_size=args.test_size,
        step_size=args.step_size,
        min_splits=args.min_splits,
        min_pass_ratio=Decimal(args.min_pass_ratio),
        min_total_trades=args.min_total_trades,
        min_avg_net_return_pct=Decimal(args.min_avg_net_return_pct),
        max_drawdown_limit_pct=Decimal(args.max_drawdown_limit_pct),
        min_avg_profit_factor=Decimal(args.min_avg_profit_factor),
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
