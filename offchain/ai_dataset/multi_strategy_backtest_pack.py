"""Mission 84.6: Multi-Strategy Backtest Pack.

Runs deterministic local fixture-based research backtests from the Mission 84.5
benchmark plan. This is offchain, paper-only research infrastructure. It does
not train models, emit live signals, place orders, deploy capital, use private
keys, call paid APIs, reweight live strategies, or make profitability claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sqlite3
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")
BACKTEST_SCOPE = "MULTI_STRATEGY_BACKTEST_PACK_LOCAL_FIXTURE_ONLY"
BACKTEST_MODE = "LOCAL_OFFCHAIN_PAPER_BACKTEST_FIXTURE_ONLY"
MISSION85_STATUS = "PAUSED_UNTIL_ROBUST_ALPHA_CANDIDATES_EXIST"
LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0
ENGINE_STATE = "AI_MULTI_STRATEGY_BACKTEST_PACK_READY_LOCAL_ONLY"
ENGINE_DECISION = "AI_MULTI_STRATEGY_BACKTEST_PACK_APPROVED_FOR_WALK_FORWARD_ROBUSTNESS_GATE"
GLOBAL_VERDICT = "AI_MULTI_STRATEGY_BACKTEST_PACK_READY_SHADOW_RESEARCH_ONLY"
RECOMMENDED_ACTION = "HAND_OFF_BACKTEST_RESULTS_TO_WALK_FORWARD_ROBUSTNESS_GATE"
NEXT_MISSION = "Mission 84.7 Walk-Forward Robustness Gate"
SOURCE_ENGINE_STATE = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_READY_LOCAL_ONLY"
SOURCE_ENGINE_DECISION = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_APPROVED_FOR_MULTI_STRATEGY_BACKTEST_PACK"
SOURCE_GLOBAL_VERDICT = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_READY_SHADOW_ONLY"
CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"
BASELINE_NAMES = ("CASH", "BUY_AND_HOLD", "DETERMINISTIC_RANDOM")
SUPPORTED_FAMILIES = (
    "TIME_SERIES_MOMENTUM",
    "CROSS_SECTIONAL_MOMENTUM_ROTATION",
    "DONCHIAN_BREAKOUT_ATR",
    "MEAN_REVERSION_ZSCORE",
    "PAIRS_STAT_ARB_RESIDUAL",
    "FUNDING_BASIS_CARRY",
    "VOLATILITY_REGIME_FILTER",
    "HYBRID_ENSEMBLE",
)
TIMEFRAME_SECONDS = {"1D": 86400, "4H": 14400, "1H": 3600}
BARS_PER_YEAR = {"1D": 365.0, "4H": 2190.0, "1H": 8760.0}
BASE_PRICES = {"CRYPTO": 30000.0, "FX": 1.1, "ETF_MACRO": 300.0}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def normalize_label(value: str, field_name: str) -> str:
    label = str(value).strip()
    if not label:
        raise ValueError(f"{field_name} is required")
    if any(ch.isspace() for ch in label):
        raise ValueError(f"{field_name} must not contain whitespace: {label}")
    return label


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def row_get(row: sqlite3.Row | dict[str, Any] | None, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ai_multi_strategy_backtest_runs (
                backtest_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                benchmark_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                backtest_scope TEXT NOT NULL,
                backtest_mode TEXT NOT NULL,
                mission85_status TEXT NOT NULL,
                source_plan_entry_count INTEGER NOT NULL,
                strategy_family_count INTEGER NOT NULL,
                asset_group_count INTEGER NOT NULL,
                timeframe_count INTEGER NOT NULL,
                fixture_dataset_count INTEGER NOT NULL,
                fixture_bar_count INTEGER NOT NULL,
                actual_backtest_count INTEGER NOT NULL,
                baseline_result_count INTEGER NOT NULL,
                positive_fixture_net_return_count INTEGER NOT NULL,
                negative_fixture_net_return_count INTEGER NOT NULL,
                outperformed_cash_count INTEGER NOT NULL,
                outperformed_buy_hold_count INTEGER NOT NULL,
                outperformed_random_count INTEGER NOT NULL,
                model_training_count INTEGER NOT NULL,
                model_artifact_count INTEGER NOT NULL,
                model_promotion_count INTEGER NOT NULL,
                strategy_reweighting_count INTEGER NOT NULL,
                live_signal_count INTEGER NOT NULL,
                exchange_order_count INTEGER NOT NULL,
                capital_deployment_count INTEGER NOT NULL,
                paid_api_count INTEGER NOT NULL,
                private_key_use_count INTEGER NOT NULL,
                profitability_claim_count INTEGER NOT NULL,
                backtest_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                engine_state TEXT NOT NULL,
                engine_decision TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                next_mission TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_multi_strategy_backtest_datasets (
                dataset_id TEXT PRIMARY KEY,
                backtest_run_label TEXT NOT NULL,
                benchmark_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                asset_group TEXT NOT NULL,
                symbol TEXT NOT NULL,
                companion_symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                data_source TEXT NOT NULL,
                bar_count INTEGER NOT NULL,
                first_timestamp TEXT NOT NULL,
                last_timestamp TEXT NOT NULL,
                fixture_hash TEXT NOT NULL,
                dataset_json TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_multi_strategy_backtest_results (
                result_id TEXT PRIMARY KEY,
                backtest_run_label TEXT NOT NULL,
                benchmark_run_label TEXT NOT NULL,
                benchmark_plan_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                strategy_family_code TEXT NOT NULL,
                asset_group TEXT NOT NULL,
                symbol TEXT NOT NULL,
                companion_symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                cost_model_code TEXT NOT NULL,
                bar_count INTEGER NOT NULL,
                trade_count INTEGER NOT NULL,
                turnover_units TEXT NOT NULL,
                gross_return_pct TEXT NOT NULL,
                net_return_pct TEXT NOT NULL,
                annualized_volatility_pct TEXT NOT NULL,
                sharpe_ratio TEXT NOT NULL,
                max_drawdown_pct TEXT NOT NULL,
                win_rate_pct TEXT NOT NULL,
                total_cost_bps TEXT NOT NULL,
                cash_return_pct TEXT NOT NULL,
                buy_hold_return_pct TEXT NOT NULL,
                random_return_pct TEXT NOT NULL,
                excess_vs_cash_pct TEXT NOT NULL,
                excess_vs_buy_hold_pct TEXT NOT NULL,
                excess_vs_random_pct TEXT NOT NULL,
                research_status TEXT NOT NULL,
                result_scope TEXT NOT NULL,
                model_training_action TEXT NOT NULL,
                model_artifact_action TEXT NOT NULL,
                model_promotion_action TEXT NOT NULL,
                strategy_reweighting_action TEXT NOT NULL,
                live_signal_action TEXT NOT NULL,
                exchange_order_action TEXT NOT NULL,
                capital_action TEXT NOT NULL,
                paid_api_action TEXT NOT NULL,
                profitability_claim_action TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_multi_strategy_backtest_baselines (
                baseline_id TEXT PRIMARY KEY,
                backtest_run_label TEXT NOT NULL,
                result_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                baseline_name TEXT NOT NULL,
                net_return_pct TEXT NOT NULL,
                annualized_volatility_pct TEXT NOT NULL,
                sharpe_ratio TEXT NOT NULL,
                max_drawdown_pct TEXT NOT NULL,
                trade_count INTEGER NOT NULL,
                total_cost_bps TEXT NOT NULL,
                baseline_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metrics_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_multi_strategy_backtest_checks (
                check_id TEXT PRIMARY KEY,
                backtest_run_label TEXT NOT NULL,
                benchmark_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                check_reason TEXT NOT NULL,
                backtest_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_multi_strategy_backtest_reports (
                report_label TEXT PRIMARY KEY,
                backtest_run_label TEXT NOT NULL,
                benchmark_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                report_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL
            );
            """
        )
        conn.commit()


