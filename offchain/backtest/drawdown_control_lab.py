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

from backtest.strategy_candidate_lab import (
    benchmark_return,
    build_result,
    load_candles,
    moving_average,
    resolve_db_path,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def ensure_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS drawdown_control_results (
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


def rolling_volatility_pct(candles: list[dict], index: int, window: int) -> Decimal | None:
    if index < window:
        return None

    returns = []

    for i in range(index - window + 1, index + 1):
        old = candles[i - 1]["close"]
        new = candles[i]["close"]

        if old > 0:
            returns.append((new - old) / old)

    if len(returns) < 2:
        return None

    mean = sum(returns, Decimal("0")) / Decimal(len(returns))

    variance = sum((item - mean) ** 2 for item in returns) / Decimal(len(returns) - 1)

    return variance.sqrt() * Decimal("365").sqrt() * Decimal("100")


def run_controlled_ma_strategy(
    candles: list[dict],
    initial_capital: Decimal,
    fast_window: int,
    slow_window: int,
    fee_bps: int,
    slippage_bps: int,
    benchmark: Decimal,
    stop_loss_pct: Decimal | None,
    trailing_stop_pct: Decimal | None,
    volatility_window: int | None,
    max_volatility_pct: Decimal | None,
    drawdown_guard_pct: Decimal | None,
    cooldown_days: int,
) -> dict:
    closes = [candle["close"] for candle in candles]
    cost = Decimal(fee_bps + slippage_bps) / Decimal("10000")

    cash = initial_capital
    units = Decimal("0")
    entry_value = Decimal("0")
    entry_price = Decimal("0")
    highest_price = Decimal("0")

    equity = []
    pnls = []

    cooldown = 0
    equity_peak = initial_capital

    for index, candle in enumerate(candles):
        close = candle["close"]

        if cooldown > 0:
            cooldown -= 1

        current_equity = cash + units * close
        equity_peak = max(equity_peak, current_equity)

        current_drawdown = Decimal("0")

        if equity_peak > 0:
            current_drawdown = ((equity_peak - current_equity) / equity_peak) * Decimal("100")

        fast = moving_average(closes, index, fast_window)
        slow = moving_average(closes, index, slow_window)

        vol_allowed = True

        if volatility_window is not None and max_volatility_pct is not None:
            vol = rolling_volatility_pct(candles, index, volatility_window)

            if vol is not None and vol > max_volatility_pct:
                vol_allowed = False

        if units > 0:
            highest_price = max(highest_price, close)

            exit_signal = False

            if fast is not None and slow is not None and fast <= slow:
                exit_signal = True

            if stop_loss_pct is not None:
                stop_price = entry_price * (Decimal("1") - stop_loss_pct / Decimal("100"))

                if close <= stop_price:
                    exit_signal = True

            if trailing_stop_pct is not None:
                trail_price = highest_price * (Decimal("1") - trailing_stop_pct / Decimal("100"))

                if close <= trail_price:
                    exit_signal = True

            if drawdown_guard_pct is not None and current_drawdown > drawdown_guard_pct:
                exit_signal = True
                cooldown = cooldown_days

            if not vol_allowed:
                exit_signal = True

            if exit_signal:
                sell_price = close * (Decimal("1") - cost)
                cash = units * sell_price
                pnls.append(cash - entry_value)

                units = Decimal("0")
                entry_value = Decimal("0")
                entry_price = Decimal("0")
                highest_price = Decimal("0")

        elif fast is not None and slow is not None:
            if cooldown == 0 and vol_allowed and fast > slow:
                if drawdown_guard_pct is None or current_drawdown <= drawdown_guard_pct:
                    buy_price = close * (Decimal("1") + cost)
                    units = cash / buy_price
                    entry_value = cash
                    entry_price = buy_price
                    highest_price = close
                    cash = Decimal("0")

        equity.append(cash + units * close)

    if units > 0:
        sell_price = candles[-1]["close"] * (Decimal("1") - cost)
        cash = units * sell_price
        pnls.append(cash - entry_value)
        equity[-1] = cash

    parts = [
        f"fast_{fast_window}",
        f"slow_{slow_window}",
    ]

    if stop_loss_pct is not None:
        parts.append(f"stop_{stop_loss_pct}")

    if trailing_stop_pct is not None:
        parts.append(f"trail_{trailing_stop_pct}")

    if max_volatility_pct is not None:
        parts.append(f"maxvol_{max_volatility_pct}")

    if drawdown_guard_pct is not None:
        parts.append(f"ddguard_{drawdown_guard_pct}")

    if cooldown_days > 0:
        parts.append(f"cooldown_{cooldown_days}")

    return build_result(
        "controlled_ma",
        "_".join(parts),
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
    INSERT INTO drawdown_control_results (
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


def run_drawdown_control_lab(
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

    candles = load_candles(db_path, chain_id, symbol, timeframe, source)

    if len(candles) < 120:
        raise ValueError("Need at least 120 candles for drawdown control lab")

    benchmark = benchmark_return(candles, initial_capital, fee_bps, slippage_bps)

    assumptions = {
        "base_strategy": "mission_15_best_candidate_ma_fast_20_slow_60",
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
        run_controlled_ma_strategy(candles, initial_capital, 20, 60, fee_bps, slippage_bps, benchmark, Decimal("12"), None, None, None, None, 0),
        run_controlled_ma_strategy(candles, initial_capital, 20, 60, fee_bps, slippage_bps, benchmark, Decimal("8"), None, None, None, None, 0),
        run_controlled_ma_strategy(candles, initial_capital, 20, 60, fee_bps, slippage_bps, benchmark, None, Decimal("15"), None, None, None, 0),
        run_controlled_ma_strategy(candles, initial_capital, 20, 60, fee_bps, slippage_bps, benchmark, Decimal("10"), Decimal("15"), 20, Decimal("85"), None, 0),
        run_controlled_ma_strategy(candles, initial_capital, 20, 60, fee_bps, slippage_bps, benchmark, Decimal("10"), Decimal("15"), 20, Decimal("85"), Decimal("25"), 20),
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

        stored.append({
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
        })

    ranked = sorted(stored, key=lambda item: Decimal(item["rank_score"]), reverse=True)

    approved = [item for item in ranked if item["verdict"] == "GO_FOR_RESEARCH"]

    if approved:
        global_verdict = "RISK_CONTROL_CANDIDATE_FOUND_NO_LIVE_TRADING"
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
    parser.add_argument("--run-label", default="mission_16_drawdown_control_lab")

    args = parser.parse_args()

    print("DeltaGrid Drawdown Control Lab")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_drawdown_control_lab(
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
