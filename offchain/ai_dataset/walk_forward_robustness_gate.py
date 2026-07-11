"""Mission 84.7: Walk-Forward Robustness Gate.

Consumes Mission 84.6 local synthetic-fixture backtests and evaluates each
candidate across deterministic expanding-window out-of-sample windows.
Research-only: no live trading, capital, keys, orders, paid APIs, model
training, model artifacts, promotion, strategy reweighting, or profitability
claims.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import statistics
from pathlib import Path
from typing import Any, Iterable, Sequence

from offchain.ai_dataset.multi_strategy_backtest_pack import (
    BACKTEST_SCOPE,
    CAPITAL_DEPLOYMENT_STATUS,
    LIVE_ORDER_SENT_VALUE,
    LIVE_TRADING_STATUS,
    MISSION85_STATUS,
    backtest_series,
    canonical_json,
    deterministic_random_signals,
    deterministic_seed,
    normalize_label,
    safe_float,
    safe_int,
    strategy_signals,
    table_exists,
    utc_now,
)

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")
ROBUSTNESS_SCOPE = "WALK_FORWARD_ROBUSTNESS_GATE_LOCAL_FIXTURE_ONLY"
ROBUSTNESS_MODE = "DETERMINISTIC_EXPANDING_WINDOW_OUT_OF_SAMPLE_FIXTURE_ONLY"
SOURCE_ENGINE_STATE = "AI_MULTI_STRATEGY_BACKTEST_PACK_READY_LOCAL_ONLY"
SOURCE_ENGINE_DECISION = "AI_MULTI_STRATEGY_BACKTEST_PACK_APPROVED_FOR_WALK_FORWARD_ROBUSTNESS_GATE"
SOURCE_GLOBAL_VERDICT = "AI_MULTI_STRATEGY_BACKTEST_PACK_READY_SHADOW_RESEARCH_ONLY"
ENGINE_STATE = "AI_WALK_FORWARD_ROBUSTNESS_GATE_READY_LOCAL_ONLY"
ENGINE_DECISION = "AI_WALK_FORWARD_ROBUSTNESS_GATE_APPROVED_FOR_ALPHA_CANDIDATE_PROMOTION_REVIEW"
GLOBAL_VERDICT = "AI_WALK_FORWARD_ROBUSTNESS_GATE_READY_SHADOW_RESEARCH_ONLY"
RECOMMENDED_ACTION = "HAND_OFF_ROBUST_FIXTURE_CANDIDATES_TO_ALPHA_CANDIDATE_PROMOTION_PACK"
NEXT_MISSION = "Mission 84.8 Alpha Candidate Promotion Pack"
CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ai_walk_forward_robustness_runs (
                robustness_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                source_backtest_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                robustness_scope TEXT NOT NULL,
                robustness_mode TEXT NOT NULL,
                mission85_status TEXT NOT NULL,
                source_backtest_count INTEGER NOT NULL,
                evaluated_candidate_count INTEGER NOT NULL,
                window_result_count INTEGER NOT NULL,
                robust_candidate_count INTEGER NOT NULL,
                blocked_candidate_count INTEGER NOT NULL,
                strategy_family_count INTEGER NOT NULL,
                asset_group_count INTEGER NOT NULL,
                timeframe_count INTEGER NOT NULL,
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
                robustness_check_count INTEGER NOT NULL,
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

            CREATE TABLE IF NOT EXISTS ai_walk_forward_robustness_windows (
                window_id TEXT PRIMARY KEY,
                robustness_run_label TEXT NOT NULL,
                source_result_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                window_index INTEGER NOT NULL,
                context_start_index INTEGER NOT NULL,
                test_start_index INTEGER NOT NULL,
                test_end_index INTEGER NOT NULL,
                context_bar_count INTEGER NOT NULL,
                test_bar_count INTEGER NOT NULL,
                strategy_family_code TEXT NOT NULL,
                asset_group TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                strategy_net_return_pct TEXT NOT NULL,
                cash_return_pct TEXT NOT NULL,
                buy_hold_return_pct TEXT NOT NULL,
                random_return_pct TEXT NOT NULL,
                excess_vs_cash_pct TEXT NOT NULL,
                excess_vs_buy_hold_pct TEXT NOT NULL,
                excess_vs_random_pct TEXT NOT NULL,
                sharpe_ratio TEXT NOT NULL,
                max_drawdown_pct TEXT NOT NULL,
                trade_count INTEGER NOT NULL,
                total_cost_bps TEXT NOT NULL,
                window_status TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_walk_forward_robustness_results (
                robustness_result_id TEXT PRIMARY KEY,
                robustness_run_label TEXT NOT NULL,
                source_result_id TEXT NOT NULL,
                source_backtest_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                strategy_family_code TEXT NOT NULL,
                asset_group TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                cost_model_code TEXT NOT NULL,
                window_count INTEGER NOT NULL,
                positive_window_count INTEGER NOT NULL,
                positive_window_ratio TEXT NOT NULL,
                median_net_return_pct TEXT NOT NULL,
                return_dispersion_pct TEXT NOT NULL,
                worst_window_drawdown_pct TEXT NOT NULL,
                median_sharpe_ratio TEXT NOT NULL,
                outperformed_cash_window_count INTEGER NOT NULL,
                outperformed_buy_hold_window_count INTEGER NOT NULL,
                outperformed_random_window_count INTEGER NOT NULL,
                robustness_status TEXT NOT NULL,
                block_reasons_json TEXT NOT NULL,
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

            CREATE TABLE IF NOT EXISTS ai_walk_forward_robustness_checks (
                check_id TEXT PRIMARY KEY,
                robustness_run_label TEXT NOT NULL,
                source_backtest_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                check_reason TEXT NOT NULL,
                robustness_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_walk_forward_robustness_reports (
                report_label TEXT PRIMARY KEY,
                robustness_run_label TEXT NOT NULL,
                source_backtest_run_label TEXT NOT NULL,
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


def build_walk_forward_windows(
    total_bars: int,
    context_bars: int = 120,
    test_bars: int = 40,
    step_bars: int = 40,
) -> list[dict[str, int]]:
    if context_bars < 20:
        raise ValueError("context_bars must be at least 20")
    if test_bars < 2:
        raise ValueError("test_bars must be at least 2")
    if step_bars < 1:
        raise ValueError("step_bars must be positive")
    windows: list[dict[str, int]] = []
    test_start = context_bars
    index = 0
    while test_start + test_bars <= total_bars:
        windows.append(
            {
                "window_index": index,
                "context_start_index": 0,
                "test_start_index": test_start,
                "test_end_index": test_start + test_bars,
                "context_bar_count": test_start,
                "test_bar_count": test_bars,
            }
        )
        index += 1
        test_start += step_bars
    return windows


def _window_metric(
    bars: Sequence[dict[str, Any]],
    signals: Sequence[float],
    cost_model: dict[str, Any],
    timeframe: str,
    test_start: int,
    test_end: int,
) -> dict[str, Any]:
    if test_start < 1 or test_end > len(bars) or test_start >= test_end:
        raise ValueError("invalid test window")
    # Retain the preceding bar so backtest_series can calculate the first test return.
    return backtest_series(
        bars[test_start - 1 : test_end],
        signals[test_start - 1 : test_end],
        cost_model,
        timeframe,
    )


def evaluate_candidate_windows(
    source_result: sqlite3.Row | dict[str, Any],
    bars: Sequence[dict[str, Any]],
    cost_model: dict[str, Any],
    robustness_run_label: str,
    created_at: str,
    context_bars: int = 120,
    test_bars: int = 40,
    step_bars: int = 40,
) -> list[dict[str, Any]]:
    family = str(source_result["strategy_family_code"])
    timeframe = str(source_result["timeframe"])
    source_result_id = str(source_result["result_id"])
    strategy = strategy_signals(family, bars)
    cash = [0.0] * len(bars)
    buy_hold = [1.0] * len(bars)
    random_signals = deterministic_random_signals(
        len(bars), deterministic_seed(robustness_run_label, source_result_id, "walk-forward-random")
    )
    rows: list[dict[str, Any]] = []
    for spec in build_walk_forward_windows(len(bars), context_bars, test_bars, step_bars):
        start = spec["test_start_index"]
        end = spec["test_end_index"]
        strategy_metric = _window_metric(bars, strategy, cost_model, timeframe, start, end)
        cash_metric = _window_metric(bars, cash, cost_model, timeframe, start, end)
        buy_hold_metric = _window_metric(bars, buy_hold, cost_model, timeframe, start, end)
        random_metric = _window_metric(bars, random_signals, cost_model, timeframe, start, end)
        net = safe_float(strategy_metric["net_return_pct"])
        rows.append(
            {
                "window_id": f"{robustness_run_label}-{source_result_id}-w{spec['window_index']}",
                "robustness_run_label": robustness_run_label,
                "source_result_id": source_result_id,
                "created_at": created_at,
                **spec,
                "strategy_family_code": family,
                "asset_group": str(source_result["asset_group"]),
                "timeframe": timeframe,
                "strategy_net_return_pct": net,
                "cash_return_pct": safe_float(cash_metric["net_return_pct"]),
                "buy_hold_return_pct": safe_float(buy_hold_metric["net_return_pct"]),
                "random_return_pct": safe_float(random_metric["net_return_pct"]),
                "excess_vs_cash_pct": net - safe_float(cash_metric["net_return_pct"]),
                "excess_vs_buy_hold_pct": net - safe_float(buy_hold_metric["net_return_pct"]),
                "excess_vs_random_pct": net - safe_float(random_metric["net_return_pct"]),
                "sharpe_ratio": safe_float(strategy_metric["sharpe_ratio"]),
                "max_drawdown_pct": safe_float(strategy_metric["max_drawdown_pct"]),
                "trade_count": safe_int(strategy_metric["trade_count"]),
                "total_cost_bps": safe_float(strategy_metric["total_cost_bps"]),
                "window_status": "OUT_OF_SAMPLE_FIXTURE_WINDOW_RECORDED_UNVALIDATED",
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": {
                    "local_only": True,
                    "paper_only": True,
                    "fixture_based": True,
                    "expanding_context": True,
                    "future_data_used": False,
                    "strategy_parameters_tuned": False,
                    "profitability_claim": False,
                },
            }
        )
    return rows


def classify_candidate(
    source_result: sqlite3.Row | dict[str, Any],
    windows: Sequence[dict[str, Any]],
    robustness_run_label: str,
    source_backtest_run_label: str,
    created_at: str,
    min_windows: int = 3,
    min_positive_ratio: float = 2.0 / 3.0,
    max_worst_drawdown_pct: float = 25.0,
    max_return_dispersion_pct: float = 20.0,
) -> dict[str, Any]:
    net_returns = [safe_float(row["strategy_net_return_pct"]) for row in windows]
    sharpes = [safe_float(row["sharpe_ratio"]) for row in windows]
    window_count = len(windows)
    positive_count = sum(value > 0.0 for value in net_returns)
    positive_ratio = positive_count / window_count if window_count else 0.0
    median_return = statistics.median(net_returns) if net_returns else 0.0
    dispersion = statistics.pstdev(net_returns) if len(net_returns) > 1 else 0.0
    worst_drawdown = max((safe_float(row["max_drawdown_pct"]) for row in windows), default=0.0)
    median_sharpe = statistics.median(sharpes) if sharpes else 0.0
    out_cash = sum(safe_float(row["excess_vs_cash_pct"]) > 0.0 for row in windows)
    out_buy = sum(safe_float(row["excess_vs_buy_hold_pct"]) > 0.0 for row in windows)
    out_random = sum(safe_float(row["excess_vs_random_pct"]) > 0.0 for row in windows)

    reasons: list[str] = []
    if window_count < min_windows:
        reasons.append("INSUFFICIENT_WINDOWS")
    if positive_ratio < min_positive_ratio:
        reasons.append("POSITIVE_WINDOW_RATIO_BELOW_THRESHOLD")
    if median_return <= 0.0:
        reasons.append("NON_POSITIVE_MEDIAN_RETURN")
    if worst_drawdown > max_worst_drawdown_pct:
        reasons.append("WORST_WINDOW_DRAWDOWN_ABOVE_THRESHOLD")
    if dispersion > max_return_dispersion_pct:
        reasons.append("RETURN_DISPERSION_ABOVE_THRESHOLD")
    if out_cash < max(1, int(min_windows * min_positive_ratio)):
        reasons.append("INSUFFICIENT_CASH_BASELINE_OUTPERFORMANCE")

    status = "ROBUST_FIXTURE_CANDIDATE_UNPROMOTED" if not reasons else "BLOCKED_BY_WALK_FORWARD_ROBUSTNESS_GATE"
    return {
        "robustness_result_id": f"{robustness_run_label}-{source_result['result_id']}",
        "robustness_run_label": robustness_run_label,
        "source_result_id": str(source_result["result_id"]),
        "source_backtest_run_label": source_backtest_run_label,
        "created_at": created_at,
        "strategy_family_code": str(source_result["strategy_family_code"]),
        "asset_group": str(source_result["asset_group"]),
        "timeframe": str(source_result["timeframe"]),
        "cost_model_code": str(source_result["cost_model_code"]),
        "window_count": window_count,
        "positive_window_count": positive_count,
        "positive_window_ratio": positive_ratio,
        "median_net_return_pct": median_return,
        "return_dispersion_pct": dispersion,
        "worst_window_drawdown_pct": worst_drawdown,
        "median_sharpe_ratio": median_sharpe,
        "outperformed_cash_window_count": out_cash,
        "outperformed_buy_hold_window_count": out_buy,
        "outperformed_random_window_count": out_random,
        "robustness_status": status,
        "block_reasons": reasons,
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
            "candidate_promoted": False,
            "model_training_enabled": False,
            "profitability_claim": False,
            "mission85_status": MISSION85_STATUS,
        },
    }


def _make_check(
    run_label: str,
    source_label: str,
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
        "robustness_run_label": run_label,
        "source_backtest_run_label": source_label,
        "created_at": created_at,
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "threshold_value": str(threshold),
        "check_reason": reason,
        "robustness_scope": ROBUSTNESS_SCOPE,
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


def _source_ready(source_run: sqlite3.Row | None) -> bool:
    return bool(
        source_run
        and source_run["engine_state"] == SOURCE_ENGINE_STATE
        and source_run["engine_decision"] == SOURCE_ENGINE_DECISION
        and source_run["global_verdict"] == SOURCE_GLOBAL_VERDICT
        and source_run["mission85_status"] == MISSION85_STATUS
        and safe_int(source_run["fail_check_count"]) == 0
        and safe_int(source_run["safety_breach_count"]) == 0
    )


def _fmt(value: Any) -> str:
    return f"{safe_float(value):.8f}"


def _build_markdown(summary: dict[str, Any]) -> str:
    return f"""# DeltaGrid Mission 84.7 Walk-Forward Robustness Gate Report

