import json
import sqlite3

import pytest

from offchain.ai_dataset.multi_strategy_backtest_pack import (
    BASELINE_NAMES,
    MISSION85_STATUS,
    SOURCE_ENGINE_DECISION,
    SOURCE_ENGINE_STATE,
    SOURCE_GLOBAL_VERDICT,
    SUPPORTED_FAMILIES,
    backtest_series,
    build_fixture_dataset,
    normalize_label,
    run_multi_strategy_backtest_pack,
    strategy_signals,
)


def seed_source(db_path, run_label="mission84-5-test", families=SUPPORTED_FAMILIES):
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE ai_institutional_alpha_benchmark_runs (
                benchmark_run_label TEXT PRIMARY KEY,
                engine_state TEXT,
                engine_decision TEXT,
                global_verdict TEXT,
                mission85_status TEXT,
                actual_backtest_count INTEGER,
                fail_check_count INTEGER,
                safety_breach_count INTEGER,
                leakage_breach_count INTEGER
            );
            CREATE TABLE ai_alpha_benchmark_plan_entries (
                benchmark_plan_id TEXT PRIMARY KEY,
                benchmark_run_label TEXT,
                strategy_family_code TEXT,
                asset_group TEXT,
                timeframe TEXT,
                cost_model_code TEXT
            );
            CREATE TABLE ai_alpha_asset_universe_registry (
                asset_id TEXT PRIMARY KEY,
                benchmark_run_label TEXT,
                asset_group TEXT,
                symbol TEXT
            );
            CREATE TABLE ai_alpha_cost_model_registry (
                cost_model_code TEXT PRIMARY KEY,
                benchmark_run_label TEXT,
                asset_group TEXT,
                commission_bps TEXT,
                slippage_bps TEXT,
                spread_bps TEXT,
                funding_bps TEXT,
                borrow_bps TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO ai_institutional_alpha_benchmark_runs VALUES (?,?,?,?,?,?,?,?,?)",
            (
                run_label,
                SOURCE_ENGINE_STATE,
                SOURCE_ENGINE_DECISION,
                SOURCE_GLOBAL_VERDICT,
                MISSION85_STATUS,
                0,
                0,
                0,
                0,
            ),
        )
        assets = {
            "CRYPTO": ("BTC", "ETH"),
            "FX": ("AUDUSD", "EURUSD"),
            "ETF_MACRO": ("SPY", "QQQ"),
        }
        for group, symbols in assets.items():
            for symbol in symbols:
                conn.execute(
                    "INSERT INTO ai_alpha_asset_universe_registry VALUES (?,?,?,?)",
                    (f"{group}-{symbol}", run_label, group, symbol),
                )
            conn.execute(
                "INSERT INTO ai_alpha_cost_model_registry VALUES (?,?,?,?,?,?,?,?)",
                (f"{group}_COST", run_label, group, "1.0", "1.5", "0.5", "2.0", "1.0"),
            )
        index = 0
        for family in families:
            for group in assets:
                for timeframe in ("1D", "4H", "1H"):
                    index += 1
                    conn.execute(
                        "INSERT INTO ai_alpha_benchmark_plan_entries VALUES (?,?,?,?,?,?)",
                        (f"plan-{index}", run_label, family, group, timeframe, f"{group}_COST"),
                    )
        conn.commit()
    return index


def fixture():
    return build_fixture_dataset("CRYPTO", "BTC", "ETH", "1D", 180, "test-seed")


def cost_model():
    return {
        "commission_bps": "1",
        "slippage_bps": "1",
        "spread_bps": "1",
        "funding_bps": "2",
        "borrow_bps": "1",
    }


def test_normalize_label_rejects_whitespace():
    with pytest.raises(ValueError):
        normalize_label("bad label", "run_label")


def test_fixture_generation_is_deterministic():
    first = fixture()
    second = fixture()
    assert first == second
    assert len(first) == 180


def test_fixture_ohlcv_invariants_hold():
    for row in fixture():
        assert row["high"] >= max(row["open"], row["close"])
        assert row["low"] <= min(row["open"], row["close"])
        assert row["low"] > 0
        assert row["volume"] > 0


def test_all_strategy_families_emit_bounded_signals():
    bars = fixture()
    for family in SUPPORTED_FAMILIES:
        signals = strategy_signals(family, bars)
        assert len(signals) == len(bars)
        assert set(signals).issubset({-1.0, 0.0, 1.0})


def test_strategy_signals_are_prefix_stable_without_future_data():
    bars = fixture()
    for family in SUPPORTED_FAMILIES:
        full = strategy_signals(family, bars)
        prefix = strategy_signals(family, bars[:140])
        assert full[:140] == prefix


def test_transaction_costs_do_not_improve_net_return():
    bars = fixture()
    signals = strategy_signals("TIME_SERIES_MOMENTUM", bars)
    result = backtest_series(bars, signals, cost_model(), "1D")
    assert result["net_return_pct"] <= result["gross_return_pct"] + 1e-10
    assert result["total_cost_bps"] >= 0


