import sqlite3

from offchain.recovery.paper_recovery_stability_monitor import (
    DECISION_BLOCK_SAFETY,
    DECISION_CONFIRMED,
    DECISION_REJECT_MISSING,
    DECISION_UNSTABLE,
    VERDICT_BLOCKED,
    VERDICT_CONFIRMED,
    VERDICT_MISSING,
    VERDICT_UNSTABLE,
    parse_symbols,
    run_paper_recovery_stability_monitor,
)


def create_source_tables(conn):
    conn.execute(
        """
        CREATE TABLE paper_drawdown_kill_switch_reviews (
            review_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_performance_run_label TEXT NOT NULL,
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
            kill_switch_state TEXT NOT NULL,
            kill_switch_decision TEXT NOT NULL,
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
        CREATE TABLE paper_drawdown_kill_switch_checks (
            check_id TEXT PRIMARY KEY,
            review_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_performance_run_label TEXT NOT NULL,
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

    conn.execute(
        """
        CREATE TABLE paper_drawdown_kill_switch_events (
            event_id TEXT PRIMARY KEY,
            review_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_performance_run_label TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_status TEXT NOT NULL,
            observed_value TEXT NOT NULL,
            threshold_value TEXT NOT NULL,
            event_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE paper_observation_performance_runs (
            run_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_capital_review_label TEXT NOT NULL,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            paper_notional TEXT NOT NULL,
            monitored_position_count INTEGER NOT NULL,
            order_count INTEGER NOT NULL,
            gross_unrealized_paper_pnl TEXT NOT NULL,
            total_simulated_fees TEXT NOT NULL,
            net_paper_pnl TEXT NOT NULL,
            net_paper_pnl_bps TEXT NOT NULL,
            max_position_loss_bps TEXT NOT NULL,
            fee_drag_bps TEXT NOT NULL,
            win_rate_pct TEXT NOT NULL,
            alert_count INTEGER NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            performance_health TEXT NOT NULL,
            performance_decision TEXT NOT NULL,
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
        CREATE TABLE paper_observation_position_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            run_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_session_label TEXT,
            position_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            quantity TEXT NOT NULL,
            entry_price TEXT NOT NULL,
            observed_price TEXT NOT NULL,
            entry_notional TEXT NOT NULL,
            gross_paper_pnl TEXT NOT NULL,
            simulated_fee_amount TEXT NOT NULL,
            net_paper_pnl TEXT NOT NULL,
            net_paper_pnl_bps TEXT NOT NULL,
            snapshot_status TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_kill_switch_review(
    conn,
    review_label="kill-1",
    performance_run_label="run-1",
    fail_check_count=0,
    triggered_event_count=0,
    safety_breach_count=0,
    kill_switch_decision="PAPER_DRAWDOWN_KILL_SWITCH_ARMED_CONTINUE_OBSERVATION",
    global_verdict="PAPER_DRAWDOWN_KILL_SWITCH_ARMED_SHADOW_ONLY",
    kill_switch_state="KILL_SWITCH_STATE_ARMED_NOT_TRIGGERED",
    net_bps="-2",
    max_position_loss_bps="-2",
    fee_drag_bps="2",
    alert_count=0,
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO paper_drawdown_kill_switch_reviews (
            review_label,
            report_label,
            created_at,
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
            kill_switch_state,
            kill_switch_decision,
            global_verdict,
            recommended_action,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_label,
            f"{review_label}-report",
            "2026-01-01T00:00:00+00:00",
            performance_run_label,
            "capital-1",
            "session-1",
            "portfolio-1",
            "100000",
            4,
            8,
            8,
            fail_check_count,
            "-20",
            net_bps,
            max_position_loss_bps,
            fee_drag_bps,
            alert_count,
            triggered_event_count,
            safety_breach_count,
            kill_switch_state,
            kill_switch_decision,
            global_verdict,
            "CONTINUE_PAPER_OBSERVATION_WITH_KILL_SWITCH_ARMED",
            "Mission 68 Paper Recovery Stability Monitor",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )


def insert_kill_switch_check(
    conn,
    check_id,
    review_label="kill-1",
    status="DRAWDOWN_CHECK_PASS",
    category="safety",
    name="safety invariants",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO paper_drawdown_kill_switch_checks (
            check_id,
            review_label,
            created_at,
            source_performance_run_label,
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            check_id,
            review_label,
            "2026-01-01T00:00:00+00:00",
            "run-1",
            category,
            name,
            status,
            "0",
            "0",
            "test",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def insert_kill_switch_event(
    conn,
    event_id="armed-event",
    review_label="kill-1",
    event_type="PAPER_DRAWDOWN_KILL_SWITCH_ARMED",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO paper_drawdown_kill_switch_events (
            event_id,
            review_label,
            created_at,
            source_performance_run_label,
            event_type,
            event_status,
            observed_value,
            threshold_value,
            event_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            review_label,
            "2026-01-01T00:00:00+00:00",
            "run-1",
            event_type,
            "RECORDED",
            "all_checks_passed",
            "no trigger",
            "test",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def insert_performance_run(conn):
    conn.execute(
        """
        INSERT INTO paper_observation_performance_runs (
            run_label,
            report_label,
            created_at,
            source_capital_review_label,
            source_session_label,
            source_portfolio_label,
            paper_notional,
            monitored_position_count,
            order_count,
            gross_unrealized_paper_pnl,
            total_simulated_fees,
            net_paper_pnl,
            net_paper_pnl_bps,
            max_position_loss_bps,
            fee_drag_bps,
            win_rate_pct,
            alert_count,
            safety_breach_count,
            performance_health,
            performance_decision,
            global_verdict,
            recommended_action,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "run-1",
            "run-1-report",
            "2026-01-01T00:00:00+00:00",
            "capital-1",
            "session-1",
            "portfolio-1",
            "100000",
            4,
            4,
            "0",
            "20",
            "-20",
            "-2",
            "-2",
            "2",
            "0",
            0,
            0,
            "PAPER_OBSERVATION_HEALTH_STABLE_BASELINE",
            "PAPER_OBSERVATION_PERFORMANCE_CONTINUE_MONITORING",
            "PAPER_OBSERVATION_PERFORMANCE_READY_SHADOW_ONLY",
            "CONTINUE_PAPER_OBSERVATION_AND_COLLECT_MORE_SNAPSHOTS",
            "Mission 67 Paper Drawdown Kill Switch",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
            "# report",
        ),
    )


def insert_snapshot(
    conn,
    snapshot_id,
    symbol="BTCUSDT",
    net_bps="-2",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO paper_observation_position_snapshots (
            snapshot_id,
            run_label,
            created_at,
            source_session_label,
            position_id,
            symbol,
            strategy_id,
            quantity,
            entry_price,
            observed_price,
            entry_notional,
            gross_paper_pnl,
            simulated_fee_amount,
            net_paper_pnl,
            net_paper_pnl_bps,
            snapshot_status,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            "run-1",
            "2026-01-01T00:00:00+00:00",
            "session-1",
            f"position-{snapshot_id}",
            symbol,
            "S1",
            "1",
            "100",
            "100",
            "25000",
            "0",
            "5",
            "-5",
            net_bps,
            "PAPER_POSITION_SNAPSHOT_LOSS",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def seed_good_source(conn):
    create_source_tables(conn)
    insert_kill_switch_review(conn)
    for idx in range(8):
        insert_kill_switch_check(conn, f"check-{idx}")
    insert_kill_switch_event(conn)
    insert_performance_run(conn)
    insert_snapshot(conn, "s1", "BTCUSDT")
    insert_snapshot(conn, "s2", "ETHUSDT")
    insert_snapshot(conn, "s3", "BTCUSDT")
    insert_snapshot(conn, "s4", "ETHUSDT")


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_recovery_stability_confirms_good_kill_switch_and_persists(tmp_path):
    db_path = tmp_path / "mission68.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_source(conn)
        conn.commit()

    result = run_paper_recovery_stability_monitor(
        db_path=db_path,
        review_label="recovery-1",
        report_label="recovery-report-1",
        kill_switch_review_label="kill-1",
    )

    assert result["recovery_stability_decision"] == DECISION_CONFIRMED
    assert result["global_verdict"] == VERDICT_CONFIRMED
    assert result["check_count"] == 10
    assert result["pass_check_count"] == 10
    assert result["fail_check_count"] == 0
    assert result["safety_breach_count"] == 0
    assert result["triggered_event_count"] == 0

    with sqlite3.connect(db_path) as conn:
        review = conn.execute(
            """
            SELECT review_label, recovery_stability_decision, global_verdict
            FROM paper_recovery_stability_reviews
            WHERE review_label = ?
            """,
            ("recovery-1",),
        ).fetchone()

        checks = conn.execute(
            """
            SELECT COUNT(*)
            FROM paper_recovery_stability_checks
            WHERE review_label = ?
            """,
            ("recovery-1",),
        ).fetchone()[0]

    assert review == ("recovery-1", DECISION_CONFIRMED, VERDICT_CONFIRMED)
    assert checks == 10


def test_recovery_stability_rejects_missing_kill_switch_review(tmp_path):
    db_path = tmp_path / "mission68-missing.db"

    result = run_paper_recovery_stability_monitor(
        db_path=db_path,
        review_label="missing-recovery",
        report_label="missing-report",
        kill_switch_review_label="missing-kill",
    )

    assert result["recovery_stability_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_recovery_stability_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission68-safety.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_source(conn)
        conn.execute(
            """
            UPDATE paper_drawdown_kill_switch_reviews
            SET safety_breach_count = ?, live_trading = ?
            WHERE review_label = ?
            """,
            (1, "ENABLED", "kill-1"),
        )
        conn.commit()

    result = run_paper_recovery_stability_monitor(
        db_path=db_path,
        review_label="safety-recovery",
        report_label="safety-report",
        kill_switch_review_label="kill-1",
    )

    assert result["recovery_stability_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED
    assert result["safety_breach_count"] >= 1


def test_recovery_stability_flags_unarmed_kill_switch(tmp_path):
    db_path = tmp_path / "mission68-unarmed.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_source(conn)
        conn.execute(
            """
            UPDATE paper_drawdown_kill_switch_reviews
            SET kill_switch_decision = ?, global_verdict = ?, kill_switch_state = ?
            WHERE review_label = ?
            """,
            (
                "PAPER_DRAWDOWN_KILL_SWITCH_TRIGGERED_STOP_OBSERVATION",
                "PAPER_DRAWDOWN_KILL_SWITCH_TRIGGERED_SHADOW_ONLY",
                "KILL_SWITCH_STATE_TRIGGERED",
                "kill-1",
            ),
        )
        conn.commit()

    result = run_paper_recovery_stability_monitor(
        db_path=db_path,
        review_label="unarmed-recovery",
        report_label="unarmed-report",
        kill_switch_review_label="kill-1",
    )

    assert result["recovery_stability_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["fail_check_count"] >= 1


def test_recovery_stability_flags_failed_drawdown_checks(tmp_path):
    db_path = tmp_path / "mission68-failed-checks.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_source(conn)
        conn.execute(
            """
            UPDATE paper_drawdown_kill_switch_reviews
            SET fail_check_count = ?
            WHERE review_label = ?
            """,
            (1, "kill-1"),
        )
        conn.commit()

    result = run_paper_recovery_stability_monitor(
        db_path=db_path,
        review_label="failed-check-recovery",
        report_label="failed-check-report",
        kill_switch_review_label="kill-1",
    )

    assert result["recovery_stability_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_recovery_stability_flags_triggered_event(tmp_path):
    db_path = tmp_path / "mission68-triggered.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_source(conn)
        insert_kill_switch_event(
            conn,
            event_id="triggered-event",
            event_type="PAPER_DRAWDOWN_KILL_SWITCH_TRIGGERED_drawdown_net_paper_pnl_bps",
        )
        conn.execute(
            """
            UPDATE paper_drawdown_kill_switch_reviews
            SET triggered_event_count = ?
            WHERE review_label = ?
            """,
            (1, "kill-1"),
        )
        conn.commit()

    result = run_paper_recovery_stability_monitor(
        db_path=db_path,
        review_label="triggered-recovery",
        report_label="triggered-report",
        kill_switch_review_label="kill-1",
    )

    assert result["recovery_stability_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["triggered_event_count"] == 1


def test_recovery_stability_flags_pnl_floor_breach(tmp_path):
    db_path = tmp_path / "mission68-pnl.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_source(conn)
        conn.execute(
            """
            UPDATE paper_drawdown_kill_switch_reviews
            SET net_paper_pnl_bps = ?
            WHERE review_label = ?
            """,
            ("-25", "kill-1"),
        )
        conn.commit()

    result = run_paper_recovery_stability_monitor(
        db_path=db_path,
        review_label="pnl-recovery",
        report_label="pnl-report",
        kill_switch_review_label="kill-1",
        min_recovery_net_pnl_bps=-10,
    )

    assert result["recovery_stability_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_markdown_report_contains_paper_only_scope(tmp_path):
    db_path = tmp_path / "mission68-markdown.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_source(conn)
        conn.commit()

    result = run_paper_recovery_stability_monitor(
        db_path=db_path,
        review_label="markdown-recovery",
        report_label="markdown-report",
        kill_switch_review_label="kill-1",
    )

    assert "# DeltaGrid Mission 68" in result["markdown_report"]
    assert "Recovery stability monitoring is paper-only and cannot send live orders." in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]
