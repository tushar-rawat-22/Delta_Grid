import sqlite3

from offchain.capital.capital_readiness_review import (
    CAPITAL_BLOCKED,
    CAPITAL_DECISION_BLOCK_CAPITAL,
    CAPITAL_DECISION_BLOCK_RISK,
    CAPITAL_DECISION_BLOCK_SAFETY,
    CAPITAL_DECISION_EXTENDED_PAPER,
    CAPITAL_DECISION_REJECT_MISSING,
    CAPITAL_MISSING,
    CAPITAL_READY_PAPER_ONLY,
    run_capital_readiness_review,
)


def create_risk_tables(conn):
    conn.execute(
        """
        CREATE TABLE institutional_risk_control_reviews (
            review_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_session_label TEXT NOT NULL,
            source_board_review_label TEXT,
            source_portfolio_label TEXT,
            paper_notional TEXT NOT NULL,
            limit_check_count INTEGER NOT NULL,
            pass_limit_count INTEGER NOT NULL,
            fail_limit_count INTEGER NOT NULL,
            position_count INTEGER NOT NULL,
            order_count INTEGER NOT NULL,
            filled_order_count INTEGER NOT NULL,
            blocked_order_count INTEGER NOT NULL,
            distinct_symbol_count INTEGER NOT NULL,
            distinct_strategy_count INTEGER NOT NULL,
            max_symbol_exposure_pct TEXT NOT NULL,
            max_strategy_exposure_pct TEXT NOT NULL,
            observed_max_symbol_exposure_pct TEXT NOT NULL,
            observed_max_strategy_exposure_pct TEXT NOT NULL,
            total_cost_bps TEXT NOT NULL,
            net_deployed_notional TEXT NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            institutional_risk_level TEXT NOT NULL,
            risk_decision TEXT NOT NULL,
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
        CREATE TABLE institutional_risk_decision_records (
            decision_id TEXT PRIMARY KEY,
            review_label TEXT NOT NULL,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_session_label TEXT NOT NULL,
            risk_decision TEXT NOT NULL,
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


def insert_risk_review(
    conn,
    review_label="risk-1",
    risk_decision="INSTITUTIONAL_RISK_APPROVED_FOR_CONTROLLED_PAPER_OBSERVATION",
    global_verdict="INSTITUTIONAL_RISK_CONTROL_READY_SHADOW_ONLY",
    recommended_action="RUN_RISK_CONTROLLED_PAPER_OBSERVATION_CYCLE",
    fail_limit_count=0,
    risk_level="INSTITUTIONAL_RISK_LEVEL_MODERATE",
    position_count=4,
    distinct_symbol_count=2,
    observed_symbol="59.647996",
    observed_strategy="50.0",
    total_cost_bps="3.5",
    safety_breach_count=0,
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO institutional_risk_control_reviews (
            review_label,
            report_label,
            created_at,
            source_session_label,
            source_board_review_label,
            source_portfolio_label,
            paper_notional,
            limit_check_count,
            pass_limit_count,
            fail_limit_count,
            position_count,
            order_count,
            filled_order_count,
            blocked_order_count,
            distinct_symbol_count,
            distinct_strategy_count,
            max_symbol_exposure_pct,
            max_strategy_exposure_pct,
            observed_max_symbol_exposure_pct,
            observed_max_strategy_exposure_pct,
            total_cost_bps,
            net_deployed_notional,
            safety_breach_count,
            institutional_risk_level,
            risk_decision,
            global_verdict,
            recommended_action,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_label,
            f"{review_label}-report",
            "2026-01-01T00:00:00+00:00",
            "session-1",
            "board-1",
            "portfolio-1",
            "100000",
            9,
            9 - fail_limit_count,
            fail_limit_count,
            position_count,
            4,
            4,
            0,
            distinct_symbol_count,
            3,
            "60",
            "50",
            observed_symbol,
            observed_strategy,
            total_cost_bps,
            "100035",
            safety_breach_count,
            risk_level,
            risk_decision,
            global_verdict,
            recommended_action,
            "Mission 65 Capital Readiness Review",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )

    conn.execute(
        """
        INSERT INTO institutional_risk_decision_records (
            decision_id,
            review_label,
            report_label,
            created_at,
            source_session_label,
            risk_decision,
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
            "session-1",
            risk_decision,
            global_verdict,
            recommended_action,
            "CONTROLLED_PAPER_OBSERVATION_ONLY",
            "NOT_LIVE_TRADING_NOT_REAL_CAPITAL",
            "test",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
        ),
    )


