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
    run_breakout,
    run_ma_crossover,
    run_mean_reversion,
    run_momentum,
)

from backtest.drawdown_control_lab import run_controlled_ma_strategy


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def ensure_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS walk_forward_candidate_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        source TEXT NOT NULL,
        run_label TEXT NOT NULL,
        candidate_name TEXT NOT NULL,
        candidate_version TEXT NOT NULL,
        split_index INTEGER NOT NULL,
        train_start_utc TEXT NOT NULL,
        train_end_utc TEXT NOT NULL,
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
        rank_score TEXT NOT NULL,
        verdict TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS walk_forward_candidate_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        source TEXT NOT NULL,
        run_label TEXT NOT NULL,
        candidate_name TEXT NOT NULL,
        candidate_version TEXT NOT NULL,
        splits_tested INTEGER NOT NULL,
        go_splits INTEGER NOT NULL,
        rejected_or_insufficient_splits INTEGER NOT NULL,
        avg_net_return_pct TEXT NOT NULL,
        avg_excess_return_pct TEXT NOT NULL,
        worst_drawdown_pct TEXT NOT NULL,
        avg_sharpe_ratio TEXT NOT NULL,
        avg_profit_factor TEXT NOT NULL,
        total_trades INTEGER NOT NULL,
        stability_score TEXT NOT NULL,
        final_verdict TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def candidate_specs() -> list[dict]:
    return [
        {
            "name": "ma_crossover",
            "version": "fast_20_slow_60",
            "type": "ma",
            "fast": 20,
            "slow": 60,
        },
        {
            "name": "ma_crossover",
            "version": "fast_10_slow_30",
            "type": "ma",
            "fast": 10,
            "slow": 30,
        },
        {
            "name": "momentum",
            "version": "lookback_20_threshold_300_hold_10",
            "type": "momentum",
            "lookback": 20,
            "threshold": 300,
            "hold": 10,
        },
        {
            "name": "breakout",
            "version": "window_20",
            "type": "breakout",
            "window": 20,
        },
        {
            "name": "mean_reversion",
            "version": "window_20_deviation_500",
            "type": "mean_reversion",
            "window": 20,
            "deviation": 500,
        },
        {
            "name": "controlled_ma",
            "version": "fast_20_slow_60_stop_12",
            "type": "controlled_ma",
            "fast": 20,
            "slow": 60,
            "stop": "12",
            "trail": None,
            "vol_window": None,
            "max_vol": None,
            "dd_guard": None,
            "cooldown": 0,
        },
        {
            "name": "controlled_ma",
            "version": "fast_20_slow_60_stop_10_trail_15_maxvol_85_ddguard_25_cooldown_20",
            "type": "controlled_ma",
            "fast": 20,
            "slow": 60,
            "stop": "10",
            "trail": "15",
            "vol_window": 20,
            "max_vol": "85",
            "dd_guard": "25",
            "cooldown": 20,
        },
    ]


