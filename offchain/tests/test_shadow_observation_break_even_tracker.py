import json
import sqlite3

from offchain.backtest.shadow_observation_break_even_tracker import (
    PENDING_VERDICT,
    REACHED_VERDICT,
    SAFETY_BREACH_VERDICT,
    NO_PNL_ATTRIBUTION_HISTORY_VERDICT,
    run_shadow_observation_break_even_tracker,
)


def create_input_table(conn):
    conn.execute(
        """
        CREATE TABLE shadow_observation_pnl_attribution (
            attribution_id TEXT PRIMARY KEY,
            attribution_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            snapshot_label TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            ledger_label TEXT NOT NULL,
            source_gate_label TEXT NOT NULL,
            symbol TEXT NOT NULL,
            lifecycle_status TEXT NOT NULL,
            simulated_notional_usd TEXT NOT NULL,
            gross_expected_funding_pnl_usd TEXT NOT NULL,
            fee_cost_usd TEXT NOT NULL,
            spread_cost_usd TEXT NOT NULL,
            slippage_cost_usd TEXT NOT NULL,
            total_cost_usd TEXT NOT NULL,
            net_expected_pnl_usd TEXT NOT NULL,
            net_expected_return_bps TEXT NOT NULL,
            edge_to_cost_ratio TEXT NOT NULL,
            attribution_status TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            risk_flags_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_attribution(
    conn,
    observation_id="obs-1",
    attribution_label="mission43-attr",
    gross="0.05",
    total_cost="0.9",
    net="-0.85",
    annualized=0.42,
    age_hours=1.0,
    live_order_sent=0,
):
    metadata = {
        "age_hours": age_hours,
        "expected_annualized_funding": annualized,
        "source_metadata": {"note": "test"},
    }

    conn.execute(
        """
        INSERT INTO shadow_observation_pnl_attribution (
            attribution_id,
            attribution_label,
            created_at,
            snapshot_label,
            observation_id,
            ledger_label,
            source_gate_label,
            symbol,
            lifecycle_status,
            simulated_notional_usd,
            gross_expected_funding_pnl_usd,
            fee_cost_usd,
            spread_cost_usd,
            slippage_cost_usd,
            total_cost_usd,
            net_expected_pnl_usd,
            net_expected_return_bps,
            edge_to_cost_ratio,
            attribution_status,
            live_trading,
            live_order_sent,
            capital_deployment,
            risk_flags_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{attribution_label}-{observation_id}",
            attribution_label,
            "2026-01-01T00:00:00+00:00",
            "snapshot-1",
            observation_id,
            "ledger-1",
            "gate-1",
            "BTCUSDT",
            "TRACKING",
            "1000.0",
            gross,
            "0.4",
            "0.2",
            "0.3",
            total_cost,
            net,
            "-8.5",
            "0.05",
            "NEGATIVE_EXPECTED_AFTER_COST",
            "DISABLED",
            live_order_sent,
            "BLOCKED",
            json.dumps([]),
            json.dumps(metadata),
        ),
    )


def test_missing_database_returns_no_pnl_attribution_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_shadow_observation_break_even_tracker(
        db_path=db_path,
        tracker_label="missing-tracker",
        report_label="missing-report",
    )

    assert result["database_exists"] is False
    assert result["observation_count"] == 0
    assert result["global_verdict"] == NO_PNL_ATTRIBUTION_HISTORY_VERDICT


def test_break_even_tracker_marks_pending_observation(tmp_path):
    db_path = tmp_path / "mission43.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_attribution(conn)
        conn.commit()

    result = run_shadow_observation_break_even_tracker(
        db_path=db_path,
        tracker_label="mission43-tracker",
        report_label="mission43-report",
        attribution_label="mission43-attr",
        gate_label="gate-1",
    )

    assert result["global_verdict"] == PENDING_VERDICT
    assert result["observation_count"] == 1
    assert result["pending_count"] == 1
    assert result["safety_breach_count"] == 0
    assert result["break_even_rows"][0]["status"] == "BREAK_EVEN_PENDING"
    assert result["break_even_rows"][0]["remaining_hours_to_break_even"] > 0
    assert result["break_even_rows"][0]["cost_remaining_usd"] == 0.85

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            """
            SELECT report_label, observation_count, pending_count, safety_breach_count, global_verdict
            FROM shadow_observation_break_even_reports
            WHERE report_label = ?
            """,
            ("mission43-report",),
        ).fetchone()

    assert stored == (
        "mission43-report",
        1,
        1,
        0,
        PENDING_VERDICT,
    )


def test_break_even_tracker_marks_reached_observation(tmp_path):
    db_path = tmp_path / "mission43-reached.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_attribution(
            conn,
            gross="1.2",
            total_cost="0.9",
            net="0.3",
            annualized=0.42,
            age_hours=30.0,
        )
        conn.commit()

    result = run_shadow_observation_break_even_tracker(
        db_path=db_path,
        tracker_label="mission43-reached-tracker",
        report_label="mission43-reached-report",
        attribution_label="mission43-attr",
        gate_label="gate-1",
    )

    assert result["global_verdict"] == REACHED_VERDICT
    assert result["reached_count"] == 1
    assert result["pending_count"] == 0
    assert result["break_even_rows"][0]["status"] == "BREAK_EVEN_REACHED"
    assert result["break_even_rows"][0]["remaining_hours_to_break_even"] == 0.0


def test_break_even_tracker_detects_safety_breach(tmp_path):
    db_path = tmp_path / "mission43-breach.db"

    with sqlite3.connect(db_path) as conn:
        create_input_table(conn)
        insert_attribution(conn, live_order_sent=1)
        conn.commit()

    result = run_shadow_observation_break_even_tracker(
        db_path=db_path,
        tracker_label="mission43-breach-tracker",
        report_label="mission43-breach-report",
        attribution_label="mission43-attr",
        gate_label="gate-1",
    )

    assert result["global_verdict"] == SAFETY_BREACH_VERDICT
    assert result["safety_breach_count"] == 1
    assert result["break_even_rows"][0]["status"] == "SAFETY_BREACH"
