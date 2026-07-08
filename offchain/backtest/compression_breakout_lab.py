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
    load_candles,
    resolve_db_path,
)

from backtest.indicator_engine import (
    atr,
    bollinger_bandwidth,
    donchian_high,
    donchian_low,
    ema,
    rolling_percentile_rank,
    sma,
    to_decimal,
)

from backtest.regime_kernel import build_regime_features, classify_regime_at


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS compression_breakout_split_results (
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
        go_trades INTEGER NOT NULL,
        compression_signals INTEGER NOT NULL,
        verdict TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS compression_breakout_summary (
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
        total_compression_signals INTEGER NOT NULL,
        stability_score TEXT NOT NULL,
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
            "name": "compression_breakout",
            "version": "donchian55_exit20_bb25_atr60_vol110_ema50",
            "entry_window": 55,
            "exit_window": 20,
            "bb_period": 20,
            "bb_std": "2",
            "bb_percentile_window": 120,
            "bb_max_percentile": "0.25",
            "atr_period": 14,
            "atr_percentile_window": 120,
            "atr_max_percentile": "0.60",
            "volume_sma": 20,
            "volume_mult": "1.10",
            "ema_filter": 50,
            "stop_atr_mult": "2.5",
            "trail_atr_mult": "3.0",
            "false_break_bars": 5,
            "max_hold": 60,
        },
        {
            "name": "compression_breakout",
            "version": "donchian40_exit15_bb30_atr65_vol105_ema50",
            "entry_window": 40,
            "exit_window": 15,
            "bb_period": 20,
            "bb_std": "2",
            "bb_percentile_window": 120,
            "bb_max_percentile": "0.30",
            "atr_period": 14,
            "atr_percentile_window": 120,
            "atr_max_percentile": "0.65",
            "volume_sma": 20,
            "volume_mult": "1.05",
            "ema_filter": 50,
            "stop_atr_mult": "2.5",
            "trail_atr_mult": "3.0",
            "false_break_bars": 5,
            "max_hold": 50,
        },
        {
            "name": "compression_breakout",
            "version": "donchian80_exit30_bb20_atr55_vol120_ema100",
            "entry_window": 80,
            "exit_window": 30,
            "bb_period": 20,
            "bb_std": "2",
            "bb_percentile_window": 120,
            "bb_max_percentile": "0.20",
            "atr_period": 14,
            "atr_percentile_window": 120,
            "atr_max_percentile": "0.55",
            "volume_sma": 20,
            "volume_mult": "1.20",
            "ema_filter": 100,
            "stop_atr_mult": "3.0",
            "trail_atr_mult": "3.5",
            "false_break_bars": 7,
            "max_hold": 80,
        },
    ]


def avg(values):
    if not values:
        return Decimal("0")

    return sum(values, Decimal("0")) / Decimal(len(values))


def percent(value):
    return value * Decimal("100")


def max_drawdown_pct(equity_curve):
    if not equity_curve:
        return Decimal("0")

    peak = equity_curve[0]
    worst = Decimal("0")

    for equity in equity_curve:
        if equity > peak:
            peak = equity

        if peak == 0:
            continue

        drawdown = (peak - equity) / peak * Decimal("100")

        if drawdown > worst:
            worst = drawdown

    return worst


def sharpe_ratio_from_equity(equity_curve):
    if len(equity_curve) < 3:
        return Decimal("0")

    returns = []

    for index in range(1, len(equity_curve)):
        previous = equity_curve[index - 1]
        current = equity_curve[index]

        if previous == 0:
            continue

        returns.append(current / previous - Decimal("1"))

    if len(returns) < 2:
        return Decimal("0")

    mean = sum(returns, Decimal("0")) / Decimal(len(returns))

    variance = sum(
        (value - mean) * (value - mean)
        for value in returns
    ) / Decimal(len(returns))

    std = variance.sqrt()

    if std == 0:
        return Decimal("0")

    return mean / std * Decimal("365").sqrt()


def profit_factor(trade_returns):
    wins = [
        value
        for value in trade_returns
        if value > 0
    ]

    losses = [
        abs(value)
        for value in trade_returns
        if value < 0
    ]

    gross_profit = sum(wins, Decimal("0"))
    gross_loss = sum(losses, Decimal("0"))

    if gross_loss == 0:
        if gross_profit > 0:
            return Decimal("999")

        return Decimal("0")

    return gross_profit / gross_loss


def win_rate_pct(trade_returns):
    if not trade_returns:
        return Decimal("0")

    wins = sum(
        1
        for value in trade_returns
        if value > 0
    )

    return Decimal(wins) / Decimal(len(trade_returns)) * Decimal("100")


def result_verdict(
    net_return_pct,
    excess_return_pct,
    max_drawdown,
    sharpe,
    pf,
    trades_count,
):
    if trades_count < 2:
        return "INSUFFICIENT_TRADES"

    if excess_return_pct <= Decimal("0"):
        return "REJECT_UNDERPERFORMS_BENCHMARK"

    if max_drawdown > Decimal("30"):
        return "REJECT_DRAWDOWN_TOO_HIGH"

    if sharpe < Decimal("0.75"):
        return "REJECT_WEAK_SHARPE"

    if pf < Decimal("1.30"):
        return "REJECT_WEAK_PROFIT_FACTOR"

    if net_return_pct <= Decimal("0"):
        return "REJECT_NEGATIVE_RETURN"

    return "GO_FOR_RESEARCH"


