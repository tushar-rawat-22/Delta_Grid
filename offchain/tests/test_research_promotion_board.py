import sqlite3

from offchain.governance.research_promotion_board import (
    BOARD_BLOCKED,
    BOARD_MISSING,
    BOARD_READY,
    BOARD_WATCHLIST,
    DECISION_APPROVE_PAPER,
    DECISION_BLOCK_RISK,
    DECISION_BLOCK_SAFETY,
    DECISION_REJECT_MISSING,
    DECISION_WATCHLIST,
    run_research_promotion_board,
)


def create_portfolio_tables(conn):
    conn.execute(
        """
        CREATE TABLE shadow_portfolio_simulations (
            portfolio_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_regime_label TEXT NOT NULL,
            shadow_notional TEXT NOT NULL,
            requested_symbol_count INTEGER NOT NULL,
            source_gate_count INTEGER NOT NULL,
            eligible_candidate_count INTEGER NOT NULL,
            included_allocation_count INTEGER NOT NULL,
            excluded_candidate_count INTEGER NOT NULL,
            total_allocated_weight TEXT NOT NULL,
            unallocated_weight TEXT NOT NULL,
            allocated_notional TEXT NOT NULL,
            weighted_alpha_score TEXT NOT NULL,
            max_symbol_weight TEXT NOT NULL,
            max_strategy_weight TEXT NOT NULL,
            max_candidate_weight TEXT NOT NULL,
            concentration_score TEXT NOT NULL,
            estimated_shadow_drawdown_pct TEXT NOT NULL,
            portfolio_risk_rating TEXT NOT NULL,
            global_verdict TEXT NOT NULL,
            recommended_action TEXT NOT NULL,
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

    conn.execute(
        """
        CREATE TABLE shadow_portfolio_risk_reports (
            risk_report_id TEXT PRIMARY KEY,
            portfolio_label TEXT NOT NULL,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            symbol_exposure_json TEXT NOT NULL,
            strategy_exposure_json TEXT NOT NULL,
            top_symbol TEXT,
            top_strategy_id TEXT,
            max_symbol_weight TEXT NOT NULL,
            max_strategy_weight TEXT NOT NULL,
            concentration_score TEXT NOT NULL,
            estimated_shadow_drawdown_pct TEXT NOT NULL,
            portfolio_risk_rating TEXT NOT NULL,
            risk_notes_json TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL
        )
        """
    )


def insert_portfolio(
    conn,
    portfolio_label="portfolio-1",
    included_allocation_count=4,
    excluded_candidate_count=11,
    weighted_alpha_score="82.0",
    concentration_score="59.0",
    drawdown="5.5",
    risk_rating="PORTFOLIO_RISK_MODERATE",
    global_verdict="SHADOW_PORTFOLIO_SIMULATION_READY",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO shadow_portfolio_simulations (
            portfolio_label,
            report_label,
            created_at,
            source_regime_label,
            shadow_notional,
            requested_symbol_count,
            source_gate_count,
            eligible_candidate_count,
            included_allocation_count,
            excluded_candidate_count,
            total_allocated_weight,
            unallocated_weight,
            allocated_notional,
            weighted_alpha_score,
            max_symbol_weight,
            max_strategy_weight,
            max_candidate_weight,
            concentration_score,
            estimated_shadow_drawdown_pct,
            portfolio_risk_rating,
            global_verdict,
            recommended_action,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            portfolio_label,
            f"{portfolio_label}-report",
            "2026-01-01T00:00:00+00:00",
            "regime-1",
            "100000",
            3,
            15,
            included_allocation_count,
            included_allocation_count,
            excluded_candidate_count,
            "1.0",
            "0.0",
            "100000",
            weighted_alpha_score,
            "0.6",
            "0.5",
            "0.35",
            concentration_score,
            drawdown,
            risk_rating,
            global_verdict,
            "test",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )


def insert_allocation(
    conn,
    portfolio_label="portfolio-1",
    allocation_id="allocation-1",
    strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH",
    symbol="BTCUSDT",
    allocation_weight="0.35",
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
            "PORTFOLIO_ALLOCATION_INCLUDED_SHADOW_ONLY",
            "test",
            1,
            "80",
            "95",
            "MARKET_RISK_STATE_NORMAL",
            "76",
            allocation_weight,
            "35000",
            "20",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def insert_risk_report(
    conn,
    portfolio_label="portfolio-1",
    risk_rating="PORTFOLIO_RISK_MODERATE",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO shadow_portfolio_risk_reports (
            risk_report_id,
            portfolio_label,
            report_label,
            created_at,
            symbol_exposure_json,
            strategy_exposure_json,
            top_symbol,
            top_strategy_id,
            max_symbol_weight,
            max_strategy_weight,
            concentration_score,
            estimated_shadow_drawdown_pct,
            portfolio_risk_rating,
            risk_notes_json,
            live_trading,
            live_order_sent,
            capital_deployment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{portfolio_label}-risk",
            portfolio_label,
            f"{portfolio_label}-report",
            "2026-01-01T00:00:00+00:00",
            '{"BTCUSDT": 0.6}',
            '{"CROSS_SYMBOL_RELATIVE_STRENGTH": 0.5}',
            "BTCUSDT",
            "CROSS_SYMBOL_RELATIVE_STRENGTH",
            "0.6",
            "0.5",
            "59",
            "5.5",
            risk_rating,
            "[]",
            live_trading,
            live_order_sent,
            capital_deployment,
        ),
    )


def seed_good_portfolio(conn, portfolio_label="portfolio-1"):
    insert_portfolio(conn, portfolio_label=portfolio_label)
    insert_allocation(conn, portfolio_label=portfolio_label, allocation_id="a1", symbol="BTCUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH")
    insert_allocation(conn, portfolio_label=portfolio_label, allocation_id="a2", symbol="ETHUSDT", strategy_id="BASIS_MEAN_REVERSION")
    insert_allocation(conn, portfolio_label=portfolio_label, allocation_id="a3", symbol="BTCUSDT", strategy_id="VOLATILITY_REGIME_FILTER")
    insert_allocation(conn, portfolio_label=portfolio_label, allocation_id="a4", symbol="ETHUSDT", strategy_id="CROSS_SYMBOL_RELATIVE_STRENGTH")
    insert_risk_report(conn, portfolio_label=portfolio_label)


def test_board_approves_ready_portfolio_and_persists(tmp_path):
    db_path = tmp_path / "mission62.db"

    with sqlite3.connect(db_path) as conn:
        create_portfolio_tables(conn)
        seed_good_portfolio(conn)
        conn.commit()

    result = run_research_promotion_board(
        db_path=db_path,
        review_label="review-1",
        report_label="report-1",
        portfolio_label="portfolio-1",
    )

    assert result["board_decision"] == DECISION_APPROVE_PAPER
    assert result["global_verdict"] == BOARD_READY
    assert result["recommended_action"] == "OPEN_PAPER_SANDBOX_RESEARCH_ONLY"
    assert result["fail_evidence_count"] == 0
    assert result["live_trading"] == "DISABLED"
    assert result["capital_deployment"] == "BLOCKED"

    with sqlite3.connect(db_path) as conn:
        review = conn.execute(
            """
            SELECT review_label, board_decision, global_verdict
            FROM research_promotion_board_reviews
            WHERE review_label = ?
            """,
            ("review-1",),
        ).fetchone()

        evidence_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM research_promotion_board_evidence_items
            WHERE review_label = ?
            """,
            ("review-1",),
        ).fetchone()[0]

    assert review == ("review-1", DECISION_APPROVE_PAPER, BOARD_READY)
    assert evidence_count >= 8


