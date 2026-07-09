import json
import sqlite3

from offchain.backtest.shadow_observation_outcome_finalizer import (
    CLOSE_READY_VERDICT,
    CONTINUED_TRACKING_VERDICT,
    NO_CLOSE_DECISION_HISTORY_VERDICT,
    REJECTED_VERDICT,
    SAFETY_BLOCKED_VERDICT,
    run_shadow_observation_outcome_finalizer,
)


def create_input_table(conn):
    conn.execute(
        """
        CREATE TABLE shadow_observation_close_decisions (
            close_decision_id TEXT PRIMARY KEY,
            decision_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            tracker_label TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            ledger_label TEXT NOT NULL,
            source_gate_label TEXT NOT NULL,
            symbol TEXT NOT NULL,
            break_even_status TEXT NOT NULL,
            close_decision TEXT NOT NULL,
            close_reason TEXT,
            continue_reason TEXT,
            remaining_hours_to_break_even TEXT,
            projected_break_even_at TEXT,
            cost_remaining_usd TEXT NOT NULL,
            net_expected_pnl_usd TEXT NOT NULL,
            total_cost_usd TEXT NOT NULL,
            simulated_notional_usd TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            risk_flags_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_close_decision(
    conn,
    observation_id="obs-1",
    decision_label="mission45-decision",
    close_decision="CONTINUE_TRACKING",
    close_reason=None,
    continue_reason="Observation continues tracking.",
    cost_remaining="0.5",
    net_expected="-0.5",
    remaining_hours="10.0",
    live_order_sent=0,
):
    conn.execute(
        """
        INSERT INTO shadow_observation_close_decisions (
            close_decision_id,
            decision_label,
            created_at,
            tracker_label,
            observation_id,
            ledger_label,
            source_gate_label,
            symbol,
            break_even_status,
            close_decision,
            close_reason,
            continue_reason,
            remaining_hours_to_break_even,
            projected_break_even_at,
            cost_remaining_usd,
            net_expected_pnl_usd,
            total_cost_usd,
            simulated_notional_usd,
            live_trading,
            live_order_sent,
            capital_deployment,
            risk_flags_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{decision_label}-{observation_id}",
            decision_label,
            "2026-01-01T00:00:00+00:00",
            "tracker-1",
            observation_id,
            "ledger-1",
            "gate-1",
            "BTCUSDT",
            "BREAK_EVEN_PENDING",
            close_decision,
            close_reason,
            continue_reason,
            remaining_hours,
            "2026-01-02T00:00:00+00:00",
            cost_remaining,
            net_expected,
            "0.9",
            "1000.0",
            "DISABLED",
            live_order_sent,
            "BLOCKED",
            json.dumps([]),
            json.dumps({"note": "test"}),
        ),
    )


def test_missing_database_returns_no_close_decision_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_shadow_observation_outcome_finalizer(
        db_path=db_path,
        outcome_label="missing-outcome",
        report_label="missing-report",
    )

    assert result["database_exists"] is False
    assert result["observation_count"] == 0
    assert result["global_verdict"] == NO_CLOSE_DECISION_HISTORY_VERDICT


def test_outcome_finalizer_continues_tracking(tmp_path):
    db_path = tmp_path / "mission45.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_close_decision(conn)
        conn.commit()

    result = run_shadow_observation_outcome_finalizer(
        db_path=db_path,
        outcome_label="mission45-outcome",
        report_label="mission45-report",
        decision_label="mission45-decision",
        gate_label="gate-1",
    )

    assert result["global_verdict"] == CONTINUED_TRACKING_VERDICT
    assert result["observation_count"] == 1
    assert result["continued_count"] == 1
    assert result["close_ready_count"] == 0
    assert result["safety_blocked_count"] == 0
    assert result["outcomes"][0]["final_outcome"] == "OUTCOME_CONTINUED_TRACKING"

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            """
            SELECT report_label, observation_count, continued_count, safety_blocked_count, global_verdict
            FROM shadow_observation_outcome_reports
            WHERE report_label = ?
            """,
            ("mission45-report",),
        ).fetchone()

    assert stored == (
        "mission45-report",
        1,
        1,
        0,
        CONTINUED_TRACKING_VERDICT,
    )


def test_outcome_finalizer_marks_close_ready(tmp_path):
    db_path = tmp_path / "mission45-close-ready.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_close_decision(
            conn,
            close_decision="CLOSE_ELIGIBLE_BREAK_EVEN_REACHED",
            close_reason="Break-even reached.",
            continue_reason=None,
            cost_remaining="0.0",
            net_expected="0.2",
            remaining_hours="0.0",
        )
        conn.commit()

    result = run_shadow_observation_outcome_finalizer(
        db_path=db_path,
        outcome_label="mission45-close-ready-outcome",
        report_label="mission45-close-ready-report",
        decision_label="mission45-decision",
        gate_label="gate-1",
    )

    assert result["global_verdict"] == CLOSE_READY_VERDICT
    assert result["close_ready_count"] == 1
    assert result["outcomes"][0]["final_outcome"] == "OUTCOME_SHADOW_CLOSE_READY"


def test_outcome_finalizer_rejects_uneconomic(tmp_path):
    db_path = tmp_path / "mission45-rejected.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_close_decision(
            conn,
            close_decision="REJECT_UNECONOMIC_TOO_LONG_TO_BREAK_EVEN",
            close_reason="Break-even too far away.",
            continue_reason=None,
            cost_remaining="3.0",
            net_expected="-3.0",
            remaining_hours="120.0",
        )
        conn.commit()

    result = run_shadow_observation_outcome_finalizer(
        db_path=db_path,
        outcome_label="mission45-rejected-outcome",
        report_label="mission45-rejected-report",
        decision_label="mission45-decision",
        gate_label="gate-1",
    )

    assert result["global_verdict"] == REJECTED_VERDICT
    assert result["rejected_count"] == 1
    assert result["outcomes"][0]["final_outcome"] == "OUTCOME_REJECTED_UNECONOMIC"


def test_outcome_finalizer_detects_safety_block(tmp_path):
    db_path = tmp_path / "mission45-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_close_decision(conn, live_order_sent=1)
        conn.commit()

    result = run_shadow_observation_outcome_finalizer(
        db_path=db_path,
        outcome_label="mission45-safety-outcome",
        report_label="mission45-safety-report",
        decision_label="mission45-decision",
        gate_label="gate-1",
    )

    assert result["global_verdict"] == SAFETY_BLOCKED_VERDICT
    assert result["safety_blocked_count"] == 1
    assert result["outcomes"][0]["final_outcome"] == "OUTCOME_SAFETY_BLOCKED"
