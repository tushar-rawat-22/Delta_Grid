import json
import sqlite3

from offchain.backtest.shadow_observation_close_eligibility_engine import (
    CLOSE_READY_VERDICT,
    CONTINUE_TRACKING_VERDICT,
    NO_BREAK_EVEN_HISTORY_VERDICT,
    REJECT_UNECONOMIC_VERDICT,
    SAFETY_BREACH_VERDICT,
    run_shadow_observation_close_eligibility_engine,
)


def create_input_table(conn):
    conn.execute(
        """
        CREATE TABLE shadow_observation_break_even_tracking (
            break_even_id TEXT PRIMARY KEY,
            tracker_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            attribution_label TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            ledger_label TEXT NOT NULL,
            source_gate_label TEXT NOT NULL,
            symbol TEXT NOT NULL,
            status TEXT NOT NULL,
            simulated_notional_usd TEXT NOT NULL,
            expected_annualized_funding TEXT NOT NULL,
            funding_per_hour_usd TEXT NOT NULL,
            gross_expected_funding_pnl_usd TEXT NOT NULL,
            total_cost_usd TEXT NOT NULL,
            net_expected_pnl_usd TEXT NOT NULL,
            cost_remaining_usd TEXT NOT NULL,
            age_hours TEXT NOT NULL,
            break_even_hours TEXT,
            remaining_hours_to_break_even TEXT,
            projected_break_even_at TEXT,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            risk_flags_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_break_even(
    conn,
    observation_id="obs-1",
    tracker_label="mission44-tracker",
    status="BREAK_EVEN_PENDING",
    remaining_hours="10.0",
    cost_remaining="0.5",
    net_expected="-0.5",
    live_order_sent=0,
):
    conn.execute(
        """
        INSERT INTO shadow_observation_break_even_tracking (
            break_even_id,
            tracker_label,
            created_at,
            attribution_label,
            observation_id,
            ledger_label,
            source_gate_label,
            symbol,
            status,
            simulated_notional_usd,
            expected_annualized_funding,
            funding_per_hour_usd,
            gross_expected_funding_pnl_usd,
            total_cost_usd,
            net_expected_pnl_usd,
            cost_remaining_usd,
            age_hours,
            break_even_hours,
            remaining_hours_to_break_even,
            projected_break_even_at,
            live_trading,
            live_order_sent,
            capital_deployment,
            risk_flags_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{tracker_label}-{observation_id}",
            tracker_label,
            "2026-01-01T00:00:00+00:00",
            "attr-1",
            observation_id,
            "ledger-1",
            "gate-1",
            "BTCUSDT",
            status,
            "1000.0",
            "0.42",
            "0.047",
            "0.4",
            "0.9",
            net_expected,
            cost_remaining,
            "10.0",
            "20.0",
            remaining_hours,
            "2026-01-02T00:00:00+00:00",
            "DISABLED",
            live_order_sent,
            "BLOCKED",
            json.dumps([]),
            json.dumps({"note": "test"}),
        ),
    )


def test_missing_database_returns_no_break_even_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_shadow_observation_close_eligibility_engine(
        db_path=db_path,
        decision_label="missing-decision",
        report_label="missing-report",
    )

    assert result["database_exists"] is False
    assert result["observation_count"] == 0
    assert result["global_verdict"] == NO_BREAK_EVEN_HISTORY_VERDICT


def test_close_eligibility_continues_pending_observation(tmp_path):
    db_path = tmp_path / "mission44.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_break_even(conn)
        conn.commit()

    result = run_shadow_observation_close_eligibility_engine(
        db_path=db_path,
        decision_label="mission44-decision",
        report_label="mission44-report",
        tracker_label="mission44-tracker",
        gate_label="gate-1",
    )

    assert result["global_verdict"] == CONTINUE_TRACKING_VERDICT
    assert result["observation_count"] == 1
    assert result["continue_count"] == 1
    assert result["close_eligible_count"] == 0
    assert result["reject_count"] == 0
    assert result["safety_breach_count"] == 0
    assert result["decisions"][0]["close_decision"] == "CONTINUE_TRACKING"

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            """
            SELECT report_label, observation_count, continue_count, safety_breach_count, global_verdict
            FROM shadow_observation_close_decision_reports
            WHERE report_label = ?
            """,
            ("mission44-report",),
        ).fetchone()

    assert stored == (
        "mission44-report",
        1,
        1,
        0,
        CONTINUE_TRACKING_VERDICT,
    )


def test_close_eligibility_marks_reached_observation_close_ready(tmp_path):
    db_path = tmp_path / "mission44-reached.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_break_even(
            conn,
            status="BREAK_EVEN_REACHED",
            remaining_hours="0.0",
            cost_remaining="0.0",
            net_expected="0.1",
        )
        conn.commit()

    result = run_shadow_observation_close_eligibility_engine(
        db_path=db_path,
        decision_label="mission44-reached-decision",
        report_label="mission44-reached-report",
        tracker_label="mission44-tracker",
        gate_label="gate-1",
    )

    assert result["global_verdict"] == CLOSE_READY_VERDICT
    assert result["close_eligible_count"] == 1
    assert result["decisions"][0]["close_decision"] == "CLOSE_ELIGIBLE_BREAK_EVEN_REACHED"


def test_close_eligibility_rejects_uneconomic_long_wait(tmp_path):
    db_path = tmp_path / "mission44-reject.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_break_even(conn, remaining_hours="120.0", cost_remaining="3.0")
        conn.commit()

    result = run_shadow_observation_close_eligibility_engine(
        db_path=db_path,
        decision_label="mission44-reject-decision",
        report_label="mission44-reject-report",
        tracker_label="mission44-tracker",
        gate_label="gate-1",
        max_remaining_hours_to_keep=72.0,
    )

    assert result["global_verdict"] == REJECT_UNECONOMIC_VERDICT
    assert result["reject_count"] == 1
    assert result["decisions"][0]["close_decision"] == "REJECT_UNECONOMIC_TOO_LONG_TO_BREAK_EVEN"


def test_close_eligibility_detects_safety_breach(tmp_path):
    db_path = tmp_path / "mission44-breach.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_break_even(conn, live_order_sent=1)
        conn.commit()

    result = run_shadow_observation_close_eligibility_engine(
        db_path=db_path,
        decision_label="mission44-breach-decision",
        report_label="mission44-breach-report",
        tracker_label="mission44-tracker",
        gate_label="gate-1",
    )

    assert result["global_verdict"] == SAFETY_BREACH_VERDICT
    assert result["safety_breach_count"] == 1
    assert result["decisions"][0]["close_decision"] == "SAFETY_BREACH_BLOCKED"
