import argparse
import json
import math
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

from backtest.strategy_candidate_lab import (
    benchmark_return,
    load_candles,
    resolve_db_path,
)

from backtest.drawdown_control_lab import run_controlled_ma_strategy


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS stability_rework_split_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        source TEXT NOT NULL,
        run_label TEXT NOT NULL,
        variant_name TEXT NOT NULL,
        variant_version TEXT NOT NULL,
        split_index INTEGER NOT NULL,
        test_start_utc TEXT NOT NULL,
        test_end_utc TEXT NOT NULL,
        net_return_pct TEXT NOT NULL,
        benchmark_return_pct TEXT NOT NULL,
        excess_return_pct TEXT NOT NULL,
        max_drawdown_pct TEXT NOT NULL,
        sharpe_ratio TEXT NOT NULL,
        profit_factor TEXT NOT NULL,
        win_rate_pct TEXT NOT NULL,
        trades_count INTEGER NOT NULL,
        verdict TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS stability_rework_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        source TEXT NOT NULL,
        run_label TEXT NOT NULL,
        variant_name TEXT NOT NULL,
        variant_version TEXT NOT NULL,
        splits_tested INTEGER NOT NULL,
        go_splits INTEGER NOT NULL,
        rejected_splits INTEGER NOT NULL,
        avg_net_return_pct TEXT NOT NULL,
        avg_excess_return_pct TEXT NOT NULL,
        worst_drawdown_pct TEXT NOT NULL,
        avg_sharpe_ratio TEXT NOT NULL,
        avg_profit_factor TEXT NOT NULL,
        total_trades INTEGER NOT NULL,
        consistency_score TEXT NOT NULL,
        final_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def variant_specs():
    return [
        {
            "name": "stability_controlled_ma",
            "version": "fast_20_slow_60_stop_8_trail_10_dd20_cd10",
            "fast": 20,
            "slow": 60,
            "stop": "8",
            "trail": "10",
            "vol_window": None,
            "max_vol": None,
            "dd_guard": "20",
            "cooldown": 10,
        },
        {
            "name": "stability_controlled_ma",
            "version": "fast_30_slow_90_stop_10_trail_15_vol70_dd22_cd15",
            "fast": 30,
            "slow": 90,
            "stop": "10",
            "trail": "15",
            "vol_window": 20,
            "max_vol": "70",
            "dd_guard": "22",
            "cooldown": 15,
        },
        {
            "name": "stability_controlled_ma",
            "version": "fast_50_slow_120_stop_12_trail_20_vol60_dd25_cd20",
            "fast": 50,
            "slow": 120,
            "stop": "12",
            "trail": "20",
            "vol_window": 20,
            "max_vol": "60",
            "dd_guard": "25",
            "cooldown": 20,
        },
        {
            "name": "stability_controlled_ma",
            "version": "fast_20_slow_100_stop_8_trail_12_vol55_dd20_cd20",
            "fast": 20,
            "slow": 100,
            "stop": "8",
            "trail": "12",
            "vol_window": 20,
            "max_vol": "55",
            "dd_guard": "20",
            "cooldown": 20,
        },
        {
            "name": "stability_controlled_ma",
            "version": "fast_10_slow_60_stop_6_trail_10_vol50_dd18_cd30",
            "fast": 10,
            "slow": 60,
            "stop": "6",
            "trail": "10",
            "vol_window": 20,
            "max_vol": "50",
            "dd_guard": "18",
            "cooldown": 30,
        },
    ]


def maybe_decimal(value):
    if value is None:
        return None

    return Decimal(str(value))


def avg(values):
    if not values:
        return Decimal("0")

    return sum(values, Decimal("0")) / Decimal(len(values))


