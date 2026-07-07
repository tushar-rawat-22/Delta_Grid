import argparse
import json
import os
import sys
from decimal import Decimal, getcontext
from pathlib import Path

from dotenv import load_dotenv


getcontext().prec = 40

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from backtest.metrics import (
    max_drawdown_pct,
    profit_factor,
    sharpe_ratio,
    win_rate_pct,
)
from db.schema import (
    init_market_database,
    insert_backtest_run,
    insert_backtest_trade,
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


def moving_average(values: list[Decimal], end_index: int, window: int) -> Decimal | None:
    if end_index + 1 < window:
        return None

    window_values = values[end_index - window + 1:end_index + 1]

    return sum(window_values) / Decimal(window)


def run_ma_crossover_backtest(
    db_path: str,
    chain_id: int,
    symbol: str,
    timeframe: str,
    source: str = "synthetic_regime_v1",
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

    if len(candles) < slow_window + 2:
        raise ValueError("Not enough candles for backtest.")

    closes = [Decimal(candle["close"]) for candle in candles]

    cost_rate = Decimal(fee_bps + slippage_bps) / Decimal(10000)

    cash = Decimal(initial_capital)
    position_qty = Decimal("0")
    entry_price = None
    entry_time = None
    entry_cash = None

    equity_curve: list[float] = []
    trades: list[dict] = []
    total_costs = Decimal("0")

    for i, candle in enumerate(candles):
        close_price = Decimal(candle["close"])

        equity = cash + (position_qty * close_price)
        equity_curve.append(float(equity))

        fast_ma = moving_average(closes, i, fast_window)
        slow_ma = moving_average(closes, i, slow_window)

        if fast_ma is None or slow_ma is None:
            continue

        should_be_long = fast_ma > slow_ma
        should_exit = fast_ma < slow_ma

        if position_qty == 0 and should_be_long:
            fill_price = close_price * (Decimal("1") + cost_rate)
            entry_cash = cash
            position_qty = cash / fill_price
            entry_price = fill_price
            entry_time = candle["timestamp_utc"]
            entry_cost = cash * cost_rate
            total_costs += entry_cost
            cash = Decimal("0")

        elif position_qty > 0 and should_exit:
            fill_price = close_price * (Decimal("1") - cost_rate)
            exit_value = position_qty * fill_price
            exit_cost = (position_qty * close_price) * cost_rate
            total_costs += exit_cost

            gross_exit_value = position_qty * close_price
            gross_pnl = gross_exit_value - entry_cash
            net_pnl = exit_value - entry_cash
            return_pct = (net_pnl / entry_cash) * Decimal(100)

            trades.append({
                "entry_timestamp_utc": entry_time,
                "exit_timestamp_utc": candle["timestamp_utc"],
                "side": "long",
                "entry_price": format(entry_price, "f"),
                "exit_price": format(fill_price, "f"),
                "quantity": format(position_qty, "f"),
                "gross_pnl": format(gross_pnl, "f"),
                "costs": format(entry_cash * cost_rate + exit_cost, "f"),
                "net_pnl": format(net_pnl, "f"),
                "return_pct": format(return_pct, "f"),
            })

            cash = exit_value
            position_qty = Decimal("0")
            entry_price = None
            entry_time = None
            entry_cash = None

    if position_qty > 0:
        last = candles[-1]
        close_price = Decimal(last["close"])
        fill_price = close_price * (Decimal("1") - cost_rate)
        exit_value = position_qty * fill_price
        exit_cost = (position_qty * close_price) * cost_rate
        total_costs += exit_cost

        gross_exit_value = position_qty * close_price
        gross_pnl = gross_exit_value - entry_cash
        net_pnl = exit_value - entry_cash
        return_pct = (net_pnl / entry_cash) * Decimal(100)

        trades.append({
            "entry_timestamp_utc": entry_time,
            "exit_timestamp_utc": last["timestamp_utc"],
            "side": "long",
            "entry_price": format(entry_price, "f"),
            "exit_price": format(fill_price, "f"),
            "quantity": format(position_qty, "f"),
            "gross_pnl": format(gross_pnl, "f"),
            "costs": format(entry_cash * cost_rate + exit_cost, "f"),
            "net_pnl": format(net_pnl, "f"),
            "return_pct": format(return_pct, "f"),
        })

        cash = exit_value
        position_qty = Decimal("0")

    final_equity = cash
    net_return = ((final_equity - Decimal(initial_capital)) / Decimal(initial_capital)) * Decimal(100)

    trade_pnls = [float(Decimal(trade["net_pnl"])) for trade in trades]

    metrics = {
        "strategy_name": "ma_crossover_baseline",
        "strategy_version": "v1",
        "chain_id": chain_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "start_timestamp_utc": candles[0]["timestamp_utc"],
        "end_timestamp_utc": candles[-1]["timestamp_utc"],
        "initial_capital": initial_capital,
        "final_equity": format(final_equity, "f"),
        "net_return_pct": format(net_return, "f"),
        "max_drawdown_pct": str(max_drawdown_pct(equity_curve)),
        "sharpe_ratio": str(sharpe_ratio(equity_curve)),
        "profit_factor": str(profit_factor(trade_pnls)),
        "win_rate_pct": str(win_rate_pct(trade_pnls)),
        "trades_count": len(trades),
        "total_costs": format(total_costs, "f"),
        "assumptions": {
            "source": source,
            "fast_window": fast_window,
            "slow_window": slow_window,
            "fee_bps": fee_bps,
            "slippage_bps": slippage_bps,
            "synthetic_data_only": True,
            "not_live_trading_approved": True,
        },
        "status": "research_only",
    }

    run_id = insert_backtest_run(
        db_path=resolved_db_path,
        strategy_name=metrics["strategy_name"],
        strategy_version=metrics["strategy_version"],
        chain_id=chain_id,
        symbol=symbol,
        timeframe=timeframe,
        start_timestamp_utc=metrics["start_timestamp_utc"],
        end_timestamp_utc=metrics["end_timestamp_utc"],
        initial_capital=metrics["initial_capital"],
        final_equity=metrics["final_equity"],
        net_return_pct=metrics["net_return_pct"],
        max_drawdown_pct=metrics["max_drawdown_pct"],
        sharpe_ratio=metrics["sharpe_ratio"],
        profit_factor=metrics["profit_factor"],
        win_rate_pct=metrics["win_rate_pct"],
        trades_count=metrics["trades_count"],
        total_costs=metrics["total_costs"],
        assumptions_json=json.dumps(metrics["assumptions"]),
        status=metrics["status"],
    )

    for trade in trades:
        insert_backtest_trade(
            db_path=resolved_db_path,
            run_id=run_id,
            chain_id=chain_id,
            symbol=symbol,
            entry_timestamp_utc=trade["entry_timestamp_utc"],
            exit_timestamp_utc=trade["exit_timestamp_utc"],
            side=trade["side"],
            entry_price=trade["entry_price"],
            exit_price=trade["exit_price"],
            quantity=trade["quantity"],
            gross_pnl=trade["gross_pnl"],
            costs=trade["costs"],
            net_pnl=trade["net_pnl"],
            return_pct=trade["return_pct"],
        )

    metrics["run_id"] = run_id

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="DeltaGrid local backtest engine")

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--chain-id", type=int, default=DEFAULT_CHAIN_ID)
    parser.add_argument("--symbol", default="WETH_USDC_DEMO")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--source", default="synthetic_regime_v1")
    parser.add_argument("--initial-capital", default="10000")
    parser.add_argument("--fast-window", type=int, default=10)
    parser.add_argument("--slow-window", type=int, default=30)
    parser.add_argument("--fee-bps", type=int, default=10)
    parser.add_argument("--slippage-bps", type=int, default=10)

    args = parser.parse_args()

    print("DeltaGrid Backtest Engine")
    print("Mode: research backtest only")
    print("No private keys. No signing. No real trades.")

    result = run_ma_crossover_backtest(
        db_path=args.db_path,
        chain_id=args.chain_id,
        symbol=args.symbol,
        timeframe=args.timeframe,
        source=args.source,
        initial_capital=args.initial_capital,
        fast_window=args.fast_window,
        slow_window=args.slow_window,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
