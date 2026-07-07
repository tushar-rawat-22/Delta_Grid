import argparse
import json
import math
import os
import sys
from decimal import Decimal, getcontext
from pathlib import Path

from dotenv import load_dotenv


getcontext().prec = 40

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from backtest.backtest_engine import run_ma_crossover_backtest
from backtest.metrics import profit_factor, win_rate_pct
from db.schema import (
    init_market_database,
    insert_market_regime_label,
    insert_strategy_regime_metric,
    list_backtest_trades,
    list_historical_candles,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")
DEFAULT_CHAIN_ID = 84532


def resolve_db_path(db_path: str) -> str:
    candidate = Path(db_path)

    if candidate.is_absolute():
        return str(candidate)

    return str(OFFCHAIN_ROOT / candidate)


def classify_trend(rolling_return_pct: float) -> str:
    if rolling_return_pct >= 5.0:
        return "bull"

    if rolling_return_pct <= -5.0:
        return "bear"

    return "sideways"


def classify_volatility(rolling_volatility_pct: float) -> str:
    if rolling_volatility_pct >= 2.0:
        return "high_volatility"

    return "low_volatility"


def standard_deviation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0

    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)

    return math.sqrt(variance)


def build_regime_labels(
    candles: list[dict],
    window: int = 30,
) -> dict[str, dict]:
    labels: dict[str, dict] = {}

    closes = [Decimal(candle["close"]) for candle in candles]

    for index, candle in enumerate(candles):
        timestamp = candle["timestamp_utc"]

        if index < window:
            rolling_return_pct = 0.0
            rolling_volatility_pct = 0.0
            trend_regime = "unknown"
            volatility_regime = "unknown"
        else:
            start_close = closes[index - window]
            end_close = closes[index]

            rolling_return_pct = float(((end_close - start_close) / start_close) * Decimal(100))

            returns = []

            for j in range(index - window + 1, index + 1):
                previous = closes[j - 1]
                current = closes[j]

                if previous > 0:
                    returns.append(float((current - previous) / previous) * 100)

            rolling_volatility_pct = standard_deviation(returns)

            trend_regime = classify_trend(rolling_return_pct)
            volatility_regime = classify_volatility(rolling_volatility_pct)

        labels[timestamp] = {
            "trend_regime": trend_regime,
            "volatility_regime": volatility_regime,
            "rolling_return_pct": rolling_return_pct,
            "rolling_volatility_pct": rolling_volatility_pct,
        }

    return labels


def store_regime_labels(
    db_path: str,
    chain_id: int,
    symbol: str,
    timeframe: str,
    labels: dict[str, dict],
    source: str,
) -> int:
    count = 0

    for timestamp, label in labels.items():
        insert_market_regime_label(
            db_path=db_path,
            chain_id=chain_id,
            symbol=symbol,
            timeframe=timeframe,
            timestamp_utc=timestamp,
            trend_regime=label["trend_regime"],
            volatility_regime=label["volatility_regime"],
            rolling_return_pct=str(label["rolling_return_pct"]),
            rolling_volatility_pct=str(label["rolling_volatility_pct"]),
            source=source,
        )

        count += 1

    return count


def regime_verdict(
    trades_count: int,
    net_pnl: float,
    pf: float,
    win_rate: float,
) -> tuple[str, str]:
    if trades_count < 5:
        return "INSUFFICIENT_SAMPLE", "Too few trades for confidence."

    if net_pnl > 0 and pf >= 1.2 and win_rate >= 45:
        return "GO_FOR_RESEARCH", "Regime shows positive research evidence."

    return "NO_GO", "Regime performance is not strong enough."


def aggregate_by_regime(
    trades: list[dict],
    labels: dict[str, dict],
    regime_key: str,
) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}

    for trade in trades:
        exit_time = trade["exit_timestamp_utc"]
        label = labels.get(exit_time)

        if not label:
            regime_name = "unknown"
        else:
            regime_name = label[regime_key]

        grouped.setdefault(regime_name, []).append(trade)

    output: dict[str, dict] = {}

    for regime_name, regime_trades in grouped.items():
        pnls = [float(Decimal(trade["net_pnl"])) for trade in regime_trades]
        costs = [float(Decimal(trade["costs"])) for trade in regime_trades]

        net_pnl = sum(pnls)
        avg_pnl = net_pnl / len(pnls) if pnls else 0.0
        pf = profit_factor(pnls)
        win_rate = win_rate_pct(pnls)
        total_costs = sum(costs)

        verdict, notes = regime_verdict(
            trades_count=len(regime_trades),
            net_pnl=net_pnl,
            pf=pf,
            win_rate=win_rate,
        )

        output[regime_name] = {
            "trades_count": len(regime_trades),
            "net_pnl": net_pnl,
            "avg_trade_pnl": avg_pnl,
            "profit_factor": pf,
            "win_rate_pct": win_rate,
            "total_costs": total_costs,
            "verdict": verdict,
            "notes": notes,
        }

    return output


