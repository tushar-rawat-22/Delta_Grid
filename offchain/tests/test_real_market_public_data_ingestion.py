import sqlite3
import urllib.error

import offchain.backtest.real_market_public_data_ingestion as ingestion
from offchain.backtest.real_market_public_data_ingestion import (
    DATA_MODE_OFFLINE_SAMPLE,
    DATA_MODE_OFFLINE_SAMPLE_FALLBACK,
    INGESTION_SUCCESS_VERDICT,
    LIVE_TRADING_STATUS,
    CAPITAL_DEPLOYMENT_STATUS,
    normalize_symbol_payload,
    parse_symbols,
    run_real_market_public_data_ingestion,
    sample_symbol_payload,
)


def test_parse_symbols_deduplicates_and_uppercases():
    assert parse_symbols("btcusdt, ETHUSDT,btcusdt") == ["BTCUSDT", "ETHUSDT"]


def test_parse_symbols_rejects_non_usdt_symbol():
    try:
        parse_symbols("BTCUSD")
    except ValueError as exc:
        assert "Only USDT perpetual symbols" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_normalize_sample_payload_calculates_basis_and_spread():
    payload = sample_symbol_payload("BTCUSDT", DATA_MODE_OFFLINE_SAMPLE)
    row = normalize_symbol_payload(
        payload,
        ingestion_label="test-ingestion",
        created_at="2026-01-01T00:00:00+00:00",
    )

    assert row["symbol"] == "BTCUSDT"
    assert row["basis_bps"] > 0
    assert row["spread_bps"] > 0
    assert row["last_funding_rate"] > 0
    assert row["annualized_funding_rate"] > 0
    assert row["live_trading"] == LIVE_TRADING_STATUS
    assert row["capital_deployment"] == CAPITAL_DEPLOYMENT_STATUS


def test_offline_ingestion_persists_snapshots_and_report(tmp_path):
    db_path = tmp_path / "mission49.db"

    result = run_real_market_public_data_ingestion(
        db_path=db_path,
        ingestion_label="mission49-test-ingestion",
        report_label="mission49-test-report",
        symbols="BTCUSDT,ETHUSDT,SOLUSDT",
        offline_sample=True,
    )

    assert result["global_verdict"] == INGESTION_SUCCESS_VERDICT
    assert result["symbol_count"] == 3
    assert result["successful_symbol_count"] == 3
    assert result["failed_symbol_count"] == 0
    assert result["offline_sample_count"] == 3
    assert result["safety_breach_count"] == 0

    with sqlite3.connect(db_path) as conn:
        snapshot_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM real_market_public_data_snapshots
            WHERE ingestion_label = ?
            """,
            ("mission49-test-ingestion",),
        ).fetchone()[0]

        report = conn.execute(
            """
            SELECT report_label, symbol_count, successful_symbol_count, global_verdict
            FROM real_market_public_data_reports
            WHERE report_label = ?
            """,
            ("mission49-test-report",),
        ).fetchone()

    assert snapshot_count == 3
    assert report == (
        "mission49-test-report",
        3,
        3,
        INGESTION_SUCCESS_VERDICT,
    )


def test_online_failure_can_fallback_to_sample(monkeypatch, tmp_path):
    db_path = tmp_path / "mission49-fallback.db"

    def raising_fetch(symbol, timeout_seconds=10.0, funding_limit=20):
        raise urllib.error.URLError("network disabled in test")

    monkeypatch.setattr(ingestion, "fetch_online_symbol_payload", raising_fetch)

    result = run_real_market_public_data_ingestion(
        db_path=db_path,
        ingestion_label="mission49-fallback-ingestion",
        report_label="mission49-fallback-report",
        symbols="BTCUSDT",
        allow_sample_fallback=True,
    )

    assert result["global_verdict"] == INGESTION_SUCCESS_VERDICT
    assert result["fallback_count"] == 1
    assert result["failed_symbol_count"] == 0
    assert result["snapshots"][0]["data_mode"] == DATA_MODE_OFFLINE_SAMPLE_FALLBACK
    assert "network disabled in test" in result["snapshots"][0]["error_message"]


def test_markdown_report_contains_shadow_safety_statement(tmp_path):
    db_path = tmp_path / "mission49-markdown.db"

    result = run_real_market_public_data_ingestion(
        db_path=db_path,
        ingestion_label="mission49-markdown-ingestion",
        report_label="mission49-markdown-report",
        symbols="BTCUSDT",
        offline_sample=True,
    )

    assert "# DeltaGrid Mission 49" in result["markdown_report"]
    assert "Live trading remains disabled." in result["markdown_report"]
    assert "No paid APIs were used." in result["markdown_report"]
