import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from db.schema import init_market_database

from backtest.funding_basis_model import ensure_schema as ensure_funding_basis_schema

from backtest.funding_basis_ingestion import (
    build_url,
    ensure_ingestion_schema,
    extract_premium_index,
    fetch_binance_funding_rates,
    fetch_binance_open_interest,
    fetch_binance_premium_index,
    ingest_binance_funding_basis,
    latest_funding_record,
    milliseconds_to_utc,
    prepare_database,
)


class FundingBasisIngestionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "funding_basis_ingestion_test.db")

        init_market_database(self.db_path)
        ensure_funding_basis_schema(self.db_path)
        ensure_ingestion_schema(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def fake_client(self, endpoint, params, timeout):
        if endpoint == "/fapi/v1/fundingRate":
            return [
                {
                    "symbol": "ETHUSDT",
                    "fundingRate": "0.00010000",
                    "fundingTime": 1720396800000,
                    "markPrice": "3100.00",
                },
                {
                    "symbol": "ETHUSDT",
                    "fundingRate": "0.00020000",
                    "fundingTime": 1720425600000,
                    "markPrice": "3106.20",
                },
            ]

        if endpoint == "/fapi/v1/premiumIndex":
            return {
                "symbol": "ETHUSDT",
                "markPrice": "3106.20",
                "indexPrice": "3100.00",
                "lastFundingRate": "0.00020000",
                "nextFundingTime": 1720454400000,
                "time": 1720425600000,
            }

        if endpoint == "/fapi/v1/openInterest":
            return {
                "symbol": "ETHUSDT",
                "openInterest": "1000000.00",
                "time": 1720425600000,
            }

        raise AssertionError(f"Unexpected endpoint: {endpoint}")

    def test_milliseconds_to_utc(self):
        timestamp = milliseconds_to_utc(1720425600000)

        self.assertEqual(timestamp, "2024-07-08T08:00:00Z")

    def test_build_url(self):
        url = build_url(
            "https://example.com",
            "/test",
            {
                "symbol": "ETHUSDT",
                "limit": 2,
            },
        )

        self.assertEqual(
            url,
            "https://example.com/test?symbol=ETHUSDT&limit=2",
        )

    def test_fetch_functions_with_fake_client(self):
        funding = fetch_binance_funding_rates(
            symbol="ETHUSDT",
            limit=2,
            client=self.fake_client,
        )

        premium = fetch_binance_premium_index(
            symbol="ETHUSDT",
            client=self.fake_client,
        )

        open_interest = fetch_binance_open_interest(
            symbol="ETHUSDT",
            client=self.fake_client,
        )

        self.assertEqual(len(funding), 2)
        self.assertEqual(premium["markPrice"], "3106.20")
        self.assertEqual(open_interest["openInterest"], "1000000.00")

    def test_extract_premium_index_from_list(self):
        payload = [
            {
                "symbol": "BTCUSDT",
                "markPrice": "60000",
            },
            {
                "symbol": "ETHUSDT",
                "markPrice": "3106.20",
            },
        ]

        result = extract_premium_index(payload, "ETHUSDT")

        self.assertEqual(result["markPrice"], "3106.20")

    def test_latest_funding_record(self):
        records = [
            {
                "fundingTime": 1000,
                "fundingRate": "0.0001",
            },
            {
                "fundingTime": 3000,
                "fundingRate": "0.0003",
            },
            {
                "fundingTime": 2000,
                "fundingRate": "0.0002",
            },
        ]

        latest = latest_funding_record(records)

        self.assertEqual(latest["fundingRate"], "0.0003")

    def test_ingest_binance_funding_basis_with_fake_client(self):
        result = ingest_binance_funding_basis(
            db_path=self.db_path,
            symbol="ETHUSDT",
            run_label="test_ingestion",
            funding_limit=2,
            interval_hours=Decimal("8"),
            client=self.fake_client,
        )

        self.assertEqual(result["global_verdict"], "REAL_INGESTION_READY_NO_LIVE_TRADING")
        self.assertEqual(result["funding_rows_ingested"], 2)
        self.assertEqual(result["mark_rows_ingested"], 1)
        self.assertEqual(result["basis_snapshots_created"], 1)
        self.assertEqual(result["candidates_created"], 1)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        funding_count = cur.execute("""
        SELECT COUNT(*)
        FROM funding_rates
        WHERE source = 'test_ingestion'
        """).fetchone()[0]

        run_count = cur.execute("""
        SELECT COUNT(*)
        FROM funding_basis_ingestion_runs
        WHERE run_label = 'test_ingestion'
        """).fetchone()[0]

        candidate = cur.execute("""
        SELECT verdict
        FROM delta_neutral_research_candidates
        ORDER BY id DESC
        LIMIT 1
        """).fetchone()[0]

        conn.close()

        self.assertEqual(funding_count, 2)
        self.assertEqual(run_count, 1)
        self.assertEqual(candidate, "GO_FOR_RESEARCH")


if __name__ == "__main__":
    unittest.main()
