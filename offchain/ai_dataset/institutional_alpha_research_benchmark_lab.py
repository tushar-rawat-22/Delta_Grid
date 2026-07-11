"""
Mission 84.5: Institutional Alpha Research Benchmark Lab.

This module registers institutional-style alpha research families, asset universes,
cost models, and benchmark plan entries.

Boundary:
- no live trading
- no capital deployment
- no private keys
- no exchange orders
- no paid APIs
- no model training
- no model artifacts
- no model promotion
- no strategy reweighting
- no live signals
- no backtests yet in Mission 84.5

Mission 84.5 is a research registry and benchmark-planning layer.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_RUNS_TABLE = "ai_offline_model_training_harness_runs"

RUNS_TABLE = "ai_institutional_alpha_benchmark_runs"
STRATEGY_TABLE = "ai_alpha_strategy_family_registry"
ASSET_TABLE = "ai_alpha_asset_universe_registry"
COST_TABLE = "ai_alpha_cost_model_registry"
PLAN_TABLE = "ai_alpha_benchmark_plan_entries"
CHECKS_TABLE = "ai_alpha_benchmark_checks"
REPORTS_TABLE = "ai_alpha_benchmark_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

SOURCE_ENGINE_STATE_READY = "AI_OFFLINE_MODEL_TRAINING_HARNESS_READY_LOCAL_ONLY"
SOURCE_ENGINE_DECISION_READY = "AI_OFFLINE_MODEL_TRAINING_HARNESS_APPROVED_FOR_MODEL_PROMOTION_ENGINE_REVIEW"
SOURCE_VERDICT_READY = "AI_OFFLINE_MODEL_TRAINING_HARNESS_READY_SHADOW_ONLY"

BENCHMARK_SCOPE = "INSTITUTIONAL_ALPHA_RESEARCH_BENCHMARK_LAB_LOCAL_ONLY"
BENCHMARK_MODE = "REGISTRY_AND_PLAN_ONLY_NO_BACKTEST_NO_TRAINING"
MISSION85_STATUS = "PAUSED_UNTIL_ROBUST_ALPHA_CANDIDATES_EXIST"

PLAN_ACTION = "REGISTER_BENCHMARK_PLAN_ONLY"
DATASET_STATUS = "DATA_REQUIRED_NOT_LOADED"
BACKTEST_ACTION = "NO_BACKTEST_RUN_IN_MISSION_84_5"
MODEL_TRAINING_ACTION = "NO_MODEL_TRAINING"
MODEL_PROMOTION_ACTION = "NO_MODEL_PROMOTION"
MODEL_ARTIFACT_ACTION = "NO_MODEL_ARTIFACT_CREATED"
NO_STRATEGY_REWEIGHTING = "NO_STRATEGY_REWEIGHTING"
NO_LIVE_SIGNAL = "NO_LIVE_SIGNAL"
NO_EXCHANGE_ORDER = "NO_EXCHANGE_ORDER"
NO_CAPITAL_DEPLOYMENT = "NO_CAPITAL_DEPLOYMENT"
NO_PROFITABILITY_CLAIM = "NO_PROFITABILITY_CLAIM"

CHECK_PASS = "AI_ALPHA_BENCHMARK_CHECK_PASS"
CHECK_FAIL = "AI_ALPHA_BENCHMARK_CHECK_FAIL"

ENGINE_STATE_READY = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_READY_LOCAL_ONLY"
ENGINE_STATE_UNSTABLE = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_UNSTABLE"
ENGINE_STATE_BLOCKED = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_BLOCKED"
ENGINE_STATE_MISSING = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_MISSING"

ENGINE_DECISION_READY = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_APPROVED_FOR_MULTI_STRATEGY_BACKTEST_PACK"
ENGINE_DECISION_UNSTABLE = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_REVIEW_REQUIRED"
ENGINE_DECISION_BLOCK_SAFETY = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_BLOCKED_BY_SAFETY_POLICY"
ENGINE_DECISION_REJECT_MISSING = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_REJECTED_MISSING_TRAINING_HARNESS"

VERDICT_READY = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_ALPHA_RESEARCH_BENCHMARK_LAB_MISSING_EVIDENCE"

ACTION_READY = "HAND_OFF_ALPHA_BENCHMARK_LAB_TO_MULTI_STRATEGY_BACKTEST_PACK"
ACTION_REVIEW_UNSTABLE = "REVIEW_ALPHA_RESEARCH_BENCHMARK_LAB"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_ALPHA_RESEARCH_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_OFFLINE_MODEL_TRAINING_HARNESS"

NEXT_READY = "Mission 84.6 Multi-Strategy Backtest Pack"


STRATEGY_FAMILIES = [
    {
        "strategy_family_code": "TIME_SERIES_MOMENTUM",
        "strategy_family_name": "Time-Series Momentum / Trend Following",
        "research_basis": "Academic/public CTA-style trend-following benchmark family.",
        "hypothesis": "Assets with positive trailing returns may continue over intermediate horizons.",
        "primary_regime": "TRENDING",
        "expected_failure_mode": "sideways whipsaw and crowded momentum unwind",
        "requires_pairs": 0,
        "requires_funding_data": 0,
    },
    {
        "strategy_family_code": "CROSS_SECTIONAL_MOMENTUM_ROTATION",
        "strategy_family_name": "Cross-Sectional Momentum / Rotation",
        "research_basis": "Relative-strength ranking across asset baskets.",
        "hypothesis": "Top-ranked assets may outperform weaker peers on a risk-adjusted basis.",
        "primary_regime": "DISPERSION",
        "expected_failure_mode": "rank instability and reversal regime",
        "requires_pairs": 0,
        "requires_funding_data": 0,
    },
    {
        "strategy_family_code": "DONCHIAN_BREAKOUT_ATR",
        "strategy_family_name": "Donchian Breakout + ATR Risk",
        "research_basis": "Classic breakout/trend-following structure with volatility-aware exits.",
        "hypothesis": "Breakouts with volatility-aware risk controls may capture convex trend moves.",
        "primary_regime": "BREAKOUT",
        "expected_failure_mode": "false breakouts and high-turnover chop",
        "requires_pairs": 0,
        "requires_funding_data": 0,
    },
    {
        "strategy_family_code": "MEAN_REVERSION_ZSCORE",
        "strategy_family_name": "Mean-Reversion Z-Score",
        "research_basis": "Rolling z-score deviation and reversal benchmark.",
        "hypothesis": "Range-bound assets may revert after statistically large deviations.",
        "primary_regime": "RANGE_BOUND",
        "expected_failure_mode": "trend continuation against the mean-reversion entry",
        "requires_pairs": 0,
        "requires_funding_data": 0,
    },
    {
        "strategy_family_code": "PAIRS_STAT_ARB_RESIDUAL",
        "strategy_family_name": "Pairs / Statistical Arbitrage Residual Mean Reversion",
        "research_basis": "Residual/spread mean reversion across related instruments.",
        "hypothesis": "Related instruments may produce temporary spread dislocations.",
        "primary_regime": "MARKET_NEUTRAL",
        "expected_failure_mode": "relationship breakdown and unstable hedge ratio",
        "requires_pairs": 1,
        "requires_funding_data": 0,
    },
    {
        "strategy_family_code": "FUNDING_BASIS_CARRY",
        "strategy_family_name": "Funding / Basis Carry",
        "research_basis": "Crypto perpetual/futures carry and basis research family.",
        "hypothesis": "Funding/basis spreads may create carry opportunities after costs.",
        "primary_regime": "CARRY",
        "expected_failure_mode": "basis compression, liquidation cascades, funding inversion",
        "requires_pairs": 1,
        "requires_funding_data": 1,
    },
    {
        "strategy_family_code": "VOLATILITY_REGIME_FILTER",
        "strategy_family_name": "Volatility Regime Filter",
        "research_basis": "Regime overlay for strategy activation and risk scaling.",
        "hypothesis": "Strategy performance changes across volatility regimes.",
        "primary_regime": "REGIME_OVERLAY",
        "expected_failure_mode": "late regime detection and over-filtering",
        "requires_pairs": 0,
        "requires_funding_data": 0,
    },
    {
        "strategy_family_code": "HYBRID_ENSEMBLE",
        "strategy_family_name": "Hybrid Ensemble",
        "research_basis": "Combination layer for families that survive standalone tests.",
        "hypothesis": "Diversified standalone edges may improve robustness when combined.",
        "primary_regime": "MULTI_REGIME",
        "expected_failure_mode": "overfit ensemble weighting and hidden correlation",
        "requires_pairs": 0,
        "requires_funding_data": 0,
    },
]

ASSET_UNIVERSE = [
    ("CRYPTO", "BTC", "Bitcoin", "crypto", "USD", "HIGH"),
    ("CRYPTO", "ETH", "Ethereum", "crypto", "USD", "HIGH"),
    ("CRYPTO", "SOL", "Solana", "crypto", "USD", "MEDIUM"),
    ("CRYPTO", "BNB", "BNB", "crypto", "USD", "MEDIUM"),
    ("CRYPTO", "XRP", "XRP", "crypto", "USD", "MEDIUM"),
    ("CRYPTO", "ADA", "Cardano", "crypto", "USD", "MEDIUM"),
    ("CRYPTO", "DOGE", "Dogecoin", "crypto", "USD", "MEDIUM"),
    ("FX", "EURUSD", "Euro / US Dollar", "fx", "USD", "HIGH"),
    ("FX", "GBPUSD", "British Pound / US Dollar", "fx", "USD", "HIGH"),
    ("FX", "USDJPY", "US Dollar / Japanese Yen", "fx", "JPY", "HIGH"),
    ("FX", "AUDUSD", "Australian Dollar / US Dollar", "fx", "USD", "HIGH"),
    ("FX", "USDCHF", "US Dollar / Swiss Franc", "fx", "CHF", "MEDIUM"),
    ("FX", "USDCAD", "US Dollar / Canadian Dollar", "fx", "CAD", "HIGH"),
    ("ETF_MACRO", "SPY", "S&P 500 ETF", "etf", "USD", "HIGH"),
    ("ETF_MACRO", "QQQ", "Nasdaq 100 ETF", "etf", "USD", "HIGH"),
    ("ETF_MACRO", "TLT", "Long Treasury ETF", "etf", "USD", "HIGH"),
    ("ETF_MACRO", "GLD", "Gold ETF", "etf", "USD", "HIGH"),
    ("ETF_MACRO", "USO", "Oil ETF", "etf", "USD", "MEDIUM"),
    ("ETF_MACRO", "UUP", "US Dollar ETF", "etf", "USD", "MEDIUM"),
    ("ETF_MACRO", "HYG", "High Yield Bond ETF", "etf", "USD", "HIGH"),
    ("ETF_MACRO", "EEM", "Emerging Markets ETF", "etf", "USD", "HIGH"),
]

COST_MODELS = [
    {
        "cost_model_code": "CRYPTO_PAPER_CONSERVATIVE",
        "asset_group": "CRYPTO",
        "commission_bps": "10.0",
        "slippage_bps": "5.0",
        "spread_bps": "3.0",
        "funding_bps": "0.0",
        "borrow_bps": "0.0",
        "notes": "Conservative spot/perp placeholder; funding modeled separately later.",
    },
    {
        "cost_model_code": "FX_PAPER_CONSERVATIVE",
        "asset_group": "FX",
        "commission_bps": "0.0",
        "slippage_bps": "1.5",
        "spread_bps": "1.5",
        "funding_bps": "0.0",
        "borrow_bps": "0.0",
        "notes": "Paper FX spread/slippage placeholder.",
    },
    {
        "cost_model_code": "ETF_PAPER_CONSERVATIVE",
        "asset_group": "ETF_MACRO",
        "commission_bps": "0.0",
        "slippage_bps": "2.0",
        "spread_bps": "1.0",
        "funding_bps": "0.0",
        "borrow_bps": "0.0",
        "notes": "Paper ETF spread/slippage placeholder.",
    },
]

TIMEFRAMES = ["1D", "4H", "1H"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_benchmark_run_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission84-5-alpha-benchmark-lab-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission84-5-alpha-benchmark-report-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_float(value: Any) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return 0.0
        return number
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def round8(value: float) -> float:
    return round(float(value), 8)


def row_get(row: sqlite3.Row | dict[str, Any] | None, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        if key in row.keys():
            return row[key]
    except Exception:
        pass
    return default


def parse_labels(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return ["mission84-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()
        if not label:
            continue
        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid training run label: {label}")
        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one training run label is required")

    return labels


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_institutional_alpha_benchmark_runs (
                benchmark_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_training_run_label TEXT NOT NULL,
                source_feedback_run_label TEXT,
                source_execution_run_label TEXT,
                source_signal_run_label TEXT,
                source_policy_run_label TEXT,
                source_recommendation_run_label TEXT,
                source_governance_review_label TEXT,
                source_evaluation_label TEXT,
                source_guard_review_label TEXT,
                source_collection_label TEXT,
                source_registry_label TEXT,
                source_build_label TEXT,
                source_schedule_label TEXT,
                source_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                benchmark_scope TEXT NOT NULL,
                benchmark_mode TEXT NOT NULL,
                mission85_status TEXT NOT NULL,
                strategy_family_count INTEGER NOT NULL,
                asset_count INTEGER NOT NULL,
                asset_group_count INTEGER NOT NULL,
                timeframe_count INTEGER NOT NULL,
                cost_model_count INTEGER NOT NULL,
                benchmark_plan_entry_count INTEGER NOT NULL,
                actual_backtest_count INTEGER NOT NULL,
                model_training_count INTEGER NOT NULL,
                model_artifact_count INTEGER NOT NULL,
                model_promotion_count INTEGER NOT NULL,
                no_strategy_reweighting_count INTEGER NOT NULL,
                no_live_signal_count INTEGER NOT NULL,
                no_exchange_order_count INTEGER NOT NULL,
                no_capital_deployment_count INTEGER NOT NULL,
                no_paid_api_count INTEGER NOT NULL,
                no_profitability_claim_count INTEGER NOT NULL,
                source_training_candidate_count INTEGER NOT NULL,
                source_training_ready_candidate_count INTEGER NOT NULL,
                source_training_blocked_candidate_count INTEGER NOT NULL,
                source_actual_model_training_count INTEGER NOT NULL,
                source_model_artifact_count INTEGER NOT NULL,
                source_fail_check_count INTEGER NOT NULL,
                benchmark_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                leakage_breach_count INTEGER NOT NULL,
                baseline_accuracy_pct TEXT NOT NULL,
                average_label_confidence TEXT NOT NULL,
                average_net_paper_outcome_bps TEXT NOT NULL,
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
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_alpha_strategy_family_registry (
                strategy_family_code TEXT PRIMARY KEY,
                benchmark_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                strategy_family_name TEXT NOT NULL,
                research_basis TEXT NOT NULL,
                hypothesis TEXT NOT NULL,
                primary_regime TEXT NOT NULL,
                expected_failure_mode TEXT NOT NULL,
                requires_pairs INTEGER NOT NULL,
                requires_funding_data INTEGER NOT NULL,
                benchmark_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_alpha_asset_universe_registry (
                asset_id TEXT PRIMARY KEY,
                benchmark_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                asset_group TEXT NOT NULL,
                symbol TEXT NOT NULL,
                asset_name TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                quote_currency TEXT NOT NULL,
                liquidity_tier TEXT NOT NULL,
                benchmark_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_alpha_cost_model_registry (
                cost_model_code TEXT PRIMARY KEY,
                benchmark_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                asset_group TEXT NOT NULL,
                commission_bps TEXT NOT NULL,
                slippage_bps TEXT NOT NULL,
                spread_bps TEXT NOT NULL,
                funding_bps TEXT NOT NULL,
                borrow_bps TEXT NOT NULL,
                notes TEXT NOT NULL,
                benchmark_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_alpha_benchmark_plan_entries (
                benchmark_plan_id TEXT PRIMARY KEY,
                benchmark_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                strategy_family_code TEXT NOT NULL,
                asset_group TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                cost_model_code TEXT NOT NULL,
                dataset_status TEXT NOT NULL,
                benchmark_action TEXT NOT NULL,
                backtest_action TEXT NOT NULL,
                model_training_action TEXT NOT NULL,
                model_promotion_action TEXT NOT NULL,
                model_artifact_action TEXT NOT NULL,
                strategy_reweighting_action TEXT NOT NULL,
                live_signal_action TEXT NOT NULL,
                exchange_order_action TEXT NOT NULL,
                capital_action TEXT NOT NULL,
                paid_api_action TEXT NOT NULL,
                profitability_claim_action TEXT NOT NULL,
                benchmark_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_alpha_benchmark_checks (
                check_id TEXT PRIMARY KEY,
                benchmark_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_training_run_label TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                check_reason TEXT NOT NULL,
                benchmark_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_alpha_benchmark_reports (
                report_label TEXT PRIMARY KEY,
                benchmark_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_training_run_label TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                report_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL
            )
            """
        )

        conn.commit()


