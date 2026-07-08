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
    adx,
    atr,
    ema,
    rolling_percentile_rank,
    rolling_realized_volatility,
    to_decimal,
)

from backtest.regime_kernel import (
    build_regime_features,
    classify_regime_at,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS vt_tsmom_split_results (
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
        avg_position_fraction TEXT NOT NULL,
        momentum_signals INTEGER NOT NULL,
        verdict TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS vt_tsmom_summary (
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
        total_momentum_signals INTEGER NOT NULL,
        avg_position_fraction TEXT NOT NULL,
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
            "name": "vt_tsmom",
            "version": "lb21_63_126_ema200_adx18_vol25_atr3",
            "lookbacks": [21, 63, 126],
            "ema_trend": 200,
            "ema_exit": 100,
            "adx_period": 14,
            "adx_min": "18",
            "atr_period": 14,
            "atr_stop_mult": "3.0",
            "atr_trail_mult": "3.0",
            "target_vol": "0.25",
            "max_position_fraction": "1.00",
            "min_position_fraction": "0.20",
            "max_vol_percentile": "0.85",
            "panic_vol_percentile": "0.90",
            "cooldown": 10,
        },
        {
            "name": "vt_tsmom",
            "version": "lb14_42_84_ema150_adx20_vol20_atr25",
            "lookbacks": [14, 42, 84],
            "ema_trend": 150,
            "ema_exit": 75,
            "adx_period": 14,
            "adx_min": "20",
            "atr_period": 14,
            "atr_stop_mult": "2.5",
            "atr_trail_mult": "2.5",
            "target_vol": "0.20",
            "max_position_fraction": "0.90",
            "min_position_fraction": "0.15",
            "max_vol_percentile": "0.80",
            "panic_vol_percentile": "0.90",
            "cooldown": 12,
        },
        {
            "name": "vt_tsmom",
            "version": "lb30_90_180_ema200_adx18_vol30_atr35",
            "lookbacks": [30, 90, 180],
            "ema_trend": 200,
            "ema_exit": 100,
            "adx_period": 14,
            "adx_min": "18",
            "atr_period": 14,
            "atr_stop_mult": "3.5",
            "atr_trail_mult": "3.5",
            "target_vol": "0.30",
            "max_position_fraction": "1.00",
            "min_position_fraction": "0.20",
            "max_vol_percentile": "0.85",
            "panic_vol_percentile": "0.92",
            "cooldown": 15,
        },
    ]


def avg(values):
    if not values:
        return Decimal("0")

    return sum(values, Decimal("0")) / Decimal(len(values))


def clamp(value, lower, upper):
    return max(lower, min(value, upper))


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
        return "REWORK_MOMENTUM_REGIME_FILTERS"

    if verdict == "NO_GO_AVG_UNDERPERFORMS_BENCHMARK":
        return "REJECT_OR_REDESIGN_ALPHA"

    if verdict == "NO_GO_WORST_DRAWDOWN_TOO_HIGH":
        return "TIGHTEN_ATR_RISK"

    if verdict == "INSUFFICIENT_TOTAL_TRADES":
        return "COLLECT_MORE_DATA_OR_LOWER_TIMEFRAME"

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
    total_momentum_signals,
    avg_position_fraction,
    verdict,
):
    capped_pf = min(avg_profit_factor, Decimal("5"))

    score = Decimal("0")
    score += Decimal(go_splits) * Decimal("45")
    score -= Decimal(rejected_splits) * Decimal("15")
    score += avg_net
    score += avg_excess * Decimal("2")
    score -= worst_drawdown
    score += avg_sharpe * Decimal("30")
    score += capped_pf * Decimal("8")
    score += Decimal(total_trades) * Decimal("0.25")
    score += Decimal(total_momentum_signals) * Decimal("0.03")
    score += avg_position_fraction * Decimal("10")

    if verdict == "GO_FOR_RESEARCH":
        score += Decimal("120")
    else:
        score -= Decimal("50")

    return score


def sign(value):
    if value > 0:
        return Decimal("1")

    if value < 0:
        return Decimal("-1")

    return Decimal("0")


def momentum_score_at(closes, index, lookbacks):
    score = Decimal("0")

    for lookback in lookbacks:
        if index - lookback < 0:
            return None

        previous = closes[index - lookback]

        if previous == 0:
            return None

        momentum_return = closes[index] / previous - Decimal("1")
        score += sign(momentum_return)

    return score


