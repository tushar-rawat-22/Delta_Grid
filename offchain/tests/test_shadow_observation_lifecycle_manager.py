import sqlite3
from datetime import datetime, timedelta, timezone

from offchain.backtest.shadow_candidate_replay_harness import run_shadow_candidate_replay
from offchain.backtest.shadow_replay_performance_reporter import generate_shadow_replay_performance_report
from offchain.backtest.shadow_research_decision_gate import run_shadow_research_decision_gate
from offchain.backtest.shadow_paper_observation_ledger import open_shadow_paper_observations
from offchain.backtest.shadow_observation_lifecycle_manager import (
    CLOSE_ELIGIBLE_VERDICT,
    NO_LEDGER_HISTORY_VERDICT,
    RISK_REVIEW_VERDICT,
    SAFETY_BREACH_VERDICT,
    TRACKING_VERDICT,
    evaluate_shadow_observation_lifecycle,
)


def prepare_open_observations(db_path):
    run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission39-replay",
        scenario_names=["all"],
    )

    generate_shadow_replay_performance_report(
        db_path=db_path,
        report_label="mission39-performance",
        replay_label="mission39-replay",
    )

    run_shadow_research_decision_gate(
        db_path=db_path,
        gate_label="mission39-gate",
        report_label="mission39-performance",
    )

    open_shadow_paper_observations(
        db_path=db_path,
        ledger_label="mission39-ledger",
        gate_label="mission39-gate",
        simulated_notional_usd=1000.0,
    )


def test_missing_database_returns_no_ledger_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = evaluate_shadow_observation_lifecycle(
        db_path=db_path,
        snapshot_label="mission39-missing",
    )

    assert result["database_exists"] is False
    assert result["observation_count"] == 0
    assert result["global_verdict"] == NO_LEDGER_HISTORY_VERDICT


def test_lifecycle_tracks_open_observations(tmp_path):
    db_path = tmp_path / "mission39.db"
    prepare_open_observations(db_path)

    result = evaluate_shadow_observation_lifecycle(
        db_path=db_path,
        snapshot_label="mission39-snapshot",
        report_label="mission39-report",
        gate_label="mission39-gate",
    )

    assert result["global_verdict"] == TRACKING_VERDICT
    assert result["observation_count"] == 2
    assert result["tracking_count"] == 2
    assert result["close_eligible_count"] == 0
    assert result["risk_review_count"] == 0
    assert result["safety_breach_count"] == 0
    assert result["status_counts"] == {"TRACKING": 2}
    assert result["symbol_counts"] == {"BTCUSDT": 2}

    for snapshot in result["snapshots"]:
        assert snapshot["live_trading"] == "DISABLED"
        assert snapshot["live_order_sent"] == 0
        assert snapshot["capital_deployment"] == "BLOCKED"
        assert snapshot["close_eligible"] is False

    with sqlite3.connect(db_path) as conn:
        snapshot_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM shadow_observation_lifecycle_snapshots
            WHERE snapshot_label = ?
            """,
            ("mission39-snapshot",),
        ).fetchone()[0]

        report = conn.execute(
            """
            SELECT
                report_label,
                observation_count,
                tracking_count,
                safety_breach_count,
                global_verdict
            FROM shadow_observation_lifecycle_reports
            WHERE report_label = ?
            """,
            ("mission39-report",),
        ).fetchone()

    assert snapshot_count == 2
    assert report == (
        "mission39-report",
        2,
        2,
        0,
        TRACKING_VERDICT,
    )


def test_lifecycle_marks_old_observations_close_eligible(tmp_path):
    db_path = tmp_path / "mission39-old.db"
    prepare_open_observations(db_path)

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
            (old_time, "mission39-gate"),
        )
        conn.commit()

    result = evaluate_shadow_observation_lifecycle(
        db_path=db_path,
        snapshot_label="mission39-old-snapshot",
        gate_label="mission39-gate",
        max_holding_hours=72.0,
    )

    assert result["global_verdict"] == CLOSE_ELIGIBLE_VERDICT
    assert result["observation_count"] == 2
    assert result["close_eligible_count"] == 2
    assert result["tracking_count"] == 0

    for snapshot in result["snapshots"]:
        assert snapshot["lifecycle_status"] == "CLOSE_ELIGIBLE"
        assert snapshot["close_eligible"] is True
        assert snapshot["close_reason"] == "MAX_HOLDING_PERIOD_REACHED"


def test_lifecycle_detects_safety_breach(tmp_path):
    db_path = tmp_path / "mission39-breach.db"
    prepare_open_observations(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE shadow_paper_observation_ledger
            SET live_order_sent = 1
            WHERE source_gate_label = ?
            """,
            ("mission39-gate",),
        )
        conn.commit()

    result = evaluate_shadow_observation_lifecycle(
        db_path=db_path,
        snapshot_label="mission39-breach-snapshot",
        gate_label="mission39-gate",
    )

    assert result["global_verdict"] == SAFETY_BREACH_VERDICT
    assert result["safety_breach_count"] == 2
    assert result["close_eligible_count"] == 0

    for snapshot in result["snapshots"]:
        assert snapshot["lifecycle_status"] == "SAFETY_BREACH"
        assert "LIVE_ORDER_SENT_NOT_FALSE" in snapshot["risk_flags"]


def test_lifecycle_detects_risk_review_state(tmp_path):
    db_path = tmp_path / "mission39-risk.db"
    prepare_open_observations(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE shadow_paper_observation_ledger
            SET risk_snapshot_json = ?
            WHERE source_gate_label = ?
            """,
            (
                '{"basis_bps": 10.0, "estimated_slippage_bps": 9.0, "leverage": 1.0, "liquidity_score": 60.0, "spread_bps": 8.0, "stressed_liquidation_buffer": 0.20}',
                "mission39-gate",
            ),
        )
        conn.commit()

    result = evaluate_shadow_observation_lifecycle(
        db_path=db_path,
        snapshot_label="mission39-risk-snapshot",
        gate_label="mission39-gate",
    )

    assert result["global_verdict"] == RISK_REVIEW_VERDICT
    assert result["risk_review_count"] == 2
    assert result["safety_breach_count"] == 0

    for snapshot in result["snapshots"]:
        assert snapshot["lifecycle_status"] == "RISK_REVIEW"
        assert "LIQUIDATION_BUFFER_BELOW_MINIMUM" in snapshot["risk_flags"]
        assert "SPREAD_ABOVE_MAXIMUM" in snapshot["risk_flags"]
        assert "SLIPPAGE_ABOVE_MAXIMUM" in snapshot["risk_flags"]
        assert "LIQUIDITY_SCORE_BELOW_MINIMUM" in snapshot["risk_flags"]
