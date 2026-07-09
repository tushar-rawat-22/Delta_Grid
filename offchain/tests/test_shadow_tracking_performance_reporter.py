import sqlite3

from offchain.backtest.shadow_tracking_performance_reporter import (
    NO_TRACKING_HISTORY_VERDICT,
    SAFETY_BREACH_VERDICT,
    STRONG_VERDICT,
    SYMBOL_HEALTH_STRONG,
    parse_symbols,
    run_shadow_tracking_performance_reporter,
)


def create_tracking_updates_table(conn):
    conn.execute(
        """
        CREATE TABLE shadow_ledger_tracking_updates (
            tracking_update_id TEXT PRIMARY KEY,
            update_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_bridge_label TEXT,
            source_ledger_entry_id TEXT NOT NULL,
            source_market_dataset_label TEXT,
            symbol TEXT NOT NULL,
            previous_remaining_funding_events INTEGER NOT NULL,
            observed_funding_events_increment INTEGER NOT NULL,
            remaining_funding_events_after_update INTEGER NOT NULL,
            latest_funding_rate_bps TEXT NOT NULL,
            latest_basis_bps TEXT NOT NULL,
            latest_spread_bps TEXT NOT NULL,
            previous_expected_net_carry_bps TEXT NOT NULL,
            updated_expected_remaining_carry_bps TEXT NOT NULL,
            carry_drift_bps TEXT NOT NULL,
            update_status TEXT NOT NULL,
            observation_state_after TEXT NOT NULL,
            update_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_tracking_update(
    conn,
    update_label="update-1",
    symbol="BTCUSDT",
    updated_carry_bps=25.0,
    drift_bps=5.0,
    funding_bps=0.6,
    spread_bps=0.05,
    remaining_events=79,
    update_status="TRACKING_UPDATE_ACTIVE_SHADOW_ONLY",
    live_order_sent=0,
):
    conn.execute(
        """
        INSERT INTO shadow_ledger_tracking_updates (
            tracking_update_id,
            update_label,
            created_at,
            source_bridge_label,
            source_ledger_entry_id,
            source_market_dataset_label,
            symbol,
            previous_remaining_funding_events,
            observed_funding_events_increment,
            remaining_funding_events_after_update,
            latest_funding_rate_bps,
            latest_basis_bps,
            latest_spread_bps,
            previous_expected_net_carry_bps,
            updated_expected_remaining_carry_bps,
            carry_drift_bps,
            update_status,
            observation_state_after,
            update_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{update_label}-{symbol}",
            update_label,
            "2026-01-01T00:00:00+00:00",
            "bridge-1",
            f"ledger-{symbol}",
            "dataset-1",
            symbol,
            80,
            1,
            remaining_events,
            str(funding_bps),
            "-1.0",
            str(spread_bps),
            "20.0",
            str(updated_carry_bps),
            str(drift_bps),
            update_status,
            "TRACKING_ACTIVE_SHADOW_ONLY",
            "test",
            "DISABLED",
            live_order_sent,
            "BLOCKED",
            "{}",
        ),
    )


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_missing_database_returns_no_tracking_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_shadow_tracking_performance_reporter(
        db_path=db_path,
        performance_label="missing-performance",
        report_label="missing-report",
    )

    assert result["global_verdict"] == NO_TRACKING_HISTORY_VERDICT
    assert result["tracking_update_count"] == 0


def test_performance_reporter_marks_strong_and_persists(tmp_path):
    db_path = tmp_path / "mission56-strong.db"

    with sqlite3.connect(db_path) as conn:
        create_tracking_updates_table(conn)
        insert_tracking_update(conn, symbol="BTCUSDT", updated_carry_bps=25.0, drift_bps=5.0)
        insert_tracking_update(conn, symbol="ETHUSDT", updated_carry_bps=15.0, drift_bps=4.0)
        conn.commit()

    result = run_shadow_tracking_performance_reporter(
        db_path=db_path,
        performance_label="mission56-strong",
        report_label="mission56-strong-report",
        update_label="update-1",
        symbols="BTCUSDT,ETHUSDT",
        strong_carry_bps=10.0,
        min_funding_bps=0.0,
        max_spread_bps=1.0,
    )

    assert result["global_verdict"] == STRONG_VERDICT
    assert result["tracking_update_count"] == 2
    assert result["active_count"] == 2
    assert result["invalidated_count"] == 0
    assert result["strongest_symbol"] == "BTCUSDT"
    assert result["symbol_summaries"][0]["health_status"] == SYMBOL_HEALTH_STRONG

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            """
            SELECT report_label, tracking_update_count, active_count, global_verdict
            FROM shadow_tracking_performance_reports
            WHERE report_label = ?
            """,
            ("mission56-strong-report",),
        ).fetchone()

    assert stored == ("mission56-strong-report", 2, 2, STRONG_VERDICT)


def test_performance_reporter_detects_invalidated_updates(tmp_path):
    db_path = tmp_path / "mission56-invalidated.db"

    with sqlite3.connect(db_path) as conn:
        create_tracking_updates_table(conn)
        insert_tracking_update(
            conn,
            symbol="BTCUSDT",
            updated_carry_bps=-1.0,
            drift_bps=-5.0,
            update_status="TRACKING_UPDATE_INVALIDATED_NEGATIVE_FUNDING",
        )
        conn.commit()

    result = run_shadow_tracking_performance_reporter(
        db_path=db_path,
        performance_label="mission56-invalidated",
        report_label="mission56-invalidated-report",
        update_label="update-1",
    )

    assert result["invalidated_count"] == 1
    assert result["global_verdict"] == "TRACKING_PERFORMANCE_INVALIDATED_SHADOW_ONLY"


def test_performance_reporter_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission56-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_tracking_updates_table(conn)
        insert_tracking_update(conn, symbol="BTCUSDT", live_order_sent=1)
        conn.commit()

    result = run_shadow_tracking_performance_reporter(
        db_path=db_path,
        performance_label="mission56-safety",
        report_label="mission56-safety-report",
        update_label="update-1",
    )

    assert result["global_verdict"] == SAFETY_BREACH_VERDICT
    assert result["safety_breach_count"] > 0


def test_markdown_report_contains_shadow_safety_statement(tmp_path):
    db_path = tmp_path / "mission56-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_tracking_updates_table(conn)
        insert_tracking_update(conn, symbol="BTCUSDT")
        conn.commit()

    result = run_shadow_tracking_performance_reporter(
        db_path=db_path,
        performance_label="mission56-markdown",
        report_label="mission56-markdown-report",
        update_label="update-1",
    )

    assert "# DeltaGrid Mission 56" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "No paid APIs were used." in result["markdown_report"]
