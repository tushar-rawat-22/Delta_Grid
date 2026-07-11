import json
import sqlite3
from pathlib import Path

import pytest

from offchain.ai_dataset.multi_strategy_backtest_pack import (
    build_fixture_dataset,
    ensure_schema as ensure_backtest_schema,
)
from offchain.ai_dataset.walk_forward_robustness_gate import (
    CAPITAL_DEPLOYMENT_STATUS,
    ENGINE_STATE,
    LIVE_TRADING_STATUS,
    MISSION85_STATUS,
    build_parser,
    build_walk_forward_windows,
    classify_candidate,
    ensure_schema,
    evaluate_candidate_windows,
    main,
    run_walk_forward_robustness_gate,
)


def insert_complete(conn: sqlite3.Connection, table: str, values: dict) -> None:
    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
    names = [row[1] for row in columns]
    payload = []
    for row in columns:
        name, declared_type = row[1], str(row[2]).upper()
        if name in values:
            payload.append(values[name])
        elif "INT" in declared_type:
            payload.append(0)
        else:
            payload.append("")
    conn.execute(
        f"INSERT INTO {table} ({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
        payload,
    )


def seed_source(db_path: Path, count: int = 1) -> None:
    ensure_backtest_schema(db_path)
    bars = build_fixture_dataset("CRYPTO", "BTC", "ETH", "1D", 260, "seed")
    with sqlite3.connect(db_path) as conn:
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
            "INSERT INTO ai_alpha_cost_model_registry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "CRYPTO_PAPER_CONSERVATIVE",
                "mission84-5-final-check",
                "2026-07-11T00:00:00+00:00",
                "CRYPTO",
                "2.0",
                "3.0",
                "1.0",
                "2.0",
                "1.0",
                "fixture",
                "LOCAL_ONLY",
                "DISABLED",
                "BLOCKED",
                "{}",
            ),
        )
        insert_complete(
            conn,
            "ai_multi_strategy_backtest_runs",
            {
                "backtest_run_label": "mission84-6-final-check",
                "report_label": "mission84-6-final-check-report",
                "benchmark_run_label": "mission84-5-final-check",
                "created_at": "2026-07-11T00:00:00+00:00",
                "backtest_scope": "MULTI_STRATEGY_BACKTEST_PACK_LOCAL_FIXTURE_ONLY",
                "backtest_mode": "LOCAL_OFFCHAIN_PAPER_BACKTEST_FIXTURE_ONLY",
                "mission85_status": MISSION85_STATUS,
                "actual_backtest_count": count,
                "fail_check_count": 0,
                "safety_breach_count": 0,
                "engine_state": "AI_MULTI_STRATEGY_BACKTEST_PACK_READY_LOCAL_ONLY",
                "engine_decision": "AI_MULTI_STRATEGY_BACKTEST_PACK_APPROVED_FOR_WALK_FORWARD_ROBUSTNESS_GATE",
                "global_verdict": "AI_MULTI_STRATEGY_BACKTEST_PACK_READY_SHADOW_RESEARCH_ONLY",
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": 0,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "summary_json": "{}",
                "markdown_report": "source",
            },
        )
        insert_complete(
            conn,
            "ai_multi_strategy_backtest_datasets",
            {
                "dataset_id": "dataset-1",
                "backtest_run_label": "mission84-6-final-check",
                "benchmark_run_label": "mission84-5-final-check",
                "created_at": "2026-07-11T00:00:00+00:00",
                "asset_group": "CRYPTO",
                "symbol": "BTC",
                "companion_symbol": "ETH",
                "timeframe": "1D",
                "data_source": "DETERMINISTIC_SYNTHETIC_OHLCV_FIXTURE_LOCAL_ONLY",
                "bar_count": 260,
                "first_timestamp": bars[0]["timestamp"],
                "last_timestamp": bars[-1]["timestamp"],
                "fixture_hash": "fixture-hash",
                "dataset_json": json.dumps(bars),
                "live_trading": LIVE_TRADING_STATUS,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata_json": "{}",
            },
        )
        for index in range(count):
            insert_complete(
                conn,
                "ai_multi_strategy_backtest_results",
                {
                    "result_id": f"source-result-{index}",
                    "backtest_run_label": "mission84-6-final-check",
                    "benchmark_run_label": "mission84-5-final-check",
                    "benchmark_plan_id": f"plan-{index}",
                    "dataset_id": "dataset-1",
                    "created_at": "2026-07-11T00:00:00+00:00",
                    "strategy_family_code": "TIME_SERIES_MOMENTUM",
                    "asset_group": "CRYPTO",
                    "symbol": "BTC",
                    "companion_symbol": "ETH",
                    "timeframe": "1D",
                    "cost_model_code": "CRYPTO_PAPER_CONSERVATIVE",
                    "bar_count": 260,
                    "research_status": "SYNTHETIC_FIXTURE_RESULT_RECORDED_UNVALIDATED_NOT_PROMOTED",
                    "result_scope": "MULTI_STRATEGY_BACKTEST_PACK_LOCAL_FIXTURE_ONLY",
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
                    "live_order_sent": 0,
                    "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                    "metrics_json": "{}",
                    "metadata_json": "{}",
                },
            )
        conn.commit()


