import sqlite3

from offchain.cycles.paper_multi_cycle_observation_tracker import (
    DECISION_BLOCK_SAFETY,
    DECISION_CONFIRMED,
    DECISION_REJECT_MISSING,
    DECISION_UNSTABLE,
    VERDICT_BLOCKED,
    VERDICT_CONFIRMED,
    VERDICT_MISSING,
    VERDICT_UNSTABLE,
    parse_labels,
    run_multi_cycle_paper_observation_tracker,
)


def create_recovery_table(conn):
    conn.execute(
        """
        CREATE TABLE paper_recovery_stability_reviews (
            review_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_kill_switch_review_label TEXT NOT NULL,
            source_performance_run_label TEXT,
            source_capital_review_label TEXT,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            paper_notional TEXT NOT NULL,
            monitored_position_count INTEGER NOT NULL,
            check_count INTEGER NOT NULL,
            pass_check_count INTEGER NOT NULL,
            fail_check_count INTEGER NOT NULL,
            net_paper_pnl TEXT NOT NULL,
            net_paper_pnl_bps TEXT NOT NULL,
            max_position_loss_bps TEXT NOT NULL,
            fee_drag_bps TEXT NOT NULL,
            alert_count INTEGER NOT NULL,
            triggered_event_count INTEGER NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            recovery_stability_state TEXT NOT NULL,
            recovery_stability_decision TEXT NOT NULL,
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


def insert_recovery_review(
    conn,
    review_label="recovery-1",
    net_pnl="-20",
    net_bps="-2",
    max_position_loss_bps="-2",
    fee_drag_bps="2",
    alert_count=0,
    triggered_event_count=0,
    safety_breach_count=0,
    fail_check_count=0,
    state="RECOVERY_STABILITY_STATE_CONFIRMED",
    decision="PAPER_RECOVERY_STABILITY_CONFIRMED_CONTINUE_OBSERVATION",
    verdict="PAPER_RECOVERY_STABILITY_CONFIRMED_SHADOW_ONLY",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO paper_recovery_stability_reviews (
            review_label,
            report_label,
            created_at,
            source_kill_switch_review_label,
            source_performance_run_label,
            source_capital_review_label,
            source_session_label,
            source_portfolio_label,
            paper_notional,
            monitored_position_count,
            check_count,
            pass_check_count,
            fail_check_count,
            net_paper_pnl,
            net_paper_pnl_bps,
            max_position_loss_bps,
            fee_drag_bps,
            alert_count,
            triggered_event_count,
            safety_breach_count,
            recovery_stability_state,
            recovery_stability_decision,
            global_verdict,
            recommended_action,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_label,
            f"{review_label}-report",
            "2026-01-01T00:00:00+00:00",
            "kill-1",
            "run-1",
            "capital-1",
            "session-1",
            "portfolio-1",
            "100000",
            4,
            10,
            10,
            fail_check_count,
            net_pnl,
            net_bps,
            max_position_loss_bps,
            fee_drag_bps,
            alert_count,
            triggered_event_count,
            safety_breach_count,
            state,
            decision,
            verdict,
            "CONTINUE_PAPER_OBSERVATION_AND_BEGIN_MULTI_CYCLE_TRACKING",
            "Mission 69 Multi-Cycle Paper Observation Tracker",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )


def seed_good(conn):
    create_recovery_table(conn)
    insert_recovery_review(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("recovery-1,recovery-2,recovery-1") == ["recovery-1", "recovery-2"]


def test_multi_cycle_tracker_confirms_single_good_cycle_and_persists(tmp_path):
    db_path = tmp_path / "mission69.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_multi_cycle_paper_observation_tracker(
        db_path=db_path,
        track_label="track-1",
        report_label="report-1",
        recovery_review_labels="recovery-1",
    )

    assert result["multi_cycle_decision"] == DECISION_CONFIRMED
    assert result["global_verdict"] == VERDICT_CONFIRMED
    assert result["cycle_count"] == 1
    assert result["check_count"] == 11
    assert result["pass_check_count"] == 11
    assert result["fail_check_count"] == 0
    assert result["cumulative_net_paper_pnl"] == -20
    assert result["cumulative_net_pnl_bps"] == -2
    assert result["worst_cycle_net_pnl_bps"] == -2
    assert result["worst_position_loss_bps"] == -2
    assert result["average_fee_drag_bps"] == 2
    assert result["safety_breach_count"] == 0

    with sqlite3.connect(db_path) as conn:
        track = conn.execute(
            """
            SELECT track_label, multi_cycle_decision, global_verdict
            FROM paper_multi_cycle_observation_tracks
            WHERE track_label = ?
            """,
            ("track-1",),
        ).fetchone()

        cycle_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM paper_multi_cycle_observation_cycles
            WHERE track_label = ?
            """,
            ("track-1",),
        ).fetchone()[0]

    assert track == ("track-1", DECISION_CONFIRMED, VERDICT_CONFIRMED)
    assert cycle_count == 1


