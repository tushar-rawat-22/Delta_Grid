import sqlite3
from datetime import datetime, timedelta, timezone

from offchain.backtest.shadow_candidate_replay_harness import run_shadow_candidate_replay
from offchain.backtest.shadow_replay_performance_reporter import generate_shadow_replay_performance_report
from offchain.backtest.shadow_research_decision_gate import run_shadow_research_decision_gate
from offchain.backtest.shadow_paper_observation_ledger import open_shadow_paper_observations
from offchain.backtest.shadow_observation_lifecycle_manager import evaluate_shadow_observation_lifecycle
from offchain.backtest.shadow_observation_pnl_attribution import (
    NEGATIVE_NET_VERDICT,
    NO_LIFECYCLE_HISTORY_VERDICT,
    POSITIVE_NET_VERDICT,
    SAFETY_BREACH_VERDICT,
    run_shadow_observation_pnl_attribution,
)


def prepare_lifecycle_snapshot(db_path, snapshot_label="mission40-snapshot"):
    run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission40-replay",
        scenario_names=["all"],
    )

    generate_shadow_replay_performance_report(
        db_path=db_path,
        report_label="mission40-performance",
        replay_label="mission40-replay",
    )

    run_shadow_research_decision_gate(
        db_path=db_path,
        gate_label="mission40-gate",
        report_label="mission40-performance",
    )

    open_shadow_paper_observations(
        db_path=db_path,
        ledger_label="mission40-ledger",
        gate_label="mission40-gate",
        simulated_notional_usd=1000.0,
    )

    return evaluate_shadow_observation_lifecycle(
        db_path=db_path,
        snapshot_label=snapshot_label,
        report_label=f"{snapshot_label}-report",
        gate_label="mission40-gate",
    )


def test_missing_database_returns_no_lifecycle_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_shadow_observation_pnl_attribution(
        db_path=db_path,
        attribution_label="mission40-missing",
        report_label="mission40-missing-report",
    )

    assert result["database_exists"] is False
    assert result["observation_count"] == 0
    assert result["global_verdict"] == NO_LIFECYCLE_HISTORY_VERDICT


def test_pnl_attribution_marks_early_observations_negative_after_cost(tmp_path):
    db_path = tmp_path / "mission40.db"
    prepare_lifecycle_snapshot(db_path)

    result = run_shadow_observation_pnl_attribution(
        db_path=db_path,
        attribution_label="mission40-attr",
        report_label="mission40-report",
        snapshot_label="mission40-snapshot",
        gate_label="mission40-gate",
    )

    assert result["observation_count"] == 2
    assert result["negative_count"] == 2
    assert result["positive_count"] == 0
    assert result["safety_breach_count"] == 0
    assert result["total_cost_usd"] > 0
    assert result["total_net_expected_pnl_usd"] < 0
    assert result["global_verdict"] == NEGATIVE_NET_VERDICT

    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM shadow_observation_pnl_attribution
            WHERE attribution_label = ?
            """,
            ("mission40-attr",),
        ).fetchone()[0]

        report = conn.execute(
            """
            SELECT
                report_label,
                observation_count,
                negative_count,
                safety_breach_count,
                global_verdict
            FROM shadow_observation_pnl_attribution_reports
            WHERE report_label = ?
            """,
            ("mission40-report",),
        ).fetchone()

    assert count == 2
    assert report == (
        "mission40-report",
        2,
        2,
        0,
        NEGATIVE_NET_VERDICT,
    )


def test_pnl_attribution_can_be_positive_after_longer_holding_period(tmp_path):
    db_path = tmp_path / "mission40-positive.db"

    run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission40-positive-replay",
        scenario_names=["all"],
    )

    generate_shadow_replay_performance_report(
        db_path=db_path,
        report_label="mission40-positive-performance",
        replay_label="mission40-positive-replay",
    )

    run_shadow_research_decision_gate(
        db_path=db_path,
        gate_label="mission40-positive-gate",
        report_label="mission40-positive-performance",
    )

    open_shadow_paper_observations(
        db_path=db_path,
        ledger_label="mission40-positive-ledger",
        gate_label="mission40-positive-gate",
        simulated_notional_usd=1000.0,
    )

    old_time = (
        datetime.now(timezone.utc) - timedelta(hours=100)
    ).replace(microsecond=0).isoformat()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE shadow_paper_observation_ledger
            SET opened_at = ?
            WHERE source_gate_label = ?
            """,
            (old_time, "mission40-positive-gate"),
        )
        conn.commit()

    evaluate_shadow_observation_lifecycle(
        db_path=db_path,
        snapshot_label="mission40-positive-snapshot",
        report_label="mission40-positive-lifecycle-report",
        gate_label="mission40-positive-gate",
        max_holding_hours=200.0,
    )

    result = run_shadow_observation_pnl_attribution(
        db_path=db_path,
        attribution_label="mission40-positive-attr",
        report_label="mission40-positive-report",
        snapshot_label="mission40-positive-snapshot",
        gate_label="mission40-positive-gate",
    )

    assert result["observation_count"] == 2
    assert result["positive_count"] == 2
    assert result["negative_count"] == 0
    assert result["total_net_expected_pnl_usd"] > 0
    assert result["global_verdict"] == POSITIVE_NET_VERDICT


def test_pnl_attribution_detects_safety_breach(tmp_path):
    db_path = tmp_path / "mission40-breach.db"
    prepare_lifecycle_snapshot(db_path, snapshot_label="mission40-breach-snapshot")

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE shadow_observation_lifecycle_snapshots
            SET live_order_sent = 1
            WHERE snapshot_label = ?
            """,
            ("mission40-breach-snapshot",),
        )
        conn.commit()

    result = run_shadow_observation_pnl_attribution(
        db_path=db_path,
        attribution_label="mission40-breach-attr",
        report_label="mission40-breach-report",
        snapshot_label="mission40-breach-snapshot",
        gate_label="mission40-gate",
    )

    assert result["observation_count"] == 2
    assert result["safety_breach_count"] == 2
    assert result["global_verdict"] == SAFETY_BREACH_VERDICT

    for item in result["attributions"]:
        assert item["attribution_status"] == "SAFETY_BREACH"