def base_metadata(role: str) -> dict[str, Any]:
    return {
        "alpha_research_role": role,
        "benchmark_scope": BENCHMARK_SCOPE,
        "benchmark_mode": BENCHMARK_MODE,
        "mission85_status": MISSION85_STATUS,
        "local_only": True,
        "paper_only": True,
        "backtest_run": False,
        "actual_model_training_enabled": False,
        "model_artifact_created": False,
        "model_promotion_enabled": False,
        "model_deployment_enabled": False,
        "live_deployment_enabled": False,
        "strategy_reweighting_enabled": False,
        "live_signal_generation_enabled": False,
        "exchange_order_enabled": False,
        "paid_api_used": False,
        "private_keys_used": False,
        "orders_sent": False,
        "real_capital_used": False,
        "autonomous_trading_enabled": False,
        "not_profitability_claim": True,
    }


def safety_problem(row: sqlite3.Row | dict[str, Any] | None) -> bool:
    if row is None:
        return False
    return (
        str(row_get(row, "live_trading", LIVE_TRADING_STATUS)) != LIVE_TRADING_STATUS
        or safe_int(row_get(row, "live_order_sent", LIVE_ORDER_SENT_VALUE)) != LIVE_ORDER_SENT_VALUE
        or str(row_get(row, "capital_deployment", CAPITAL_DEPLOYMENT_STATUS)) != CAPITAL_DEPLOYMENT_STATUS
    )