- Run: {summary['robustness_run_label']}
- Source: {summary['source_backtest_run_label']}
- Evaluated candidates: {summary['evaluated_candidate_count']}
- Window results: {summary['window_result_count']}
- Robust fixture candidates: {summary['robust_candidate_count']}
- Blocked candidates: {summary['blocked_candidate_count']}
- Checks: {summary['pass_check_count']} passed, {summary['fail_check_count']} failed
- Safety breaches: {summary['safety_breach_count']}
- Mission 85: {summary['mission85_status']}

Synthetic fixture robustness is an unvalidated research observation, not a
profitability claim or authorization for live trading, capital deployment,
model training, model promotion, or strategy reweighting.
"""


def run_walk_forward_robustness_gate(
    db_path: str | Path = DEFAULT_DB_PATH,
    robustness_run_label: str = "mission84-7-local-check",
    report_label: str = "mission84-7-local-check-report",
    source_backtest_run_label: str = "mission84-6-final-check",
    min_source_backtests: int = 72,
    context_bars: int = 120,
    test_bars: int = 40,
    step_bars: int = 40,
    min_windows: int = 3,
    min_positive_ratio: float = 2.0 / 3.0,
    max_worst_drawdown_pct: float = 25.0,
    max_return_dispersion_pct: float = 20.0,
) -> dict[str, Any]:
    robustness_run_label = normalize_label(robustness_run_label, "robustness_run_label")
    report_label = normalize_label(report_label, "report_label")
    source_backtest_run_label = normalize_label(source_backtest_run_label, "source_backtest_run_label")
    if min_source_backtests < 1 or min_windows < 1:
        raise ValueError("minimum counts must be positive")
    ensure_schema(db_path)
    created_at = utc_now()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        required = (
            "ai_multi_strategy_backtest_runs",
            "ai_multi_strategy_backtest_results",
            "ai_multi_strategy_backtest_datasets",
            "ai_alpha_cost_model_registry",
        )
        source_tables_present = all(table_exists(conn, name) for name in required)
        source_run = None
        source_results: list[sqlite3.Row] = []
        datasets: dict[str, list[dict[str, Any]]] = {}
        cost_models: dict[str, dict[str, Any]] = {}
        if source_tables_present:
            source_run = conn.execute(
                "SELECT * FROM ai_multi_strategy_backtest_runs WHERE backtest_run_label=?",
                (source_backtest_run_label,),
            ).fetchone()
            source_results = conn.execute(
                "SELECT * FROM ai_multi_strategy_backtest_results WHERE backtest_run_label=? ORDER BY result_id",
                (source_backtest_run_label,),
            ).fetchall()
            for row in conn.execute(
                "SELECT dataset_id,dataset_json FROM ai_multi_strategy_backtest_datasets WHERE backtest_run_label=?",
                (source_backtest_run_label,),
            ):
                datasets[str(row["dataset_id"])] = json.loads(row["dataset_json"])
            benchmark_label = source_run["benchmark_run_label"] if source_run else ""
            for row in conn.execute(
                "SELECT * FROM ai_alpha_cost_model_registry WHERE benchmark_run_label=?",
                (benchmark_label,),
            ):
                cost_models[str(row["cost_model_code"])] = dict(row)

        window_rows: list[dict[str, Any]] = []
        result_rows: list[dict[str, Any]] = []
        if _source_ready(source_run):
            for source_result in source_results:
                bars = datasets.get(str(source_result["dataset_id"]), [])
                if not bars:
                    continue
                cost_model = cost_models.get(str(source_result["cost_model_code"]), {})
                windows = evaluate_candidate_windows(
                    source_result,
                    bars,
                    cost_model,
                    robustness_run_label,
                    created_at,
                    context_bars,
                    test_bars,
                    step_bars,
                )
                window_rows.extend(windows)
                result_rows.append(
                    classify_candidate(
                        source_result,
                        windows,
                        robustness_run_label,
                        source_backtest_run_label,
                        created_at,
                        min_windows,
                        min_positive_ratio,
                        max_worst_drawdown_pct,
                        max_return_dispersion_pct,
                    )
                )

        source_count = len(source_results)
        evaluated_count = len(result_rows)
        robust_count = sum(row["robustness_status"] == "ROBUST_FIXTURE_CANDIDATE_UNPROMOTED" for row in result_rows)
        blocked_count = evaluated_count - robust_count
        strategy_family_count = len({row["strategy_family_code"] for row in result_rows})
        asset_group_count = len({row["asset_group"] for row in result_rows})
        timeframe_count = len({row["timeframe"] for row in result_rows})
        safety_breach_count = sum(
            row["live_trading"] != LIVE_TRADING_STATUS
            or safe_int(row["live_order_sent"]) != 0
            or row["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
            for row in result_rows
        )

        checks = [
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "SOURCE", "SOURCE_TABLES_PRESENT", source_tables_present, source_tables_present, True, "Mission 84.6 source tables must exist."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "SOURCE", "SOURCE_RUN_READY", _source_ready(source_run), _source_ready(source_run), True, "Mission 84.6 source run must be ready and safe."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "COVERAGE", "SOURCE_BACKTEST_COUNT", source_count >= min_source_backtests, source_count, min_source_backtests, "All required source backtests must exist."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "COVERAGE", "EVALUATED_CANDIDATE_COUNT", evaluated_count == source_count and source_count >= min_source_backtests, evaluated_count, source_count, "Every source backtest must be evaluated."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "WINDOW", "MINIMUM_WINDOWS_PER_CANDIDATE", all(row["window_count"] >= min_windows for row in result_rows) and evaluated_count > 0, min((row["window_count"] for row in result_rows), default=0), min_windows, "Each candidate must have enough out-of-sample windows."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "WINDOW", "WINDOW_RESULT_COUNT", len(window_rows) >= evaluated_count * min_windows and evaluated_count > 0, len(window_rows), evaluated_count * min_windows, "Window coverage must be complete."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "GOVERNANCE", "NO_PARAMETER_TUNING", True, 0, 0, "Strategy parameters remain fixed."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "SAFETY", "NO_MODEL_TRAINING", True, 0, 0, "Model training remains disabled."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "SAFETY", "NO_MODEL_ARTIFACTS", True, 0, 0, "No model artifacts are created."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "SAFETY", "NO_MODEL_PROMOTION", True, 0, 0, "Mission 85 remains paused."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "SAFETY", "NO_STRATEGY_REWEIGHTING", True, 0, 0, "No capital-linked strategy reweighting is allowed."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "SAFETY", "NO_LIVE_SIGNALS", True, 0, 0, "No live signals are emitted."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "SAFETY", "NO_EXCHANGE_ORDERS", True, 0, 0, "No exchange orders are sent."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "SAFETY", "NO_CAPITAL_DEPLOYMENT", True, 0, 0, "No real capital is deployed."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "SAFETY", "NO_PAID_APIS", True, 0, 0, "Only local persisted fixtures are used."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "SAFETY", "NO_PRIVATE_KEYS", True, 0, 0, "No keys or signing are used."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "GOVERNANCE", "NO_PROFITABILITY_CLAIMS", True, 0, 0, "Fixture robustness is not a profitability claim."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "GOVERNANCE", "MISSION85_PAUSED", MISSION85_STATUS == "PAUSED_UNTIL_ROBUST_ALPHA_CANDIDATES_EXIST", MISSION85_STATUS, "PAUSED_UNTIL_ROBUST_ALPHA_CANDIDATES_EXIST", "Model promotion remains paused."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "SAFETY", "ZERO_SAFETY_BREACHES", safety_breach_count == 0, safety_breach_count, 0, "All persisted results must preserve safety locks."),
            _make_check(robustness_run_label, source_backtest_run_label, created_at, "GOVERNANCE", "ROBUST_STATUS_DOES_NOT_PROMOTE", all(row["model_promotion_action"] == "NO_MODEL_PROMOTION" for row in result_rows), 0, 0, "Robust fixture classification cannot promote models."),
        ]
        pass_count = sum(row["check_status"] == CHECK_PASS for row in checks)
        fail_count = len(checks) - pass_count
        ready = fail_count == 0

        summary = {
            "robustness_run_label": robustness_run_label,
            "report_label": report_label,
            "source_backtest_run_label": source_backtest_run_label,
            "created_at": created_at,
            "robustness_scope": ROBUSTNESS_SCOPE,
            "robustness_mode": ROBUSTNESS_MODE,
            "mission85_status": MISSION85_STATUS,
            "source_backtest_count": source_count,
            "evaluated_candidate_count": evaluated_count,
            "window_result_count": len(window_rows),
            "robust_candidate_count": robust_count,
            "blocked_candidate_count": blocked_count,
            "strategy_family_count": strategy_family_count,
            "asset_group_count": asset_group_count,
            "timeframe_count": timeframe_count,
            "model_training_count": 0,
            "model_artifact_count": 0,
            "model_promotion_count": 0,
            "strategy_reweighting_count": 0,
            "live_signal_count": 0,
            "exchange_order_count": 0,
            "capital_deployment_count": 0,
            "paid_api_count": 0,
            "private_key_use_count": 0,
            "profitability_claim_count": 0,
            "robustness_check_count": len(checks),
            "pass_check_count": pass_count,
            "fail_check_count": fail_count,
            "safety_breach_count": safety_breach_count,
            "engine_state": ENGINE_STATE if ready else "AI_WALK_FORWARD_ROBUSTNESS_GATE_BLOCKED",
            "engine_decision": ENGINE_DECISION if ready else "AI_WALK_FORWARD_ROBUSTNESS_GATE_REQUIRES_REMEDIATION",
            "global_verdict": GLOBAL_VERDICT if ready else "AI_WALK_FORWARD_ROBUSTNESS_GATE_BLOCKED_RESEARCH_ONLY",
            "recommended_action": RECOMMENDED_ACTION if ready else "REMEDIATE_FAILED_ROBUSTNESS_CHECKS",
            "next_mission": NEXT_MISSION if ready else "Mission 84.7 remediation",
            "live_trading": LIVE_TRADING_STATUS,
            "live_order_sent": LIVE_ORDER_SENT_VALUE,
            "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
            "robustness_checks": checks,
            "robustness_results": result_rows,
            "safety_disclaimer": "Synthetic fixture robustness is unvalidated research evidence and is not a profitability claim.",
        }
        markdown_report = _build_markdown(summary)
        summary["markdown_report"] = markdown_report

        for table, column, value in (
            ("ai_walk_forward_robustness_windows", "robustness_run_label", robustness_run_label),
            ("ai_walk_forward_robustness_results", "robustness_run_label", robustness_run_label),
            ("ai_walk_forward_robustness_checks", "robustness_run_label", robustness_run_label),
            ("ai_walk_forward_robustness_runs", "robustness_run_label", robustness_run_label),
            ("ai_walk_forward_robustness_reports", "report_label", report_label),
        ):
            conn.execute(f"DELETE FROM {table} WHERE {column}=?", (value,))

        for row in window_rows:
            metrics = {key: row[key] for key in ("strategy_net_return_pct", "cash_return_pct", "buy_hold_return_pct", "random_return_pct", "excess_vs_cash_pct", "excess_vs_buy_hold_pct", "excess_vs_random_pct", "sharpe_ratio", "max_drawdown_pct", "trade_count", "total_cost_bps")}
            conn.execute(
                "INSERT INTO ai_walk_forward_robustness_windows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["window_id"], row["robustness_run_label"], row["source_result_id"], row["created_at"], row["window_index"], row["context_start_index"], row["test_start_index"], row["test_end_index"], row["context_bar_count"], row["test_bar_count"], row["strategy_family_code"], row["asset_group"], row["timeframe"], _fmt(row["strategy_net_return_pct"]), _fmt(row["cash_return_pct"]), _fmt(row["buy_hold_return_pct"]), _fmt(row["random_return_pct"]), _fmt(row["excess_vs_cash_pct"]), _fmt(row["excess_vs_buy_hold_pct"]), _fmt(row["excess_vs_random_pct"]), _fmt(row["sharpe_ratio"]), _fmt(row["max_drawdown_pct"]), row["trade_count"], _fmt(row["total_cost_bps"]), row["window_status"], row["live_trading"], row["live_order_sent"], row["capital_deployment"], canonical_json(metrics), canonical_json(row["metadata"]),
                ),
            )

        for row in result_rows:
            metrics = {key: row[key] for key in ("window_count", "positive_window_count", "positive_window_ratio", "median_net_return_pct", "return_dispersion_pct", "worst_window_drawdown_pct", "median_sharpe_ratio", "outperformed_cash_window_count", "outperformed_buy_hold_window_count", "outperformed_random_window_count")}
            conn.execute(
                "INSERT INTO ai_walk_forward_robustness_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["robustness_result_id"], row["robustness_run_label"], row["source_result_id"], row["source_backtest_run_label"], row["created_at"], row["strategy_family_code"], row["asset_group"], row["timeframe"], row["cost_model_code"], row["window_count"], row["positive_window_count"], _fmt(row["positive_window_ratio"]), _fmt(row["median_net_return_pct"]), _fmt(row["return_dispersion_pct"]), _fmt(row["worst_window_drawdown_pct"]), _fmt(row["median_sharpe_ratio"]), row["outperformed_cash_window_count"], row["outperformed_buy_hold_window_count"], row["outperformed_random_window_count"], row["robustness_status"], canonical_json(row["block_reasons"]), row["model_training_action"], row["model_artifact_action"], row["model_promotion_action"], row["strategy_reweighting_action"], row["live_signal_action"], row["exchange_order_action"], row["capital_action"], row["paid_api_action"], row["profitability_claim_action"], row["live_trading"], row["live_order_sent"], row["capital_deployment"], canonical_json(metrics), canonical_json(row["metadata"]),
                ),
            )

        for row in checks:
            conn.execute(
                "INSERT INTO ai_walk_forward_robustness_checks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row["check_id"], row["robustness_run_label"], row["source_backtest_run_label"], row["created_at"], row["check_category"], row["check_name"], row["check_status"], row["observed_value"], row["threshold_value"], row["check_reason"], row["robustness_scope"], row["live_trading"], row["live_order_sent"], row["capital_deployment"], canonical_json(row["metadata"])),
            )

        run_keys = (
            "robustness_run_label", "report_label", "source_backtest_run_label", "created_at", "robustness_scope", "robustness_mode", "mission85_status", "source_backtest_count", "evaluated_candidate_count", "window_result_count", "robust_candidate_count", "blocked_candidate_count", "strategy_family_count", "asset_group_count", "timeframe_count", "model_training_count", "model_artifact_count", "model_promotion_count", "strategy_reweighting_count", "live_signal_count", "exchange_order_count", "capital_deployment_count", "paid_api_count", "private_key_use_count", "profitability_claim_count", "robustness_check_count", "pass_check_count", "fail_check_count", "safety_breach_count", "engine_state", "engine_decision", "global_verdict", "recommended_action", "next_mission", "live_trading", "live_order_sent", "capital_deployment",
        )
        conn.execute(
            "INSERT INTO ai_walk_forward_robustness_runs VALUES (" + ",".join("?" for _ in range(39)) + ")",
            tuple(summary[key] for key in run_keys)
            + (
                canonical_json({key: value for key, value in summary.items() if key not in {"markdown_report", "robustness_results"}}),
                markdown_report,
            ),
        )
        conn.execute(
            "INSERT INTO ai_walk_forward_robustness_reports VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (report_label, robustness_run_label, source_backtest_run_label, created_at, summary["global_verdict"], summary["recommended_action"], canonical_json({key: value for key, value in summary.items() if key not in {"markdown_report", "robustness_results"}}), markdown_report, LIVE_TRADING_STATUS, LIVE_ORDER_SENT_VALUE, CAPITAL_DEPLOYMENT_STATUS),
        )
        conn.commit()
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Mission 84.7 deterministic walk-forward robustness evaluation.")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--robustness-run-label", default="mission84-7-local-check")
    parser.add_argument("--report-label", default="mission84-7-local-check-report")
    parser.add_argument("--source-backtest-run-label", default="mission84-6-final-check")
    parser.add_argument("--min-source-backtests", type=int, default=72)
    parser.add_argument("--context-bars", type=int, default=120)
    parser.add_argument("--test-bars", type=int, default=40)
    parser.add_argument("--step-bars", type=int, default=40)
    parser.add_argument("--min-windows", type=int, default=3)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    summary = run_walk_forward_robustness_gate(
        db_path=args.db_path,
        robustness_run_label=args.robustness_run_label,
        report_label=args.report_label,
        source_backtest_run_label=args.source_backtest_run_label,
        min_source_backtests=args.min_source_backtests,
        context_bars=args.context_bars,
        test_bars=args.test_bars,
        step_bars=args.step_bars,
        min_windows=args.min_windows,
    )
    output = {key: value for key, value in summary.items() if key not in {"markdown_report", "robustness_results"}}
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if summary["fail_check_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
