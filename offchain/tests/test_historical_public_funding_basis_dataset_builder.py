import sqlite3
import urllib.error

import offchain.backtest.historical_public_funding_basis_dataset_builder as builder
from offchain.backtest.historical_public_funding_basis_dataset_builder import (
    DATASET_READY_VERDICT,
    DATA_MODE_OFFLINE_SAMPLE,
    DATA_MODE_OFFLINE_SAMPLE_FALLBACK,
    LIVE_TRADING_STATUS,
    CAPITAL_DEPLOYMENT_STATUS,
    normalize_funding_record,
    parse_symbols,
    run_historical_public_funding_basis_dataset_builder,
    sample_funding_history,
)


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_normalize_funding_record_calculates_bps_and_annualized():
    row = {
        "symbol": "BTCUSDT",
        "fundingTime": 1700000000000,
        "fundingRate": "0.00010000",
        "markPrice": "62000.00",
    }

    normalized = normalize_funding_record(
        dataset_label="dataset-1",
        symbol="BTCUSDT",
        row=row,
        data_mode=DATA_MODE_OFFLINE_SAMPLE,
    )

    assert normalized["funding_rate"] == 0.0001
    assert normalized["funding_rate_bps"] == 1.0
    assert normalized["annualized_funding_rate"] == 0.1095
    assert normalized["live_trading"] == LIVE_TRADING_STATUS
    assert normalized["capital_deployment"] == CAPITAL_DEPLOYMENT_STATUS


def test_offline_dataset_builder_persists_funding_basis_and_report(tmp_path):
    db_path = tmp_path / "mission50.db"

    result = run_historical_public_funding_basis_dataset_builder(
        db_path=db_path,
        dataset_label="mission50-test-dataset",
        report_label="mission50-test-report",
        symbols="BTCUSDT,ETHUSDT,SOLUSDT",
        funding_limit=5,
        offline_sample=True,
    )

    assert result["global_verdict"] == DATASET_READY_VERDICT
    assert result["symbol_count"] == 3
    assert result["funding_record_count"] == 15
    assert result["basis_observation_count"] == 3
    assert result["successful_symbol_count"] == 3
    assert result["failed_symbol_count"] == 0
    assert result["offline_sample_count"] == 15
    assert result["safety_breach_count"] == 0

    with sqlite3.connect(db_path) as conn:
        funding_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM historical_public_funding_rates
            WHERE dataset_label = ?
            """,
            ("mission50-test-dataset",),
        ).fetchone()[0]

        basis_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM historical_public_basis_observations
            WHERE dataset_label = ?
            """,
            ("mission50-test-dataset",),
        ).fetchone()[0]

        report = conn.execute(
            """
            SELECT report_label, funding_record_count, basis_observation_count, global_verdict
            FROM historical_public_funding_basis_dataset_reports
            WHERE report_label = ?
            """,
            ("mission50-test-report",),
        ).fetchone()

    assert funding_count == 15
    assert basis_count == 3
    assert report == (
        "mission50-test-report",
        15,
        3,
        DATASET_READY_VERDICT,
    )


def test_builder_uses_latest_mission49_basis_snapshot(tmp_path):
    db_path = tmp_path / "mission50-basis.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE real_market_public_data_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                ingestion_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                source TEXT NOT NULL,
                data_mode TEXT NOT NULL,
                mark_price TEXT NOT NULL,
                index_price TEXT NOT NULL,
                basis_bps TEXT NOT NULL,
                last_funding_rate TEXT NOT NULL,
                last_funding_rate_bps TEXT NOT NULL,
                annualized_funding_rate TEXT NOT NULL,
                avg_funding_rate_history TEXT NOT NULL,
                funding_history_count INTEGER NOT NULL,
                bid_price TEXT NOT NULL,
                ask_price TEXT NOT NULL,
                spread_bps TEXT NOT NULL,
                quote_volume TEXT NOT NULL,
                price_change_percent TEXT NOT NULL,
                next_funding_time INTEGER,
                event_time INTEGER,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                error_message TEXT,
                raw_payload_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO real_market_public_data_snapshots (
                snapshot_id, ingestion_label, created_at, symbol, source, data_mode,
                mark_price, index_price, basis_bps, last_funding_rate,
                last_funding_rate_bps, annualized_funding_rate, avg_funding_rate_history,
                funding_history_count, bid_price, ask_price, spread_bps, quote_volume,
                price_change_percent, next_funding_time, event_time, live_trading,
                live_order_sent, capital_deployment, error_message, raw_payload_json, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-btc",
                "mission49-source",
                "2026-01-01T00:00:00+00:00",
                "BTCUSDT",
                "BINANCE_USDS_M_FUTURES_PUBLIC_REST",
                "ONLINE_PUBLIC_API",
                "62001",
                "62000",
                "0.16129",
                "0.0001",
                "1.0",
                "0.1095",
                "0.0001",
                20,
                "62000",
                "62001",
                "0.16129",
                "1000000",
                "1.2",
                1,
                1,
                "DISABLED",
                0,
                "BLOCKED",
                None,
                "{}",
                "{}",
            ),
        )
        conn.commit()

    result = run_historical_public_funding_basis_dataset_builder(
        db_path=db_path,
        dataset_label="mission50-basis-dataset",
        report_label="mission50-basis-report",
        symbols="BTCUSDT",
        funding_limit=3,
        offline_sample=False,
        allow_sample_fallback=True,
        source_ingestion_label="mission49-source",
    )

    assert result["basis_observation_count"] == 1
    assert result["symbol_summary"]["BTCUSDT"]["latest_basis_bps"] == 0.16129


def test_online_failure_can_fallback_to_sample(monkeypatch, tmp_path):
    db_path = tmp_path / "mission50-fallback.db"

    def raising_fetch(symbol, timeout_seconds=10.0, funding_limit=100, start_time=None, end_time=None):
        raise urllib.error.URLError("network disabled in test")

    monkeypatch.setattr(builder, "fetch_online_funding_history", raising_fetch)

    result = run_historical_public_funding_basis_dataset_builder(
        db_path=db_path,
        dataset_label="mission50-fallback-dataset",
        report_label="mission50-fallback-report",
        symbols="BTCUSDT",
        funding_limit=4,
        allow_sample_fallback=True,
    )

    assert result["global_verdict"] == DATASET_READY_VERDICT
    assert result["fallback_count"] == 4
    assert result["failed_symbol_count"] == 0
    assert result["symbol_summary"]["BTCUSDT"]["data_modes"] == [DATA_MODE_OFFLINE_SAMPLE_FALLBACK]


def test_markdown_report_contains_shadow_safety_statement(tmp_path):
    db_path = tmp_path / "mission50-markdown.db"

    result = run_historical_public_funding_basis_dataset_builder(
        db_path=db_path,
        dataset_label="mission50-markdown-dataset",
        report_label="mission50-markdown-report",
        symbols="BTCUSDT",
        funding_limit=3,
        offline_sample=True,
    )

    assert "# DeltaGrid Mission 50" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "No paid APIs were used." in result["markdown_report"]