def position_fraction_from_vol(
    realized_vol,
    target_vol,
    min_position_fraction,
    max_position_fraction,
):
    if realized_vol is None or realized_vol <= 0:
        return min_position_fraction

    raw = target_vol / realized_vol

    return clamp(raw, min_position_fraction, max_position_fraction)


def run_vt_tsmom_strategy(
    candles,
    initial_capital,
    lookbacks,
    ema_trend,
    ema_exit,
    adx_period,
    adx_min,
    atr_period,
    atr_stop_mult,
    atr_trail_mult,
    target_vol,
    max_position_fraction,
    min_position_fraction,
    max_vol_percentile,
    panic_vol_percentile,
    cooldown,
    fee_bps,
    slippage_bps,
    benchmark,
):
    closes = [to_decimal(candle["close"]) for candle in candles]
    highs = [to_decimal(candle["high"]) for candle in candles]
    lows = [to_decimal(candle["low"]) for candle in candles]
    opens = [to_decimal(candle["open"]) for candle in candles]

    ema_trend_values = ema(closes, ema_trend)
    ema_exit_values = ema(closes, ema_exit)
    adx_values = adx(highs, lows, closes, adx_period)
    atr_values = atr(highs, lows, closes, atr_period)

    atr_pct = rolling_percentile_rank(
        [
            value if value is not None else Decimal("0")
            for value in atr_values
        ],
        120,
    )

    realized_vol = rolling_realized_volatility(closes, 20)

    realized_vol_pct = rolling_percentile_rank(
        [
            value if value is not None else Decimal("0")
            for value in realized_vol
        ],
        120,
    )

    regime_features = build_regime_features(candles)

    fee_rate = Decimal(fee_bps) / Decimal("10000")
    slippage_rate = Decimal(slippage_bps) / Decimal("10000")
    cost_rate = fee_rate + slippage_rate

    equity = initial_capital
    equity_curve = [equity]

    position = Decimal("0")
    position_fraction = Decimal("0")
    entry_price = None
    highest_close = None
    cooldown_left = 0

    trade_returns = []
    position_fractions = []
    momentum_signals = 0

    start = max(
        max(lookbacks),
        ema_trend,
        ema_exit,
        adx_period * 2,
        atr_period,
        120,
    )

    for index in range(start, len(candles) - 1):
        needed = [
            ema_trend_values[index],
            ema_exit_values[index],
            adx_values[index],
            atr_values[index],
            atr_pct[index],
            realized_vol[index],
            realized_vol_pct[index],
        ]

        if any(value is None for value in needed):
            equity_curve.append(equity)
            continue

        if cooldown_left > 0:
            cooldown_left -= 1
            equity_curve.append(equity)
            continue

        regime = classify_regime_at(regime_features, index)
        labels = regime["labels"]
        primary_regime = regime["primary_regime"]

        momentum_score = momentum_score_at(closes, index, lookbacks)

        if momentum_score is None:
            equity_curve.append(equity)
            continue

        regime_ok = (
            "PANIC_VOLATILITY" not in labels
            and "BEAR_TREND" not in labels
            and primary_regime != "SIDEWAYS"
        )

        trend_ok = (
            closes[index] > ema_trend_values[index]
            and adx_values[index] >= adx_min
        )

        volatility_ok = (
            atr_pct[index] <= max_vol_percentile
            and realized_vol_pct[index] <= max_vol_percentile
        )

        long_trigger = (
            position == 0
            and momentum_score >= Decimal("2")
            and trend_ok
            and volatility_ok
            and regime_ok
        )

        if long_trigger:
            momentum_signals += 1

            entry_price = opens[index + 1] * (Decimal("1") + cost_rate)
            highest_close = closes[index]

            position_fraction = position_fraction_from_vol(
                realized_vol[index],
                target_vol,
                min_position_fraction,
                max_position_fraction,
            )

            position_fractions.append(position_fraction)
            position = Decimal("1")

            equity_curve.append(equity)
            continue

        if position > 0:
            highest_close = max(highest_close, closes[index])

            stop_loss = entry_price - atr_stop_mult * atr_values[index]
            trailing_stop = highest_close - atr_trail_mult * atr_values[index]

            exit_signal = (
                momentum_score <= Decimal("0")
                or closes[index] < ema_exit_values[index]
                or closes[index] <= stop_loss
                or closes[index] <= trailing_stop
                or atr_pct[index] >= panic_vol_percentile
                or realized_vol_pct[index] >= panic_vol_percentile
                or primary_regime == "PANIC_VOLATILITY"
                or "BEAR_TREND" in labels
            )

            mark_exit = closes[index] * (Decimal("1") - cost_rate)
            raw_mark_return = mark_exit / entry_price - Decimal("1")
            weighted_mark_return = raw_mark_return * position_fraction

            equity_curve.append(equity * (Decimal("1") + weighted_mark_return))

            if exit_signal:
                exit_price = opens[index + 1] * (Decimal("1") - cost_rate)
                raw_trade_return = exit_price / entry_price - Decimal("1")
                weighted_trade_return = raw_trade_return * position_fraction

                trade_returns.append(weighted_trade_return)

                equity = equity * (Decimal("1") + weighted_trade_return)

                position = Decimal("0")
                position_fraction = Decimal("0")
                entry_price = None
                highest_close = None
                cooldown_left = cooldown
        else:
            equity_curve.append(equity)

    if position > 0:
        exit_price = closes[-1] * (Decimal("1") - cost_rate)
        raw_trade_return = exit_price / entry_price - Decimal("1")
        weighted_trade_return = raw_trade_return * position_fraction

        trade_returns.append(weighted_trade_return)

        equity = equity * (Decimal("1") + weighted_trade_return)
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

    avg_position_fraction = avg(position_fractions)

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
        "avg_position_fraction": avg_position_fraction,
        "momentum_signals": momentum_signals,
        "verdict": verdict,
    }


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
    INSERT INTO vt_tsmom_split_results (
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
        avg_position_fraction,
        momentum_signals,
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
        format(result["avg_position_fraction"], "f"),
        int(result["momentum_signals"]),
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
    INSERT INTO vt_tsmom_summary (
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
        total_momentum_signals,
        avg_position_fraction,
        stability_score,
        final_verdict,
        recommended_action,
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
        summary["splits_tested"],
        summary["go_splits"],
        summary["rejected_splits"],
        format(summary["avg_net_return_pct"], "f"),
        format(summary["avg_excess_return_pct"], "f"),
        format(summary["worst_drawdown_pct"], "f"),
        format(summary["avg_sharpe_ratio"], "f"),
        format(summary["avg_profit_factor"], "f"),
        summary["total_trades"],
        summary["total_momentum_signals"],
        format(summary["avg_position_fraction"], "f"),
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


def run_vt_tsmom_lab(
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
        raise ValueError("Not enough candles for VT-TSMOM lab")

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
        "strategy_family": "VOLATILITY_TARGETED_TIME_SERIES_MOMENTUM",
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
            result = run_vt_tsmom_strategy(
                candles=test,
                initial_capital=initial_capital,
                lookbacks=spec["lookbacks"],
                ema_trend=spec["ema_trend"],
                ema_exit=spec["ema_exit"],
                adx_period=spec["adx_period"],
                adx_min=Decimal(spec["adx_min"]),
                atr_period=spec["atr_period"],
                atr_stop_mult=Decimal(spec["atr_stop_mult"]),
                atr_trail_mult=Decimal(spec["atr_trail_mult"]),
                target_vol=Decimal(spec["target_vol"]),
                max_position_fraction=Decimal(spec["max_position_fraction"]),
                min_position_fraction=Decimal(spec["min_position_fraction"]),
                max_vol_percentile=Decimal(spec["max_vol_percentile"]),
                panic_vol_percentile=Decimal(spec["panic_vol_percentile"]),
                cooldown=spec["cooldown"],
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
                "avg_position_fraction": result["avg_position_fraction"],
                "momentum_signals": int(result["momentum_signals"]),
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
        total_momentum_signals = sum(row["momentum_signals"] for row in rows)
        avg_position_fraction = avg([row["avg_position_fraction"] for row in rows])

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
            total_momentum_signals,
            avg_position_fraction,
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
            "total_momentum_signals": total_momentum_signals,
            "avg_position_fraction": avg_position_fraction,
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
        global_verdict = "VT_TSMOM_CANDIDATE_FOUND_NO_LIVE_TRADING"
        best_variant = approved[0]
    else:
        global_verdict = "REJECT_ALL_VT_TSMOM_VARIANTS_NO_LIVE_TRADING"
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
            "total_momentum_signals": item["total_momentum_signals"],
            "avg_position_fraction": format(item["avg_position_fraction"], "f"),
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
    parser.add_argument("--run-label", default="mission_21_vt_tsmom_lab")

    args = parser.parse_args()

    print("DeltaGrid VT-TSMOM Lab")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_vt_tsmom_lab(
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