def test_board_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission62-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_portfolio_tables(conn)
        insert_portfolio(conn, live_trading="ENABLED")
        insert_allocation(conn, live_trading="ENABLED")
        insert_risk_report(conn)
        conn.commit()

    result = run_research_promotion_board(
        db_path=db_path,
        review_label="safety-review",
        report_label="safety-report",
        portfolio_label="portfolio-1",
    )

    assert result["board_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == BOARD_BLOCKED
    assert result["recommended_action"] == "STOP_AND_REVIEW_SAFETY_STATE"


def test_board_blocks_high_risk_portfolio(tmp_path):
    db_path = tmp_path / "mission62-risk.db"

    with sqlite3.connect(db_path) as conn:
        create_portfolio_tables(conn)
        insert_portfolio(
            conn,
            concentration_score="80",
            drawdown="9",
            risk_rating="PORTFOLIO_RISK_HIGH",
        )
        insert_allocation(conn)
        insert_risk_report(conn, risk_rating="PORTFOLIO_RISK_HIGH")
        conn.commit()

    result = run_research_promotion_board(
        db_path=db_path,
        review_label="risk-review",
        report_label="risk-report",
        portfolio_label="portfolio-1",
    )

    assert result["board_decision"] == DECISION_BLOCK_RISK
    assert result["global_verdict"] == BOARD_BLOCKED
    assert result["fail_evidence_count"] >= 1


def test_board_watchlists_when_multiple_warnings(tmp_path):
    db_path = tmp_path / "mission62-watch.db"

    with sqlite3.connect(db_path) as conn:
        create_portfolio_tables(conn)
        insert_portfolio(
            conn,
            global_verdict="SHADOW_PORTFOLIO_SIMULATION_CONSTRAINED",
            weighted_alpha_score="40",
        )
        insert_allocation(conn)
        insert_allocation(conn, allocation_id="a2", symbol="ETHUSDT")
        insert_allocation(conn, allocation_id="a3", symbol="ETHUSDT", strategy_id="BASIS_MEAN_REVERSION")
        insert_risk_report(conn)
        conn.commit()

    result = run_research_promotion_board(
        db_path=db_path,
        review_label="watch-review",
        report_label="watch-report",
        portfolio_label="portfolio-1",
        min_included_allocations=3,
        min_weighted_alpha_score=50,
    )

    assert result["board_decision"] == DECISION_WATCHLIST
    assert result["global_verdict"] == BOARD_WATCHLIST


def test_board_rejects_missing_portfolio(tmp_path):
    db_path = tmp_path / "mission62-missing.db"

    result = run_research_promotion_board(
        db_path=db_path,
        review_label="missing-review",
        report_label="missing-report",
        portfolio_label="missing-portfolio",
    )

    assert result["board_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == BOARD_MISSING
    assert result["fail_evidence_count"] == 1


def test_markdown_report_contains_non_live_trading_scope(tmp_path):
    db_path = tmp_path / "mission62-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_portfolio_tables(conn)
        seed_good_portfolio(conn)
        conn.commit()

    result = run_research_promotion_board(
        db_path=db_path,
        review_label="markdown-review",
        report_label="markdown-report",
        portfolio_label="portfolio-1",
    )

    assert "# DeltaGrid Mission 62" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "Approval scope, if approved, is paper sandbox research only." in result["markdown_report"]
