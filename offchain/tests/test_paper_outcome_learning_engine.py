import sqlite3

from offchain.ai_outcome.paper_outcome_learning_engine import (
    AUTONOMY_LABEL_RECOMMENDATION_ONLY,
    DECISION_BLOCK_SAFETY,
    DECISION_READY,
    DECISION_REJECT_MISSING,
    DECISION_UNSTABLE,
    OUTCOME_LABEL_EARLY_STABLE,
    OUTCOME_LABEL_STABLE,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_ai_paper_outcome_learning_engine,
)


def create_multi_cycle_tables(conn):
    conn.execute(
        """
        CREATE TABLE paper_multi_cycle_observation_tracks (
            track_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            recovery_review_labels_json TEXT NOT NULL,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            cycle_count INTEGER NOT NULL,
            paper_notional TEXT NOT NULL,
            cumulative_net_paper_pnl TEXT NOT NULL,
            cumulative_net_pnl_bps TEXT NOT NULL,
            average_cycle_net_pnl_bps TEXT NOT NULL,
            worst_cycle_net_pnl_bps TEXT NOT NULL,
            worst_position_loss_bps TEXT NOT NULL,
            average_fee_drag_bps TEXT NOT NULL,
            total_alert_count INTEGER NOT NULL,
            total_triggered_event_count INTEGER NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            check_count INTEGER NOT NULL,
            pass_check_count INTEGER NOT NULL,
            fail_check_count INTEGER NOT NULL,
            multi_cycle_state TEXT NOT NULL,
            multi_cycle_decision TEXT NOT NULL,
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

    conn.execute(
        """
        CREATE TABLE paper_multi_cycle_observation_cycles (
            cycle_id TEXT PRIMARY KEY,
            track_label TEXT NOT NULL,
            cycle_index INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            source_recovery_review_label TEXT NOT NULL,
            source_kill_switch_review_label TEXT,
            source_performance_run_label TEXT,
            source_capital_review_label TEXT,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            paper_notional TEXT NOT NULL,
            monitored_position_count INTEGER NOT NULL,
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
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE paper_multi_cycle_observation_checks (
            check_id TEXT PRIMARY KEY,
            track_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            check_category TEXT NOT NULL,
            check_name TEXT NOT NULL,
            check_status TEXT NOT NULL,
            observed_value TEXT NOT NULL,
            threshold_value TEXT NOT NULL,
            check_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_track(
    conn,
    track_label="track-1",
    cycle_count=1,
    cumulative_net_pnl="-20",
    cumulative_net_bps="-2",
    average_cycle_bps="-2",
    worst_cycle_bps="-2",
    worst_position_bps="-2",
    average_fee_drag_bps="2",
    total_alert_count=0,
    total_triggered_event_count=0,
    safety_breach_count=0,
    check_count=11,
    pass_check_count=11,
    fail_check_count=0,
    state="MULTI_CYCLE_STATE_CONFIRMED",
    decision="MULTI_CYCLE_OBSERVATION_CONFIRMED_CONTINUE_TRACKING",
    verdict="MULTI_CYCLE_OBSERVATION_TRACK_READY_SHADOW_ONLY",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO paper_multi_cycle_observation_tracks (
            track_label,
            report_label,
            created_at,
            recovery_review_labels_json,
            source_session_label,
            source_portfolio_label,
            cycle_count,
            paper_notional,
            cumulative_net_paper_pnl,
            cumulative_net_pnl_bps,
            average_cycle_net_pnl_bps,
            worst_cycle_net_pnl_bps,
            worst_position_loss_bps,
            average_fee_drag_bps,
            total_alert_count,
            total_triggered_event_count,
            safety_breach_count,
            check_count,
            pass_check_count,
            fail_check_count,
            multi_cycle_state,
            multi_cycle_decision,
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
            track_label,
            f"{track_label}-report",
            "2026-01-01T00:00:00+00:00",
            '["recovery-1"]',
            "session-1",
            "portfolio-1",
            cycle_count,
            "100000",
            cumulative_net_pnl,
            cumulative_net_bps,
            average_cycle_bps,
            worst_cycle_bps,
            worst_position_bps,
            average_fee_drag_bps,
            total_alert_count,
            total_triggered_event_count,
            safety_breach_count,
            check_count,
            pass_check_count,
            fail_check_count,
            state,
            decision,
            verdict,
            "CONTINUE_MULTI_CYCLE_PAPER_TRACKING_AND_PREPARE_AI_DATASET",
            "Mission 70 AI Paper Outcome Learning Engine",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )


def insert_cycle(
    conn,
    cycle_id="cycle-1",
    track_label="track-1",
    cycle_index=1,
    net_pnl="-20",
    net_bps="-2",
):
    conn.execute(
        """
        INSERT INTO paper_multi_cycle_observation_cycles (
            cycle_id,
            track_label,
            cycle_index,
            created_at,
            source_recovery_review_label,
            source_kill_switch_review_label,
            source_performance_run_label,
            source_capital_review_label,
            source_session_label,
            source_portfolio_label,
            paper_notional,
            monitored_position_count,
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
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cycle_id,
            track_label,
            cycle_index,
            "2026-01-01T00:00:00+00:00",
            f"recovery-{cycle_index}",
            "kill-1",
            "run-1",
            "capital-1",
            "session-1",
            "portfolio-1",
            "100000",
            4,
            net_pnl,
            net_bps,
            "-2",
            "2",
            0,
            0,
            0,
            "RECOVERY_STABILITY_STATE_CONFIRMED",
            "PAPER_RECOVERY_STABILITY_CONFIRMED_CONTINUE_OBSERVATION",
            "PAPER_RECOVERY_STABILITY_CONFIRMED_SHADOW_ONLY",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def insert_check(conn, check_id="check-1", track_label="track-1"):
    conn.execute(
        """
        INSERT INTO paper_multi_cycle_observation_checks (
            check_id,
            track_label,
            created_at,
            check_category,
            check_name,
            check_status,
            observed_value,
            threshold_value,
            check_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            check_id,
            track_label,
            "2026-01-01T00:00:00+00:00",
            "safety",
            "safety breach count",
            "MULTI_CYCLE_CHECK_PASS",
            "0",
            "0",
            "test",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def seed_good(conn):
    create_multi_cycle_tables(conn)
    insert_track(conn)
    insert_cycle(conn)
    insert_check(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("track-1,track-2,track-1") == ["track-1", "track-2"]


def test_ai_learning_ready_for_good_early_track_and_persists(tmp_path):
    db_path = tmp_path / "mission70.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_outcome_learning_engine(
        db_path=db_path,
        learning_run_label="learning-1",
        report_label="report-1",
        multi_cycle_track_label="track-1",
    )

    assert result["learning_decision"] == DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["cycle_count"] == 1
    assert result["feature_count"] == 12
    assert result["label_count"] == 4
    assert result["recommendation_count"] == 3
    assert result["learning_score"] >= 75
    assert result["outcome_label"] == OUTCOME_LABEL_EARLY_STABLE
    assert result["autonomy_label"] == AUTONOMY_LABEL_RECOMMENDATION_ONLY
    assert result["safety_breach_count"] == 0

    with sqlite3.connect(db_path) as conn:
        run = conn.execute(
            """
            SELECT learning_run_label, learning_decision, global_verdict
            FROM ai_paper_outcome_learning_runs
            WHERE learning_run_label = ?
            """,
            ("learning-1",),
        ).fetchone()

        feature_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ai_paper_outcome_learning_features
            WHERE learning_run_label = ?
            """,
            ("learning-1",),
        ).fetchone()[0]

    assert run == ("learning-1", DECISION_READY, VERDICT_READY)
    assert feature_count == 12


def test_ai_learning_rejects_missing_track(tmp_path):
    db_path = tmp_path / "mission70-missing.db"

    result = run_ai_paper_outcome_learning_engine(
        db_path=db_path,
        learning_run_label="missing-learning",
        report_label="missing-report",
        multi_cycle_track_label="missing-track",
    )

    assert result["learning_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["cycle_count"] == 0


def test_ai_learning_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission70-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_multi_cycle_tables(conn)
        insert_track(conn, safety_breach_count=1, live_trading="ENABLED")
        conn.commit()

    result = run_ai_paper_outcome_learning_engine(
        db_path=db_path,
        learning_run_label="safety-learning",
        report_label="safety-report",
        multi_cycle_track_label="track-1",
    )

    assert result["learning_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED
    assert result["safety_breach_count"] >= 1


def test_ai_learning_flags_unconfirmed_track(tmp_path):
    db_path = tmp_path / "mission70-unconfirmed.db"

    with sqlite3.connect(db_path) as conn:
        create_multi_cycle_tables(conn)
        insert_track(
            conn,
            state="MULTI_CYCLE_STATE_UNSTABLE",
            decision="MULTI_CYCLE_OBSERVATION_UNSTABLE_STOP_AND_REVIEW",
            verdict="MULTI_CYCLE_OBSERVATION_TRACK_UNSTABLE_SHADOW_ONLY",
        )
        conn.commit()

    result = run_ai_paper_outcome_learning_engine(
        db_path=db_path,
        learning_run_label="unconfirmed-learning",
        report_label="unconfirmed-report",
        multi_cycle_track_label="track-1",
    )

    assert result["learning_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_ai_learning_flags_large_loss_threshold(tmp_path):
    db_path = tmp_path / "mission70-loss.db"

    with sqlite3.connect(db_path) as conn:
        create_multi_cycle_tables(conn)
        insert_track(conn, cumulative_net_pnl="-900", cumulative_net_bps="-90")
        conn.commit()

    result = run_ai_paper_outcome_learning_engine(
        db_path=db_path,
        learning_run_label="loss-learning",
        report_label="loss-report",
        multi_cycle_track_label="track-1",
        max_allowed_learning_loss_bps=50,
    )

    assert result["learning_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_ai_learning_multi_cycle_stable_label(tmp_path):
    db_path = tmp_path / "mission70-multi.db"

    with sqlite3.connect(db_path) as conn:
        create_multi_cycle_tables(conn)
        insert_track(
            conn,
            cycle_count=3,
            cumulative_net_pnl="40",
            cumulative_net_bps="1.333333",
            average_cycle_bps="1",
            worst_cycle_bps="-1",
            worst_position_bps="-2",
        )
        insert_cycle(conn, "cycle-1", cycle_index=1, net_pnl="-20", net_bps="-2")
        insert_cycle(conn, "cycle-2", cycle_index=2, net_pnl="30", net_bps="3")
        insert_cycle(conn, "cycle-3", cycle_index=3, net_pnl="30", net_bps="3")
        conn.commit()

    result = run_ai_paper_outcome_learning_engine(
        db_path=db_path,
        learning_run_label="multi-learning",
        report_label="multi-report",
        multi_cycle_track_label="track-1",
        min_recommended_cycles=3,
    )

    assert result["learning_decision"] == DECISION_READY
    assert result["outcome_label"] == OUTCOME_LABEL_STABLE
    assert result["cycle_count"] == 3


def test_ai_learning_can_be_blocked_by_high_min_score(tmp_path):
    db_path = tmp_path / "mission70-score.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_outcome_learning_engine(
        db_path=db_path,
        learning_run_label="score-learning",
        report_label="score-report",
        multi_cycle_track_label="track-1",
        min_learning_score=99,
    )

    assert result["learning_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_markdown_report_contains_recommendation_only_scope(tmp_path):
    db_path = tmp_path / "mission70-markdown.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_outcome_learning_engine(
        db_path=db_path,
        learning_run_label="markdown-learning",
        report_label="markdown-report",
        multi_cycle_track_label="track-1",
    )

    assert "# DeltaGrid Mission 70" in result["markdown_report"]
    assert "AI output is recommendation-only." in result["markdown_report"]
    assert "does not perform autonomous trading" in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]
