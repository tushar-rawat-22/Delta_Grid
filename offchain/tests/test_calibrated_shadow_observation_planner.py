import sqlite3

from offchain.backtest.calibrated_shadow_observation_planner import (
    NO_CALIBRATION_HISTORY_VERDICT,
    PLAN_STATUS_READY,
    READY_VERDICT,
    SAFETY_BREACH_VERDICT,
    parse_symbols,
    run_calibrated_shadow_observation_planner,
)


def create_scenarios_table(conn):
    conn.execute(
        """
        CREATE TABLE cost_calibration_break_even_scenarios (
            scenario_id TEXT PRIMARY KEY,
            calibration_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_scanner_label TEXT,
            source_candidate_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            fee_bps_per_side TEXT NOT NULL,
            slippage_bps TEXT NOT NULL,
            holding_funding_events INTEGER NOT NULL,
            average_funding_rate_bps TEXT NOT NULL,
            latest_spread_bps TEXT NOT NULL,
            gross_horizon_carry_bps TEXT NOT NULL,
            estimated_cost_bps TEXT NOT NULL,
            net_carry_bps TEXT NOT NULL,
            break_even_funding_bps TEXT NOT NULL,
            funding_gap_to_break_even_bps TEXT NOT NULL,
            scenario_status TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_scenario(
    conn,
    calibration_label="calibration-1",
    symbol="BTCUSDT",
    net_carry_bps=10.0,
    status="SCENARIO_POSITIVE_AFTER_COST",
    live_order_sent=0,
):
    conn.execute(
        """
        INSERT INTO cost_calibration_break_even_scenarios (
            scenario_id,
            calibration_label,
            created_at,
            source_scanner_label,
            source_candidate_id,
            symbol,
            fee_bps_per_side,
            slippage_bps,
            holding_funding_events,
            average_funding_rate_bps,
            latest_spread_bps,
            gross_horizon_carry_bps,
            estimated_cost_bps,
            net_carry_bps,
            break_even_funding_bps,
            funding_gap_to_break_even_bps,
            scenario_status,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{calibration_label}-{symbol}-{net_carry_bps}-{status}",
            calibration_label,
            "2026-01-01T00:00:00+00:00",
            "scanner-1",
            f"candidate-{symbol}",
            symbol,
            "0.1",
            "0.1",
            81,
            "0.5",
            "0.1",
            "20.0",
            "1.0",
            str(net_carry_bps),
            "0.01",
            "0.49",
            status,
            "DISABLED",
            live_order_sent,
            "BLOCKED",
            "{}",
        ),
    )


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_missing_database_returns_no_calibration_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_calibrated_shadow_observation_planner(
        db_path=db_path,
        plan_label="missing-plan",
        report_label="missing-report",
    )

    assert result["global_verdict"] == NO_CALIBRATION_HISTORY_VERDICT
    assert result["plan_count"] == 0


def test_planner_creates_best_shadow_plans_and_persists(tmp_path):
    db_path = tmp_path / "mission53-plan.db"

    with sqlite3.connect(db_path) as conn:
        create_scenarios_table(conn)
        insert_scenario(conn, symbol="BTCUSDT", net_carry_bps=25.0)
        insert_scenario(conn, symbol="BTCUSDT", net_carry_bps=10.0)
        insert_scenario(conn, symbol="ETHUSDT", net_carry_bps=9.0)
        insert_scenario(conn, symbol="SOLUSDT", net_carry_bps=-1.0, status="SCENARIO_REJECT_NEGATIVE_AVERAGE_FUNDING")
        conn.commit()

    result = run_calibrated_shadow_observation_planner(
        db_path=db_path,
        plan_label="mission53-plan",
        report_label="mission53-report",
        calibration_label="calibration-1",
        symbols="BTCUSDT,ETHUSDT,SOLUSDT",
        max_plans=2,
        min_net_carry_bps=0.25,
    )

    assert result["global_verdict"] == READY_VERDICT
    assert result["plan_count"] == 2
    assert result["ready_plan_count"] == 2
    assert result["top_symbol"] == "BTCUSDT"
    assert result["plans"][0]["symbol"] == "BTCUSDT"
    assert result["plans"][1]["symbol"] == "ETHUSDT"
    assert result["excluded_symbols"] == ["SOLUSDT"]
    assert result["plans"][0]["plan_status"] == PLAN_STATUS_READY

    with sqlite3.connect(db_path) as conn:
        plan_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM calibrated_shadow_observation_plans
            WHERE plan_label = ?
            """,
            ("mission53-plan",),
        ).fetchone()[0]

        report = conn.execute(
            """
            SELECT report_label, plan_count, ready_plan_count, global_verdict
            FROM calibrated_shadow_observation_plan_reports
            WHERE report_label = ?
            """,
            ("mission53-report",),
        ).fetchone()

    assert plan_count == 2
    assert report == ("mission53-report", 2, 2, READY_VERDICT)


def test_planner_respects_max_plans(tmp_path):
    db_path = tmp_path / "mission53-max.db"

    with sqlite3.connect(db_path) as conn:
        create_scenarios_table(conn)
        insert_scenario(conn, symbol="BTCUSDT", net_carry_bps=25.0)
        insert_scenario(conn, symbol="ETHUSDT", net_carry_bps=9.0)
        conn.commit()

    result = run_calibrated_shadow_observation_planner(
        db_path=db_path,
        plan_label="mission53-max-plan",
        report_label="mission53-max-report",
        calibration_label="calibration-1",
        max_plans=1,
    )

    assert result["plan_count"] == 1
    assert result["top_symbol"] == "BTCUSDT"


def test_planner_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission53-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_scenarios_table(conn)
        insert_scenario(conn, symbol="BTCUSDT", net_carry_bps=25.0, live_order_sent=1)
        conn.commit()

    result = run_calibrated_shadow_observation_planner(
        db_path=db_path,
        plan_label="mission53-safety-plan",
        report_label="mission53-safety-report",
        calibration_label="calibration-1",
    )

    assert result["global_verdict"] == SAFETY_BREACH_VERDICT
    assert result["safety_breach_count"] > 0


def test_markdown_report_contains_shadow_safety_statement(tmp_path):
    db_path = tmp_path / "mission53-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_scenarios_table(conn)
        insert_scenario(conn, symbol="BTCUSDT", net_carry_bps=25.0)
        conn.commit()

    result = run_calibrated_shadow_observation_planner(
        db_path=db_path,
        plan_label="mission53-markdown-plan",
        report_label="mission53-markdown-report",
        calibration_label="calibration-1",
    )

    assert "# DeltaGrid Mission 53" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "No paid APIs were used." in result["markdown_report"]
