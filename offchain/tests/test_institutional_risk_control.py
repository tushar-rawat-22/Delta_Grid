import sqlite3

from offchain.risk.institutional_risk_control import (
    RISK_BLOCKED,
    RISK_DECISION_APPROVED,
    RISK_DECISION_BLOCK_LIMITS,
    RISK_DECISION_BLOCK_SAFETY,
    RISK_DECISION_REJECT_MISSING,
    RISK_MISSING,
    RISK_READY,
    parse_symbols,
    run_institutional_risk_control,
)


def create_paper_tables(conn):
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


def insert_session(
    conn,
    session_label="session-1",
    paper_notional="100000",
    submitted=4,
    filled=4,
    blocked=0,
    position_count=4,
    fees="20",
    slippage="15",
    net_deployed="100035",
    global_verdict="PAPER_SANDBOX_READY_SHADOW_ONLY",
    safety_breach_count=0,
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
            paper_notional,
            3,
            4,
            submitted,
            filled,
            blocked,
            position_count,
            paper_notional,
            fees,
            slippage,
            net_deployed,
            "4000",
            safety_breach_count,
            global_verdict,
            "RUN_PAPER_SANDBOX_OBSERVATION_CYCLE",
            "Mission 64 Institutional Risk Control Layer",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )


def insert_order(
    conn,
    order_id,
    session_label="session-1",
    symbol="BTCUSDT",
    strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH",
    notional="35000",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
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
            "0.35",
            notional,
            "100",
            "1",
            "1.5",
            "2.0",
            "1",
            "LOCAL_PAPER_SANDBOX_ONLY",
            "test",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def insert_position(
    conn,
    position_id,
    session_label="session-1",
    symbol="BTCUSDT",
    strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH",
    notional="35000",
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
            "1",
            "100",
            notional,
            "0.35",
            "1",
            "0",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def seed_good_session(conn):
    create_paper_tables(conn)
    insert_session(conn)
    insert_order(conn, "o1", symbol="BTCUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", notional="35000")
    insert_order(conn, "o2", symbol="ETHUSDT", strategy_id="BASIS_MEAN_REVERSION", notional="25352")
    insert_order(conn, "o3", symbol="BTCUSDT", strategy_id="VOLATILITY_REGIME_FILTER", notional="24648")
    insert_order(conn, "o4", symbol="ETHUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", notional="15000")
    insert_position(conn, "p1", symbol="BTCUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", notional="35000")
    insert_position(conn, "p2", symbol="ETHUSDT", strategy_id="BASIS_MEAN_REVERSION", notional="25352")
    insert_position(conn, "p3", symbol="BTCUSDT", strategy_id="VOLATILITY_REGIME_FILTER", notional="24648")
    insert_position(conn, "p4", symbol="ETHUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", notional="15000")


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_risk_control_approves_good_session_and_persists(tmp_path):
    db_path = tmp_path / "mission64.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_session(conn)
        conn.commit()

    result = run_institutional_risk_control(
        db_path=db_path,
        review_label="risk-review-1",
        report_label="risk-report-1",
        session_label="session-1",
    )

    assert result["risk_decision"] == RISK_DECISION_APPROVED
    assert result["global_verdict"] == RISK_READY
    assert result["fail_limit_count"] == 0
    assert result["pass_limit_count"] == 9
    assert result["safety_breach_count"] == 0
    assert result["observed_max_symbol_exposure_pct"] <= 60
    assert result["observed_max_strategy_exposure_pct"] <= 50

    with sqlite3.connect(db_path) as conn:
        review = conn.execute(
            """
            SELECT review_label, risk_decision, global_verdict
            FROM institutional_risk_control_reviews
            WHERE review_label = ?
            """,
            ("risk-review-1",),
        ).fetchone()

        checks = conn.execute(
            """
            SELECT COUNT(*)
            FROM institutional_risk_limit_checks
            WHERE review_label = ?
            """,
            ("risk-review-1",),
        ).fetchone()[0]

    assert review == ("risk-review-1", RISK_DECISION_APPROVED, RISK_READY)
    assert checks == 9


def test_risk_control_blocks_missing_session(tmp_path):
    db_path = tmp_path / "mission64-missing.db"

    result = run_institutional_risk_control(
        db_path=db_path,
        review_label="missing-review",
        report_label="missing-report",
        session_label="missing-session",
    )

    assert result["risk_decision"] == RISK_DECISION_REJECT_MISSING
    assert result["global_verdict"] == RISK_MISSING
    assert result["fail_limit_count"] == 1


def test_risk_control_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission64-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_paper_tables(conn)
        insert_session(conn, live_trading="ENABLED", safety_breach_count=1)
        insert_order(conn, "o1", live_trading="ENABLED")
        insert_position(conn, "p1", live_trading="ENABLED")
        conn.commit()

    result = run_institutional_risk_control(
        db_path=db_path,
        review_label="safety-review",
        report_label="safety-report",
        session_label="session-1",
    )

    assert result["risk_decision"] == RISK_DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == RISK_BLOCKED
    assert result["safety_breach_count"] >= 1


def test_risk_control_blocks_high_symbol_exposure(tmp_path):
    db_path = tmp_path / "mission64-symbol.db"

    with sqlite3.connect(db_path) as conn:
        create_paper_tables(conn)
        insert_session(conn, position_count=3)
        insert_order(conn, "o1", symbol="BTCUSDT", strategy_id="S1", notional="90000")
        insert_order(conn, "o2", symbol="ETHUSDT", strategy_id="S2", notional="10000")
        insert_order(conn, "o3", symbol="ETHUSDT", strategy_id="S3", notional="0")
        insert_position(conn, "p1", symbol="BTCUSDT", strategy_id="S1", notional="90000")
        insert_position(conn, "p2", symbol="ETHUSDT", strategy_id="S2", notional="10000")
        insert_position(conn, "p3", symbol="ETHUSDT", strategy_id="S3", notional="0")
        conn.commit()

    result = run_institutional_risk_control(
        db_path=db_path,
        review_label="symbol-review",
        report_label="symbol-report",
        session_label="session-1",
        max_symbol_exposure_pct=60,
    )

    assert result["risk_decision"] == RISK_DECISION_BLOCK_LIMITS
    assert result["global_verdict"] == RISK_BLOCKED
    assert result["observed_max_symbol_exposure_pct"] == 90.0


def test_risk_control_blocks_excess_cost(tmp_path):
    db_path = tmp_path / "mission64-cost.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_session(conn)
        conn.execute(
            """
            UPDATE paper_sandbox_sessions
            SET total_simulated_fees = ?, total_simulated_slippage = ?, net_paper_deployed_notional = ?
            WHERE session_label = ?
            """,
            ("100", "100", "100200", "session-1"),
        )
        conn.commit()

    result = run_institutional_risk_control(
        db_path=db_path,
        review_label="cost-review",
        report_label="cost-report",
        session_label="session-1",
        max_total_cost_bps=10,
    )

    assert result["risk_decision"] == RISK_DECISION_BLOCK_LIMITS
    assert result["global_verdict"] == RISK_BLOCKED
    assert result["total_cost_bps"] == 20.0


def test_markdown_report_contains_non_live_trading_scope(tmp_path):
    db_path = tmp_path / "mission64-markdown.db"

    with sqlite3.connect(db_path) as conn:
        seed_good_session(conn)
        conn.commit()

    result = run_institutional_risk_control(
        db_path=db_path,
        review_label="markdown-review",
        report_label="markdown-report",
        session_label="session-1",
    )

    assert "# DeltaGrid Mission 64" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "Approval scope, if approved, is controlled paper observation only." in result["markdown_report"]
