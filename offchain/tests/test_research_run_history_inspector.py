from offchain.backtest.research_pipeline_runner import (
    DEFAULT_VERDICT,
    LIVE_TRADING_STATUS,
    SHADOW_APPROVED_VERDICT,
    PipelineConfig,
    ResearchPipelineRunner,
)
from offchain.backtest.research_run_history_inspector import (
    NO_HISTORY_VERDICT,
    NO_MATCHING_RUNS_VERDICT,
    SHADOW_APPROVED_HISTORY_VERDICT,
    inspect_research_run_history,
)


def test_missing_database_returns_safe_no_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = inspect_research_run_history(db_path=db_path)

    assert result["database_exists"] is False
    assert result["total_runs"] == 0
    assert result["global_verdict"] == NO_HISTORY_VERDICT
    assert result["safety"]["live_trading_disabled_all"] is True


def test_inspector_reads_shadow_pipeline_history(tmp_path):
    db_path = tmp_path / "history.db"

    runner = ResearchPipelineRunner(
        db_path=db_path,
        config=PipelineConfig(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT")),
    )

    runner.run(run_label="mission34-no-go")

    strong_shadow_candidate = [
        {
            "symbol": "BTCUSDT",
            "funding_rate": 0.001,
            "annualized_funding": 0.42,
            "basis_bps": 12.0,
            "expected_funding_edge_bps": 120.0,
            "total_round_trip_cost_bps": 30.0,
            "spread_bps": 2.0,
            "estimated_slippage_bps": 3.0,
            "stressed_liquidation_buffer": 0.50,
            "liquidity_score": 95.0,
        }
    ]

    runner.run(
        run_label="mission34-approved",
        candidates=strong_shadow_candidate,
    )

    result = inspect_research_run_history(db_path=db_path, limit=10)

    assert result["database_exists"] is True
    assert result["tables_present"] is True
    assert result["total_runs"] == 2
    assert result["verdict_counts"][DEFAULT_VERDICT] == 1
    assert result["verdict_counts"][SHADOW_APPROVED_VERDICT] == 1
    assert result["global_verdict"] == SHADOW_APPROVED_HISTORY_VERDICT
    assert result["safety"]["live_trading_disabled_all"] is True
    assert result["safety"]["live_trading_required_status"] == LIVE_TRADING_STATUS
    assert result["safety"]["breach_count"] == 0

    run_labels = {run["run_label"] for run in result["runs"]}

    assert run_labels == {"mission34-no-go", "mission34-approved"}

    for run in result["runs"]:
        assert run["live_trading"] == "DISABLED"
        assert run["stage_count"] == 7
        assert run["report_length"] is not None
        assert run["report_length"] > 0


def test_inspector_filters_specific_run_label(tmp_path):
    db_path = tmp_path / "filtered-history.db"
    runner = ResearchPipelineRunner(db_path=db_path)

    runner.run(run_label="mission34-filtered-no-go")

    result = inspect_research_run_history(
        db_path=db_path,
        run_label="mission34-filtered-no-go",
    )

    assert result["total_runs"] == 1
    assert result["runs"][0]["run_label"] == "mission34-filtered-no-go"
    assert result["runs"][0]["verdict"] == DEFAULT_VERDICT

    missing = inspect_research_run_history(
        db_path=db_path,
        run_label="does-not-exist",
    )

    assert missing["total_runs"] == 0
    assert missing["global_verdict"] == NO_MATCHING_RUNS_VERDICT
