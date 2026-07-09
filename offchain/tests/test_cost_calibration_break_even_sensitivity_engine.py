import sqlite3

from offchain.backtest.cost_calibration_break_even_sensitivity_engine import (
    NO_SCANNER_HISTORY_VERDICT,
    POSITIVE_SCENARIOS_VERDICT,
    SAFETY_BREACH_VERDICT,
    SYMBOL_POSSIBLE,
    SYMBOL_REJECT_NEGATIVE_AVERAGE,
    parse_float_grid,
    parse_int_grid,
    run_cost_calibration_break_even_sensitivity_engine,
)


def create_candidate_table(conn):
    conn.execute(
        """
        CREATE TABLE funding_basis_alpha_candidates (
            candidate_id TEXT PRIMARY KEY,
            scanner_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_dataset_label TEXT NOT NULL,
            symbol TEXT NOT NULL,
            funding_record_count INTEGER NOT NULL,
            positive_funding_count INTEGER NOT NULL,
            negative_funding_count INTEGER NOT NULL,
            positive_funding_ratio TEXT NOT NULL,
            negative_funding_ratio TEXT NOT NULL,
            average_funding_rate_bps TEXT NOT NULL,
            latest_funding_rate_bps TEXT NOT NULL,
            funding_volatility_bps TEXT NOT NULL,
            latest_basis_bps TEXT NOT NULL,
            latest_spread_bps TEXT NOT NULL,
            quote_volume TEXT NOT NULL,
            gross_horizon_carry_bps TEXT NOT NULL,
            estimated_cost_bps TEXT NOT NULL,
            cost_adjusted_carry_bps TEXT NOT NULL,
            alpha_score TEXT NOT NULL,
            candidate_rank INTEGER NOT NULL,
            scanner_status TEXT NOT NULL,
            scanner_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            risk_flags_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_candidate(
    conn,
    scanner_label="scanner-1",
    symbol="BTCUSDT",
    average_funding_bps=1.0,
    spread_bps=0.1,
    rank=1,
    live_order_sent=0,
    scanner_status="WATCHLIST_NEGATIVE_AFTER_COST",
):
    conn.execute(
        """
        INSERT INTO funding_basis_alpha_candidates (
            candidate_id,
            scanner_label,
            created_at,
            source_dataset_label,
            symbol,
            funding_record_count,
            positive_funding_count,
            negative_funding_count,
            positive_funding_ratio,
            negative_funding_ratio,
            average_funding_rate_bps,
            latest_funding_rate_bps,
            funding_volatility_bps,
            latest_basis_bps,
            latest_spread_bps,
            quote_volume,
            gross_horizon_carry_bps,
            estimated_cost_bps,
            cost_adjusted_carry_bps,
            alpha_score,
            candidate_rank,
            scanner_status,
            scanner_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            risk_flags_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{scanner_label}-{symbol}",
            scanner_label,
            "2026-01-01T00:00:00+00:00",
            "dataset-1",
            symbol,
            100,
            80,
            20,
            "0.8",
            "0.2",
            str(average_funding_bps),
            str(average_funding_bps),
            "0.1",
            "0.0",
            str(spread_bps),
            "1000000",
            "0.0",
            "0.0",
            "-1.0",
            "1.0",
            rank,
            scanner_status,
            "test",
            "DISABLED",
            live_order_sent,
            "BLOCKED",
            "[]",
            "{}",
        ),
    )


def test_grid_parsers_deduplicate_and_sort():
    assert parse_float_grid("4,0.1,1,0.1", default=[1.0]) == [0.1, 1.0, 4.0]
    assert parse_int_grid("9,1,3,3", default=[1]) == [1, 3, 9]


def test_missing_database_returns_no_scanner_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_cost_calibration_break_even_sensitivity_engine(
        db_path=db_path,
        calibration_label="missing-calibration",
        report_label="missing-report",
    )

    assert result["global_verdict"] == NO_SCANNER_HISTORY_VERDICT
    assert result["candidate_count"] == 0