def test_pack_runs_all_plans_and_three_baselines(tmp_path):
    db_path = tmp_path / "mission84-6.db"
    plan_count = seed_source(db_path)
    result = run_multi_strategy_backtest_pack(
        db_path=db_path,
        backtest_run_label="mission84-6-test",
        report_label="mission84-6-test-report",
        benchmark_run_label="mission84-5-test",
        min_plan_entries=plan_count,
        bars=140,
    )
    assert result["actual_backtest_count"] == plan_count
    assert result["baseline_result_count"] == plan_count * len(BASELINE_NAMES)
    assert result["fixture_dataset_count"] == 9
    assert result["fail_check_count"] == 0


def test_pack_persists_required_tables(tmp_path):
    db_path = tmp_path / "mission84-6-persist.db"
    plan_count = seed_source(db_path)
    result = run_multi_strategy_backtest_pack(
        db_path=db_path,
        backtest_run_label="mission84-6-persist",
        report_label="mission84-6-persist-report",
        benchmark_run_label="mission84-5-test",
        min_plan_entries=plan_count,
        bars=140,
    )
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ai_multi_strategy_backtest_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ai_multi_strategy_backtest_datasets").fetchone()[0] == 9
        assert conn.execute("SELECT COUNT(*) FROM ai_multi_strategy_backtest_results").fetchone()[0] == plan_count
        assert conn.execute("SELECT COUNT(*) FROM ai_multi_strategy_backtest_baselines").fetchone()[0] == plan_count * 3
        assert conn.execute("SELECT COUNT(*) FROM ai_multi_strategy_backtest_checks").fetchone()[0] == result["backtest_check_count"]
        assert conn.execute("SELECT COUNT(*) FROM ai_multi_strategy_backtest_reports").fetchone()[0] == 1


def test_pack_is_idempotent_for_same_labels(tmp_path):
    db_path = tmp_path / "mission84-6-idempotent.db"
    plan_count = seed_source(db_path)
    kwargs = dict(
        db_path=db_path,
        backtest_run_label="mission84-6-idempotent",
        report_label="mission84-6-idempotent-report",
        benchmark_run_label="mission84-5-test",
        min_plan_entries=plan_count,
        bars=140,
    )
    run_multi_strategy_backtest_pack(**kwargs)
    run_multi_strategy_backtest_pack(**kwargs)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ai_multi_strategy_backtest_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ai_multi_strategy_backtest_results").fetchone()[0] == plan_count
        assert conn.execute("SELECT COUNT(*) FROM ai_multi_strategy_backtest_baselines").fetchone()[0] == plan_count * 3


def test_safety_locks_and_mission85_pause_are_preserved(tmp_path):
    db_path = tmp_path / "mission84-6-safety.db"
    plan_count = seed_source(db_path)
    result = run_multi_strategy_backtest_pack(
        db_path=db_path,
        backtest_run_label="mission84-6-safety",
        report_label="mission84-6-safety-report",
        benchmark_run_label="mission84-5-test",
        min_plan_entries=plan_count,
        bars=140,
    )
    assert result["mission85_status"] == MISSION85_STATUS
    assert result["model_training_count"] == 0
    assert result["model_artifact_count"] == 0
    assert result["model_promotion_count"] == 0
    assert result["strategy_reweighting_count"] == 0
    assert result["live_signal_count"] == 0
    assert result["exchange_order_count"] == 0
    assert result["capital_deployment_count"] == 0
    assert result["paid_api_count"] == 0
    assert result["private_key_use_count"] == 0
    assert result["profitability_claim_count"] == 0
    assert result["safety_breach_count"] == 0


def test_report_explicitly_disclaims_profitability(tmp_path):
    db_path = tmp_path / "mission84-6-report.db"
    plan_count = seed_source(db_path)
    result = run_multi_strategy_backtest_pack(
        db_path=db_path,
        backtest_run_label="mission84-6-report",
        report_label="mission84-6-report-label",
        benchmark_run_label="mission84-5-test",
        min_plan_entries=plan_count,
        bars=140,
    )
    assert "not profitability claims" in result["markdown_report"]
    assert "Mission 84.7 Walk-Forward Robustness Gate" in result["markdown_report"]


def test_persisted_metadata_marks_fixture_results_unvalidated(tmp_path):
    db_path = tmp_path / "mission84-6-metadata.db"
    plan_count = seed_source(db_path)
    run_multi_strategy_backtest_pack(
        db_path=db_path,
        backtest_run_label="mission84-6-metadata",
        report_label="mission84-6-metadata-report",
        benchmark_run_label="mission84-5-test",
        min_plan_entries=plan_count,
        bars=140,
    )
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT research_status, metadata_json FROM ai_multi_strategy_backtest_results LIMIT 1"
        ).fetchone()
    assert row[0] == "SYNTHETIC_FIXTURE_RESULT_RECORDED_UNVALIDATED_NOT_PROMOTED"
    metadata = json.loads(row[1])
    assert metadata["not_profitability_claim"] is True
    assert metadata["signals_shifted_one_bar"] is True
