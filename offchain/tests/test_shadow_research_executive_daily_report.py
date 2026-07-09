import sqlite3

from offchain.backtest.shadow_research_executive_daily_report import (
    CONTINUE_SHADOW_RESEARCH_VERDICT,
    NO_DATABASE_VERDICT,
    RISK_REVIEW_VERDICT,
    SAFETY_BLOCKED_VERDICT,
    run_shadow_research_executive_daily_report,
)


def create_report_table(conn, table_name):
    conn.execute(
        f"""
        CREATE TABLE {table_name} (
            report_label TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            observation_count INTEGER NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            risk_review_count INTEGER NOT NULL,
            total_cost_remaining_usd TEXT NOT NULL,
            total_net_expected_pnl_usd TEXT NOT NULL,
            global_verdict TEXT NOT NULL,
            recommended_action TEXT NOT NULL
        )
        """
    )


def insert_report(
    conn,
    table_name,
    label,
    safety_breach_count=0,
    risk_review_count=0,
    verdict="TEST_VERDICT",
):
    conn.execute(
        f"""
        INSERT INTO {table_name} (
            report_label,
            created_at,
            observation_count,
            safety_breach_count,
            risk_review_count,
            total_cost_remaining_usd,
            total_net_expected_pnl_usd,
            global_verdict,
            recommended_action
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            label,
            "2026-01-01T00:00:00+00:00",
            2,
            safety_breach_count,
            risk_review_count,
            "1.2",
            "-1.2",
            verdict,
            "TEST_ACTION",
        ),
    )


def test_missing_database_returns_no_database_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_shadow_research_executive_daily_report(
        db_path=db_path,
        daily_label="missing-daily",
        report_label="missing-report",
    )

    assert result["database_exists"] is False
    assert result["global_verdict"] == NO_DATABASE_VERDICT
    assert result["source_report_section_count"] == 0


def test_executive_daily_report_summarizes_present_sections(tmp_path):
    db_path = tmp_path / "mission47.db"

    with sqlite3.connect(db_path) as conn:
        create_report_table(conn, "shadow_test_alpha_reports")
        create_report_table(conn, "shadow_test_beta_reports")
        insert_report(conn, "shadow_test_alpha_reports", "alpha-report")
        insert_report(conn, "shadow_test_beta_reports", "beta-report")
        conn.commit()

    result = run_shadow_research_executive_daily_report(
        db_path=db_path,
        daily_label="mission47-daily",
        report_label="mission47-report",
    )

    assert result["global_verdict"] == CONTINUE_SHADOW_RESEARCH_VERDICT
    assert result["source_report_section_count"] == 2
    assert result["present_section_count"] == 2
    assert result["safety_issue_count"] == 0
    assert result["risk_review_count"] == 0
    assert "shadow_test_alpha_reports" in result["markdown_report"]

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            """
            SELECT report_label, source_report_section_count, present_section_count, global_verdict
            FROM shadow_research_executive_daily_reports
            WHERE report_label = ?
            """,
            ("mission47-report",),
        ).fetchone()

    assert stored == (
        "mission47-report",
        2,
        2,
        CONTINUE_SHADOW_RESEARCH_VERDICT,
    )


def test_executive_daily_report_detects_safety_issues(tmp_path):
    db_path = tmp_path / "mission47-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_report_table(conn, "shadow_test_safety_reports")
        insert_report(
            conn,
            "shadow_test_safety_reports",
            "safety-report",
            safety_breach_count=1,
        )
        conn.commit()

    result = run_shadow_research_executive_daily_report(
        db_path=db_path,
        daily_label="mission47-safety-daily",
        report_label="mission47-safety-report",
    )

    assert result["global_verdict"] == SAFETY_BLOCKED_VERDICT
    assert result["safety_issue_count"] == 1


def test_executive_daily_report_detects_risk_review(tmp_path):
    db_path = tmp_path / "mission47-risk.db"

    with sqlite3.connect(db_path) as conn:
        create_report_table(conn, "shadow_test_risk_reports")
        insert_report(
            conn,
            "shadow_test_risk_reports",
            "risk-report",
            risk_review_count=2,
        )
        conn.commit()

    result = run_shadow_research_executive_daily_report(
        db_path=db_path,
        daily_label="mission47-risk-daily",
        report_label="mission47-risk-report",
    )

    assert result["global_verdict"] == RISK_REVIEW_VERDICT
    assert result["risk_review_count"] == 2


def test_executive_daily_markdown_contains_safety_statement(tmp_path):
    db_path = tmp_path / "mission47-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_report_table(conn, "shadow_test_markdown_reports")
        insert_report(conn, "shadow_test_markdown_reports", "markdown-report")
        conn.commit()

    result = run_shadow_research_executive_daily_report(
        db_path=db_path,
        daily_label="mission47-markdown-daily",
        report_label="mission47-markdown-report",
    )

    assert "# DeltaGrid Mission 47" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "Capital deployment remains blocked." in result["markdown_report"]
