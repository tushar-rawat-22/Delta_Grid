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
    CREATE TABLE IF NOT EXISTS strategy_candidate_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        source TEXT NOT NULL,
        run_label TEXT NOT NULL,
        strategy_name TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
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
            dd = ((peak - value) / peak) * Decimal("100")
            worst = max(worst, dd)

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


def moving_average(values: list[Decimal], index: int, window: int) -> Decimal | None:
    if index + 1 < window:
        return None

    data = values[index + 1 - window:index + 1]

    return sum(data, Decimal("0")) / Decimal(window)


def result_verdict(
    net_return: Decimal,
    benchmark_return: Decimal,
    drawdown: Decimal,
    sharpe_value: Decimal,
    profit_factor: Decimal,
    trades_count: int,
) -> str:
    if trades_count < 3:
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


def rank_score(
    net_return: Decimal,
    benchmark_return: Decimal,
    drawdown: Decimal,
    sharpe_value: Decimal,
    profit_factor: Decimal,
    win_rate: Decimal,
    trades_count: int,
    verdict: str,
) -> Decimal:
    score = Decimal("0")

    score += net_return
    score += net_return - benchmark_return
    score -= drawdown
    score += sharpe_value * Decimal("10")
    score += profit_factor * Decimal("5")
    score += win_rate * Decimal("0.1")
    score += Decimal(trades_count) * Decimal("0.25")

    if verdict == "GO_FOR_RESEARCH":
        score += Decimal("50")
    elif verdict == "INSUFFICIENT_SAMPLE":
        score -= Decimal("20")
    else:
        score -= Decimal("40")

    return score