def deterministic_seed(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def build_fixture_dataset(
    asset_group: str,
    symbol: str,
    companion_symbol: str,
    timeframe: str,
    bars: int,
    seed_label: str,
) -> list[dict[str, Any]]:
    if bars < 120:
        raise ValueError("bars must be at least 120")
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    rng = random.Random(deterministic_seed(seed_label, asset_group, symbol, timeframe))
    base_price = BASE_PRICES.get(asset_group, 100.0)
    scale = {"CRYPTO": 1.0, "FX": 0.25, "ETF_MACRO": 0.55}.get(asset_group, 0.5)
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    step = timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    close = base_price
    companion_close = base_price * 0.72
    rows: list[dict[str, Any]] = []

    for index in range(bars):
        regime = (index // 55) % 4
        regime_drift = (0.00065, -0.00045, 0.0001, 0.00035)[regime] * scale
        cyclical = math.sin(index / 9.0) * 0.0018 * scale
        volatility = (0.006, 0.009, 0.004, 0.012)[regime] * scale
        shock = rng.gauss(0.0, volatility)
        return_value = regime_drift + cyclical + shock
        previous_close = close
        close = max(previous_close * (1.0 + return_value), base_price * 0.05)

        pair_noise = rng.gauss(0.0, volatility * 0.35)
        pair_return = regime_drift * 0.85 + cyclical * 0.75 + shock * 0.72 + pair_noise
        companion_close = max(companion_close * (1.0 + pair_return), base_price * 0.04)

        open_price = previous_close * (1.0 + rng.gauss(0.0, volatility * 0.15))
        range_fraction = abs(rng.gauss(volatility * 0.8, volatility * 0.25)) + 0.0001
        high = max(open_price, close) * (1.0 + range_fraction)
        low = min(open_price, close) * max(0.0001, 1.0 - range_fraction)
        volume = max(1.0, 1_000_000.0 * (1.0 + abs(return_value) * 35.0 + rng.random() * 0.25))
        funding_bps = math.sin(index / 17.0) * 0.55 + regime_drift * 1000.0
        basis_bps = math.sin(index / 23.0) * 4.0 + shock * 150.0
        timestamp = (start + index * step).isoformat()
        rows.append(
            {
                "timestamp": timestamp,
                "open": round(open_price, 10),
                "high": round(high, 10),
                "low": round(low, 10),
                "close": round(close, 10),
                "volume": round(volume, 4),
                "companion_close": round(companion_close, 10),
                "funding_bps": round(funding_bps, 8),
                "basis_bps": round(basis_bps, 8),
            }
        )
    return rows


def rolling_mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def rolling_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.pstdev(values)


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def bar_returns(bars: Sequence[dict[str, Any]]) -> list[float]:
    closes = [safe_float(row["close"]) for row in bars]
    result = [0.0]
    for index in range(1, len(closes)):
        result.append(closes[index] / closes[index - 1] - 1.0)
    return result


def strategy_signals(strategy_family_code: str, bars: Sequence[dict[str, Any]]) -> list[float]:
    if strategy_family_code not in SUPPORTED_FAMILIES:
        raise ValueError(f"Unsupported strategy family: {strategy_family_code}")

    closes = [safe_float(row["close"]) for row in bars]
    highs = [safe_float(row["high"]) for row in bars]
    lows = [safe_float(row["low"]) for row in bars]
    pairs = [safe_float(row["companion_close"]) for row in bars]
    returns = bar_returns(bars)
    signals = [0.0] * len(bars)

    if strategy_family_code == "TIME_SERIES_MOMENTUM":
        for index in range(20, len(bars)):
            momentum = closes[index] / closes[index - 20] - 1.0
            signals[index] = 1.0 if momentum > 0 else -1.0 if momentum < 0 else 0.0

    elif strategy_family_code == "CROSS_SECTIONAL_MOMENTUM_ROTATION":
        for index in range(60, len(bars)):
            short_momentum = closes[index] / closes[index - 20] - 1.0
            long_momentum = closes[index] / closes[index - 60] - 1.0
            relative_score = short_momentum - long_momentum
            signals[index] = 1.0 if relative_score > 0 else -1.0 if relative_score < 0 else 0.0

    elif strategy_family_code == "DONCHIAN_BREAKOUT_ATR":
        position = 0.0
        for index in range(20, len(bars)):
            prior_high = max(highs[index - 20:index])
            prior_low = min(lows[index - 20:index])
            if closes[index] > prior_high:
                position = 1.0
            elif closes[index] < prior_low:
                position = -1.0
            signals[index] = position

    elif strategy_family_code == "MEAN_REVERSION_ZSCORE":
        for index in range(20, len(bars)):
            window = closes[index - 20:index]
            mean = rolling_mean(window)
            std = rolling_std(window)
            zscore = (closes[index] - mean) / std if std > 0 else 0.0
            signals[index] = -1.0 if zscore > 1.25 else 1.0 if zscore < -1.25 else 0.0

    elif strategy_family_code == "PAIRS_STAT_ARB_RESIDUAL":
        residuals = [math.log(max(closes[i], 1e-12)) - math.log(max(pairs[i], 1e-12)) for i in range(len(bars))]
        for index in range(30, len(bars)):
            window = residuals[index - 30:index]
            mean = rolling_mean(window)
            std = rolling_std(window)
            zscore = (residuals[index] - mean) / std if std > 0 else 0.0
            signals[index] = -1.0 if zscore > 1.1 else 1.0 if zscore < -1.1 else 0.0

    elif strategy_family_code == "FUNDING_BASIS_CARRY":
        for index, row in enumerate(bars):
            carry_score = safe_float(row["funding_bps"]) - abs(safe_float(row["basis_bps"])) * 0.05
            signals[index] = 1.0 if carry_score > 0.2 else -1.0 if carry_score < -0.2 else 0.0

    elif strategy_family_code == "VOLATILITY_REGIME_FILTER":
        realized_history: list[float] = []
        for index in range(20, len(bars)):
            realized = rolling_std(returns[index - 20:index])
            threshold = percentile(realized_history[-60:], 0.75) if realized_history else realized
            momentum = closes[index] / closes[index - 20] - 1.0
            if realized <= threshold:
                signals[index] = 1.0 if momentum > 0 else -1.0 if momentum < 0 else 0.0
            realized_history.append(realized)

    elif strategy_family_code == "HYBRID_ENSEMBLE":
        momentum = strategy_signals("TIME_SERIES_MOMENTUM", bars)
        breakout = strategy_signals("DONCHIAN_BREAKOUT_ATR", bars)
        mean_reversion = strategy_signals("MEAN_REVERSION_ZSCORE", bars)
        for index in range(len(bars)):
            vote = momentum[index] + breakout[index] + mean_reversion[index]
            signals[index] = 1.0 if vote >= 1.0 else -1.0 if vote <= -1.0 else 0.0

    return signals


def deterministic_random_signals(length: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.choice((-1.0, 0.0, 1.0)) for _ in range(length)]


def max_drawdown_pct(equity_curve: Sequence[float]) -> float:
    peak = equity_curve[0] if equity_curve else 1.0
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        drawdown = value / peak - 1.0 if peak else 0.0
        worst = min(worst, drawdown)
    return abs(worst) * 100.0


def backtest_series(
    bars: Sequence[dict[str, Any]],
    signals: Sequence[float],
    cost_model: dict[str, Any],
    timeframe: str,
) -> dict[str, Any]:
    if len(bars) != len(signals):
        raise ValueError("bars and signals must have equal length")

    per_turnover_bps = (
        safe_float(cost_model.get("commission_bps"))
        + safe_float(cost_model.get("slippage_bps"))
        + safe_float(cost_model.get("spread_bps"))
    )
    annual_holding_bps = safe_float(cost_model.get("funding_bps")) + safe_float(cost_model.get("borrow_bps"))
    bars_per_year = BARS_PER_YEAR[timeframe]
    closes = [safe_float(row["close"]) for row in bars]
    gross_equity = 1.0
    net_equity = 1.0
    gross_curve = [1.0]
    net_curve = [1.0]
    net_bar_returns: list[float] = []
    turnover_units = 0.0
    trade_count = 0
    total_cost_fraction = 0.0
    previous_position = 0.0

    for index in range(1, len(bars)):
        position = float(signals[index - 1])
        asset_return = closes[index] / closes[index - 1] - 1.0
        gross_return = position * asset_return
        turnover = abs(position - previous_position)
        if turnover > 0:
            trade_count += 1
        transaction_cost = turnover * per_turnover_bps / 10000.0
        holding_cost = abs(position) * annual_holding_bps / 10000.0 / bars_per_year
        net_return = gross_return - transaction_cost - holding_cost
        gross_equity *= max(1e-12, 1.0 + gross_return)
        net_equity *= max(1e-12, 1.0 + net_return)
        gross_curve.append(gross_equity)
        net_curve.append(net_equity)
        net_bar_returns.append(net_return)
        turnover_units += turnover
        total_cost_fraction += transaction_cost + holding_cost
        previous_position = position

    mean_return = rolling_mean(net_bar_returns)
    volatility = rolling_std(net_bar_returns)
    sharpe = mean_return / volatility * math.sqrt(bars_per_year) if volatility > 0 else 0.0
    win_rate = (
        sum(1 for value in net_bar_returns if value > 0) / len(net_bar_returns) * 100.0
        if net_bar_returns else 0.0
    )
    return {
        "gross_return_pct": (gross_equity - 1.0) * 100.0,
        "net_return_pct": (net_equity - 1.0) * 100.0,
        "annualized_volatility_pct": volatility * math.sqrt(bars_per_year) * 100.0,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_drawdown_pct(net_curve),
        "win_rate_pct": win_rate,
        "trade_count": trade_count,
        "turnover_units": turnover_units,
        "total_cost_bps": total_cost_fraction * 10000.0,
        "ending_equity": net_equity,
    }


def fmt(value: Any) -> str:
    return f"{safe_float(value):.8f}"


def load_source_context(
    conn: sqlite3.Connection,
    benchmark_run_label: str,
) -> tuple[sqlite3.Row | None, list[sqlite3.Row], list[sqlite3.Row], list[sqlite3.Row]]:
    required = (
        "ai_institutional_alpha_benchmark_runs",
        "ai_alpha_benchmark_plan_entries",
        "ai_alpha_asset_universe_registry",
        "ai_alpha_cost_model_registry",
    )
    if not all(table_exists(conn, name) for name in required):
        return None, [], [], []

    source_run = conn.execute(
        "SELECT * FROM ai_institutional_alpha_benchmark_runs WHERE benchmark_run_label=?",
        (benchmark_run_label,),
    ).fetchone()
    plans = conn.execute(
        """
        SELECT * FROM ai_alpha_benchmark_plan_entries
        WHERE benchmark_run_label=?
        ORDER BY strategy_family_code, asset_group, timeframe, benchmark_plan_id
        """,
        (benchmark_run_label,),
    ).fetchall()
    assets = conn.execute(
        """
        SELECT * FROM ai_alpha_asset_universe_registry
        WHERE benchmark_run_label=?
        ORDER BY asset_group, asset_id
        """,
        (benchmark_run_label,),
    ).fetchall()
    costs = conn.execute(
        """
        SELECT * FROM ai_alpha_cost_model_registry
        WHERE benchmark_run_label=?
        ORDER BY cost_model_code
        """,
        (benchmark_run_label,),
    ).fetchall()
    return source_run, plans, assets, costs


def source_is_ready(source_run: sqlite3.Row | None) -> bool:
    return bool(
        source_run
        and row_get(source_run, "engine_state") == SOURCE_ENGINE_STATE
        and row_get(source_run, "engine_decision") == SOURCE_ENGINE_DECISION
        and row_get(source_run, "global_verdict") == SOURCE_GLOBAL_VERDICT
        and row_get(source_run, "mission85_status") == MISSION85_STATUS
        and safe_int(row_get(source_run, "actual_backtest_count")) == 0
        and safe_int(row_get(source_run, "fail_check_count")) == 0
        and safe_int(row_get(source_run, "safety_breach_count")) == 0
        and safe_int(row_get(source_run, "leakage_breach_count")) == 0
    )


def representative_assets(assets: Sequence[sqlite3.Row]) -> dict[str, tuple[str, str]]:
    grouped: dict[str, list[str]] = {}
    for row in assets:
        grouped.setdefault(str(row["asset_group"]), []).append(str(row["symbol"]))
    representatives: dict[str, tuple[str, str]] = {}
    for group, symbols in grouped.items():
        primary = symbols[0]
        companion = symbols[1] if len(symbols) > 1 else f"{primary}_PAIR_FIXTURE"
        representatives[group] = (primary, companion)
    return representatives


def make_check(
    run_label: str,
    benchmark_run_label: str,
    created_at: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{run_label}-{category.lower()}-{name.lower().replace('_', '-')}",
        "backtest_run_label": run_label,
        "benchmark_run_label": benchmark_run_label,
        "created_at": created_at,
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "threshold_value": str(threshold),
        "check_reason": reason,
        "backtest_scope": BACKTEST_SCOPE,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "local_only": True,
            "paper_only": True,
            "model_training_enabled": False,
            "live_signal_generation_enabled": False,
            "profitability_claim": False,
        },
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    family_lines = "\n".join(
        f"- {family}: results={count}"
        for family, count in sorted(summary["results_by_strategy_family"].items())
    )
    check_lines = "\n".join(
        f"- {check['check_category']} / {check['check_name']}: {check['check_status']} "
        f"(observed={check['observed_value']}, threshold={check['threshold_value']})"
        for check in summary["backtest_checks"]
    )
    return f"""# DeltaGrid Mission 84.6 Multi-Strategy Backtest Pack Report

Report label: {summary['report_label']}

Backtest run label: {summary['backtest_run_label']}

Benchmark run label: {summary['benchmark_run_label']}

Created at: {summary['created_at']}

## Scope

- Local/offchain fixture-based paper research only.
- No live trading, real capital, private keys, signing, exchange orders, paid APIs, live signals, model training, model artifacts, model promotion, or strategy reweighting.
- Return metrics are synthetic-fixture observations only and are not profitability claims.
- Mission 85 remains: {summary['mission85_status']}.

## Backtest Summary

- Source plan entries: {summary['source_plan_entry_count']}
- Fixture datasets: {summary['fixture_dataset_count']}
- Fixture bars: {summary['fixture_bar_count']}
- Actual local research backtests: {summary['actual_backtest_count']}
- Baseline results: {summary['baseline_result_count']}
- Positive synthetic-fixture net-return observations: {summary['positive_fixture_net_return_count']}
- Negative synthetic-fixture net-return observations: {summary['negative_fixture_net_return_count']}
- Outperformed cash observations: {summary['outperformed_cash_count']}
- Outperformed buy-and-hold observations: {summary['outperformed_buy_hold_count']}
- Outperformed deterministic-random observations: {summary['outperformed_random_count']}

## Strategy Coverage

{family_lines}

## Safety and Governance

- Model training count: {summary['model_training_count']}
- Model artifact count: {summary['model_artifact_count']}
- Model promotion count: {summary['model_promotion_count']}
- Strategy reweighting count: {summary['strategy_reweighting_count']}
- Live signal count: {summary['live_signal_count']}
- Exchange order count: {summary['exchange_order_count']}
- Capital deployment count: {summary['capital_deployment_count']}
- Paid API count: {summary['paid_api_count']}
- Private-key use count: {summary['private_key_use_count']}
- Profitability claim count: {summary['profitability_claim_count']}
- Safety breach count: {summary['safety_breach_count']}

## Checks

{check_lines}

## Decision

- Engine state: {summary['engine_state']}
- Engine decision: {summary['engine_decision']}
- Global verdict: {summary['global_verdict']}
- Recommended action: {summary['recommended_action']}
- Next mission: {summary['next_mission']}
"""


def run_multi_strategy_backtest_pack(
    db_path: str | Path = DEFAULT_DB_PATH,
    backtest_run_label: str = "mission84-6-local-check",
    report_label: str = "mission84-6-local-check-report",
    benchmark_run_label: str = "mission84-5-final-check",
    min_plan_entries: int = 72,
    bars: int = 260,
) -> dict[str, Any]:
    backtest_run_label = normalize_label(backtest_run_label, "backtest_run_label")
    report_label = normalize_label(report_label, "report_label")
    benchmark_run_label = normalize_label(benchmark_run_label, "benchmark_run_label")
    if min_plan_entries < 1:
        raise ValueError("min_plan_entries must be positive")
    if bars < 120:
        raise ValueError("bars must be at least 120")

    ensure_schema(db_path)
    created_at = utc_now()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        source_run, plans, assets, costs = load_source_context(conn, benchmark_run_label)
        representatives = representative_assets(assets)
        cost_map = {str(row["cost_model_code"]): dict(row) for row in costs}

        dataset_keys = sorted({(str(row["asset_group"]), str(row["timeframe"])) for row in plans})
        datasets: dict[tuple[str, str], dict[str, Any]] = {}
        for asset_group, timeframe in dataset_keys:
            primary, companion = representatives.get(
                asset_group,
                (f"{asset_group}_FIXTURE", f"{asset_group}_PAIR_FIXTURE"),
            )
            fixture = build_fixture_dataset(
                asset_group=asset_group,
                symbol=primary,
                companion_symbol=companion,
                timeframe=timeframe,
                bars=bars,
                seed_label=benchmark_run_label,
            )
            dataset_id = f"{backtest_run_label}-{asset_group}-{timeframe}-fixture"
            payload = canonical_json(fixture)
            datasets[(asset_group, timeframe)] = {
                "dataset_id": dataset_id,
                "backtest_run_label": backtest_run_label,
                "benchmark_run_label": benchmark_run_label,
                "created_at": created_at,
                "asset_group": asset_group,
                "symbol": primary,
                "companion_symbol": companion,
                "timeframe": timeframe,
                "data_source": "DETERMINISTIC_SYNTHETIC_OHLCV_FIXTURE_LOCAL_ONLY",
                "bar_count": len(fixture),
                "first_timestamp": fixture[0]["timestamp"],
                "last_timestamp": fixture[-1]["timestamp"],
                "fixture_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                "dataset_json": payload,
                "bars": fixture,
                "live_trading": LIVE_TRADING_STATUS,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": {
                    "fixture_based": True,
                    "local_only": True,
                    "paper_only": True,
                    "paid_api_used": False,
                    "private_keys_used": False,
                    "not_real_market_data": True,
                },
            }

        results: list[dict[str, Any]] = []
        baselines: list[dict[str, Any]] = []
        for plan in plans:
            family = str(plan["strategy_family_code"])
            asset_group = str(plan["asset_group"])
            timeframe = str(plan["timeframe"])
            cost_model_code = str(plan["cost_model_code"])
            dataset = datasets[(asset_group, timeframe)]
            fixture = dataset["bars"]
            cost_model = cost_map.get(
                cost_model_code,
                {
                    "commission_bps": 0.0,
                    "slippage_bps": 0.0,
                    "spread_bps": 0.0,
                    "funding_bps": 0.0,
                    "borrow_bps": 0.0,
                },
            )
            strategy_metric = backtest_series(
                fixture,
                strategy_signals(family, fixture),
                cost_model,
                timeframe,
            )
            baseline_signal_map = {
                "CASH": [0.0] * len(fixture),
                "BUY_AND_HOLD": [1.0] * len(fixture),
                "DETERMINISTIC_RANDOM": deterministic_random_signals(
                    len(fixture),
                    deterministic_seed(backtest_run_label, str(plan["benchmark_plan_id"]), "random"),
                ),
            }
            baseline_metrics = {
                name: backtest_series(fixture, signal_values, cost_model, timeframe)
                for name, signal_values in baseline_signal_map.items()
            }
            result_id = f"{backtest_run_label}-{plan['benchmark_plan_id']}"
            result = {
                "result_id": result_id,
                "backtest_run_label": backtest_run_label,
                "benchmark_run_label": benchmark_run_label,
                "benchmark_plan_id": str(plan["benchmark_plan_id"]),
                "dataset_id": dataset["dataset_id"],
                "created_at": created_at,
                "strategy_family_code": family,
                "asset_group": asset_group,
                "symbol": dataset["symbol"],
                "companion_symbol": dataset["companion_symbol"],
                "timeframe": timeframe,
                "cost_model_code": cost_model_code,
                "bar_count": len(fixture),
                **strategy_metric,
                "cash_return_pct": baseline_metrics["CASH"]["net_return_pct"],
                "buy_hold_return_pct": baseline_metrics["BUY_AND_HOLD"]["net_return_pct"],
                "random_return_pct": baseline_metrics["DETERMINISTIC_RANDOM"]["net_return_pct"],
                "excess_vs_cash_pct": strategy_metric["net_return_pct"] - baseline_metrics["CASH"]["net_return_pct"],
                "excess_vs_buy_hold_pct": strategy_metric["net_return_pct"] - baseline_metrics["BUY_AND_HOLD"]["net_return_pct"],
                "excess_vs_random_pct": strategy_metric["net_return_pct"] - baseline_metrics["DETERMINISTIC_RANDOM"]["net_return_pct"],
                "research_status": "SYNTHETIC_FIXTURE_RESULT_RECORDED_UNVALIDATED_NOT_PROMOTED",
                "result_scope": BACKTEST_SCOPE,
                "model_training_action": "NO_MODEL_TRAINING",
                "model_artifact_action": "NO_MODEL_ARTIFACT",
                "model_promotion_action": "NO_MODEL_PROMOTION",
                "strategy_reweighting_action": "NO_STRATEGY_REWEIGHTING",
                "live_signal_action": "NO_LIVE_SIGNAL",
                "exchange_order_action": "NO_EXCHANGE_ORDER",
                "capital_action": "NO_CAPITAL_DEPLOYMENT",
                "paid_api_action": "NO_PAID_API",
                "profitability_claim_action": "NO_PROFITABILITY_CLAIM",
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": {
                    "fixture_based": True,
                    "local_only": True,
                    "paper_only": True,
                    "signals_shifted_one_bar": True,
                    "transaction_costs_included": True,
                    "slippage_included": True,
                    "not_profitability_claim": True,
                    "mission85_status": MISSION85_STATUS,
                },
            }
            results.append(result)
            for baseline_name, metric in baseline_metrics.items():
                baselines.append(
                    {
                        "baseline_id": f"{result_id}-{baseline_name.lower()}",
                        "backtest_run_label": backtest_run_label,
                        "result_id": result_id,
                        "created_at": created_at,
                        "baseline_name": baseline_name,
                        **metric,
                        "baseline_scope": BACKTEST_SCOPE,
                        "live_trading": LIVE_TRADING_STATUS,
                        "live_order_sent": LIVE_ORDER_SENT_VALUE,
                        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                    }
                )

        strategy_families = sorted({str(row["strategy_family_code"]) for row in plans})
        asset_groups = sorted({str(row["asset_group"]) for row in plans})
        timeframes = sorted({str(row["timeframe"]) for row in plans})
        model_training_count = sum(1 for row in results if row["model_training_action"] != "NO_MODEL_TRAINING")
        model_artifact_count = sum(1 for row in results if row["model_artifact_action"] != "NO_MODEL_ARTIFACT")
        model_promotion_count = sum(1 for row in results if row["model_promotion_action"] != "NO_MODEL_PROMOTION")
        strategy_reweighting_count = sum(1 for row in results if row["strategy_reweighting_action"] != "NO_STRATEGY_REWEIGHTING")
        live_signal_count = sum(1 for row in results if row["live_signal_action"] != "NO_LIVE_SIGNAL")
        exchange_order_count = sum(1 for row in results if row["exchange_order_action"] != "NO_EXCHANGE_ORDER")
        capital_deployment_count = sum(1 for row in results if row["capital_action"] != "NO_CAPITAL_DEPLOYMENT")
        paid_api_count = sum(1 for row in results if row["paid_api_action"] != "NO_PAID_API")
        profitability_claim_count = sum(1 for row in results if row["profitability_claim_action"] != "NO_PROFITABILITY_CLAIM")
        private_key_use_count = 0
        safety_breach_count = sum(
            1 for row in results
            if row["live_trading"] != LIVE_TRADING_STATUS
            or safe_int(row["live_order_sent"]) != 0
            or row["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
        )

        checks = [
            make_check(backtest_run_label, benchmark_run_label, created_at, "SOURCE", "SOURCE_RUN_PRESENT", source_run is not None, source_run is not None, True, "Mission 84.5 source run must exist."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "SOURCE", "SOURCE_READY", source_is_ready(source_run), source_is_ready(source_run), True, "Mission 84.5 must be ready with zero source failures, safety breaches, leakage breaches, or backtests."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "COVERAGE", "PLAN_ENTRY_COUNT", len(plans) >= min_plan_entries, len(plans), min_plan_entries, "All required benchmark plan entries must be available."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "COVERAGE", "SUPPORTED_STRATEGY_FAMILIES", set(strategy_families).issubset(set(SUPPORTED_FAMILIES)), len(strategy_families), len(SUPPORTED_FAMILIES), "Every source strategy family must have deterministic baseline logic."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "DATA", "FIXTURE_DATASET_COUNT", len(datasets) == len(dataset_keys), len(datasets), len(dataset_keys), "One deterministic fixture dataset is required per asset-group/timeframe pair."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "DATA", "MINIMUM_FIXTURE_BARS", all(row["bar_count"] >= 120 for row in datasets.values()), min((row["bar_count"] for row in datasets.values()), default=0), 120, "Each fixture must have enough bars for baseline indicators."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "BACKTEST", "RESULT_COUNT", len(results) == len(plans), len(results), len(plans), "Every benchmark plan entry must produce one local research backtest result."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "BASELINE", "BASELINE_COUNT", len(baselines) == len(results) * len(BASELINE_NAMES), len(baselines), len(results) * len(BASELINE_NAMES), "Every result must include cash, buy-and-hold, and deterministic-random baselines."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "SAFETY", "NO_MODEL_TRAINING", model_training_count == 0, model_training_count, 0, "Model training remains disabled."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "SAFETY", "NO_MODEL_ARTIFACTS", model_artifact_count == 0, model_artifact_count, 0, "No model artifacts may be created."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "SAFETY", "NO_MODEL_PROMOTION", model_promotion_count == 0, model_promotion_count, 0, "Mission 85 remains paused."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "SAFETY", "NO_STRATEGY_REWEIGHTING", strategy_reweighting_count == 0, strategy_reweighting_count, 0, "No capital-linked strategy reweighting is allowed."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "SAFETY", "NO_LIVE_SIGNALS", live_signal_count == 0, live_signal_count, 0, "Backtest positions are local historical research states, not live signals."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "SAFETY", "NO_EXCHANGE_ORDERS", exchange_order_count == 0, exchange_order_count, 0, "No exchange orders are allowed."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "SAFETY", "NO_CAPITAL_DEPLOYMENT", capital_deployment_count == 0, capital_deployment_count, 0, "No real capital is deployed."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "SAFETY", "NO_PAID_APIS", paid_api_count == 0, paid_api_count, 0, "Fixtures are local and no paid API is used."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "SAFETY", "NO_PRIVATE_KEYS", private_key_use_count == 0, private_key_use_count, 0, "No private keys or signing are used."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "GOVERNANCE", "NO_PROFITABILITY_CLAIMS", profitability_claim_count == 0, profitability_claim_count, 0, "Synthetic fixture metrics are observations only, never profitability claims."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "GOVERNANCE", "MISSION85_PAUSED", row_get(source_run, "mission85_status", MISSION85_STATUS) == MISSION85_STATUS, row_get(source_run, "mission85_status", "MISSING"), MISSION85_STATUS, "Model promotion remains paused until robust candidates exist."),
            make_check(backtest_run_label, benchmark_run_label, created_at, "SAFETY", "ZERO_SAFETY_BREACHES", safety_breach_count == 0, safety_breach_count, 0, "All persisted results must retain safety locks."),
        ]
        pass_check_count = sum(1 for check in checks if check["check_status"] == CHECK_PASS)
        fail_check_count = len(checks) - pass_check_count
        results_by_family = {
            family: sum(1 for row in results if row["strategy_family_code"] == family)
            for family in strategy_families
        }
        summary = {
            "backtest_run_label": backtest_run_label,
            "report_label": report_label,
            "benchmark_run_label": benchmark_run_label,
            "created_at": created_at,
            "backtest_scope": BACKTEST_SCOPE,
            "backtest_mode": BACKTEST_MODE,
            "mission85_status": MISSION85_STATUS,
            "source_plan_entry_count": len(plans),
            "strategy_family_count": len(strategy_families),
            "asset_group_count": len(asset_groups),
            "timeframe_count": len(timeframes),
            "fixture_dataset_count": len(datasets),
            "fixture_bar_count": sum(row["bar_count"] for row in datasets.values()),
            "actual_backtest_count": len(results),
            "baseline_result_count": len(baselines),
            "positive_fixture_net_return_count": sum(1 for row in results if row["net_return_pct"] > 0),
            "negative_fixture_net_return_count": sum(1 for row in results if row["net_return_pct"] < 0),
            "outperformed_cash_count": sum(1 for row in results if row["excess_vs_cash_pct"] > 0),
            "outperformed_buy_hold_count": sum(1 for row in results if row["excess_vs_buy_hold_pct"] > 0),
            "outperformed_random_count": sum(1 for row in results if row["excess_vs_random_pct"] > 0),
            "model_training_count": model_training_count,
            "model_artifact_count": model_artifact_count,
            "model_promotion_count": model_promotion_count,
            "strategy_reweighting_count": strategy_reweighting_count,
            "live_signal_count": live_signal_count,
            "exchange_order_count": exchange_order_count,
            "capital_deployment_count": capital_deployment_count,
            "paid_api_count": paid_api_count,
            "private_key_use_count": private_key_use_count,
            "profitability_claim_count": profitability_claim_count,
            "backtest_check_count": len(checks),
            "pass_check_count": pass_check_count,
            "fail_check_count": fail_check_count,
            "safety_breach_count": safety_breach_count,
            "engine_state": ENGINE_STATE if fail_check_count == 0 else "AI_MULTI_STRATEGY_BACKTEST_PACK_BLOCKED",
            "engine_decision": ENGINE_DECISION if fail_check_count == 0 else "AI_MULTI_STRATEGY_BACKTEST_PACK_REQUIRES_REMEDIATION",
            "global_verdict": GLOBAL_VERDICT if fail_check_count == 0 else "AI_MULTI_STRATEGY_BACKTEST_PACK_BLOCKED_RESEARCH_ONLY",
            "recommended_action": RECOMMENDED_ACTION if fail_check_count == 0 else "REMEDIATE_FAILED_BACKTEST_CHECKS",
            "next_mission": NEXT_MISSION if fail_check_count == 0 else "Mission 84.6 remediation",
            "live_trading": LIVE_TRADING_STATUS,
            "live_order_sent": LIVE_ORDER_SENT_VALUE,
            "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
            "results_by_strategy_family": results_by_family,
            "fixture_datasets": [
                {key: value for key, value in row.items() if key not in {"bars", "dataset_json"}}
                for row in datasets.values()
            ],
            "backtest_results": results,
            "backtest_checks": checks,
            "safety_disclaimer": "Synthetic fixture results are unvalidated research observations and are not profitability claims.",
        }
        markdown_report = build_markdown_report(summary)
        summary["markdown_report"] = markdown_report

        conn.execute("DELETE FROM ai_multi_strategy_backtest_baselines WHERE backtest_run_label=?", (backtest_run_label,))
        conn.execute("DELETE FROM ai_multi_strategy_backtest_results WHERE backtest_run_label=?", (backtest_run_label,))
        conn.execute("DELETE FROM ai_multi_strategy_backtest_datasets WHERE backtest_run_label=?", (backtest_run_label,))
        conn.execute("DELETE FROM ai_multi_strategy_backtest_checks WHERE backtest_run_label=?", (backtest_run_label,))
        conn.execute("DELETE FROM ai_multi_strategy_backtest_runs WHERE backtest_run_label=?", (backtest_run_label,))
        conn.execute("DELETE FROM ai_multi_strategy_backtest_reports WHERE report_label=?", (report_label,))

        for row in datasets.values():
            conn.execute(
                """
                INSERT INTO ai_multi_strategy_backtest_datasets VALUES (
                    :dataset_id,:backtest_run_label,:benchmark_run_label,:created_at,
                    :asset_group,:symbol,:companion_symbol,:timeframe,:data_source,
                    :bar_count,:first_timestamp,:last_timestamp,:fixture_hash,:dataset_json,
                    :live_trading,:capital_deployment,:metadata_json
                )
                """,
                {**row, "metadata_json": canonical_json(row["metadata"])},
            )

        for row in results:
            metrics = {
                key: row[key]
                for key in (
                    "gross_return_pct", "net_return_pct", "annualized_volatility_pct",
                    "sharpe_ratio", "max_drawdown_pct", "win_rate_pct", "trade_count",
                    "turnover_units", "total_cost_bps", "cash_return_pct",
                    "buy_hold_return_pct", "random_return_pct", "excess_vs_cash_pct",
                    "excess_vs_buy_hold_pct", "excess_vs_random_pct",
                )
            }
            conn.execute(
                """
                INSERT INTO ai_multi_strategy_backtest_results VALUES (
                    :result_id,:backtest_run_label,:benchmark_run_label,:benchmark_plan_id,
                    :dataset_id,:created_at,:strategy_family_code,:asset_group,:symbol,
                    :companion_symbol,:timeframe,:cost_model_code,:bar_count,:trade_count,
                    :turnover_units,:gross_return_pct,:net_return_pct,:annualized_volatility_pct,
                    :sharpe_ratio,:max_drawdown_pct,:win_rate_pct,:total_cost_bps,
                    :cash_return_pct,:buy_hold_return_pct,:random_return_pct,
                    :excess_vs_cash_pct,:excess_vs_buy_hold_pct,:excess_vs_random_pct,
                    :research_status,:result_scope,:model_training_action,:model_artifact_action,
                    :model_promotion_action,:strategy_reweighting_action,:live_signal_action,
                    :exchange_order_action,:capital_action,:paid_api_action,
                    :profitability_claim_action,:live_trading,:live_order_sent,
                    :capital_deployment,:metrics_json,:metadata_json
                )
                """,
                {
                    **row,
                    "turnover_units": fmt(row["turnover_units"]),
                    "gross_return_pct": fmt(row["gross_return_pct"]),
                    "net_return_pct": fmt(row["net_return_pct"]),
                    "annualized_volatility_pct": fmt(row["annualized_volatility_pct"]),
                    "sharpe_ratio": fmt(row["sharpe_ratio"]),
                    "max_drawdown_pct": fmt(row["max_drawdown_pct"]),
                    "win_rate_pct": fmt(row["win_rate_pct"]),
                    "total_cost_bps": fmt(row["total_cost_bps"]),
                    "cash_return_pct": fmt(row["cash_return_pct"]),
                    "buy_hold_return_pct": fmt(row["buy_hold_return_pct"]),
                    "random_return_pct": fmt(row["random_return_pct"]),
                    "excess_vs_cash_pct": fmt(row["excess_vs_cash_pct"]),
                    "excess_vs_buy_hold_pct": fmt(row["excess_vs_buy_hold_pct"]),
                    "excess_vs_random_pct": fmt(row["excess_vs_random_pct"]),
                    "metrics_json": canonical_json(metrics),
                    "metadata_json": canonical_json(row["metadata"]),
                },
            )

        for row in baselines:
            metrics = {
                key: row[key]
                for key in (
                    "gross_return_pct", "net_return_pct", "annualized_volatility_pct",
                    "sharpe_ratio", "max_drawdown_pct", "win_rate_pct", "trade_count",
                    "turnover_units", "total_cost_bps",
                )
            }
            conn.execute(
                """
                INSERT INTO ai_multi_strategy_backtest_baselines VALUES (
                    :baseline_id,:backtest_run_label,:result_id,:created_at,:baseline_name,
                    :net_return_pct,:annualized_volatility_pct,:sharpe_ratio,
                    :max_drawdown_pct,:trade_count,:total_cost_bps,:baseline_scope,
                    :live_trading,:live_order_sent,:capital_deployment,:metrics_json
                )
                """,
                {
                    **row,
                    "net_return_pct": fmt(row["net_return_pct"]),
                    "annualized_volatility_pct": fmt(row["annualized_volatility_pct"]),
                    "sharpe_ratio": fmt(row["sharpe_ratio"]),
                    "max_drawdown_pct": fmt(row["max_drawdown_pct"]),
                    "total_cost_bps": fmt(row["total_cost_bps"]),
                    "metrics_json": canonical_json(metrics),
                },
            )

        for row in checks:
            conn.execute(
                """
                INSERT INTO ai_multi_strategy_backtest_checks VALUES (
                    :check_id,:backtest_run_label,:benchmark_run_label,:created_at,
                    :check_category,:check_name,:check_status,:observed_value,
                    :threshold_value,:check_reason,:backtest_scope,:live_trading,
                    :live_order_sent,:capital_deployment,:metadata_json
                )
                """,
                {**row, "metadata_json": canonical_json(row["metadata"])},
            )

        run_values = {
            key: summary[key]
            for key in (
                "backtest_run_label", "report_label", "benchmark_run_label", "created_at",
                "backtest_scope", "backtest_mode", "mission85_status",
                "source_plan_entry_count", "strategy_family_count", "asset_group_count",
                "timeframe_count", "fixture_dataset_count", "fixture_bar_count",
                "actual_backtest_count", "baseline_result_count",
                "positive_fixture_net_return_count", "negative_fixture_net_return_count",
                "outperformed_cash_count", "outperformed_buy_hold_count",
                "outperformed_random_count", "model_training_count", "model_artifact_count",
                "model_promotion_count", "strategy_reweighting_count", "live_signal_count",
                "exchange_order_count", "capital_deployment_count", "paid_api_count",
                "private_key_use_count", "profitability_claim_count", "backtest_check_count",
                "pass_check_count", "fail_check_count", "safety_breach_count",
                "engine_state", "engine_decision", "global_verdict", "recommended_action",
                "next_mission", "live_trading", "live_order_sent", "capital_deployment",
            )
        }
        conn.execute(
            """
            INSERT INTO ai_multi_strategy_backtest_runs VALUES (
                :backtest_run_label,:report_label,:benchmark_run_label,:created_at,
                :backtest_scope,:backtest_mode,:mission85_status,:source_plan_entry_count,
                :strategy_family_count,:asset_group_count,:timeframe_count,
                :fixture_dataset_count,:fixture_bar_count,:actual_backtest_count,
                :baseline_result_count,:positive_fixture_net_return_count,
                :negative_fixture_net_return_count,:outperformed_cash_count,
                :outperformed_buy_hold_count,:outperformed_random_count,
                :model_training_count,:model_artifact_count,:model_promotion_count,
                :strategy_reweighting_count,:live_signal_count,:exchange_order_count,
                :capital_deployment_count,:paid_api_count,:private_key_use_count,
                :profitability_claim_count,:backtest_check_count,:pass_check_count,
                :fail_check_count,:safety_breach_count,:engine_state,:engine_decision,
                :global_verdict,:recommended_action,:next_mission,:live_trading,
                :live_order_sent,:capital_deployment,:summary_json,:markdown_report
            )
            """,
            {
                **run_values,
                "summary_json": canonical_json({key: value for key, value in summary.items() if key not in {"markdown_report", "backtest_results"}}),
                "markdown_report": markdown_report,
            },
        )
        conn.execute(
            """
            INSERT INTO ai_multi_strategy_backtest_reports VALUES (
                :report_label,:backtest_run_label,:benchmark_run_label,:created_at,
                :global_verdict,:recommended_action,:report_json,:markdown_report,
                :live_trading,:live_order_sent,:capital_deployment
            )
            """,
            {
                "report_label": report_label,
                "backtest_run_label": backtest_run_label,
                "benchmark_run_label": benchmark_run_label,
                "created_at": created_at,
                "global_verdict": summary["global_verdict"],
                "recommended_action": summary["recommended_action"],
                "report_json": canonical_json({key: value for key, value in summary.items() if key not in {"markdown_report", "backtest_results"}}),
                "markdown_report": markdown_report,
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
            },
        )
        conn.commit()
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Mission 84.6 local fixture-based multi-strategy backtests.")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--backtest-run-label", default="mission84-6-local-check")
    parser.add_argument("--report-label", default="mission84-6-local-check-report")
    parser.add_argument("--benchmark-run-label", default="mission84-5-final-check")
    parser.add_argument("--min-plan-entries", type=int, default=72)
    parser.add_argument("--bars", type=int, default=260)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    summary = run_multi_strategy_backtest_pack(
        db_path=args.db_path,
        backtest_run_label=args.backtest_run_label,
        report_label=args.report_label,
        benchmark_run_label=args.benchmark_run_label,
        min_plan_entries=args.min_plan_entries,
        bars=args.bars,
    )
    output = {key: value for key, value in summary.items() if key not in {"markdown_report", "backtest_results"}}
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if summary["fail_check_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
