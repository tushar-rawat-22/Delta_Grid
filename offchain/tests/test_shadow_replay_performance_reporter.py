import sqlite3

from offchain.backtest.shadow_candidate_replay_harness import run_shadow_candidate_replay
from offchain.backtest.shadow_replay_performance_reporter import (
    APPROVED_REPLAY_VERDICT,
    NO_REPLAY_HISTORY_VERDICT,
    generate_shadow_replay_performance_report,
)


def test_missing_database_returns_no_replay_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = generate_shadow_replay_performance_report(
        db_path=db_path,
        report_label="mission36-missing-db",
    )

    assert result["database_exists"] is False
    assert result["replay_count"] == 0
    assert result["scenario_count"] == 0
    assert result["global_verdict"] == NO_REPLAY_HISTORY_VERDICT
    assert result["live_trading_breach_count"] == 0


def test_performance_report_summarizes_shadow_replay(tmp_path):
    db_path = tmp_path / "mission36.db"

    run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission36-replay",
        scenario_names=["all"],
    )

    result = generate_shadow_replay_performance_report(
        db_path=db_path,
        report_label="mission36-report",
        replay_label="mission36-replay",
    )

    assert result["report_label"] == "mission36-report"
    assert result["source_replay_label"] == "mission36-replay"
    assert result["replay_count"] == 1
    assert result["scenario_count"] == 4
    assert result["pipeline_run_count"] == 4
    assert result["total_approved_count"] == 2
    assert result["total_rejected_count"] == 6
    assert result["total_paper_positions_count"] == 2
    assert result["approval_rate"] == 0.25
    assert result["rejection_rate"] == 0.75
    assert result["paper_position_rate"] == 0.5
    assert result["live_trading_breach_count"] == 0
    assert result["global_verdict"] == APPROVED_REPLAY_VERDICT

    assert result["scenario_distribution"] == {
        "approved_shadow_btc": 1,
        "fail_closed_baseline": 1,
        "mixed_shadow_set": 1,
        "non_universe_rejection": 1,
    }

    assert "DeltaGrid Mission 36 Shadow Replay Performance Report" in result["markdown_report"]

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            """
            SELECT
                report_label,
                replay_count,
                scenario_count,
                total_approved_count,
                total_rejected_count,
                total_paper_positions_count,
                global_verdict
            FROM shadow_replay_performance_reports
            WHERE report_label = ?
            """,
            ("mission36-report",),
        ).fetchone()

    assert stored == (
        "mission36-report",
        1,
        4,
        2,
        6,
        2,
        APPROVED_REPLAY_VERDICT,
    )


def test_performance_report_can_aggregate_multiple_replays(tmp_path):
    db_path = tmp_path / "mission36-multiple.db"

    run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission36-replay-a",
        scenario_names=["approved_shadow_btc"],
    )

    run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission36-replay-b",
        scenario_names=["non_universe_rejection"],
    )

    result = generate_shadow_replay_performance_report(
        db_path=db_path,
        report_label="mission36-aggregate-report",
        limit=10,
    )

    assert result["replay_count"] == 2
    assert result["scenario_count"] == 2
    assert result["pipeline_run_count"] == 2
    assert result["total_approved_count"] == 1
    assert result["total_rejected_count"] == 1
    assert result["total_paper_positions_count"] == 1
    assert result["approval_rate"] == 0.5
    assert result["rejection_rate"] == 0.5
    assert result["paper_position_rate"] == 0.5
    assert result["live_trading_breach_count"] == 0
    assert result["global_verdict"] == APPROVED_REPLAY_VERDICT