def benchmark_return(
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


def build_result(
    strategy_name: str,
    strategy_version: str,
    equity: list[Decimal],
    pnls: list[Decimal],
    initial_capital: Decimal,
    benchmark: Decimal,
) -> dict:
    net = pct(initial_capital, equity[-1])
    dd = max_drawdown(equity)
    sharpe_value = sharpe(equity)
    pf, win_rate, trades = profit_stats(pnls)

    verdict = result_verdict(
        net,
        benchmark,
        dd,
        sharpe_value,
        pf,
        trades,
    )

    score = rank_score(
        net,
        benchmark,
        dd,
        sharpe_value,
        pf,
        win_rate,
        trades,
        verdict,
    )

    return {
        "strategy_name": strategy_name,
        "strategy_version": strategy_version,
        "net_return_pct": net,
        "benchmark_return_pct": benchmark,
        "excess_return_pct": net - benchmark,
        "max_drawdown_pct": dd,
        "sharpe_ratio": sharpe_value,
        "profit_factor": pf,
        "win_rate_pct": win_rate,
        "trades_count": trades,
        "rank_score": score,
        "verdict": verdict,
    }


def run_ma_crossover(
    candles: list[dict],
    initial_capital: Decimal,
    fast_window: int,
    slow_window: int,
    fee_bps: int,
    slippage_bps: int,
    benchmark: Decimal,
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

        fast = moving_average(closes, index, fast_window)
        slow = moving_average(closes, index, slow_window)

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

    return build_result(
        "ma_crossover",
        f"fast_{fast_window}_slow_{slow_window}",
        equity,
        pnls,
        initial_capital,
        benchmark,
    )


def run_momentum(
    candles: list[dict],
    initial_capital: Decimal,
    lookback: int,
    threshold_bps: int,
    hold_days: int,
    fee_bps: int,
    slippage_bps: int,
    benchmark: Decimal,
) -> dict:
    cost = Decimal(fee_bps + slippage_bps) / Decimal("10000")
    threshold = Decimal(threshold_bps) / Decimal("10000")

    cash = initial_capital
    units = Decimal("0")
    entry_value = Decimal("0")
    entry_index = -1

    equity = []
    pnls = []

    for index, candle in enumerate(candles):
        close = candle["close"]

        if index >= lookback:
            old_close = candles[index - lookback]["close"]
            momentum = (close - old_close) / old_close

            if units == 0 and momentum > threshold:
                buy_price = close * (Decimal("1") + cost)
                units = cash / buy_price
                entry_value = cash
                cash = Decimal("0")
                entry_index = index

            elif units > 0:
                held = index - entry_index

                if held >= hold_days or momentum <= Decimal("0"):
                    sell_price = close * (Decimal("1") - cost)
                    cash = units * sell_price
                    pnls.append(cash - entry_value)
                    units = Decimal("0")
                    entry_value = Decimal("0")
                    entry_index = -1

        equity.append(cash + units * close)

    if units > 0:
        sell_price = candles[-1]["close"] * (Decimal("1") - cost)
        cash = units * sell_price
        pnls.append(cash - entry_value)
        equity[-1] = cash

    return build_result(
        "momentum",
        f"lookback_{lookback}_threshold_{threshold_bps}_hold_{hold_days}",
        equity,
        pnls,
        initial_capital,
        benchmark,
    )


def run_breakout(
    candles: list[dict],
    initial_capital: Decimal,
    window: int,
    fee_bps: int,
    slippage_bps: int,
    benchmark: Decimal,
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

        if index >= window:
            previous_high = max(
                item["high"]
                for item in candles[index - window:index]
            )

            ma = moving_average(closes, index, window)

            if units == 0 and close > previous_high:
                buy_price = close * (Decimal("1") + cost)
                units = cash / buy_price
                entry_value = cash
                cash = Decimal("0")

            elif units > 0 and ma is not None and close < ma:
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

    return build_result(
        "breakout",
        f"window_{window}",
        equity,
        pnls,
        initial_capital,
        benchmark,
    )


def run_mean_reversion(
    candles: list[dict],
    initial_capital: Decimal,
    window: int,
    deviation_bps: int,
    fee_bps: int,
    slippage_bps: int,
    benchmark: Decimal,
) -> dict:
    closes = [candle["close"] for candle in candles]
    cost = Decimal(fee_bps + slippage_bps) / Decimal("10000")
    deviation = Decimal(deviation_bps) / Decimal("10000")

    cash = initial_capital
    units = Decimal("0")
    entry_value = Decimal("0")

    equity = []
    pnls = []

    for index, candle in enumerate(candles):
        close = candle["close"]
        ma = moving_average(closes, index, window)

        if ma is not None:
            lower_band = ma * (Decimal("1") - deviation)

            if units == 0 and close < lower_band:
                buy_price = close * (Decimal("1") + cost)
                units = cash / buy_price
                entry_value = cash
                cash = Decimal("0")

            elif units > 0 and close >= ma:
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

    return build_result(
        "mean_reversion",
        f"window_{window}_deviation_{deviation_bps}",
        equity,
        pnls,
        initial_capital,
        benchmark,
    )


def insert_result(
    db_path: str,
    chain_id: int,
    symbol: str,
    timeframe: str,
    source: str,
    run_label: str,
    result: dict,
    assumptions: dict,
) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO strategy_candidate_results (
        chain_id,
        symbol,
        timeframe,
        source,
        run_label,
        strategy_name,
        strategy_version,
        net_return_pct,
        benchmark_return_pct,
        excess_return_pct,
        max_drawdown_pct,
        sharpe_ratio,
        profit_factor,
        win_rate_pct,
        trades_count,
        rank_score,
        verdict,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chain_id,
        symbol.upper(),
        timeframe,
        source,
        run_label,
        result["strategy_name"],
        result["strategy_version"],
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


def run_candidate_lab(
    db_path: str,
    chain_id: int,
    symbol: str,
    timeframe: str,
    source: str,
    initial_capital: Decimal,
    fee_bps: int,
    slippage_bps: int,
    run_label: str,
) -> dict:
    db_path = resolve_db_path(db_path)

    init_market_database(db_path)
    ensure_schema(db_path)

    candles = load_candles(
        db_path,
        chain_id,
        symbol,
        timeframe,
        source,
    )

    if len(candles) < 100:
        raise ValueError("Need at least 100 candles for candidate lab")

    benchmark = benchmark_return(
        candles,
        initial_capital,
        fee_bps,
        slippage_bps,
    )

    assumptions = {
        "initial_capital": format(initial_capital, "f"),
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "benchmark": "buy_and_hold",
        "research_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
    }

    candidates = [
        run_ma_crossover(candles, initial_capital, 10, 30, fee_bps, slippage_bps, benchmark),
        run_ma_crossover(candles, initial_capital, 20, 60, fee_bps, slippage_bps, benchmark),
        run_momentum(candles, initial_capital, 20, 300, 10, fee_bps, slippage_bps, benchmark),
        run_breakout(candles, initial_capital, 20, fee_bps, slippage_bps, benchmark),
        run_mean_reversion(candles, initial_capital, 20, 500, fee_bps, slippage_bps, benchmark),
    ]

    stored = []

    for result in candidates:
        row_id = insert_result(
            db_path,
            chain_id,
            symbol,
            timeframe,
            source,
            run_label,
            result,
            assumptions,
        )

        clean = {
            "id": row_id,
            "strategy_name": result["strategy_name"],
            "strategy_version": result["strategy_version"],
            "net_return_pct": format(result["net_return_pct"], "f"),
            "benchmark_return_pct": format(result["benchmark_return_pct"], "f"),
            "excess_return_pct": format(result["excess_return_pct"], "f"),
            "max_drawdown_pct": format(result["max_drawdown_pct"], "f"),
            "sharpe_ratio": format(result["sharpe_ratio"], "f"),
            "profit_factor": format(result["profit_factor"], "f"),
            "win_rate_pct": format(result["win_rate_pct"], "f"),
            "trades_count": result["trades_count"],
            "rank_score": format(result["rank_score"], "f"),
            "verdict": result["verdict"],
        }

        stored.append(clean)

    ranked = sorted(
        stored,
        key=lambda item: Decimal(item["rank_score"]),
        reverse=True,
    )

    approved = [
        item
        for item in ranked
        if item["verdict"] == "GO_FOR_RESEARCH"
    ]

    if approved:
        global_verdict = "RESEARCH_CANDIDATE_FOUND_NO_LIVE_TRADING"
        best_candidate = approved[0]
    else:
        global_verdict = "REJECT_ALL_NO_LIVE_TRADING"
        best_candidate = ranked[0]

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "source": source,
        "candles_seen": len(candles),
        "run_label": run_label,
        "candidate_count": len(ranked),
        "approved_count": len(approved),
        "rejected_or_insufficient": len(ranked) - len(approved),
        "best_candidate": best_candidate,
        "ranked_candidates": ranked,
        "global_verdict": global_verdict,
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--chain-id", type=int, default=0)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--source", default="binance_spot")
    parser.add_argument("--initial-capital", default="10000")
    parser.add_argument("--fee-bps", type=int, default=10)
    parser.add_argument("--slippage-bps", type=int, default=10)
    parser.add_argument("--run-label", default="mission_15_candidate_lab")

    args = parser.parse_args()

    print("DeltaGrid Strategy Candidate Lab")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_candidate_lab(
        db_path=args.db_path,
        chain_id=args.chain_id,
        symbol=args.symbol,
        timeframe=args.timeframe,
        source=args.source,
        initial_capital=Decimal(args.initial_capital),
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
        run_label=args.run_label,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
