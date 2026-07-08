import sqlite3

from offchain.backtest.research_pipeline_runner import (
    DEFAULT_VERDICT,
    LIVE_TRADING_STATUS,
    SHADOW_APPROVED_VERDICT,
    PipelineConfig,
    ResearchPipelineRunner,
)


def test_mission33_default_shadow_runner_fails_closed(tmp_path):
    db_path = tmp_path / "mission33.db"
    runner = ResearchPipelineRunner(db_path=db_path)

    result = runner.run(run_label="mission33-default-test")

    assert result["mode"] == "SHADOW_MODE"
    assert result["live_trading"] == LIVE_TRADING_STATUS
    assert result["symbols"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert result["approved_count"] == 0
    assert result["rejected_count"] == 3
    assert result["paper_positions_count"] == 0
    assert result["verdict"] == DEFAULT_VERDICT
    assert any(alert["code"] == "LIVE_TRADING_DISABLED" for alert in result["alerts"])
    assert any(alert["code"] == "NO_SHADOW_APPROVED_CANDIDATES" for alert in result["alerts"])

    with sqlite3.connect(db_path) as conn:
        run_count = conn.execute(
            "SELECT COUNT(*) FROM research_pipeline_runs WHERE run_label = ?",
            ("mission33-default-test",),
        ).fetchone()[0]

        stage_count = conn.execute(
            "SELECT COUNT(*) FROM research_pipeline_stage_results WHERE run_label = ?",
            ("mission33-default-test",),
        ).fetchone()[0]

        report_count = conn.execute(
            "SELECT COUNT(*) FROM research_pipeline_reports WHERE run_label = ?",
            ("mission33-default-test",),
        ).fetchone()[0]

    assert run_count == 1
    assert stage_count == 7
    assert report_count == 1


def test_mission33_can_open_shadow_paper_position_without_live_trading(tmp_path):
    db_path = tmp_path / "mission33-approved.db"
    runner = ResearchPipelineRunner(
        db_path=db_path,
        config=PipelineConfig(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT")),
    )

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

    result = runner.run(
        run_label="mission33-approved-shadow-test",
        candidates=strong_shadow_candidate,
    )

    assert result["mode"] == "SHADOW_MODE"
    assert result["live_trading"] == LIVE_TRADING_STATUS
    assert result["approved_count"] == 1
    assert result["rejected_count"] == 0
    assert result["paper_positions_count"] == 1
    assert result["verdict"] == SHADOW_APPROVED_VERDICT
    assert any(alert["code"] == "LIVE_TRADING_DISABLED" for alert in result["alerts"])

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            """
            SELECT live_trading, verdict, approved_count, paper_positions_count
            FROM research_pipeline_runs
            WHERE run_label = ?
            """,
            ("mission33-approved-shadow-test",),
        ).fetchone()

    assert stored == (
        "DISABLED",
        SHADOW_APPROVED_VERDICT,
        1,
        1,
    )