def run_strategy_regime_analysis(
    db_path: str,
    chain_id: int,
    symbol: str,
    timeframe: str,
    source: str = "synthetic_regime_v1",
    regime_window: int = 30,
    initial_capital: str = "10000",
    fast_window: int = 10,
    slow_window: int = 30,
    fee_bps: int = 10,
    slippage_bps: int = 10,
) -> dict:
    resolved_db_path = resolve_db_path(db_path)

    init_market_database(resolved_db_path)

    candles = list_historical_candles(
        db_path=resolved_db_path,
        chain_id=chain_id,
        symbol=symbol,
        timeframe=timeframe,
        source=source,
    )

    if len(candles) < regime_window + slow_window:
        raise ValueError("Not enough candles for regime analysis.")

    labels = build_regime_labels(candles, window=regime_window)

    labels_stored = store_regime_labels(
        db_path=resolved_db_path,
        chain_id=chain_id,
        symbol=symbol,
        timeframe=timeframe,
        labels=labels,
        source=source,
    )

    backtest_result = run_ma_crossover_backtest(
        db_path=resolved_db_path,
        chain_id=chain_id,
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        initial_capital=initial_capital,
        fast_window=fast_window,
        slow_window=slow_window,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )

    run_id = backtest_result["run_id"]
    trades = list_backtest_trades(resolved_db_path, run_id)

    trend_metrics = aggregate_by_regime(
        trades=trades,
        labels=labels,
        regime_key="trend_regime",
    )

    volatility_metrics = aggregate_by_regime(
        trades=trades,
        labels=labels,
        regime_key="volatility_regime",
    )

    metrics_stored = 0

    for regime_name, metric in trend_metrics.items():
        insert_strategy_regime_metric(
            db_path=resolved_db_path,
            run_id=run_id,
            regime_type="trend",
            regime_name=regime_name,
            trades_count=metric["trades_count"],
            net_pnl=str(metric["net_pnl"]),
            avg_trade_pnl=str(metric["avg_trade_pnl"]),
            profit_factor=str(metric["profit_factor"]),
            win_rate_pct=str(metric["win_rate_pct"]),
            total_costs=str(metric["total_costs"]),
            verdict=metric["verdict"],
            notes=metric["notes"],
        )
        metrics_stored += 1

    for regime_name, metric in volatility_metrics.items():
        insert_strategy_regime_metric(
            db_path=resolved_db_path,
            run_id=run_id,
            regime_type="volatility",
            regime_name=regime_name,
            trades_count=metric["trades_count"],
            net_pnl=str(metric["net_pnl"]),
            avg_trade_pnl=str(metric["avg_trade_pnl"]),
            profit_factor=str(metric["profit_factor"]),
            win_rate_pct=str(metric["win_rate_pct"]),
            total_costs=str(metric["total_costs"]),
            verdict=metric["verdict"],
            notes=metric["notes"],
        )
        metrics_stored += 1

    return {
        "run_id": run_id,
        "labels_stored": labels_stored,
        "metrics_stored": metrics_stored,
        "trades_count": len(trades),
        "trend_metrics": trend_metrics,
        "volatility_metrics": volatility_metrics,
        "backtest_result": backtest_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DeltaGrid strategy regime analysis")

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--chain-id", type=int, default=DEFAULT_CHAIN_ID)
    parser.add_argument("--symbol", default="WETH_USDC_DEMO")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--source", default="synthetic_regime_v1")
    parser.add_argument("--regime-window", type=int, default=30)
    parser.add_argument("--initial-capital", default="10000")
    parser.add_argument("--fast-window", type=int, default=10)
    parser.add_argument("--slow-window", type=int, default=30)
    parser.add_argument("--fee-bps", type=int, default=10)
    parser.add_argument("--slippage-bps", type=int, default=10)

    args = parser.parse_args()

    print("DeltaGrid Strategy Regime Analysis")
    print("Mode: research analysis only")
    print("No private keys. No signing. No real trades.")

    result = run_strategy_regime_analysis(
        db_path=args.db_path,
        chain_id=args.chain_id,
        symbol=args.symbol,
        timeframe=args.timeframe,
        source=args.source,
        regime_window=args.regime_window,
        initial_capital=args.initial_capital,
        fast_window=args.fast_window,
        slow_window=args.slow_window,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