def run_compression_breakout_strategy(
    candles,
    initial_capital,
    entry_window,
    exit_window,
    bb_period,
    bb_std,
    bb_percentile_window,
    bb_max_percentile,
    atr_period,
    atr_percentile_window,
    atr_max_percentile,
    volume_sma,
    volume_mult,
    ema_filter,
    stop_atr_mult,
    trail_atr_mult,
    false_break_bars,
    max_hold,
    fee_bps,
    slippage_bps,
    benchmark,
):
    closes = [to_decimal(candle["close"]) for candle in candles]
    highs = [to_decimal(candle["high"]) for candle in candles]
    lows = [to_decimal(candle["low"]) for candle in candles]
    opens = [to_decimal(candle["open"]) for candle in candles]
    volumes = [to_decimal(candle["volume"]) for candle in candles]

    atr_values = atr(highs, lows, closes, atr_period)
    atr_pct = rolling_percentile_rank(
        [
            value if value is not None else Decimal("0")
            for value in atr_values
        ],
        atr_percentile_window,
    )

    bb_width = bollinger_bandwidth(closes, bb_period, bb_std)
    bb_pct = rolling_percentile_rank(
        [
            value if value is not None else Decimal("0")
            for value in bb_width
        ],
        bb_percentile_window,
    )

    upper_channel = donchian_high(highs, entry_window)
    lower_channel = donchian_low(lows, exit_window)
    volume_average = sma(volumes, volume_sma)
    ema_values = ema(closes, ema_filter)

    fee_rate = Decimal(fee_bps) / Decimal("10000")
    slippage_rate = Decimal(slippage_bps) / Decimal("10000")
    cost_rate = fee_rate + slippage_rate

    equity = initial_capital
    equity_curve = [equity]

    position = Decimal("0")
    entry_price = None
    entry_index = None
    highest_close = None

    trade_returns = []
    compression_signals = 0
    go_trades = 0

    start = max(
        entry_window,
        exit_window,
        bb_period,
        bb_percentile_window,
        atr_period,
        atr_percentile_window,
        volume_sma,
        ema_filter,
    )

    for index in range(start, len(candles) - 1):
        needed = [
            atr_values[index],
            atr_pct[index],
            bb_pct[index],
            upper_channel[index],
            lower_channel[index],
            volume_average[index],
            ema_values[index],
        ]

        if any(value is None for value in needed):
            equity_curve.append(equity)
            continue

        compression_ok = (
            bb_pct[index] <= bb_max_percentile
            and atr_pct[index] <= atr_max_percentile
        )

        if compression_ok:
            compression_signals += 1

        expansion_ok = (
            atr_values[index] > atr_values[index - 1]
            and volumes[index] > volume_average[index] * volume_mult
        )

        trend_ok = closes[index] > ema_values[index]

        long_trigger = (
            position == 0
            and closes[index] > upper_channel[index]
            and compression_ok
            and expansion_ok
            and trend_ok
        )

        if long_trigger:
            entry_price = opens[index + 1] * (Decimal("1") + cost_rate)
            entry_index = index + 1
            highest_close = closes[index]
            position = Decimal("1")
            equity_curve.append(equity)
            continue

        if position > 0:
            highest_close = max(highest_close, closes[index])
            bars_since_entry = index - entry_index

            initial_stop = entry_price - stop_atr_mult * atr_values[index]
            trailing_stop = highest_close - trail_atr_mult * atr_values[index]

            false_break = (
                closes[index] < upper_channel[index]
                and bars_since_entry <= false_break_bars
            )

            exit_signal = (
                closes[index] < lower_channel[index]
                or closes[index] <= initial_stop
                or closes[index] <= trailing_stop
                or false_break
                or bars_since_entry >= max_hold
            )

            mark_exit = closes[index] * (Decimal("1") - cost_rate)
            mark_return = mark_exit / entry_price - Decimal("1")
            equity_curve.append(equity * (Decimal("1") + mark_return))

            if exit_signal:
                exit_price = opens[index + 1] * (Decimal("1") - cost_rate)
                trade_return = exit_price / entry_price - Decimal("1")

                trade_returns.append(trade_return)

                if trade_return > 0:
                    go_trades += 1

                equity = equity * (Decimal("1") + trade_return)

                position = Decimal("0")
                entry_price = None
                entry_index = None
                highest_close = None
        else:
            equity_curve.append(equity)

    if position > 0:
        exit_price = closes[-1] * (Decimal("1") - cost_rate)
        trade_return = exit_price / entry_price - Decimal("1")
        trade_returns.append(trade_return)

        if trade_return > 0:
            go_trades += 1

        equity = equity * (Decimal("1") + trade_return)
        equity_curve.append(equity)

    net_return = equity / initial_capital - Decimal("1")
    net_return_pct = percent(net_return)

    benchmark_return_pct = benchmark
    excess_return_pct = net_return_pct - benchmark_return_pct

    max_dd = max_drawdown_pct(equity_curve)
    sharpe = sharpe_ratio_from_equity(equity_curve)
    pf = profit_factor(trade_returns)
    win_rate = win_rate_pct(trade_returns)
    trades_count = len(trade_returns)

    verdict = result_verdict(
        net_return_pct,
        excess_return_pct,
        max_dd,
        sharpe,
        pf,
        trades_count,
    )

    return {
        "net_return_pct": net_return_pct,
        "benchmark_return_pct": benchmark_return_pct,
        "excess_return_pct": excess_return_pct,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "profit_factor": pf,
        "win_rate_pct": win_rate,
        "trades_count": trades_count,
        "go_trades": go_trades,
        "compression_signals": compression_signals,
        "verdict": verdict,
    }


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

    required = Decimal(splits_tested) * min_pass_ratio
    required_go = int(required)

    if Decimal(required_go) < required:
        required_go += 1

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
        return "REWORK_REGIME_FILTERS"

    if verdict == "NO_GO_AVG_UNDERPERFORMS_BENCHMARK":
        return "REJECT_OR_REDESIGN_ALPHA"

    if verdict == "NO_GO_WORST_DRAWDOWN_TOO_HIGH":
        return "TIGHTEN_RISK_CONTROLS"

    return "OBSERVE_ONLY"


