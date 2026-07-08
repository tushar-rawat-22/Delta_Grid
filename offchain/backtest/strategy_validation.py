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


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def resolve_db_path(db_path: str) -> str:
    path = Path(db_path)

    if path.is_absolute():
        return str(path)

    return str(OFFCHAIN_ROOT / path)


def ensure_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS strategy_validation_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        source TEXT NOT NULL,
        validation_type TEXT NOT NULL,
        split_index INTEGER NOT NULL,
        strategy_name TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
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

    conn.commit()
    conn.close()


def load_candles(
    db_path: str,
    chain_id: int,
    symbol: str,
    timeframe: str,
    source: str,
) -> list[dict]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        timestamp_utc,
        "open",
        high,
        low,
        close,
        volume
    FROM historical_candles
    WHERE chain_id = ?
    AND symbol = ?
    AND timeframe = ?
    AND source = ?
    ORDER BY timestamp_utc
    """, (
        chain_id,
        symbol.upper(),
        timeframe,
        source,
    )).fetchall()

    conn.close()

    return [
        {
            "timestamp_utc": row[0],
            "open": Decimal(str(row[1])),
            "high": Decimal(str(row[2])),
            "low": Decimal(str(row[3])),
            "close": Decimal(str(row[4])),
            "volume": Decimal(str(row[5])),
        }
        for row in rows
    ]


def pct(start: Decimal, end: Decimal) -> Decimal:
    if start == 0:
        return Decimal("0")

    return ((end - start) / start) * Decimal("100")


def max_drawdown(equity: list[Decimal]) -> Decimal:
    peak = equity[0]
    worst = Decimal("0")

    for value in equity:
        peak = max(peak, value)

        if peak > 0:
            drawdown = ((peak - value) / peak) * Decimal("100")
            worst = max(worst, drawdown)

    return worst


def sharpe(equity: list[Decimal]) -> Decimal:
    returns = []

    for old, new in zip(equity, equity[1:]):
        if old > 0:
            returns.append(float((new - old) / old))

    if len(returns) < 2:
        return Decimal("0")

    mean = sum(returns) / len(returns)
    variance = sum((x - mean) ** 2 for x in returns) / (len(returns) - 1)
    std = math.sqrt(variance)

    if std == 0:
        return Decimal("0")

    return Decimal(str((mean / std) * math.sqrt(365)))


def profit_stats(pnls: list[Decimal]) -> tuple[Decimal, Decimal, int]:
    if not pnls:
        return Decimal("0"), Decimal("0"), 0

    wins = [x for x in pnls if x > 0]
    losses = [abs(x) for x in pnls if x < 0]

    win_rate = Decimal(len(wins)) / Decimal(len(pnls)) * Decimal("100")

    gross_profit = sum(wins, Decimal("0"))
    gross_loss = sum(losses, Decimal("0"))

    if gross_loss == 0:
        profit_factor = Decimal("999") if gross_profit > 0 else Decimal("0")
    else:
        profit_factor = gross_profit / gross_loss

    return profit_factor, win_rate, len(pnls)


def verdict(
    net_return: Decimal,
    benchmark_return: Decimal,
    drawdown: Decimal,
    sharpe_value: Decimal,
    profit_factor: Decimal,
    trades: int,
) -> str:
    if trades < 3:
        return "INSUFFICIENT_SAMPLE"

    if net_return <= benchmark_return:
        return "NO_GO_UNDERPERFORMS_BENCHMARK"

    if drawdown > Decimal("30"):
        return "NO_GO_DRAWDOWN_TOO_HIGH"

    if sharpe_value < Decimal("0.75"):
        return "NO_GO_WEAK_SHARPE"

    if profit_factor < Decimal("1.3"):
        return "NO_GO_WEAK_PROFIT_FACTOR"

    return "GO_FOR_RESEARCH"


def buy_and_hold_return(
    candles: list[dict],
    initial_capital: Decimal,
    fee_bps: int,
    slippage_bps: int,
) -> Decimal:
    cost = Decimal(fee_bps + slippage_bps) / Decimal("10000")

    entry = candles[0]["close"] * (Decimal("1") + cost)
    exit_ = candles[-1]["close"] * (Decimal("1") - cost)

    units = initial_capital / entry
    final_value = units * exit_

    return pct(initial_capital, final_value)


def ma_value(values: list[Decimal], index: int, window: int) -> Decimal | None:
    if index + 1 < window:
        return None

    data = values[index + 1 - window:index + 1]

    return sum(data, Decimal("0")) / Decimal(window)


def run_ma_strategy(
    candles: list[dict],
    initial_capital: Decimal,
    fast_window: int,
    slow_window: int,
    fee_bps: int,
    slippage_bps: int,
    benchmark_return: Decimal,
) -> dict:
    closes = [candle["close"] for candle in candles]
    cost = Decimal(fee_bps + slippage_bps) / Decimal("10000")

    cash = initial_capital
    units = Decimal("0")
    entry_value = Decimal("0")

    equity = []
    pnls = []

    for index, candle in enumerate(candles):
        close = candle["close"]

        fast = ma_value(closes, index, fast_window)
        slow = ma_value(closes, index, slow_window)

        if fast is not None and slow is not None:
            if fast > slow and units == 0:
                buy_price = close * (Decimal("1") + cost)
                units = cash / buy_price
                entry_value = cash
                cash = Decimal("0")

            elif fast <= slow and units > 0:
                sell_price = close * (Decimal("1") - cost)
                cash = units * sell_price
                pnls.append(cash - entry_value)
                units = Decimal("0")
                entry_value = Decimal("0")

        equity.append(cash + units * close)

    if units > 0:
        sell_price = candles[-1]["close"] * (Decimal("1") - cost)
        cash = units * sell_price
        pnls.append(cash - entry_value)
        equity[-1] = cash

    net_return = pct(initial_capital, equity[-1])
    drawdown = max_drawdown(equity)
    sharpe_value = sharpe(equity)
    profit_factor, win_rate, trades = profit_stats(pnls)

    return {
        "strategy_name": "ma_crossover_baseline",
        "strategy_version": f"fast_{fast_window}_slow_{slow_window}",
        "net_return_pct": net_return,
        "benchmark_return_pct": benchmark_return,
        "excess_return_pct": net_return - benchmark_return,
        "max_drawdown_pct": drawdown,
        "sharpe_ratio": sharpe_value,
        "profit_factor": profit_factor,
        "win_rate_pct": win_rate,
        "trades_count": trades,
        "verdict": verdict(
            net_return,
            benchmark_return,
            drawdown,
            sharpe_value,
            profit_factor,
            trades,
        ),
    }


def insert_result(
    db_path: str,
    chain_id: int,
    symbol: str,
    timeframe: str,
    source: str,
    validation_type: str,
    split_index: int,
    candles: list[dict],
    result: dict,
    assumptions: dict,
) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO strategy_validation_results (
        chain_id,
        symbol,
        timeframe,
        source,
        validation_type,
        split_index,
        strategy_name,
        strategy_version,
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
        validation_type,
        split_index,
        result["strategy_name"],
        result["strategy_version"],
        candles[0]["timestamp_utc"],
        candles[-1]["timestamp_utc"],
        format(result["net_return_pct"], "f"),
        format(result["benchmark_return_pct"], "f"),
        format(result["excess_return_pct"], "f"),
        format(result["max_drawdown_pct"], "f"),
        format(result["sharpe_ratio"], "f"),
        format(result["profit_factor"], "f"),
        format(result["win_rate_pct"], "f"),
        result["trades_count"],
        result["verdict"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def run_strategy_validation(
    db_path: str,
    chain_id: int,
    symbol: str,
    timeframe: str,
    source: str,
    initial_capital: Decimal,
    fast_window: int,
    slow_window: int,
    fee_bps: int,
    slippage_bps: int,
    train_size: int,
    test_size: int,
    step_size: int,
) -> dict:
    db_path = resolve_db_path(db_path)

    init_market_database(db_path)
    ensure_schema(db_path)

    candles = load_candles(db_path, chain_id, symbol, timeframe, source)

    if len(candles) < slow_window + test_size:
        raise ValueError("Not enough candles for validation")

    assumptions = {
        "initial_capital": format(initial_capital, "f"),
        "fast_window": fast_window,
        "slow_window": slow_window,
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "train_size": train_size,
        "test_size": test_size,
        "step_size": step_size,
        "research_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
    }

    benchmark = buy_and_hold_return(candles, initial_capital, fee_bps, slippage_bps)

    full = run_ma_strategy(
        candles,
        initial_capital,
        fast_window,
        slow_window,
        fee_bps,
        slippage_bps,
        benchmark,
    )

    full_id = insert_result(
        db_path,
        chain_id,
        symbol,
        timeframe,
        source,
        "full_period",
        -1,
        candles,
        full,
        assumptions,
    )

    split_results = []

    start = 0
    split_index = 0

    while start + train_size + test_size <= len(candles):
        test = candles[start + train_size:start + train_size + test_size]

        split_benchmark = buy_and_hold_return(
            test,
            initial_capital,
            fee_bps,
            slippage_bps,
        )

        split = run_ma_strategy(
            test,
            initial_capital,
            fast_window,
            slow_window,
            fee_bps,
            slippage_bps,
            split_benchmark,
        )

        row_id = insert_result(
            db_path,
            chain_id,
            symbol,
            timeframe,
            source,
            "walk_forward_test",
            split_index,
            test,
            split,
            assumptions,
        )

        split_results.append({
            "id": row_id,
            "split_index": split_index,
            "net_return_pct": format(split["net_return_pct"], "f"),
            "benchmark_return_pct": format(split["benchmark_return_pct"], "f"),
            "excess_return_pct": format(split["excess_return_pct"], "f"),
            "max_drawdown_pct": format(split["max_drawdown_pct"], "f"),
            "sharpe_ratio": format(split["sharpe_ratio"], "f"),
            "profit_factor": format(split["profit_factor"], "f"),
            "trades_count": split["trades_count"],
            "verdict": split["verdict"],
        })

        split_index += 1
        start += step_size

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "source": source,
        "candles_seen": len(candles),
        "full_period_result_id": full_id,
        "full_period": {
            "net_return_pct": format(full["net_return_pct"], "f"),
            "benchmark_return_pct": format(full["benchmark_return_pct"], "f"),
            "excess_return_pct": format(full["excess_return_pct"], "f"),
            "max_drawdown_pct": format(full["max_drawdown_pct"], "f"),
            "sharpe_ratio": format(full["sharpe_ratio"], "f"),
            "profit_factor": format(full["profit_factor"], "f"),
            "trades_count": full["trades_count"],
            "verdict": full["verdict"],
        },
        "walk_forward": {
            "splits": len(split_results),
            "go_for_research": sum(1 for x in split_results if x["verdict"] == "GO_FOR_RESEARCH"),
            "rejected_or_insufficient": sum(1 for x in split_results if x["verdict"] != "GO_FOR_RESEARCH"),
            "results": split_results,
        },
        "global_verdict": "RESEARCH_ONLY_NO_LIVE_TRADING",
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--chain-id", type=int, default=0)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--source", default="binance_spot")
    parser.add_argument("--initial-capital", default="10000")
    parser.add_argument("--fast-window", type=int, default=10)
    parser.add_argument("--slow-window", type=int, default=30)
    parser.add_argument("--fee-bps", type=int, default=10)
    parser.add_argument("--slippage-bps", type=int, default=10)
    parser.add_argument("--train-size", type=int, default=365)
    parser.add_argument("--test-size", type=int, default=180)
    parser.add_argument("--step-size", type=int, default=180)

    args = parser.parse_args()

    print("DeltaGrid Strategy Validation Engine")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_strategy_validation(
        db_path=args.db_path,
        chain_id=args.chain_id,
        symbol=args.symbol,
        timeframe=args.timeframe,
        source=args.source,
        initial_capital=Decimal(args.initial_capital),
        fast_window=args.fast_window,
        slow_window=args.slow_window,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
        train_size=args.train_size,
        test_size=args.test_size,
        step_size=args.step_size,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