def final_verdict(
    splits_tested,
    go_splits,
    avg_excess,
    worst_drawdown,
    avg_sharpe,
    avg_profit_factor,
    total_trades,
    min_pass_ratio,
):
    if splits_tested < 3:
        return "INSUFFICIENT_SPLITS"

    required_go = int(math.ceil(float(Decimal(splits_tested) * min_pass_ratio)))

    if go_splits < required_go:
        return "NO_GO_STABILITY_FAILURE"

    if avg_excess <= Decimal("0"):
        return "NO_GO_AVG_UNDERPERFORMS_BENCHMARK"

    if worst_drawdown > Decimal("30"):
        return "NO_GO_WORST_DRAWDOWN_TOO_HIGH"

    if avg_sharpe < Decimal("0.75"):
        return "NO_GO_AVG_WEAK_SHARPE"

    if avg_profit_factor < Decimal("1.30"):
        return "NO_GO_AVG_WEAK_PROFIT_FACTOR"

    if total_trades < 10:
        return "INSUFFICIENT_TOTAL_TRADES"

    return "GO_FOR_RESEARCH"


def recommended_action(verdict):
    if verdict == "GO_FOR_RESEARCH":
        return "PROMOTE_TO_DEEP_VALIDATION"

    if verdict == "NO_GO_STABILITY_FAILURE":
        return "REWORK_STABILITY_FILTERS"

    if verdict == "NO_GO_WORST_DRAWDOWN_TOO_HIGH":
        return "TIGHTEN_DRAWDOWN_CONTROL"

    if verdict == "NO_GO_AVG_UNDERPERFORMS_BENCHMARK":
        return "REJECT_OR_REDESIGN_ALPHA"

    return "OBSERVE_ONLY"


def run_variant(spec, candles, initial_capital, fee_bps, slippage_bps, benchmark):
    return run_controlled_ma_strategy(
        candles,
        initial_capital,
        spec["fast"],
        spec["slow"],
        fee_bps,
        slippage_bps,
        benchmark,
        maybe_decimal(spec["stop"]),
        maybe_decimal(spec["trail"]),
        spec["vol_window"],
        maybe_decimal(spec["max_vol"]),
        maybe_decimal(spec["dd_guard"]),
        spec["cooldown"],
    )


def consistency_score(
    go_splits,
    rejected_splits,
    avg_net,
    avg_excess,
    worst_drawdown,
    avg_sharpe,
    avg_profit_factor,
    total_trades,
    verdict,
):
    score = Decimal("0")

    score += Decimal(go_splits) * Decimal("35")
    score -= Decimal(rejected_splits) * Decimal("12")
    score += avg_net
    score += avg_excess
    score -= worst_drawdown
    score += avg_sharpe * Decimal("20")
    score += avg_profit_factor * Decimal("5")
    score += Decimal(total_trades) * Decimal("0.10")

    if verdict == "GO_FOR_RESEARCH":
        score += Decimal("100")
    else:
        score -= Decimal("40")

    return score