def stability_score(
    go_splits,
    rejected_splits,
    avg_net,
    avg_excess,
    worst_drawdown,
    avg_sharpe,
    avg_profit_factor,
    total_trades,
    total_compression_signals,
    verdict,
):
    capped_pf = min(avg_profit_factor, Decimal("5"))

    score = Decimal("0")
    score += Decimal(go_splits) * Decimal("40")
    score -= Decimal(rejected_splits) * Decimal("15")
    score += avg_net
    score += avg_excess * Decimal("2")
    score -= worst_drawdown
    score += avg_sharpe * Decimal("25")
    score += capped_pf * Decimal("8")
    score += Decimal(total_trades) * Decimal("0.20")
    score += Decimal(total_compression_signals) * Decimal("0.05")

    if verdict == "GO_FOR_RESEARCH":
        score += Decimal("100")
    else:
        score -= Decimal("50")

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
    INSERT INTO compression_breakout_split_results (
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
        go_trades,
        compression_signals,
        verdict,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        int(result["go_trades"]),
        int(result["compression_signals"]),
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
    INSERT INTO compression_breakout_summary (
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
        total_compression_signals,
        stability_score,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        summary["total_compression_signals"],
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


def run_compression_breakout_lab(
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
        raise ValueError("Not enough candles for compression breakout lab")

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
        "regime_focus": "COMPRESSION_TO_EXPANSION",
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
            result = run_compression_breakout_strategy(
                candles=test,
                initial_capital=initial_capital,
                entry_window=spec["entry_window"],
                exit_window=spec["exit_window"],
                bb_period=spec["bb_period"],
                bb_std=Decimal(spec["bb_std"]),
                bb_percentile_window=spec["bb_percentile_window"],
                bb_max_percentile=Decimal(spec["bb_max_percentile"]),
                atr_period=spec["atr_period"],
                atr_percentile_window=spec["atr_percentile_window"],
                atr_max_percentile=Decimal(spec["atr_max_percentile"]),
                volume_sma=spec["volume_sma"],
                volume_mult=Decimal(spec["volume_mult"]),
                ema_filter=spec["ema_filter"],
                stop_atr_mult=Decimal(spec["stop_atr_mult"]),
                trail_atr_mult=Decimal(spec["trail_atr_mult"]),
                false_break_bars=spec["false_break_bars"],
                max_hold=spec["max_hold"],
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
                benchmark=split_benchmark,
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
                "go_trades": int(result["go_trades"]),
                "compression_signals": int(result["compression_signals"]),
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
        total_compression_signals = sum(row["compression_signals"] for row in rows)

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
            rejected_splits,
            avg_net,
            avg_excess,
            worst_drawdown,
            avg_sharpe,
            avg_profit_factor,
            total_trades,
            total_compression_signals,
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
            "total_compression_signals": total_compression_signals,
            "stability_score": score,
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
        key=lambda item: item["stability_score"],
        reverse=True,
    )

    approved = [
        item
        for item in ranked
        if item["final_verdict"] == "GO_FOR_RESEARCH"
    ]

    if approved:
        global_verdict = "COMPRESSION_BREAKOUT_CANDIDATE_FOUND_NO_LIVE_TRADING"
        best_variant = approved[0]
    else:
        global_verdict = "REJECT_ALL_COMPRESSION_BREAKOUT_VARIANTS_NO_LIVE_TRADING"
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
            "total_compression_signals": item["total_compression_signals"],
            "stability_score": format(item["stability_score"], "f"),
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
    parser.add_argument("--run-label", default="mission_20_compression_breakout_lab")

    args = parser.parse_args()

    print("DeltaGrid Compression Breakout Lab")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_compression_breakout_lab(
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