def test_multi_cycle_tracker_rejects_missing_recovery_review(tmp_path):
    db_path = tmp_path / "mission69-missing.db"

    result = run_multi_cycle_paper_observation_tracker(
        db_path=db_path,
        track_label="missing-track",
        report_label="missing-report",
        recovery_review_labels="missing-recovery",
    )

    assert result["multi_cycle_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["cycle_count"] == 0


def test_multi_cycle_tracker_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission69-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_recovery_table(conn)
        insert_recovery_review(
            conn,
            safety_breach_count=1,
            live_trading="ENABLED",
        )
        conn.commit()

    result = run_multi_cycle_paper_observation_tracker(
        db_path=db_path,
        track_label="safety-track",
        report_label="safety-report",
        recovery_review_labels="recovery-1",
    )

    assert result["multi_cycle_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED
    assert result["safety_breach_count"] >= 1


def test_multi_cycle_tracker_flags_unconfirmed_recovery_decision(tmp_path):
    db_path = tmp_path / "mission69-unconfirmed.db"

    with sqlite3.connect(db_path) as conn:
        create_recovery_table(conn)
        insert_recovery_review(
            conn,
            decision="PAPER_RECOVERY_STABILITY_UNSTABLE_STOP_AND_REVIEW",
            verdict="PAPER_RECOVERY_STABILITY_UNSTABLE_SHADOW_ONLY",
            state="RECOVERY_STABILITY_STATE_UNSTABLE",
        )
        conn.commit()

    result = run_multi_cycle_paper_observation_tracker(
        db_path=db_path,
        track_label="unconfirmed-track",
        report_label="unconfirmed-report",
        recovery_review_labels="recovery-1",
    )

    assert result["multi_cycle_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["fail_check_count"] >= 1


def test_multi_cycle_tracker_flags_cumulative_loss_threshold(tmp_path):
    db_path = tmp_path / "mission69-loss.db"

    with sqlite3.connect(db_path) as conn:
        create_recovery_table(conn)
        insert_recovery_review(conn, net_pnl="-800", net_bps="-80")
        conn.commit()

    result = run_multi_cycle_paper_observation_tracker(
        db_path=db_path,
        track_label="loss-track",
        report_label="loss-report",
        recovery_review_labels="recovery-1",
        max_allowed_cumulative_loss_bps=50,
    )

    assert result["multi_cycle_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["cumulative_net_pnl_bps"] < -50


def test_multi_cycle_tracker_flags_triggered_event_count(tmp_path):
    db_path = tmp_path / "mission69-events.db"

    with sqlite3.connect(db_path) as conn:
        create_recovery_table(conn)
        insert_recovery_review(conn, triggered_event_count=1)
        conn.commit()

    result = run_multi_cycle_paper_observation_tracker(
        db_path=db_path,
        track_label="events-track",
        report_label="events-report",
        recovery_review_labels="recovery-1",
        max_allowed_triggered_events=0,
    )

    assert result["multi_cycle_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["total_triggered_event_count"] == 1


def test_multi_cycle_tracker_handles_two_good_cycles(tmp_path):
    db_path = tmp_path / "mission69-two.db"

    with sqlite3.connect(db_path) as conn:
        create_recovery_table(conn)
        insert_recovery_review(conn, review_label="recovery-1", net_pnl="-20", net_bps="-2")
        insert_recovery_review(conn, review_label="recovery-2", net_pnl="10", net_bps="1")
        conn.commit()

    result = run_multi_cycle_paper_observation_tracker(
        db_path=db_path,
        track_label="two-track",
        report_label="two-report",
        recovery_review_labels="recovery-1,recovery-2",
        min_cycles=2,
    )

    assert result["multi_cycle_decision"] == DECISION_CONFIRMED
    assert result["cycle_count"] == 2
    assert result["cumulative_net_paper_pnl"] == -10
    assert result["average_cycle_net_pnl_bps"] == -0.5


def test_markdown_report_contains_ai_dataset_scope(tmp_path):
    db_path = tmp_path / "mission69-markdown.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_multi_cycle_paper_observation_tracker(
        db_path=db_path,
        track_label="markdown-track",
        report_label="markdown-report",
        recovery_review_labels="recovery-1",
    )

    assert "# DeltaGrid Mission 69" in result["markdown_report"]
    assert "prepares data for AI learning" in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]