def evaluate_candidate(spec, candles, initial_capital, fee_bps, slippage_bps, benchmark):
    if spec["type"] == "ma":
        return run_ma_crossover(
            candles,
            initial_capital,
            spec["fast"],
            spec["slow"],
            fee_bps,
            slippage_bps,
            benchmark,
        )

    if spec["type"] == "momentum":
        return run_momentum(
            candles,
            initial_capital,
            spec["lookback"],
            spec["threshold"],
            spec["hold"],
            fee_bps,
            slippage_bps,
            benchmark,
        )

    if spec["type"] == "breakout":
        return run_breakout(
            candles,
            initial_capital,
            spec["window"],
            fee_bps,
            slippage_bps,
            benchmark,
        )

    if spec["type"] == "mean_reversion":
        return run_mean_reversion(
            candles,
            initial_capital,
            spec["window"],
            spec["deviation"],
            fee_bps,
            slippage_bps,
            benchmark,
        )

    if spec["type"] == "controlled_ma":
        return run_controlled_ma_strategy(
            candles,
            initial_capital,
            spec["fast"],
            spec["slow"],
            fee_bps,
            slippage_bps,
            benchmark,
            Decimal(spec["stop"]) if spec["stop"] else None,
            Decimal(spec["trail"]) if spec["trail"] else None,
            spec["vol_window"],
            Decimal(spec["max_vol"]) if spec["max_vol"] else None,
            Decimal(spec["dd_guard"]) if spec["dd_guard"] else None,
            spec["cooldown"],
        )

    raise ValueError("Unknown candidate type")


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
        return "NO_GO_WALK_FORWARD_FAILURE"

    if avg_excess <= Decimal("0"):
        return "NO_GO_AVG_UNDERPERFORMS_BENCHMARK"

    if worst_drawdown > Decimal("30"):
        return "NO_GO_WORST_DRAWDOWN_TOO_HIGH"

    if avg_sharpe < Decimal("0.75"):
        return "NO_GO_AVG_WEAK_SHARPE"

    if avg_profit_factor < Decimal("1.3"):
        return "NO_GO_AVG_WEAK_PROFIT_FACTOR"

    if total_trades < 10:
        return "INSUFFICIENT_TOTAL_TRADES"

    return "GO_FOR_RESEARCH"


