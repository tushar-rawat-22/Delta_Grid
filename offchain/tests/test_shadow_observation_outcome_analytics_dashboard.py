import json
import sqlite3

from offchain.backtest.shadow_observation_outcome_analytics_dashboard import (
    CONTINUED_TRACKING_VERDICT,
    NO_OUTCOME_HISTORY_VERDICT,
    SAFETY_BLOCKED_VERDICT,
    run_shadow_observation_outcome_analytics_dashboard,
)


def create_input_table(conn):
    conn.execute(
        """
        CREATE TABLE shadow_observation_outcomes (
            outcome_id TEXT PRIMARY KEY,
            outcome_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_decision_label TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            ledger_label TEXT NOT NULL,
            source_gate_label TEXT NOT NULL,
            symbol TEXT NOT NULL,
            close_decision TEXT NOT NULL,
            final_outcome TEXT NOT NULL,
            outcome_reason TEXT NOT NULL,
            close_ready INTEGER NOT NULL,
            continued_tracking INTEGER NOT NULL,
            rejected INTEGER NOT NULL,
            risk_review_required INTEGER NOT NULL,
            safety_blocked INTEGER NOT NULL,
            cost_remaining_usd TEXT NOT NULL,
            net_expected_pnl_usd TEXT NOT NULL,
            total_cost_usd TEXT NOT NULL,
            remaining_hours_to_break_even TEXT,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            risk_flags_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_outcome(
    conn,
    observation_id="obs-1",
    outcome_label="mission46-outcome",
    symbol="BTCUSDT",
    final_outcome="OUTCOME_CONTINUED_TRACKING",
    cost_remaining="0.5",
    net_expected="-0.5",
    remaining_hours="10.0",
    live_order_sent=0,
):
    conn.execute(
        """
        INSERT INTO shadow_observation_outcomes (
            outcome_id,
            outcome_label,
            created_at,
            source_decision_label,
            observation_id,
            ledger_label,
            source_gate_label,
            symbol,
            close_decision,
            final_outcome,
            outcome_reason,
            close_ready,
            continued_tracking,
            rejected,
            risk_review_required,
            safety_blocked,
            cost_remaining_usd,
            net_expected_pnl_usd,
            total_cost_usd,
            remaining_hours_to_break_even,
            live_trading,
            live_order_sent,
            capital_deployment,
            risk_flags_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{outcome_label}-{observation_id}",
            outcome_label,
            "2026-01-01T00:00:00+00:00",
            "decision-1",
            observation_id,
            "ledger-1",
            "gate-1",
            symbol,
            "CONTINUE_TRACKING",
            final_outcome,
            "test outcome",
            1 if final_outcome == "OUTCOME_SHADOW_CLOSE_READY" else 0,
            1 if final_outcome == "OUTCOME_CONTINUED_TRACKING" else 0,
            1 if final_outcome == "OUTCOME_REJECTED_UNECONOMIC" else 0,
            1 if final_outcome == "OUTCOME_RISK_REVIEW_REQUIRED" else 0,
            1 if final_outcome == "OUTCOME_SAFETY_BLOCKED" else 0,
            cost_remaining,
            net_expected,
            "0.9",
            remaining_hours,
            "DISABLED",
            live_order_sent,
            "BLOCKED",
            json.dumps([]),
            json.dumps({"note": "test"}),
        ),
    )


def test_missing_database_returns_no_outcome_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_shadow_observation_outcome_analytics_dashboard(
        db_path=db_path,
        analytics_label="missing-analytics",
        report_label="missing-report",
    )

    assert result["database_exists"] is False
    assert result["observation_count"] == 0
    assert result["global_verdict"] == NO_OUTCOME_HISTORY_VERDICT


def test_outcome_analytics_summarizes_continued_outcomes(tmp_path):
    db_path = tmp_path / "mission46.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_outcome(conn, observation_id="obs-1", cost_remaining="0.5", net_expected="-0.5")
        insert_outcome(conn, observation_id="obs-2", cost_remaining="0.7", net_expected="-0.7")
        conn.commit()

    result = run_shadow_observation_outcome_analytics_dashboard(
        db_path=db_path,
        analytics_label="mission46-analytics",
        report_label="mission46-report",
        outcome_label="mission46-outcome",
        gate_label="gate-1",
    )

    assert result["global_verdict"] == CONTINUED_TRACKING_VERDICT
    assert result["observation_count"] == 2
    assert result["continued_count"] == 2
    assert result["continued_rate"] == 1.0
    assert result["total_cost_remaining_usd"] == 1.2
    assert result["total_net_expected_pnl_usd"] == -1.2
    assert result["symbol_summary"]["BTCUSDT"]["observation_count"] == 2

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            """
            SELECT report_label, observation_count, continued_count, global_verdict
            FROM shadow_observation_outcome_analytics_reports
            WHERE report_label = ?
            """,
            ("mission46-report",),
        ).fetchone()

    assert stored == (
        "mission46-report",
        2,
        2,
        CONTINUED_TRACKING_VERDICT,
    )


def test_outcome_analytics_supports_symbol_filter(tmp_path):
    db_path = tmp_path / "mission46-symbol.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_outcome(conn, observation_id="btc-1", symbol="BTCUSDT")
        insert_outcome(conn, observation_id="eth-1", symbol="ETHUSDT")
        conn.commit()

    result = run_shadow_observation_outcome_analytics_dashboard(
        db_path=db_path,
        analytics_label="mission46-symbol-analytics",
        report_label="mission46-symbol-report",
        outcome_label="mission46-outcome",
        gate_label="gate-1",
        symbol="ETHUSDT",
    )

    assert result["observation_count"] == 1
    assert list(result["symbol_summary"]) == ["ETHUSDT"]


def test_outcome_analytics_detects_safety_state_breach(tmp_path):
    db_path = tmp_path / "mission46-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_outcome(conn, live_order_sent=1)
        conn.commit()

    result = run_shadow_observation_outcome_analytics_dashboard(
        db_path=db_path,
        analytics_label="mission46-safety-analytics",
        report_label="mission46-safety-report",
        outcome_label="mission46-outcome",
        gate_label="gate-1",
    )

    assert result["global_verdict"] == SAFETY_BLOCKED_VERDICT
    assert result["safety_state_breach_count"] == 1


def test_outcome_analytics_markdown_contains_verdict(tmp_path):
    db_path = tmp_path / "mission46-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_outcome(conn)
        conn.commit()

    result = run_shadow_observation_outcome_analytics_dashboard(
        db_path=db_path,
        analytics_label="mission46-markdown-analytics",
        report_label="mission46-markdown-report",
        outcome_label="mission46-outcome",
        gate_label="gate-1",
    )

    assert "# DeltaGrid Mission 46" in result["markdown_report"]
    assert CONTINUED_TRACKING_VERDICT in result["markdown_report"]
