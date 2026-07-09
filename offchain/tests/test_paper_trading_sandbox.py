import sqlite3

from offchain.paper_sandbox.paper_trading_sandbox import (
    SESSION_BLOCKED_BOARD,
    SESSION_BLOCKED_SAFETY,
    SESSION_NO_ALLOCATIONS,
    SESSION_READY,
    parse_symbols,
    run_paper_trading_sandbox,
)


def create_board_and_allocation_tables(conn):
    conn.execute(
        """
        CREATE TABLE research_promotion_board_reviews (
            review_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_portfolio_label TEXT NOT NULL,
            source_regime_label TEXT,
            evidence_item_count INTEGER NOT NULL,
            pass_evidence_count INTEGER NOT NULL,
            warn_evidence_count INTEGER NOT NULL,
            fail_evidence_count INTEGER NOT NULL,
            included_allocation_count INTEGER NOT NULL,
            excluded_candidate_count INTEGER NOT NULL,
            weighted_alpha_score TEXT NOT NULL,
            concentration_score TEXT NOT NULL,
            estimated_shadow_drawdown_pct TEXT NOT NULL,
            portfolio_risk_rating TEXT NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            board_decision TEXT NOT NULL,
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
        CREATE TABLE research_promotion_board_decision_records (
            decision_id TEXT PRIMARY KEY,
            review_label TEXT NOT NULL,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_portfolio_label TEXT NOT NULL,
            board_decision TEXT NOT NULL,
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
        CREATE TABLE shadow_portfolio_allocations (
            allocation_id TEXT PRIMARY KEY,
            portfolio_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_regime_label TEXT NOT NULL,
            source_gate_id TEXT NOT NULL,
            source_candidate_id TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            candidate_status TEXT NOT NULL,
            candidate_gate_status TEXT NOT NULL,
            allocation_status TEXT NOT NULL,
            allocation_reason TEXT NOT NULL,
            promotion_eligible INTEGER NOT NULL,
            alpha_score TEXT NOT NULL,
            data_quality_score TEXT NOT NULL,
            market_risk_state TEXT NOT NULL,
            raw_score TEXT NOT NULL,
            allocation_weight TEXT NOT NULL,
            allocation_notional TEXT NOT NULL,
            expected_alpha_contribution TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def create_basis_table(conn):
    conn.execute(
        """
        CREATE TABLE historical_public_basis_observations (
            basis_id TEXT PRIMARY KEY,
            dataset_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            source_snapshot_id TEXT,
            source_ingestion_label TEXT,
            source TEXT NOT NULL,
            data_mode TEXT NOT NULL,
            mark_price TEXT NOT NULL,
            index_price TEXT NOT NULL,
            basis_bps TEXT NOT NULL,
            spread_bps TEXT NOT NULL,
            quote_volume TEXT NOT NULL,
            last_funding_rate TEXT NOT NULL,
            annualized_funding_rate TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            raw_payload_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_board(
    conn,
    review_label="review-1",
    portfolio_label="portfolio-1",
    board_decision="RESEARCH_BOARD_APPROVED_FOR_PAPER_SANDBOX_SHADOW_ONLY",
    global_verdict="RESEARCH_PROMOTION_BOARD_REVIEW_READY",
    recommended_action="OPEN_PAPER_SANDBOX_RESEARCH_ONLY",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO research_promotion_board_reviews (
            review_label,
            report_label,
            created_at,
            source_portfolio_label,
            source_regime_label,
            evidence_item_count,
            pass_evidence_count,
            warn_evidence_count,
            fail_evidence_count,
            included_allocation_count,
            excluded_candidate_count,
            weighted_alpha_score,
            concentration_score,
            estimated_shadow_drawdown_pct,
            portfolio_risk_rating,
            safety_breach_count,
            board_decision,
            global_verdict,
            recommended_action,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_label,
            f"{review_label}-report",
            "2026-01-01T00:00:00+00:00",
            portfolio_label,
            "regime-1",
            9,
            9,
            0,
            0,
            4,
            11,
            "82",
            "59",
            "5.5",
            "PORTFOLIO_RISK_MODERATE",
            0,
            board_decision,
            global_verdict,
            recommended_action,
            "Mission 63: Paper Trading Sandbox",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )

    conn.execute(
        """
        INSERT INTO research_promotion_board_decision_records (
            decision_id,
            review_label,
            report_label,
            created_at,
            source_portfolio_label,
            board_decision,
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
            portfolio_label,
            board_decision,
            global_verdict,
            recommended_action,
            "PAPER_SANDBOX_RESEARCH_ONLY",
            "NOT_LIVE_TRADING_NOT_REAL_CAPITAL",
            "test",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def insert_allocation(
    conn,
    allocation_id,
    portfolio_label="portfolio-1",
    symbol="BTCUSDT",
    strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH",
    weight="0.35",
    status="PORTFOLIO_ALLOCATION_INCLUDED_SHADOW_ONLY",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO shadow_portfolio_allocations (
            allocation_id,
            portfolio_label,
            created_at,
            source_regime_label,
            source_gate_id,
            source_candidate_id,
            strategy_id,
            symbol,
            candidate_status,
            candidate_gate_status,
            allocation_status,
            allocation_reason,
            promotion_eligible,
            alpha_score,
            data_quality_score,
            market_risk_state,
            raw_score,
            allocation_weight,
            allocation_notional,
            expected_alpha_contribution,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            allocation_id,
            portfolio_label,
            "2026-01-01T00:00:00+00:00",
            "regime-1",
            f"gate-{allocation_id}",
            f"candidate-{allocation_id}",
            strategy_id,
            symbol,
            "STRATEGY_CANDIDATE_PROMOTION_SHORTLIST_SHADOW_ONLY",
            "CANDIDATE_GATE_PASS_RESEARCH_REVIEW",
            status,
            "test",
            1,
            "80",
            "95",
            "MARKET_RISK_STATE_NORMAL",
            "76",
            weight,
            str(float(weight) * 100000),
            "20",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def insert_basis_price(conn, symbol="BTCUSDT", price="100000"):
    conn.execute(
        """
        INSERT INTO historical_public_basis_observations (
            basis_id,
            dataset_label,
            created_at,
            symbol,
            source_snapshot_id,
            source_ingestion_label,
            source,
            data_mode,
            mark_price,
            index_price,
            basis_bps,
            spread_bps,
            quote_volume,
            last_funding_rate,
            annualized_funding_rate,
            live_trading,
            live_order_sent,
            capital_deployment,
            raw_payload_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"basis-{symbol}",
            "dataset-1",
            "2026-01-01T00:00:00+00:00",
            symbol,
            None,
            None,
            "test",
            "ONLINE_PUBLIC_API",
            price,
            price,
            "0",
            "0.1",
            "1000000",
            "0",
            "0",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
            "{}",
        ),
    )


def seed_approved_sandbox(conn):
    create_board_and_allocation_tables(conn)
    create_basis_table(conn)
    insert_board(conn)
    insert_allocation(conn, "a1", symbol="BTCUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", weight="0.35")
    insert_allocation(conn, "a2", symbol="ETHUSDT", strategy_id="BASIS_MEAN_REVERSION", weight="0.25")
    insert_allocation(conn, "a3", symbol="BTCUSDT", strategy_id="VOLATILITY_REGIME_FILTER", weight="0.25")
    insert_allocation(conn, "a4", symbol="ETHUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH", weight="0.15")
    insert_basis_price(conn, "BTCUSDT", "100000")
    insert_basis_price(conn, "ETHUSDT", "4000")


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_paper_sandbox_creates_orders_fills_positions_and_persists(tmp_path):
    db_path = tmp_path / "mission63.db"

    with sqlite3.connect(db_path) as conn:
        seed_approved_sandbox(conn)
        conn.commit()

    result = run_paper_trading_sandbox(
        db_path=db_path,
        session_label="session-1",
        report_label="report-1",
        board_review_label="review-1",
        reference_dataset_label="dataset-1",
        paper_notional=100000,
    )

    assert result["global_verdict"] == SESSION_READY
    assert result["source_allocation_count"] == 4
    assert result["submitted_order_count"] == 4
    assert result["filled_order_count"] == 4
    assert result["position_count"] == 4
    assert result["total_paper_order_notional"] == 100000
    assert result["safety_breach_count"] == 0
    assert result["live_trading"] == "DISABLED"
    assert result["capital_deployment"] == "BLOCKED"

    with sqlite3.connect(db_path) as conn:
        order_count = conn.execute(
            "SELECT COUNT(*) FROM paper_sandbox_orders WHERE session_label = ?",
            ("session-1",),
        ).fetchone()[0]
        fill_count = conn.execute(
            "SELECT COUNT(*) FROM paper_sandbox_fills WHERE session_label = ?",
            ("session-1",),
        ).fetchone()[0]
        position_count = conn.execute(
            "SELECT COUNT(*) FROM paper_sandbox_positions WHERE session_label = ?",
            ("session-1",),
        ).fetchone()[0]
        session = conn.execute(
            """
            SELECT session_label, global_verdict, live_trading, capital_deployment
            FROM paper_sandbox_sessions
            WHERE session_label = ?
            """,
            ("session-1",),
        ).fetchone()

    assert order_count == 4
    assert fill_count == 4
    assert position_count == 4
    assert session == ("session-1", SESSION_READY, "DISABLED", "BLOCKED")


def test_paper_sandbox_blocks_missing_board(tmp_path):
    db_path = tmp_path / "mission63-missing.db"

    result = run_paper_trading_sandbox(
        db_path=db_path,
        session_label="missing-session",
        report_label="missing-report",
        board_review_label="missing-board",
    )

    assert result["global_verdict"] == SESSION_BLOCKED_BOARD
    assert result["submitted_order_count"] == 0
    assert result["position_count"] == 0


def test_paper_sandbox_blocks_unapproved_board(tmp_path):
    db_path = tmp_path / "mission63-unapproved.db"

    with sqlite3.connect(db_path) as conn:
        create_board_and_allocation_tables(conn)
        insert_board(
            conn,
            board_decision="RESEARCH_BOARD_WATCHLIST_MORE_SHADOW_DATA",
            global_verdict="RESEARCH_PROMOTION_BOARD_REVIEW_WATCHLIST",
            recommended_action="CONTINUE_SHADOW_OBSERVATION_AND_REVIEW",
        )
        insert_allocation(conn, "a1")
        conn.commit()

    result = run_paper_trading_sandbox(
        db_path=db_path,
        session_label="unapproved-session",
        report_label="unapproved-report",
        board_review_label="review-1",
    )

    assert result["global_verdict"] == SESSION_BLOCKED_BOARD
    assert result["submitted_order_count"] == 0


def test_paper_sandbox_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission63-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_board_and_allocation_tables(conn)
        insert_board(conn, live_trading="ENABLED")
        insert_allocation(conn, "a1", live_trading="ENABLED")
        conn.commit()

    result = run_paper_trading_sandbox(
        db_path=db_path,
        session_label="safety-session",
        report_label="safety-report",
        board_review_label="review-1",
    )

    assert result["global_verdict"] == SESSION_BLOCKED_SAFETY
    assert result["safety_breach_count"] >= 1


def test_paper_sandbox_handles_no_included_allocations(tmp_path):
    db_path = tmp_path / "mission63-empty.db"

    with sqlite3.connect(db_path) as conn:
        create_board_and_allocation_tables(conn)
        insert_board(conn)
        insert_allocation(
            conn,
            "excluded-a1",
            status="PORTFOLIO_ALLOCATION_EXCLUDED_SHADOW_ONLY",
        )
        conn.commit()

    result = run_paper_trading_sandbox(
        db_path=db_path,
        session_label="empty-session",
        report_label="empty-report",
        board_review_label="review-1",
    )

    assert result["global_verdict"] == SESSION_NO_ALLOCATIONS
    assert result["submitted_order_count"] == 0


def test_markdown_report_contains_paper_only_safety_statement(tmp_path):
    db_path = tmp_path / "mission63-markdown.db"

    with sqlite3.connect(db_path) as conn:
        seed_approved_sandbox(conn)
        conn.commit()

    result = run_paper_trading_sandbox(
        db_path=db_path,
        session_label="markdown-session",
        report_label="markdown-report",
        board_review_label="review-1",
        reference_dataset_label="dataset-1",
    )

    assert "# DeltaGrid Mission 63" in result["markdown_report"]
    assert "All orders, fills, and positions are paper-only local simulations." in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]
