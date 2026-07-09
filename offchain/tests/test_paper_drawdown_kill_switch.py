import sqlite3

from offchain.safety.paper_drawdown_kill_switch import (
    DECISION_ARMED,
    DECISION_BLOCK_SAFETY,
    DECISION_REJECT_MISSING,
    DECISION_TRIGGERED,
    VERDICT_ARMED,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_TRIGGERED,
    parse_symbols,
    run_paper_drawdown_kill_switch,
)


def create_performance_tables(conn):
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

    conn.execute(
        """
        CREATE TABLE paper_observation_performance_alerts (
            alert_id TEXT PRIMARY KEY,
            run_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_capital_review_label TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            alert_status TEXT NOT NULL,
            observed_value TEXT NOT NULL,
            threshold_value TEXT NOT NULL,
            alert_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_run(
    conn,
    run_label="run-1",
    net_bps="-2",
    max_position_loss_bps="-2",
    fee_drag_bps="2",
    alert_count=0,
    performance_decision="PAPER_OBSERVATION_PERFORMANCE_CONTINUE_MONITORING",
    global_verdict="PAPER_OBSERVATION_PERFORMANCE_READY_SHADOW_ONLY",
    safety_breach_count=0,
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
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
            run_label,
            f"{run_label}-report",
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
            net_bps,
            max_position_loss_bps,
            fee_drag_bps,
            "0",
            alert_count,
            safety_breach_count,
            "PAPER_OBSERVATION_HEALTH_STABLE_BASELINE",
            performance_decision,
            global_verdict,
            "CONTINUE_PAPER_OBSERVATION_AND_COLLECT_MORE_SNAPSHOTS",
            "Mission 67 Paper Drawdown Kill Switch",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )


def insert_snapshot(
    conn,
    snapshot_id,
    run_label="run-1",
    symbol="BTCUSDT",
    strategy_id="S1",
    notional="25000",
    net_pnl="-5",
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
            run_label,
            "2026-01-01T00:00:00+00:00",
            "session-1",
            f"position-{snapshot_id}",
            symbol,
            strategy_id,
            "1",
            "100",
            "100",
            notional,
            "0",
            "5",
            net_pnl,
            net_bps,
            "PAPER_POSITION_SNAPSHOT_LOSS",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def insert_alert(conn, alert_id="alert-1", run_label="run-1"):
    conn.execute(
        """
        INSERT INTO paper_observation_performance_alerts (
            alert_id,
            run_label,
            created_at,
            source_capital_review_label,
            alert_type,
            alert_status,
            observed_value,
            threshold_value,
            alert_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alert_id,
            run_label,
            "2026-01-01T00:00:00+00:00",
            "capital-1",
            "net_loss_bps_limit",
            "PERFORMANCE_ALERT_TRIGGERED",
            "-60",
            ">= -50",
            "test alert",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def seed_good_run(conn):
    create_performance_tables(conn)
    insert_run(conn)
    insert_snapshot(conn, "s1", symbol="BTCUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", notional="35000", net_pnl="-7")
    insert_snapshot(conn, "s2", symbol="ETHUSDT", strategy_id="BASIS_MEAN_REVERSION", notional="25352", net_pnl="-5.0704")
    insert_snapshot(conn, "s3", symbol="BTCUSDT", strategy_id="VOLATILITY_REGIME_FILTER", notional="24648", net_pnl="-4.9296")
    insert_snapshot(conn, "s4", symbol="ETHUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", notional="15000", net_pnl="-3")


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_kill_switch_arms_good_run_and_persists(tmp_path):
    db_path = tmp_path / "mission67.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_run(conn)
        conn.commit()

    result = run_paper_drawdown_kill_switch(
        db_path=db_path,
        review_label="review-1",
        report_label="report-1",
        performance_run_label="run-1",
    )

    assert result["kill_switch_decision"] == DECISION_ARMED
    assert result["global_verdict"] == VERDICT_ARMED
    assert result["kill_switch_state"] == "KILL_SWITCH_STATE_ARMED_NOT_TRIGGERED"
    assert result["check_count"] == 8
    assert result["pass_check_count"] == 8
    assert result["fail_check_count"] == 0
    assert result["triggered_event_count"] == 0
    assert result["safety_breach_count"] == 0

    with sqlite3.connect(db_path) as conn:
        review = conn.execute(
            """
            SELECT review_label, kill_switch_decision, global_verdict
            FROM paper_drawdown_kill_switch_reviews
            WHERE review_label = ?
            """,
            ("review-1",),
        ).fetchone()

        checks = conn.execute(
            """
            SELECT COUNT(*)
            FROM paper_drawdown_kill_switch_checks
            WHERE review_label = ?
            """,
            ("review-1",),
        ).fetchone()[0]

        events = conn.execute(
            """
            SELECT COUNT(*)
            FROM paper_drawdown_kill_switch_events
            WHERE review_label = ?
            """,
            ("review-1",),
        ).fetchone()[0]

    assert review == ("review-1", DECISION_ARMED, VERDICT_ARMED)
    assert checks == 8
    assert events == 1


def test_kill_switch_rejects_missing_run(tmp_path):
    db_path = tmp_path / "mission67-missing.db"

    result = run_paper_drawdown_kill_switch(
        db_path=db_path,
        review_label="missing-review",
        report_label="missing-report",
        performance_run_label="missing-run",
    )

    assert result["kill_switch_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_kill_switch_triggers_on_net_drawdown(tmp_path):
    db_path = tmp_path / "mission67-net.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_run(conn)
        conn.execute(
            """
            UPDATE paper_observation_performance_runs
            SET net_paper_pnl_bps = ?, net_paper_pnl = ?
            WHERE run_label = ?
            """,
            ("-80", "-800", "run-1"),
        )
        conn.commit()

    result = run_paper_drawdown_kill_switch(
        db_path=db_path,
        review_label="net-review",
        report_label="net-report",
        performance_run_label="run-1",
        max_allowed_net_drawdown_bps=50,
    )

    assert result["kill_switch_decision"] == DECISION_TRIGGERED
    assert result["global_verdict"] == VERDICT_TRIGGERED
    assert result["fail_check_count"] >= 1
    assert result["triggered_event_count"] >= 1


def test_kill_switch_triggers_on_position_drawdown(tmp_path):
    db_path = tmp_path / "mission67-position.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_run(conn)
        conn.execute(
            """
            UPDATE paper_observation_performance_runs
            SET max_position_loss_bps = ?
            WHERE run_label = ?
            """,
            ("-100", "run-1"),
        )
        conn.commit()

    result = run_paper_drawdown_kill_switch(
        db_path=db_path,
        review_label="position-review",
        report_label="position-report",
        performance_run_label="run-1",
        max_allowed_position_drawdown_bps=75,
    )

    assert result["kill_switch_decision"] == DECISION_TRIGGERED
    assert result["global_verdict"] == VERDICT_TRIGGERED


def test_kill_switch_triggers_on_alert_count(tmp_path):
    db_path = tmp_path / "mission67-alert.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_run(conn)
        insert_alert(conn)
        conn.execute(
            """
            UPDATE paper_observation_performance_runs
            SET alert_count = ?
            WHERE run_label = ?
            """,
            (1, "run-1"),
        )
        conn.commit()

    result = run_paper_drawdown_kill_switch(
        db_path=db_path,
        review_label="alert-review",
        report_label="alert-report",
        performance_run_label="run-1",
        max_allowed_alert_count=0,
    )

    assert result["kill_switch_decision"] == DECISION_TRIGGERED
    assert result["global_verdict"] == VERDICT_TRIGGERED


def test_kill_switch_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission67-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_performance_tables(conn)
        insert_run(conn, safety_breach_count=1, live_trading="ENABLED")
        insert_snapshot(conn, "safety-snapshot", live_trading="ENABLED")
        conn.commit()

    result = run_paper_drawdown_kill_switch(
        db_path=db_path,
        review_label="safety-review",
        report_label="safety-report",
        performance_run_label="run-1",
    )

    assert result["kill_switch_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED
    assert result["safety_breach_count"] >= 1


def test_markdown_report_contains_no_live_execution_scope(tmp_path):
    db_path = tmp_path / "mission67-markdown.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_run(conn)
        conn.commit()

    result = run_paper_drawdown_kill_switch(
        db_path=db_path,
        review_label="markdown-review",
        report_label="markdown-report",
        performance_run_label="run-1",
    )

    assert "# DeltaGrid Mission 67" in result["markdown_report"]
    assert "The kill switch is paper-only and cannot send live orders." in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]