def source_result() -> dict:
    return {
        "result_id": "result-1",
        "strategy_family_code": "TIME_SERIES_MOMENTUM",
        "asset_group": "CRYPTO",
        "timeframe": "1D",
        "cost_model_code": "CRYPTO_PAPER_CONSERVATIVE",
    }


def test_build_walk_forward_windows_has_three_default_windows():
    windows = build_walk_forward_windows(260)
    assert len(windows) == 3
    assert windows[0]["test_start_index"] == 120
    assert windows[-1]["test_end_index"] == 240


def test_build_walk_forward_windows_validates_inputs():
    with pytest.raises(ValueError):
        build_walk_forward_windows(260, context_bars=19)
    with pytest.raises(ValueError):
        build_walk_forward_windows(260, test_bars=1)


def test_evaluate_candidate_windows_is_deterministic():
    bars = build_fixture_dataset("CRYPTO", "BTC", "ETH", "1D", 260, "same")
    cost = {"commission_bps": 2, "slippage_bps": 3, "spread_bps": 1, "funding_bps": 2, "borrow_bps": 1}
    first = evaluate_candidate_windows(source_result(), bars, cost, "run", "now")
    second = evaluate_candidate_windows(source_result(), bars, cost, "run", "now")
    assert first == second
    assert len(first) == 3


def test_evaluate_candidate_windows_preserves_safety():
    bars = build_fixture_dataset("CRYPTO", "BTC", "ETH", "1D", 260, "safe")
    rows = evaluate_candidate_windows(source_result(), bars, {}, "run", "now")
    assert all(row["live_trading"] == "DISABLED" for row in rows)
    assert all(row["live_order_sent"] == 0 for row in rows)
    assert all(row["capital_deployment"] == "BLOCKED" for row in rows)


def test_classify_candidate_accepts_stable_positive_fixture_windows():
    windows = [
        {"strategy_net_return_pct": 1.0, "sharpe_ratio": 1.0, "max_drawdown_pct": 2.0, "excess_vs_cash_pct": 1.0, "excess_vs_buy_hold_pct": 0.2, "excess_vs_random_pct": 0.5},
        {"strategy_net_return_pct": 1.2, "sharpe_ratio": 1.1, "max_drawdown_pct": 3.0, "excess_vs_cash_pct": 1.2, "excess_vs_buy_hold_pct": -0.1, "excess_vs_random_pct": 0.3},
        {"strategy_net_return_pct": 0.8, "sharpe_ratio": 0.9, "max_drawdown_pct": 2.5, "excess_vs_cash_pct": 0.8, "excess_vs_buy_hold_pct": 0.1, "excess_vs_random_pct": 0.4},
    ]
    result = classify_candidate(source_result(), windows, "run", "source", "now")
    assert result["robustness_status"] == "ROBUST_FIXTURE_CANDIDATE_UNPROMOTED"
    assert result["model_promotion_action"] == "NO_MODEL_PROMOTION"