def load_source_training_run(conn: sqlite3.Connection, label: str) -> sqlite3.Row | None:
    if not table_exists(conn, SOURCE_RUNS_TABLE):
        return None
    return conn.execute(
        "SELECT * FROM ai_offline_model_training_harness_runs WHERE training_run_label = ?",
        (label,),
    ).fetchone()


def source_training_harness_is_ready(source_run: sqlite3.Row | None) -> bool:
    if source_run is None:
        return False
    return (
        row_get(source_run, "engine_state", "") == SOURCE_ENGINE_STATE_READY
        and row_get(source_run, "engine_decision", "") == SOURCE_ENGINE_DECISION_READY
        and row_get(source_run, "global_verdict", "") == SOURCE_VERDICT_READY
    )


def build_strategy_registry(benchmark_run_label: str, created_at: str) -> list[dict[str, Any]]:
    rows = []
    for strategy in STRATEGY_FAMILIES:
        row = {
            **strategy,
            "benchmark_run_label": benchmark_run_label,
            "created_at": created_at,
            "benchmark_scope": BENCHMARK_SCOPE,
            "live_trading": LIVE_TRADING_STATUS,
            "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
            "metadata": base_metadata("STRATEGY_FAMILY_REGISTRY"),
        }
        rows.append(row)
    return rows