def test_positive_scenarios_are_found_and_persisted(tmp_path):
    db_path = tmp_path / "mission52-positive.db"

    with sqlite3.connect(db_path) as conn:
        create_candidate_table(conn)
        insert_candidate(conn, average_funding_bps=2.0, spread_bps=0.1)
        conn.commit()

    result = run_cost_calibration_break_even_sensitivity_engine(
        db_path=db_path,
        calibration_label="mission52-positive",
        report_label="mission52-positive-report",
        scanner_label="scanner-1",
        fee_bps_grid="0.1,4.0",
        slippage_bps_grid="0.1,3.0",
        holding_events_grid="1,3",
    )

    assert result["global_verdict"] == POSITIVE_SCENARIOS_VERDICT
    assert result["candidate_count"] == 1
    assert result["positive_scenario_count"] > 0
    assert result["symbol_summaries"][0]["calibration_status"] == SYMBOL_POSSIBLE

    with sqlite3.connect(db_path) as conn:
        scenario_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM cost_calibration_break_even_scenarios
            WHERE calibration_label = ?
            """,
            ("mission52-positive",),
        ).fetchone()[0]

        report = conn.execute(
            """
            SELECT report_label, candidate_count, positive_scenario_count, global_verdict
            FROM cost_calibration_break_even_reports
            WHERE report_label = ?
            """,
            ("mission52-positive-report",),
        ).fetchone()

    assert scenario_count == 8
    assert report[0] == "mission52-positive-report"
    assert report[1] == 1
    assert report[2] > 0
    assert report[3] == POSITIVE_SCENARIOS_VERDICT


def test_negative_average_funding_is_rejected(tmp_path):
    db_path = tmp_path / "mission52-negative.db"

    with sqlite3.connect(db_path) as conn:
        create_candidate_table(conn)
        insert_candidate(conn, symbol="SOLUSDT", average_funding_bps=-0.5, spread_bps=1.0)
        conn.commit()

    result = run_cost_calibration_break_even_sensitivity_engine(
        db_path=db_path,
        calibration_label="mission52-negative",
        report_label="mission52-negative-report",
        scanner_label="scanner-1",
        fee_bps_grid="0.1",
        slippage_bps_grid="0.1",
        holding_events_grid="1,3,9",
    )

    assert result["positive_scenario_count"] == 0
    assert result["symbol_summaries"][0]["calibration_status"] == SYMBOL_REJECT_NEGATIVE_AVERAGE


def test_safety_breach_blocks_calibration(tmp_path):
    db_path = tmp_path / "mission52-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_candidate_table(conn)
        insert_candidate(conn, average_funding_bps=2.0, live_order_sent=1)
        conn.commit()

    result = run_cost_calibration_break_even_sensitivity_engine(
        db_path=db_path,
        calibration_label="mission52-safety",
        report_label="mission52-safety-report",
        scanner_label="scanner-1",
        fee_bps_grid="0.1",
        slippage_bps_grid="0.1",
        holding_events_grid="1",
    )

    assert result["global_verdict"] == SAFETY_BREACH_VERDICT
    assert result["safety_breach_count"] == 1


def test_markdown_report_contains_shadow_safety_statement(tmp_path):
    db_path = tmp_path / "mission52-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_candidate_table(conn)
        insert_candidate(conn, average_funding_bps=2.0)
        conn.commit()

    result = run_cost_calibration_break_even_sensitivity_engine(
        db_path=db_path,
        calibration_label="mission52-markdown",
        report_label="mission52-markdown-report",
        scanner_label="scanner-1",
        fee_bps_grid="0.1",
        slippage_bps_grid="0.1",
        holding_events_grid="1",
    )

    assert "# DeltaGrid Mission 52" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "No paid APIs were used." in result["markdown_report"]
