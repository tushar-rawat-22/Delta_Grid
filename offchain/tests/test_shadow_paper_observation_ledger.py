import sqlite3

from offchain.backtest.shadow_candidate_replay_harness import run_shadow_candidate_replay
from offchain.backtest.shadow_replay_performance_reporter import generate_shadow_replay_performance_report
from offchain.backtest.shadow_research_decision_gate import (
    run_shadow_research_decision_gate,
)
from offchain.backtest.shadow_paper_observation_ledger import (
    GATE_NOT_APPROVED_VERDICT,
    OBSERVATIONS_OPENED_VERDICT,
    close_shadow_paper_observation,
    generate_shadow_paper_observation_report,
    open_shadow_paper_observations,
)


def prepare_approved_gate(db_path):
    run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission38-replay",
        scenario_names=["all"],
    )

    generate_shadow_replay_performance_report(
        db_path=db_path,
        report_label="mission38-performance",
        replay_label="mission38-replay",
    )

    run_shadow_research_decision_gate(
        db_path=db_path,
        gate_label="mission38-gate",
        report_label="mission38-performance",
    )


def test_missing_database_returns_no_gate_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = open_shadow_paper_observations(
        db_path=db_path,
        ledger_label="mission38-missing",
        gate_label="missing-gate",
    )

    assert result["database_exists"] is False
    assert result["opened_count"] == 0
    assert result["live_trading"] == "DISABLED"
    assert result["capital_deployment"] == "BLOCKED"


def test_open_shadow_observations_from_approved_decision_gate(tmp_path):
    db_path = tmp_path / "mission38.db"
    prepare_approved_gate(db_path)

    result = open_shadow_paper_observations(
        db_path=db_path,
        ledger_label="mission38-ledger",
        gate_label="mission38-gate",
        simulated_notional_usd=1000.0,
    )

    assert result["global_verdict"] == OBSERVATIONS_OPENED_VERDICT
    assert result["opened_count"] == 2
    assert result["eligible_scenario_count"] == 2
    assert result["live_trading"] == "DISABLED"
    assert result["live_order_sent"] is False
    assert result["capital_deployment"] == "BLOCKED"

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                ledger_label,
                status,
                mode,
                symbol,
                simulated_notional_usd,
                source_gate_label,
                source_report_label,
                source_replay_label,
                live_trading,
                live_order_sent,
                capital_deployment
            FROM shadow_paper_observation_ledger
            ORDER BY observation_id ASC
            """
        ).fetchall()

    assert len(rows) == 2

    for row in rows:
        assert row[0] == "mission38-ledger"
        assert row[1] == "OPEN"
        assert row[2] == "SHADOW_PAPER"
        assert row[3] == "BTCUSDT"
        assert row[4] == "1000.0"
        assert row[5] == "mission38-gate"
        assert row[6] == "mission38-performance"
        assert row[7] == "mission38-replay"
        assert row[8] == "DISABLED"
        assert row[9] == 0
        assert row[10] == "BLOCKED"


def test_gate_not_approved_does_not_open_observations(tmp_path):
    db_path = tmp_path / "mission38-small.db"

    run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission38-small-replay",
        scenario_names=["approved_shadow_btc"],
    )

    generate_shadow_replay_performance_report(
        db_path=db_path,
        report_label="mission38-small-performance",
        replay_label="mission38-small-replay",
    )

    run_shadow_research_decision_gate(
        db_path=db_path,
        gate_label="mission38-small-gate",
        report_label="mission38-small-performance",
    )

    result = open_shadow_paper_observations(
        db_path=db_path,
        ledger_label="mission38-small-ledger",
        gate_label="mission38-small-gate",
    )

    assert result["global_verdict"] == GATE_NOT_APPROVED_VERDICT
    assert result["opened_count"] == 0
    assert result["live_order_sent"] is False
    assert result["capital_deployment"] == "BLOCKED"


def test_close_shadow_observation_and_generate_report(tmp_path):
    db_path = tmp_path / "mission38-close.db"
    prepare_approved_gate(db_path)

    open_result = open_shadow_paper_observations(
        db_path=db_path,
        ledger_label="mission38-close-ledger",
        gate_label="mission38-gate",
        simulated_notional_usd=1000.0,
    )

    observation_id = open_result["observation_ids"][0]

    close_result = close_shadow_paper_observation(
        db_path=db_path,
        observation_id=observation_id,
        realized_pnl_usd=2.5,
        realized_funding_bps=4.0,
        fees_bps=1.0,
        slippage_bps=0.5,
        close_reason="test close",
    )

    assert close_result["closed"] is True
    assert close_result["realized_pnl_usd"] == 2.5
    assert close_result["realized_return_bps"] == 25.0

    report = generate_shadow_paper_observation_report(
        db_path=db_path,
        report_label="mission38-report",
        gate_label="mission38-gate",
    )

    assert report["observation_count"] == 2
    assert report["open_count"] == 1
    assert report["closed_count"] == 1
    assert report["total_simulated_notional_usd"] == 2000.0
    assert report["total_realized_pnl_usd"] == 2.5
    assert report["live_trading_breach_count"] == 0
    assert "DeltaGrid Mission 38 Shadow Paper Observation Ledger Report" in report["markdown_report"]
