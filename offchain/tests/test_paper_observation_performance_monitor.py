import sqlite3

from offchain.performance.paper_observation_performance_monitor import (
    PERFORMANCE_BLOCKED,
    PERFORMANCE_DECISION_BLOCK_LOSS,
    PERFORMANCE_DECISION_BLOCK_READINESS,
    PERFORMANCE_DECISION_BLOCK_SAFETY,
    PERFORMANCE_DECISION_CONTINUE,
    PERFORMANCE_DECISION_REJECT_MISSING,
    PERFORMANCE_MISSING,
    PERFORMANCE_READY,
    parse_symbols,
    run_paper_observation_performance_monitor,
)


def create_capital_and_paper_tables(conn):
    conn.execute(
        """
        CREATE TABLE capital_readiness_reviews (
            review_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_risk_review_label TEXT NOT NULL,
            source_session_label TEXT,
            source_board_review_label TEXT,
            source_portfolio_label TEXT,
            evidence_item_count INTEGER NOT NULL,
            pass_evidence_count INTEGER NOT NULL,
            warn_evidence_count INTEGER NOT NULL,
            fail_evidence_count INTEGER NOT NULL,
            paper_notional TEXT NOT NULL,
            position_count INTEGER NOT NULL,
            order_count INTEGER NOT NULL,
            distinct_symbol_count INTEGER NOT NULL,
            distinct_strategy_count INTEGER NOT NULL,
            observed_max_symbol_exposure_pct TEXT NOT NULL,
            observed_max_strategy_exposure_pct TEXT NOT NULL,
            total_cost_bps TEXT NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            institutional_risk_level TEXT NOT NULL,
            capital_readiness_level TEXT NOT NULL,
            capital_decision TEXT NOT NULL,
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
        CREATE TABLE capital_readiness_decision_records (
            decision_id TEXT PRIMARY KEY,
            review_label TEXT NOT NULL,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_risk_review_label TEXT NOT NULL,
            capital_decision TEXT NOT NULL,
            global_verdict TEXT NOT NULL,
            recommended_action TEXT NOT NULL,
            approval_scope TEXT NOT NULL,
            explicit_non_approval_scope TEXT NOT NULL,
            decision_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE paper_sandbox_sessions (
            session_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_board_review_label TEXT NOT NULL,
            source_portfolio_label TEXT,
            paper_notional TEXT NOT NULL,
            requested_symbol_count INTEGER NOT NULL,
            source_allocation_count INTEGER NOT NULL,
            submitted_order_count INTEGER NOT NULL,
            filled_order_count INTEGER NOT NULL,
            blocked_order_count INTEGER NOT NULL,
            position_count INTEGER NOT NULL,
            total_paper_order_notional TEXT NOT NULL,
            total_simulated_fees TEXT NOT NULL,
            total_simulated_slippage TEXT NOT NULL,
            net_paper_deployed_notional TEXT NOT NULL,
            weighted_average_fill_price TEXT NOT NULL,
            safety_breach_count INTEGER NOT NULL,
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
        CREATE TABLE paper_sandbox_orders (
            order_id TEXT PRIMARY KEY,
            session_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_board_review_label TEXT NOT NULL,
            source_portfolio_label TEXT,
            source_allocation_id TEXT,
            strategy_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            paper_order_side TEXT NOT NULL,
            paper_order_type TEXT NOT NULL,
            paper_order_status TEXT NOT NULL,
            allocation_weight TEXT NOT NULL,
            requested_notional TEXT NOT NULL,
            reference_price TEXT NOT NULL,
            simulated_quantity TEXT NOT NULL,
            simulated_slippage_bps TEXT NOT NULL,
            simulated_fee_bps TEXT NOT NULL,
            simulated_fee_amount TEXT NOT NULL,
            paper_execution_venue TEXT NOT NULL,
            order_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE paper_sandbox_positions (
            position_id TEXT PRIMARY KEY,
            session_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            position_status TEXT NOT NULL,
            paper_side TEXT NOT NULL,
            quantity TEXT NOT NULL,
            entry_price TEXT NOT NULL,
            entry_notional TEXT NOT NULL,
            allocation_weight TEXT NOT NULL,
            simulated_fee_amount TEXT NOT NULL,
            unrealized_paper_pnl TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_capital_review(
    conn,
    review_label="capital-1",
    session_label="session-1",
    capital_decision="CAPITAL_READINESS_APPROVED_FOR_EXTENDED_PAPER_OBSERVATION_ONLY",
    global_verdict="CAPITAL_READINESS_REVIEW_PAPER_ONLY_READY",
    recommended_action="CONTINUE_EXTENDED_PAPER_OBSERVATION_ONLY",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO capital_readiness_reviews (
            review_label,
            report_label,
            created_at,
            source_risk_review_label,
            source_session_label,
            source_board_review_label,
            source_portfolio_label,
            evidence_item_count,
            pass_evidence_count,
            warn_evidence_count,
            fail_evidence_count,
            paper_notional,
            position_count,
            order_count,
            distinct_symbol_count,
            distinct_strategy_count,
            observed_max_symbol_exposure_pct,
            observed_max_strategy_exposure_pct,
            total_cost_bps,
            safety_breach_count,
            institutional_risk_level,
            capital_readiness_level,
            capital_decision,
            global_verdict,
            recommended_action,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_label,
            f"{review_label}-report",
            "2026-01-01T00:00:00+00:00",
            "risk-1",
            session_label,
            "board-1",
            "portfolio-1",
            12,
            12,
            0,
            0,
            "100000",
            4,
            4,
            2,
            3,
            "59.647996",
            "50.0",
            "3.5",
            0,
            "INSTITUTIONAL_RISK_LEVEL_MODERATE",
            "CAPITAL_READINESS_LEVEL_EARLY_PAPER_ONLY",
            capital_decision,
            global_verdict,
            recommended_action,
            "Mission 66 Paper Observation Performance Monitor",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )

    conn.execute(
        """
        INSERT INTO capital_readiness_decision_records (
            decision_id,
            review_label,
            report_label,
            created_at,
            source_risk_review_label,
            capital_decision,
            global_verdict,
            recommended_action,
            approval_scope,
            explicit_non_approval_scope,
            decision_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{review_label}-decision",
            review_label,
            f"{review_label}-report",
            "2026-01-01T00:00:00+00:00",
            "risk-1",
            capital_decision,
            global_verdict,
            recommended_action,
            "EXTENDED_PAPER_OBSERVATION_ONLY",
            "NOT_LIVE_TRADING_NOT_REAL_CAPITAL",
            "test",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def insert_session(
    conn,
    session_label="session-1",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO paper_sandbox_sessions (
            session_label,
            report_label,
            created_at,
            source_board_review_label,
            source_portfolio_label,
            paper_notional,
            requested_symbol_count,
            source_allocation_count,
            submitted_order_count,
            filled_order_count,
            blocked_order_count,
            position_count,
            total_paper_order_notional,
            total_simulated_fees,
            total_simulated_slippage,
            net_paper_deployed_notional,
            weighted_average_fill_price,
            safety_breach_count,
            global_verdict,
            recommended_action,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_label,
            f"{session_label}-report",
            "2026-01-01T00:00:00+00:00",
            "board-1",
            "portfolio-1",
            "100000",
            3,
            4,
            4,
            4,
            0,
            4,
            "100000",
            "20",
            "15",
            "100035",
            "4000",
            0,
            "PAPER_SANDBOX_READY_SHADOW_ONLY",
            "RUN_PAPER_SANDBOX_OBSERVATION_CYCLE",
            "Mission 64 Institutional Risk Control Layer",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )


def insert_order(conn, order_id, session_label="session-1", symbol="BTCUSDT", strategy_id="S1"):
    conn.execute(
        """
        INSERT INTO paper_sandbox_orders (
            order_id,
            session_label,
            created_at,
            source_board_review_label,
            source_portfolio_label,
            source_allocation_id,
            strategy_id,
            symbol,
            paper_order_side,
            paper_order_type,
            paper_order_status,
            allocation_weight,
            requested_notional,
            reference_price,
            simulated_quantity,
            simulated_slippage_bps,
            simulated_fee_bps,
            simulated_fee_amount,
            paper_execution_venue,
            order_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id,
            session_label,
            "2026-01-01T00:00:00+00:00",
            "board-1",
            "portfolio-1",
            f"allocation-{order_id}",
            strategy_id,
            symbol,
            "PAPER_BUY",
            "PAPER_MARKET_SIMULATION",
            "PAPER_ORDER_FILLED",
            "0.25",
            "25000",
            "100",
            "1",
            "1.5",
            "2.0",
            "5",
            "LOCAL_PAPER_SANDBOX_ONLY",
            "test",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def insert_position(
    conn,
    position_id,
    session_label="session-1",
    symbol="BTCUSDT",
    strategy_id="S1",
    notional="25000",
    entry_price="100",
    quantity="250",
    fee="5",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO paper_sandbox_positions (
            position_id,
            session_label,
            created_at,
            symbol,
            strategy_id,
            position_status,
            paper_side,
            quantity,
            entry_price,
            entry_notional,
            allocation_weight,
            simulated_fee_amount,
            unrealized_paper_pnl,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            position_id,
            session_label,
            "2026-01-01T00:00:00+00:00",
            symbol,
            strategy_id,
            "PAPER_POSITION_OPEN",
            "PAPER_BUY",
            quantity,
            entry_price,
            notional,
            "0.25",
            fee,
            "0",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def seed_good_monitor(conn):
    create_capital_and_paper_tables(conn)
    insert_capital_review(conn)
    insert_session(conn)
    insert_order(conn, "o1", symbol="BTCUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH")
    insert_order(conn, "o2", symbol="ETHUSDT", strategy_id="BASIS_MEAN_REVERSION")
    insert_order(conn, "o3", symbol="BTCUSDT", strategy_id="VOLATILITY_REGIME_FILTER")
    insert_order(conn, "o4", symbol="ETHUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH")
    insert_position(conn, "p1", symbol="BTCUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", notional="35000", entry_price="100", quantity="350", fee="7")
    insert_position(conn, "p2", symbol="ETHUSDT", strategy_id="BASIS_MEAN_REVERSION", notional="25352", entry_price="100", quantity="253.52", fee="5.0704")
    insert_position(conn, "p3", symbol="BTCUSDT", strategy_id="VOLATILITY_REGIME_FILTER", notional="24648", entry_price="100", quantity="246.48", fee="4.9296")
    insert_position(conn, "p4", symbol="ETHUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", notional="15000", entry_price="100", quantity="150", fee="3")


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_monitor_continues_good_paper_observation_and_persists(tmp_path):
    db_path = tmp_path / "mission66.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_monitor(conn)
        conn.commit()

    result = run_paper_observation_performance_monitor(
        db_path=db_path,
        run_label="run-1",
        report_label="report-1",
        capital_review_label="capital-1",
    )

    assert result["performance_decision"] == PERFORMANCE_DECISION_CONTINUE
    assert result["global_verdict"] == PERFORMANCE_READY
    assert result["monitored_position_count"] == 4
    assert result["order_count"] == 4
    assert result["gross_unrealized_paper_pnl"] == 0
    assert result["total_simulated_fees"] == 20
    assert result["net_paper_pnl"] == -20
    assert result["net_paper_pnl_bps"] == -2
    assert result["fee_drag_bps"] == 2
    assert result["alert_count"] == 0
    assert result["safety_breach_count"] == 0

    with sqlite3.connect(db_path) as conn:
        run = conn.execute(
            """
            SELECT run_label, performance_decision, global_verdict
            FROM paper_observation_performance_runs
            WHERE run_label = ?
            """,
            ("run-1",),
        ).fetchone()

        snapshots = conn.execute(
            """
            SELECT COUNT(*)
            FROM paper_observation_position_snapshots
            WHERE run_label = ?
            """,
            ("run-1",),
        ).fetchone()[0]

    assert run == ("run-1", PERFORMANCE_DECISION_CONTINUE, PERFORMANCE_READY)
    assert snapshots == 4


def test_monitor_rejects_missing_capital_review(tmp_path):
    db_path = tmp_path / "mission66-missing.db"

    result = run_paper_observation_performance_monitor(
        db_path=db_path,
        run_label="missing-run",
        report_label="missing-report",
        capital_review_label="missing-capital",
    )

    assert result["performance_decision"] == PERFORMANCE_DECISION_REJECT_MISSING
    assert result["global_verdict"] == PERFORMANCE_MISSING


def test_monitor_blocks_unapproved_capital_review(tmp_path):
    db_path = tmp_path / "mission66-unapproved.db"

    with sqlite3.connect(db_path) as conn:
        create_capital_and_paper_tables(conn)
        insert_capital_review(
            conn,
            capital_decision="CAPITAL_READINESS_BLOCKED_BY_RISK_CONTROL",
            global_verdict="CAPITAL_READINESS_REVIEW_BLOCKED",
            recommended_action="REMEDIATE_RISK_AND_RERUN_CONTROL_LAYER",
        )
        insert_session(conn)
        conn.commit()

    result = run_paper_observation_performance_monitor(
        db_path=db_path,
        run_label="unapproved-run",
        report_label="unapproved-report",
        capital_review_label="capital-1",
    )

    assert result["performance_decision"] == PERFORMANCE_DECISION_BLOCK_READINESS
    assert result["global_verdict"] == PERFORMANCE_BLOCKED
    assert result["alert_count"] >= 1


def test_monitor_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission66-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_capital_and_paper_tables(conn)
        insert_capital_review(conn, live_trading="ENABLED")
        insert_session(conn, live_trading="ENABLED")
        insert_position(conn, "p1", live_trading="ENABLED")
        conn.commit()

    result = run_paper_observation_performance_monitor(
        db_path=db_path,
        run_label="safety-run",
        report_label="safety-report",
        capital_review_label="capital-1",
    )

    assert result["performance_decision"] == PERFORMANCE_DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == PERFORMANCE_BLOCKED
    assert result["safety_breach_count"] >= 1


def test_monitor_blocks_loss_threshold_breach(tmp_path):
    db_path = tmp_path / "mission66-loss.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_monitor(conn)
        conn.commit()

    result = run_paper_observation_performance_monitor(
        db_path=db_path,
        run_label="loss-run",
        report_label="loss-report",
        capital_review_label="capital-1",
        price_shock_bps=-100,
        max_allowed_net_loss_bps=50,
        max_allowed_position_loss_bps=75,
    )

    assert result["performance_decision"] == PERFORMANCE_DECISION_BLOCK_LOSS
    assert result["global_verdict"] == PERFORMANCE_BLOCKED
    assert result["net_paper_pnl_bps"] < -50


def test_monitor_rejects_no_positions(tmp_path):
    db_path = tmp_path / "mission66-empty.db"

    with sqlite3.connect(db_path) as conn:
        create_capital_and_paper_tables(conn)
        insert_capital_review(conn)
        insert_session(conn)
        conn.commit()

    result = run_paper_observation_performance_monitor(
        db_path=db_path,
        run_label="empty-run",
        report_label="empty-report",
        capital_review_label="capital-1",
    )

    assert result["performance_decision"] == PERFORMANCE_DECISION_REJECT_MISSING
    assert result["global_verdict"] == PERFORMANCE_MISSING


def test_markdown_report_contains_paper_only_scope(tmp_path):
    db_path = tmp_path / "mission66-markdown.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_monitor(conn)
        conn.commit()

    result = run_paper_observation_performance_monitor(
        db_path=db_path,
        run_label="markdown-run",
        report_label="markdown-report",
        capital_review_label="capital-1",
    )

    assert "# DeltaGrid Mission 66" in result["markdown_report"]
    assert "All monitoring is paper-only local analytics." in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]