def build_asset_registry(benchmark_run_label: str, created_at: str) -> list[dict[str, Any]]:
    rows = []
    for asset_group, symbol, asset_name, asset_type, quote_currency, liquidity_tier in ASSET_UNIVERSE:
        rows.append(
            {
                "asset_id": f"{asset_group}-{symbol}",
                "benchmark_run_label": benchmark_run_label,
                "created_at": created_at,
                "asset_group": asset_group,
                "symbol": symbol,
                "asset_name": asset_name,
                "asset_type": asset_type,
                "quote_currency": quote_currency,
                "liquidity_tier": liquidity_tier,
                "benchmark_scope": BENCHMARK_SCOPE,
                "live_trading": LIVE_TRADING_STATUS,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": base_metadata("ASSET_UNIVERSE_REGISTRY"),
            }
        )
    return rows


def build_cost_model_registry(benchmark_run_label: str, created_at: str) -> list[dict[str, Any]]:
    rows = []
    for cost_model in COST_MODELS:
        rows.append(
            {
                **cost_model,
                "benchmark_run_label": benchmark_run_label,
                "created_at": created_at,
                "benchmark_scope": BENCHMARK_SCOPE,
                "live_trading": LIVE_TRADING_STATUS,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": base_metadata("COST_MODEL_REGISTRY"),
            }
        )
    return rows


def cost_model_for_asset_group(asset_group: str) -> str:
    for cost_model in COST_MODELS:
        if cost_model["asset_group"] == asset_group:
            return cost_model["cost_model_code"]
    return "UNKNOWN_COST_MODEL"


