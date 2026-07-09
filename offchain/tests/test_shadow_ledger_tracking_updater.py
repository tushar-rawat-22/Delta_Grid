import sqlite3

from offchain.backtest.shadow_ledger_tracking_updater import (
    ACTIVE_VERDICT,
    NO_LEDGER_HISTORY_VERDICT,
    SAFETY_BREACH_VERDICT,
    UPDATE_STATUS_ACTIVE,
    UPDATE_STATUS_INVALIDATED_NEGATIVE_FUNDING,
    parse_symbols,
    run_shadow_ledger_tracking_updater,
)


def create_ledger_table(conn):
    conn.execute(
        """
        CREATE TABLE shadow_observation_ledger_entries (
            ledger_entry_id TEXT PRIMARY KEY,
            bridge_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_plan_label TEXT NOT NULL,
            source_plan_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            observation_priority INTEGER NOT NULL,
            ledger_status TEXT NOT NULL,
            shadow_notional_usd TEXT NOT NULL,
            planned_holding_funding_events INTEGER NOT NULL,
            remaining_holding_funding_events INTEGER NOT NULL,
            fee_bps_per_side TEXT NOT NULL,
            slippage_bps TEXT NOT NULL,
            average_funding_rate_bps TEXT NOT NULL,
            latest_spread_bps TEXT NOT NULL,
            gross_horizon_carry_bps TEXT NOT NULL,
            estimated_cost_bps TEXT NOT NULL,
            expected_net_carry_bps TEXT NOT NULL,
            break_even_funding_bps TEXT NOT NULL,
            funding_gap_to_break_even_bps TEXT NOT NULL,
            observation_state TEXT NOT NULL,
            ledger_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def create_market_tables(conn):
    conn.execute(
        """
        CREATE TABLE historical_public_funding_rates (
            dataset_label TEXT NOT NULL,
            symbol TEXT NOT NULL,
            funding_time INTEGER NOT NULL,
            funding_time_iso TEXT NOT NULL,
            funding_rate TEXT NOT NULL,
            funding_rate_bps TEXT NOT NULL,
            annualized_funding_rate TEXT NOT NULL,
            mark_price TEXT NOT NULL,
            source TEXT NOT NULL,
            data_mode TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            raw_payload_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            PRIMARY KEY (dataset_label, symbol, funding_time)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE historical_public_basis_observations (
            basis_id TEXT PRIMARY KEY,
            dataset_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            source_snapshot_id TEXT,
            source_ingestion_label TEXT,
            source TEXT NOT NULL,
            data_mode TEXT NOT NULL,
            mark_price TEXT NOT NULL,
            index_price TEXT NOT NULL,
            basis_bps TEXT NOT NULL,
            spread_bps TEXT NOT NULL,
            quote_volume TEXT NOT NULL,
            last_funding_rate TEXT NOT NULL,
            annualized_funding_rate TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            raw_payload_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_ledger_entry(
    conn,
    bridge_label="bridge-1",
    symbol="BTCUSDT",
    priority=1,
    remaining_events=81,
    expected_net_carry_bps=25.0,
    estimated_cost_bps=0.3,
    live_order_sent=0,
):
    conn.execute(
        """
        INSERT INTO shadow_observation_ledger_entries (
            ledger_entry_id,
            bridge_label,
            created_at,
            source_plan_label,
            source_plan_id,
            symbol,
            observation_priority,
            ledger_status,
            shadow_notional_usd,
            planned_holding_funding_events,
            remaining_holding_funding_events,
            fee_bps_per_side,
            slippage_bps,
            average_funding_rate_bps,
            latest_spread_bps,
            gross_horizon_carry_bps,
            estimated_cost_bps,
            expected_net_carry_bps,
            break_even_funding_bps,
            funding_gap_to_break_even_bps,
            observation_state,
            ledger_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{bridge_label}-{symbol}",
            bridge_label,
            "2026-01-01T00:00:00+00:00",
            "plan-1",
            f"plan-{symbol}",
            symbol,
            priority,
            "LEDGER_ENTRY_ACTIVE_SHADOW_TRACKING",
            "1000",
            81,
            remaining_events,
            "0.1",
            "0.1",
            "0.5",
            "0.1",
            "20.0",
            str(estimated_cost_bps),
            str(expected_net_carry_bps),
            "0.01",
            "0.49",
            "TRACKING_NOT_STARTED_SHADOW_ONLY",
            "test",
            "DISABLED",
            live_order_sent,
            "BLOCKED",
            "{}",
        ),
    )


def insert_market_data(
    conn,
    dataset_label="dataset-1",
    symbol="BTCUSDT",
    funding_bps=0.6,
    basis_bps=-2.0,
    spread_bps=0.05,
):
    conn.execute(
        """
        INSERT INTO historical_public_funding_rates (
            dataset_label,
            symbol,
            funding_time,
            funding_time_iso,
            funding_rate,
            funding_rate_bps,
            annualized_funding_rate,
            mark_price,
            source,
            data_mode,
            live_trading,
            live_order_sent,
            capital_deployment,
            raw_payload_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_label,
            symbol,
            1700000000000,
            "2026-01-01T00:00:00+00:00",
            str(funding_bps / 10000.0),
            str(funding_bps),
            "0.1",
            "100",
            "test",
            "ONLINE_PUBLIC_API",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
            "{}",
        ),
    )

    conn.execute(
        """
        INSERT INTO historical_public_basis_observations (
            basis_id,
            dataset_label,
            created_at,
            symbol,
            source_snapshot_id,
            source_ingestion_label,
            source,
            data_mode,
            mark_price,
            index_price,
            basis_bps,
            spread_bps,
            quote_volume,
            last_funding_rate,
            annualized_funding_rate,
            live_trading,
            live_order_sent,
            capital_deployment,
            raw_payload_json,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{dataset_label}-{symbol}-basis",
            dataset_label,
            "2026-01-01T00:00:00+00:00",
            symbol,
            None,
            None,
            "test",
            "ONLINE_PUBLIC_API",
            "100",
            "100",
            str(basis_bps),
            str(spread_bps),
            "1000000",
            str(funding_bps / 10000.0),
            "0.1",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
            "{}",
        ),
    )


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_missing_database_returns_no_ledger_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_shadow_ledger_tracking_updater(
        db_path=db_path,
        update_label="missing-update",
        report_label="missing-report",
    )

    assert result["global_verdict"] == NO_LEDGER_HISTORY_VERDICT
    assert result["tracking_update_count"] == 0


def test_tracking_update_keeps_entries_active_and_persists(tmp_path):
    db_path = tmp_path / "mission55-active.db"

    with sqlite3.connect(db_path) as conn:
        create_ledger_table(conn)
        create_market_tables(conn)
        insert_ledger_entry(conn, symbol="BTCUSDT", priority=1, expected_net_carry_bps=25.0)
        insert_ledger_entry(conn, symbol="ETHUSDT", priority=2, expected_net_carry_bps=9.0)
        insert_market_data(conn, symbol="BTCUSDT", funding_bps=0.6, spread_bps=0.05)
        insert_market_data(conn, symbol="ETHUSDT", funding_bps=0.7, spread_bps=0.05)
        conn.commit()

    result = run_shadow_ledger_tracking_updater(
        db_path=db_path,
        update_label="mission55-active",
        report_label="mission55-active-report",
        bridge_label="bridge-1",
        market_dataset_label="dataset-1",
        symbols="BTCUSDT,ETHUSDT",
        observed_funding_events_increment=1,
    )

    assert result["global_verdict"] == ACTIVE_VERDICT
    assert result["tracking_update_count"] == 2
    assert result["active_after_update_count"] == 2
    assert result["tracking_updates"][0]["update_status"] == UPDATE_STATUS_ACTIVE

    with sqlite3.connect(db_path) as conn:
        update_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM shadow_ledger_tracking_updates
            WHERE update_label = ?
            """,
            ("mission55-active",),
        ).fetchone()[0]

        remaining = conn.execute(
            """
            SELECT remaining_holding_funding_events
            FROM shadow_observation_ledger_entries
            WHERE ledger_entry_id = ?
            """,
            ("bridge-1-BTCUSDT",),
        ).fetchone()[0]

        report = conn.execute(
            """
            SELECT report_label, tracking_update_count, active_after_update_count, global_verdict
            FROM shadow_ledger_tracking_update_reports
            WHERE report_label = ?
            """,
            ("mission55-active-report",),
        ).fetchone()

    assert update_count == 2
    assert remaining == 80
    assert report == ("mission55-active-report", 2, 2, ACTIVE_VERDICT)


def test_negative_funding_invalidates_entry(tmp_path):
    db_path = tmp_path / "mission55-negative.db"

    with sqlite3.connect(db_path) as conn:
        create_ledger_table(conn)
        create_market_tables(conn)
        insert_ledger_entry(conn, symbol="BTCUSDT", expected_net_carry_bps=25.0)
        insert_market_data(conn, symbol="BTCUSDT", funding_bps=-0.1, spread_bps=0.05)
        conn.commit()

    result = run_shadow_ledger_tracking_updater(
        db_path=db_path,
        update_label="mission55-negative",
        report_label="mission55-negative-report",
        bridge_label="bridge-1",
        market_dataset_label="dataset-1",
    )

    assert result["invalidated_count"] == 1
    assert result["tracking_updates"][0]["update_status"] == UPDATE_STATUS_INVALIDATED_NEGATIVE_FUNDING


def test_safety_breach_blocks_tracking(tmp_path):
    db_path = tmp_path / "mission55-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_ledger_table(conn)
        create_market_tables(conn)
        insert_ledger_entry(conn, symbol="BTCUSDT", live_order_sent=1)
        insert_market_data(conn, symbol="BTCUSDT", funding_bps=0.6)
        conn.commit()

    result = run_shadow_ledger_tracking_updater(
        db_path=db_path,
        update_label="mission55-safety",
        report_label="mission55-safety-report",
        bridge_label="bridge-1",
        market_dataset_label="dataset-1",
    )

    assert result["global_verdict"] == SAFETY_BREACH_VERDICT
    assert result["safety_breach_count"] > 0


def test_markdown_report_contains_shadow_safety_statement(tmp_path):
    db_path = tmp_path / "mission55-markdown.db"

    with sqlite3.connect(db_path) as conn:
        create_ledger_table(conn)
        create_market_tables(conn)
        insert_ledger_entry(conn, symbol="BTCUSDT")
        insert_market_data(conn, symbol="BTCUSDT", funding_bps=0.6)
        conn.commit()

    result = run_shadow_ledger_tracking_updater(
        db_path=db_path,
        update_label="mission55-markdown",
        report_label="mission55-markdown-report",
        bridge_label="bridge-1",
        market_dataset_label="dataset-1",
    )

    assert "# DeltaGrid Mission 55" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "No paid APIs were used." in result["markdown_report"]