def test_classify_candidate_blocks_unstable_windows():
    windows = [
        {"strategy_net_return_pct": -1.0, "sharpe_ratio": -1.0, "max_drawdown_pct": 30.0, "excess_vs_cash_pct": -1.0, "excess_vs_buy_hold_pct": -2.0, "excess_vs_random_pct": -1.0},
        {"strategy_net_return_pct": 0.1, "sharpe_ratio": 0.1, "max_drawdown_pct": 5.0, "excess_vs_cash_pct": 0.1, "excess_vs_buy_hold_pct": -1.0, "excess_vs_random_pct": -0.2},
    ]
    result = classify_candidate(source_result(), windows, "run", "source", "now")
    assert result["robustness_status"] == "BLOCKED_BY_WALK_FORWARD_ROBUSTNESS_GATE"
    assert "INSUFFICIENT_WINDOWS" in result["block_reasons"]


def test_ensure_schema_creates_all_mission_tables(tmp_path):
    db = tmp_path / "gate.db"
    ensure_schema(db)
    with sqlite3.connect(db) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "ai_walk_forward_robustness_runs",
        "ai_walk_forward_robustness_windows",
        "ai_walk_forward_robustness_results",
        "ai_walk_forward_robustness_checks",
        "ai_walk_forward_robustness_reports",
    } <= tables


def test_missing_source_fails_closed(tmp_path):
    summary = run_walk_forward_robustness_gate(db_path=tmp_path / "missing.db", min_source_backtests=1)
    assert summary["fail_check_count"] > 0
    assert summary["evaluated_candidate_count"] == 0
    assert summary["next_mission"] == "Mission 84.7 remediation"


def test_full_gate_evaluates_and_persists_source_candidate(tmp_path):
    db = tmp_path / "full.db"
    seed_source(db)
    summary = run_walk_forward_robustness_gate(db_path=db, min_source_backtests=1)
    assert summary["source_backtest_count"] == 1
    assert summary["evaluated_candidate_count"] == 1
    assert summary["window_result_count"] == 3
    assert summary["fail_check_count"] == 0
    assert summary["engine_state"] == ENGINE_STATE
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ai_walk_forward_robustness_results").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ai_walk_forward_robustness_windows").fetchone()[0] == 3


def test_full_gate_is_idempotent_for_same_labels(tmp_path):
    db = tmp_path / "repeat.db"
    seed_source(db)
    kwargs = dict(db_path=db, min_source_backtests=1, robustness_run_label="repeat", report_label="repeat-report")
    run_walk_forward_robustness_gate(**kwargs)
    run_walk_forward_robustness_gate(**kwargs)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ai_walk_forward_robustness_runs WHERE robustness_run_label='repeat'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ai_walk_forward_robustness_windows WHERE robustness_run_label='repeat'").fetchone()[0] == 3


def test_summary_keeps_all_prohibited_action_counts_zero(tmp_path):
    db = tmp_path / "safe.db"
    seed_source(db)
    summary = run_walk_forward_robustness_gate(db_path=db, min_source_backtests=1)
    for key in (
        "model_training_count",
        "model_artifact_count",
        "model_promotion_count",
        "strategy_reweighting_count",
        "live_signal_count",
        "exchange_order_count",
        "capital_deployment_count",
        "paid_api_count",
        "private_key_use_count",
        "profitability_claim_count",
        "safety_breach_count",
    ):
        assert summary[key] == 0
    assert summary["mission85_status"] == MISSION85_STATUS


def test_parser_and_main_support_final_cli(tmp_path, capsys):
    db = tmp_path / "cli.db"
    seed_source(db)
    parser = build_parser()
    args = parser.parse_args(["--min-source-backtests", "1"])
    assert args.min_source_backtests == 1
    exit_code = main([
        "--db-path", str(db),
        "--robustness-run-label", "cli-run",
        "--report-label", "cli-report",
        "--min-source-backtests", "1",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["evaluated_candidate_count"] == 1
    assert payload["fail_check_count"] == 0
