import json
import sqlite3

from offchain.backtest.shadow_research_promotion_readiness_gate import (
    APPROVE_ALPHA_BUILDOUT_VERDICT,
    NO_EXECUTIVE_HISTORY_VERDICT,
    RISK_REVIEW_VERDICT,
    SAFETY_BLOCKED_VERDICT,
    SHADOW_EXPANSION_READY_VERDICT,
    run_shadow_research_promotion_readiness_gate,
)


def create_input_table(conn):
    conn.execute(
        """
        CREATE TABLE shadow_research_executive_daily_reports (
            report_label TEXT PRIMARY KEY,
            daily_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_report_section_count INTEGER NOT NULL,
            present_section_count INTEGER NOT NULL,
            safety_issue_count INTEGER NOT NULL,
            risk_review_count INTEGER NOT NULL,
            live_trading_status TEXT NOT NULL,
            capital_deployment_status TEXT NOT NULL,
            global_verdict TEXT NOT NULL,
            recommended_action TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            markdown_report TEXT NOT NULL
        )
        """
    )


def executive_summary(
    total_net_expected=-1.2,
    close_ready_count=0,
    negative_count=2,
    continued_count=2,
):
    return {
        "sections": [
            {
                "table_name": "shadow_observation_outcome_analytics_reports",
                "metrics": {
                    "total_net_expected_pnl_usd": total_net_expected,
                    "close_ready_count": close_ready_count,
                    "continued_count": continued_count,
                },
                "latest_row": {},
            },
            {
                "table_name": "shadow_observation_pnl_attribution_reports",
                "metrics": {
                    "negative_count": negative_count,
                },
                "latest_row": {},
            },
        ]
    }


def insert_executive_report(
    conn,
    report_label="mission48-source-report",
    daily_label="mission48-source-daily",
    safety_issue_count=0,
    risk_review_count=0,
    live_trading_status="DISABLED",
    capital_deployment_status="BLOCKED",
    present_section_count=9,
    source_report_section_count=9,
    summary=None,
):
    conn.execute(
        """
        INSERT INTO shadow_research_executive_daily_reports (
            report_label,
            daily_label,
            created_at,
            source_report_section_count,
            present_section_count,
            safety_issue_count,
            risk_review_count,
            live_trading_status,
            capital_deployment_status,
            global_verdict,
            recommended_action,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report_label,
            daily_label,
            "2026-01-01T00:00:00+00:00",
            source_report_section_count,
            present_section_count,
            safety_issue_count,
            risk_review_count,
            live_trading_status,
            capital_deployment_status,
            "EXECUTIVE_DAILY_CONTINUE_SHADOW_RESEARCH_NO_LIVE_TRADING",
            "CONTINUE_SHADOW_RESEARCH_NO_LIVE_TRADING",
            json.dumps(summary or executive_summary()),
            "# test",
        ),
    )


def test_missing_database_returns_no_executive_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_shadow_research_promotion_readiness_gate(
        db_path=db_path,
        readiness_label="missing-readiness",
        report_label="missing-report",
    )

    assert result["database_exists"] is False
    assert result["global_verdict"] == NO_EXECUTIVE_HISTORY_VERDICT
    assert result["promotion_readiness_decision"] == "BLOCKED"


def test_readiness_gate_approves_alpha_buildout_but_blocks_live(tmp_path):
    db_path = tmp_path / "mission48.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_executive_report(conn)
        conn.commit()

    result = run_shadow_research_promotion_readiness_gate(
        db_path=db_path,
        readiness_label="mission48-readiness",
        report_label="mission48-report",
        daily_label="mission48-source-daily",
    )

    assert result["global_verdict"] == APPROVE_ALPHA_BUILDOUT_VERDICT
    assert result["promotion_readiness_decision"] == "APPROVE_ALPHA_ENGINE_BUILDOUT_ONLY"
    assert result["approved_next_stage"] == "REAL_MARKET_ALPHA_ENGINE_BUILDOUT"
    assert result["live_trading_decision"] == "BLOCKED"
    assert result["capital_deployment_decision"] == "BLOCKED"
    assert result["blocker_count"] == 3

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            """
            SELECT report_label, promotion_readiness_decision, approved_next_stage, global_verdict
            FROM shadow_research_promotion_readiness_reports
            WHERE report_label = ?
            """,
            ("mission48-report",),
        ).fetchone()

    assert stored == (
        "mission48-report",
        "APPROVE_ALPHA_ENGINE_BUILDOUT_ONLY",
        "REAL_MARKET_ALPHA_ENGINE_BUILDOUT",
        APPROVE_ALPHA_BUILDOUT_VERDICT,
    )


def test_readiness_gate_blocks_on_safety_issue(tmp_path):
    db_path = tmp_path / "mission48-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_executive_report(conn, safety_issue_count=1)
        conn.commit()

    result = run_shadow_research_promotion_readiness_gate(
        db_path=db_path,
        readiness_label="mission48-safety-readiness",
        report_label="mission48-safety-report",
    )

    assert result["global_verdict"] == SAFETY_BLOCKED_VERDICT
    assert result["promotion_readiness_decision"] == "BLOCKED"


def test_readiness_gate_blocks_on_risk_review(tmp_path):
    db_path = tmp_path / "mission48-risk.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_executive_report(conn, risk_review_count=1)
        conn.commit()

    result = run_shadow_research_promotion_readiness_gate(
        db_path=db_path,
        readiness_label="mission48-risk-readiness",
        report_label="mission48-risk-report",
    )

    assert result["global_verdict"] == RISK_REVIEW_VERDICT
    assert result["promotion_readiness_decision"] == "BLOCKED"


def test_readiness_gate_can_approve_shadow_expansion_when_profit_checks_pass(tmp_path):
    db_path = tmp_path / "mission48-shadow-ready.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_executive_report(
            conn,
            summary=executive_summary(
                total_net_expected=2.0,
                close_ready_count=1,
                negative_count=0,
                continued_count=1,
            ),
        )
        conn.commit()

    result = run_shadow_research_promotion_readiness_gate(
        db_path=db_path,
        readiness_label="mission48-shadow-ready",
        report_label="mission48-shadow-ready-report",
    )

    assert result["global_verdict"] == SHADOW_EXPANSION_READY_VERDICT
    assert result["promotion_readiness_decision"] == "APPROVE_SHADOW_RESEARCH_EXPANSION_ONLY"
    assert result["live_trading_decision"] == "BLOCKED"
    assert result["capital_deployment_decision"] == "BLOCKED"