def build_benchmark_plan_entries(
    benchmark_run_label: str,
    created_at: str,
    strategy_rows: list[dict[str, Any]],
    asset_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    asset_groups = sorted({row["asset_group"] for row in asset_rows})
    entries = []

    for strategy in strategy_rows:
        for asset_group in asset_groups:
            for timeframe in TIMEFRAMES:
                entries.append(
                    {
                        "benchmark_plan_id": f"{benchmark_run_label}-{strategy['strategy_family_code']}-{asset_group}-{timeframe}",
                        "benchmark_run_label": benchmark_run_label,
                        "created_at": created_at,
                        "strategy_family_code": strategy["strategy_family_code"],
                        "asset_group": asset_group,
                        "timeframe": timeframe,
                        "cost_model_code": cost_model_for_asset_group(asset_group),
                        "dataset_status": DATASET_STATUS,
                        "benchmark_action": PLAN_ACTION,
                        "backtest_action": BACKTEST_ACTION,
                        "model_training_action": MODEL_TRAINING_ACTION,
                        "model_promotion_action": MODEL_PROMOTION_ACTION,
                        "model_artifact_action": MODEL_ARTIFACT_ACTION,
                        "strategy_reweighting_action": NO_STRATEGY_REWEIGHTING,
                        "live_signal_action": NO_LIVE_SIGNAL,
                        "exchange_order_action": NO_EXCHANGE_ORDER,
                        "capital_action": NO_CAPITAL_DEPLOYMENT,
                        "paid_api_action": "NO_PAID_API",
                        "profitability_claim_action": NO_PROFITABILITY_CLAIM,
                        "benchmark_scope": BENCHMARK_SCOPE,
                        "live_trading": LIVE_TRADING_STATUS,
                        "live_order_sent": LIVE_ORDER_SENT_VALUE,
                        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                        "metadata": base_metadata("BENCHMARK_PLAN_ENTRY"),
                    }
                )

    return entries


def make_check(
    benchmark_run_label: str,
    created_at: str,
    source_training_label: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{benchmark_run_label}-{category}-{name}".replace(" ", "_"),
        "benchmark_run_label": benchmark_run_label,
        "created_at": created_at,
        "source_training_run_label": source_training_label,
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "threshold_value": str(threshold),
        "check_reason": reason,
        "benchmark_scope": BENCHMARK_SCOPE,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": base_metadata("ALPHA_BENCHMARK_CHECK"),
    }


def build_missing_checks(benchmark_run_label: str, created_at: str, source_training_label: str) -> list[dict[str, Any]]:
    return [
        make_check(
            benchmark_run_label,
            created_at,
            source_training_label,
            "availability",
            "source training run exists",
            False,
            "missing",
            "present",
            "Source Mission 84 training harness run is missing.",
        )
    ]


def build_benchmark_checks(
    benchmark_run_label: str,
    created_at: str,
    source_training_label: str,
    source_run: sqlite3.Row,
    strategies: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    cost_models: list[dict[str, Any]],
    plan_entries: list[dict[str, Any]],
    min_plan_entries: int,
) -> list[dict[str, Any]]:
    strategy_family_count = len(strategies)
    asset_count = len(assets)
    asset_group_count = len({row["asset_group"] for row in assets})
    cost_model_count = len(cost_models)
    timeframe_count = len(TIMEFRAMES)
    plan_count = len(plan_entries)

    actual_backtest_count = sum(1 for row in plan_entries if row["backtest_action"] != BACKTEST_ACTION)
    model_training_count = sum(1 for row in plan_entries if row["model_training_action"] != MODEL_TRAINING_ACTION)
    model_artifact_count = sum(1 for row in plan_entries if row["model_artifact_action"] != MODEL_ARTIFACT_ACTION)
    model_promotion_count = sum(1 for row in plan_entries if row["model_promotion_action"] != MODEL_PROMOTION_ACTION)
    no_reweight_count = sum(1 for row in plan_entries if row["strategy_reweighting_action"] == NO_STRATEGY_REWEIGHTING)
    no_live_signal_count = sum(1 for row in plan_entries if row["live_signal_action"] == NO_LIVE_SIGNAL)
    no_exchange_order_count = sum(1 for row in plan_entries if row["exchange_order_action"] == NO_EXCHANGE_ORDER)
    no_capital_count = sum(1 for row in plan_entries if row["capital_action"] == NO_CAPITAL_DEPLOYMENT)
    no_paid_api_count = sum(1 for row in plan_entries if row["paid_api_action"] == "NO_PAID_API")
    no_profitability_count = sum(1 for row in plan_entries if row["profitability_claim_action"] == NO_PROFITABILITY_CLAIM)

    source_ready = source_training_harness_is_ready(source_run)
    source_fail_checks = safe_int(row_get(source_run, "fail_check_count", 0))
    source_safety = safe_int(row_get(source_run, "safety_breach_count", 0))
    source_leakage = safe_int(row_get(source_run, "leakage_breach_count", 0))
    source_actual_training = safe_int(row_get(source_run, "actual_model_training_count", 0))
    source_model_artifacts = safe_int(row_get(source_run, "model_artifact_count", 0))
    source_ready_candidates = safe_int(row_get(source_run, "training_ready_candidate_count", 0))
    source_blocked_candidates = safe_int(row_get(source_run, "training_blocked_candidate_count", 0))
    source_candidate_count = safe_int(row_get(source_run, "training_candidate_count", 0))

    safety_count = source_safety + (1 if safety_problem(source_run) else 0)

    return [
        make_check(benchmark_run_label, created_at, source_training_label, "availability", "source training run exists", True, "present", "present", "Source training harness run exists."),
        make_check(benchmark_run_label, created_at, source_training_label, "source", "source offline training harness ready", source_ready, f"state={row_get(source_run, 'engine_state', '')}, decision={row_get(source_run, 'engine_decision', '')}, verdict={row_get(source_run, 'global_verdict', '')}", "ready local-only training harness", "Source Mission 84 training harness must be ready."),
        make_check(benchmark_run_label, created_at, source_training_label, "source", "source failed checks", source_fail_checks == 0, source_fail_checks, 0, "Source failed checks must remain zero."),
        make_check(benchmark_run_label, created_at, source_training_label, "safety", "safety breach count", safety_count == 0, safety_count, 0, "Safety breach count must be zero."),
        make_check(benchmark_run_label, created_at, source_training_label, "leakage", "leakage breach count", source_leakage == 0, source_leakage, 0, "Leakage breach count must be zero."),
        make_check(benchmark_run_label, created_at, source_training_label, "mission85", "mission 85 paused", MISSION85_STATUS == "PAUSED_UNTIL_ROBUST_ALPHA_CANDIDATES_EXIST", MISSION85_STATUS, "PAUSED_UNTIL_ROBUST_ALPHA_CANDIDATES_EXIST", "Mission 85 must remain paused until robust alpha candidates exist."),
        make_check(benchmark_run_label, created_at, source_training_label, "source_training", "source no actual training", source_actual_training == 0, source_actual_training, 0, "Source Mission 84 must not have run actual model training."),
        make_check(benchmark_run_label, created_at, source_training_label, "source_artifacts", "source no model artifacts", source_model_artifacts == 0, source_model_artifacts, 0, "Source Mission 84 must not have created model artifacts."),
        make_check(benchmark_run_label, created_at, source_training_label, "source_candidates", "source candidates locked", source_ready_candidates == 0 and source_blocked_candidates == source_candidate_count and source_candidate_count > 0, f"ready={source_ready_candidates}, blocked={source_blocked_candidates}, total={source_candidate_count}", "ready=0, blocked=total", "Source training candidates must remain locked before alpha research."),
        make_check(benchmark_run_label, created_at, source_training_label, "registry", "strategy family count", strategy_family_count >= 8, strategy_family_count, ">= 8", "Benchmark lab must register varied strategy families."),
        make_check(benchmark_run_label, created_at, source_training_label, "registry", "asset count", asset_count >= 21, asset_count, ">= 21", "Benchmark lab must register varied assets."),
        make_check(benchmark_run_label, created_at, source_training_label, "registry", "asset group count", asset_group_count >= 3, asset_group_count, ">= 3", "Benchmark lab must register crypto, FX, and ETF/macro groups."),
        make_check(benchmark_run_label, created_at, source_training_label, "registry", "timeframe count", timeframe_count >= 3, timeframe_count, ">= 3", "Benchmark lab must register daily, 4H, and 1H timeframes."),
        make_check(benchmark_run_label, created_at, source_training_label, "registry", "cost model count", cost_model_count >= 3, cost_model_count, ">= 3", "Benchmark lab must register cost models for all asset groups."),
        make_check(benchmark_run_label, created_at, source_training_label, "plan", "benchmark plan entry count", plan_count >= min_plan_entries, plan_count, f">= {min_plan_entries}", "Benchmark lab must create enough varied benchmark plans."),
        make_check(benchmark_run_label, created_at, source_training_label, "backtest", "no backtests run", actual_backtest_count == 0, actual_backtest_count, 0, "Mission 84.5 must not run backtests yet."),
        make_check(benchmark_run_label, created_at, source_training_label, "training", "no model training", model_training_count == 0, model_training_count, 0, "Mission 84.5 must not train models."),
        make_check(benchmark_run_label, created_at, source_training_label, "artifacts", "no model artifacts", model_artifact_count == 0, model_artifact_count, 0, "Mission 84.5 must not create model artifacts."),
        make_check(benchmark_run_label, created_at, source_training_label, "promotion", "no model promotion", model_promotion_count == 0, model_promotion_count, 0, "Mission 84.5 must not promote models."),
        make_check(benchmark_run_label, created_at, source_training_label, "strategy", "no strategy reweighting", no_reweight_count == plan_count and plan_count > 0, no_reweight_count, plan_count, "Mission 84.5 must not reweight strategies."),
        make_check(benchmark_run_label, created_at, source_training_label, "live_signal", "no live signals", no_live_signal_count == plan_count and plan_count > 0, no_live_signal_count, plan_count, "Mission 84.5 must not create live signals."),
        make_check(benchmark_run_label, created_at, source_training_label, "orders", "no exchange orders", no_exchange_order_count == plan_count and plan_count > 0, no_exchange_order_count, plan_count, "Mission 84.5 must not send exchange orders."),
        make_check(benchmark_run_label, created_at, source_training_label, "capital", "no capital deployment", no_capital_count == plan_count and plan_count > 0, no_capital_count, plan_count, "Mission 84.5 must not deploy capital."),
        make_check(benchmark_run_label, created_at, source_training_label, "paid_api", "no paid apis", no_paid_api_count == plan_count and plan_count > 0, no_paid_api_count, plan_count, "Mission 84.5 must not use paid APIs."),
        make_check(benchmark_run_label, created_at, source_training_label, "profitability", "no profitability claim", no_profitability_count == plan_count and plan_count > 0, no_profitability_count, plan_count, "Benchmark plans are not profitability evidence."),
        make_check(benchmark_run_label, created_at, source_training_label, "live_trading", "live trading disabled", str(row_get(source_run, "live_trading", "")) == LIVE_TRADING_STATUS, row_get(source_run, "live_trading", ""), LIVE_TRADING_STATUS, "Live trading must remain disabled."),
        make_check(benchmark_run_label, created_at, source_training_label, "capital_deployment", "capital deployment blocked", str(row_get(source_run, "capital_deployment", "")) == CAPITAL_DEPLOYMENT_STATUS, row_get(source_run, "capital_deployment", ""), CAPITAL_DEPLOYMENT_STATUS, "Capital deployment must remain blocked."),
    ]


def decide_engine_outcome(
    source_run: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if source_run is None:
        return (
            ENGINE_DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 84 Offline Model Training Harness",
            ENGINE_STATE_MISSING,
            "Source offline training harness evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            ENGINE_DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 84.5 safety remediation",
            ENGINE_STATE_BLOCKED,
            "Safety invariant failed during alpha benchmark lab registration.",
        )

    if failed:
        return (
            ENGINE_DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 84.5 Institutional Alpha Research Benchmark Lab",
            ENGINE_STATE_UNSTABLE,
            "Alpha benchmark lab failed one or more registration or safety checks.",
        )

    return (
        ENGINE_DECISION_READY,
        VERDICT_READY,
        ACTION_READY,
        NEXT_READY,
        ENGINE_STATE_READY,
        "Institutional alpha benchmark lab registered varied strategy families, asset universes, cost models, and benchmark plans. Mission 85 remains paused until robust alpha candidates exist.",
    )


def build_summary(
    db_path: str | Path,
    benchmark_run_label: str,
    report_label: str,
    created_at: str,
    source_training_label: str,
    source_run: sqlite3.Row | None,
    strategies: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    cost_models: list[dict[str, Any]],
    plan_entries: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    decision: str,
    verdict: str,
    action: str,
    next_mission: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    plan_count = len(plan_entries)
    asset_groups = {row["asset_group"] for row in assets}

    return {
        "benchmark_run_label": benchmark_run_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_training_run_label": source_training_label,
        "source_feedback_run_label": row_get(source_run, "source_feedback_run_label", None),
        "source_execution_run_label": row_get(source_run, "source_execution_run_label", None),
        "source_signal_run_label": row_get(source_run, "source_signal_run_label", None),
        "source_policy_run_label": row_get(source_run, "source_policy_run_label", None),
        "source_recommendation_run_label": row_get(source_run, "source_recommendation_run_label", None),
        "source_governance_review_label": row_get(source_run, "source_governance_review_label", None),
        "source_evaluation_label": row_get(source_run, "source_evaluation_label", None),
        "source_guard_review_label": row_get(source_run, "source_guard_review_label", None),
        "source_collection_label": row_get(source_run, "source_collection_label", None),
        "source_registry_label": row_get(source_run, "source_registry_label", None),
        "source_build_label": row_get(source_run, "source_build_label", None),
        "source_schedule_label": row_get(source_run, "source_schedule_label", None),
        "source_learning_run_label": row_get(source_run, "source_learning_run_label", None),
        "source_multi_cycle_track_label": row_get(source_run, "source_multi_cycle_track_label", None),
        "source_session_label": row_get(source_run, "source_session_label", None),
        "source_portfolio_label": row_get(source_run, "source_portfolio_label", None),
        "benchmark_scope": BENCHMARK_SCOPE,
        "benchmark_mode": BENCHMARK_MODE,
        "mission85_status": MISSION85_STATUS,
        "strategy_family_count": len(strategies),
        "asset_count": len(assets),
        "asset_group_count": len(asset_groups),
        "timeframe_count": len(TIMEFRAMES),
        "cost_model_count": len(cost_models),
        "benchmark_plan_entry_count": plan_count,
        "actual_backtest_count": sum(1 for row in plan_entries if row["backtest_action"] != BACKTEST_ACTION),
        "model_training_count": sum(1 for row in plan_entries if row["model_training_action"] != MODEL_TRAINING_ACTION),
        "model_artifact_count": sum(1 for row in plan_entries if row["model_artifact_action"] != MODEL_ARTIFACT_ACTION),
        "model_promotion_count": sum(1 for row in plan_entries if row["model_promotion_action"] != MODEL_PROMOTION_ACTION),
        "no_strategy_reweighting_count": sum(1 for row in plan_entries if row["strategy_reweighting_action"] == NO_STRATEGY_REWEIGHTING),
        "no_live_signal_count": sum(1 for row in plan_entries if row["live_signal_action"] == NO_LIVE_SIGNAL),
        "no_exchange_order_count": sum(1 for row in plan_entries if row["exchange_order_action"] == NO_EXCHANGE_ORDER),
        "no_capital_deployment_count": sum(1 for row in plan_entries if row["capital_action"] == NO_CAPITAL_DEPLOYMENT),
        "no_paid_api_count": sum(1 for row in plan_entries if row["paid_api_action"] == "NO_PAID_API"),
        "no_profitability_claim_count": sum(1 for row in plan_entries if row["profitability_claim_action"] == NO_PROFITABILITY_CLAIM),
        "source_training_candidate_count": safe_int(row_get(source_run, "training_candidate_count", 0)),
        "source_training_ready_candidate_count": safe_int(row_get(source_run, "training_ready_candidate_count", 0)),
        "source_training_blocked_candidate_count": safe_int(row_get(source_run, "training_blocked_candidate_count", 0)),
        "source_actual_model_training_count": safe_int(row_get(source_run, "actual_model_training_count", 0)),
        "source_model_artifact_count": safe_int(row_get(source_run, "model_artifact_count", 0)),
        "source_fail_check_count": safe_int(row_get(source_run, "fail_check_count", 0)),
        "benchmark_check_count": len(checks),
        "pass_check_count": sum(1 for check in checks if check["check_status"] == CHECK_PASS),
        "fail_check_count": sum(1 for check in checks if check["check_status"] == CHECK_FAIL),
        "safety_breach_count": safe_int(row_get(source_run, "safety_breach_count", 0)),
        "leakage_breach_count": safe_int(row_get(source_run, "leakage_breach_count", 0)),
        "baseline_accuracy_pct": round8(safe_float(row_get(source_run, "baseline_accuracy_pct", 0.0))),
        "average_label_confidence": round8(safe_float(row_get(source_run, "average_label_confidence", 0.0))),
        "average_net_paper_outcome_bps": round8(safe_float(row_get(source_run, "average_net_paper_outcome_bps", 0.0))),
        "strategy_families": strategies,
        "asset_universe": assets,
        "cost_models": cost_models,
        "benchmark_plan_entries": plan_entries,
        "benchmark_checks": checks,
        "engine_state": state,
        "engine_decision": decision,
        "global_verdict": verdict,
        "recommended_action": action,
        "next_mission": next_mission,
        "decision_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    strategy_lines = [
        f"- {row['strategy_family_code']}: {row['strategy_family_name']} | regime={row['primary_regime']}"
        for row in summary["strategy_families"]
    ]

    asset_group_counts: dict[str, int] = {}
    for row in summary["asset_universe"]:
        asset_group_counts[row["asset_group"]] = asset_group_counts.get(row["asset_group"], 0) + 1
    asset_lines = [f"- {group}: {count} assets" for group, count in sorted(asset_group_counts.items())]

    cost_lines = [
        f"- {row['cost_model_code']}: group={row['asset_group']}, commission={row['commission_bps']}bps, slippage={row['slippage_bps']}bps, spread={row['spread_bps']}bps"
        for row in summary["cost_models"]
    ]

    check_lines = [
        f"- {check['check_category']} / {check['check_name']}: status={check['check_status']}, observed={check['observed_value']}, threshold={check['threshold_value']}"
        for check in summary["benchmark_checks"]
    ]

    return f"""# DeltaGrid Mission 84.5 Institutional Alpha Research Benchmark Lab Report

Report label: {summary['report_label']}
Benchmark run label: {summary['benchmark_run_label']}
Created at: {summary['created_at']}
Source training run label: {summary['source_training_run_label']}
Source feedback run label: {summary['source_feedback_run_label']}
Source execution run label: {summary['source_execution_run_label']}
Source signal run label: {summary['source_signal_run_label']}
Source policy run label: {summary['source_policy_run_label']}
Source recommendation run label: {summary['source_recommendation_run_label']}

## Benchmark Lab Summary

Benchmark scope: {summary['benchmark_scope']}
Benchmark mode: {summary['benchmark_mode']}
Mission 85 status: {summary['mission85_status']}

Strategy family count: {summary['strategy_family_count']}
Asset count: {summary['asset_count']}
Asset group count: {summary['asset_group_count']}
Timeframe count: {summary['timeframe_count']}
Cost model count: {summary['cost_model_count']}
Benchmark plan entry count: {summary['benchmark_plan_entry_count']}

Actual backtest count: {summary['actual_backtest_count']}
Model training count: {summary['model_training_count']}
Model artifact count: {summary['model_artifact_count']}
Model promotion count: {summary['model_promotion_count']}
No strategy reweighting count: {summary['no_strategy_reweighting_count']}
No live signal count: {summary['no_live_signal_count']}
No exchange order count: {summary['no_exchange_order_count']}
No capital deployment count: {summary['no_capital_deployment_count']}
No paid API count: {summary['no_paid_api_count']}
No profitability claim count: {summary['no_profitability_claim_count']}

Source training candidate count: {summary['source_training_candidate_count']}
Source training ready candidate count: {summary['source_training_ready_candidate_count']}
Source training blocked candidate count: {summary['source_training_blocked_candidate_count']}
Source actual model training count: {summary['source_actual_model_training_count']}
Source model artifact count: {summary['source_model_artifact_count']}

Benchmark check count: {summary['benchmark_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}
Leakage breach count: {summary['leakage_breach_count']}

## Strategy Families

{chr(10).join(strategy_lines)}

## Asset Universe

{chr(10).join(asset_lines)}

## Cost Models

{chr(10).join(cost_lines)}

## Checks

{chr(10).join(check_lines)}

## Decision

Engine state: {summary['engine_state']}
Engine decision: {summary['engine_decision']}
Global verdict: {summary['global_verdict']}
Recommended action: {summary['recommended_action']}
Decision reason: {summary['decision_reason']}
Next mission: {summary['next_mission']}

## Safety Statement

Mission 85 remains paused until robust alpha candidates exist.

This lab creates strategy, asset, cost, and benchmark-plan registries only.
It does not run backtests.
It does not train models.
It does not create model artifacts.
It does not promote models.
It does not reweight strategies.
It does not create live trading signals.
It does not send exchange orders.
It does not deploy capital.
It does not use paid APIs.
It does not use private keys.
It does not perform autonomous live trading.

Benchmark plans are not profitability evidence.
"""


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any], columns: list[str]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
        [row[column] for column in columns],
    )


def persist_benchmark_run(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for table in (STRATEGY_TABLE, ASSET_TABLE, COST_TABLE, PLAN_TABLE, CHECKS_TABLE, RUNS_TABLE):
            conn.execute(f"DELETE FROM {table} WHERE benchmark_run_label = ?", (summary["benchmark_run_label"],))

        conn.execute(
            "DELETE FROM ai_alpha_benchmark_reports WHERE benchmark_run_label = ? OR report_label = ?",
            (summary["benchmark_run_label"], summary["report_label"]),
        )

        for row in summary["strategy_families"]:
            stored = dict(row)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                STRATEGY_TABLE,
                stored,
                [
                    "strategy_family_code", "benchmark_run_label", "created_at",
                    "strategy_family_name", "research_basis", "hypothesis",
                    "primary_regime", "expected_failure_mode", "requires_pairs",
                    "requires_funding_data", "benchmark_scope", "live_trading",
                    "capital_deployment", "metadata_json",
                ],
            )

        for row in summary["asset_universe"]:
            stored = dict(row)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                ASSET_TABLE,
                stored,
                [
                    "asset_id", "benchmark_run_label", "created_at",
                    "asset_group", "symbol", "asset_name", "asset_type",
                    "quote_currency", "liquidity_tier", "benchmark_scope",
                    "live_trading", "capital_deployment", "metadata_json",
                ],
            )

        for row in summary["cost_models"]:
            stored = dict(row)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                COST_TABLE,
                stored,
                [
                    "cost_model_code", "benchmark_run_label", "created_at",
                    "asset_group", "commission_bps", "slippage_bps",
                    "spread_bps", "funding_bps", "borrow_bps", "notes",
                    "benchmark_scope", "live_trading", "capital_deployment",
                    "metadata_json",
                ],
            )

        for row in summary["benchmark_plan_entries"]:
            stored = dict(row)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                PLAN_TABLE,
                stored,
                [
                    "benchmark_plan_id", "benchmark_run_label", "created_at",
                    "strategy_family_code", "asset_group", "timeframe",
                    "cost_model_code", "dataset_status", "benchmark_action",
                    "backtest_action", "model_training_action",
                    "model_promotion_action", "model_artifact_action",
                    "strategy_reweighting_action", "live_signal_action",
                    "exchange_order_action", "capital_action", "paid_api_action",
                    "profitability_claim_action", "benchmark_scope", "live_trading",
                    "live_order_sent", "capital_deployment", "metadata_json",
                ],
            )

        for check in summary["benchmark_checks"]:
            stored = dict(check)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CHECKS_TABLE,
                stored,
                [
                    "check_id", "benchmark_run_label", "created_at",
                    "source_training_run_label", "check_category", "check_name",
                    "check_status", "observed_value", "threshold_value",
                    "check_reason", "benchmark_scope", "live_trading",
                    "live_order_sent", "capital_deployment", "metadata_json",
                ],
            )

        run_row = {
            **{key: summary[key] for key in [
                "benchmark_run_label", "report_label", "created_at",
                "source_training_run_label", "source_feedback_run_label",
                "source_execution_run_label", "source_signal_run_label",
                "source_policy_run_label", "source_recommendation_run_label",
                "source_governance_review_label", "source_evaluation_label",
                "source_guard_review_label", "source_collection_label",
                "source_registry_label", "source_build_label",
                "source_schedule_label", "source_learning_run_label",
                "source_multi_cycle_track_label", "source_session_label",
                "source_portfolio_label", "benchmark_scope", "benchmark_mode",
                "mission85_status", "strategy_family_count", "asset_count",
                "asset_group_count", "timeframe_count", "cost_model_count",
                "benchmark_plan_entry_count", "actual_backtest_count",
                "model_training_count", "model_artifact_count",
                "model_promotion_count", "no_strategy_reweighting_count",
                "no_live_signal_count", "no_exchange_order_count",
                "no_capital_deployment_count", "no_paid_api_count",
                "no_profitability_claim_count", "source_training_candidate_count",
                "source_training_ready_candidate_count",
                "source_training_blocked_candidate_count",
                "source_actual_model_training_count", "source_model_artifact_count",
                "source_fail_check_count", "benchmark_check_count",
                "pass_check_count", "fail_check_count", "safety_breach_count",
                "leakage_breach_count", "baseline_accuracy_pct",
                "average_label_confidence", "average_net_paper_outcome_bps",
                "engine_state", "engine_decision", "global_verdict",
                "recommended_action", "next_mission", "live_trading",
                "live_order_sent", "capital_deployment",
            ]},
            "summary_json": json.dumps(summary, sort_keys=True),
            "markdown_report": markdown_report,
        }

        insert_row(
            conn,
            RUNS_TABLE,
            run_row,
            [
                "benchmark_run_label", "report_label", "created_at",
                "source_training_run_label", "source_feedback_run_label",
                "source_execution_run_label", "source_signal_run_label",
                "source_policy_run_label", "source_recommendation_run_label",
                "source_governance_review_label", "source_evaluation_label",
                "source_guard_review_label", "source_collection_label",
                "source_registry_label", "source_build_label",
                "source_schedule_label", "source_learning_run_label",
                "source_multi_cycle_track_label", "source_session_label",
                "source_portfolio_label", "benchmark_scope", "benchmark_mode",
                "mission85_status", "strategy_family_count", "asset_count",
                "asset_group_count", "timeframe_count", "cost_model_count",
                "benchmark_plan_entry_count", "actual_backtest_count",
                "model_training_count", "model_artifact_count",
                "model_promotion_count", "no_strategy_reweighting_count",
                "no_live_signal_count", "no_exchange_order_count",
                "no_capital_deployment_count", "no_paid_api_count",
                "no_profitability_claim_count", "source_training_candidate_count",
                "source_training_ready_candidate_count",
                "source_training_blocked_candidate_count",
                "source_actual_model_training_count", "source_model_artifact_count",
                "source_fail_check_count", "benchmark_check_count",
                "pass_check_count", "fail_check_count", "safety_breach_count",
                "leakage_breach_count", "baseline_accuracy_pct",
                "average_label_confidence", "average_net_paper_outcome_bps",
                "engine_state", "engine_decision", "global_verdict",
                "recommended_action", "next_mission", "live_trading",
                "live_order_sent", "capital_deployment", "summary_json",
                "markdown_report",
            ],
        )

        report_row = {
            "report_label": summary["report_label"],
            "benchmark_run_label": summary["benchmark_run_label"],
            "created_at": summary["created_at"],
            "source_training_run_label": summary["source_training_run_label"],
            "global_verdict": summary["global_verdict"],
            "recommended_action": summary["recommended_action"],
            "report_json": json.dumps(summary, sort_keys=True),
            "markdown_report": markdown_report,
            "live_trading": LIVE_TRADING_STATUS,
            "live_order_sent": LIVE_ORDER_SENT_VALUE,
            "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        }

        insert_row(
            conn,
            REPORTS_TABLE,
            report_row,
            [
                "report_label", "benchmark_run_label", "created_at",
                "source_training_run_label", "global_verdict",
                "recommended_action", "report_json", "markdown_report",
                "live_trading", "live_order_sent", "capital_deployment",
            ],
        )

        conn.commit()


def run_institutional_alpha_research_benchmark_lab(
    db_path: str | Path = "offchain/deltagrid.db",
    benchmark_run_label: str | None = None,
    report_label: str | None = None,
    training_run_label: str = "mission84-final-check",
    min_plan_entries: int = 72,
) -> dict[str, Any]:
    if min_plan_entries <= 0:
        raise ValueError("min_plan_entries must be positive")

    db = Path(db_path)
    run_label = benchmark_run_label or new_benchmark_run_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_training_label = parse_labels(training_run_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        source_run = load_source_training_run(conn, source_training_label)

    strategies = build_strategy_registry(run_label, created_at)
    assets = build_asset_registry(run_label, created_at)
    cost_models = build_cost_model_registry(run_label, created_at)
    plan_entries = build_benchmark_plan_entries(run_label, created_at, strategies, assets)

    if source_run is None:
        checks = build_missing_checks(run_label, created_at, source_training_label)
    else:
        checks = build_benchmark_checks(
            benchmark_run_label=run_label,
            created_at=created_at,
            source_training_label=source_training_label,
            source_run=source_run,
            strategies=strategies,
            assets=assets,
            cost_models=cost_models,
            plan_entries=plan_entries,
            min_plan_entries=min_plan_entries,
        )

    decision, verdict, action, next_mission, state, reason = decide_engine_outcome(
        source_run=source_run,
        checks=checks,
    )

    summary = build_summary(
        db_path=db,
        benchmark_run_label=run_label,
        report_label=report,
        created_at=created_at,
        source_training_label=source_training_label,
        source_run=source_run,
        strategies=strategies,
        assets=assets,
        cost_models=cost_models,
        plan_entries=plan_entries,
        checks=checks,
        decision=decision,
        verdict=verdict,
        action=action,
        next_mission=next_mission,
        state=state,
        reason=reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_benchmark_run(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid institutional alpha research benchmark lab.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--benchmark-run-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--training-run-label", default="mission84-final-check")
    parser.add_argument("--min-plan-entries", type=int, default=72)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_institutional_alpha_research_benchmark_lab(
        db_path=args.db,
        benchmark_run_label=args.benchmark_run_label,
        report_label=args.report_label,
        training_run_label=args.training_run_label,
        min_plan_entries=args.min_plan_entries,
    )

    print(result["markdown_report"] if args.markdown else json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