def insert_split_result(
    db_path,
    chain_id,
    symbol,
    timeframe,
    source,
    run_label,
    spec,
    split_index,
    test,
    result,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO stability_rework_split_results (
        chain_id,
        symbol,
        timeframe,
        source,
        run_label,
        variant_name,
        variant_version,
        split_index,
        test_start_utc,
        test_end_utc,
        net_return_pct,
        benchmark_return_pct,
        excess_return_pct,
        max_drawdown_pct,
        sharpe_ratio,
        profit_factor,
        win_rate_pct,
        trades_count,
        verdict,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chain_id,
        symbol.upper(),
        timeframe,
        source,
        run_label,
        spec["name"],
        spec["version"],
        split_index,
        test[0]["timestamp_utc"],
        test[-1]["timestamp_utc"],
        format(result["net_return_pct"], "f"),
        format(result["benchmark_return_pct"], "f"),
        format(result["excess_return_pct"], "f"),
        format(result["max_drawdown_pct"], "f"),
        format(result["sharpe_ratio"], "f"),
        format(result["profit_factor"], "f"),
        format(result["win_rate_pct"], "f"),
        int(result["trades_count"]),
        result["verdict"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def insert_summary(
    db_path,
    chain_id,
    symbol,
    timeframe,
    source,
    run_label,
    spec,
    summary,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO stability_rework_summary (
        chain_id,
        symbol,
        timeframe,
        source,
        run_label,
        variant_name,
        variant_version,
        splits_tested,
        go_splits,
        rejected_splits,
        avg_net_return_pct,
        avg_excess_return_pct,
        worst_drawdown_pct,
        avg_sharpe_ratio,
        avg_profit_factor,
        total_trades,
        consistency_score,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chain_id,
        symbol.upper(),
        timeframe,
        source,
        run_label,
        spec["name"],
        spec["version"],
        summary["splits_tested"],
        summary["go_splits"],
        summary["rejected_splits"],
        format(summary["avg_net_return_pct"], "f"),
        format(summary["avg_excess_return_pct"], "f"),
        format(summary["worst_drawdown_pct"], "f"),
        format(summary["avg_sharpe_ratio"], "f"),
        format(summary["avg_profit_factor"], "f"),
        summary["total_trades"],
        format(summary["consistency_score"], "f"),
        summary["final_verdict"],
        summary["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def run_stability_rework_lab(
    db_path,
    chain_id,
    symbol,
    timeframe,
    source,
    initial_capital,
    fee_bps,
    slippage_bps,
    train_size,
    test_size,
    step_size,
    min_pass_ratio,
    run_label,
):
    db_path = resolve_db_path(db_path)

    init_market_database(db_path)
    ensure_schema(db_path)

    candles = load_candles(db_path, chain_id, symbol, timeframe, source)

    if len(candles) < train_size + test_size:
        raise ValueError("Not enough candles for stability rework lab")

    assumptions = {
        "initial_capital": format(initial_capital, "f"),
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "train_size": train_size,
        "test_size": test_size,
        "step_size": step_size,
        "min_pass_ratio": format(min_pass_ratio, "f"),
        "research_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
    }

    specs = variant_specs()

    split_results = {
        f"{spec['name']}::{spec['version']}": []
        for spec in specs
    }

    split_index = 0
    start = 0

    while start + train_size + test_size <= len(candles):
        test = candles[start + train_size:start + train_size + test_size]

        split_benchmark = benchmark_return(
            test,
            initial_capital,
            fee_bps,
            slippage_bps,
        )

        for spec in specs:
            result = run_variant(
                spec,
                test,
                initial_capital,
                fee_bps,
                slippage_bps,
                split_benchmark,
            )

            row_id = insert_split_result(
                db_path,
                chain_id,
                symbol,
                timeframe,
                source,
                run_label,
                spec,
                split_index,
                test,
                result,
                assumptions,
            )

            key = f"{spec['name']}::{spec['version']}"

            split_results[key].append({
                "id": row_id,
                "net_return_pct": result["net_return_pct"],
                "benchmark_return_pct": result["benchmark_return_pct"],
                "excess_return_pct": result["excess_return_pct"],
                "max_drawdown_pct": result["max_drawdown_pct"],
                "sharpe_ratio": result["sharpe_ratio"],
                "profit_factor": result["profit_factor"],
                "win_rate_pct": result["win_rate_pct"],
                "trades_count": int(result["trades_count"]),
                "verdict": result["verdict"],
            })

        split_index += 1
        start += step_size

    summaries = []

    for spec in specs:
        key = f"{spec['name']}::{spec['version']}"
        rows = split_results[key]

        splits_tested = len(rows)
        go_splits = sum(1 for row in rows if row["verdict"] == "GO_FOR_RESEARCH")
        rejected_splits = splits_tested - go_splits

        avg_net = avg([row["net_return_pct"] for row in rows])
        avg_excess = avg([row["excess_return_pct"] for row in rows])
        worst_drawdown = max(row["max_drawdown_pct"] for row in rows)
        avg_sharpe = avg([row["sharpe_ratio"] for row in rows])
        avg_profit_factor = avg([row["profit_factor"] for row in rows])
        total_trades = sum(row["trades_count"] for row in rows)

        verdict = final_verdict(
            splits_tested,
            go_splits,
            avg_excess,
            worst_drawdown,
            avg_sharpe,
            avg_profit_factor,
            total_trades,
            min_pass_ratio,
        )

        score = consistency_score(
            go_splits,
            rejected_splits,
            avg_net,
            avg_excess,
            worst_drawdown,
            avg_sharpe,
            avg_profit_factor,
            total_trades,
            verdict,
        )

        summary = {
            "variant_name": spec["name"],
            "variant_version": spec["version"],
            "splits_tested": splits_tested,
            "go_splits": go_splits,
            "rejected_splits": rejected_splits,
            "avg_net_return_pct": avg_net,
            "avg_excess_return_pct": avg_excess,
            "worst_drawdown_pct": worst_drawdown,
            "avg_sharpe_ratio": avg_sharpe,
            "avg_profit_factor": avg_profit_factor,
            "total_trades": total_trades,
            "consistency_score": score,
            "final_verdict": verdict,
            "recommended_action": recommended_action(verdict),
        }

        summary["id"] = insert_summary(
            db_path,
            chain_id,
            symbol,
            timeframe,
            source,
            run_label,
            spec,
            summary,
            assumptions,
        )

        summaries.append(summary)

    ranked = sorted(
        summaries,
        key=lambda item: item["consistency_score"],
        reverse=True,
    )

    approved = [
        item
        for item in ranked
        if item["final_verdict"] == "GO_FOR_RESEARCH"
    ]

    if approved:
        global_verdict = "STABILITY_VARIANT_FOUND_NO_LIVE_TRADING"
        best_variant = approved[0]
    else:
        global_verdict = "REJECT_ALL_STABILITY_VARIANTS_NO_LIVE_TRADING"
        best_variant = ranked[0]

    def clean(item):
        return {
            "id": item["id"],
            "variant_name": item["variant_name"],
            "variant_version": item["variant_version"],
            "splits_tested": item["splits_tested"],
            "go_splits": item["go_splits"],
            "rejected_splits": item["rejected_splits"],
            "avg_net_return_pct": format(item["avg_net_return_pct"], "f"),
            "avg_excess_return_pct": format(item["avg_excess_return_pct"], "f"),
            "worst_drawdown_pct": format(item["worst_drawdown_pct"], "f"),
            "avg_sharpe_ratio": format(item["avg_sharpe_ratio"], "f"),
            "avg_profit_factor": format(item["avg_profit_factor"], "f"),
            "total_trades": item["total_trades"],
            "consistency_score": format(item["consistency_score"], "f"),
            "final_verdict": item["final_verdict"],
            "recommended_action": item["recommended_action"],
        }

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "source": source,
        "candles_seen": len(candles),
        "run_label": run_label,
        "variant_count": len(specs),
        "splits_tested": split_index,
        "split_results_created": split_index * len(specs),
        "summary_results_created": len(specs),
        "approved_count": len(approved),
        "rejected_or_insufficient": len(ranked) - len(approved),
        "best_variant": clean(best_variant),
        "ranked_variants": [clean(item) for item in ranked],
        "global_verdict": global_verdict,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--chain-id", type=int, default=0)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--source", default="binance_spot")
    parser.add_argument("--initial-capital", default="10000")
    parser.add_argument("--fee-bps", type=int, default=10)
    parser.add_argument("--slippage-bps", type=int, default=10)
    parser.add_argument("--train-size", type=int, default=365)
    parser.add_argument("--test-size", type=int, default=180)
    parser.add_argument("--step-size", type=int, default=180)
    parser.add_argument("--min-pass-ratio", default="0.60")
    parser.add_argument("--run-label", default="mission_19_stability_rework_lab")

    args = parser.parse_args()

    print("DeltaGrid Stability Rework Lab")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_stability_rework_lab(
        db_path=args.db_path,
        chain_id=args.chain_id,
        symbol=args.symbol,
        timeframe=args.timeframe,
        source=args.source,
        initial_capital=Decimal(args.initial_capital),
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
        train_size=args.train_size,
        test_size=args.test_size,
        step_size=args.step_size,
        min_pass_ratio=Decimal(args.min_pass_ratio),
        run_label=args.run_label,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