def test_capital_readiness_approves_extended_paper_and_persists(tmp_path):
    db_path = tmp_path / "mission65.db"

    with sqlite3.connect(db_path) as conn:
        create_risk_tables(conn)
        insert_risk_review(conn)
        conn.commit()

    result = run_capital_readiness_review(
        db_path=db_path,
        review_label="capital-review-1",
        report_label="capital-report-1",
        risk_review_label="risk-1",
    )

    assert result["capital_decision"] == CAPITAL_DECISION_EXTENDED_PAPER
    assert result["global_verdict"] == CAPITAL_READY_PAPER_ONLY
    assert result["fail_evidence_count"] == 0
    assert result["pass_evidence_count"] == 12
    assert result["capital_deployment"] == "BLOCKED"
    assert result["live_trading"] == "DISABLED"

    with sqlite3.connect(db_path) as conn:
        review = conn.execute(
            """
            SELECT review_label, capital_decision, global_verdict
            FROM capital_readiness_reviews
            WHERE review_label = ?
            """,
            ("capital-review-1",),
        ).fetchone()

        evidence_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM capital_readiness_evidence_items
            WHERE review_label = ?
            """,
            ("capital-review-1",),
        ).fetchone()[0]

    assert review == ("capital-review-1", CAPITAL_DECISION_EXTENDED_PAPER, CAPITAL_READY_PAPER_ONLY)
    assert evidence_count == 12


def test_capital_readiness_rejects_missing_evidence(tmp_path):
    db_path = tmp_path / "mission65-missing.db"

    result = run_capital_readiness_review(
        db_path=db_path,
        review_label="missing-review",
        report_label="missing-report",
        risk_review_label="missing-risk",
    )

    assert result["capital_decision"] == CAPITAL_DECISION_REJECT_MISSING
    assert result["global_verdict"] == CAPITAL_MISSING
    assert result["fail_evidence_count"] == 1


def test_capital_readiness_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission65-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_risk_tables(conn)
        insert_risk_review(conn, safety_breach_count=1, live_trading="ENABLED")
        conn.commit()

    result = run_capital_readiness_review(
        db_path=db_path,
        review_label="safety-review",
        report_label="safety-report",
        risk_review_label="risk-1",
    )

    assert result["capital_decision"] == CAPITAL_DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == CAPITAL_BLOCKED
    assert result["fail_evidence_count"] >= 1


def test_capital_readiness_blocks_failed_risk_limits(tmp_path):
    db_path = tmp_path / "mission65-risk.db"

    with sqlite3.connect(db_path) as conn:
        create_risk_tables(conn)
        insert_risk_review(
            conn,
            fail_limit_count=2,
            risk_decision="INSTITUTIONAL_RISK_BLOCKED_BY_LIMITS",
            global_verdict="INSTITUTIONAL_RISK_CONTROL_BLOCKED_SHADOW_ONLY",
        )
        conn.commit()

    result = run_capital_readiness_review(
        db_path=db_path,
        review_label="risk-review",
        report_label="risk-report",
        risk_review_label="risk-1",
    )

    assert result["capital_decision"] == CAPITAL_DECISION_BLOCK_RISK
    assert result["global_verdict"] == CAPITAL_BLOCKED
    assert result["fail_evidence_count"] >= 1


def test_capital_readiness_blocks_capital_policy_breach(tmp_path):
    db_path = tmp_path / "mission65-capital.db"

    with sqlite3.connect(db_path) as conn:
        create_risk_tables(conn)
        insert_risk_review(conn, capital_deployment="ENABLED")
        conn.commit()

    result = run_capital_readiness_review(
        db_path=db_path,
        review_label="capital-policy-review",
        report_label="capital-policy-report",
        risk_review_label="risk-1",
    )

    assert result["capital_decision"] == CAPITAL_DECISION_BLOCK_CAPITAL
    assert result["global_verdict"] == CAPITAL_BLOCKED


def test_capital_readiness_blocks_exposure_breach(tmp_path):
    db_path = tmp_path / "mission65-exposure.db"

    with sqlite3.connect(db_path) as conn:
        create_risk_tables(conn)
        insert_risk_review(conn, observed_symbol="75.0")
        conn.commit()

    result = run_capital_readiness_review(
        db_path=db_path,
        review_label="exposure-review",
        report_label="exposure-report",
        risk_review_label="risk-1",
        max_allowed_symbol_exposure_pct=60,
    )

    assert result["capital_decision"] == CAPITAL_DECISION_BLOCK_RISK
    assert result["global_verdict"] == CAPITAL_BLOCKED


def test_markdown_report_contains_non_capital_approval_scope(tmp_path):
    db_path = tmp_path / "mission65-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_risk_tables(conn)
        insert_risk_review(conn)
        conn.commit()

    result = run_capital_readiness_review(
        db_path=db_path,
        review_label="markdown-review",
        report_label="markdown-report",
        risk_review_label="risk-1",
    )

    assert "# DeltaGrid Mission 65" in result["markdown_report"]
    assert "Capital deployment remains blocked." in result["markdown_report"]
    assert "Approval scope, if approved, is extended paper observation only." in result["markdown_report"]
    assert "It is not approval for live trading or real capital." in result["markdown_report"]