def stability_score(
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

    score += avg_net
    score += avg_excess
    score -= worst_drawdown
    score += avg_sharpe * Decimal("10")
    score += avg_profit_factor * Decimal("5")
    score += Decimal(go_splits) * Decimal("25")
    score -= Decimal(rejected_splits) * Decimal("10")
    score += Decimal(total_trades) * Decimal("0.10")

    if verdict == "GO_FOR_RESEARCH":
        score += Decimal("100")
    else:
        score -= Decimal("50")

    return score


def insert_split_result(db_path, chain_id, symbol, timeframe, source, run_label, spec, split_index, train, test, result, assumptions):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO walk_forward_candidate_results (
        chain_id, symbol, timeframe, source, run_label,
        candidate_name, candidate_version, split_index,
        train_start_utc, train_end_utc, test_start_utc, test_end_utc,
        net_return_pct, benchmark_return_pct, excess_return_pct,
        max_drawdown_pct, sharpe_ratio, profit_factor, win_rate_pct,
        trades_count, rank_score, verdict, assumptions_json, created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chain_id,
        symbol.upper(),
        timeframe,
        source,
        run_label,
        spec["name"],
        spec["version"],
        split_index,
        train[0]["timestamp_utc"],
        train[-1]["timestamp_utc"],
        test[0]["timestamp_utc"],
        test[-1]["timestamp_utc"],
        format(result["net_return_pct"], "f"),
        format(result["benchmark_return_pct"], "f"),
        format(result["excess_return_pct"], "f"),
        format(result["max_drawdown_pct"], "f"),
        format(result["sharpe_ratio"], "f"),
        format(result["profit_factor"], "f"),
        format(result["win_rate_pct"], "f"),
        result["trades_count"],
        format(result["rank_score"], "f"),
        result["verdict"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def insert_summary(db_path, chain_id, symbol, timeframe, source, run_label, spec, summary, assumptions):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO walk_forward_candidate_summary (
        chain_id, symbol, timeframe, source, run_label,
        candidate_name, candidate_version,
        splits_tested, go_splits, rejected_or_insufficient_splits,
        avg_net_return_pct, avg_excess_return_pct, worst_drawdown_pct,
        avg_sharpe_ratio, avg_profit_factor, total_trades,
        stability_score, final_verdict, assumptions_json, created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        summary["rejected_or_insufficient_splits"],
        format(summary["avg_net_return_pct"], "f"),
        format(summary["avg_excess_return_pct"], "f"),
        format(summary["worst_drawdown_pct"], "f"),
        format(summary["avg_sharpe_ratio"], "f"),
        format(summary["avg_profit_factor"], "f"),
        summary["total_trades"],
        format(summary["stability_score"], "f"),
        summary["final_verdict"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def run_walk_forward_candidate_lab(
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
        raise ValueError("Not enough candles for walk-forward candidate lab")

    assumptions = {
        "initial_capital": format(initial_capital, "f"),
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "train_size": train_size,
        "test_size": test_size,
        "step_size": step_size,
        "min_pass_ratio": format(min_pass_ratio, "f"),
        "benchmark": "buy_and_hold",
        "research_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
    }

    specs = candidate_specs()

    split_results = {
        f"{spec['name']}::{spec['version']}": []
        for spec in specs
    }

    split_index = 0
    start = 0

    while start + train_size + test_size <= len(candles):
        train = candles[start:start + train_size]
        test = candles[start + train_size:start + train_size + test_size]

        split_benchmark = benchmark_return(
            test,
            initial_capital,
            fee_bps,
            slippage_bps,
        )

        for spec in specs:
            result = evaluate_candidate(
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
                train,
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
                "trades_count": result["trades_count"],
                "rank_score": result["rank_score"],
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
        rejected = splits_tested - go_splits

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

        score = stability_score(
            go_splits,
            rejected,
            avg_net,
            avg_excess,
            worst_drawdown,
            avg_sharpe,
            avg_profit_factor,
            total_trades,
            verdict,
        )

        summary = {
            "candidate_name": spec["name"],
            "candidate_version": spec["version"],
            "splits_tested": splits_tested,
            "go_splits": go_splits,
            "rejected_or_insufficient_splits": rejected,
            "avg_net_return_pct": avg_net,
            "avg_excess_return_pct": avg_excess,
            "worst_drawdown_pct": worst_drawdown,
            "avg_sharpe_ratio": avg_sharpe,
            "avg_profit_factor": avg_profit_factor,
            "total_trades": total_trades,
            "stability_score": score,
            "final_verdict": verdict,
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
        key=lambda item: item["stability_score"],
        reverse=True,
    )

    approved = [
        item
        for item in ranked
        if item["final_verdict"] == "GO_FOR_RESEARCH"
    ]

    if approved:
        global_verdict = "WALK_FORWARD_CANDIDATE_FOUND_NO_LIVE_TRADING"
        best_candidate = approved[0]
    else:
        global_verdict = "REJECT_ALL_NO_LIVE_TRADING"
        best_candidate = ranked[0]

    def clean(item):
        return {
            "id": item["id"],
            "candidate_name": item["candidate_name"],
            "candidate_version": item["candidate_version"],
            "splits_tested": item["splits_tested"],
            "go_splits": item["go_splits"],
            "rejected_or_insufficient_splits": item["rejected_or_insufficient_splits"],
            "avg_net_return_pct": format(item["avg_net_return_pct"], "f"),
            "avg_excess_return_pct": format(item["avg_excess_return_pct"], "f"),
            "worst_drawdown_pct": format(item["worst_drawdown_pct"], "f"),
            "avg_sharpe_ratio": format(item["avg_sharpe_ratio"], "f"),
            "avg_profit_factor": format(item["avg_profit_factor"], "f"),
            "total_trades": item["total_trades"],
            "stability_score": format(item["stability_score"], "f"),
            "final_verdict": item["final_verdict"],
        }

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "source": source,
        "candles_seen": len(candles),
        "run_label": run_label,
        "candidate_count": len(specs),
        "splits_tested": split_index,
        "split_results_created": split_index * len(specs),
        "summary_results_created": len(specs),
        "approved_count": len(approved),
        "rejected_or_insufficient": len(ranked) - len(approved),
        "best_candidate": clean(best_candidate),
        "ranked_candidates": [clean(item) for item in ranked],
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
    parser.add_argument("--run-label", default="mission_17_walk_forward_candidate_lab")

    args = parser.parse_args()

    print("DeltaGrid Walk-Forward Candidate Lab")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_walk_forward_candidate_lab(
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
