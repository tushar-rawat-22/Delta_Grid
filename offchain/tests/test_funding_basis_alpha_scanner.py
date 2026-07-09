import sqlite3

from offchain.backtest.funding_basis_alpha_scanner import (
    APPROVED_VERDICT,
    NO_DATASET_HISTORY_VERDICT,
    SAFETY_BREACH_VERDICT,
    STATUS_APPROVED,
    STATUS_REJECT_UNSTABLE_FUNDING,
    WATCHLIST_VERDICT,
    parse_symbols,
    run_funding_basis_alpha_scanner,
)


def create_dataset_tables(conn):
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

    conn.execute(
        """
        CREATE TABLE historical_public_funding_basis_dataset_reports (
            report_label TEXT PRIMARY KEY,
            dataset_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            symbol_count INTEGER NOT NULL,
            funding_record_count INTEGER NOT NULL,
            basis_observation_count INTEGER NOT NULL,
            successful_symbol_count INTEGER NOT NULL,
            failed_symbol_count INTEGER NOT NULL,
            online_public_api_count INTEGER NOT NULL,
            offline_sample_count INTEGER NOT NULL,
            fallback_count INTEGER NOT NULL,
            positive_funding_record_count INTEGER NOT NULL,
            negative_funding_record_count INTEGER NOT NULL,
            zero_funding_record_count INTEGER NOT NULL,
            average_funding_rate_bps TEXT NOT NULL,
            average_annualized_funding_rate TEXT NOT NULL,
            average_basis_bps TEXT NOT NULL,
            average_spread_bps TEXT NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            global_verdict TEXT NOT NULL,
            recommended_action TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            markdown_report TEXT NOT NULL
        )
        """
    )


