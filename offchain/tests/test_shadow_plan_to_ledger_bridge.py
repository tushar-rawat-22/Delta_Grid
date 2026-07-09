import sqlite3

from offchain.backtest.shadow_plan_to_ledger_bridge import (
    LEDGER_STATUS_ACTIVE,
    NO_PLAN_HISTORY_VERDICT,
    READY_VERDICT,
    SAFETY_BREACH_VERDICT,
    parse_symbols,
    run_shadow_plan_to_ledger_bridge,
)


def create_plans_table(conn):
    conn.execute(
        """
        CREATE TABLE calibrated_shadow_observation_plans (
            plan_id TEXT PRIMARY KEY,
            plan_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_calibration_label TEXT NOT NULL,
            source_scenario_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            observation_priority INTEGER NOT NULL,
            plan_status TEXT NOT NULL,
            planned_notional_usd TEXT NOT NULL,
            holding_funding_events INTEGER NOT NULL,
            fee_bps_per_side TEXT NOT NULL,
            slippage_bps TEXT NOT NULL,
            average_funding_rate_bps TEXT NOT NULL,
            latest_spread_bps TEXT NOT NULL,
            gross_horizon_carry_bps TEXT NOT NULL,
            estimated_cost_bps TEXT NOT NULL,
            net_carry_bps TEXT NOT NULL,
            break_even_funding_bps TEXT NOT NULL,
            funding_gap_to_break_even_bps TEXT NOT NULL,
            planning_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_plan(
    conn,
    plan_label="plan-1",
    symbol="BTCUSDT",
    priority=1,
    net_carry_bps=25.0,
    plan_status="PLANNED_SHADOW_OBSERVATION_READY",
    live_order_sent=0,
):
    conn.execute(
        """
        INSERT INTO calibrated_shadow_observation_plans (
            plan_id,
            plan_label,
            created_at,
            source_calibration_label,
            source_scenario_id,
            symbol,
            observation_priority,
            plan_status,
            planned_notional_usd,
            holding_funding_events,
            fee_bps_per_side,
            slippage_bps,
            average_funding_rate_bps,
            latest_spread_bps,
            gross_horizon_carry_bps,
            estimated_cost_bps,
            net_carry_bps,
            break_even_funding_bps,
            funding_gap_to_break_even_bps,
            planning_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{plan_label}-{symbol}",
            plan_label,
            "2026-01-01T00:00:00+00:00",
            "calibration-1",
            f"scenario-{symbol}",
            symbol,
            priority,
            plan_status,
            "1000",
            81,
            "0.1",
            "0.1",
            "0.5",
            "0.1",
            "20.0",
            "1.0",
            str(net_carry_bps),
            "0.01",
            "0.49",
            "test",
            "DISABLED",
            live_order_sent,
            "BLOCKED",
            "{}",
        ),
    )


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_missing_database_returns_no_plan_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_shadow_plan_to_ledger_bridge(
        db_path=db_path,
        bridge_label="missing-bridge",
        report_label="missing-report",
    )

    assert result["global_verdict"] == NO_PLAN_HISTORY_VERDICT
    assert result["ledger_entry_count"] == 0


def test_bridge_creates_shadow_ledger_entries_and_persists(tmp_path):
    db_path = tmp_path / "mission54-ledger.db"

    with sqlite3.connect(db_path) as conn:
        create_plans_table(conn)
        insert_plan(conn, symbol="BTCUSDT", priority=1, net_carry_bps=25.0)
        insert_plan(conn, symbol="ETHUSDT", priority=2, net_carry_bps=9.0)
        insert_plan(conn, symbol="SOLUSDT", priority=3, net_carry_bps=-1.0, plan_status="PLANNED_SHADOW_OBSERVATION_BLOCKED")
        conn.commit()

    result = run_shadow_plan_to_ledger_bridge(
        db_path=db_path,
        bridge_label="mission54-bridge",
        report_label="mission54-report",
        plan_label="plan-1",
        symbols="BTCUSDT,ETHUSDT,SOLUSDT",
        max_entries=2,
        min_net_carry_bps=0.25,
    )

    assert result["global_verdict"] == READY_VERDICT
    assert result["ledger_entry_count"] == 2
    assert result["active_ledger_entry_count"] == 2
    assert result["blocked_ledger_entry_count"] == 0
    assert result["excluded_symbols"] == ["SOLUSDT"]
    assert result["top_symbol"] == "BTCUSDT"
    assert result["ledger_entries"][0]["ledger_status"] == LEDGER_STATUS_ACTIVE

    with sqlite3.connect(db_path) as conn:
        ledger_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM shadow_observation_ledger_entries
            WHERE bridge_label = ?
            """,
            ("mission54-bridge",),
        ).fetchone()[0]

        report = conn.execute(
            """
            SELECT report_label, ledger_entry_count, active_ledger_entry_count, global_verdict
            FROM shadow_plan_to_ledger_bridge_reports
            WHERE report_label = ?
            """,
            ("mission54-report",),
        ).fetchone()

    assert ledger_count == 2
    assert report == ("mission54-report", 2, 2, READY_VERDICT)


def test_bridge_respects_max_entries(tmp_path):
    db_path = tmp_path / "mission54-max.db"

    with sqlite3.connect(db_path) as conn:
        create_plans_table(conn)
        insert_plan(conn, symbol="BTCUSDT", priority=1, net_carry_bps=25.0)
        insert_plan(conn, symbol="ETHUSDT", priority=2, net_carry_bps=9.0)
        conn.commit()

    result = run_shadow_plan_to_ledger_bridge(
        db_path=db_path,
        bridge_label="mission54-max-bridge",
        report_label="mission54-max-report",
        plan_label="plan-1",
        max_entries=1,
    )

    assert result["ledger_entry_count"] == 1
    assert result["top_symbol"] == "BTCUSDT"


def test_bridge_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission54-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_plans_table(conn)
        insert_plan(conn, symbol="BTCUSDT", priority=1, net_carry_bps=25.0, live_order_sent=1)
        conn.commit()

    result = run_shadow_plan_to_ledger_bridge(
        db_path=db_path,
        bridge_label="mission54-safety-bridge",
        report_label="mission54-safety-report",
        plan_label="plan-1",
    )

    assert result["global_verdict"] == SAFETY_BREACH_VERDICT
    assert result["safety_breach_count"] > 0


def test_markdown_report_contains_shadow_safety_statement(tmp_path):
    db_path = tmp_path / "mission54-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_plans_table(conn)
        insert_plan(conn, symbol="BTCUSDT", priority=1, net_carry_bps=25.0)
        conn.commit()

    result = run_shadow_plan_to_ledger_bridge(
        db_path=db_path,
        bridge_label="mission54-markdown-bridge",
        report_label="mission54-markdown-report",
        plan_label="plan-1",
    )

    assert "# DeltaGrid Mission 54" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "No paid APIs were used." in result["markdown_report"]