def insert_dataset_report(conn, dataset_label="dataset-1"):
    conn.execute(
        """
        INSERT INTO historical_public_funding_basis_dataset_reports (
            report_label,
            dataset_label,
            created_at,
            source,
            symbol_count,
            funding_record_count,
            basis_observation_count,
            successful_symbol_count,
            failed_symbol_count,
            online_public_api_count,
            offline_sample_count,
            fallback_count,
            positive_funding_record_count,
            negative_funding_record_count,
            zero_funding_record_count,
            average_funding_rate_bps,
            average_annualized_funding_rate,
            average_basis_bps,
            average_spread_bps,
            safety_breach_count,
            global_verdict,
            recommended_action,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{dataset_label}-report",
            dataset_label,
            "2026-01-01T00:00:00+00:00",
            "test",
            1,
            10,
            1,
            1,
            0,
            10,
            0,
            0,
            10,
            0,
            0,
            "1.0",
            "0.1095",
            "1.0",
            "0.1",
            0,
            "READY",
            "TEST",
            "{}",
            "# test",
        ),
    )


def insert_funding_series(
    conn,
    dataset_label="dataset-1",
    symbol="BTCUSDT",
    count=40,
    funding_bps=5.0,
    negative_every=None,
    live_order_sent=0,
):
    for index in range(count):
        value = funding_bps

        if negative_every is not None and index % negative_every == 0:
            value = -abs(funding_bps)

        funding_rate = value / 10000.0

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
                1700000000000 + index,
                "2026-01-01T00:00:00+00:00",
                str(funding_rate),
                str(value),
                str(funding_rate * 1095),
                "62000",
                "test",
                "ONLINE_PUBLIC_API",
                "DISABLED",
                live_order_sent,
                "BLOCKED",
                "{}",
                "{}",
            ),
        )


def insert_basis(
    conn,
    dataset_label="dataset-1",
    symbol="BTCUSDT",
    basis_bps="2.0",
    spread_bps="0.1",
):
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
            "62001",
            "62000",
            basis_bps,
            spread_bps,
            "1000000",
            "0.0001",
            "0.1095",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
            "{}",
        ),
    )


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_missing_database_returns_no_dataset_history(tmp_path):
    db_path = tmp_path / "missing.db"

    result = run_funding_basis_alpha_scanner(
        db_path=db_path,
        scanner_label="missing-scanner",
        report_label="missing-report",
    )

    assert result["global_verdict"] == NO_DATASET_HISTORY_VERDICT
    assert result["candidate_count"] == 0


def test_scanner_approves_strong_cost_adjusted_candidate(tmp_path):
    db_path = tmp_path / "mission51-approve.db"

    with sqlite3.connect(db_path) as conn:
        create_dataset_tables(conn)
        insert_dataset_report(conn)
        insert_funding_series(conn, funding_bps=5.0, count=40)
        insert_basis(conn, basis_bps="2.0", spread_bps="0.1")
        conn.commit()

    result = run_funding_basis_alpha_scanner(
        db_path=db_path,
        scanner_label="mission51-approve-scanner",
        report_label="mission51-approve-report",
        dataset_label="dataset-1",
        fee_bps_per_side=0.1,
        slippage_bps=0.1,
        min_cost_adjusted_carry_bps=1.0,
    )

    assert result["global_verdict"] == APPROVED_VERDICT
    assert result["approved_count"] == 1
    assert result["candidates"][0]["scanner_status"] == STATUS_APPROVED

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            """
            SELECT report_label, candidate_count, approved_count, global_verdict
            FROM funding_basis_alpha_scanner_reports
            WHERE report_label = ?
            """,
            ("mission51-approve-report",),
        ).fetchone()

    assert stored == (
        "mission51-approve-report",
        1,
        1,
        APPROVED_VERDICT,
    )


def test_scanner_rejects_unstable_negative_funding(tmp_path):
    db_path = tmp_path / "mission51-reject.db"

    with sqlite3.connect(db_path) as conn:
        create_dataset_tables(conn)
        insert_dataset_report(conn)
        insert_funding_series(conn, funding_bps=1.0, count=40, negative_every=2)
        insert_basis(conn)
        conn.commit()

    result = run_funding_basis_alpha_scanner(
        db_path=db_path,
        scanner_label="mission51-reject-scanner",
        report_label="mission51-reject-report",
        dataset_label="dataset-1",
    )

    assert result["rejected_count"] == 1
    assert result["candidates"][0]["scanner_status"] == STATUS_REJECT_UNSTABLE_FUNDING


def test_scanner_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission51-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_dataset_tables(conn)
        insert_dataset_report(conn)
        insert_funding_series(conn, funding_bps=5.0, count=40, live_order_sent=1)
        insert_basis(conn)
        conn.commit()

    result = run_funding_basis_alpha_scanner(
        db_path=db_path,
        scanner_label="mission51-safety-scanner",
        report_label="mission51-safety-report",
        dataset_label="dataset-1",
    )

    assert result["global_verdict"] == SAFETY_BREACH_VERDICT
    assert result["safety_breach_count"] == 1


def test_scanner_watchlists_promising_but_negative_after_cost(tmp_path):
    db_path = tmp_path / "mission51-watchlist.db"

    with sqlite3.connect(db_path) as conn:
        create_dataset_tables(conn)
        insert_dataset_report(conn)
        insert_funding_series(conn, funding_bps=1.0, count=40)
        insert_basis(conn, basis_bps="0.5", spread_bps="0.5")
        conn.commit()

    result = run_funding_basis_alpha_scanner(
        db_path=db_path,
        scanner_label="mission51-watchlist-scanner",
        report_label="mission51-watchlist-report",
        dataset_label="dataset-1",
        fee_bps_per_side=4.0,
        slippage_bps=3.0,
    )

    assert result["global_verdict"] == WATCHLIST_VERDICT
    assert result["watchlist_count"] == 1
    assert result["candidates"][0]["cost_adjusted_carry_bps"] < 0
    assert "Live trading remains disabled." in result["markdown_report"]
